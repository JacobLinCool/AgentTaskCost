/**
 * Cost model from README.md.
 *
 *   Context window -> Output inflation -> Model calls -> Repeated context input -> Task cost
 *
 * The only dependent variable is C_task(W); everything else returned here is a
 * diagnostic that explains why the cost moves.
 */

/** Calibrated from historical sessions. */
export interface Calibration {
	/** W_0 — reference context window. */
	W0: number;
	/** B — context tokens on the first request. */
	B: number;
	/** rho — cached-read share of input. */
	rho: number;
	/** omega — cache-write share of input. */
	omega: number;
	/** theta — fraction of W at which compaction triggers. */
	theta: number;
	/** S_c — context left after a compaction. */
	Sc: number;
	/** o-bar — mean billed output tokens per model call. */
	oBar: number;
	/** d-bar — mean net history growth per model call. */
	dBar: number;
}

/** Model price parameters, USD per 1M tokens. */
export interface Pricing {
	/** p_u — uncached input. */
	pu: number;
	/** p_c — cached input read. */
	pc: number;
	/** p_w — cache write. */
	pw: number;
	/** p_o — output. */
	po: number;
	/** Context size above which the long-context tier applies. */
	tierThreshold: number;
	/** Input multiplier inside the long-context tier. */
	tierInputMult: number;
	/** Output multiplier inside the long-context tier. */
	tierOutputMult: number;
	/** C_tool,direct — USD of tool fees per task. */
	cToolDirect: number;
}

/** The scenario the user drives. */
export interface Scenario {
	/** Y — effective output the task requires. */
	Y: number;
	/** phi_0 — baseline output inflation at W_0. */
	phi0: number;
	/** beta — sensitivity of productivity to a small context. */
	beta: number;
}

export interface CostPoint {
	W: number;
	/** phi(W) — output inflation factor. */
	phi: number;
	/** O(W) — total billed output tokens. */
	O: number;
	/** N(W) — model calls. */
	N: number;
	/** K(W) — compactions. */
	compactions: number;
	/** Sum of S_t — total repeated context input read across the task. */
	inputTokens: number;
	/** Mean S_t. */
	meanContext: number;
	/** Share of model calls billed in the long-context tier. */
	tierShare: number;
	inputCost: number;
	outputCost: number;
	compactionCost: number;
	toolCost: number;
	/** C_task(W). */
	cost: number;
	/** False when W is below the compaction floor and the model is undefined. */
	feasible: boolean;
}

export const DEFAULT_CALIBRATION: Calibration = {
	W0: 256_000,
	B: 24_000,
	rho: 0.975,
	omega: 0,
	theta: 0.9,
	Sc: 32_000,
	oBar: 350,
	dBar: 1_500,
};

export const DEFAULT_PRICING: Pricing = {
	pu: 5,
	pc: 0.5,
	pw: 6.25,
	po: 30,
	tierThreshold: 272_000,
	tierInputMult: 2,
	tierOutputMult: 1.5,
	cToolDirect: 0,
};

export const DEFAULT_SCENARIO: Scenario = {
	Y: 1_000_000,
	phi0: 1.8,
	beta: 0.45,
};

/** H(W) = theta * W - S_c — history a compaction cycle can accumulate. */
export function historySpan(W: number, cal: Calibration): number {
	return cal.theta * W - cal.Sc;
}

/** The smallest W with a positive history span; below it the model is undefined. */
export function feasibleFloor(cal: Calibration): number {
	return cal.Sc / cal.theta;
}

/** p_u(1 - rho - omega) + p_c*rho + p_w*omega — the blended price of one input token. */
export function inputTokenPrice(cal: Calibration, p: Pricing): number {
	return p.pu * (1 - cal.rho - cal.omega) + p.pc * cal.rho + p.pw * cal.omega;
}

/**
 * Tokens a compaction actually generates.
 *
 * B is the fixed prefix — system instructions, tool definitions, the task prompt —
 * which compaction does not rewrite. Only the history is replaced, so the summary
 * it writes is what is left of S_c once that prefix is accounted for.
 */
export function compactionOutput(cal: Calibration): number {
	return Math.max(0, cal.Sc - cal.B);
}

/**
 * c_compact — the price of one compaction, derived rather than assumed.
 *
 * A compaction is itself a model call outside the N(W) task calls: it reads the
 * context that triggered it (about theta*W) and writes the summary that replaces
 * the history. Both sides carry the long-context multipliers when theta*W crosses
 * the tier. The read is priced with the same cached-read blend as any other call,
 * on the assumption that compaction keeps the conversation prefix cached.
 */
export function compactionCost(W: number, cal: Calibration, p: Pricing): number {
	const contextRead = cal.theta * W;
	const overTier = contextRead > p.tierThreshold;
	const inputMult = overTier ? p.tierInputMult : 1;
	const outputMult = overTier ? p.tierOutputMult : 1;
	return (
		(inputMult * inputTokenPrice(cal, p) * contextRead +
			outputMult * p.po * compactionOutput(cal)) /
		1e6
	);
}

/** phi(W) = phi_0 * max[1, (H_0 / H(W))^beta]. */
export function inflation(W: number, s: Scenario, cal: Calibration): number {
	const h = historySpan(W, cal);
	const h0 = historySpan(cal.W0, cal);
	if (h <= 0 || h0 <= 0) return Number.POSITIVE_INFINITY;
	return s.phi0 * Math.max(1, Math.pow(h0 / h, s.beta));
}

interface SegmentAggregate {
	/** Number of calls in the segment. */
	count: number;
	/** Sum of S_t over the segment. */
	sum: number;
	/** Number of calls whose S_t exceeds the long-context threshold. */
	aboveCount: number;
	/** Sum of S_t over those calls. */
	aboveSum: number;
}

const EMPTY: SegmentAggregate = { count: 0, sum: 0, aboveCount: 0, aboveSum: 0 };

/**
 * Between two compactions the context is an arithmetic sequence
 * S_0, S_0 + d, S_0 + 2d, ... so a whole segment aggregates in closed form —
 * no per-call loop, whatever the task size.
 */
function aggregate(S0: number, d: number, m: number, threshold: number): SegmentAggregate {
	if (m <= 0) return EMPTY;
	const sum = m * S0 + (d * m * (m - 1)) / 2;

	// Index of the first call that crosses into the long-context tier.
	let k0: number;
	if (d > 0) {
		k0 = Math.min(m, Math.max(0, Math.floor((threshold - S0) / d) + 1));
	} else {
		k0 = S0 > threshold ? 0 : m;
	}
	const aboveCount = m - k0;
	const indexSum = ((m - 1) * m) / 2 - ((k0 - 1) * k0) / 2;
	const aboveSum = aboveCount * S0 + d * indexSum;

	return { count: m, sum, aboveCount, aboveSum };
}

/** Calls from S0 until the one after which compaction fires (inclusive). */
function segmentLength(S0: number, d: number, thetaW: number): number {
	if (S0 + d >= thetaW) return 1;
	if (d <= 0) return Number.POSITIVE_INFINITY;
	return Math.max(1, Math.ceil((thetaW - d - S0) / d) + 1);
}

/** Evaluate C_task(W) and every diagnostic at a single context-window limit. */
export function evaluate(
	W: number,
	s: Scenario,
	cal: Calibration,
	p: Pricing,
): CostPoint {
	const thetaW = cal.theta * W;
	const phi = inflation(W, s, cal);

	if (!Number.isFinite(phi) || phi <= 0 || s.Y <= 0 || cal.oBar <= 0) {
		return {
			W,
			phi,
			O: Number.POSITIVE_INFINITY,
			N: Number.POSITIVE_INFINITY,
			compactions: Number.POSITIVE_INFINITY,
			inputTokens: Number.POSITIVE_INFINITY,
			meanContext: Number.NaN,
			tierShare: Number.NaN,
			inputCost: Number.POSITIVE_INFINITY,
			outputCost: Number.POSITIVE_INFINITY,
			compactionCost: Number.POSITIVE_INFINITY,
			toolCost: p.cToolDirect,
			cost: Number.POSITIVE_INFINITY,
			feasible: false,
		};
	}

	const O = s.Y * phi;
	const N = Math.max(1, Math.ceil(O / cal.oBar));
	const oPerCall = O / N;

	// The context walk: one opening segment from B, then identical cycles from S_c.
	const openLength = segmentLength(cal.B, cal.dBar, thetaW);
	const cycleLength = segmentLength(cal.Sc, cal.dBar, thetaW);

	const opening = Math.min(N, openLength);
	const rest = N - opening;
	const cycles = Number.isFinite(cycleLength) ? Math.floor(rest / cycleLength) : 0;
	const partial = Number.isFinite(cycleLength) ? rest - cycles * cycleLength : rest;

	const aOpen = aggregate(cal.B, cal.dBar, opening, p.tierThreshold);
	const aCycle = Number.isFinite(cycleLength)
		? aggregate(cal.Sc, cal.dBar, cycleLength, p.tierThreshold)
		: EMPTY;
	const aPartial = aggregate(cal.Sc, cal.dBar, partial, p.tierThreshold);

	const inputTokens = aOpen.sum + cycles * aCycle.sum + aPartial.sum;
	const tierTokens = aOpen.aboveSum + cycles * aCycle.aboveSum + aPartial.aboveSum;
	const tierCalls = aOpen.aboveCount + cycles * aCycle.aboveCount + aPartial.aboveCount;

	// K(W) counts compactions strictly before the last call, so a segment that
	// ends exactly on call N does not contribute one.
	const completedSegments = (opening === openLength ? 1 : 0) + cycles;
	const compactions = Math.max(0, partial > 0 ? completedSegments : completedSegments - 1);

	const inputMix = inputTokenPrice(cal, p);

	const inputCost =
		(inputMix * (inputTokens - tierTokens + p.tierInputMult * tierTokens)) / 1e6;
	const outputCost =
		(p.po * oPerCall * (N - tierCalls + p.tierOutputMult * tierCalls)) / 1e6;
	const compactionTotal = compactions * compactionCost(W, cal, p);
	const toolCost = p.cToolDirect;

	return {
		W,
		phi,
		O,
		N,
		compactions,
		inputTokens,
		meanContext: inputTokens / N,
		tierShare: tierCalls / N,
		inputCost,
		outputCost,
		compactionCost: compactionTotal,
		toolCost,
		cost: inputCost + outputCost + compactionTotal + toolCost,
		feasible: true,
	};
}

/** Evaluate C_task across a log-spaced sweep of W. */
export function sweep(
	from: number,
	to: number,
	steps: number,
	s: Scenario,
	cal: Calibration,
	p: Pricing,
): CostPoint[] {
	const lo = Math.log(from);
	const hi = Math.log(to);
	const points: CostPoint[] = [];
	for (let i = 0; i < steps; i++) {
		const W = Math.exp(lo + ((hi - lo) * i) / (steps - 1));
		points.push(evaluate(W, s, cal, p));
	}
	return points;
}

/** The cheapest point of a sweep, or null when nothing is feasible. */
export function cheapest(points: CostPoint[]): CostPoint | null {
	let best: CostPoint | null = null;
	for (const pt of points) {
		if (!pt.feasible) continue;
		if (best === null || pt.cost < best.cost) best = pt;
	}
	return best;
}
