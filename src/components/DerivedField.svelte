<script lang="ts">
	interface Props {
		symbol: string;
		label: string;
		value: string;
		note?: string;
	}

	let { symbol, label, value, note }: Props = $props();
</script>

<div class="field">
	<div class="head">
		<span class="symbol">{symbol}</span>
		<span class="label">{label}</span>
	</div>
	<output class="box num">{value}</output>
	{#if note}<p class="note">{note}</p>{/if}
</div>

<style>
	.field {
		display: flex;
		flex-direction: column;
		gap: 5px;
		min-width: 0;
	}
	.head {
		display: flex;
		align-items: baseline;
		gap: 6px;
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
	/* No fill and no caret: this one is read out of the model, not typed in. */
	.box {
		display: block;
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		padding: 6px 8px;
		font-size: 0.8125rem;
		color: var(--ink-secondary);
	}
	.note {
		color: var(--ink-muted);
		font-size: 0.625rem;
		line-height: 1.4;
	}
</style>
