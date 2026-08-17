---
name: context-window-advisor
description: Recommend the least wasteful Codex context-window size from the user's own local session history. Use when the user asks how large their context window should be, whether their current window is burning more usage than it needs to, how much extra a task is consuming, why their weekly quota or API bill runs out fast, or wants their Codex token telemetry turned into concrete `model_context_window` and `model_auto_compact_token_limit` settings. Measures compaction behaviour, cache hit rate, per-call output and context growth from ~/.codex/sessions, finds the window that minimises consumption for small/medium/large tasks, returns a visualiser URL carrying the measured parameters, and can apply the settings to config.toml.
---

# Context Window Advisor

## Overview

Codex logs every model call's input context, cache split, output size, and every
compaction event. That is enough to measure the parameters of the Agent Task Cost
cost model — and once those are known, the context window that a task consumes
least at follows from the model rather than from guesswork.

This skill reads the user's local session history, computes the least wasteful
window for three task sizes, compares it against the window they are actually
running, and offers to change the setting.

Everything the user sees is stated as a multiple of what the task would consume
at its best window. That reads the same on a subscription and on the API, because
metered consumption is weighted the way the price list is — usage and bill are
one quantity.

Everything runs locally with the Python standard library. The only thing that
leaves the machine is a URL the user may choose to open.

**Reply in whatever language the user is writing in.** The scripts print English,
but nothing about that constrains your own response — translate the findings into
their language rather than pasting the raw output at them.

## Workflow

### 1. Run the analysis

```bash
python3 <skill_dir>/scripts/advise.py --json /tmp/context-window-advice.json
```

Useful flags:

- `--include-archived` — also scan `~/.codex/archived_sessions`. More data, roughly
  double the scan time. Worth it when `~/.codex/sessions` holds few sessions.
- `--since YYYY-MM-DD` — restrict to recent history, which matters when the user
  changed models or harness settings recently.
- `--limit N` — sample N session files, for a quick check on a large history.
- `--quiet` — no progress bar.

A full scan of tens of GB takes seconds; do not pre-emptively limit it.

Read the JSON rather than scraping stdout. Its shape:

```
measured           the eight calibration parameters (W0, B, rho, omega, theta, Sc, oBar, dBar)
evidence           session count, model calls, date range, windows observed
current            model, window, and either configured key if config.toml sets them
recommendations[]  per task size: optimal_W, usage_multiple, wasted_share, verdict, window_gap
urls               visualiser link per task size
overall_verdict    "ok" | "advise" | "strong"
suggested_config   {model_context_window, model_auto_compact_token_limit} — null when nothing to change
```

If no sessions are found, say so and stop. Do not fabricate a recommendation.

### 2. Report to the user

Give them, in this order:

1. **The current window** and where it came from — `config.toml` if either
   configured key is set, otherwise the session records.
2. **The least wasteful window per task size**, with `usage_multiple` stated in
   plain words: "a small task currently uses 1.35× what it would at 98K". That
   sentence is the whole point; lead with it.
3. **The visualiser URL** for whichever task size is most relevant, so they can
   see the curve with their own numbers. Hand over the link; do not fetch it.

State plainly that β — how much pre-existing information a task needs held at
once — has no calibrated value, so the three task sizes use illustrative values.
φ₀ and Y cannot be measured either, but they only scale the bill and do not move
the optimal window, so the recommendation does not depend on them.

### 3. Offer the change, then ask

`overall_verdict` is the worst verdict across the three task sizes:

| verdict | meaning | what to do |
|---|---|---|
| `ok` | every task size is within threshold | say so, change nothing |
| `advise` | `usage_multiple` ≥ 1.5× | mention it, offer the change |
| `strong` | `usage_multiple` ≥ 2.0× | lead with it, recommend the change |

**Speak in multiples, not money.** `usage_multiple` is how many times over the
same task consumes at the current window — "this task currently uses 2.1× what it
needs to". That reads correctly whether the user is on a subscription (quota
burns 2.1× faster) or on the API (bill is 2.1×), because consumption is metered
the way the price list is weighted; they are one quantity, not two. Do not
translate it into dollars: the model's dollar figure depends on `Y` and `φ₀`,
which are arbitrary, so only the ratio carries meaning.

`wasted_share` is the same fact from the other side — the fraction of current
consumption that the optimum would not have spent. Use whichever reads better.

**Thresholds are on the multiple, never on window size.** Consumption is
second-order flat around its minimum, so the distance between the current window
and the optimal one says almost nothing — an 81K window gap can mean 1.04×.
`window_gap` is reported for context only and must not drive the decision.

Below `min_calls_for_advice` model calls the verdict is forced to `ok`: the
measurement is too thin to act on and the setup is too lightly used to matter.
Say that rather than presenting a recommendation.

When there is something to change, ask the user before touching anything.
`suggested_config` uses the medium-task optimum, since Codex takes one
`model_context_window` value. If they mostly do one size of work, offer that
size's `optimal_W` instead.

### 4. Apply it only if they agree

Codex needs **two** top-level keys, and they have to move together:

```toml
model_context_window           = 1000000   # the total context budget
model_auto_compact_token_limit = 900000    # where automatic compaction starts
```

The second one is this model's θ·W — the absolute token count at which a
compaction fires — so it is written directly with no ratio to guess. Setting only
the window would leave compaction firing wherever the harness defaults it, and
the cost prediction would no longer describe what actually happens.

`suggested_config` in the JSON already carries both values; the compact limit
uses the θ measured from the user's own sessions, so their compaction cadence
carries over to the new window.

```bash
python3 <skill_dir>/scripts/advise.py --apply <window> --compact-limit <tokens>
```

Both keys are written above the first `[section]` header (TOML would otherwise
read them as belonging to that section), the rest of the file is preserved, and
the original is copied to a timestamped `.bak-` file beside it. Tell the user the
backup path, and that Codex has to be restarted with a **new session** before the
setting takes effect.

Omitting `--compact-limit` falls back to the 0.9 ratio used in the official
example and says so; prefer passing the measured value.

Never edit `config.toml` by hand — the script handles placement and the backup.

## Interpreting the result

The recommendation trades two effects that pull in opposite directions:

- A **larger** window means every request re-reads more context. Input dominates
  the bill, so this rises quickly.
- A **smaller** window means more compactions, and each compaction both costs a
  model call and throws away context the agent then has to rebuild.

The optimum sits between them, and it moves with how much information the task
needs resident — not with how big the repository is. A localised fix in a large
monorepo wants a small window; a cross-cutting refactor in a small repo wants a
large one.

If a recommendation lands at the edge of the search range the script says so; the
true optimum may lie outside 48K–1M.

## Standalone calibration report

For the full measurement detail — per-model `ō`, per-workspace `d̄`, compaction
statistics, and the cross-window comparison that would be needed to actually
estimate β — run the analyser directly:

```bash
python3 <skill_dir>/scripts/calibrate.py --include-archived
```

## Requirements

Python 3.9+, standard library only. No network access is used or needed.
