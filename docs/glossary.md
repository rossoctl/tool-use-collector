# Glossary

Terms specific to tool-use-collector, or general terms this repo uses in a narrower sense than usual.
The second category matters more than the first: a borrowed word used precisely is harder to
spot than an invented one, and causes more confusion.

Keep entries short — one or two sentences, linking the spec that defines the term fully.

## tool-use-collector terms

**duty cycle** — the fraction of a session's span during which a tool call was executing:
Σ tool durations / span. Reported both as a per-session percentile (p50, p90) and
time-weighted across sessions (aggregate). See
[`tool-use-collector-overview.md`](tool-use-collector-overview.md) §3.

**span** — wall-clock time from a session's first to last transcript entry. Includes tool
time, think gaps and away gaps; a session left open for days has a large span and (usually) a
tiny duty cycle.

**think gap / away gap** — idle time between tool calls, split at the `away-secs` threshold
(default 120 s). *Think* ≈ the model working; *away* ≈ the user gone. The split is a
heuristic, not a measurement.

**disk-relevant tool** — a tool that writes to the sandbox workspace (`Bash`, `Write`,
`Edit`, `NotebookEdit`), as opposed to read-only inspection tools. Classifying by tool name
is a proxy: a read-only `ls` in Bash counts as disk-relevant. See `DISK_TOOLS` in
`claude-duty.py`.

**hung-call clamp** — a tool call whose result is logged more than `MAX_CALL_SECS`
(30 minutes) after the call is counted as only 30 minutes of execution, because transcript
timestamps record when a result was *written down*, not when the work completed.

**machine id** — truncated sha256 of the hostname, the report's only identifier. Stable
across runs so repeat submissions are recognizable; reveals nothing about the machine by
itself.

## Terms we use narrowly

**verify** — in this repo, specifically *recompute the report's signature and tool-hash*
(`--verify`). It is integrity checking against typos and edits, **not** authentication: a
correctly signed report proves the text is intact, not that the numbers are true.

**collector** — the *person* receiving pasted reports, or this repo generally. Deliberately
not a service: there is no collector endpoint, and extending the word to mean one would
contradict the design.

## Deliberately avoided

**"anonymous"** — use **"aggregate-only"** instead, because the reports are not anonymous in
the cryptographic sense: the machine id is a stable pseudonym, and the collector may know
who pasted what. Claiming anonymity would overpromise.

**"telemetry"** — use **"report"** instead, because telemetry implies background,
continuous, opt-out collection; this is an explicit, one-shot, opt-in paste.

---

_Assisted-By: Claude Code_
