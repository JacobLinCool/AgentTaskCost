<script lang="ts">
	import type { Snippet } from "svelte";
	import ChevronDown from "@lucide/svelte/icons/chevron-down";

	interface Props {
		title: string;
		summary: string;
		open?: boolean;
		children: Snippet;
	}

	let { title, summary, open = false, children }: Props = $props();
</script>

<details class="card" {open}>
	<summary>
		<span class="title">{title}</span>
		<span class="summary">{summary}</span>
		<ChevronDown class="chevron" size={15} strokeWidth={1.75} />
	</summary>
	<div class="body">
		{@render children()}
	</div>
</details>

<style>
	details {
		overflow: hidden;
	}
	summary {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 12px 16px;
		cursor: pointer;
		list-style: none;
		user-select: none;
	}
	summary::-webkit-details-marker {
		display: none;
	}
	.title {
		font-size: 0.8125rem;
		font-weight: 600;
	}
	.summary {
		flex: 1;
		min-width: 0;
		color: var(--ink-muted);
		font-size: 0.6875rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	summary :global(.chevron) {
		color: var(--ink-muted);
		flex-shrink: 0;
		transition: transform 0.15s ease;
	}
	details[open] summary :global(.chevron) {
		transform: rotate(180deg);
	}
	.body {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
		gap: 14px 16px;
		padding: 4px 16px 18px;
		border-top: 1px solid var(--border);
		padding-top: 16px;
	}
</style>
