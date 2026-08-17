# Calibrating from Codex session logs

The model has eight session parameters. All eight can be measured from the
rollout logs Codex already writes to `~/.codex/sessions`, which is what the
`context-window-advisor` skill does.

This page documents where each number comes from, so the measurement can be
audited or reimplemented.

## What the logs contain

Each session is a JSONL file, one record per line. Three record types matter:

| Record | Field | Gives |
| --- | --- | --- |
| `event_msg` / `token_count` | `info.last_token_usage.input_tokens` | $S_t$ — the context of that model call |
| `event_msg` / `token_count` | `info.last_token_usage.cached_input_tokens` | the cached share of that input |
| `event_msg` / `token_count` | `info.last_token_usage.output_tokens` | billed output for that call |
| `event_msg` / `token_count` | `info.model_context_window` | the window in effect |
| `event_msg` / `context_compacted` | — | a compaction fired here |
| `turn_context` | `model`, `effort` | which model produced the surrounding calls |
| `session_meta` | `cwd`, `thread_source`, `parent_thread_id`, `forked_from_id` | workspace and session lineage |

The important consequence: `last_token_usage.input_tokens` **is** the model's
$S_t$. The entire context walk can be reconstructed call by call rather than
inferred. And because `context_compacted` is an explicit event, $\theta$ and
$S_c$ are measured directly instead of being guessed from drops in $S_t$.

## How each parameter is derived

| Parameter | Derivation |
| --- | --- |
| $W$ | `model_context_window`, the window Codex actually used |
| $B$ | the first call's `input_tokens`, **root sessions only** |
| $\rho$ | $\sum$ `cached_input_tokens` $\div \sum$ `input_tokens` |
| $\omega$ | $\sum$ `cache_write_input_tokens` $\div \sum$ `input_tokens` |
| $\theta$ | (context on the call before a `context_compacted`) $\div\ W$ |
| $S_c$ | the context on the first call after a `context_compacted` |
| $\bar o$ | $\sum$ `output_tokens` $\div$ number of model calls |
| $\bar d$ | mean of $S_{t+1} - S_t$ over consecutive calls **within** one cycle |

## Three things that are easy to get wrong

**$B$ must exclude subagent and forked threads.** Those start mid-conversation,
so their "first request" is inherited history, not the fixed prefix. Without the
filter, a session that resumed at 221K context reports that as $B$. Codex marks
lineage in `session_meta` via `thread_source`, `parent_thread_id` and
`forked_from_id`, so the filter is exact rather than heuristic.

**$\bar d$ must be the mean, not the median.** The distribution is heavily
right-skewed — on one real corpus the median was 517 and the mean 1,480, with p10
at 61 and p90 at 4,461, because a few large tool results account for most of the
growth. The recurrence accumulates *total* growth ($S = S_0 + n\bar d$ after $n$
steps), so the mean is the correct statistic. Using the median would understate
compaction frequency by roughly threefold.

**Steps that cross a compaction are not growth.** The difference $S_{t+1} - S_t$
across a compaction boundary is a reset, not history growth, so those pairs are
excluded from $\bar d$.

## What varies with what

$\bar o$ is not a global constant — it is a property of the model and its
reasoning effort. Measured on one corpus it ranged from 90 (a lightweight review
model) to 1,451 (a small model at high effort), with the main model around 350.
It has to be stratified by model × effort.

$\bar d$ varies by workspace, since file sizes and search noise differ between
repositories. It should be stratified per workspace rather than pooled.

$\rho$, $\theta$ and $S_c$ are harness properties and are stable globally for a
given harness version.

## What cannot be measured this way

$\phi_0$ and $Y$ both need to know which output actually accomplished the task,
and the logs contain no such ground truth. $\beta$ needs the same kind of work
observed at several different context windows.

Sessions do typically span more than one window — a real corpus showed 121.6K,
258.4K and 353.4K, with the compaction rate per call falling monotonically across
them (0.0179 → 0.0069 → 0.0051). That is the raw material for estimating $\beta$
by natural experiment, though controlling for model and task type first is
essential.

For why the recommendation does not actually need $\phi_0$ or $Y$, see
[cost-model.md](cost-model.md#classifying-the-variables).

## Running it

```bash
# Full calibration report
python3 .agents/skills/context-window-advisor/scripts/calibrate.py --include-archived

# Measurement plus a context-window recommendation
python3 .agents/skills/context-window-advisor/scripts/advise.py
```

Standard library only, Python 3.9+. Nothing is sent anywhere; the scripts read
local files and print. A full scan of tens of gigabytes takes seconds.

## Feeding measurements into the visualiser

The web page accepts a calibration in its query string, so a measurement can be
opened as a link:

```
https://jacoblincool.github.io/AgentTaskCost/?w0=258400&b=22109&rho=0.97176&theta=0.87262&sc=32260&obar=376&dbar=1479&beta=0.15&w=258400
```

| Parameter | Meaning |
| --- | --- |
| `w0` `b` `rho` `omega` `theta` `sc` `obar` `dbar` | the calibration |
| `y` `phi0` `beta` | the scenario |
| `w` | the context window to inspect |
| `from` `to` | sweep range |
| `src` | free-form origin tag, shown in the banner |

Every value is range-checked before use; a URL is untrusted input, and an
out-of-range number is ignored rather than rendered as a broken chart.
