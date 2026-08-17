"""
The Agent Task Cost model, in Python.

This is a port of src/lib/model.ts and must stay numerically identical to it —
the skill and the web page have to agree on the number they show the user.
Standard library only.

    Context window -> Output inflation -> Model calls -> Repeated input -> Cost
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Calibration:
    W0: float = 256_000  # reference window
    B: float = 24_000  # fixed prefix on the first request
    rho: float = 0.975  # cached-read share of input
    omega: float = 0.0  # cache-write share of input
    theta: float = 0.9  # fraction of W at which compaction fires
    Sc: float = 32_000  # context left after a compaction
    oBar: float = 350  # mean billed output tokens per model call
    dBar: float = 1_500  # mean net history growth per model call


@dataclass(frozen=True)
class Pricing:
    pu: float = 5.0  # uncached input, USD / 1M
    pc: float = 0.5  # cached input read
    pw: float = 6.25  # cache write
    po: float = 30.0  # output
    tier_threshold: float = 272_000
    tier_input_mult: float = 2.0
    tier_output_mult: float = 1.5
    tool_direct: float = 0.0


@dataclass(frozen=True)
class Scenario:
    Y: float = 1_000_000  # effective output the task requires
    phi0: float = 1.8  # baseline inflation at W0
    beta: float = 0.45  # information the task must hold at once


@dataclass(frozen=True)
class CostPoint:
    W: float
    phi: float
    O: float
    N: int
    compactions: int
    input_tokens: float
    mean_context: float
    input_cost: float
    output_cost: float
    compaction_cost: float
    tool_cost: float
    cost: float
    feasible: bool


def history_span(W: float, cal: Calibration) -> float:
    """H(W) = theta*W - S_c."""
    return cal.theta * W - cal.Sc


def inflation(W: float, s: Scenario, cal: Calibration) -> float:
    """phi(W) = phi_0 * max[1, (H_0 / H(W))^beta]."""
    h = history_span(W, cal)
    h0 = history_span(cal.W0, cal)
    if h <= 0 or h0 <= 0:
        return math.inf
    return s.phi0 * max(1.0, (h0 / h) ** s.beta)


def input_token_price(cal: Calibration, p: Pricing) -> float:
    return p.pu * (1 - cal.rho - cal.omega) + p.pc * cal.rho + p.pw * cal.omega


def compaction_output(cal: Calibration) -> float:
    """The summary a compaction writes: S_c minus the prefix it does not rewrite."""
    return max(0.0, cal.Sc - cal.B)


def compaction_cost(W: float, cal: Calibration, p: Pricing) -> float:
    """One compaction is an extra model call: read theta*W, write S_c - B."""
    read = cal.theta * W
    over = read > p.tier_threshold
    in_mult = p.tier_input_mult if over else 1.0
    out_mult = p.tier_output_mult if over else 1.0
    return (in_mult * input_token_price(cal, p) * read + out_mult * p.po * compaction_output(cal)) / 1e6


def _segment(S0: float, d: float, m: int, threshold: float):
    """Aggregate an arithmetic run of contexts in closed form."""
    if m <= 0:
        return 0.0, 0, 0.0
    total = m * S0 + (d * m * (m - 1)) / 2
    if d > 0:
        k0 = min(m, max(0, math.floor((threshold - S0) / d) + 1))
    else:
        k0 = 0 if S0 > threshold else m
    above_count = m - k0
    index_sum = ((m - 1) * m) / 2 - ((k0 - 1) * k0) / 2
    above_sum = above_count * S0 + d * index_sum
    return total, above_count, above_sum


def _segment_length(S0: float, d: float, thetaW: float) -> float:
    if S0 + d >= thetaW:
        return 1
    if d <= 0:
        return math.inf
    return max(1, math.ceil((thetaW - d - S0) / d) + 1)


def evaluate(W: float, s: Scenario, cal: Calibration, p: Pricing) -> CostPoint:
    thetaW = cal.theta * W
    phi = inflation(W, s, cal)

    if not math.isfinite(phi) or phi <= 0 or s.Y <= 0 or cal.oBar <= 0:
        inf = math.inf
        return CostPoint(W, phi, inf, 0, 0, inf, math.nan, inf, inf, inf, p.tool_direct, inf, False)

    O = s.Y * phi
    N = max(1, math.ceil(O / cal.oBar))
    o_per_call = O / N

    open_len = _segment_length(cal.B, cal.dBar, thetaW)
    cycle_len = _segment_length(cal.Sc, cal.dBar, thetaW)

    opening = int(min(N, open_len))
    rest = N - opening
    cycles = math.floor(rest / cycle_len) if math.isfinite(cycle_len) else 0
    partial = int(rest - cycles * cycle_len) if math.isfinite(cycle_len) else rest

    o_sum, o_ac, o_as = _segment(cal.B, cal.dBar, opening, p.tier_threshold)
    if math.isfinite(cycle_len):
        c_sum, c_ac, c_as = _segment(cal.Sc, cal.dBar, int(cycle_len), p.tier_threshold)
    else:
        c_sum, c_ac, c_as = 0.0, 0, 0.0
    p_sum, p_ac, p_as = _segment(cal.Sc, cal.dBar, partial, p.tier_threshold)

    input_tokens = o_sum + cycles * c_sum + p_sum
    tier_tokens = o_as + cycles * c_as + p_as
    tier_calls = o_ac + cycles * c_ac + p_ac

    completed = (1 if opening == open_len else 0) + cycles
    compactions = max(0, completed if partial > 0 else completed - 1)

    mix = input_token_price(cal, p)
    input_cost = mix * (input_tokens - tier_tokens + p.tier_input_mult * tier_tokens) / 1e6
    output_cost = p.po * o_per_call * (N - tier_calls + p.tier_output_mult * tier_calls) / 1e6
    comp_cost = compactions * compaction_cost(W, cal, p)

    return CostPoint(
        W=W,
        phi=phi,
        O=O,
        N=N,
        compactions=int(compactions),
        input_tokens=input_tokens,
        mean_context=input_tokens / N,
        input_cost=input_cost,
        output_cost=output_cost,
        compaction_cost=comp_cost,
        tool_cost=p.tool_direct,
        cost=input_cost + output_cost + comp_cost + p.tool_direct,
        feasible=True,
    )


def sweep(lo: float, hi: float, steps: int, s: Scenario, cal: Calibration, p: Pricing):
    a, b = math.log(lo), math.log(hi)
    return [
        evaluate(math.exp(a + (b - a) * i / (steps - 1)), s, cal, p)
        for i in range(steps)
    ]


def optimal_window(lo: float, hi: float, s: Scenario, cal: Calibration, p: Pricing, steps: int = 400):
    """
    Coarse log sweep, then a golden-section refine on the bracket.

    Cost is the objective, and it is also the usage measure: metered consumption
    weights cached input, uncached input and output the same way the price list
    does, so minimising the bill and minimising quota burn are one problem.
    """
    points = [pt for pt in sweep(lo, hi, steps, s, cal, p) if pt.feasible]
    if not points:
        return None
    best_i = min(range(len(points)), key=lambda i: points[i].cost)
    left = points[max(0, best_i - 1)].W
    right = points[min(len(points) - 1, best_i + 1)].W

    phi_ratio = (math.sqrt(5) - 1) / 2
    for _ in range(60):
        if right - left < 1000:
            break
        x1 = right - phi_ratio * (right - left)
        x2 = left + phi_ratio * (right - left)
        if evaluate(x1, s, cal, p).cost <= evaluate(x2, s, cal, p).cost:
            right = x2
        else:
            left = x1
    return evaluate((left + right) / 2, s, cal, p)


__all__ = [
    "Calibration",
    "Pricing",
    "Scenario",
    "CostPoint",
    "evaluate",
    "sweep",
    "optimal_window",
    "inflation",
    "history_span",
    "compaction_cost",
    "compaction_output",
    "input_token_price",
    "replace",
]
