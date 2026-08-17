import {
	DEFAULT_CALIBRATION,
	DEFAULT_PRICING,
	DEFAULT_SCENARIO,
	type Calibration,
	type Pricing,
	type Scenario,
} from "./model";
import { applyUrlParams } from "./params";

export const scenario: Scenario = $state({ ...DEFAULT_SCENARIO });
export const calibration: Calibration = $state({ ...DEFAULT_CALIBRATION });
export const pricing: Pricing = $state({ ...DEFAULT_PRICING });

export const view = $state({
	/** The context-window limit under inspection. */
	W: 256_000,
	/** Sweep domain. */
	from: 48_000,
	to: 1_024_000,
	steps: 220,
	/** Table view of the curve, the tooltip-free way to read every value. */
	table: false,
});

/** A calibration handed over in the query string, if there was one. */
export const imported = $state(applyUrlParams(calibration, scenario, pricing, view));

export function resetAll() {
	Object.assign(scenario, DEFAULT_SCENARIO);
	Object.assign(calibration, DEFAULT_CALIBRATION);
	Object.assign(pricing, DEFAULT_PRICING);
	view.W = 256_000;
	view.from = 48_000;
	view.to = 1_024_000;
	imported.active = false;
}

export interface Preset {
	id: string;
	label: string;
	hint: string;
	scenario: Scenario;
}

/**
 * How much pre-existing information the task needs held at once — the quantity
 * beta encodes. Illustrative values, not calibrated strata: beta still needs a
 * controlled experiment (same task set, several W, each run to success).
 */
export const PRESETS: Preset[] = [
	{
		id: "small",
		label: "Small",
		hint: "Needs little existing information to make progress — a local fix, a single file",
		scenario: { Y: 1_000_000, phi0: 1.8, beta: 0.15 },
	},
	{
		id: "medium",
		label: "Medium",
		hint: "Needs a moderate body of existing information resident at once",
		scenario: { Y: 1_000_000, phi0: 1.8, beta: 0.45 },
	},
	{
		id: "large",
		label: "Large",
		hint: "Needs a lot held at once — a cross-cutting refactor, a large codebase",
		scenario: { Y: 1_000_000, phi0: 1.8, beta: 0.9 },
	},
];
