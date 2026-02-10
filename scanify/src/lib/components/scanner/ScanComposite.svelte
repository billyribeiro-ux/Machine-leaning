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
		if (val > 0) return 'text-[var(--bullish)]';
		if (val < 0) return 'text-[var(--bearish)]';
		return 'text-[var(--text-tertiary)]';
	}

	function directionBadgeClass(dir: string): string {
		if (dir === 'bullish') return 'badge-bullish';
		if (dir === 'bearish') return 'badge-bearish';
		return 'badge-neutral';
	}

	function strengthDots(s: number): string {
		let out = '';
		for (let i = 0; i < 5; i++) {
			out += i < s ? '\u25CF' : '\u25CB';
		}
		return out;
	}

	function strengthColor(s: number): string {
		const map: Record<number, string> = {
			1: 'text-[var(--strength-1)]',
			2: 'text-[var(--strength-2)]',
			3: 'text-[var(--strength-3)]',
			4: 'text-[var(--strength-4)]',
			5: 'text-[var(--strength-5)]',
		};
		return map[s] || 'text-[var(--text-tertiary)]';
	}

	function signalCountColor(count: number): string {
		if (count >= 5) return 'bg-[var(--warning-bg)] text-[var(--warning-bright)] border-[var(--warning-dim)]';
		if (count >= 3) return 'bg-[var(--accent-bg)] text-[var(--accent-bright)] border-[var(--accent-dim)]';
		return 'bg-[var(--bg-overlay)] text-[var(--text-secondary)] border-[var(--border-default)]';
	}

	function signalDotClass(dir: string): string {
		if (dir === 'bullish') return 'bg-[var(--bullish)]';
		if (dir === 'bearish') return 'bg-[var(--bearish)]';
		return 'bg-[var(--neutral)]';
	}

	function relativeTime(ts: number): string {
		const delta = Date.now() - ts;
		if (delta < 60_000) return 'now';
		if (delta < 3_600_000) return Math.floor(delta / 60_000) + 'm';
		if (delta < 86_400_000) return Math.floor(delta / 3_600_000) + 'h';
		return Math.floor(delta / 86_400_000) + 'd';
	}

	function headerBorderClass(dir: string): string {
		if (dir === 'bullish') return 'border-l-[var(--bullish-dim)]';
		if (dir === 'bearish') return 'border-l-[var(--bearish-dim)]';
		return 'border-l-[var(--neutral-dim)]';
	}
</script>

<div class="space-y-1.5 {className}" role="list" aria-label="Composite scan results grouped by symbol">
	{#if groups.length === 0}
		<div class="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-6 py-10 text-center">
			<p class="text-sm text-[var(--text-disabled)]">No results to display</p>
		</div>
	{:else}
		{#each groups as group (group.symbol)}
			{@const isExpanded = expandedSymbol === group.symbol}
			<div class="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] transition-all duration-150">
				<!-- Group header -->
				<button
					type="button"
					class="flex w-full items-center gap-3 border-l-2 px-4 py-2.5 text-left transition-colors hover:bg-[var(--bg-elevated)]
						{headerBorderClass(group.direction)}"
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
						class="flex-shrink-0 text-[var(--text-disabled)] transition-transform duration-150 {isExpanded ? 'rotate-90' : ''}"
					>
						<path d="m9 18 6-6-6-6" />
					</svg>

					<!-- Symbol -->
					<div class="min-w-[70px]">
						<span class="font-mono text-sm font-bold uppercase text-[var(--text-primary)]" style="letter-spacing: 0.02em;">
							{group.symbol}
						</span>
					</div>

					<!-- Name -->
					<span class="hidden text-xs text-[var(--text-tertiary)] sm:inline truncate" style="max-width: 120px;">
						{group.name}
					</span>

					<!-- Price + Change -->
					<div class="flex items-center gap-2 flex-shrink-0 ml-auto">
						<span class="mono-nums text-sm text-[var(--text-primary)]">{formatPrice(group.price)}</span>
						<span class="mono-nums text-sm font-medium {changeColor(group.changePercent)}">{formatPercent(group.changePercent)}</span>
					</div>

					<!-- Signal count badge -->
					<span class="flex-shrink-0 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full border px-1.5 text-[10px] font-bold leading-none {signalCountColor(group.results.length)}">
						{group.results.length}
					</span>

					<!-- Max strength indicator -->
					<span class="flex-shrink-0 font-mono text-[10px] tracking-tight {strengthColor(group.maxStrength)}" title="Max strength: {group.maxStrength}/5">
						{strengthDots(group.maxStrength)}
					</span>

					<!-- Sector -->
					<span class="hidden flex-shrink-0 text-2xs text-[var(--text-disabled)] lg:inline">
						{group.sector}
					</span>
				</button>

				<!-- Expanded signals list -->
				{#if isExpanded}
					<div class="border-t border-[var(--border-subtle)] bg-[var(--bg-base)]">
						{#each group.results as result, i (result.id)}
							<div
								class="flex items-center gap-3 px-5 py-2 transition-colors hover:bg-[var(--bg-surface)]
									{i < group.results.length - 1 ? 'border-b border-[var(--border-subtle)]' : ''}"
							>
								<!-- Timeline dot -->
								<div class="h-2 w-2 flex-shrink-0 rounded-full {signalDotClass(result.direction)}"></div>

								<!-- Signal name badge -->
								<span class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium leading-none {directionBadgeClass(result.direction)}">
									{result.signalName}
								</span>

								<!-- Direction label -->
								<span class="text-xs text-[var(--text-tertiary)]">{result.direction}</span>

								<!-- Strength -->
								<span class="font-mono text-[10px] tracking-tight {strengthColor(result.strength)}" title="Strength: {result.strength}/5">
									{strengthDots(result.strength)}
								</span>

								<!-- Category -->
								<span class="hidden text-2xs text-[var(--text-disabled)] sm:inline">{result.category}</span>

								<!-- Spacer -->
								<div class="flex-1"></div>

								<!-- Relative volume -->
								<span class="mono-nums text-xs {result.relativeVolume >= 2 ? 'text-[var(--warning)]' : 'text-[var(--text-tertiary)]'}">
									{result.relativeVolume.toFixed(1)}x
								</span>

								<!-- Timestamp -->
								<span class="mono-nums text-2xs text-[var(--text-disabled)] flex-shrink-0">
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
		<div class="flex items-center justify-between px-2 pt-1">
			<span class="text-2xs text-[var(--text-disabled)]">
				{groups.length} symbol{groups.length !== 1 ? 's' : ''} &middot; {results.length} total signal{results.length !== 1 ? 's' : ''}
			</span>
			<span class="text-2xs text-[var(--text-disabled)]">
				Sorted by signal count
			</span>
		</div>
	{/if}
</div>
