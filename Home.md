---
tags:
  - oskg/root
  - oskg-methodology
created: 2026-08-12
aliases:
  - "OSKG Methodology Home"
  - "The OSKG Method"
pinned: true
---

# OSKG-methodology

> Seven knowledge graphs, each one restating the method in its own words, each one drifting a little
> further from the last. This is the version they should have been sharing.

The home note for **OSKG-methodology** — the canonical statement of the Open Source Knowledge Graph method,
plus the toolkit that runs it end to end from a single prompt.

## Structure

- **[[METHODOLOGY]]** — the method itself, domain-agnostic and normative
- **[[spec/claim-node|Claim node]]** — the claim file format contract
- **[[spec/edge-types|Edge types]]** — edge vocabulary and how to choose
- **[[spec/reading-note|Reading note]]** — the Phase 1 substrate
- **[[spec/tag-taxonomy|Tag taxonomy]]** — the four tag layers
- **[[spec/project-manifest|Project manifest]]** — `oskg.yaml`
- **[[spec/quality-gates|Quality gates]]** — what must pass at each boundary
- **[[spec/budget-model|Budget model]]** — allocation, rollover, the hard cap

## The idea

Decompose sources into claims. Connect claims with typed edges. Compute the synthesis from graph structure
rather than writing it from impressions. Every claim traceable, every edge written down, the whole pipeline
reproducible.

The part that is new here is the last mile: the method used to take supervised sessions across days. Now it
takes one command and a budget.

## Sibling projects

| Project | Domain | Status |
|---|---|---|
| [[../OSKG-YahWeh/Home\|OSKG-YahWeh]] | Yahweh origins | Capstone complete — 723 claims |
| [[../OSKG-ZeroTrust/Home\|OSKG-ZeroTrust]] | Zero Trust architecture | 406 claims |
| [[../OSKG-vCISO/Home\|OSKG-vCISO]] | Security leadership | Claims extraction |
| [[../OSKG-DND/Home\|OSKG-DND]] | D&D 5e rules | Phase 0 |
| [[../OSKG-IBD/Home\|OSKG-IBD]] | IBD/SIBO | Capstone epub |
| [[../OSKG-OnePageRules/Home\|OSKG-OnePageRules]] | Grimdark Future | Phase 0 |
| [[../OSKG-GrahamBrooks/Home\|OSKG-GrahamBrooks]] | Person graph | Phase 0 |

## Status

**Toolkit complete, awaiting its first full unattended build.** The method is stable — it has produced
seven graphs. What is unproven is the orchestrator's ability to hit a target scope inside a fixed budget
without supervision. The first real test is a `$20` build on a topic none of the existing graphs cover.

- **GitHub:** https://github.com/LittleSeneca/OSKG-methodology
- **Local:** `~/Projects/Personal/OSKG-methodology`

---

*This is a living document. It will change as the method is used.*
