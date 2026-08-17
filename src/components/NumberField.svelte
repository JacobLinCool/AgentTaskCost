<script lang="ts">
	interface Props {
		symbol: string;
		label: string;
		value: number;
		min?: number;
		max?: number;
		step?: number;
		unit?: string;
		note?: string;
	}

	let { symbol, label, value = $bindable(), min, max, step = 1, unit, note }: Props = $props();

	const id = $props.id();
</script>

<div class="field">
	<label for={id}>
		<span class="symbol">{symbol}</span>
		<span class="label">{label}</span>
	</label>
	<div class="input">
		<input {id} type="number" bind:value {min} {max} {step} class="num" />
		{#if unit}<span class="unit">{unit}</span>{/if}
	</div>
	{#if note}<p class="note">{note}</p>{/if}
</div>

<style>
	.field {
		display: flex;
		flex-direction: column;
		gap: 5px;
		min-width: 0;
	}
	label {
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
	.input {
		display: flex;
		align-items: center;
		gap: 6px;
		background: var(--surface-sunken);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		padding: 0 8px;
	}
	.input:focus-within {
		border-color: var(--accent);
	}
	input {
		flex: 1;
		min-width: 0;
		border: 0;
		background: transparent;
		color: var(--ink);
		font: inherit;
		font-size: 0.8125rem;
		padding: 6px 0;
		outline: none;
	}
	.unit {
		color: var(--ink-muted);
		font-size: 0.6875rem;
		white-space: nowrap;
	}
	.note {
		color: var(--ink-muted);
		font-size: 0.625rem;
		line-height: 1.4;
	}
</style>
