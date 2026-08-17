# The cost model

A model for the dollar cost of finishing a fixed agent task, with the
context-window limit $W$ as the independent variable.

## Overview

The causal chain is:

$$
\text{Context window}
\rightarrow
\text{Output inflation}
\rightarrow
\text{Model calls}
\rightarrow
\text{Repeated context input}
\rightarrow
\text{Task cost}
$$

There is exactly one dependent variable:

$$
C_{\mathrm{task}} = \text{the dollar cost of finishing a fixed task}
$$

Written out in full:

$$
C_{\mathrm{task}} = F\left(W;\ Y,\ \phi_0,\ \beta,\ \Phi_{\mathrm{session}},\ \Pi_{\mathrm{price}}\right)
$$

where:

- $W$ — the independent variable, the context-window limit.
- $Y$ — the effective output the task requires.
- $\phi_0, \beta$ — behavioural parameters for the output inflation a small context causes.
- $\Phi_{\mathrm{session}}$ — parameters calibrated from historical sessions.
- $\Pi_{\mathrm{price}}$ — model price parameters.

Output, model calls, input tokens and compactions are all **intermediate
quantities or diagnostics**, never additional dependent variables. The main
chart fixes $Y = 1{,}000{,}000$, sweeps $W$ on the x-axis, and plots
$C_{\mathrm{task}}(W)$ on the y-axis.

## Design principle: no double counting

In a model like this it is easy to let several near-synonymous variables describe
the same thing:

- A tool-call multiplier and a semantic-efficiency discount both describe extra
  retrieval, extra tool calls, and rework.
- An effective-output ratio, tool-control output, and rework output all describe
  how much total output a fixed amount of real work requires.
- Per-call output, tool-result size, and other appended messages all describe how
  much the context grows after one model call.

Putting all of them in the formula prices the same phenomenon several times over.
To avoid that, everything collapses into two parameters:

- an **output-inflation response** $\phi(W)$, absorbing everything about efficiency;
- an **empirical net-context-growth parameter** $\bar d$, absorbing everything
  about context growth.

So there is no separate $O_{\mathrm{tool}}$ or $O_{\mathrm{rework}}$, and context
sensitivity needs the single parameter $\beta$ rather than a family of penalty
parameters.

## Core definitions

### Output inflation $\phi(W)$

The model uses one efficiency variable, the **output inflation factor**:

$$
\phi(W) = \frac{O_{\mathrm{billed}}(W)}{Y_{\mathrm{effective}}}
$$

Read directly:

- $\phi(W) = 1$ — 1M effective output takes 1M billed output.
- $\phi(W) = 1.5$ — 1M effective output takes 1.5M billed output.
- $\phi(W) = 3$ — 1M effective output takes 3M billed output.

Every wasted or indirect token counts toward $\phi$: tool-call arguments, shell
scripts, search queries, re-retrieving information, re-reading and re-analysing,
failed attempts, regeneration, rebuilding context after a compaction, and any
reasoning or output that ends up not contributing to task completion.

### History span $H(W)$

The room a context window has to accumulate new history within one compaction
cycle:

$$
H(W) = \theta W - S_c
$$

where $\theta W$ is the context size that triggers compaction and $S_c$ is what
is left afterwards. With the canonical constants $\theta = 0.9$ and
$S_c = 32\mathrm{K}$:

$$
H(W) = 0.9W - 32\mathrm{K}
$$

At the reference window $W_0 = 256\mathrm{K}$:

$$
H_0 = H(W_0) = 0.9 \times 256\mathrm{K} - 32\mathrm{K} = 198.4\mathrm{K}
$$

### Productivity response function

One context-sensitivity parameter $\beta \ge 0$:

$$
\phi(W) = \phi_0 \max\left[1,\ \left(\frac{H_0}{H(W)}\right)^\beta\right]
$$

where $\phi_0$ is the baseline output inflation at $W_0 = 256\mathrm{K}$.

- At $W = W_0$, $H(W) = H_0$, so $\phi(W_0) = \phi_0$.
- Below $W_0$, $H(W) < H_0$, so $\phi(W) > \phi_0$: the smaller the context, the
  more total billed output a fixed amount of real work takes.
- At or above $W_0$, productivity is assumed not to improve further, so
  $\phi(W) = \phi_0$. This is a deliberately conservative saturation assumption;
  whether 512K or 1M pushes $\phi$ down further needs experiments at several
  windows to decide.

What $\beta$ means:

- $\beta = 0$ — context-window size has no effect on output productivity.
- $\beta > 0$ — the smaller the usable history span per cycle, the worse the
  output inflation; a larger $\beta$ means a harsher penalty for a small context.

Intuitively, $\beta$ encodes **how much pre-existing information the task needs
held at once**. When a task moves forward on a small amount of context, whatever
a compaction discards is cheap to recover and $\beta$ is near 0. When a task
needs a large body of existing information resident, every compaction forces that
context to be rebuilt and $\beta$ is large. For coding work, codebase size is a
reasonable intuitive proxy, but what actually sets $\beta$ is the information the
task itself requires, not the boundary of a repository — a single-file change in
a large monorepo is still low $\beta$.

This also separates $\beta$ from $\phi_0$:

- $\phi_0$ is the fixed overhead of **finding** information: searching, reading
  irrelevant files, going down dead ends. It does not change with $W$, so it is
  only a multiplier on the whole cost curve.
- $\beta$ is the amount of information that must be **held at once**. It sets how
  harsh shrinking $W$ is, which makes it the only user-facing parameter that
  materially moves the optimal $W$.

Both tend to rise together on a large codebase, but they act on the curve very
differently: $\phi_0$ changes the size of the bill, $\beta$ changes which context
window you should pick.

### Total billed output $O(W)$

With $Y = Y_{\mathrm{effective}}$ fixed:

$$
O(W) = Y\,\phi(W)
$$

For example, $Y = 1\mathrm{M}$ and $\phi(W) = 2.4$ give $O(W) = 2.4\mathrm{M}$:
finishing 1M of effective output actually emitted 2.4M billed output tokens.
$O(W)$ belongs in the visualiser, but it is a diagnostic derived from the
formula, not another dependent variable.

### Model calls $N(W)$

With $\bar o$ the mean billed output tokens per model inference:

$$
N(W) = \left\lceil \frac{O(W)}{\bar o} \right\rceil
$$

The whole derivation needs only $Y \rightarrow O(W) \rightarrow N(W)$.

### Context growth and compaction

Let $S_t$ be the input context tokens of the $t$-th model inference, starting at
$S_1 = B$.

Let $\bar d$ be the mean net history growth after each model call: model output
appended back to the conversation, tool results, tool metadata, environment
output, and any other new messages. Splitting those sources into separate
variables would model the same thing more than once, so a single
session-calibrated $\bar d$ covers them.

The context recurrence is $\widetilde S_{t+1} = S_t + \bar d$, and:

$$
S_{t+1} =
\begin{cases}
S_c, & \widetilde S_{t+1} \ge \theta W \\
\widetilde S_{t+1}, & \widetilde S_{t+1} < \theta W
\end{cases}
$$

The number of compactions is:

$$
K(W) = \sum_{t=1}^{N(W)-1} \mathbf{1}\left[S_t + \bar d \ge \theta W\right]
$$

### Input token split and pricing

The context $S_t$ of the $t$-th request splits into:

$$
I_t^{c} = \rho S_t,\qquad
I_t^{u} = (1-\rho-\omega)S_t,\qquad
I_t^{w} = \omega S_t
$$

with $\rho$ the cached-read share, $\omega$ the cache-write share, and the rest
ordinary uncached input.

Standard GPT-5.6 Sol prices, USD per 1M tokens:

| Symbol | Item | Price |
| --- | --- | ---: |
| $p_u$ | uncached input | 5.00 |
| $p_c$ | cached input read | 0.50 |
| $p_w$ | cache write | 6.25 |
| $p_o$ | output | 30.00 |

A request whose input exceeds 272K is billed at 2× input and 1.5× output for the
whole request[^1]:

$$
\ell_I(S_t) =
\begin{cases}
1, & S_t \le 272\mathrm{K} \\
2, & S_t > 272\mathrm{K}
\end{cases}
\qquad
\ell_O(S_t) =
\begin{cases}
1, & S_t \le 272\mathrm{K} \\
1.5, & S_t > 272\mathrm{K}
\end{cases}
$$

## The full cost formula

With $o_t$ the output of the $t$-th model call and
$\sum_{t=1}^{N(W)} o_t = O(W)$, the single dependent variable is:

$$
\begin{aligned}
C_{\mathrm{task}}(W)
=&\ \frac{1}{10^6}
\sum_{t=1}^{N(W)}
\Big\{
\ell_I(S_t)\left[p_u I_t^u + p_c I_t^c + p_w I_t^w\right]
+ \ell_O(S_t)\,p_o\,o_t
\Big\} \\
&+ K(W)\,c_{\mathrm{compact}} + C_{\mathrm{tool,direct}}
\end{aligned}
$$

where:

$$
O(W) = Y\phi(W),\qquad
N(W) = \left\lceil \frac{O(W)}{\bar o} \right\rceil,\qquad
\phi(W) = \phi_0 \max\left[1, \left(\frac{H_0}{H(W)}\right)^\beta\right],\qquad
H(W) = \theta W - S_c
$$

and $S_t$ follows the compaction recurrence. Tool counts enter only when a tool
carries a direct monetary fee:

$$
C_{\mathrm{tool,direct}} = \sum_j n_j c_j
$$

### The price of one compaction

$c_{\mathrm{compact}}$ is not a free parameter — it follows from the parameters
already in the model. A compaction is itself an extra model call: it reads the
context that triggered it (about $\theta W$) and writes the summary that replaces
the history.

What it writes is $S_c - B$, not $S_c$. $B$ is the fixed prefix — system
instructions, tool definitions, the task description — which a compaction does
not rewrite. Only the history is replaced, so what is actually generated is $S_c$
minus that prefix. With canonical values that is
$32\mathrm{K} - 24\mathrm{K} = 8\mathrm{K}$, not 32K.

Both sides carry the long-context multipliers:

$$
c_{\mathrm{compact}}(W)
=
\frac{
\ell_I(\theta W)\,\bar p_I\,\theta W
+
\ell_O(\theta W)\,p_o\,(S_c - B)
}{10^6},
\qquad
\bar p_I = p_u(1-\rho-\omega) + p_c\rho + p_w\omega
$$

These compaction calls are not among the $N(W)$ task calls, so
$K(W)\,c_{\mathrm{compact}}$ is a separate term and nothing is double counted.

At $W = 256\mathrm{K}$, $c_{\mathrm{compact}} \approx 0.38$ USD: $0.24$ to write
the 8K summary plus $0.14$ to read $\theta W$. Reading 230.4K tokens costs only
$0.14 because almost all of it is a cache hit; the output is billed at full
$p_o$.

The term is not negligible at small windows. The smaller $H(W)$ is, the faster
$K(W)$ climbs:

| $W$ | $K(W)$ | $c_{\mathrm{compact}}$ | compaction subtotal | share of $C_{\mathrm{task}}$ |
| ---: | ---: | ---: | ---: | ---: |
| 64K | 717 | $0.28 | $197 | 28.7% |
| 128K | 135 | $0.31 | $42 | 9.1% |
| 256K | 38 | $0.38 | $14 | 3.0% |
| 512K | 17 | $0.92 | $16 | 1.2% |
| 1M | 8 | $1.49 | $12 | 0.4% |

($Y = 1\mathrm{M}$, $\phi_0 = 1.8$, $\beta = 0.45$. $c_{\mathrm{compact}}$ jumps
around $W \approx 302\mathrm{K}$ because $\theta W$ crosses the 272K threshold.)

Treating $c_{\mathrm{compact}}$ as zero understates what a small context costs:
in the scenario above, ignoring it moves the apparent optimum from 161K to 122K.

## Simplified approximation

Away from the 272K long-context tier, and for a project long enough to go through
many compaction cycles:

$$
\bar S(W) \approx \frac{S_c + \theta W}{2},\qquad
p_{\mathrm{eff}} = (1-\rho)p_u + \rho p_c,\qquad
N(W) \approx \frac{Y\phi(W)}{\bar o}
$$

giving:

$$
C_{\mathrm{task}}(W)
\approx
\frac{Y\phi(W)}{10^6}
\left[p_o + \frac{\bar S(W)}{\bar o}\,p_{\mathrm{eff}}\right]
+ K(W)\,c_{\mathrm{compact}}
$$

which shows the two opposing effects plainly:

- **Larger context window** — $W\uparrow \Rightarrow \bar S(W)\uparrow$. Every
  request reads more input, so direct cost rises.
- **Smaller context window** — $W\downarrow \Rightarrow \phi(W)\uparrow
  \Rightarrow O(W)\uparrow \Rightarrow N(W)\uparrow$. The same task needs more
  output and more model calls.

So $C_{\mathrm{task}}(W)$ can have an interior minimum rather than being
monotonic in either direction.

## Classifying the variables

Where each number comes from determines how it can be obtained — measured from
history, looked up in a price list, or estimated by experiment.

| Variable | Primary source | Also affected by | Scope | Measurable from session logs? |
| --- | --- | --- | --- | --- |
| $p_u, p_c, p_w, p_o$ | provider price list | — | per model | look up |
| tier threshold, $\ell_I$, $\ell_O$ | provider price list | — | per model | look up |
| $\omega$ | provider billing model | harness | per model | only if telemetry itemises it |
| $\theta$ | harness setting | — | global | yes: context before compaction ÷ $W$ |
| $B$ | harness (system prompt, tool definitions) | workspace rules files, task text | mixed | yes: first request's input |
| $S_c$ | harness (requested summary length) | model compliance | global | yes: first request after a compaction |
| $\rho$ | harness cache strategy | provider TTL, usage rhythm | global | yes: cached ÷ total input |
| $C_{\mathrm{tool,direct}}$ | harness / integration | — | per workspace | yes: paid tool call counts |
| $\bar o$ | model behaviour (verbosity, reasoning) | harness effort setting, task type | per model × effort | yes: total output ÷ calls |
| $\bar d$ | harness (tool-result truncation) | workspace (file sizes, grep noise) | **per workspace** | yes: differences between adjacent requests |
| $\phi_0$ | model capability | workspace complexity, tool quality | per model × workspace | **no** — logs have no effective-output ground truth |
| $\beta$ | the task itself | workspace as a proxy | **per task** | **no** — needs observations at several $W$ |
| $Y$ | the task itself | — | per task | **no** |
| $W_0$ | calibration reference point | — | follows the data | it is a fact about the data, not a choice |

$W_0$ deserves a note: it is not a tunable parameter but the window at which
$\phi_0$ is *defined*. Recalibrating on sessions recorded at 512K means $W_0$
must become 512K too, or $\phi_0$ loses its meaning.

Three consequences matter for anyone building a recommender on this model:

**$Y$ and $\phi_0$ are unmeasurable but unnecessary.** Both are pure multipliers.
Sweeping $\phi_0$ from 1.2 to 6.0 moves the optimal $W$ by under 3%; $Y$ from
0.2M to 5M barely moves it either. They set the size of the bill, not the window
to choose.

**What can be measured determines the curve's shape; only $\beta$ is missing.**
$B$, $\theta$, $S_c$ and $\bar d$ fix how the context walks and how often it
compacts; $\rho$, $\omega$ and the price list fix what a token costs; $\bar o$
converts output into calls. All of them come out of session history. A
recommender is short exactly one parameter: $\beta$.

**$B$ should not be treated as one number.** It is the sum of the system prompt
(harness), tool definitions (harness × which MCP servers are connected),
rules files such as `AGENTS.md` (workspace), and the task description (task) —
four components with four different scopes. Estimating across contexts means
measuring them separately, or switching workspace and connecting two more MCP
servers will invalidate the whole figure.

## Getting at $\beta$

$\beta$ is the only parameter that decides the answer and the only one that
cannot be read off a log, so it is worth attacking directly. Besides a controlled
experiment — the same task set, several windows, each run to success — two routes
work from existing logs:

**Re-read rate after a compaction.** Count how often, after a compaction, the
agent re-reads a file or re-runs a search it already did before that compaction.
That directly reflects a working set that did not fit, needs no effective-output
ground truth, and is computable from tool-call logs alone. A high re-read rate
means a large $\beta$.

**Measure the working set and reparameterise.** Collect the distinct set of files
and resources a session touches and their total token size, giving a real
"information required" quantity $R$. Then rewrite $\phi(W)$ as a function of $R$
and $H(W)$ — for instance $\phi_0\max[1,(R/H(W))^\gamma]$ — so a single
experiment calibrates $\gamma$ once and every task's $R$ can be measured
thereafter. That replaces an abstract exponent with an observable quantity.

## The role of $M$ (tool calls per task)

An observed distribution:

$$
M_{50}=16,\quad
M_{\mathrm{mean}}=100,\quad
M_{90}=256,\quad
M_{95}=512
$$

These numbers are useful, but they **do not enter the core cost formula**. The
extra model activity $M$ causes is already absorbed by $\phi(W)$; scaling model
calls by $M$ again — anything of the form $N \propto M+1$ — would price the same
phenomenon twice.

$M$ belongs in workload strata instead:

$$
q \in \{\text{Typical},\ \text{Mean},\ \text{Heavy},\ \text{Very Heavy}\}
$$

with $\bar o_q,\ \bar d_q,\ \phi_{0,q},\ \beta_q$ estimated per group. That is,
$M$ is for **grouping and calibrating parameters**, not for entering the formula.

## Visualiser design

The main chart:

$$
x = W,\qquad y = C_{\mathrm{task}}(W)
$$

- **User controls** — $Y$, $\phi_0$, $\beta$.
- **Fixed calibration** — $B$, $\rho$, $\theta$, $S_c$, $W_0$, $\bar o$, $\bar d$.
- **Hover / side-panel diagnostics** — $\phi(W)$ (output inflation), $O(W)$
  (total billed output), $N(W)$ (model calls), $\sum S_t$ (total repeated input),
  $K(W)$ (compactions).

Diagnostics exist only to explain why the cost moved; the model has one formal
output, $C_{\mathrm{task}}(W)$.

To avoid overlapping controls — a tool-call multiplier, effective output per
turn, semantic efficiency, extra retrieval strength, tool-control output,
tool-result size, all knobs describing the same phenomenon twice — the UI
deliberately exposes one output-inflation response ($\phi_0$, $\beta$) and one
empirical net-context-growth parameter ($\bar d$).

## Implementation

`src/lib/model.ts` is the single implementation. It writes the "context grows
arithmetically between two compactions" structure as a closed form, so evaluating
any $W$ is $O(1)$ regardless of task size and sweeping the whole curve never
simulates individual model calls.

`.agents/skills/context-window-advisor/scripts/model.py` is a Python port used by
the skill. The two are checked against each other numerically; they must agree,
because the skill and the web page have to show the same number.

[^1]: [GPT-5.6 Sol — OpenAI API docs](https://developers.openai.com/api/docs/models/gpt-5.6-sol)
