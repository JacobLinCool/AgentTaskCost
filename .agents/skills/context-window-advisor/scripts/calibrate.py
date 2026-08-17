#!/usr/bin/env python3
"""
Measure the Agent Task Cost session-calibration parameters from local Codex
rollout logs. Standard library only, Python 3.9+.

Nothing leaves the machine: this reads ~/.codex/sessions and prints aggregates.

What it measures, and where each number comes from in the logs:

  W      model_context_window on every token_count event (already the effective
         window: Codex reports ~95% of the model's raw context_window)
  B      input_tokens of a root session's first model call — the prefix a
         compaction keeps (system prompt + tool definitions + rules + task text)
  rho    cached_input_tokens / input_tokens, summed
  omega  cache_write_input_tokens / input_tokens, summed
  theta  the context just before a context_compacted event, over W
  S_c    the context on the first model call after a context_compacted event
  o-bar  output_tokens / model calls
  d-bar  mean of S_{t+1} - S_t between consecutive calls inside one cycle

Run standalone for the full report:
  python3 calibrate.py --include-archived --json out.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

# Cap on how many per-call growth samples one session contributes, so a single
# enormous session cannot dominate the pooled distribution.
DELTA_SAMPLE_CAP = 3000

DEFAULT_ROOTS = ["~/.codex/sessions"]
ARCHIVED_ROOT = "~/.codex/archived_sessions"

# Requests above this context are billed at the long-context rate. Tracked while
# parsing so the observed spend can be reconstructed from the logs.
LONG_CONTEXT_THRESHOLD = 272_000


# ----------------------------------------------------------------------------
# Per-file parsing (runs in a worker process)
# ----------------------------------------------------------------------------


def parse_session(path):
    """Reduce one rollout file to a small summary. Returns None if unusable."""
    calls = []  # S_t, the input context of each model call
    cached = write = out = reasoning = total_in = 0
    tier_calls = 0  # requests large enough to hit the long-context rate
    windows = Counter()
    models = Counter()
    cwd = None
    cli_version = None
    session_id = None
    started = None
    session_kind = "root"  # root | subagent | forked
    compaction_marks = []  # index into `calls` where a compaction fired

    try:
        size = os.path.getsize(path)
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                # Cheap prefilter: the record type always sits near the front.
                head = line[:160]
                if '"token_count"' in head:
                    pass
                elif '"context_compacted"' in head:
                    compaction_marks.append(len(calls))
                    continue
                elif '"session_meta"' in head or '"turn_context"' in head:
                    pass
                else:
                    continue

                try:
                    rec = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                rtype = rec.get("type")
                payload = rec.get("payload")
                if not isinstance(payload, dict):
                    continue

                if rtype == "session_meta":
                    session_id = payload.get("session_id") or payload.get("id")
                    cwd = payload.get("cwd") or cwd
                    cli_version = payload.get("cli_version") or cli_version
                    started = payload.get("timestamp") or rec.get("timestamp")
                    # A subagent or a fork starts mid-conversation, so its first
                    # request is inherited history, not the fixed prefix B.
                    if payload.get("thread_source") == "subagent" or payload.get("parent_thread_id"):
                        session_kind = "subagent"
                    elif payload.get("forked_from_id"):
                        session_kind = "forked"

                elif rtype == "turn_context":
                    model = payload.get("model")
                    effort = payload.get("effort") or payload.get("reasoning_effort")
                    if model:
                        models[(model, effort)] += 1
                    cwd = payload.get("cwd") or cwd

                elif rtype == "event_msg" and payload.get("type") == "token_count":
                    info = payload.get("info") or {}
                    last = info.get("last_token_usage") or {}
                    s_t = last.get("input_tokens")
                    if not isinstance(s_t, int) or s_t <= 0:
                        continue
                    calls.append(s_t)
                    total_in += s_t
                    cached += last.get("cached_input_tokens") or 0
                    write += last.get("cache_write_input_tokens") or 0
                    out += last.get("output_tokens") or 0
                    reasoning += last.get("reasoning_output_tokens") or 0
                    if s_t > LONG_CONTEXT_THRESHOLD:
                        tier_calls += 1
                    window = info.get("model_context_window")
                    if isinstance(window, int) and window > 0:
                        windows[window] += 1
    except (OSError, UnicodeError):
        return None

    if not calls:
        return None

    compactions = []
    for idx in compaction_marks:
        before = calls[idx - 1] if idx > 0 else None
        after = calls[idx] if idx < len(calls) else None
        if before is None and after is None:
            continue
        compactions.append({"before": before, "after": after})

    boundaries = set(compaction_marks)
    deltas = [calls[i] - calls[i - 1] for i in range(1, len(calls)) if i not in boundaries]
    if len(deltas) > DELTA_SAMPLE_CAP:
        deltas = random.sample(deltas, DELTA_SAMPLE_CAP)

    return {
        "path": path,
        "bytes": size,
        "session_id": session_id,
        "started": started,
        "cwd": cwd,
        "cli_version": cli_version,
        "models": dict(models),
        "window": windows.most_common(1)[0][0] if windows else None,
        "windows": dict(windows),
        "n_calls": len(calls),
        "first_context": calls[0],
        "max_context": max(calls),
        "input_tokens": total_in,
        "cached_tokens": cached,
        "cache_write_tokens": write,
        "output_tokens": out,
        "reasoning_tokens": reasoning,
        "tier_calls": tier_calls,
        "compactions": compactions,
        "deltas": deltas,
        "kind": session_kind,
    }


# ----------------------------------------------------------------------------
# Small stats helpers (no numpy)
# ----------------------------------------------------------------------------


def pct(values, q):
    """Linear-interpolated percentile."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = q * (len(ordered) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return float(ordered[lo])
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def fmt_int(v):
    return "—" if v != v else "{:,}".format(round(v))


def fmt_tokens(v):
    if v != v:
        return "—"
    a = abs(v)
    if a >= 1e9:
        return "{:.1f}B".format(v / 1e9)
    if a >= 1e6:
        return "{:.1f}M".format(v / 1e6)
    if a >= 1e3:
        return "{:.1f}K".format(v / 1e3)
    return "{:.0f}".format(v)


def short_path(p, width=42):
    if not p:
        return "(unknown)"
    home = os.path.expanduser("~")
    if p.startswith(home):
        p = "~" + p[len(home):]
    parts = p.split(os.sep)
    if len(parts) > 4:
        p = os.sep.join(parts[:2] + ["…"] + parts[-2:])
    if len(p) > width:
        p = "…" + p[-(width - 1):]
    return p


# ----------------------------------------------------------------------------
# Progress bar
# ----------------------------------------------------------------------------


class Progress:
    def __init__(self, total, label="", width=30, stream=None):
        self.total = max(1, total)
        self.label = label
        self.width = width
        self.stream = stream or sys.stderr
        self.start = time.time()
        self.done = 0
        self.tty = self.stream.isatty()
        self.last_draw = 0.0

    def advance(self, n=1):
        self.done += n
        now = time.time()
        if not self.tty:
            step = max(1, self.total // 10)
            if self.done % step == 0 or self.done == self.total:
                print("  {} {}/{}".format(self.label, self.done, self.total), file=self.stream)
            return
        if now - self.last_draw < 0.05 and self.done < self.total:
            return
        self.last_draw = now
        frac = self.done / self.total
        bar = "█" * int(self.width * frac) + "·" * (self.width - int(self.width * frac))
        elapsed = now - self.start
        eta = (elapsed / frac - elapsed) if frac > 0 else 0.0
        self.stream.write(
            "\r  {} [{}] {:>5}/{} {:5.1f}%  {:5.1f}s  ETA {:5.1f}s".format(
                self.label, bar, self.done, self.total, frac * 100, elapsed, eta
            )
        )
        self.stream.flush()

    def close(self):
        if self.tty:
            self.stream.write("\r" + " " * (self.width + 64) + "\r")
            self.stream.flush()


# ----------------------------------------------------------------------------
# Discovery and collection
# ----------------------------------------------------------------------------


def find_files(roots, since=None):
    found = []
    for root in roots:
        root = os.path.expanduser(root)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if not name.endswith(".jsonl"):
                    continue
                if since and not _after(name, since):
                    continue
                found.append(os.path.join(dirpath, name))
    return sorted(found)


def _after(filename, since):
    """rollout-2026-08-17T21-27-36-<uuid>.jsonl -> compare the date part."""
    stamp = filename.replace("rollout-", "")[:10]
    if len(stamp) != 10 or stamp[4] != "-":
        return True  # unrecognised name: keep rather than silently drop
    return stamp >= since


def collect(roots, since=None, limit=None, workers=0, show_progress=True, stream=None):
    """Parse every session under `roots`. Returns (sessions, files)."""
    files = find_files(roots, since)
    if not files:
        return [], []
    if limit and limit < len(files):
        random.seed(0)
        files = sorted(random.sample(files, limit))

    workers = workers or min(8, (os.cpu_count() or 2))
    sessions = []
    bar = Progress(len(files), label="parsing sessions", stream=stream) if show_progress else None

    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(parse_session, p) for p in files]
            for fut in as_completed(futures):
                try:
                    res = fut.result()
                except Exception:
                    res = None
                if res:
                    sessions.append(res)
                if bar:
                    bar.advance()
    else:
        for p in files:
            res = parse_session(p)
            if res:
                sessions.append(res)
            if bar:
                bar.advance()
    if bar:
        bar.close()
    return sessions, files


# ----------------------------------------------------------------------------
# Aggregation
# ----------------------------------------------------------------------------


def summarize(sessions):
    """Reduce parsed sessions to the model's calibration parameters."""
    total_calls = sum(s["n_calls"] for s in sessions)
    total_in = sum(s["input_tokens"] for s in sessions)
    total_cached = sum(s["cached_tokens"] for s in sessions)
    total_write = sum(s["cache_write_tokens"] for s in sessions)
    total_out = sum(s["output_tokens"] for s in sessions)
    total_reasoning = sum(s["reasoning_tokens"] for s in sessions)

    thetas, s_c = [], []
    for s in sessions:
        window = s["window"]
        for comp in s["compactions"]:
            if comp["before"] and window:
                thetas.append(comp["before"] / window)
            if comp["after"]:
                s_c.append(float(comp["after"]))

    root = [s for s in sessions if s["kind"] == "root"]
    b_values = [float(s["first_context"]) for s in root]

    deltas = []
    for s in sessions:
        deltas.extend(s["deltas"])
    # The recurrence accumulates total growth, so the mean is the right statistic
    # even though the distribution is heavily right-skewed.
    d_mean = sum(deltas) / len(deltas) if deltas else float("nan")

    windows = Counter()
    for s in sessions:
        for w, n in s["windows"].items():
            windows[w] += n
    dominant_window = windows.most_common(1)[0][0] if windows else None

    per_model = defaultdict(lambda: {"calls": 0, "out": 0, "sessions": 0, "windows": Counter()})
    for s in sessions:
        if s["models"]:
            key_t = max(s["models"].items(), key=lambda kv: kv[1])[0]
            key = "{} / {}".format(key_t[0], key_t[1] or "—") if isinstance(key_t, tuple) else str(key_t)
        else:
            key = "(unknown)"
        e = per_model[key]
        e["calls"] += s["n_calls"]
        e["out"] += s["output_tokens"]
        e["sessions"] += 1
        for w, n in s["windows"].items():
            e["windows"][w] += n

    per_ws = defaultdict(lambda: {"calls": 0, "sessions": 0, "deltas": [], "b": []})
    for s in sessions:
        e = per_ws[s["cwd"] or "(unknown)"]
        e["calls"] += s["n_calls"]
        e["sessions"] += 1
        e["deltas"].extend(s["deltas"])
        e["b"].append(float(s["first_context"]))

    by_window = defaultdict(lambda: {"calls": 0, "sessions": 0, "out": 0, "n_d": 0, "sum_d": 0, "comp": 0})
    for s in sessions:
        if not s["window"]:
            continue
        e = by_window[s["window"]]
        e["calls"] += s["n_calls"]
        e["sessions"] += 1
        e["out"] += s["output_tokens"]
        e["n_d"] += len(s["deltas"])
        e["sum_d"] += sum(s["deltas"])
        e["comp"] += len(s["compactions"])

    dates = sorted(s["started"][:10] for s in sessions if s.get("started"))

    return {
        "n_sessions": len(sessions),
        "n_root": len(root),
        "n_subagent": sum(1 for s in sessions if s["kind"] == "subagent"),
        "n_forked": sum(1 for s in sessions if s["kind"] == "forked"),
        "bytes": sum(s["bytes"] for s in sessions),
        "calls": total_calls,
        "input_tokens": total_in,
        "cached_tokens": total_cached,
        "output_tokens": total_out,
        "reasoning_tokens": total_reasoning,
        "cache_write_tokens": total_write,
        "tier_calls": sum(s["tier_calls"] for s in sessions),
        "date_range": [dates[0], dates[-1]] if dates else None,
        "calibration": {
            "W0": float(dominant_window) if dominant_window else float("nan"),
            "B": pct(b_values, 0.5),
            "rho": total_cached / total_in if total_in else float("nan"),
            "omega": total_write / total_in if total_in else float("nan"),
            "theta": pct(thetas, 0.5) if thetas else float("nan"),
            "Sc": pct(s_c, 0.5) if s_c else float("nan"),
            "oBar": total_out / total_calls if total_calls else float("nan"),
            "dBar": d_mean,
        },
        "samples": {
            "theta": len(thetas),
            "Sc": len(s_c),
            "B": len(b_values),
            "dBar": len(deltas),
        },
        "spread": {
            "theta": (pct(thetas, 0.25), pct(thetas, 0.75)) if thetas else (float("nan"),) * 2,
            "Sc": (pct(s_c, 0.25), pct(s_c, 0.75)) if s_c else (float("nan"),) * 2,
            "B": (pct(b_values, 0.25), pct(b_values, 0.75)) if b_values else (float("nan"),) * 2,
            "dBar": (pct([float(x) for x in deltas], 0.25), pct([float(x) for x in deltas], 0.75))
            if deltas
            else (float("nan"),) * 2,
            "dBar_median": pct([float(x) for x in deltas], 0.5) if deltas else float("nan"),
            "dBar_p90": pct([float(x) for x in deltas], 0.90) if deltas else float("nan"),
        },
        "windows": dict(windows),
        "dominant_window": dominant_window,
        "per_model": {k: dict(v, windows=dict(v["windows"])) for k, v in per_model.items()},
        "per_workspace": {k: v for k, v in per_ws.items()},
        "by_window": {k: v for k, v in by_window.items()},
        "compaction_sessions": sum(1 for s in sessions if s["compactions"]),
        "compaction_total": sum(len(s["compactions"]) for s in sessions),
    }


# ----------------------------------------------------------------------------
# Standalone report
# ----------------------------------------------------------------------------


def rule(title):
    print("\n\033[1m{}\033[0m".format(title) if sys.stdout.isatty() else "\n{}".format(title))
    print("─" * 78)


def report(summary, n_files, top=12):
    cal = summary["calibration"]
    rule("Data scanned")
    print("  Usable sessions   {:,} / {:,} files   ({:.1f} GB)".format(
        summary["n_sessions"], n_files, summary["bytes"] / 1e9))
    if summary["date_range"]:
        print("  Dates             {} → {}".format(*summary["date_range"]))
    print("  Model calls       {:,}".format(summary["calls"]))
    print("  Input tokens      {:>8}   of which cached {}".format(
        fmt_tokens(summary["input_tokens"]), fmt_tokens(summary["cached_tokens"])))
    print("  Output tokens     {:>8}   of which reasoning {}".format(
        fmt_tokens(summary["output_tokens"]), fmt_tokens(summary["reasoning_tokens"])))

    rule("Global / harness parameters")
    print("  Session kinds  root {:,}   subagent {:,}   forked {:,}   (B comes from root only)".format(
        summary["n_root"], summary["n_subagent"], summary["n_forked"]))
    print()
    print("  {:<6}{:<26}{:>12}{:>11}{:>11}{:>10}".format(
        "Param", "Description", "median", "p25", "p75", "samples"))
    rows = [
        ("θ", "compaction trigger ratio", cal["theta"], summary["spread"]["theta"], "{:.4f}", summary["samples"]["theta"]),
        ("S_c", "kept after compaction", cal["Sc"], summary["spread"]["Sc"], "{:,.0f}", summary["samples"]["Sc"]),
        ("B", "first request context", cal["B"], summary["spread"]["B"], "{:,.0f}", summary["samples"]["B"]),
        ("d̄", "context growth per call", summary["spread"]["dBar_median"],
         summary["spread"]["dBar"], "{:,.0f}", summary["samples"]["dBar"]),
    ]
    for sym, label, mid, (q25, q75), fmt, n in rows:
        # U+0304 (combining macron, as in d̄) takes no column, so pad past it.
        print("  {}{:<26}{:>12}{:>11}{:>11}{:>10,}".format(
            sym.ljust(6 + sym.count("̄")), label,
            fmt.format(mid), fmt.format(q25), fmt.format(q75), n))
    print()
    print("  ρ     cached-read share   {:.4f}   (pooled cached / input)".format(cal["rho"]))
    print("  ω     cache-write share   {:.4f}   (0 when telemetry has no breakdown)".format(cal["omega"]))
    print("  ō     output per call     {:>6,.0f}   (pooled output / calls)".format(cal["oBar"]))
    print()
    print("  ! d̄ must be the mean {:,.0f}, not the median {:,.0f}: the recurrence".format(
        cal["dBar"], summary["spread"]["dBar_median"]))
    print("    accumulates total growth, and the distribution is right-skewed (p90 {:,.0f}),".format(
        summary["spread"]["dBar_p90"]))
    print("    so a few large tool results account for most of that growth.")

    rule("Per model (ō and the context window change with the model)")
    print("  {:<30}{:>9}{:>10}{:>9}   context window".format("model / effort", "sessions", "calls", "ō"))
    for key, e in sorted(summary["per_model"].items(), key=lambda kv: -kv[1]["calls"])[:top]:
        o_bar = e["out"] / e["calls"] if e["calls"] else float("nan")
        wins = ", ".join("{}×{:,}".format(fmt_tokens(w), n)
                         for w, n in Counter(e["windows"]).most_common(3))
        print("  {:<30}{:>9,}{:>10,}{:>9,.0f}   {}".format(key, e["sessions"], e["calls"], o_bar, wins))

    rule("Across context windows (the raw material for estimating β)")
    print("  {:>10}{:>9}{:>10}{:>8}{:>10}{:>12}{:>9}".format(
        "W", "sessions", "calls", "ō", "d̄", "compaction", "K/call"))
    for w, e in sorted(summary["by_window"].items()):
        o_b = e["out"] / e["calls"] if e["calls"] else float("nan")
        d_b = e["sum_d"] / e["n_d"] if e["n_d"] else float("nan")
        k_rate = e["comp"] / e["calls"] if e["calls"] else float("nan")
        print("  {:>10}{:>9,}{:>10,}{:>8,.0f}{:>9,.0f}{:>12,}{:>9.4f}".format(
            fmt_tokens(w), e["sessions"], e["calls"], o_b, d_b, e["comp"], k_rate))

    rule("Per workspace (d̄ and B change with the workspace, top {})".format(top))
    print("  {:<44}{:>8}{:>9}{:>11}{:>10}".format(
        "workspace", "sessions", "calls", "d̄ mean", "B median"))
    for key, e in sorted(summary["per_workspace"].items(), key=lambda kv: -kv[1]["calls"])[:top]:
        d_mean = sum(e["deltas"]) / len(e["deltas"]) if e["deltas"] else float("nan")
        print("  {:<44}{:>8,}{:>9,}{:>10}{:>10}".format(
            short_path(key), e["sessions"], e["calls"], fmt_int(d_mean), fmt_int(pct(e["b"], 0.5))))

    rule("Compaction in practice")
    print("  Sessions with a compaction   {:,} / {:,}  ({:.1f}%)".format(
        summary["compaction_sessions"], summary["n_sessions"],
        summary["compaction_sessions"] / max(1, summary["n_sessions"]) * 100))
    print("  Compactions in total         {:,}".format(summary["compaction_total"]))

    rule("Against the model's original canonical values")
    canon = [("W₀", cal["W0"], 256_000), ("B", cal["B"], 24_000), ("ρ", cal["rho"], 0.975),
             ("ω", cal["omega"], 0.0), ("θ", cal["theta"], 0.9), ("S_c", cal["Sc"], 32_000),
             ("ō", cal["oBar"], 350), ("d̄", cal["dBar"], 1_500)]
    print("  {:<6}{:>14}{:>18}{:>12}".format("Param", "measured here", "canonical", "diff"))
    for sym, measured, canonical in canon:
        # U+0304 (combining macron, as in d̄) takes no column, so pad past it.
        pad = sym.ljust(6 + sym.count("̄"))
        if measured != measured:
            print("  {}{:>14}{:>18,}".format(pad, "—", canonical))
            continue
        m = "{:,.4f}".format(measured) if measured < 10 else "{:,.0f}".format(measured)
        c = "{:,.4f}".format(canonical) if canonical < 10 else "{:,.0f}".format(canonical)
        d = "—" if not canonical else "{:+.1f}%".format((measured / canonical - 1) * 100)
        print("  {}{:>14}{:>18}{:>12}".format(pad, m, c, d))

    print()
    print("  Cannot be taken from the logs: φ₀ (no ground truth for effective output),")
    print("  β (needs the same tasks observed at different W), and Y (the task's")
    print("  effective output).")


def main():
    ap = argparse.ArgumentParser(description="Measure Agent Task Cost calibration from local Codex sessions.")
    ap.add_argument("--root", action="append", default=None, help="Session directory (repeatable)")
    ap.add_argument("--include-archived", action="store_true", help="Also scan ~/.codex/archived_sessions")
    ap.add_argument("--since", help="Only sessions on/after this date (YYYY-MM-DD)")
    ap.add_argument("--limit", type=int, help="Randomly sample at most N files")
    ap.add_argument("--workers", type=int, default=0, help="Worker processes (0 = auto)")
    ap.add_argument("--top", type=int, default=12, help="Rows per table")
    ap.add_argument("--json", dest="json_out", help="Write the summary to this file")
    args = ap.parse_args()

    roots = args.root or [os.path.expanduser(r) for r in DEFAULT_ROOTS]
    if args.include_archived:
        roots.append(os.path.expanduser(ARCHIVED_ROOT))

    print("Agent Task Cost — calibrating model parameters from local Codex sessions")
    print("=" * 78)
    for r in roots:
        print("  source  {}".format(short_path(r)))

    sessions, files = collect(roots, since=args.since, limit=args.limit, workers=args.workers)
    if not sessions:
        print("\nNo usable sessions found (no token_count events).", file=sys.stderr)
        return 1

    summary = summarize(sessions)
    report(summary, len(files), top=args.top)

    if args.json_out:
        payload = {
            "generated_from": {
                "sessions": summary["n_sessions"],
                "files": len(files),
                "model_calls": summary["calls"],
                "date_range": summary["date_range"],
            },
            "calibration": {k: (round(v, 5) if v < 10 else round(v)) for k, v in summary["calibration"].items()},
            "per_model": {
                k: {"sessions": e["sessions"], "calls": e["calls"],
                    "oBar": round(e["out"] / e["calls"]) if e["calls"] else None,
                    "windows": e["windows"]}
                for k, e in summary["per_model"].items()
            },
            "per_workspace": {
                k: {"sessions": e["sessions"], "calls": e["calls"],
                    "dBar": round(sum(e["deltas"]) / len(e["deltas"])) if e["deltas"] else None,
                    "B": round(pct(e["b"], 0.5))}
                for k, e in sorted(summary["per_workspace"].items(), key=lambda kv: -kv[1]["calls"])[:50]
            },
        }
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print("\n  Wrote {}".format(args.json_out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
