# First duty-cycle measurements (claude-duty) — Implementation report

Status: Partial <!-- Partial | Complete. "Partial" is normal: extend this file as later steps land. -->
Date: 2026-10-27
Spec: none yet <!-- this report precedes any spec; the overview is the design record -->
Covers: claude-duty.py parsing, stats, signed report and verification, as measured on one
contributor machine (67 Claude Code sessions, 2026-08 to 2026-10)

> **What this report says in one sentence.** On one real machine, agent-session duty cycle
> measured at **1.4% aggregate / 2.5% p50** — but the naive measurement said **30.8%**, and
> almost all of that difference was transcript-timestamp artifact, not execution.

**Append-only.** This document is not rewritten when a later phase changes the answer — write
a new report or append a dated section. See
[the lifecycle note](../README.md#specs-revise-reports-do-not).

---

## 1. What landed

| Spec ref | What it was                                        | Landed | Where            |
| -------- | -------------------------------------------------- | ------ | ---------------- |
| —        | Claude transcript scan + tool-call pairing by id   | Yes    | `claude-duty.py` |
| —        | Signed report block + `--verify`                   | Yes    | `claude-duty.py` |
| —        | Human-in-the-loop tool exclusion                   | Yes    | `WAIT_TOOLS`     |
| —        | Hung-call clamp (30 min)                           | Yes    | `MAX_CALL_SECS`  |
| —        | Per-tool time breakdown in the report              | Yes    | `tooltime-*-h:`  |
| —        | Adapters for other agent CLIs                      | No     | see §5           |
| —        | Cross-contributor aggregation                      | No     | see §6           |

## 2. Measurements

| What was measured                          | Spec predicted | Measured | Method |
| ------------------------------------------ | -------------- | -------- | ------ |
| Aggregate duty cycle, naive intervals      | none           | 30.8%    | tool_use→tool_result wall clock, 67 sessions, one laptop |
| Aggregate duty cycle, corrected            | none           | **1.4%** | wait-tools excluded, calls clamped at 30 min |
| Per-session duty p50 / p90                 | none           | 2.5% / 52.6% | corrected method |
| Total span / tool time / disk-relevant     | none           | 1812.6 h / 26.3 h / 24.0 h | corrected method |
| Away time share of span (≥120 s gaps)      | none           | 1370.1 h (~76%) | gap split at 120 s |
| Per-tool time (top)                        | none           | bash 22.1 h, edit 1.7 h, webfetch 1.2 h | corrected method |

The headline disagreement is with *the naive expectation*, not a spec: a ~1% duty cycle had
been hypothesized from first principles, the first implementation measured 30.8%, and the
investigation in §4 showed the 30.8% was artifact. The corrected figure supports the
hypothesis on this sample.

## 3. Deltas from the design

1. **Wait-tools and the hung-call clamp were not in the original design.** Both were added
   after the first measurement (§4); the report format was unchanged, but every signature
   changed, which is why the report is format-versioned by tool-hash.
2. **Per-tool breakdown added to the report block** (top 8 tools, ≥5 min each). Accepted as a
   format extension; older reports fail `--verify` with a tool-hash mismatch by design.

## 4. Findings

### 4.1 Naive tool intervals overcount execution ~20×

- **Symptom:** 557.8 h of "tool time" across 67 sessions — implausible on inspection
  (~500 h of git/ls was the reaction), and a 30.8% aggregate duty cycle that contradicted the
  idle-session intuition.
- **Root cause:** three distinct mechanisms, all invisible in the per-session table:
  1. *Abandoned sessions* (~285 of 309 raw Bash hours): a tool_use whose tool_result is
     logged hours later, when the session is next touched. The transcript records when the
     result was **written down**, not when the work completed.
  2. *Human-in-the-loop tools* (~69 h): `AskUserQuestion` intervals measure the **user**
     deciding — ~3 h per question on this sample.
  3. *Hung fetches* (~169 h): stalled `WebFetch` calls resolving at next session touch,
     ~2 h per call.
- **Fix:** `WAIT_TOOLS` excluded from tool time (counted as idle); calls longer than
  `MAX_CALL_SECS` (30 min) clamped. Combined effect: 557.8 h → 26.3 h; 30.8% → 1.4%.

### 4.2 The corrections now undercount legitimately long calls

- **Symptom:** none yet — no workload on this sample ran genuine >30-minute tool calls.
- **Root cause:** the clamp cannot distinguish "ran 45 minutes" from "ran 2 minutes, logged
  45 minutes later". On this sample the artifact calls were hours long, so the result is
  insensitive to the threshold; a build-heavy contributor would not be.
- **Fix:** none; documented as a floor in the overview's "What this does not do".

## 5. What is NOT verified

- **Single-machine sample.** One contributor, 67 sessions, one work pattern. The fleet
  number requires more reports; this report establishes the *method's* error bars, not the
  fleet distribution.
- **The 30-minute clamp threshold is unvalidated against ground truth.** No execution trace
  (e.g. shell-level timestamps) was compared against transcript-derived durations.
- **`--verify` is tested only against sed-style single-character corruption** and clean
  round-trips. Line-wrapping by chat clients, encoding mangling and partial truncation were
  not systematically exercised.
- **Adapters for codex/opencode/pi** were prototyped in a scratch repo against their storage
  formats, but only against test "hello" sessions — never real workload transcripts. They
  are not in this tree.

## 6. Follow-ups

| What                                  | Why it was deferred | Issue |
| ------------------------------------- | ------------------- | ----- |
| Cross-contributor aggregation guide   | no second report yet | — |
| codex / opencode / pi adapters        | need real transcripts to validate | — |
| Clamp-threshold sensitivity study     | insensitive on current sample | — |
| Chat-mangle corpus for --verify       | cosmetic until first real paste fails | — |

---

_Assisted-By: Claude Code_
