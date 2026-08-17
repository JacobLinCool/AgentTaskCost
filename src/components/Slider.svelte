<script lang="ts">
	interface Props {
		label: string;
		symbol?: string;
		hint?: string;
		value: number;
		min: number;
		max: number;
		step?: number;
		/** Map the track logarithmically — right for quantities read multiplicatively. */
		log?: boolean;
		/** Round the value coming off a logarithmic track. */
		snap?: (v: number) => number;
		format: (v: number) => string;
	}

	let {
		label,
		symbol,
		hint,
		value = $bindable(),
		min,
		max,
		step = 1,
		log = false,
		snap,
		format,
	}: Props = $props();

	const RESOLUTION = 1000;

	const position = $derived(
		log
			? (Math.log(Math.max(value, min) / min) / Math.log(max / min)) * RESOLUTION
			: value,
	);

	function commit(raw: number) {
		if (!log) {
			value = raw;
			return;
		}
		const mapped = min * Math.pow(max / min, raw / RESOLUTION);
		value = snap ? snap(mapped) : mapped;
	}
</script>

<div class="control">
	<div class="head">
		<label for="slider-{label}">
			{#if symbol}<span class="symbol">{symbol}</span>{/if}
			<span class="text">{label}</span>
		</label>
		<output class="num" for="slider-{label}">{format(value)}</output>
	</div>
	<input
		id="slider-{label}"
		type="range"
		min={log ? 0 : min}
		max={log ? RESOLUTION : max}
		step={log ? 1 : step}
		value={position}
		oninput={(e) => commit(e.currentTarget.valueAsNumber)}
	/>
	{#if hint}<p class="hint">{hint}</p>{/if}
</div>

<style>
	.control {
		display: flex;
		flex-direction: column;
		gap: 6px;
		min-width: 0;
	}
	.head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 10px;
	}
	label {
		display: flex;
		align-items: baseline;
		gap: 6px;
		min-width: 0;
		cursor: pointer;
	}
	.symbol {
		font-family: var(--mono);
		font-size: 0.75rem;
		color: var(--ink);
	}
	.text {
		color: var(--ink-muted);
		font-size: 0.6875rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	output {
		font-size: 0.8125rem;
		font-weight: 600;
		white-space: nowrap;
	}
	.hint {
		color: var(--ink-muted);
		font-size: 0.6875rem;
		line-height: 1.4;
	}

	input[type="range"] {
		-webkit-appearance: none;
		appearance: none;
		width: 100%;
		height: 20px;
		margin: 0;
		background: transparent;
		cursor: pointer;
	}
	input[type="range"]::-webkit-slider-runnable-track {
		height: 3px;
		border-radius: 2px;
		background: var(--border-strong);
	}
	input[type="range"]::-moz-range-track {
		height: 3px;
		border-radius: 2px;
		background: var(--border-strong);
	}
	input[type="range"]::-webkit-slider-thumb {
		-webkit-appearance: none;
		appearance: none;
		width: 14px;
		height: 14px;
		margin-top: -5.5px;
		border-radius: 50%;
		background: var(--accent);
		border: 2px solid var(--surface);
		box-shadow: 0 0 0 1px var(--border-strong);
	}
	input[type="range"]::-moz-range-thumb {
		width: 14px;
		height: 14px;
		border-radius: 50%;
		background: var(--accent);
		border: 2px solid var(--surface);
		box-shadow: 0 0 0 1px var(--border-strong);
	}
	input[type="range"]:focus-visible {
		outline-offset: 4px;
	}
</style>
