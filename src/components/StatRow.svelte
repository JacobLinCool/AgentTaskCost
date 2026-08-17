<script lang="ts">
	import Sparkline from "./Sparkline.svelte";

	interface Props {
		symbol: string;
		label: string;
		value: string;
		series: number[];
		index: number;
	}

	let { symbol, label, value, series, index }: Props = $props();
</script>

<div class="row">
	<div class="names">
		<span class="symbol">{symbol}</span>
		<span class="label">{label}</span>
	</div>
	<Sparkline values={series} {index} width={52} />
	<span class="value num">{value}</span>
</div>

<style>
	.row {
		display: grid;
		grid-template-columns: 1fr auto auto;
		align-items: center;
		gap: 10px;
		padding: 9px 0;
		border-top: 1px solid var(--border);
	}
	.names {
		display: flex;
		align-items: baseline;
		gap: 7px;
		min-width: 0;
	}
	.symbol {
		font-family: var(--mono);
		font-size: 0.75rem;
		color: var(--ink);
		white-space: nowrap;
	}
	.label {
		color: var(--ink-muted);
		font-size: 0.6875rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.value {
		min-width: 4rem;
		text-align: right;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--ink);
	}
</style>
