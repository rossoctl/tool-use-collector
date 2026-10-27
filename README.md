# rossoctl/tool-use-collector

Measure how much of an AI-agent session's lifetime its sandbox actually **runs**, from the
session logs already on the contributor's laptop — and collect the result as a short, signed,
text-only report that can be pasted into chat.

The question this repo exists to answer: **what is the duty cycle of a sandbox?** Sandbox-host
density planning (overcommit ratios, idle-snapshot thresholds, migration cost) depends on it,
nobody can predict it, and public data does not exist. But everyone who runs an agent CLI has
the raw evidence in `~/.claude` (and, for other agents, their equivalents), with timestamps
good enough to measure it.

## What you get

One zero-dependency script per agent CLI:

| Script            | Reads                                     | Status                       |
| ----------------- | ----------------------------------------- | ---------------------------- |
| `claude-duty.py`  | `~/.claude/projects/*/*.jsonl`            | tested against real sessions |

```sh
./claude-duty.py              # print the signed report block
./claude-duty.py --list       # per-session table first (local eyeballing)
./claude-duty.py --days 30    # only sessions touched in the last 30 days
```

Python 3.7+, standard library only. No install, no network access, no output files.

## The report

```text
-----BEGIN AGENT-DUTY REPORT-----
tool: claude-duty/1
machine: f1c9a1e52f60
sessions: 67
away-secs: 120
span-total-h: 1812.6
tool-total-h: 26.3
disk-total-h: 24.0
away-total-h: 1370.1
duty-aggregate-pct: 1.4
duty-p50-pct: 2.5
duty-p90-pct: 52.6
tooltime-bash-h: 22.1
tooltime-edit-h: 1.7
...
tool-hash: e5615ff97292e7fc
signature: 2d8cd11254a2d8e2
-----END AGENT-DUTY REPORT-----
```

Paste it back to the collector (@galmasi) by any non-permanent channel
(e.g. slack deletes messages after a time). Verify what you receive:

```sh
./claude-duty.py --verify < pasted-report.txt
```

The signature chains the sha256 of the script itself with the report text, so transit garbles
and hand-edits fail verification. It is accident-proofing, not cryptography — anyone with the
script can forge a valid report, so treat aggregates as volunteered data, not attested data.

## Privacy

IMPORTANT. While I did everything I could to make sure that your
  privacy is not compromised by issuing a report with this tool, let's
  treat the reports themselves as fungible. Do not record them on
  permanent media if possible: do not add them to github issues. We
  have a [Box note](https://ibm.box.com/s/0kv0cj332u67301gjm20k3vaa79uxh8e) to which
  you can append your report.


To wit:

- The tool reads **only** timestamps, entry types, and tool-call
  ids/names. Message bodies, file paths and command text are never
  opened or emitted.

- The report contains aggregate numbers and a truncated sha256 of the
  hostname — stable enough to recognize a repeat submission, without
  broadcasting the hostname itself.

- No network calls, no file writes. `--verify` works on a machine with
  no session logs.


## Method — and its known traps

Tool calls are paired by id (`tool_use` → matching `tool_result`); duration is the wall clock
between them. Three artifacts had to be corrected to get honest numbers, and anyone extending
this to another agent should expect the same class of problems:

1. **Human-in-the-loop tools** (`AskUserQuestion`, `ExitPlanMode`) measure the *user*
   deciding, not execution — counted as idle.
2. **Abandoned sessions**: a tool call whose result is logged hours later (session resumed)
   is not a hours-long call. Calls over 30 minutes are clamped as hung.
3. **Read-only vs disk-relevant tools** are separated, since only the latter imply workspace
   writes.

Full method and caveats: [the overview](docs/tool-use-collector-overview.md); the measured
results that motivated the clamps: [the report](docs/reports/2026-10-27-claude-duty-first-measurements-report.md).

### Python dependencies, exactly

Standard-library modules (the complete list, verified by import analysis — nothing else
is linked, and no external binaries are executed anywhere in the script):

| Module       | Used for                                            |
| ------------ | --------------------------------------------------- |
| `argparse`   | CLI options                                         |
| `datetime`   | transcript timestamps (`fromisoformat`, 3.7+)       |
| `hashlib`    | machine id, tool-hash, report signature             |
| `json`       | parsing transcript lines                            |
| `os`         | path expansion, file mtimes for `--days`            |
| `socket`     | hostname for the machine id (no `hostname` binary)  |
| `sys`        | stdin for `--verify`, stderr, exit codes            |
| `glob`       | finding `~/.claude/projects/*/*.jsonl` (deferred import — `--verify` runs without it) |

Filesystem access is read-only and limited to `~/.claude/projects/` (or `--projects`).
There is no `subprocess`, no `os.system`, no network code — the zero-dependency claim is
about the interpreter's own library, not a vendored bundle.


---

*Assisted-By: Claude Code*
