"""The project manifest — `oskg.yaml`.

The manifest is what makes the pipeline domain-agnostic. Edge vocabulary,
evidence types, claim types, note domains, budget, gate thresholds: everything
the seven prior OSKG projects hard-coded into their own METHODOLOGY.md lives
here instead, so no phase driver ever needs to know what domain it is in.

See spec/project-manifest.md for the schema and the field rules.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import yamlish

__all__ = ["Manifest", "ManifestError", "BASE_EDGE_TYPES", "PHASES", "default_manifest"]

MANIFEST_NAME = "oskg.yaml"
SUPPORTED_VERSIONS = (1,)

BASE_EDGE_TYPES = ("supports", "contradicts", "extends", "depends_on")
PHASES = (0, 1, 2, 3, 4, 5)
RESERVED_NOTE_DOMAINS = {"claims", "synthesis"}

CONFIDENCE_LEVELS = (
    "very-low",
    "low",
    "low-medium",
    "medium",
    "medium-high",
    "high",
    "very-high",
)

# Phase 0 is funded to acquire roughly as many sources as Phase 1 can afford to
# read. Under-funding it starves every phase after it; over-funding it buys
# sources nobody reads. See `oskg build --dry-run`, which reports the binding
# constraint for a given budget.
DEFAULT_ALLOCATION = {
    "phase0": 0.12,
    "phase1": 0.30,
    "phase2": 0.28,
    "phase3": 0.16,
    "phase4": 0.09,
    "phase5": 0.05,
}

DEFAULT_GATES = {
    "min_edges_per_claim": 1.5,
    "min_cross_source_ratio": 0.25,
    "max_orphan_ratio": 0.10,
    "min_topic_tags": 1,
    "min_evidence_chars": 120,
    "repair_attempts": 1,
    "strict": False,
}

_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class ManifestError(ValueError):
    """A manifest that will not produce a usable run."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("invalid oskg.yaml:\n  - " + "\n  - ".join(problems))


@dataclass
class Manifest:
    """A validated `oskg.yaml`. Construct via `load` or `default_manifest`."""

    data: dict[str, Any]
    path: Path | None = None
    problems: list[str] = field(default_factory=list)

    # ── identity ────────────────────────────────────────────────────────
    @property
    def project(self) -> str:
        return str(self.data.get("project", ""))

    @property
    def topic(self) -> str:
        return str(self.data.get("topic", ""))

    @property
    def question(self) -> str:
        return str(self.data.get("question", "") or self.topic)

    @property
    def slug(self) -> str:
        return str(self.data.get("slug", ""))

    @property
    def tag(self) -> str:
        return str(self.data.get("tag", ""))

    @property
    def slug_prefix(self) -> str:
        return str(self.data.get("slug_prefix", "") or "")

    @property
    def domain_type(self) -> str:
        return str(self.data.get("domain_type", "domain"))

    # ── vocabulary ──────────────────────────────────────────────────────
    @property
    def edge_types(self) -> list[str]:
        return list(self.data.get("edge_types") or BASE_EDGE_TYPES)

    @property
    def claim_types(self) -> list[str]:
        return list(self.data.get("claim_types") or [])

    @property
    def evidence_types(self) -> list[str]:
        return list(self.data.get("evidence_types") or [])

    @property
    def note_domains(self) -> list[str]:
        return list(self.data.get("note_domains") or ["concepts"])

    @property
    def topics(self) -> list[str]:
        return list(self.data.get("topics") or [])

    # ── scope ───────────────────────────────────────────────────────────
    @property
    def scope(self) -> dict[str, Any]:
        return dict(self.data.get("scope") or {})

    @property
    def claims_per_note(self) -> tuple[int, int]:
        rng = self.scope.get("claims_per_note") or [5, 10]
        return int(rng[0]), int(rng[1])

    @property
    def min_tier(self) -> int:
        return int(self.scope.get("min_tier", 1))

    # ── acquisition ─────────────────────────────────────────────────────
    @property
    def acquisition(self) -> dict[str, Any]:
        return dict(self.data.get("acquisition") or {})

    @property
    def local_library(self) -> list[str]:
        """Directories of already-obtained texts, searched before the web."""
        raw = self.acquisition.get("local_library") or []
        return [str(raw)] if isinstance(raw, str) else [str(p) for p in raw]

    @property
    def fetch_command(self) -> str:
        """Operator-configured command for sources not found locally or open-access."""
        return str(self.acquisition.get("fetch_command") or "")

    # ── budget ──────────────────────────────────────────────────────────
    @property
    def budget(self) -> dict[str, Any]:
        return dict(self.data.get("budget") or {})

    @property
    def total_usd(self) -> float:
        return float(self.budget.get("total_usd", 20.0))

    @property
    def reserve_usd(self) -> float:
        return float(self.budget.get("reserve_usd", 0.5))

    @property
    def allocation(self) -> dict[str, float]:
        alloc = self.budget.get("allocation") or DEFAULT_ALLOCATION
        return {k: float(v) for k, v in alloc.items()}

    @property
    def rollover(self) -> bool:
        return bool(self.budget.get("rollover", True))

    # ── model ───────────────────────────────────────────────────────────
    @property
    def model(self) -> str | None:
        return self.data.get("model", {}).get("default") if self.data.get("model") else None

    @property
    def provider(self) -> str | None:
        return self.data.get("model", {}).get("provider") if self.data.get("model") else None

    def model_for_phase(self, phase: int) -> tuple[str | None, str | None]:
        """(model, provider) for `phase`, honouring `model.per_phase` overrides."""
        cfg = self.data.get("model") or {}
        override = (cfg.get("per_phase") or {}).get(f"phase{phase}")
        if override:
            return str(override), cfg.get("provider")
        return cfg.get("default"), cfg.get("provider")

    # ── gates ───────────────────────────────────────────────────────────
    @property
    def gates(self) -> dict[str, Any]:
        merged = dict(DEFAULT_GATES)
        merged.update(self.data.get("gates") or {})
        return merged

    @property
    def strict(self) -> bool:
        return bool(self.gates.get("strict", False))

    # ── persistence ─────────────────────────────────────────────────────
    @classmethod
    def load(cls, project_dir: Path | str, *, validate: bool = True) -> "Manifest":
        path = Path(project_dir) / MANIFEST_NAME
        if not path.exists():
            raise ManifestError([f"no {MANIFEST_NAME} in {project_dir}"])
        try:
            data = yamlish.load_file(path)
        except yamlish.YamlishError as exc:
            raise ManifestError([str(exc)]) from exc
        m = cls(data=data, path=path)
        m.problems = m.validate()
        if validate and m.problems:
            raise ManifestError(m.problems)
        return m

    def save(self, project_dir: Path | str | None = None) -> Path:
        path = Path(project_dir) / MANIFEST_NAME if project_dir else self.path
        if path is None:
            raise ManifestError(["no path to save to"])
        header = (
            f"# {self.project} — OSKG project manifest\n"
            "# Schema: https://github.com/LittleSeneca/OSKG-methodology/blob/main/spec/project-manifest.md\n"
        )
        yamlish.dump_file(path, self.data, header=header)
        self.path = Path(path)
        return self.path

    # ── validation ──────────────────────────────────────────────────────
    def validate(self) -> list[str]:
        """Every problem with this manifest, as human-readable strings."""
        p: list[str] = []
        d = self.data

        version = d.get("oskg_version")
        if version not in SUPPORTED_VERSIONS:
            p.append(f"UNSUPPORTED_VERSION: oskg_version={version!r}, supported={SUPPORTED_VERSIONS}")

        for key in ("project", "topic", "slug", "tag", "created"):
            if not d.get(key):
                p.append(f"MISSING_KEY: {key}")

        if d.get("tag") and not _TAG_RE.match(str(d["tag"])):
            p.append(f"BAD_TAG: {d['tag']!r} must match [a-z0-9-]+")
        if d.get("slug") and not _SLUG_RE.match(str(d["slug"])):
            p.append(f"BAD_SLUG: {d['slug']!r} must match [a-z0-9-]+")

        missing_edges = [e for e in BASE_EDGE_TYPES if e not in self.edge_types]
        if missing_edges:
            p.append(f"INCOMPLETE_EDGE_TYPES: missing {missing_edges}")

        if not self.claim_types:
            p.append("MISSING_KEY: claim_types")
        if not self.evidence_types:
            p.append("MISSING_KEY: evidence_types")

        domains = self.note_domains
        if not domains:
            p.append("BAD_NOTE_DOMAINS: at least one note domain is required")
        clashes = sorted(set(domains) & RESERVED_NOTE_DOMAINS)
        if clashes:
            p.append(f"BAD_NOTE_DOMAINS: {clashes} are reserved")

        p.extend(self._validate_budget())

        cfg = d.get("model") or {}
        if cfg.get("provider") and not cfg.get("default"):
            p.append("PROVIDER_WITHOUT_MODEL: model.provider requires model.default")

        rng = self.scope.get("claims_per_note")
        if rng is not None:
            if not isinstance(rng, (list, tuple)) or len(rng) != 2:
                p.append("BAD_RANGE: scope.claims_per_note must be [min, max]")
            elif int(rng[0]) > int(rng[1]) or int(rng[0]) < 1:
                p.append(f"BAD_RANGE: scope.claims_per_note={list(rng)}")

        if self.min_tier not in (1, 2, 3, 4):
            p.append(f"BAD_RANGE: scope.min_tier={self.min_tier} must be 1-4")

        return p

    def _validate_budget(self) -> list[str]:
        p: list[str] = []
        try:
            total = self.total_usd
            reserve = self.reserve_usd
        except (TypeError, ValueError):
            return ["BAD_BUDGET: total_usd and reserve_usd must be numbers"]

        if total <= 0:
            p.append(f"BAD_BUDGET: total_usd={total} must be > 0")
        if reserve < 0:
            p.append(f"BAD_BUDGET: reserve_usd={reserve} must be >= 0")
        elif reserve >= total:
            p.append(f"BAD_BUDGET: reserve_usd={reserve} must be < total_usd={total}")

        alloc = self.allocation
        for phase in PHASES:
            if f"phase{phase}" not in alloc:
                p.append(f"MISSING_PHASE_ALLOCATION: phase{phase}")
        if not p:
            total_share = sum(alloc.values())
            if abs(total_share - 1.0) > 0.001:
                p.append(f"BAD_ALLOCATION: shares sum to {total_share:.4f}, must be 1.0")
            negative = sorted(k for k, v in alloc.items() if v < 0)
            if negative:
                p.append(f"BAD_ALLOCATION: negative shares {negative}")
        return p


def default_manifest(
    *,
    project: str,
    topic: str,
    slug: str,
    question: str = "",
    budget_usd: float = 20.0,
    model: str | None = None,
    provider: str | None = None,
    domain_type: str = "domain",
) -> Manifest:
    """A minimal valid manifest. Phase 0 fills in the domain vocabulary."""
    today = _dt.date.today().isoformat()
    data: dict[str, Any] = {
        "oskg_version": 1,
        "project": project,
        "topic": topic,
        "question": question or topic,
        "slug": slug,
        "tag": f"oskg-{slug}",
        "slug_prefix": "",
        "domain_type": domain_type,
        "created": today,
        "edge_types": list(BASE_EDGE_TYPES),
        # Phase 0 replaces these with a domain-appropriate vocabulary; they are
        # kept generic here so a manifest is valid the moment it is written and
        # a --dry-run works before any model has been consulted.
        "claim_types": ["definitional", "empirical", "causal", "normative", "methodological"],
        "evidence_types": ["primary-source", "secondary-source", "empirical", "expert-opinion"],
        "note_domains": ["concepts", "history", "questions"],
        "topics": [],
        "scope": {
            "target_sources": 0,
            "target_notes": 0,
            "target_claims": 0,
            "claims_per_note": [5, 10],
            "min_tier": 1,
        },
        "budget": {
            "total_usd": float(budget_usd),
            "allocation": dict(DEFAULT_ALLOCATION),
            "rollover": True,
            "reserve_usd": 0.5,
        },
        "acquisition": {"local_library": [], "fetch_command": ""},
        "model": {"default": model, "provider": provider, "per_phase": {}},
        "gates": dict(DEFAULT_GATES),
    }
    m = Manifest(data=data)
    m.problems = m.validate()
    if m.problems:  # a bug in this function, not user input
        raise ManifestError(m.problems)
    return m
