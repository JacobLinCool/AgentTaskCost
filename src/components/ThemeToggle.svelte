<script lang="ts">
	import Sun from "@lucide/svelte/icons/sun";
	import Moon from "@lucide/svelte/icons/moon";
	import Monitor from "@lucide/svelte/icons/monitor";
	import { theme, type ThemePreference } from "../lib/theme.svelte";

	const options: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
		{ value: "light", label: "Light", icon: Sun },
		{ value: "dark", label: "Dark", icon: Moon },
		{ value: "system", label: "System", icon: Monitor },
	];
</script>

<div class="toggle" role="group" aria-label="Theme">
	{#each options as option (option.value)}
		{@const Icon = option.icon}
		<button
			type="button"
			title={option.label}
			aria-label={option.label}
			aria-pressed={theme.preference === option.value}
			onclick={() => theme.set(option.value)}
		>
			<Icon size={14} strokeWidth={1.75} />
		</button>
	{/each}
</div>

<style>
	.toggle {
		display: inline-flex;
		gap: 2px;
		padding: 2px;
		background: var(--surface-sunken);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
	}
	button {
		display: grid;
		place-items: center;
		width: 26px;
		height: 24px;
		border: 0;
		border-radius: 4px;
		background: transparent;
		color: var(--ink-muted);
		cursor: pointer;
		transition: color 0.12s ease, background 0.12s ease;
	}
	button:hover {
		color: var(--ink);
	}
	button[aria-pressed="true"] {
		background: var(--surface);
		color: var(--ink);
		box-shadow: 0 0 0 1px var(--border);
	}
</style>
