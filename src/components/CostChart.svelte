<script lang="ts">
	import { onMount } from "svelte";
	import * as echarts from "echarts/core";
	import { LineChart } from "echarts/charts";
	import {
		GridComponent,
		TooltipComponent,
		MarkLineComponent,
		MarkPointComponent,
	} from "echarts/components";
	import { CanvasRenderer } from "echarts/renderers";
	import type { CostPoint } from "../lib/model";
	import { chartTokens } from "../lib/tokens";
	import { count, money, moneyAxis, ratio, tokens } from "../lib/format";

	echarts.use([
		LineChart,
		GridComponent,
		TooltipComponent,
		MarkLineComponent,
		MarkPointComponent,
		CanvasRenderer,
	]);

	interface Props {
		points: CostPoint[];
		selected: CostPoint;
		best: CostPoint | null;
		W0: number;
		from: number;
		to: number;
		mode: "light" | "dark";
		onselect: (W: number) => void;
	}

	let { points, selected, best, W0, from, to, mode, onselect }: Props = $props();

	let host: HTMLDivElement;
	let chart: echarts.ECharts | undefined = $state();

	onMount(() => {
		const instance = echarts.init(host, undefined, { renderer: "canvas" });
		chart = instance;

		const resize = new ResizeObserver(() => instance.resize());
		resize.observe(host);

		// Click or drag anywhere on the plot to move the inspected W.
		const zr = instance.getZr();
		let dragging = false;
		const pick = (event: { offsetX: number; offsetY: number }) => {
			const value = instance.convertFromPixel({ xAxisIndex: 0 }, [
				event.offsetX,
				event.offsetY,
			]);
			const W = Array.isArray(value) ? value[0] : value;
			if (typeof W === "number" && Number.isFinite(W)) onselect(W);
		};
		zr.on("mousedown", (e) => {
			dragging = true;
			pick(e);
		});
		zr.on("mousemove", (e) => {
			if (dragging) pick(e);
		});
		zr.on("mouseup", () => (dragging = false));
		zr.on("globalout", () => (dragging = false));

		return () => {
			resize.disconnect();
			instance.dispose();
			chart = undefined;
		};
	});

	const TICKS = [64_000, 128_000, 256_000, 512_000, 1_024_000];

	/**
	 * Left to itself ECharts rounds the axis minimum down to a multiple of its
	 * tick interval, which drags a $420–$2,900 curve to a $0 baseline and flattens
	 * the very minimum the chart exists to show. Pin the extent to the data
	 * instead, with a little air on each side.
	 */
	function verticalBounds(costs: number[]) {
		let lo = Infinity;
		let hi = -Infinity;
		for (const c of costs) {
			if (c < lo) lo = c;
			if (c > hi) hi = c;
		}
		if (!Number.isFinite(lo) || !Number.isFinite(hi)) return null;
		const pad = (hi - lo || Math.max(hi * 0.2, 1)) * 0.08;
		return { min: Math.max(0, lo - pad), max: hi + pad };
	}

	function option(): echarts.EChartsCoreOption {
		const t = chartTokens(mode);
		const usable = points.filter((p) => p.feasible && Number.isFinite(p.cost));
		const anchor = best ?? selected;
		const ticks = TICKS.filter((v) => v >= from && v <= to);
		const bounds = verticalBounds(usable.map((p) => p.cost));

		return {
			animationDurationUpdate: 160,
			grid: {
				left: 4,
				right: 20,
				top: 28,
				bottom: 4,
				outerBoundsMode: "same",
				outerBoundsContain: "all",
			},
			xAxis: {
				type: "log",
				logBase: 2,
				min: from,
				max: to,
				name: "Context window  W",
				nameLocation: "middle",
				nameGap: 30,
				nameTextStyle: { color: t.muted, fontSize: 11 },
				axisLine: { lineStyle: { color: t.axis, width: 1 } },
				axisTick: { show: false, customValues: ticks },
				splitLine: { show: true, lineStyle: { color: t.grid, width: 1, type: "solid" } },
				axisLabel: {
					color: t.muted,
					fontSize: 11,
					customValues: ticks,
					formatter: (v: number) => tokens(v),
				},
			},
			yAxis: {
				type: "value",
				scale: true,
				splitNumber: 5,
				...(bounds ?? {}),
				name: "C_task  (USD)",
				nameLocation: "end",
				nameGap: 12,
				nameTextStyle: { color: t.muted, fontSize: 11, align: "left" },
				axisLine: { show: false },
				axisTick: { show: false },
				splitLine: { show: true, lineStyle: { color: t.grid, width: 1, type: "solid" } },
				axisLabel: {
					color: t.muted,
					fontSize: 11,
					// The floor is a padded data bound, not a round tick — don't label it.
					showMinLabel: false,
					formatter: (v: number) => moneyAxis(v),
				},
			},
			tooltip: {
				trigger: "axis",
				axisPointer: {
					type: "line",
					snap: true,
					lineStyle: { color: t.axis, width: 1, type: "solid" },
				},
				backgroundColor: t.tooltipBg,
				borderColor: t.grid,
				borderWidth: 1,
				padding: [10, 12],
				textStyle: { color: t.primary, fontSize: 12 },
				extraCssText: "border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,.08);",
				formatter: (params: unknown) => {
					const list = Array.isArray(params) ? params : [params];
					const first = list[0] as { dataIndex?: number } | undefined;
					const p = usable[first?.dataIndex ?? 0];
					if (!p) return "";
					return [
						`<div style="color:${t.muted};font-size:11px;letter-spacing:.04em">W = ${tokens(p.W)}</div>`,
						`<div style="display:flex;align-items:center;gap:7px;margin:3px 0 6px">`,
						`<span style="width:12px;height:2px;border-radius:1px;background:${t.series1}"></span>`,
						`<span style="font-size:17px;font-weight:600">${money(p.cost)}</span>`,
						`</div>`,
						`<div style="color:${t.secondary};font-size:11px;font-variant-numeric:tabular-nums">`,
						`φ ${ratio(p.phi)} · N ${count(p.N)} · K ${count(p.compactions)}`,
						`</div>`,
						`<div style="color:${t.muted};font-size:11px;font-variant-numeric:tabular-nums">`,
						`mean context ${tokens(p.meanContext)}`,
						`</div>`,
					].join("");
				},
			},
			series: [
				{
					type: "line",
					name: "C_task",
					smooth: false,
					showSymbol: false,
					symbol: "circle",
					data: usable.map((p) => [p.W, p.cost]),
					lineStyle: { width: 2, color: t.series1, cap: "round", join: "round" },
					itemStyle: { color: t.series1 },
					emphasis: { disabled: true },
					markLine: {
						silent: true,
						symbol: "none",
						animation: false,
						data: [
							{
								xAxis: W0,
								lineStyle: { color: t.axis, width: 1, type: "solid" },
								label: {
									show: true,
									formatter: "W₀",
									position: "end",
									color: t.muted,
									fontSize: 11,
									distance: 4,
								},
							},
							{
								xAxis: selected.W,
								lineStyle: { color: t.series1, width: 1, type: "solid", opacity: 0.45 },
								label: { show: false },
							},
						],
					},
					markPoint: {
						animation: false,
						symbol: "circle",
						data: [
							{
								coord: [anchor.W, anchor.cost],
								symbolSize: 9,
								itemStyle: {
									color: t.series1,
									borderColor: t.surface,
									borderWidth: 2,
								},
								label: {
									show: true,
									position: "top",
									distance: 9,
									formatter: `${money(anchor.cost)}  @ ${tokens(anchor.W)}`,
									color: t.primary,
									fontSize: 11.5,
									fontWeight: 600,
								},
							},
							{
								coord: [selected.W, selected.cost],
								symbolSize: 11,
								itemStyle: {
									color: t.surface,
									borderColor: t.series1,
									borderWidth: 2.5,
								},
								label: { show: false },
							},
						],
					},
				},
			],
		};
	}

	$effect(() => {
		// Reads the reactive props so the option rebuilds whenever they move.
		void [points, selected, best, mode, from, to, W0];
		chart?.setOption(option());
	});
</script>

<div class="plot" bind:this={host} role="img" aria-label="C_task(W) cost curve"></div>

<style>
	.plot {
		width: 100%;
		height: clamp(280px, 42vh, 420px);
		cursor: crosshair;
		touch-action: pan-y;
	}
</style>
