<script lang="ts">
	import ArrowRight from "@lucide/svelte/icons/arrow-right";
	import ChartLine from "@lucide/svelte/icons/chart-line";

	import {
		cheapest,
		evaluate,
		historySpan,
		inputTokenPrice,
		sweep,
		type CostPoint,
		type Scenario,
	} from "../lib/model";
	import { calibration, pricing, scenario, view } from "../lib/state.svelte";
	import { count, money, percent, ratio, signedPercent, tokens } from "../lib/format";

	interface Props {
		/** The point the chart is currently inspecting. */
		selected: CostPoint;
		/** Load a worked example into the instrument above. */
		onpick: (s: Scenario, W: number) => void;
	}

	let { selected, onpick }: Props = $props();

	/** The cheapest window for a scenario, under the calibration in force right now. */
	function optimum(s: Scenario): CostPoint | null {
		return cheapest(sweep(view.from, view.to, 180, s, calibration, pricing));
	}

	function costAt(W: number, s: Scenario): number {
		return evaluate(W, s, calibration, pricing).cost;
	}

	// Each knob swept across its plausible range, with the other two left where the
	// user has them. Two of the three barely move the answer; that is the point.
	const yLow = $derived(optimum({ ...scenario, Y: 200_000 }));
	const yHigh = $derived(optimum({ ...scenario, Y: 5_000_000 }));
	const phiLow = $derived(optimum({ ...scenario, phi0: 1.2 }));
	const phiHigh = $derived(optimum({ ...scenario, phi0: 6 }));
	const betaLow = $derived(optimum({ ...scenario, beta: 0 }));
	const betaHigh = $derived(optimum({ ...scenario, beta: 1.2 }));

	const room = $derived([64_000, 128_000, 256_000].map((W) => ({ W, H: historySpan(W, calibration) })));

	/** What a cached read actually costs, against the sticker price of an uncached one. */
	const cacheShare = $derived(
		pricing.pu > 0 ? inputTokenPrice(calibration, pricing) / pricing.pu : Number.NaN,
	);

	const compactsSmall = $derived(evaluate(64_000, scenario, calibration, pricing));
	const compactsLarge = $derived(evaluate(256_000, scenario, calibration, pricing));

	const LOCAL: Scenario = { Y: 200_000, phi0: 1.6, beta: 0.15 };
	const SPRAWL: Scenario = { Y: 3_000_000, phi0: 2.4, beta: 0.9 };

	const localBest = $derived(optimum(LOCAL));
	const sprawlBest = $derived(optimum(SPRAWL));

	/** Each task run in the window the other one wants. */
	const localPenalty = $derived(
		localBest && sprawlBest ? costAt(sprawlBest.W, LOCAL) / localBest.cost - 1 : Number.NaN,
	);
	const sprawlPenalty = $derived(
		localBest && sprawlBest ? costAt(localBest.W, SPRAWL) / sprawlBest.cost - 1 : Number.NaN,
	);

	const chain = $derived([
		{ symbol: "W", value: tokens(selected.W), caption: "context window" },
		{ symbol: "φ(W)", value: ratio(selected.phi), caption: "output inflation" },
		{ symbol: "O(W)", value: tokens(selected.O), caption: "billed output" },
		{ symbol: "N(W)", value: count(selected.N), caption: "model calls" },
		{ symbol: "ΣSₜ", value: tokens(selected.inputTokens), caption: "context re-read" },
		{ symbol: "C_task", value: money(selected.cost), caption: "the bill" },
	]);
</script>

{#snippet moves(range: string, lo: CostPoint | null, hi: CostPoint | null)}
	<p class="moves">
		<span class="range">{range}</span>
		<span>
			bill
			<b class="num">×{lo && hi && lo.cost > 0 ? ratio(hi.cost / lo.cost, hi.cost / lo.cost >= 10 ? 0 : 1) : "—"}</b>
		</span>
		<span>
			cheapest window
			<b class="num">{lo ? tokens(lo.W) : "—"} → {hi ? tokens(hi.W) : "—"}</b>
		</span>
	</p>
{/snippet}

{#snippet example(title: string, body: string, s: Scenario, best: CostPoint | null, penalty: number, against: string)}
	<article class="card example">
		<h4>{title}</h4>
		<p>{body}</p>
		<p class="inputs">
			Y <b>{tokens(s.Y)}</b> · φ₀ <b>{ratio(s.phi0)}</b> · β <b>{ratio(s.beta)}</b>
		</p>
		<dl class="result">
			<dt>cheapest window</dt>
			<dd class="num">{best ? tokens(best.W) : "—"}</dd>
			<dt>cost there</dt>
			<dd class="num">{best ? money(best.cost) : "—"}</dd>
			<dt>run at {against}</dt>
			<dd class="num">{signedPercent(penalty)}</dd>
		</dl>
		<button type="button" onclick={() => best && onpick(s, best.W)}>
			<ChartLine size={13} strokeWidth={1.75} />
			<span>Put this task on the chart</span>
		</button>
	</article>
{/snippet}

<section class="explainer" aria-labelledby="explainer-title">
	<div class="intro">
		<h2 id="explainer-title">What the numbers mean</h2>
		<p class="lede">
			Everything on this page comes out of one formula, and that formula has exactly one
			output: what it costs to finish one fixed task. Inflation, model calls, compactions —
			none of them is a second answer. They are there to explain why the cost moved. Here is
			what each one is, in terms an engineer already has words for.
		</p>
	</div>

	<ol class="chain">
		{#each chain as node, i (node.symbol)}
			{#if i > 0}
				<li class="arrow" aria-hidden="true">
					<ArrowRight size={13} strokeWidth={1.5} />
				</li>
			{/if}
			<li class="node">
				<span class="sym">{node.symbol}</span>
				<span class="val num">{node.value}</span>
				<span class="cap">{node.caption}</span>
			</li>
		{/each}
	</ol>
	<p class="chain-note">
		Live, at the window the chart is inspecting. The window decides how much productivity you
		lose; that decides how much output the task takes; that decides how many calls it takes;
		that decides how much context gets re-read on every one of them — and that is the bill.
	</p>

	<div class="formula" role="figure" aria-label="The model, in five lines">
		<div class="lhs">H(W)</div>
		<div class="rhs">= θW − S<sub>c</sub></div>
		<div class="gloss">room for new history in one compaction cycle</div>

		<div class="lhs">φ(W)</div>
		<div class="rhs">= φ₀ · max[ 1, (H₀ / H(W))<sup>β</sup> ]</div>
		<div class="gloss">output inflation — billed ÷ effective</div>

		<div class="lhs">O(W)</div>
		<div class="rhs">= Y · φ(W)</div>
		<div class="gloss">billed output tokens</div>

		<div class="lhs">N(W)</div>
		<div class="rhs">= ⌈ O(W) / ō ⌉</div>
		<div class="gloss">model calls</div>

		<div class="lhs">C<sub>task</sub>(W)</div>
		<div class="rhs">= Σ<sub>t</sub> [ input(S<sub>t</sub>) + output(o<sub>t</sub>) ] + K(W)·c<sub>comp</sub> + C<sub>tool</sub></div>
		<div class="gloss">the only thing the model actually claims</div>
	</div>
	<p class="chain-note">
		Three of those symbols are yours to set — Y, φ₀ and β, the controls at the top. Everything
		else is calibration: measured from session history, or read off a price list. The input and
		output terms each carry a long-context multiplier whenever a single request crosses the tier
		threshold.
	</p>

	<div class="group">
		<h3>The three you set</h3>
		<dl class="glossary">
			<dt>
				<span class="symbol">Y</span>
				<span class="label">effective output the task needs</span>
			</dt>
			<dd>
				<h4>The size of the work, not the size of the transcript.</h4>
				<p>
					Effective output is what survives: code that ends up in files, the diff you keep,
					the migration that runs, the answer you act on. That is all Y counts. The
					reasoning it took to get there is not effective output. Neither is reading the
					codebase, running greps, calling tools, backing out of a wrong approach, or
					re-deriving something a compaction just threw away. All of that is real and all
					of it is billed — but it lands in φ, not in Y.
				</p>
				<p>
					So Y is roughly what a competent engineer would have to write if they already
					knew everything. Three small bug fixes across a handful of files is small. A
					feature touching a dozen files is around a million tokens. A greenfield service,
					or a refactor that rewrites a package, is several million.
				</p>
				<p>
					Y is a pure multiplier on the bill and almost nothing on the answer. Five times
					the work is five times the money, at very nearly the same context window.
				</p>
				{@render moves("Y  200K → 5M", yLow, yHigh)}
			</dd>

			<dt>
				<span class="symbol">φ₀</span>
				<span class="label">overhead of finding information</span>
			</dt>
			<dd>
				<h4>What it costs to work out what to write.</h4>
				<p>
					φ(W) is the ratio between what you were billed for and what you actually got:
					φ = 2 means the task emitted two output tokens for every one that mattered. φ₀ is
					that ratio at the reference window — the part that has nothing to do with how big
					the context is, and everything to do with how hard your codebase is to find
					things in.
				</p>
				<p>
					It goes up when names do not tell you where things live; when a grep for a symbol
					returns forty hits across generated code, vendored trees and dead paths; when the
					documentation describes a design that was replaced two years ago; when the only
					way to learn what a service does is to read all of it. It goes up with a weaker
					model too. Two agents in the same repository do not pay the same φ₀, because one
					of them opens the right file on the second try and the other on the ninth.
				</p>
				<p>
					φ₀ scales the whole curve and barely bends it. It is the number you attack with
					repository hygiene, better tooling and a better model — and it is not the number
					that answers which window to run.
				</p>
				{@render moves("φ₀  1.20 → 6.00", phiLow, phiHigh)}
			</dd>

			<dt>
				<span class="symbol">β</span>
				<span class="label">information the task holds at once</span>
			</dt>
			<dd>
				<h4>How much you need in your head before the first correct line.</h4>
				<p>
					Not how big the repository is — how much of it this particular task has to hold
					at once. The test: if the agent's memory were wiped right now, how much would it
					have to go and re-learn before the next edit is safe?
				</p>
				<p>
					β is low when the working set is small. A bug in one endpoint. A dependency bump.
					A change inside a service you can name, where the code you touch and the code
					that constrains it are the same few files. Whatever a compaction discards is
					cheap to recover, so a small window barely hurts.
				</p>
				<p>
					β is high when correctness spans the codebase. Renaming a concept that appears in
					forty files. Changing a wire format six services agree on. Anything where edit
					number forty is only correct because of what was learned at edit number three.
					Every compaction throws that working set away, and rebuilding it is billed at
					full price, over and over.
				</p>
				<p>
					Repository size is a decent proxy and a bad definition. A one-file change in a
					monorepo is still low β; a cross-cutting refactor of a five-file project can be
					high. What sets β is the task, not the boundary of the repo.
				</p>
				<p>
					This is the only control here that materially moves the answer — and the only one
					that cannot be read off a session log. The three <em>Task size</em> buttons are
					illustrative values, not measurements, which is why the page says so instead of
					hiding it.
				</p>
				{@render moves("β  0.00 → 1.20", betaLow, betaHigh)}
			</dd>
		</dl>
	</div>

	<div class="group">
		<h3>The parameters behind the panels</h3>
		<p class="lede short">
			These sit in the two collapsed panels above. They are collapsed because they should be
			measured rather than guessed — but they are where most of the behaviour actually lives.
		</p>
		<dl class="glossary tight">
			<dt>
				<span class="symbol">θ, S<sub>c</sub></span>
				<span class="label">the compaction rule</span>
			</dt>
			<dd>
				<p>
					Compaction fires when the context reaches θ of the window and leaves S<sub>c</sub>
					behind, so the room one cycle actually has is θW − S<sub>c</sub>, not W. At the
					calibration in force right now:
				</p>
				<p class="moves">
					{#each room as r (r.W)}
						<span>
							{tokens(r.W)} window
							<b class="num">{r.H > 0 ? tokens(r.H) : "no room"}</b>
						</span>
					{/each}
				</p>
				<p>
					Halving the window does considerably worse than halving the runway. That is why
					the left-hand side of the curve turns up so hard.
				</p>
			</dd>

			<dt>
				<span class="symbol">K(W)</span>
				<span class="label">compactions</span>
			</dt>
			<dd>
				<p>
					Not a setting — an outcome. K is how many times the task hits the ceiling and has
					its history summarised, and you pay for every one of them twice. Once directly: a
					compaction is itself a model call that reads about θW and writes the replacement
					summary. Once indirectly: everything the summary dropped has to be found again,
					which is precisely what β prices.
				</p>
				<p class="moves">
					<span class="range">this task</span>
					<span>
						at 64K
						<b class="num">{compactsSmall.feasible ? count(compactsSmall.compactions) : "—"}</b>
					</span>
					<span>
						at 256K
						<b class="num">{compactsLarge.feasible ? count(compactsLarge.compactions) : "—"}</b>
					</span>
				</p>
			</dd>

			<dt>
				<span class="symbol">d̄</span>
				<span class="label">context growth per call</span>
			</dt>
			<dd>
				<p>
					How much the conversation grows after one call: the model's own message, tool
					results, file contents, test output, stack traces, the lot. One number for all of
					it, because splitting it up would price the same thing several times. d̄ decides
					how fast you climb to θW, so d̄ decides K. A harness that truncates tool output,
					in a workspace whose files are small, has a low d̄; piping a four-thousand-line
					file into the conversation is a high one.
				</p>
			</dd>

			<dt>
				<span class="symbol">ō</span>
				<span class="label">billed output per call</span>
			</dt>
			<dd>
				<p>
					The exchange rate between output and calls. It is also where the reasoning-effort
					setting shows up: raising effort makes turns longer and more deliberate, which
					raises ō and lowers N for the same O. Whether that lowers the bill depends
					entirely on what it does to φ.
				</p>
			</dd>

			<dt>
				<span class="symbol">B</span>
				<span class="label">the fixed prefix</span>
			</dt>
			<dd>
				<p>
					System prompt, tool definitions, <code>AGENTS.md</code>, the task description. You
					pay for it on every single request, and compaction does not remove it — it is the
					part of the context that is not history. Connecting three more MCP servers raises
					it permanently, on every call, for the rest of the session.
				</p>
			</dd>

			<dt>
				<span class="symbol">ρ</span>
				<span class="label">cached-read share</span>
			</dt>
			<dd>
				<p>
					The reason any of this is affordable at all. At the cached-read share in force
					right now, re-reading a context costs <b>{percent(cacheShare)}</b> of what the
					uncached price would imply. It is also the most fragile number on the page:
					anything that invalidates the prefix — editing an earlier message, letting the
					cache expire between sessions — reprices the whole conversation at
					p<sub>u</sub>.
				</p>
			</dd>

			<dt>
				<span class="symbol">ℓ<sub>I</sub>, ℓ<sub>O</sub></span>
				<span class="label">the long-context tier</span>
			</dt>
			<dd>
				<p>
					A request whose input crosses the threshold is surcharged for the whole request —
					{ratio(pricing.tierInputMult, 0)}× input, {ratio(pricing.tierOutputMult, 1)}× output — not
					just for the part above the line. It is the step you can see in the curve, and it
					is why a window sitting a little over {tokens(pricing.tierThreshold)} can cost
					more than one comfortably under it.
				</p>
			</dd>
		</dl>
	</div>

	<div class="group">
		<h3>Two tasks, two answers</h3>
		<p class="lede short">
			Same agent, same repository, same price list. The only thing that changes is the work.
		</p>
		<div class="examples">
			{@render example(
				"A bug in a service you can name",
				"A failing endpoint. You know which service owns it, the change is a handful of files, and the code that constrains the fix is sitting right next to the code being fixed. Small Y, because there is not much to write. Small β, because whatever a compaction forgets comes back in one grep.",
				LOCAL,
				localBest,
				localPenalty,
				sprawlBest ? tokens(sprawlBest.W) : "the other window",
			)}
			{@render example(
				"Renaming a concept across the monorepo",
				"Forty files, six packages, and a hundred call sites that only make sense together. Large Y, because there is a great deal to write. Large β, because edit number forty is only correct given what was learned at edit number three — and every compaction in between throws that away.",
				SPRAWL,
				sprawlBest,
				sprawlPenalty,
				localBest ? tokens(localBest.W) : "the other window",
			)}
		</div>
		<p class="takeaway">
			Neither window is wrong; they belong to different work. What is worth taking away is the
			asymmetry. Running the small task in the big window costs
			<b class="num">{signedPercent(localPenalty)}</b>. Running the big task in the small window
			costs <b class="num">{signedPercent(sprawlPenalty)}</b>. If one setting has to serve
			everything, guessing high is the cheaper mistake — and the reason to measure your own
			calibration is that the gap between those two numbers is yours, not this page's.
		</p>
	</div>

	<p class="caveat">
		What the model does not claim: above W₀ it assumes productivity stops improving, so φ
		flattens out. Deciding otherwise needs the same task set run to completion at several
		windows. The right-hand side of every curve here is therefore the cost of a bigger window
		with none of its benefit priced in — if large windows do keep helping, the true optimum sits
		further right than what you see.
	</p>
</section>

<style>
	.explainer {
		display: flex;
		flex-direction: column;
		gap: 22px;
		margin-top: clamp(28px, 5vw, 52px);
		padding-top: clamp(24px, 4vw, 40px);
		border-top: 1px solid var(--border);
	}

	h2 {
		font-size: clamp(1.125rem, 2.4vw, 1.375rem);
		font-weight: 600;
		letter-spacing: -0.018em;
	}
	.lede {
		margin-top: 10px;
		max-width: 66ch;
		color: var(--ink-secondary);
		font-size: 0.9375rem;
		line-height: 1.72;
	}
	.lede.short {
		margin-top: 0;
		font-size: 0.875rem;
	}

	/* The causal chain, live at the inspected window. */
	.chain {
		display: flex;
		flex-wrap: wrap;
		align-items: stretch;
		gap: 10px 14px;
		margin: 0;
		padding: 14px 16px;
		list-style: none;
		background: var(--surface-sunken);
		border: 1px solid var(--border);
		border-radius: var(--radius);
	}
	.node {
		display: flex;
		flex-direction: column;
		gap: 1px;
		min-width: 0;
	}
	.node .sym {
		font-family: var(--mono);
		font-size: 0.6875rem;
		color: var(--ink-muted);
	}
	.node .val {
		font-size: 0.9375rem;
		font-weight: 600;
		letter-spacing: -0.01em;
		color: var(--ink);
	}
	.node .cap {
		font-size: 0.6875rem;
		color: var(--ink-muted);
		white-space: nowrap;
	}
	.arrow {
		display: grid;
		place-items: center;
		color: var(--axis);
	}
	.chain-note {
		max-width: 72ch;
		margin-top: -10px;
		color: var(--ink-secondary);
		font-size: 0.75rem;
		line-height: 1.65;
	}

	.formula {
		display: grid;
		grid-template-columns: auto auto minmax(0, 1fr);
		align-items: baseline;
		column-gap: 16px;
		row-gap: 8px;
		padding: 16px 18px;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		overflow-x: auto;
		font-family: var(--mono);
		font-size: 0.8125rem;
	}
	.lhs {
		text-align: right;
		white-space: nowrap;
		color: var(--ink);
	}
	.rhs {
		white-space: nowrap;
		color: var(--ink);
	}
	.gloss {
		font-family: var(--font);
		font-size: 0.6875rem;
		color: var(--ink-muted);
		white-space: nowrap;
	}
	.formula sub,
	.formula sup {
		font-size: 0.72em;
	}

	.group {
		display: flex;
		flex-direction: column;
		gap: 18px;
		padding-top: 26px;
		border-top: 1px solid var(--border);
	}
	h3 {
		font-size: 0.9375rem;
		font-weight: 600;
		letter-spacing: -0.008em;
	}

	.glossary {
		display: grid;
		grid-template-columns: 136px minmax(0, 1fr);
		gap: 30px 24px;
		margin: 0;
	}
	.glossary.tight {
		gap: 22px 24px;
	}
	dt {
		display: flex;
		flex-direction: column;
		gap: 3px;
		min-width: 0;
	}
	.symbol {
		font-family: var(--mono);
		font-size: 1rem;
		color: var(--ink);
	}
	.label {
		font-size: 0.6875rem;
		line-height: 1.45;
		color: var(--ink-muted);
	}
	dd {
		margin: 0;
		min-width: 0;
	}
	h4 {
		margin: -2px 0 8px;
		font-size: 0.875rem;
		font-weight: 600;
		letter-spacing: -0.008em;
		color: var(--ink);
	}
	dd p {
		max-width: 66ch;
		color: var(--ink-secondary);
		font-size: 0.875rem;
		line-height: 1.72;
	}
	dd p + p {
		margin-top: 11px;
	}
	dd code {
		font-family: var(--mono);
		font-size: 0.9em;
	}
	dd em {
		font-style: normal;
		color: var(--ink);
	}
	dd b {
		font-weight: 600;
		color: var(--ink);
	}

	/* Evidence strip: what this parameter does to the curve, computed live. */
	.moves {
		display: flex;
		flex-wrap: wrap;
		gap: 3px 18px;
		max-width: 66ch;
		margin-top: 13px;
		padding-top: 10px;
		border-top: 1px solid var(--border);
		color: var(--ink-secondary);
		font-size: 0.6875rem;
	}
	.moves .range {
		font-family: var(--mono);
		color: var(--ink-secondary);
	}
	.moves b {
		font-weight: 600;
		color: var(--ink);
	}
	dd p.moves + p {
		margin-top: 13px;
	}

	.examples {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
		gap: 16px;
	}
	.example {
		display: flex;
		flex-direction: column;
		padding: 18px;
	}
	.example h4 {
		margin: 0 0 8px;
		font-size: 0.9375rem;
	}
	.example p {
		max-width: 60ch;
		color: var(--ink-secondary);
		font-size: 0.8125rem;
		line-height: 1.68;
	}
	.inputs {
		margin-top: auto;
		padding-top: 12px;
		font-family: var(--mono);
		font-size: 0.75rem;
		color: var(--ink-muted);
	}
	.inputs b {
		font-weight: 400;
		color: var(--ink);
	}
	.result {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		gap: 0;
		margin: 12px 0 0;
	}
	.result dt,
	.result dd {
		padding: 8px 0;
		border-top: 1px solid var(--border);
		line-height: 20px;
	}
	.result dt {
		font-size: 0.75rem;
		color: var(--ink-muted);
	}
	.result dd {
		text-align: right;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--ink);
	}
	.example button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 6px;
		margin-top: 16px;
		padding: 7px 12px;
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		background: transparent;
		color: var(--ink-secondary);
		font-size: 0.75rem;
		cursor: pointer;
		transition: color 0.14s ease, border-color 0.14s ease, background-color 0.14s ease;
	}
	.example button:hover {
		color: var(--ink);
		border-color: var(--border-strong);
		background: var(--surface-sunken);
	}

	.takeaway {
		max-width: 68ch;
		color: var(--ink-secondary);
		font-size: 0.875rem;
		line-height: 1.72;
	}
	.takeaway b {
		font-weight: 600;
		color: var(--ink);
	}

	.caveat {
		max-width: 72ch;
		padding-top: 20px;
		border-top: 1px solid var(--border);
		color: var(--ink-secondary);
		font-size: 0.75rem;
		line-height: 1.7;
	}

	@media (max-width: 720px) {
		.glossary,
		.glossary.tight {
			grid-template-columns: minmax(0, 1fr);
			gap: 26px;
		}
		dt {
			flex-direction: row;
			align-items: baseline;
			gap: 8px;
		}
		dd {
			margin-top: -18px;
		}
		.formula {
			grid-template-columns: auto minmax(0, 1fr);
			row-gap: 4px;
			padding: 14px;
			font-size: 0.75rem;
		}
		.gloss {
			grid-column: 1 / -1;
			padding-bottom: 11px;
		}
		.gloss:last-child {
			padding-bottom: 0;
		}
	}
</style>
