<script lang="ts">
	import ChartLine from "@lucide/svelte/icons/chart-line";
	import TableIcon from "@lucide/svelte/icons/table";
	import RotateCcw from "@lucide/svelte/icons/rotate-ccw";
	import ExternalLink from "@lucide/svelte/icons/external-link";
	import Copy from "@lucide/svelte/icons/copy";
	import Check from "@lucide/svelte/icons/check";

	import CostChart from "./components/CostChart.svelte";
	import CurveTable from "./components/CurveTable.svelte";
	import CompositionBar from "./components/CompositionBar.svelte";
	import StatRow from "./components/StatRow.svelte";
	import Slider from "./components/Slider.svelte";
	import NumberField from "./components/NumberField.svelte";
	import DerivedField from "./components/DerivedField.svelte";
	import ParamGroup from "./components/ParamGroup.svelte";
	import Explainer from "./components/Explainer.svelte";
	import ThemeToggle from "./components/ThemeToggle.svelte";

	import {
		cheapest,
		compactionCost,
		compactionOutput,
		evaluate,
		historySpan,
		sweep,
	} from "./lib/model";
	import {
		calibration,
		imported,
		pricing,
		PRESETS,
		resetAll,
		scenario,
		view,
	} from "./lib/state.svelte";
	import { theme } from "./lib/theme.svelte";
	import { count, money, ratio, signedPercent, tokens } from "./lib/format";

	const REPO = "https://github.com/JacobLinCool/AgentTaskCost";
	const INSTALL = "npx skills add JacobLinCool/AgentTaskCost";

	const points = $derived(
		sweep(view.from, view.to, view.steps, scenario, calibration, pricing),
	);
	const best = $derived(cheapest(points));
	const selected = $derived(evaluate(view.W, scenario, calibration, pricing));

	const index = $derived.by(() => {
		let bestIndex = 0;
		let bestGap = Infinity;
		for (let i = 0; i < points.length; i++) {
			const gap = Math.abs(Math.log(points[i]!.W / view.W));
			if (gap < bestGap) {
				bestGap = gap;
				bestIndex = i;
			}
		}
		return bestIndex;
	});

	const series = $derived({
		phi: points.map((p) => p.phi),
		output: points.map((p) => p.O),
		calls: points.map((p) => p.N),
		input: points.map((p) => p.inputTokens),
		compactions: points.map((p) => p.compactions),
	});

	const versusBest = $derived(
		best && best.cost > 0 ? selected.cost / best.cost - 1 : Number.NaN,
	);
	const atOptimum = $derived(Number.isFinite(versusBest) && versusBest < 0.005);

	const H0 = $derived(historySpan(calibration.W0, calibration));
	const perCompaction = $derived(compactionCost(view.W, calibration, pricing));
	const summaryTokens = $derived(compactionOutput(calibration));

	function select(W: number) {
		view.W = Math.min(view.to, Math.max(view.from, Math.round(W / 1000) * 1000));
	}

	function loadExample(next: typeof scenario, W: number) {
		Object.assign(scenario, next);
		select(W);
		const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
		document
			.getElementById("curve")
			?.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "center" });
	}

	let copied = $state(false);
	let copyTimer: ReturnType<typeof setTimeout> | undefined;

	async function copyInstall() {
		try {
			await navigator.clipboard.writeText(INSTALL);
			copied = true;
			clearTimeout(copyTimer);
			copyTimer = setTimeout(() => (copied = false), 1600);
		} catch {
			// Clipboard access can be denied; the command is selectable either way.
		}
	}

	const activePreset = $derived(
		PRESETS.find(
			(p) =>
				p.scenario.Y === scenario.Y &&
				p.scenario.phi0 === scenario.phi0 &&
				p.scenario.beta === scenario.beta,
		)?.id,
	);
</script>

<div class="shell">
	<header>
		<div class="identity">
			<h1>Agent Task Cost</h1>
			<p class="tagline">
				How the context window <code>W</code> decides what it costs an agent to finish a
				fixed task
			</p>
		</div>
		<div class="actions">
			<ThemeToggle />
			<a class="repo" href="{REPO}/blob/main/docs/cost-model.md" target="_blank" rel="noreferrer noopener">
				<span>The model</span>
				<ExternalLink size={13} strokeWidth={1.75} />
			</a>
		</div>
	</header>

	{#if imported.active}
		<p class="imported">
			<span class="dot"></span>
			Showing {imported.applied.length} calibration values from the URL{imported.source ===
			"codex"
				? ", measured from your own Codex sessions"
				: ""}. Reset returns to the defaults.
		</p>
	{/if}

	<section class="card scenario" aria-label="Scenario">
		<div class="presets" role="group" aria-label="How much information the task needs at once">
			<span class="presets-label">Task size</span>
			{#each PRESETS as preset (preset.id)}
				<button
					type="button"
					title={preset.hint}
					aria-pressed={activePreset === preset.id}
					onclick={() => Object.assign(scenario, preset.scenario)}
				>
					{preset.label}
				</button>
			{/each}
		</div>
		<div class="knobs">
			<Slider
				symbol="Y"
				label="effective output the task needs"
				bind:value={scenario.Y}
				min={100_000}
				max={20_000_000}
				log
				snap={(v) => Math.round(v / 50_000) * 50_000}
				format={tokens}
			/>
			<Slider
				symbol="φ₀"
				label="overhead of finding information"
				bind:value={scenario.phi0}
				min={1}
				max={5}
				step={0.05}
				format={(v) => ratio(v)}
			/>
			<Slider
				symbol="β"
				label="information the task holds at once"
				bind:value={scenario.beta}
				min={0}
				max={1.5}
				step={0.01}
				format={(v) => ratio(v)}
			/>
		</div>
		<button class="reset" type="button" onclick={resetAll} title="Back to defaults">
			<RotateCcw size={13} strokeWidth={1.75} />
			<span>Reset</span>
		</button>
	</section>

	<div class="layout">
		<aside class="rail">
			<section class="card readout" aria-label="Cost at the selected window">
				<p class="eyebrow">C_task &nbsp;@&nbsp; W = {tokens(selected.W)}</p>
				<p class="hero">{money(selected.cost)}</p>
				{#if best}
					<p class="delta" class:optimal={atOptimum}>
						{#if atOptimum}
							Cheapest window in the swept range
						{:else}
							<strong class="num">{signedPercent(versusBest)}</strong> vs the cheapest
							<span class="muted">({money(best.cost)} @ {tokens(best.W)})</span>
						{/if}
					</p>
				{/if}
				<CompositionBar
					segments={[
						{
							label: "context re-read each call",
							value: selected.inputCost,
							color: "var(--series-1)",
						},
						{ label: "billed output", value: selected.outputCost, color: "var(--series-2)" },
						{ label: "compaction", value: selected.compactionCost, color: "var(--series-3)" },
						{ label: "direct tool fees", value: selected.toolCost, color: "var(--series-4)" },
					]}
				/>
			</section>

			<section class="card diagnostics" aria-label="Diagnostics">
				<p class="eyebrow">Diagnostics</p>
				<p class="note">These explain why the cost moved. None of them is a second output.</p>
				<StatRow
					symbol="φ(W)"
					label="inflation"
					value={ratio(selected.phi)}
					series={series.phi}
					{index}
				/>
				<StatRow
					symbol="O(W)"
					label="billed output"
					value={tokens(selected.O)}
					series={series.output}
					{index}
				/>
				<StatRow
					symbol="N(W)"
					label="model calls"
					value={count(selected.N)}
					series={series.calls}
					{index}
				/>
				<StatRow
					symbol="ΣSₜ"
					label="repeated input"
					value={tokens(selected.inputTokens)}
					series={series.input}
					{index}
				/>
				<StatRow
					symbol="K(W)"
					label="compactions"
					value={count(selected.compactions)}
					series={series.compactions}
					{index}
				/>
			</section>
		</aside>

		<section class="card plot" id="curve" aria-label="Cost curve">
			<div class="plot-head">
				<div>
					<h2>Cost of finishing one fixed task</h2>
					<p class="note">
						{#if view.table}
							Sampled across the swept range; the cheapest row is marked.
						{:else}
							Click or drag the curve to move the inspection point.
						{/if}
						Y = {tokens(scenario.Y)}, calibration held fixed.
					</p>
				</div>
				<div class="viewswitch" role="group" aria-label="View as">
					<button
						type="button"
						aria-pressed={!view.table}
						onclick={() => (view.table = false)}
					>
						<ChartLine size={13} strokeWidth={1.75} />
						<span>Chart</span>
					</button>
					<button type="button" aria-pressed={view.table} onclick={() => (view.table = true)}>
						<TableIcon size={13} strokeWidth={1.75} />
						<span>Table</span>
					</button>
				</div>
			</div>

			{#if view.table}
				<CurveTable {points} {selected} {best} />
			{:else}
				<CostChart
					{points}
					{selected}
					{best}
					W0={calibration.W0}
					from={view.from}
					to={view.to}
					mode={theme.mode}
					onselect={select}
				/>
			{/if}

			<div class="scrub">
				<Slider
					symbol="W"
					label="context-window limit under inspection"
					bind:value={view.W}
					min={view.from}
					max={view.to}
					log
					snap={(v) => Math.round(v / 1000) * 1000}
					format={tokens}
				/>
			</div>
		</section>
	</div>

	<section class="params" aria-label="Calibration and pricing">
		<ParamGroup
			title="Session calibration"
			summary="H₀ = {tokens(H0)}  ·  compaction fires at θW and leaves S_c"
		>
			<NumberField
				symbol="W₀"
				label="reference window"
				bind:value={calibration.W0}
				min={1000}
				step={1000}
				unit="tokens"
			/>
			<NumberField
				symbol="B"
				label="first request context"
				bind:value={calibration.B}
				min={0}
				step={1000}
				unit="tokens"
				note="fixed prefix; compaction does not rewrite it"
			/>
			<NumberField
				symbol="θ"
				label="fraction of W that fires compaction"
				bind:value={calibration.theta}
				min={0.1}
				max={1}
				step={0.01}
			/>
			<NumberField
				symbol="S_c"
				label="context left after compaction"
				bind:value={calibration.Sc}
				min={0}
				step={1000}
				unit="tokens"
			/>
			<NumberField
				symbol="ρ"
				label="cached-read share"
				bind:value={calibration.rho}
				min={0}
				max={1}
				step={0.005}
			/>
			<NumberField
				symbol="ω"
				label="cache-write share"
				bind:value={calibration.omega}
				min={0}
				max={1}
				step={0.005}
			/>
			<NumberField
				symbol="ō"
				label="billed output per call"
				bind:value={calibration.oBar}
				min={1}
				step={10}
				unit="tokens"
				note="provisional"
			/>
			<NumberField
				symbol="d̄"
				label="context growth per call"
				bind:value={calibration.dBar}
				min={0}
				step={100}
				unit="tokens"
				note="uncalibrated"
			/>
		</ParamGroup>

		<ParamGroup title="Pricing" summary="USD / 1M tokens  ·  a request over the tier threshold is surcharged in full">
			<NumberField symbol="p_u" label="uncached input" bind:value={pricing.pu} min={0} step={0.25} unit="$/1M" />
			<NumberField symbol="p_c" label="cached input" bind:value={pricing.pc} min={0} step={0.05} unit="$/1M" />
			<NumberField symbol="p_w" label="cache write" bind:value={pricing.pw} min={0} step={0.25} unit="$/1M" />
			<NumberField symbol="p_o" label="output" bind:value={pricing.po} min={0} step={1} unit="$/1M" />
			<NumberField
				symbol="tier"
				label="long-context threshold"
				bind:value={pricing.tierThreshold}
				min={1000}
				step={1000}
				unit="tokens"
			/>
			<NumberField symbol="ℓ_I" label="input multiplier over threshold" bind:value={pricing.tierInputMult} min={1} step={0.1} />
			<NumberField symbol="ℓ_O" label="output multiplier over threshold" bind:value={pricing.tierOutputMult} min={1} step={0.1} />
			<DerivedField
				symbol="c_comp"
				label="per compaction"
				value="{money(perCompaction)} @ W = {tokens(selected.W)}"
				note="derived: reads θW, writes a summary of S_c − B = {tokens(summaryTokens)}"
			/>
			<NumberField
				symbol="C_tool"
				label="direct tool fees"
				bind:value={pricing.cToolDirect}
				min={0}
				step={0.5}
				unit="USD"
			/>
		</ParamGroup>
	</section>

	<Explainer {selected} onpick={loadExample} />

	<section class="card skill" aria-label="Calibrate from your own usage">
		<div class="skill-copy">
			<p class="eyebrow">Tune this to your own work</p>
			<h2>Stop guessing at the defaults</h2>
			<p>
				Every number on this page is a stand-in until it is measured. The
				<strong>context-window advisor</strong> skill reads your local Codex session history,
				measures these parameters from what your agent actually did, and works out which
				context window your own work wants — for small, medium and large tasks separately.
				It opens this page pre-loaded with your calibration, and can write the setting into
				<code>config.toml</code> for you.
			</p>
			<p class="note">
				Runs entirely on your machine, nothing is uploaded.
			</p>
		</div>
		<div class="skill-install">
			<div class="command">
				<code>{INSTALL}</code>
				<button type="button" onclick={copyInstall} aria-label="Copy install command">
					{#if copied}
						<Check size={14} strokeWidth={2} />
					{:else}
						<Copy size={14} strokeWidth={1.75} />
					{/if}
				</button>
			</div>
			<p class="note">
				Then ask your agent: <em>“what context window should I be using?”</em>
			</p>
		</div>
	</section>

	<footer>
		<p>
			Defaults are calibrated from the author's own Codex session history and experience.
		</p>
		<p>
			<a href="{REPO}/blob/main/docs/cost-model.md">The cost model</a> ·
			<a href="{REPO}/blob/main/docs/calibration.md">How calibration works</a> ·
			<a href={REPO}>Source</a>
		</p>
	</footer>
</div>

<style>
	.shell {
		max-width: 1240px;
		margin: 0 auto;
		padding: clamp(20px, 4vw, 40px) clamp(16px, 4vw, 32px) 64px;
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 20px;
		flex-wrap: wrap;
		padding-bottom: 4px;
	}
	h1 {
		font-size: 1.0625rem;
		font-weight: 600;
		letter-spacing: -0.01em;
	}
	.tagline {
		color: var(--ink-muted);
		font-size: 0.75rem;
		margin-top: 2px;
	}
	code {
		font-family: var(--mono);
		font-size: 0.9em;
		color: var(--ink-secondary);
	}
	.actions {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.repo {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		padding: 4px 10px;
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		color: var(--ink-secondary);
		font-size: 0.75rem;
		text-decoration: none;
	}
	.repo:hover {
		color: var(--ink);
		border-color: var(--border-strong);
	}

	.imported {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 8px 14px;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		background: var(--accent-wash);
		color: var(--ink-secondary);
		font-size: 0.75rem;
	}
	.imported .dot {
		width: 6px;
		height: 6px;
		flex-shrink: 0;
		border-radius: 50%;
		background: var(--accent);
	}

	.scenario {
		display: flex;
		align-items: flex-end;
		gap: clamp(16px, 3vw, 32px);
		flex-wrap: wrap;
		padding: 14px 16px;
	}
	.presets {
		display: inline-flex;
		align-items: center;
		gap: 2px;
		padding: 2px;
		background: var(--surface-sunken);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		margin-bottom: 2px;
	}
	.presets-label {
		color: var(--ink-muted);
		font-size: 0.6875rem;
		padding: 0 8px 0 7px;
		white-space: nowrap;
	}
	.presets button {
		border: 0;
		border-radius: 4px;
		background: transparent;
		color: var(--ink-muted);
		font-size: 0.75rem;
		padding: 5px 11px;
		cursor: pointer;
		white-space: nowrap;
	}
	.presets button:hover {
		color: var(--ink);
	}
	.presets button[aria-pressed="true"] {
		background: var(--surface);
		color: var(--ink);
		box-shadow: 0 0 0 1px var(--border);
	}
	.knobs {
		flex: 1;
		min-width: 260px;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
		gap: 10px 24px;
	}
	.reset {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		background: transparent;
		color: var(--ink-muted);
		font-size: 0.75rem;
		padding: 5px 10px;
		cursor: pointer;
		margin-bottom: 2px;
	}
	.reset:hover {
		color: var(--ink);
		border-color: var(--border-strong);
	}

	.layout {
		display: grid;
		grid-template-columns: minmax(0, 330px) minmax(0, 1fr);
		gap: 16px;
		align-items: start;
	}
	.rail {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.readout {
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.hero {
		font-size: clamp(2.5rem, 5.5vw, 3.25rem);
		font-weight: 600;
		line-height: 1.05;
		letter-spacing: -0.02em;
		margin: 2px 0 0;
	}
	.delta {
		color: var(--ink-secondary);
		font-size: 0.75rem;
		margin-bottom: 12px;
	}
	.delta.optimal {
		color: var(--success-text);
	}
	.delta .muted {
		color: var(--ink-muted);
	}

	.diagnostics {
		padding: 16px;
	}
	.note {
		color: var(--ink-muted);
		font-size: 0.6875rem;
		line-height: 1.5;
	}
	.diagnostics .note {
		margin: 2px 0 6px;
	}

	.plot {
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 12px;
		min-width: 0;
	}
	.plot-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 16px;
		flex-wrap: wrap;
	}
	h2 {
		font-size: 0.875rem;
		font-weight: 600;
	}
	.viewswitch {
		display: inline-flex;
		gap: 2px;
		padding: 2px;
		background: var(--surface-sunken);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
	}
	.viewswitch button {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		border: 0;
		border-radius: 4px;
		background: transparent;
		color: var(--ink-muted);
		font-size: 0.75rem;
		padding: 4px 10px;
		cursor: pointer;
	}
	.viewswitch button:hover {
		color: var(--ink);
	}
	.viewswitch button[aria-pressed="true"] {
		background: var(--surface);
		color: var(--ink);
		box-shadow: 0 0 0 1px var(--border);
	}
	.scrub {
		border-top: 1px solid var(--border);
		padding-top: 12px;
	}

	.skill {
		display: grid;
		grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr);
		gap: clamp(20px, 4vw, 40px);
		align-items: center;
		padding: clamp(18px, 3vw, 26px);
	}
	.skill h2 {
		font-size: 1.0625rem;
		margin: 4px 0 8px;
		letter-spacing: -0.01em;
	}
	.skill p {
		color: var(--ink-secondary);
		font-size: 0.8125rem;
		line-height: 1.65;
		max-width: 60ch;
	}
	.skill .note {
		margin-top: 8px;
	}
	.skill code {
		font-family: var(--mono);
		font-size: 0.9em;
	}
	.command {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 10px 12px;
		background: var(--surface-sunken);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
	}
	.command code {
		flex: 1;
		min-width: 0;
		font-size: 0.8125rem;
		color: var(--ink);
		overflow-x: auto;
		white-space: nowrap;
	}
	.command button {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		width: 26px;
		height: 26px;
		border: 0;
		border-radius: 4px;
		background: transparent;
		color: var(--ink-muted);
		cursor: pointer;
	}
	.command button:hover {
		color: var(--ink);
		background: var(--surface);
	}
	.skill-install .note {
		margin-top: 10px;
	}

	.params {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
		gap: 16px;
	}

	footer p {
		color: var(--ink-muted);
		font-size: 0.6875rem;
		line-height: 1.6;
		max-width: 62ch;
	}

	@media (max-width: 900px) {
		.layout,
		.skill {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
