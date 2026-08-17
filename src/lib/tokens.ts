/**
 * Chart-facing colors, mirroring the CSS custom properties in app.css.
 * ECharts needs resolved hex, not var() references, so the two modes live here
 * and the chart rebuilds its option when the mode flips.
 */
export interface ChartTokens {
	surface: string;
	primary: string;
	secondary: string;
	muted: string;
	grid: string;
	axis: string;
	series1: string;
	series2: string;
	series3: string;
	tooltipBg: string;
}

const LIGHT: ChartTokens = {
	surface: "#fcfcfb",
	primary: "#0b0b0b",
	secondary: "#52514e",
	muted: "#898781",
	grid: "#e1e0d9",
	axis: "#c3c2b7",
	series1: "#2a78d6",
	series2: "#eb6834",
	series3: "#1baf7a",
	tooltipBg: "#ffffff",
};

const DARK: ChartTokens = {
	surface: "#1a1a19",
	primary: "#ffffff",
	secondary: "#c3c2b7",
	muted: "#898781",
	grid: "#2c2c2a",
	axis: "#383835",
	series1: "#3987e5",
	series2: "#d95926",
	series3: "#199e70",
	tooltipBg: "#232322",
};

export function chartTokens(mode: "light" | "dark"): ChartTokens {
	return mode === "dark" ? DARK : LIGHT;
}
