import type { Calibration, Pricing, Scenario } from "./model";

/**
 * The visualiser accepts a calibration in its query string so a measurement made
 * elsewhere — the context-window-advisor skill reading local Codex sessions —
 * can be opened as a link. Every value is range-checked: a URL is untrusted
 * input, and a bad number here would render as a broken chart rather than an error.
 */
export interface ImportedParams {
	/** True when the URL carried at least one recognised parameter. */
	active: boolean;
	/** Free-form origin tag, e.g. "codex". */
	source: string | null;
	/** Names of the parameters that were applied. */
	applied: string[];
}

interface Bound {
	min: number;
	max: number;
}

const CALIBRATION_KEYS: Record<keyof Calibration, { param: string; bound: Bound }> = {
	W0: { param: "w0", bound: { min: 1_000, max: 100_000_000 } },
	B: { param: "b", bound: { min: 0, max: 10_000_000 } },
	rho: { param: "rho", bound: { min: 0, max: 1 } },
	omega: { param: "omega", bound: { min: 0, max: 1 } },
	theta: { param: "theta", bound: { min: 0.05, max: 1 } },
	Sc: { param: "sc", bound: { min: 0, max: 10_000_000 } },
	oBar: { param: "obar", bound: { min: 1, max: 1_000_000 } },
	dBar: { param: "dbar", bound: { min: 0, max: 1_000_000 } },
};

const SCENARIO_KEYS: Record<keyof Scenario, { param: string; bound: Bound }> = {
	Y: { param: "y", bound: { min: 1_000, max: 1_000_000_000 } },
	phi0: { param: "phi0", bound: { min: 0.1, max: 100 } },
	beta: { param: "beta", bound: { min: 0, max: 10 } },
};

const PRICING_KEYS: Partial<Record<keyof Pricing, { param: string; bound: Bound }>> = {
	pu: { param: "pu", bound: { min: 0, max: 10_000 } },
	pc: { param: "pc", bound: { min: 0, max: 10_000 } },
	pw: { param: "pw", bound: { min: 0, max: 10_000 } },
	po: { param: "po", bound: { min: 0, max: 10_000 } },
	tierThreshold: { param: "tier", bound: { min: 1_000, max: 100_000_000 } },
	cToolDirect: { param: "tool", bound: { min: 0, max: 1_000_000 } },
};

function read(params: URLSearchParams, key: string, bound: Bound): number | undefined {
	const raw = params.get(key);
	if (raw === null || raw.trim() === "") return undefined;
	const value = Number(raw);
	if (!Number.isFinite(value) || value < bound.min || value > bound.max) return undefined;
	return value;
}

/**
 * Apply any recognised query parameters onto the live state objects, and report
 * what was taken. Mutates in place because the callers are $state proxies.
 */
export function applyUrlParams(
	calibration: Calibration,
	scenario: Scenario,
	pricing: Pricing,
	view: { W: number; from: number; to: number },
	search: string = typeof location === "undefined" ? "" : location.search,
): ImportedParams {
	const params = new URLSearchParams(search);
	const applied: string[] = [];

	for (const [field, spec] of Object.entries(CALIBRATION_KEYS)) {
		const value = read(params, spec.param, spec.bound);
		if (value === undefined) continue;
		calibration[field as keyof Calibration] = value;
		applied.push(spec.param);
	}
	for (const [field, spec] of Object.entries(SCENARIO_KEYS)) {
		const value = read(params, spec.param, spec.bound);
		if (value === undefined) continue;
		scenario[field as keyof Scenario] = value;
		applied.push(spec.param);
	}
	for (const [field, spec] of Object.entries(PRICING_KEYS)) {
		if (!spec) continue;
		const value = read(params, spec.param, spec.bound);
		if (value === undefined) continue;
		pricing[field as keyof Pricing] = value as never;
		applied.push(spec.param);
	}

	// The inspected window, and a sweep range wide enough to contain it.
	const W = read(params, "w", { min: 1_000, max: 100_000_000 });
	if (W !== undefined) {
		view.W = W;
		applied.push("w");
	}
	const from = read(params, "from", { min: 1_000, max: 100_000_000 });
	const to = read(params, "to", { min: 1_000, max: 100_000_000 });
	if (from !== undefined && to !== undefined && to > from) {
		view.from = from;
		view.to = to;
		applied.push("from", "to");
	}

	// A window outside the sweep would leave the marker off-chart.
	if (view.W < view.from) view.from = Math.max(1_000, view.W * 0.5);
	if (view.W > view.to) view.to = view.W * 1.5;

	return {
		active: applied.length > 0,
		source: params.get("src"),
		applied,
	};
}
