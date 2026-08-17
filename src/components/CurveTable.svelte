<script lang="ts">
	import type { CostPoint } from "../lib/model";
	import { count, money, ratio, tokens } from "../lib/format";

	interface Props {
		points: CostPoint[];
		selected: CostPoint;
		best: CostPoint | null;
		rows?: number;
	}

	let { points, selected, best, rows = 18 }: Props = $props();

	// The tooltip is an enhancement; this table is the ungated way to read the curve.
	const sampled = $derived.by(() => {
		const usable = points.filter((p) => p.feasible);
		if (usable.length <= rows) return usable;
		const stride = (usable.length - 1) / (rows - 1);
		return Array.from({ length: rows }, (_, i) => usable[Math.round(i * stride)]!);
	});
</script>

<div class="wrap">
	<table>
		<caption class="visually-hidden">C_task(W) and its diagnostics</caption>
		<thead>
			<tr>
				<th scope="col">W</th>
				<th scope="col">φ(W)</th>
				<th scope="col">O(W)</th>
				<th scope="col">N(W)</th>
				<th scope="col">K(W)</th>
				<th scope="col">Σ S<sub>t</sub></th>
				<th scope="col">C_task</th>
			</tr>
		</thead>
		<tbody>
			{#each sampled as p (p.W)}
				<tr class:best={p === best} class:selected={p === selected}>
					<th scope="row" class="num">{tokens(p.W)}</th>
					<td class="num">{ratio(p.phi)}</td>
					<td class="num">{tokens(p.O)}</td>
					<td class="num">{count(p.N)}</td>
					<td class="num">{count(p.compactions)}</td>
					<td class="num">{tokens(p.inputTokens)}</td>
					<td class="num cost">{money(p.cost)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.wrap {
		overflow-x: auto;
		max-height: clamp(280px, 42vh, 420px);
		overflow-y: auto;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.75rem;
	}
	th,
	td {
		padding: 6px 10px;
		text-align: right;
		white-space: nowrap;
	}
	thead th {
		position: sticky;
		top: 0;
		background: var(--surface);
		color: var(--ink-muted);
		font-weight: 600;
		font-size: 0.6875rem;
		border-bottom: 1px solid var(--border);
	}
	tbody th {
		font-weight: 600;
		color: var(--ink);
	}
	tbody td {
		color: var(--ink-secondary);
	}
	tbody tr + tr th,
	tbody tr + tr td {
		border-top: 1px solid var(--border);
	}
	.cost {
		color: var(--ink);
		font-weight: 600;
	}
	tr.best td.cost,
	tr.best th {
		color: var(--accent);
	}
	tr.selected {
		background: var(--accent-wash);
	}
</style>
