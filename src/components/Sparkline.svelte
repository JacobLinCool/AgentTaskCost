<script lang="ts">
	interface Props {
		values: number[];
		index: number;
		width?: number;
		height?: number;
	}

	let { values, index, width = 72, height = 20 }: Props = $props();

	const geometry = $derived.by(() => {
		const finite = values.filter((v) => Number.isFinite(v));
		if (finite.length < 2 || values.length < 2) return null;

		let lo = Infinity;
		let hi = -Infinity;
		for (const v of finite) {
			if (v < lo) lo = v;
			if (v > hi) hi = v;
		}
		const span = hi - lo || 1;
		const x = (i: number) => (i / (values.length - 1)) * width;
		const y = (v: number) => height - 1.5 - ((v - lo) / span) * (height - 3);

		let path = "";
		let pen = false;
		for (let i = 0; i < values.length; i++) {
			const v = values[i];
			if (v === undefined || !Number.isFinite(v)) {
				pen = false;
				continue;
			}
			path += `${pen ? "L" : "M"}${x(i).toFixed(2)} ${y(v).toFixed(2)} `;
			pen = true;
		}

		const current = values[index];
		const dot =
			current !== undefined && Number.isFinite(current)
				? { cx: x(index), cy: y(current) }
				: null;

		return { path, dot };
	});
</script>

{#if geometry}
	<svg
		class="spark"
		viewBox="0 0 {width} {height}"
		{width}
		{height}
		aria-hidden="true"
		preserveAspectRatio="none"
	>
		<path d={geometry.path} fill="none" vector-effect="non-scaling-stroke" />
		{#if geometry.dot}
			<circle class="dot" cx={geometry.dot.cx} cy={geometry.dot.cy} r="2.5" />
		{/if}
	</svg>
{/if}

<style>
	.spark {
		display: block;
		overflow: visible;
	}
	path {
		stroke: var(--ink-muted);
		stroke-width: 1.25;
		stroke-linejoin: round;
		stroke-linecap: round;
		opacity: 0.7;
	}
	.dot {
		fill: var(--accent);
		stroke: var(--surface);
		stroke-width: 1.5;
	}
</style>
