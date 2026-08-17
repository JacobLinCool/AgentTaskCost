<script lang="ts">
	import { money, percent } from "../lib/format";

	interface Segment {
		label: string;
		value: number;
		color: string;
	}

	interface Props {
		segments: Segment[];
	}

	let { segments }: Props = $props();

	const shown = $derived(segments.filter((s) => Number.isFinite(s.value) && s.value > 0));
	const total = $derived(shown.reduce((sum, s) => sum + s.value, 0));
</script>

{#if total > 0}
	<div class="composition">
		<div class="bar" role="presentation">
			{#each shown as segment (segment.label)}
				<span
					class="segment"
					style:flex-grow={segment.value / total}
					style:background={segment.color}
				></span>
			{/each}
		</div>
		<ul class="legend">
			{#each shown as segment (segment.label)}
				<li>
					<span class="key" style:background={segment.color}></span>
					<span class="name">{segment.label}</span>
					<span class="share num">{percent(segment.value / total)}</span>
					<span class="amount num">{money(segment.value)}</span>
				</li>
			{/each}
		</ul>
	</div>
{/if}

<style>
	.composition {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.bar {
		display: flex;
		/* 2px of surface doing the separating — no borders on the marks. */
		gap: 2px;
		height: 8px;
		border-radius: 4px;
		overflow: hidden;
	}
	.segment {
		min-width: 2px;
		border-radius: 1px;
	}
	.segment:first-child {
		border-radius: 4px 1px 1px 4px;
	}
	.segment:last-child {
		border-radius: 1px 4px 4px 1px;
	}
	.legend {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	li {
		display: grid;
		grid-template-columns: 12px 1fr auto auto;
		align-items: center;
		gap: 8px;
		font-size: 0.6875rem;
	}
	.key {
		height: 2px;
		border-radius: 1px;
	}
	.name {
		color: var(--ink-secondary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.share {
		color: var(--ink-muted);
		min-width: 2.5rem;
		text-align: right;
	}
	.amount {
		color: var(--ink);
		font-weight: 600;
		min-width: 3.75rem;
		text-align: right;
	}
</style>
