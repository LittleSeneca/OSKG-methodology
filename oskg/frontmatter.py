"""Markdown frontmatter and section parsing.

Every node in an OSKG — claim, reading note, synthesis document — is a markdown
file with YAML frontmatter and a body of known headings. This module is the one
place that knows how to take those apart, so the gates, the graph builder, and
the analysis all see the same view of a file.

Parsing is total: a file with broken frontmatter yields a `Document` with
``error`` set rather than raising, because a single malformed claim in a batch
of four hundred should be reported as one gate failure, not an aborted run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .yamlish import YamlishError, dumps, loads

__all__ = ["Document", "parse", "read", "write", "wikilinks", "WIKILINK_RE"]

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$", re.MULTILINE)


@dataclass
class Document:
    """A parsed markdown file: frontmatter, body, and its heading sections."""

    path: Path
    meta: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    error: str | None = None

    # ── identity ────────────────────────────────────────────────────────
    @property
    def slug(self) -> str:
        """The filename stem — the node ID that wikilinks resolve against."""
        return self.path.stem

    @property
    def tags(self) -> list[str]:
        raw = self.meta.get("tags") or []
        if isinstance(raw, str):
            return [t.strip() for t in raw.split(",") if t.strip()]
        return [str(t).strip() for t in raw if str(t).strip()]

    def tags_with_prefix(self, prefix: str) -> list[str]:
        return [t for t in self.tags if t.startswith(prefix)]

    def tag_after(self, prefix: str) -> str | None:
        """The value of the first tag with `prefix`, e.g. ``source/x`` → ``x``."""
        for t in self.tags:
            if t.startswith(prefix):
                return t[len(prefix) :]
        return None

    # ── sections ────────────────────────────────────────────────────────
    def sections(self) -> dict[str, str]:
        """Body text keyed by heading title, case-preserved.

        A heading's section runs until the next heading at the same level or
        shallower, so ``## Edges`` owns its ``**Supports:**`` subsections but
        stops at the next ``##``.
        """
        out: dict[str, str] = {}
        matches = list(_HEADING_RE.finditer(self.body))
        for i, m in enumerate(matches):
            level, title = len(m.group(1)), m.group(2).strip()
            end = len(self.body)
            for later in matches[i + 1 :]:
                if len(later.group(1)) <= level:
                    end = later.start()
                    break
            out[title] = self.body[m.end() : end].strip()
        return out

    def section(self, *titles: str) -> str:
        """First matching section body, compared case-insensitively. '' if none."""
        found = {k.lower(): v for k, v in self.sections().items()}
        for t in titles:
            if t.lower() in found:
                return found[t.lower()]
        return ""

    def wikilinks(self) -> list[str]:
        return wikilinks(self.body)

    def to_text(self) -> str:
        fm = dumps(self.meta) if self.meta else ""
        body = self.body if self.body.endswith("\n") else self.body + "\n"
        return f"---\n{fm}---\n\n{body.lstrip(chr(10))}"


def wikilinks(text: str) -> list[str]:
    """Every ``[[target]]`` in `text`, in order, with anchors and aliases stripped."""
    return [m.group(1).strip() for m in WIKILINK_RE.finditer(text)]


def parse(text: str, path: Path | str = "") -> Document:
    p = Path(path)
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return Document(path=p, meta={}, body=text, error="NO_FRONTMATTER")
    try:
        meta = loads(m.group(1))
    except YamlishError as exc:
        return Document(path=p, meta={}, body=text[m.end() :], error=f"YAML_PARSE_ERROR: {exc}")
    return Document(path=p, meta=meta, body=text[m.end() :].lstrip("\n"))


def read(path: Path | str) -> Document:
    p = Path(path)
    try:
        return parse(p.read_text(encoding="utf-8"), p)
    except OSError as exc:
        return Document(path=p, error=f"READ_ERROR: {exc}")
    except UnicodeDecodeError as exc:
        return Document(path=p, error=f"ENCODING_ERROR: {exc}")


def write(path: Path | str, meta: dict[str, Any], body: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(Document(path=p, meta=meta, body=body).to_text(), encoding="utf-8")
