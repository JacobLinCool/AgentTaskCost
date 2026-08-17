#!/usr/bin/env python3
"""
Turn local Codex session history into a context-window recommendation.

Measures the Agent Task Cost calibration parameters from ~/.codex/sessions, finds
the context window that minimises cost for small / medium / large tasks, compares
that against the window currently in use, and prints a shareable visualiser URL
carrying the measured parameters.

Standard library only, Python 3.9+. Nothing leaves the machine except the URL,
which is only printed — it is never fetched.

  python3 advise.py                       # measure and advise
  python3 advise.py --json out.json       # machine-readable
  python3 advise.py --apply 160000        # write model_context_window to config
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import sys
import time
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import calibrate  # noqa: E402
from model import Calibration, Pricing, Scenario, evaluate, optimal_window  # noqa: E402

VISUALIZER = "https://jacoblincool.github.io/AgentTaskCost/"
CODEX_CONFIG = os.path.expanduser("~/.codex/config.toml")

# Codex takes two top-level keys, and they have to move together:
#
#   model_context_window            the total context budget
#   model_auto_compact_token_limit  where automatic compaction starts
#
# The second one is this model's theta*W — the absolute token count at which a
# compaction fires — so it can be written directly, with no ratio to guess.
# Setting only the window would leave compaction firing at whatever default the
# harness picks, and the cost prediction would not hold.
CONFIG_KEYS = ("model_context_window", "model_auto_compact_token_limit")

# The task-size presets, matching the visualiser. beta is not calibrated —
# it needs the same tasks run at several windows — so these are illustrative.
TASK_SIZES = [
    ("small", "small", 0.15, "needs little pre-existing information; a local edit, a single-file bug"),
    ("medium", "medium", 0.45, "needs a moderate amount of pre-existing information present at once"),
    ("large", "large", 0.90, "must hold a lot of pre-existing information at once; a cross-file refactor"),
]

# Thresholds are on how much MORE the task consumes at the current window —
# stated as a multiple, which reads the same whether the user is metered on a
# subscription quota or on an API invoice. (Consumption is weighted the way the
# price list is, so those are one quantity, not two.)
#
# Not on the distance between window sizes: consumption is second-order flat
# around its minimum, so a window-gap threshold fires long before anything real
# is at stake — an 86K window gap can mean 1.04x consumption.
ADVISE_MULTIPLE = 1.5
STRONG_MULTIPLE = 2.0

# Below this many observed model calls the measurement is too thin to act on,
# and the setup is too lightly used for the difference to matter.
MIN_CALLS = 500

# The upper end matches the largest documented window on a current Codex model
# (GPT-5.6 Sol, 1,050,000). Recommending past what can actually be configured
# would be advice nobody can take.
SEARCH_LO, SEARCH_HI = 48_000, 1_050_000


# ----------------------------------------------------------------------------
# Codex config (no tomllib on Python 3.9, and we only need flat scalars)
# ----------------------------------------------------------------------------


def read_config(path=CODEX_CONFIG):
    """Top-level scalar keys, i.e. everything before the first [section]."""
    values = {}
    if not os.path.isfile(path):
        return values
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped.startswith("["):
                    break
                m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$', stripped)
                if not m:
                    continue
                key, raw = m.group(1), m.group(2)
                if raw.startswith(('"', "'")):
                    values[key] = raw.strip("\"'")
                elif re.fullmatch(r'-?\d+', raw):
                    values[key] = int(raw)
                elif re.fullmatch(r'-?\d*\.\d+', raw):
                    values[key] = float(raw)
                else:
                    values[key] = raw
    except OSError:
        pass
    return values


def write_window_settings(window, compact_limit, path=CODEX_CONFIG):
    """
    Set both top-level keys, keeping the rest of the file intact.

    They must sit above the first [section] header, or TOML would read them as
    belonging to that section.
    """
    if not os.path.isfile(path):
        raise SystemExit("Cannot find {}".format(path))
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = "{}.bak-{}".format(path, stamp)
    # Two runs in the same second must not clobber the earlier backup.
    seq = 1
    while os.path.exists(backup):
        backup = "{}.bak-{}-{}".format(path, stamp, seq)
        seq += 1
    shutil.copy2(path, backup)

    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()

    replaced = {}
    for key, value in zip(CONFIG_KEYS, (window, compact_limit)):
        line = "{} = {}\n".format(key, int(value))
        first_section = next(
            (i for i, l in enumerate(lines) if l.strip().startswith("[")), len(lines)
        )
        existing = next(
            (i for i, l in enumerate(lines[:first_section])
             if re.match(r'^\s*{}\s*='.format(key), l)),
            None,
        )
        if existing is not None:
            replaced[key] = lines[existing].strip()
            lines[existing] = line
        else:
            insert_at = first_section
            while insert_at > 0 and not lines[insert_at - 1].strip():
                insert_at -= 1
            lines.insert(insert_at, line)

    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    return backup, replaced


# ----------------------------------------------------------------------------
# Advice
# ----------------------------------------------------------------------------


def verdict(multiple, n_calls):
    """How much extra the current window consumes, and whether to say anything."""
    if multiple != multiple or n_calls < MIN_CALLS:
        return "ok"
    if multiple >= STRONG_MULTIPLE:
        return "strong"
    if multiple >= ADVISE_MULTIPLE:
        return "advise"
    return "ok"


def wasted_share(multiple):
    """The fraction of current consumption that the optimum would not have spent."""
    if multiple != multiple or multiple <= 1:
        return 0.0
    return 1 - 1 / multiple


def build_url(cal, current_window, beta):
    params = {
        "w0": round(cal.W0),
        "b": round(cal.B),
        "rho": round(cal.rho, 5),
        "omega": round(cal.omega, 5),
        "theta": round(cal.theta, 5),
        "sc": round(cal.Sc),
        "obar": round(cal.oBar),
        "dbar": round(cal.dBar),
        "beta": beta,
        "src": "codex",
    }
    if current_window:
        params["w"] = round(current_window)
    return VISUALIZER + "?" + urlencode(params)


def calibration_from(measured):
    """
    Build a Calibration, falling back to the model default for anything the logs
    could not produce. A history with no compaction in it yields no theta and no
    S_c, and feeding those NaNs into the model would crash it rather than report
    that there was too little to go on.
    """
    defaults = Calibration()
    values, fell_back = {}, []
    for field in ("W0", "B", "rho", "omega", "theta", "Sc", "oBar", "dBar"):
        value = measured.get(field)
        if value is None or value != value or value in (float("inf"), float("-inf")):
            values[field] = getattr(defaults, field)
            fell_back.append(field)
        else:
            values[field] = value
    return Calibration(**values), fell_back


def analyse(summary, current_window):
    cal, fell_back = calibration_from(summary["calibration"])
    pricing = Pricing()

    rows = []
    for label, key, beta, blurb in TASK_SIZES:
        scenario = Scenario(Y=1_000_000, phi0=1.8, beta=beta)
        found = optimal_window(SEARCH_LO, SEARCH_HI, scenario, cal, pricing)
        if found is None:
            continue
        # Context windows are chosen in coarse steps; a value like 154,798 reads
        # as false precision and is no cheaper than the round number beside it.
        best = evaluate(round(found.W / 1000) * 1000, scenario, cal, pricing)
        here = evaluate(current_window, scenario, cal, pricing) if current_window else None
        multiple = (here.cost / best.cost) if (here and best.cost > 0) else float("nan")
        # Round once so the printed multiple and the verdict cannot disagree:
        # 1.4995 shown as "1.50x" beside "close enough" reads as a bug.
        if multiple == multiple:
            multiple = round(multiple, 2)
        rows.append({
            "label": label, "key": key, "beta": beta, "blurb": blurb,
            "optimal_W": best.W,
            # How many times over the task consumes at the current window.
            "usage_multiple": multiple,
            "wasted_share": wasted_share(multiple),
            "verdict": verdict(multiple, summary["calls"]),
            # Context only — never what the thresholds look at.
            "window_gap": abs(current_window - best.W) if current_window else float("nan"),
            "at_search_edge": best.W >= SEARCH_HI * 0.99 or best.W <= SEARCH_LO * 1.01,
        })
    return cal, rows, fell_back


def settings_for(window, theta):
    """
    The pair of config values that puts this model's optimum into Codex.

    The compact limit is theta*W: the same absolute trigger the sessions were
    measured at, moved to the recommended window, so the cost prediction still
    describes what the harness will actually do.
    """
    window = round(window / 1000) * 1000
    return window, round(window * theta / 1000) * 1000


# ----------------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------------


def bold(text):
    return "\033[1m{}\033[0m".format(text) if sys.stdout.isatty() else text


def fmt_w(v):
    return "—" if v != v else "{:,.0f}K".format(v / 1000)


def main():
    ap = argparse.ArgumentParser(description="Recommend a Codex context window from local session history.")
    ap.add_argument("--root", action="append", default=None, help="Session directory (repeatable)")
    ap.add_argument("--include-archived", action="store_true", help="Also scan ~/.codex/archived_sessions")
    ap.add_argument("--since", help="Only sessions on/after this date (YYYY-MM-DD)")
    ap.add_argument("--limit", type=int, help="Randomly sample at most N session files")
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--json", dest="json_out", help="Write the result as JSON")
    ap.add_argument("--config", default=CODEX_CONFIG, help="Path to Codex config.toml")
    ap.add_argument("--apply", type=int, metavar="WINDOW",
                    help="Write model_context_window into config.toml and exit")
    ap.add_argument("--compact-limit", type=int, metavar="TOKENS",
                    help="model_auto_compact_token_limit to write alongside --apply")
    ap.add_argument("--quiet", action="store_true", help="Suppress the progress bar")
    args = ap.parse_args()

    if args.apply:
        window = round(args.apply / 1000) * 1000
        limit = args.compact_limit
        if limit is None:
            # Fall back to the headroom the Codex docs use, and say so.
            limit = round(window * 0.9 / 1000) * 1000
            print("No --compact-limit given; using the 0.9 ratio from the official example.")
        backup, replaced = write_window_settings(window, limit, args.config)
        print("Wrote {}".format(args.config))
        print("  model_context_window           = {:,}".format(window))
        print("  model_auto_compact_token_limit = {:,}   (compaction fires at this)".format(limit))
        for key, old in replaced.items():
            print("  replaced: {}".format(old))
        print("  backup: {}".format(backup))
        print("\nRestart Codex and start a new session for this to take effect.")
        print("To undo, copy the backup back over the config.")
        return 0

    roots = args.root or [os.path.expanduser(r) for r in calibrate.DEFAULT_ROOTS]
    if args.include_archived:
        roots.append(os.path.expanduser(calibrate.ARCHIVED_ROOT))

    print(bold("Codex context window advice"))
    print("=" * 70)
    for r in roots:
        print("  source  {}".format(calibrate.short_path(r)))

    sessions, files = collect_sessions(roots, args)
    if not sessions:
        print("\nNo usable Codex sessions found.", file=sys.stderr)
        return 1

    summary = calibrate.summarize(sessions)
    config = read_config(args.config)

    # The window actually in use. config.toml wins when set, because it is what
    # the next session will use; otherwise fall back to what the logs report.
    configured = config.get("model_context_window")
    configured_limit = config.get("model_auto_compact_token_limit")
    current_window = configured or summary["dominant_window"]

    cal, rows, fell_back = analyse(summary, current_window)

    # ---- measured parameters ------------------------------------------------
    print("\n" + bold("Measured parameters") + "  ({:,} sessions · {:,} model calls{})".format(
        summary["n_sessions"], summary["calls"],
        " · {} → {}".format(*summary["date_range"]) if summary["date_range"] else ""))
    print("─" * 70)
    print("  W₀ {:>9,.0f}   B {:>8,.0f}   θ {:.4f}   S_c {:>7,.0f}".format(
        cal.W0, cal.B, cal.theta, cal.Sc))
    # d̄ carries a zero-width combining macron, hence the extra space.
    print("  ρ  {:>9.4f}   ω {:>8.4f}   ō {:>6,.0f}   d̄   {:>7,.0f}".format(
        cal.rho, cal.omega, cal.oBar, cal.dBar))
    if fell_back:
        print("  ! no value in the logs for {} — using the model default".format(
            ", ".join(fell_back)))

    # ---- current state ------------------------------------------------------
    print("\n" + bold("Current setup"))
    print("─" * 70)
    model = config.get("model", "(not set in config)")
    print("  model                   {}".format(model))
    print("  current context window  {}{}".format(
        fmt_w(current_window),
        "   (set in config.toml)" if configured else "   (from the session logs; not set in config.toml)"))
    if configured_limit:
        print("  compaction fires at     {}   (set in config.toml)".format(fmt_w(configured_limit)))
    else:
        print("  compaction fires at     {}   (measured θ×W; not set in config.toml)".format(
            fmt_w(current_window * cal.theta)))

    # ---- recommendation -----------------------------------------------------
    print("\n" + bold("What the same work consumes at your window vs at the best one"))
    print("─" * 70)
    print("  {:<9}{:>13}{:>9}{:>10}{:>13}      {}".format(
        "task size", "best window", "uses", "savable", "window gap", "verdict"))
    labels = {"ok": "close enough", "advise": "worth changing", "strong": "change this"}
    for r in rows:
        mark = {"ok": " ", "advise": "!", "strong": "!!"}[r["verdict"]]
        mult = "—" if r["usage_multiple"] != r["usage_multiple"] else "{:.2f}×".format(r["usage_multiple"])
        print("  {:<9}{:>13}{:>9}{:>10}{:>13}   {:<2} {}".format(
            r["label"], fmt_w(r["optimal_W"]), mult,
            "{:.0f}%".format(r["wasted_share"] * 100),
            fmt_w(r["window_gap"]), mark, labels[r["verdict"]]))
    print()
    print("  \"uses\" is how many times over the same task consumes at the current")
    print("  window compared with the best window. On a subscription that is how fast")
    print("  the quota burns down; on the API it is the bill — the same quantity.")
    print("  The verdict looks at that multiple, never at the window gap: consumption")
    print("  is flat near its minimum, so a large window gap can still mean almost no")
    print("  difference (the window-gap column is context only).")

    worst = max(rows, key=lambda r: {"ok": 0, "advise": 1, "strong": 2}[r["verdict"]])
    medium = next((r for r in rows if r["key"] == "medium"), rows[0])
    heaviest = max(
        rows, key=lambda r: r["usage_multiple"] if r["usage_multiple"] == r["usage_multiple"] else -1
    )

    print("\n" + bold("Verdict"))
    print("─" * 70)
    if worst["verdict"] in ("advise", "strong"):
        lead = "▲ Change this. " if worst["verdict"] == "strong" else "• Worth changing. "
        print("  {}Every run of a {} task currently consumes {:.2f}× as much.".format(
            lead, worst["label"], worst["usage_multiple"]))
        print("    Move to a {} window and the same work uses {:.0f}% less.".format(
            fmt_w(worst["optimal_W"]), worst["wasted_share"] * 100))
    elif summary["calls"] < MIN_CALLS:
        print("  Only {:,} model calls so far (threshold {:,}) — too little data to act".format(
            summary["calls"], MIN_CALLS))
        print("    on. Come back after using Codex for a while longer.")
    else:
        print("  ✓ No change needed. At the current {}, all three task sizes stay".format(
            fmt_w(current_window)))
        print("    within {:.1f}× of the best window (the heaviest is a {} task, at {:.2f}×).".format(
            ADVISE_MULTIPLE, heaviest["label"], heaviest["usage_multiple"]))

    if worst["verdict"] in ("advise", "strong"):
        window, limit = settings_for(medium["optimal_W"], cal.theta)
        print("\n  Codex takes one setting for everything, so use the medium task's optimum:")
        print("    model_context_window           = {}".format(window))
        print("    model_auto_compact_token_limit = {}".format(limit))
        print("    apply it: python3 {} --apply {} --compact-limit {}".format(
            os.path.basename(__file__), window, limit))
        print("\n  Both keys must be set together. The compact limit is the model's θ×W,")
        print("  carried over at the measured θ={:.4f}, so the cost prediction still".format(cal.theta))
        print("  describes what the harness will actually do.")
    if any(r["at_search_edge"] for r in rows):
        print("\n  ⚠ An optimum landed on the edge of the search range ({}–{}); the".format(
            fmt_w(SEARCH_LO), fmt_w(SEARCH_HI)))
        print("    true best value may lie outside it.")

    # ---- visualiser ---------------------------------------------------------
    print("\n" + bold("Interactive visualiser (pre-loaded with your measurements)"))
    print("─" * 70)
    for r in rows:
        print("  {:<6} task  {}".format(r["label"], build_url(cal, current_window, r["beta"])))

    print("\n  β (how much information a task needs) has no canonical value, so the three")
    print("  values above are illustrative. φ₀ and Y only scale the amount and do not")
    print("  move the best W, so not being able to measure them does not change the advice.")

    if args.json_out:
        payload = {
            "measured": {k: (round(v, 5) if v < 10 else round(v)) for k, v in summary["calibration"].items()},
            "evidence": {
                "sessions": summary["n_sessions"], "model_calls": summary["calls"],
                "date_range": summary["date_range"],
                "windows_observed": {str(k): v for k, v in summary["windows"].items()},
                "min_calls_for_advice": MIN_CALLS,
            },
            "current": {
                "model": config.get("model"),
                "window": current_window,
                "configured_model_context_window": configured,
                "configured_model_auto_compact_token_limit": configured_limit,
            },
            "recommendations": [
                {k: v for k, v in r.items() if k != "blurb"} for r in rows
            ],
            "urls": {r["key"]: build_url(cal, current_window, r["beta"]) for r in rows},
            "overall_verdict": worst["verdict"],
            "suggested_config": dict(
                zip(CONFIG_KEYS, settings_for(medium["optimal_W"], cal.theta))
            ) if worst["verdict"] in ("advise", "strong") else None,
        }
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print("\n  Wrote {}".format(args.json_out))

    return 0


def collect_sessions(roots, args):
    return calibrate.collect(
        roots,
        since=args.since,
        limit=args.limit,
        workers=args.workers,
        show_progress=not args.quiet,
    )


if __name__ == "__main__":
    sys.exit(main())
