"""Local library search — books you already have.

Acquisition's best case is the one that needs no download at all: the text is
already on your disk. This indexes the directories named in the manifest's
`acquisition.local_library` and matches them against the source list, so Phase 0
checks what you own before it goes looking anywhere else.

It is also the extension point. `acquisition.fetch_command` is a shell template
the acquisition stage runs for a source it could not find locally or
open-access. What that command does is the operator's decision and the
operator's configuration — this module only substitutes the fields and reports
whether a file appeared.

Matching is deliberately conservative. A wrong match silently attributes claims
to a book that was never read, which is the worst failure this pipeline has, so
a candidate must agree on a distinctive title token *and* either the author
surname or the year before it is offered — and it is offered to the agent as a
candidate to confirm, never auto-accepted.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

__all__ = ["LibraryMatch", "index_library", "match_sources", "run_fetch_command", "TEXT_SUFFIXES"]

TEXT_SUFFIXES = (".txt", ".md", ".pdf", ".epub", ".djvu", ".mobi", ".azw3", ".html", ".htm")

# Tokens too common in academic titles to identify anything.
_STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "with", "from", "its",
    "introduction", "guide", "handbook", "history", "study", "studies", "analysis", "essays",
    "volume", "edition", "second", "third", "new", "modern", "complete", "collected",
}
_MIN_TOKEN = 4


@dataclass
class LibraryMatch:
    slug: str
    path: Path
    score: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"slug": self.slug, "path": str(self.path), "score": round(self.score, 2), "reason": self.reason}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) >= _MIN_TOKEN and w not in _STOPWORDS}


def index_library(roots: Iterable[Path | str], *, max_files: int = 20_000) -> list[Path]:
    """Every plausibly-readable file under `roots`, deduplicated."""
    seen: set[Path] = set()
    out: list[Path] = []
    for root in roots:
        base = Path(root).expanduser()
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if len(out) >= max_files:
                return out
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            out.append(path)
    return out


def match_sources(
    sources: list[dict[str, Any]], files: list[Path], *, min_score: float = 0.5
) -> dict[str, list[LibraryMatch]]:
    """Candidate local files per source slug, best first.

    A candidate needs a distinctive title token *and* corroboration from the
    author surname or the year. Title overlap alone matches far too much — every
    Antikythera paper shares "antikythera" — and a wrong match is worse than no
    match, because it attributes claims to a work nobody read.
    """
    out: dict[str, list[LibraryMatch]] = {}
    for source in sources:
        slug = str(source.get("slug") or "")
        if not slug:
            continue
        title_tokens = _tokens(source.get("title", ""))
        surnames = {
            w for w in re.findall(r"[A-Z][a-z]{2,}", str(source.get("author") or ""))
        }
        surnames = {s.lower() for s in surnames}
        year = str(source.get("year") or "").strip()

        flat_slug = slug.replace("-", "").replace("_", "")
        matches: list[LibraryMatch] = []
        for path in files:
            haystack = f"{path.parent.name} {path.stem}"
            file_tokens = _tokens(haystack)
            low = haystack.lower()

            # A file named for the slug is the strongest signal there is — it
            # means someone already filed it under this source — so it does not
            # need to clear the title-overlap bar the fuzzier paths do.
            if flat_slug and flat_slug in path.stem.lower().replace("-", "").replace("_", ""):
                matches.append(
                    LibraryMatch(slug=slug, path=path, score=1.0, reason="filename matches the source slug")
                )
                continue

            shared = title_tokens & file_tokens
            if not shared:
                continue
            title_score = len(shared) / max(1, min(len(title_tokens), 6))

            corroborated = []
            if surnames & file_tokens:
                corroborated.append("author")
            if year and len(year) == 4 and year in low:
                corroborated.append("year")
            if slug.replace("-", "") in low.replace("-", "").replace("_", ""):
                corroborated.append("slug")
            if not corroborated:
                continue

            score = min(1.0, title_score + 0.25 * len(corroborated))
            if score >= min_score:
                matches.append(
                    LibraryMatch(
                        slug=slug,
                        path=path,
                        score=score,
                        reason=f"title:{sorted(shared)[:3]} + {'+'.join(corroborated)}",
                    )
                )
        if matches:
            matches.sort(key=lambda m: (-m.score, len(str(m.path))))
            out[slug] = matches[:4]
    return out


def run_fetch_command(
    template: str, source: dict[str, Any], out_dir: Path, *, timeout: int = 300
) -> tuple[bool, str]:
    """Run the operator's configured fetch command for one source.

    The template is substituted with `{slug} {title} {author} {year} {out}` and
    executed as an argument vector — never through a shell — so a title
    containing quotes or semicolons cannot become a command. What the command
    itself does is the operator's decision; this reports only whether a file
    appeared at `{out}`.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{source.get('slug', 'source')}.txt"
    fields = {
        "slug": str(source.get("slug", "")),
        "title": str(source.get("title", "")),
        "author": str(source.get("author", "")),
        "year": str(source.get("year", "")),
        "out": str(target),
    }
    try:
        argv = [part.format(**fields) for part in shlex.split(template)]
    except (KeyError, ValueError) as exc:
        return False, f"bad acquisition.fetch_command template: {exc}"
    if not argv:
        return False, "empty acquisition.fetch_command"

    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError:
        return False, f"fetch command not found: {argv[0]}"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"fetch command failed: {exc}"

    if target.exists() and target.stat().st_size > 0:
        return True, str(target)
    detail = (proc.stderr or proc.stdout or "").strip()[:300]
    return False, f"exit {proc.returncode}: {detail}" if detail else f"exit {proc.returncode}, no output file"
