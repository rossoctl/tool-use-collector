# tool-use-collector — Executive Overview

**Status:** `claude-duty.py` working and measured on one machine; other agent adapters deferred.
**Repo:** `rossoctl/tool-use-collector`
**Date:** 2026-10-27

---

This document carries **all the essential information** about tool-use-collector, at a depth a reader
can absorb in one sitting. Every claim in it is covered in detail by a document in
[`specs/`](specs/) — this is the map; those are the territory.

Unlike a spec, this file is **kept current.** When a design changes, update this document in
the same PR.

## 1. What it is, and what problem it solves

Sandbox hosting for AI agent sessions is provisioned per session, but an agent session spends
most of its existence *not executing anything* — the model is thinking, or the user is away.
How much of a session's span is actual tool execution (the **duty cycle**) determines how many
sandboxes fit on a host, whether idle sandboxes should be snapshotted, and what a sandbox
migration costs. No public data answers this, and it cannot be predicted — but it can be
measured, because every agent CLI writes a timestamped session transcript to the user's own
machine.

tool-use-collector is a set of zero-dependency scripts, one per agent CLI, that read those
transcripts locally and emit a short **signed, text-only report** (session count, aggregate
and percentile duty cycle, per-tool time breakdown). Contributors run a script and paste the
report block over any channel; the collector verifies it with the same script's `--verify`
mode, which detects transit garbles and hand-edits by re-computing a hash chained over the
report text and the script's own bytes. The design is deliberately submission-infrastructure
free — no collector service, no auth, no network — so the ask of a contributor is one command
and one paste.

The privacy stance is the enabling constraint: the scripts read only timestamps, entry types,
and tool-call ids/names; message content, paths and command text are never opened or emitted;
the report's only identifier is a truncated hash of the hostname.

## 2. Architecture

```text
contributor laptop                    collector
────────────────                      ─────────
~/.claude/projects/*/*.jsonl
        │
        ▼
claude-duty.py ──prints──▶ report block ──paste──▶ claude-duty.py --verify
   (local parse, no network)            (recompute signature; tool-hash check)
```

### Key components

| Component        | Role                                                  | Spec |
| ---------------- | ----------------------------------------------------- | ---- |
| **claude-duty.py** | parse transcripts, compute stats, build/verify report | —    |

## 3. How it works

1. Scan `~/.claude/projects/*/*.jsonl`, newest first; each line is a transcript entry with an
   ISO timestamp.
2. Pair tool calls by id: a `tool_use` block starts a call, the `tool_result` with the same id
   ends it. Calls from human-in-the-loop tools (`AskUserQuestion`, `ExitPlanMode`) are
   excluded — their interval measures the user, not execution.
3. Clamp any call longer than 30 minutes to 30 minutes: transcript timestamps record when a
   result was *written down*, not when work completed, and an abandoned session's pending
   call otherwise reads as hours of execution.
4. Per session: duty cycle = Σ tool durations / session span; idle gaps between call
   boundaries split into *think* (< threshold, default 120 s) and *away* (≥ threshold).
5. Aggregate across sessions; emit the canonical report block with a signature — sha256 over
   the report body including the script's own hash, truncated for pastability.
6. `--verify` re-parses a pasted block and recomputes the signature; a mismatch names whether
   the text was garbled or the report came from a different script version.

## 4. The decisions that shape it

| Decision                             | Why                                                    | ADR |
| ------------------------------------ | ------------------------------------------------------ | --- |
| Paste-a-report over a submission API | the ask must be one command for a volunteer contributor | —   |
| Signature over script-hash + text    | detects garbles without any identity infrastructure    | —   |
| Zero dependencies, Python 3.7+       | the script must run on any laptop without setup        | —   |
| One script per agent CLI             | transcript formats differ; privacy code stays auditable | —  |
| 30-minute hung-call clamp            | abandoned sessions otherwise inflate tool time ~20×    | —   |

(No ADRs yet; the table records the choices pending their write-up.)

## 5. Current state

| Capability                          | Status      | Evidence                                                              |
| ----------------------------------- | ----------- | --------------------------------------------------------------------- |
| Claude transcript parsing + stats   | Implemented | `claude-duty.py`; measured on 67 real sessions                        |
| Signed report + verification        | Implemented | round-trip and tamper-detection tested locally                        |
| First duty-cycle measurements       | Measured    | [`reports/2026-10-27-claude-duty-first-measurements-report.md`](reports/2026-10-27-claude-duty-first-measurements-report.md) |
| Adapters for codex, opencode, pi    | Design only | formats previously prototyped in a scratch repo, not yet ported       |
| Cross-contributor aggregation guide | Not started | —                                                                     |

## 6. What it does not do

- **No submission infrastructure.** Reports arrive by whatever channel contributors choose;
  there is no server, no auth, no storage. If collection ever needs scale, that is a new
  design, not a gap.
- **No attestation.** The signature is accident-proofing: anyone with the script can forge a
  valid report. Aggregates are volunteered data.
- **Execution time is bounded, not exact.** The clamp makes `tool-total-h` a floor for
  machines that run real >30-minute tool calls; durations also include harness overhead.
- **Think/away split is heuristic.** The 120 s threshold is a guess; results quote both
  buckets and should be sensitivity-checked (`--away-secs 60` / `300`).
- **One agent CLI.** Only Claude Code is supported; each new adapter must re-derive the
  pairing and artifact corrections against that agent's transcript format.

## 7. Where to go next

| If you want to…              | Read                                                                  |
| ---------------------------- | --------------------------------------------------------------------- |
| Run it                       | [root README](../README.md)                                           |
| Change the stats or format   | `claude-duty.py` (single file, commented)                             |
| Know what was measured       | [`reports/`](reports/)                                                |
| Extend to another agent CLI  | `parse_session()` in `claude-duty.py` is the template                 |
| Know why a number is odd     | [the report's artifact sections](reports/2026-10-27-claude-duty-first-measurements-report.md) |

---

_Assisted-By: Claude Code_
