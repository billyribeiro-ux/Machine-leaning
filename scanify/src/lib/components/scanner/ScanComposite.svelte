<script lang="ts">
	interface ScanResult {
		id: string;
		symbol: string;
		name: string;
		price: number;
		prevPrice?: number;
		change: number;
		changePercent: number;
		direction: 'bullish' | 'bearish' | 'neutral';
		strength: 1 | 2 | 3 | 4 | 5;
		volume: number;
		relativeVolume: number;
		sector: string;
		timestamp: number;
		sparklineData: number[];
		category: string;
		signalName: string;
	}

	interface SymbolGroup {
		symbol: string;
		name: string;
		price: number;
		changePercent: number;
		direction: 'bullish' | 'bearish' | 'neutral';
		sector: string;
		results: ScanResult[];
		maxStrength: number;
		latestTimestamp: number;
	}

	interface Props {
		results: ScanResult[];
		class?: string;
	}

	let { results, class: className = '' }: Props = $props();

	let expandedSymbol = $state<string | null>(null);

	// Group results by symbol, sorted by most signals first
	let groups = $derived.by((): SymbolGroup[] => {
		const map = new Map<string, ScanResult[]>();

		for (const r of results) {
			if (!map.has(r.symbol)) {
				map.set(r.symbol, []);
			}
			map.get(r.symbol)!.push(r);
		}

		const groupList: SymbolGroup[] = [];
		for (const [symbol, items] of map) {
			const latest = items.reduce((a, b) => (a.timestamp > b.timestamp ? a : b));
			const maxStr = items.reduce((m, r) => Math.max(m, r.strength), 0);

			groupList.push({
				symbol,
				name: latest.name,
				price: latest.price,
				changePercent: latest.changePercent,
				direction: latest.direction,
				sector: latest.sector,
				results: [...items].sort((a, b) => b.timestamp - a.timestamp),
				maxStrength: maxStr,
				latestTimestamp: latest.timestamp,
			});
		}

		// Sort by number of signals descending, then by max strength
		groupList.sort((a, b) => {
			if (b.results.length !== a.results.length) return b.results.length - a.results.length;
			return b.maxStrength - a.maxStrength;
		});

		return groupList;
	});

	function toggleGroup(symbol: string) {
		expandedSymbol = expandedSymbol === symbol ? null : symbol;
	}

	function formatPrice(val: number): string {
		if (!Number.isFinite(val)) return '$--';
		return '$' + val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	}

	function formatPercent(val: number): string {
		if (!Number.isFinite(val)) return '--%';
		const sign = val > 0 ? '+' : '';
		return sign + val.toFixed(2) + '%';
	}

	function changeColor(val: number): string {
		if (val > 0) return 'color-bullish';
		if (val < 0) return 'color-bearish';
		return 'color-tertiary';
	}

	function directionBadgeClass(dir: string): string {
		if (dir === 'bullish') return 'badge-bullish';
		if (dir === 'bearish') return 'badge-bearish';
		return 'badge-neutral';
	}

	function strengthDots(s: number): string {
		let out = '';
		for (let i = 0; i < 5; i++) {
			out += i < s ? '●' : '○';
		}
		return out;
	}

	function strengthColor(s: number): string {
		const map: Record<number, string> = {
			1: 'strength-1',
			2: 'strength-2',
			3: 'strength-3',
			4: 'strength-4',
			5: 'strength-5',
		};
		return map[s] || 'color-tertiary';
	}

	function signalCountColor(count: number): string {
		if (count >= 5) return 'signal-count-warning';
		if (count >= 3) return 'signal-count-accent';
		return 'signal-count-default';
	}

	function signalDotClass(dir: string): string {
		if (dir === 'bullish') return 'dot-bullish';
		if (dir === 'bearish') return 'dot-bearish';
		return 'dot-neutral';
	}

	function relativeTime(ts: number): string {
		const delta = Date.now() - ts;
		if (delta < 60_000) return 'now';
		if (delta < 3_600_000) return Math.floor(delta / 60_000) + 'm';
		if (delta < 86_400_000) return Math.floor(delta / 3_600_000) + 'h';
		return Math.floor(delta / 86_400_000) + 'd';
	}

	function headerBorderClass(dir: string): string {
		if (dir === 'bullish') return 'border-left-bullish';
		if (dir === 'bearish') return 'border-left-bearish';
		return 'border-left-neutral';
	}
</script>

<div class="composite-list {className}" role="list" aria-label="Composite scan results grouped by symbol">
	{#if groups.length === 0}
		<div class="empty-state">
			<p class="empty-text">No results to display</p>
		</div>
	{:else}
		{#each groups as group (group.symbol)}
			{@const isExpanded = expandedSymbol === group.symbol}
			<div class="group-card">
				<!-- Group header -->
				<button
					type="button"
					class="group-header {headerBorderClass(group.direction)}"
					onclick={() => toggleGroup(group.symbol)}
					aria-expanded={isExpanded}
				>
					<!-- Expand chevron -->
					<svg
						xmlns="http://www.w3.org/2000/svg"
						width="14"
						height="14"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="2"
						stroke-linecap="round"
						stroke-linejoin="round"
						class="chevron-icon {isExpanded ? 'chevron-expanded' : ''}"
					>
						<path d="m9 18 6-6-6-6" />
					</svg>

					<!-- Symbol -->
					<div class="symbol-cell">
						<span class="symbol-label" style="letter-spacing: 0.02em;">
							{group.symbol}
						</span>
					</div>

					<!-- Name -->
					<span class="group-name">
						{group.name}
					</span>

					<!-- Price + Change -->
					<div class="price-change-group">
						<span class="price-value mono-nums">{formatPrice(group.price)}</span>
						<span class="change-value mono-nums {changeColor(group.changePercent)}">{formatPercent(group.changePercent)}</span>
					</div>

					<!-- Signal count badge -->
					<span class="signal-count-badge {signalCountColor(group.results.length)}">
						{group.results.length}
					</span>

					<!-- Max strength indicator -->
					<span class="strength-indicator {strengthColor(group.maxStrength)}" title="Max strength: {group.maxStrength}/5">
						{strengthDots(group.maxStrength)}
					</span>

					<!-- Sector -->
					<span class="sector-label">
						{group.sector}
					</span>
				</button>

				<!-- Expanded signals list -->
				{#if isExpanded}
					<div class="signals-panel">
						{#each group.results as result, i (result.id)}
							<div
								class="signal-row {i < group.results.length - 1 ? 'signal-row-bordered' : ''}"
							>
								<!-- Timeline dot -->
								<div class="timeline-dot {signalDotClass(result.direction)}"></div>

								<!-- Signal name badge -->
								<span class="signal-name-badge {directionBadgeClass(result.direction)}">
									{result.signalName}
								</span>

								<!-- Direction label -->
								<span class="direction-label">{result.direction}</span>

								<!-- Strength -->
								<span class="strength-indicator {strengthColor(result.strength)}" title="Strength: {result.strength}/5">
									{strengthDots(result.strength)}
								</span>

								<!-- Category -->
								<span class="category-label">{result.category}</span>

								<!-- Spacer -->
								<div class="spacer"></div>

								<!-- Relative volume -->
								<span class="relative-volume mono-nums {result.relativeVolume >= 2 ? 'volume-high' : 'volume-normal'}">
									{result.relativeVolume.toFixed(1)}x
								</span>

								<!-- Timestamp -->
								<span class="timestamp mono-nums">
									{relativeTime(result.timestamp)}
								</span>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		{/each}
	{/if}

	<!-- Summary footer -->
	{#if groups.length > 0}
		<div class="summary-footer">
			<span class="summary-text">
				{groups.length} symbol{groups.length !== 1 ? 's' : ''} &middot; {results.length} total signal{results.length !== 1 ? 's' : ''}
			</span>
			<span class="summary-text">
				Sorted by signal count
			</span>
		</div>
	{/if}
</div>

<style>
	/* Container */
	.composite-list > :global(* + *) {
		margin-top: 6px;
	}

	/* Empty state */
	.empty-state {
		border-radius: var(--radius-lg);
		border: 1px solid var(--border-subtle);
		background-color: var(--bg-surface);
		padding: 40px 24px;
		text-align: center;
	}

	.empty-text {
		font-size: var(--text-sm);
		color: var(--text-disabled);
	}

	/* Group card */
	.group-card {
		overflow: hidden;
		border-radius: var(--radius-lg);
		border: 1px solid var(--border-subtle);
		background-color: var(--bg-surface);
		transition: all 150ms;
	}

	/* Group header button */
	.group-header {
		display: flex;
		width: 100%;
		align-items: center;
		gap: 12px;
		border-left: 2px solid;
		padding: 10px 16px;
		text-align: left;
		transition: color 150ms, background-color 150ms, border-color 150ms;
	}

	.group-header:hover {
		background-color: var(--bg-elevated);
	}

	/* Header border-left color variants */
	.border-left-bullish {
		border-left-color: var(--bullish-dim);
	}

	.border-left-bearish {
		border-left-color: var(--bearish-dim);
	}

	.border-left-neutral {
		border-left-color: var(--neutral-dim);
	}

	/* Chevron icon */
	.chevron-icon {
		flex-shrink: 0;
		color: var(--text-disabled);
		transition: transform 150ms;
	}

	.chevron-expanded {
		transform: rotate(90deg);
	}

	/* Symbol cell */
	.symbol-cell {
		min-width: 70px;
	}

	.symbol-label {
		font-family: var(--font-mono);
		font-size: var(--text-sm);
		font-weight: 700;
		text-transform: uppercase;
		color: var(--text-primary);
	}

	/* Group name (responsive) */
	.group-name {
		display: none;
		font-size: var(--text-xs);
		color: var(--text-tertiary);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		max-width: 120px;
	}

	@media (min-width: 640px) {
		.group-name {
			display: inline;
		}
	}

	/* Price + Change group */
	.price-change-group {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-shrink: 0;
		margin-left: auto;
	}

	.price-value {
		font-size: var(--text-sm);
		color: var(--text-primary);
	}

	.change-value {
		font-size: var(--text-sm);
		font-weight: 500;
	}

	/* Change color variants */
	.color-bullish {
		color: var(--bullish);
	}

	.color-bearish {
		color: var(--bearish);
	}

	.color-tertiary {
		color: var(--text-tertiary);
	}

	/* Signal count badge */
	.signal-count-badge {
		flex-shrink: 0;
		display: inline-flex;
		height: 20px;
		min-width: 20px;
		align-items: center;
		justify-content: center;
		border-radius: var(--radius-full);
		border: 1px solid;
		padding: 0 6px;
		font-size: 10px;
		font-weight: 700;
		line-height: 1;
	}

	.signal-count-warning {
		background-color: var(--warning-bg);
		color: var(--warning-bright);
		border-color: var(--warning-dim);
	}

	.signal-count-accent {
		background-color: var(--accent-bg);
		color: var(--accent-bright);
		border-color: var(--accent-dim);
	}

	.signal-count-default {
		background-color: var(--bg-overlay);
		color: var(--text-secondary);
		border-color: var(--border-default);
	}

	/* Strength indicator */
	.strength-indicator {
		flex-shrink: 0;
		font-family: var(--font-mono);
		font-size: 10px;
		letter-spacing: -0.01em;
	}

	/* Strength color variants */
	.strength-1 {
		color: var(--strength-1);
	}

	.strength-2 {
		color: var(--strength-2);
	}

	.strength-3 {
		color: var(--strength-3);
	}

	.strength-4 {
		color: var(--strength-4);
	}

	.strength-5 {
		color: var(--strength-5);
	}

	/* Sector label (responsive) */
	.sector-label {
		display: none;
		flex-shrink: 0;
		font-size: var(--text-2xs);
		color: var(--text-disabled);
	}

	@media (min-width: 1024px) {
		.sector-label {
			display: inline;
		}
	}

	/* Expanded signals panel */
	.signals-panel {
		border-top: 1px solid var(--border-subtle);
		background-color: var(--bg-base);
	}

	/* Signal row */
	.signal-row {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 8px 20px;
		transition: color 150ms, background-color 150ms, border-color 150ms;
	}

	.signal-row:hover {
		background-color: var(--bg-surface);
	}

	.signal-row-bordered {
		border-bottom: 1px solid var(--border-subtle);
	}

	/* Timeline dot */
	.timeline-dot {
		height: 8px;
		width: 8px;
		flex-shrink: 0;
		border-radius: var(--radius-full);
	}

	.dot-bullish {
		background-color: var(--bullish);
	}

	.dot-bearish {
		background-color: var(--bearish);
	}

	.dot-neutral {
		background-color: var(--neutral);
	}

	/* Signal name badge */
	.signal-name-badge {
		display: inline-flex;
		align-items: center;
		border-radius: var(--radius-full);
		padding: 2px 8px;
		font-size: 10px;
		font-weight: 500;
		line-height: 1;
	}

	/* Direction badge variants (shared with signal-name-badge) */
	.badge-bullish {
		background-color: var(--bullish-bg, rgba(var(--bullish-rgb), 0.1));
		color: var(--bullish);
	}

	.badge-bearish {
		background-color: var(--bearish-bg, rgba(var(--bearish-rgb), 0.1));
		color: var(--bearish);
	}

	.badge-neutral {
		background-color: var(--neutral-bg, rgba(var(--neutral-rgb), 0.1));
		color: var(--neutral);
	}

	/* Direction label */
	.direction-label {
		font-size: var(--text-xs);
		color: var(--text-tertiary);
	}

	/* Category label (responsive) */
	.category-label {
		display: none;
		font-size: var(--text-2xs);
		color: var(--text-disabled);
	}

	@media (min-width: 640px) {
		.category-label {
			display: inline;
		}
	}

	/* Spacer */
	.spacer {
		flex: 1;
	}

	/* Relative volume */
	.relative-volume {
		font-size: var(--text-xs);
	}

	.volume-high {
		color: var(--warning);
	}

	.volume-normal {
		color: var(--text-tertiary);
	}

	/* Timestamp */
	.timestamp {
		font-size: var(--text-2xs);
		color: var(--text-disabled);
		flex-shrink: 0;
	}

	/* Summary footer */
	.summary-footer {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0 8px;
		padding-top: 4px;
	}

	.summary-text {
		font-size: var(--text-2xs);
		color: var(--text-disabled);
	}
</style>
