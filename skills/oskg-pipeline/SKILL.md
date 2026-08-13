---
name: oskg-pipeline
description: "Build a complete Open Source Knowledge Graph on any subject, end to end, under a fixed budget."
version: 1.0.0
category: research
metadata:
  hermes:
    tags: [oskg, knowledge-graph, research, pipeline, claims, synthesis]
---

# OSKG Pipeline

Turn a research question into a complete knowledge graph — sourced, claim-decomposed, edge-connected,
structurally analyzed, and capped at a dollar budget — with one command.

## Trigger

Graham says any of:

- "build me a knowledge graph about X"
- "make an OSKG on X" / "OSKG this"
- "research X properly" / "I want a graph of what we know about X"
- "spend $N and build me a graph about X"

Also when he asks to **continue, resume, or extend** an existing OSKG project, or to check what one cost.

## What you do

**Run `oskg`. Do not do the research yourself.** The whole point is that the pipeline is measured,
resumable, gated, and budget-capped; doing it by hand in a chat session gets none of that and costs more.

```bash
oskg build "<the topic, as a research question>" --budget 20
```

The toolkit is at `~/Projects/Personal/OSKG-methodology`. If `oskg` is not on PATH:

```bash
python3 ~/Projects/Personal/OSKG-methodology/bin/oskg build "<topic>" --budget 20
```

### Before you run it

1. **Sharpen the topic into a question.** "Zero Trust" is a subject; "what does the evidence show about how
   to implement Zero Trust?" is a question a graph can answer. Do this yourself — it is the highest-leverage
   thing in the whole run — and pass the question as the topic string.
2. **Confirm the budget** if Graham did not name one. Default is $20. Show him the projection first:

   ```bash
   oskg build "<topic>" --budget 20 --dry-run
   ```

   This makes no calls and spends nothing. It prints per-phase allowances, expected artifact counts, and
   which phase is the binding constraint.
3. **Say roughly how long it will take.** It is slow: a measured $2 build was 36 calls over 5.5 hours,
   because each call is a full agent turn doing real research. Budget most of a day for a $20 run, start
   it in the morning, and leave it. It is resumable, so an interrupt is not a loss.

### While it runs

It is unattended by design — it does not ask questions. Let it finish. It commits per phase, so progress is
visible in the project's git log.

### When it finishes

Report, from `oskg status`:

- where it got to and what it spent
- the graph size: claims, edges, cross-source ratio
- **any scope trims** — these are in `PROGRESS.md` and they are what the graph does not cover
- the path to `notes/synthesis/capstone.md`

Then read the capstone and give Graham the three-sentence version: what is settled, what is genuinely
contested, and where the graph is fragile.

## Other commands

```bash
oskg status                 # phase, spend, remaining
oskg status --ledger        # every call and what it cost
oskg build --resume         # continue a stopped run (from inside the project dir)
oskg build --resume --budget 35   # raise the cap and continue
oskg gate --phase 2         # run a quality gate by hand
oskg gate --fix             # gate, then one targeted repair pass
oskg analyze                # recompute the five structural analyses — free, no model calls
oskg export --format json   # the whole graph, for a real query layer
```

## Where projects go

Sibling directories of the toolkit: `~/Projects/Personal/OSKG-<Topic>/`, git-initialized, committed per
phase, matching the existing OSKG repos.

**Nothing is pushed to GitHub** unless `--github` is passed. Do not pass it on Graham's behalf — creating a
repo is his call, and an unattended run should not publish anything. If he asks for it afterwards, use
`gh repo create` from inside the project directory, or re-run with `--github` (private by default,
`--public` to override).

## Existing OSKG projects

Before starting a new graph, check whether one already covers the subject — extending an existing graph is
cheaper and better than starting a thin parallel one.

| Project | Domain |
|---|---|
| OSKG-YahWeh | Yahweh origins, biblical monotheism |
| OSKG-ZeroTrust | Zero Trust architecture |
| OSKG-vCISO | Security leadership — GRC, SecOps, DevOps |
| OSKG-DND | D&D 5e rules |
| OSKG-IBD | IBD/SIBO medical literature |
| OSKG-OnePageRules | Grimdark Future |
| OSKG-GrahamBrooks | Person-knowledge graph |

To extend one: `cd` into it and `oskg build --resume --budget N`, optionally with `--from-phase`.

## What to tell Graham about the result

Three things, every time, because they are what makes the graph trustworthy or not:

1. **What it cost and whether it hit the cap.** A run that stopped at the ceiling covered less than planned.
2. **What was trimmed.** `PROGRESS.md` lists every scope trim. These are the graph's blind spots.
3. **That source selection was automated.** `SOURCE-GUIDE.md` says what the corpus is and what it left out.
   A corpus that omits the strongest counter-position produces a confident, wrong graph, and no amount of
   internal structure reveals that. If the subject is contested, skim the source list yourself and say
   whether the opposition is represented.

## The method

Documented in `~/Projects/Personal/OSKG-methodology/METHODOLOGY.md`, with normative format contracts in
`spec/`. Read those before hand-editing anything in a generated project — the gates enforce them, and the
most common way to break a graph is to write wikilinks using `claim_id` instead of the filename slug.
