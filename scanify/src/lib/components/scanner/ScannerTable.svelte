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
		return sortDir === 'asc' ? ' ▲' : ' ▼';
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
			1: 'color-strength-1',
			2: 'color-strength-2',
			3: 'color-strength-3',
			4: 'color-strength-4',
			5: 'color-strength-5',
		};
		return map[s] || 'color-tertiary';
	}

	function relVolColor(rv: number): string {
		if (rv >= 3) return 'color-warning-bright';
		if (rv >= 2) return 'color-warning';
		if (rv >= 1.5) return 'color-bullish';
		return 'color-secondary';
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
		{ key: 'symbol', label: 'Symbol', align: 'left' as const, widthClass: 'col-symbol' },
		{ key: 'price', label: 'Price', align: 'right' as const, widthClass: 'col-price' },
		{ key: 'changePercent', label: 'Change%', align: 'right' as const, widthClass: 'col-change' },
		{ key: 'signalName', label: 'Signal', align: 'left' as const, widthClass: 'col-signal' },
		{ key: 'strength', label: 'Strength', align: 'center' as const, widthClass: 'col-strength' },
		{ key: 'volume', label: 'Volume', align: 'right' as const, widthClass: 'col-volume' },
		{ key: 'relativeVolume', label: 'RelVol', align: 'right' as const, widthClass: 'col-relvol' },
		{ key: 'sector', label: 'Sector', align: 'left' as const, widthClass: 'col-sector' },
		{ key: 'timestamp', label: 'Time', align: 'right' as const, widthClass: 'col-time' },
	];
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
	class="table-container {className}"
	onkeydown={handleKeydown}
	tabindex="0"
	role="grid"
	aria-label="Scanner results table"
>
	<!-- Fixed header -->
	<div class="table-header">
		{#each columns as col}
			<button
				class="header-cell {col.widthClass} {col.align === 'right' ? 'align-right' : col.align === 'center' ? 'align-center' : 'align-left'}"
				onclick={() => toggleSort(col.key)}
				type="button"
			>
				{col.label}{sortIndicator(col.key)}
			</button>
		{/each}
	</div>

	<!-- Scrollable body with virtual scrolling -->
	<div
		class="table-body"
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
					class="table-row {isSelected ? 'row-selected' : isEven ? 'row-even' : 'row-odd'}"
					style="top: {actualIndex * ROW_HEIGHT}px; height: {ROW_HEIGHT}px;"
					onclick={() => selectRow(result, actualIndex)}
					ondblclick={() => toggleExpand(result)}
					role="row"
					aria-selected={isSelected}
					aria-rowindex={actualIndex + 1}
				>
					<!-- Symbol -->
					<div class="cell col-symbol">
						<span class="symbol-text">
							{result.symbol}
						</span>
					</div>

					<!-- Price -->
					<div class="cell col-price align-right">
						<span class="mono-nums price-text">
							{formatPrice(result.price)}
						</span>
					</div>

					<!-- Change% -->
					<div class="cell col-change align-right">
						<span class="mono-nums change-text {changeColor(result.changePercent)}">
							{formatPercent(result.changePercent)}
						</span>
					</div>

					<!-- Signal -->
					<div class="cell col-signal">
						<span class="signal-badge {directionBadgeClass(result.direction)}">
							{result.signalName}
						</span>
					</div>

					<!-- Strength (dots) -->
					<div class="cell col-strength align-center">
						<span class="strength-dots {strengthColor(result.strength)}" title="Strength: {result.strength}/5">
							{strengthDots(result.strength)}
						</span>
					</div>

					<!-- Volume -->
					<div class="cell col-volume align-right">
						<span class="mono-nums volume-text">
							{formatVolume(result.volume)}
						</span>
					</div>

					<!-- RelVol -->
					<div class="cell col-relvol align-right">
						<span class="mono-nums relvol-text {relVolColor(result.relativeVolume)}">
							{result.relativeVolume.toFixed(1)}x
						</span>
					</div>

					<!-- Sector -->
					<div class="cell col-sector sector-cell">
						<span class="sector-text">
							{result.sector}
						</span>
					</div>

					<!-- Time -->
					<div class="cell col-time align-right">
						<span class="mono-nums time-text">
							{formatTimestamp(result.timestamp)}
						</span>
					</div>
				</div>

				<!-- Expanded detail row -->
				{#if isExpanded}
					<div
						class="expanded-row"
						style="top: {(actualIndex + 1) * ROW_HEIGHT}px;"
					>
						<div class="expanded-grid">
							<!-- Left column: detail info -->
							<div class="expanded-col">
								<div class="expanded-header">
									<span class="expanded-symbol">{result.symbol}</span>
									<span class="expanded-name">{result.name}</span>
								</div>
								<div class="detail-grid">
									<div>
										<div class="detail-label">Price</div>
										<div class="mono-nums detail-value-primary">{formatPrice(result.price)}</div>
									</div>
									<div>
										<div class="detail-label">Change</div>
										<div class="mono-nums {changeColor(result.changePercent)}">{formatPercent(result.changePercent)}</div>
									</div>
									<div>
										<div class="detail-label">Volume</div>
										<div class="mono-nums detail-value-secondary">{formatVolume(result.volume)}</div>
									</div>
								</div>
							</div>

							<!-- Right column: sparkline + signal -->
							<div class="expanded-col">
								<div class="expanded-signal-row">
									<span class="signal-badge {directionBadgeClass(result.direction)}">
										{result.direction}
									</span>
									<span class="expanded-category">Category: {result.category}</span>
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
									<svg width={sparkW} height={sparkH} viewBox="0 0 {sparkW} {sparkH}" class="sparkline-svg" role="img" aria-label="Price sparkline">
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
	<div class="table-footer">
		<span class="footer-text">
			{results.length} result{results.length !== 1 ? 's' : ''}
		</span>
		<span class="footer-hint">
			j/k navigate &middot; Enter expand
		</span>
	</div>
</div>

<style>
	/* Container */
	.table-container {
		display: flex;
		flex-direction: column;
		overflow: hidden;
		border-radius: var(--radius-lg);
		border: 1px solid var(--border-subtle);
		background-color: var(--bg-surface);
	}

	/* Header */
	.table-header {
		display: flex;
		align-items: center;
		border-bottom: 1px solid var(--border-default);
		background-color: var(--bg-elevated);
		padding-inline: 4px;
		height: 36px;
		min-height: 36px;
	}

	.header-cell {
		flex-shrink: 0;
		padding-inline: 8px;
		padding-block: 6px;
		font-size: var(--text-2xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-tertiary);
		transition: color 150ms, background-color 150ms, border-color 150ms;
		user-select: none;
		background: none;
		border: none;
		cursor: pointer;
	}

	.header-cell:hover {
		color: var(--text-primary);
	}

	/* Body */
	.table-body {
		flex: 1;
		overflow-y: auto;
	}

	/* Row */
	.table-row {
		position: absolute;
		left: 0;
		right: 0;
		display: flex;
		align-items: center;
		padding-inline: 4px;
		transition: color 75ms, background-color 75ms, border-color 75ms;
		cursor: pointer;
	}

	.row-selected {
		background-color: var(--accent-bg);
		border-left: 2px solid var(--accent);
	}

	.row-even {
		background-color: transparent;
	}

	.row-odd {
		background-color: oklch(0.12 0.02 260);
	}

	.row-even:hover,
	.row-odd:hover {
		background-color: var(--hover-overlay);
		border-left: 2px solid var(--border-strong);
	}

	/* Cell base */
	.cell {
		flex-shrink: 0;
		padding-inline: 8px;
	}

	/* Column widths */
	.col-symbol {
		width: 100px;
	}

	.col-price {
		width: 90px;
	}

	.col-change {
		width: 85px;
	}

	.col-signal {
		width: 120px;
	}

	.col-strength {
		width: 80px;
	}

	.col-volume {
		width: 85px;
	}

	.col-relvol {
		width: 70px;
	}

	.col-sector {
		width: 100px;
	}

	.col-time {
		width: 70px;
	}

	/* Alignment */
	.align-right {
		text-align: right;
	}

	.align-center {
		text-align: center;
	}

	.align-left {
		text-align: left;
	}

	/* Cell content styles */
	.symbol-text {
		font-family: var(--font-mono);
		font-size: var(--text-sm);
		font-weight: 600;
		text-transform: uppercase;
		color: var(--text-primary);
		letter-spacing: 0.02em;
	}

	.price-text {
		font-size: var(--text-sm);
		color: var(--text-primary);
	}

	.change-text {
		font-size: var(--text-sm);
		font-weight: 500;
	}

	.signal-badge {
		display: inline-flex;
		align-items: center;
		border-radius: var(--radius-full);
		padding-inline: 8px;
		padding-block: 2px;
		font-size: 10px;
		font-weight: 500;
		line-height: 1;
	}

	.strength-dots {
		font-family: var(--font-mono);
		font-size: var(--text-xs);
		letter-spacing: -0.01em;
	}

	.volume-text {
		font-size: var(--text-sm);
		color: var(--text-secondary);
	}

	.relvol-text {
		font-size: var(--text-sm);
		font-weight: 500;
	}

	.sector-cell {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.sector-text {
		font-size: var(--text-xs);
		color: var(--text-tertiary);
	}

	.time-text {
		font-size: var(--text-xs);
		color: var(--text-tertiary);
	}

	/* Dynamic color classes */
	.color-bullish {
		color: var(--bullish);
	}

	.color-bearish {
		color: var(--bearish);
	}

	.color-tertiary {
		color: var(--text-tertiary);
	}

	.color-secondary {
		color: var(--text-secondary);
	}

	.color-warning-bright {
		color: var(--warning-bright);
	}

	.color-warning {
		color: var(--warning);
	}

	.color-strength-1 {
		color: var(--strength-1);
	}

	.color-strength-2 {
		color: var(--strength-2);
	}

	.color-strength-3 {
		color: var(--strength-3);
	}

	.color-strength-4 {
		color: var(--strength-4);
	}

	.color-strength-5 {
		color: var(--strength-5);
	}

	/* Expanded row */
	.expanded-row {
		position: absolute;
		left: 0;
		right: 0;
		border-top: 1px solid var(--border-default);
		border-bottom: 1px solid var(--border-default);
		background-color: var(--bg-elevated);
		padding: 12px 16px;
	}

	.expanded-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 16px;
		font-size: var(--text-sm);
	}

	.expanded-col > * + * {
		margin-top: 8px;
	}

	.expanded-header {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.expanded-symbol {
		font-family: var(--font-mono);
		font-size: var(--text-base);
		font-weight: 700;
		color: var(--text-primary);
	}

	.expanded-name {
		color: var(--text-tertiary);
	}

	.detail-grid {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 12px;
	}

	.detail-label {
		font-size: var(--text-2xs);
		text-transform: uppercase;
		color: var(--text-tertiary);
	}

	.detail-value-primary {
		color: var(--text-primary);
	}

	.detail-value-secondary {
		color: var(--text-secondary);
	}

	.expanded-signal-row {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.expanded-category {
		font-size: var(--text-xs);
		color: var(--text-tertiary);
	}

	.sparkline-svg {
		display: inline-block;
	}

	/* Footer */
	.table-footer {
		display: flex;
		align-items: center;
		justify-content: space-between;
		border-top: 1px solid var(--border-subtle);
		background-color: var(--bg-elevated);
		padding-inline: 12px;
		height: 28px;
		min-height: 28px;
	}

	.footer-text {
		font-size: var(--text-2xs);
		color: var(--text-tertiary);
	}

	.footer-hint {
		font-size: var(--text-2xs);
		color: var(--text-disabled);
	}
</style>
