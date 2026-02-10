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

	interface Props {
		results: ScanResult[];
		onrowselect?: (result: ScanResult) => void;
		onrowexpand?: (result: ScanResult) => void;
		class?: string;
	}

	let { results, onrowselect, onrowexpand, class: className = '' }: Props = $props();

	let selectedId = $state<string | null>(null);
	let expandedId = $state<string | null>(null);
	let selectedIndex = $state(0);
	let containerEl: HTMLDivElement;
	let scrollTop = $state(0);
	const ROW_HEIGHT = 40;
	const VISIBLE_BUFFER = 5;

	// Virtual scrolling calculations
	let containerHeight = $state(600);
	let visibleStart = $derived(Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - VISIBLE_BUFFER));
	let visibleEnd = $derived(Math.min(results.length, Math.ceil((scrollTop + containerHeight) / ROW_HEIGHT) + VISIBLE_BUFFER));
	let visibleResults = $derived(results.slice(visibleStart, visibleEnd));
	let totalHeight = $derived(results.length * ROW_HEIGHT);

	// Sort state
	let sortField = $state<string>('changePercent');
	let sortDir = $state<'asc' | 'desc'>('desc');

	function handleScroll(e: Event) {
		const target = e.target as HTMLDivElement;
		scrollTop = target.scrollTop;
	}

	function selectRow(result: ScanResult, index: number) {
		selectedId = result.id;
		selectedIndex = index;
		onrowselect?.(result);
	}

	function toggleExpand(result: ScanResult) {
		expandedId = expandedId === result.id ? null : result.id;
		onrowexpand?.(result);
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'j' || e.key === 'ArrowDown') {
			e.preventDefault();
			selectedIndex = Math.min(selectedIndex + 1, results.length - 1);
			const row = results[selectedIndex];
			selectedId = row?.id ?? null;
			if (row) onrowselect?.(row);
			scrollToIndex(selectedIndex);
		} else if (e.key === 'k' || e.key === 'ArrowUp') {
			e.preventDefault();
			selectedIndex = Math.max(selectedIndex - 1, 0);
			const row = results[selectedIndex];
			selectedId = row?.id ?? null;
			if (row) onrowselect?.(row);
			scrollToIndex(selectedIndex);
		} else if (e.key === 'Enter') {
			e.preventDefault();
			const row = results[selectedIndex];
			if (row) {
				toggleExpand(row);
			}
		}
	}

	function scrollToIndex(idx: number) {
		if (!containerEl) return;
		const rowTop = idx * ROW_HEIGHT;
		const rowBottom = rowTop + ROW_HEIGHT;
		const viewTop = containerEl.scrollTop;
		const viewBottom = viewTop + containerHeight;

		if (rowTop < viewTop) {
			containerEl.scrollTop = rowTop;
		} else if (rowBottom > viewBottom) {
			containerEl.scrollTop = rowBottom - containerHeight;
		}
	}

	function toggleSort(field: string) {
		if (sortField === field) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			sortField = field;
			sortDir = 'desc';
		}
	}

	function sortIndicator(field: string): string {
		if (sortField !== field) return '';
		return sortDir === 'asc' ? ' \u25B2' : ' \u25BC';
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

	function formatVolume(val: number): string {
		if (!Number.isFinite(val)) return '--';
		if (val >= 1_000_000_000) return (val / 1_000_000_000).toFixed(1) + 'B';
		if (val >= 1_000_000) return (val / 1_000_000).toFixed(1) + 'M';
		if (val >= 1_000) return (val / 1_000).toFixed(1) + 'K';
		return val.toFixed(0);
	}

	function formatTimestamp(ts: number): string {
		const d = new Date(ts);
		const now = Date.now();
		const delta = now - ts;
		if (delta < 60_000) return 'just now';
		if (delta < 3_600_000) return Math.floor(delta / 60_000) + 'm ago';
		return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
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

	function relVolColor(rv: number): string {
		if (rv >= 3) return 'text-[var(--warning-bright)]';
		if (rv >= 2) return 'text-[var(--warning)]';
		if (rv >= 1.5) return 'text-[var(--bullish)]';
		return 'text-[var(--text-secondary)]';
	}

	$effect(() => {
		if (containerEl) {
			const ro = new ResizeObserver((entries) => {
				for (const entry of entries) {
					containerHeight = entry.contentRect.height;
				}
			});
			ro.observe(containerEl);
			return () => ro.disconnect();
		}
	});

	const columns = [
		{ key: 'symbol', label: 'Symbol', align: 'left' as const, width: 'w-[100px]' },
		{ key: 'price', label: 'Price', align: 'right' as const, width: 'w-[90px]' },
		{ key: 'changePercent', label: 'Change%', align: 'right' as const, width: 'w-[85px]' },
		{ key: 'signalName', label: 'Signal', align: 'left' as const, width: 'w-[120px]' },
		{ key: 'strength', label: 'Strength', align: 'center' as const, width: 'w-[80px]' },
		{ key: 'volume', label: 'Volume', align: 'right' as const, width: 'w-[85px]' },
		{ key: 'relativeVolume', label: 'RelVol', align: 'right' as const, width: 'w-[70px]' },
		{ key: 'sector', label: 'Sector', align: 'left' as const, width: 'w-[100px]' },
		{ key: 'timestamp', label: 'Time', align: 'right' as const, width: 'w-[70px]' },
	];
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
	class="flex flex-col overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] {className}"
	onkeydown={handleKeydown}
	tabindex="0"
	role="grid"
	aria-label="Scanner results table"
>
	<!-- Fixed header -->
	<div class="flex items-center border-b border-[var(--border-default)] bg-[var(--bg-elevated)] px-1" style="height: 36px; min-height: 36px;">
		{#each columns as col}
			<button
				class="flex-shrink-0 {col.width} px-2 py-1.5 text-2xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-primary)] select-none
					{col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'}"
				onclick={() => toggleSort(col.key)}
				type="button"
			>
				{col.label}{sortIndicator(col.key)}
			</button>
		{/each}
	</div>

	<!-- Scrollable body with virtual scrolling -->
	<div
		class="flex-1 overflow-y-auto"
		bind:this={containerEl}
		onscroll={handleScroll}
		role="rowgroup"
	>
		<div style="height: {totalHeight}px; position: relative;">
			{#each visibleResults as result, vIdx (result.id)}
				{@const actualIndex = visibleStart + vIdx}
				{@const isSelected = selectedId === result.id}
				{@const isExpanded = expandedId === result.id}
				{@const isEven = actualIndex % 2 === 0}

				<!-- Row -->
				<div
					class="absolute left-0 right-0 flex items-center px-1 transition-colors duration-75 cursor-pointer
						{isSelected ? 'bg-[var(--accent-bg)] border-l-2 border-l-[var(--accent)]' : isEven ? 'bg-transparent' : 'bg-[oklch(0.12_0.02_260)]'}
						{!isSelected ? 'hover:bg-[var(--hover-overlay)] hover:border-l-2 hover:border-l-[var(--border-strong)]' : ''}"
					style="top: {actualIndex * ROW_HEIGHT}px; height: {ROW_HEIGHT}px;"
					onclick={() => selectRow(result, actualIndex)}
					ondblclick={() => toggleExpand(result)}
					role="row"
					aria-selected={isSelected}
					aria-rowindex={actualIndex + 1}
				>
					<!-- Symbol -->
					<div class="flex-shrink-0 w-[100px] px-2">
						<span class="font-mono text-sm font-semibold uppercase text-[var(--text-primary)]" style="letter-spacing: 0.02em;">
							{result.symbol}
						</span>
					</div>

					<!-- Price -->
					<div class="flex-shrink-0 w-[90px] px-2 text-right">
						<span class="mono-nums text-sm text-[var(--text-primary)]">
							{formatPrice(result.price)}
						</span>
					</div>

					<!-- Change% -->
					<div class="flex-shrink-0 w-[85px] px-2 text-right">
						<span class="mono-nums text-sm font-medium {changeColor(result.changePercent)}">
							{formatPercent(result.changePercent)}
						</span>
					</div>

					<!-- Signal -->
					<div class="flex-shrink-0 w-[120px] px-2">
						<span class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium leading-none {directionBadgeClass(result.direction)}">
							{result.signalName}
						</span>
					</div>

					<!-- Strength (dots) -->
					<div class="flex-shrink-0 w-[80px] px-2 text-center">
						<span class="font-mono text-xs tracking-tight {strengthColor(result.strength)}" title="Strength: {result.strength}/5">
							{strengthDots(result.strength)}
						</span>
					</div>

					<!-- Volume -->
					<div class="flex-shrink-0 w-[85px] px-2 text-right">
						<span class="mono-nums text-sm text-[var(--text-secondary)]">
							{formatVolume(result.volume)}
						</span>
					</div>

					<!-- RelVol -->
					<div class="flex-shrink-0 w-[70px] px-2 text-right">
						<span class="mono-nums text-sm font-medium {relVolColor(result.relativeVolume)}">
							{result.relativeVolume.toFixed(1)}x
						</span>
					</div>

					<!-- Sector -->
					<div class="flex-shrink-0 w-[100px] px-2 truncate">
						<span class="text-xs text-[var(--text-tertiary)]">
							{result.sector}
						</span>
					</div>

					<!-- Time -->
					<div class="flex-shrink-0 w-[70px] px-2 text-right">
						<span class="mono-nums text-xs text-[var(--text-tertiary)]">
							{formatTimestamp(result.timestamp)}
						</span>
					</div>
				</div>

				<!-- Expanded detail row -->
				{#if isExpanded}
					<div
						class="absolute left-0 right-0 border-y border-[var(--border-default)] bg-[var(--bg-elevated)] px-4 py-3"
						style="top: {(actualIndex + 1) * ROW_HEIGHT}px;"
					>
						<div class="grid grid-cols-2 gap-4 text-sm">
							<!-- Left column: detail info -->
							<div class="space-y-2">
								<div class="flex items-center gap-2">
									<span class="font-mono text-base font-bold text-[var(--text-primary)]">{result.symbol}</span>
									<span class="text-[var(--text-tertiary)]">{result.name}</span>
								</div>
								<div class="grid grid-cols-3 gap-3">
									<div>
										<div class="text-2xs uppercase text-[var(--text-tertiary)]">Price</div>
										<div class="mono-nums text-[var(--text-primary)]">{formatPrice(result.price)}</div>
									</div>
									<div>
										<div class="text-2xs uppercase text-[var(--text-tertiary)]">Change</div>
										<div class="mono-nums {changeColor(result.changePercent)}">{formatPercent(result.changePercent)}</div>
									</div>
									<div>
										<div class="text-2xs uppercase text-[var(--text-tertiary)]">Volume</div>
										<div class="mono-nums text-[var(--text-secondary)]">{formatVolume(result.volume)}</div>
									</div>
								</div>
							</div>

							<!-- Right column: sparkline + signal -->
							<div class="space-y-2">
								<div class="flex items-center gap-2">
									<span class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium {directionBadgeClass(result.direction)}">
										{result.direction}
									</span>
									<span class="text-xs text-[var(--text-tertiary)]">Category: {result.category}</span>
								</div>
								{#if result.sparklineData.length > 1}
									{@const sparkW = 200}
									{@const sparkH = 40}
									{@const sparkData = result.sparklineData}
									{@const minVal = Math.min(...sparkData)}
									{@const maxVal = Math.max(...sparkData)}
									{@const range = maxVal - minVal || 1}
									{@const sparkPath = sparkData.map((v, i) => {
										const x = 2 + (i / (sparkData.length - 1)) * (sparkW - 4);
										const y = 2 + (sparkH - 4) - ((v - minVal) / range) * (sparkH - 4);
										return (i === 0 ? 'M ' : 'L ') + x + ' ' + y;
									}).join(' ')}
									{@const lastVal = sparkData[sparkData.length - 1] ?? 0}
									{@const firstVal = sparkData[0] ?? 0}
									{@const sparkColor = lastVal >= firstVal
										? 'var(--bullish)'
										: 'var(--bearish)'}
									<svg width={sparkW} height={sparkH} viewBox="0 0 {sparkW} {sparkH}" class="inline-block" role="img" aria-label="Price sparkline">
										<path d={sparkPath} fill="none" stroke={sparkColor} stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
									</svg>
								{/if}
							</div>
						</div>
					</div>
				{/if}
			{/each}
		</div>
	</div>

	<!-- Footer bar -->
	<div class="flex items-center justify-between border-t border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3" style="height: 28px; min-height: 28px;">
		<span class="text-2xs text-[var(--text-tertiary)]">
			{results.length} result{results.length !== 1 ? 's' : ''}
		</span>
		<span class="text-2xs text-[var(--text-disabled)]">
			j/k navigate &middot; Enter expand
		</span>
	</div>
</div>
