#!/usr/bin/env python3
"""claude-duty: sandbox duty cycle from Claude Code session logs. Zero deps.

Scans ~/.claude/projects/*/*.jsonl locally and prints a short, signed,
text-only report suitable for pasting into chat. Only timestamps and
tool-call ids/names are read; message content is never inspected or
emitted.

  ./claude-duty.py              print the signed report
  ./claude-duty.py --list       also show a per-session table (local only)
  ./claude-duty.py --verify     verify a pasted report (reads stdin)
  ./claude-duty.py --days 30    limit to sessions touched in the last N days

The report's signature chains the sha256 of this script itself with the
report text, so a garbled or hand-edited paste fails verification:
  ./claude-duty.py --verify < report.txt
Python 3.7+, standard library only.
"""

import argparse
import datetime
import hashlib
import json
import os
import socket
import sys

REPORT_BEGIN = "-----BEGIN AGENT-DUTY REPORT-----"
REPORT_END = "-----END AGENT-DUTY REPORT-----"
TOOL_VERSION = "claude-duty/1"

# Tools that write to the sandbox workspace (vs read-only inspection).
DISK_TOOLS = {"bash", "write", "edit", "notebookedit"}

# Human-in-the-loop tools: the tool_use->tool_result interval measures the
# *user* deciding/approving, not execution. Counted as idle (away) time,
# never as tool time.
WAIT_TOOLS = {"askuserquestion", "exitplanmode", "enterplanmode"}

# A tool call whose result lands later than this is treated as hung or
# abandoned-in-session; only this much of it counts as execution. Keeps a
# wedged WebFetch from inflating tool time by hours.
MAX_CALL_SECS = 1800.0


def parse_ts(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_session(path):
    """Return (calls, first_ts, last_ts) or None if no usable data.

    calls: list of (name, start, end-or-None). Pairing is by tool_use id.
    """
    calls = []
    open_calls = {}
    first = last = None
    try:
        fh = open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return None
    with fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            ts = parse_ts(entry.get("timestamp"))
            if ts is not None:
                if first is None:
                    first = ts
                last = ts
            if ts is None:
                continue
            content = (entry.get("message") or {}).get("content")
            if not isinstance(content, list):
                content = entry.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_use":
                    cid = block.get("id")
                    name = str(block.get("name") or "?").lower()
                    if cid and name not in WAIT_TOOLS:
                        call = [name, ts, None]
                        open_calls[cid] = call
                        calls.append(call)
                elif btype == "tool_result":
                    cid = block.get("tool_use_id")
                    if cid in open_calls:
                        open_calls.pop(cid)[2] = ts
    if first is None or last is None or not calls:
        return None
    calls.sort(key=lambda c: c[1])
    return calls, first, last


def session_stats(calls, first, last, away_secs):
    span = (last - first).total_seconds()
    if span <= 0:
        return None
    tool_time = 0.0
    disk_time = 0.0
    # Per-tool execution time (post-clamp), for the report breakdown.
    tool_totals = {}
    for name, start, end in calls:
        dur = min(max(0.0, (end - start).total_seconds()), MAX_CALL_SECS) \
            if end else 0.0
        tool_time += dur
        if name in DISK_TOOLS:
            disk_time += dur
        tool_totals[name] = tool_totals.get(name, 0.0) + dur

    # Idle gaps on sorted call boundaries; parallel calls don't create
    # phantom idle time. Gaps above away_secs count as user-away.
    boundaries = []
    for _name, start, end in calls:
        boundaries.append((start, 1))
        if end is not None:
            boundaries.append((end, -1))
    boundaries.sort(key=lambda b: b[0])
    think = away = 0.0
    depth = 0
    prev = first
    for ts, delta in boundaries:
        if depth == 0 and ts > prev:
            gap = (ts - prev).total_seconds()
            if gap > away_secs:
                away += gap
            else:
                think += gap
        depth += delta
        if ts > prev:
            prev = ts
    if boundaries:
        head = (boundaries[0][0] - first).total_seconds()
        tail = (last - prev).total_seconds()
        for gap in (head, tail):
            if gap > 0:
                if gap > away_secs:
                    away += gap
                else:
                    think += gap

    return {
        "span": span,
        "calls": len(calls),
        "tool": tool_time,
        "disk": disk_time,
        "think": think,
        "away": away,
        "duty": tool_time / span,
        "tools": tool_totals,
    }


def scan(projects_dir, days):
    import glob  # deferred: only needed for scanning, not for --verify
    paths = sorted(glob.glob(os.path.join(projects_dir, "*", "*.jsonl")),
                   key=lambda p: os.path.getmtime(p), reverse=True)
    if days is not None:
        cutoff = datetime.datetime.now().timestamp() - days * 86400
        paths = [p for p in paths if os.path.getmtime(p) >= cutoff]
    stats = []
    for path in paths:
        parsed = parse_session(path)
        if parsed:
            st = session_stats(*parsed, away_secs=args_away)
            if st:
                stats.append(st)
    return stats


def aggregate(stats):
    span = sum(s["span"] for s in stats)
    tool = sum(s["tool"] for s in stats)
    away = sum(s["away"] for s in stats)
    disk = sum(s["disk"] for s in stats)
    duties = sorted(s["duty"] for s in stats)
    tool_totals = {}
    for s in stats:
        for name, secs in s["tools"].items():
            tool_totals[name] = tool_totals.get(name, 0.0) + secs
    n = len(stats)

    def pct(p):
        return duties[min(int(p / 100 * n), n - 1)] * 100 if duties else 0.0

    return {
        "n": n, "span": span, "tool": tool, "away": away, "disk": disk,
        "p50": pct(50), "p90": pct(90),
        "agg": (tool / span * 100) if span else 0.0,
        "tools": tool_totals,
    }


def machine_id():
    """Stable, non-obvious identifier: truncated sha256 of the hostname."""
    raw = socket.gethostname().encode("utf-8", "replace")
    return hashlib.sha256(b"agent-duty:" + raw).hexdigest()[:12]


def tool_hash():
    """sha256 of this script's own bytes, truncated for pastability."""
    with open(os.path.abspath(__file__), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def fmt_hours(secs):
    return "%.1f" % (secs / 3600.0)


def build_report(stats, away_secs):
    agg = aggregate(stats)
    # Canonical body lines. Verification depends on exact text and number
    # formatting, so never hand-edit a report.
    body = [
        "tool: " + TOOL_VERSION,
        "machine: " + machine_id(),
        "sessions: %d" % agg["n"],
        "away-secs: %d" % away_secs,
        "span-total-h: " + fmt_hours(agg["span"]),
        "tool-total-h: " + fmt_hours(agg["tool"]),
        "disk-total-h: " + fmt_hours(agg["disk"]),
        "away-total-h: " + fmt_hours(agg["away"]),
        "duty-aggregate-pct: %.1f" % agg["agg"],
        "duty-p50-pct: %.1f" % agg["p50"],
        "duty-p90-pct: %.1f" % agg["p90"],
    ]
    # Per-tool breakdown: top tools by execution time, deterministic order
    # (hours descending, then name) so the signature is reproducible.
    ranked = sorted(agg["tools"].items(), key=lambda kv: (-kv[1], kv[0]))
    for name, secs in ranked[:8]:
        if secs >= 300.0:  # skip sub-five-minute noise
            body.append("tooltime-%s-h: %s" % (name, fmt_hours(secs)))
    body.append("tool-hash: " + tool_hash())
    digest = hashlib.sha256(
        ("\n".join(body) + "\n").encode("utf-8")).hexdigest()[:16]
    return "\n".join([REPORT_BEGIN] + body + ["signature: " + digest, REPORT_END])


def verify(text):
    lines = [ln.rstrip() for ln in text.strip().splitlines()]
    try:
        start = lines.index(REPORT_BEGIN)
        end = len(lines) - 1 - lines[::-1].index(REPORT_END)
    except ValueError:
        return False, "report markers missing"
    body = [ln for ln in lines[start + 1:end] if ln.strip()]
    sig_lines = [ln for ln in body if ln.startswith("signature: ")]
    body_no_sig = [ln for ln in body if not ln.startswith("signature: ")]
    if len(sig_lines) != 1:
        return False, "expected exactly one signature line"
    claimed = sig_lines[0][len("signature: "):].strip()

    hash_lines = [ln for ln in body_no_sig if ln.startswith("tool-hash: ")]
    if len(hash_lines) != 1:
        return False, "expected exactly one tool-hash line"
    if hash_lines[0][len("tool-hash: "):].strip() != tool_hash():
        return False, ("tool-hash mismatch: report made by a different "
                       "version of the script")
    digest = hashlib.sha256(
        ("\n".join(body_no_sig) + "\n").encode("utf-8")).hexdigest()[:16]
    if digest != claimed:
        return False, "signature mismatch: report text was garbled or edited"
    return True, "report verified"


def human(secs):
    if secs >= 86400:
        return "%.1fd" % (secs / 86400)
    if secs >= 3600:
        return "%.1fh" % (secs / 3600)
    if secs >= 60:
        return "%.1fm" % (secs / 60)
    return "%.0fs" % secs


def list_sessions(stats, limit):
    print("%-10s %8s %7s %9s %9s %7s" %
          ("session", "span", "calls", "tool", "away", "duty"))
    for i, s in enumerate(stats):
        if i >= limit:
            print("... and %d more" % (len(stats) - limit))
            break
        print("%-10s %8s %7d %9s %9s %6.1f%%" %
              ("#%d" % i, human(s["span"]), s["calls"], human(s["tool"]),
               human(s["away"]), s["duty"] * 100))
    print()


args_away = 120.0  # set from CLI in main(); module-level for scan()


def main():
    global args_away
    ap = argparse.ArgumentParser(
        description="sandbox duty cycle from Claude Code session logs")
    ap.add_argument("--projects", default="~/.claude/projects")
    ap.add_argument("--days", type=float)
    ap.add_argument("--away-secs", type=float, default=120.0,
                    help="idle gap above this counts as user-away (default 120)")
    ap.add_argument("--list", action="store_true",
                    help="print a per-session table before the report")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--verify", action="store_true",
                    help="verify a pasted report from stdin")
    args = ap.parse_args()
    args_away = args.away_secs

    if args.verify:
        ok, why = verify(sys.stdin.read())
        print(why)
        return 0 if ok else 1

    stats = scan(os.path.expanduser(args.projects), args.days)
    if not stats:
        print("claude-duty: no usable sessions found", file=sys.stderr)
        return 1
    if args.list:
        list_sessions(stats, args.limit)
    print(build_report(stats, args.away_secs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
