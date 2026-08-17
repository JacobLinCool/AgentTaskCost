const usd0 = new Intl.NumberFormat("en-US", {
	style: "currency",
	currency: "USD",
	maximumFractionDigits: 0,
});
const usd2 = new Intl.NumberFormat("en-US", {
	style: "currency",
	currency: "USD",
	minimumFractionDigits: 2,
	maximumFractionDigits: 2,
});

/** Money, with the decimals dropped once they stop carrying information. */
export function money(v: number): string {
	if (!Number.isFinite(v)) return "—";
	return Math.abs(v) >= 1000 ? usd0.format(v) : usd2.format(v);
}

/** Money on an axis: round steps only, compacted past $10K. */
export function moneyAxis(v: number): string {
	if (!Number.isFinite(v)) return "—";
	const abs = Math.abs(v);
	if (abs >= 1e6) return "$" + trim(v / 1e6) + "M";
	if (abs >= 1e4) return "$" + trim(v / 1e3) + "K";
	return "$" + Math.round(v).toLocaleString("en-US");
}

/** Tokens as 24K / 198.4K / 2.4M — the units the model is written in. */
export function tokens(v: number): string {
	if (!Number.isFinite(v)) return "—";
	const abs = Math.abs(v);
	if (abs >= 1e9) return trim(v / 1e9) + "B";
	if (abs >= 1e6) return trim(v / 1e6) + "M";
	if (abs >= 1e3) return trim(v / 1e3) + "K";
	return trim(v);
}

/** Counts, grouped by thousands. */
export function count(v: number): string {
	if (!Number.isFinite(v)) return "—";
	return Math.round(v).toLocaleString("en-US");
}

export function ratio(v: number, digits = 2): string {
	if (!Number.isFinite(v)) return "—";
	return v.toFixed(digits);
}

export function percent(v: number): string {
	if (!Number.isFinite(v)) return "—";
	return (v * 100).toFixed(v < 0.1 ? 1 : 0) + "%";
}

/** Signed delta against a baseline, e.g. "+18%" / "−7%". */
export function signedPercent(v: number): string {
	if (!Number.isFinite(v)) return "—";
	const sign = v > 0 ? "+" : v < 0 ? "−" : "";
	return sign + (Math.abs(v) * 100).toFixed(Math.abs(v) < 0.1 ? 1 : 0) + "%";
}

function trim(v: number): string {
	const rounded = Math.abs(v) >= 100 ? Math.round(v) : Math.round(v * 10) / 10;
	return String(rounded);
}
