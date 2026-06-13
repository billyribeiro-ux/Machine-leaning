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
		result: ScanResult;
		class?: string;
	}

	let { result, class: className = '' }: Props = $props();

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
		if (val >= 1_000_000_000) return (val / 1_000_000_000).toFixed(2) + 'B';
		if (val >= 1_000_000) return (val / 1_000_000).toFixed(2) + 'M';
		if (val >= 1_000) return (val / 1_000).toFixed(2) + 'K';
		return val.toFixed(0);
	}

	function formatMarketCap(val: number): string {
		if (val >= 1_000_000_000_000) return '$' + (val / 1_000_000_000_000).toFixed(2) + 'T';
		if (val >= 1_000_000_000) return '$' + (val / 1_000_000_000).toFixed(2) + 'B';
		if (val >= 1_000_000) return '$' + (val / 1_000_000).toFixed(2) + 'M';
		return '$' + val.toLocaleString('en-US');
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

	function formatTimestamp(ts: number): string {
		const d = new Date(ts);
		return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
	}

	// Placeholder key metrics
	let keyMetrics = $derived([
		{ label: 'Market Cap', value: formatMarketCap(result.price * 250_000_000) },
		{ label: 'Avg Volume', value: formatVolume(result.volume / (result.relativeVolume || 1)) },
		{ label: '52W High', value: formatPrice(result.price * 1.35) },
		{ label: '52W Low', value: formatPrice(result.price * 0.65) },
		{ label: 'Float', value: formatVolume(180_000_000) },
		{ label: 'Short Interest', value: '8.4%' },
	]);

	// Mock signal history
	let signalHistory = $derived([
		{
			name: result.signalName,
			direction: result.direction,
			strength: result.strength,
			time: result.timestamp,
		},
		{
			name: 'RSI Reversal',
			direction: 'bullish' as const,
			strength: 3,
			time: result.timestamp - 1_800_000,
		},
		{
			name: 'Volume Spike',
			direction: result.direction,
			strength: 4,
			time: result.timestamp - 5_400_000,
		},
		{
			name: 'VWAP Cross',
			direction: 'bearish' as const,
			strength: 2,
			time: result.timestamp - 14_400_000,
		},
		{
			name: 'Momentum Shift',
			direction: 'neutral' as const,
			strength: 3,
			time: result.timestamp - 28_800_000,
		},
	]);

	function signalDotClass(dir: string): string {
		if (dir === 'bullish') return 'dot-bullish';
		if (dir === 'bearish') return 'dot-bearish';
		return 'dot-neutral';
	}

	function relativeTime(ts: number): string {
		const delta = Date.now() - ts;
		if (delta < 60_000) return 'just now';
		if (delta < 3_600_000) return Math.floor(delta / 60_000) + 'm ago';
		if (delta < 86_400_000) return Math.floor(delta / 3_600_000) + 'h ago';
		return Math.floor(delta / 86_400_000) + 'd ago';
	}

	// Sparkline for chart placeholder
	let chartPath = $derived.by(() => {
		const data = result.sparklineData;
		if (!data || data.length < 2) return '';
		const w = 400;
		const h = 120;
		const pad = 4;
		const min = Math.min(...data);
		const max = Math.max(...data);
		const range = max - min || 1;
		return data
			.map((v, i) => {
				const x = pad + (i / (data.length - 1)) * (w - pad * 2);
				const y = pad + (h - pad * 2) - ((v - min) / range) * (h - pad * 2);
				return (i === 0 ? 'M ' : 'L ') + x + ' ' + y;
			})
			.join(' ');
	});

	let chartAreaPath = $derived.by(() => {
		const data = result.sparklineData;
		if (!data || data.length < 2) return '';
		const w = 400;
		const h = 120;
		const pad = 4;
		const min = Math.min(...data);
		const max = Math.max(...data);
		const range = max - min || 1;
		const points = data
			.map((v, i) => {
				const x = pad + (i / (data.length - 1)) * (w - pad * 2);
				const y = pad + (h - pad * 2) - ((v - min) / range) * (h - pad * 2);
				return x + ' ' + y;
			})
			.join(' L ');
		const lastX = pad + (w - pad * 2);
		const firstX = pad;
		return 'M ' + points + ' L ' + lastX + ' ' + h + ' L ' + firstX + ' ' + h + ' Z';
	});

	let chartColor = $derived.by(() => {
		const data = result.sparklineData;
		if (!data || data.length < 2) return 'var(--text-tertiary)';
		const last = data[data.length - 1] ?? 0;
		const first = data[0] ?? 0;
		return last >= first ? 'var(--bullish)' : 'var(--bearish)';
	});

	let chartFillColor = $derived.by(() => {
		const data = result.sparklineData;
		if (!data || data.length < 2) return 'var(--text-tertiary)';
		const last = data[data.length - 1] ?? 0;
		const first = data[0] ?? 0;
		return last >= first ? 'var(--bullish-bg)' : 'var(--bearish-bg)';
	});
</script>

<div class="scan-detail-root {className}">
	<!-- Header -->
	<div class="header">
		<div class="header-left">
			<span class="symbol-label">
				{result.symbol}
			</span>
			<span class="name-label">{result.name}</span>
			<span class="direction-badge {directionBadgeClass(result.direction)}">
				{result.direction}
			</span>
		</div>
		<div class="header-right">
			<div>
				<div class="price-value mono-nums">{formatPrice(result.price)}</div>
				<div class="change-value mono-nums {changeColor(result.changePercent)}">
					{formatPercent(result.changePercent)} ({result.change > 0 ? '+' : ''}{result.change.toFixed(2)})
				</div>
			</div>
		</div>
	</div>

	<!-- Two-column body -->
	<div class="body-grid">
		<!-- Left column: Key Metrics -->
		<div class="left-column">
			<h4 class="section-heading">Key Metrics</h4>
			<div class="metrics-grid">
				{#each keyMetrics as metric}
					<div>
						<div class="metric-label">{metric.label}</div>
						<div class="metric-value mono-nums">{metric.value}</div>
					</div>
				{/each}
			</div>

			<!-- Strength & Signal -->
			<div class="signal-strip">
				<div>
					<div class="metric-label">Signal</div>
					<span class="signal-badge {directionBadgeClass(result.direction)}">
						{result.signalName}
					</span>
				</div>
				<div>
					<div class="metric-label">Strength</div>
					<span class="strength-display {strengthColor(result.strength)}" title="Strength: {result.strength}/5">
						{strengthDots(result.strength)}
					</span>
				</div>
				<div>
					<div class="metric-label">Rel Volume</div>
					<span class="rel-volume mono-nums {result.relativeVolume >= 2 ? 'vol-warning' : 'vol-normal'}">
						{result.relativeVolume.toFixed(1)}x
					</span>
				</div>
			</div>
		</div>

		<!-- Right column: Chart + Signal History -->
		<div class="right-column">
			<!-- Chart placeholder -->
			<h4 class="section-heading chart-heading">Price Chart</h4>
			<div class="chart-container">
				{#if chartPath}
					<svg width="100%" height="120" viewBox="0 0 400 120" preserveAspectRatio="none" role="img" aria-label="Price chart for {result.symbol}">
						<!-- Area fill -->
						<path d={chartAreaPath} fill={chartFillColor} opacity="0.3" />
						<!-- Line -->
						<path d={chartPath} fill="none" stroke={chartColor} stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
					</svg>
				{:else}
					<div class="chart-empty">
						No chart data available
					</div>
				{/if}
			</div>

			<!-- Signal History -->
			<h4 class="section-heading signal-history-heading">Signal History</h4>
			<div class="signal-history-list">
				{#each signalHistory as signal, i}
					<div class="signal-row">
						<!-- Timeline dot + connector -->
						<div class="timeline-column">
							<div class="timeline-dot {signalDotClass(signal.direction)}"></div>
							{#if i < signalHistory.length - 1}
								<div class="timeline-connector"></div>
							{/if}
						</div>

						<!-- Content -->
						<div class="signal-content">
							<div class="signal-info">
								<span class="signal-name">{signal.name}</span>
								<span class="signal-strength {strengthColor(signal.strength)}">
									{strengthDots(signal.strength)}
								</span>
							</div>
							<span class="signal-time mono-nums">
								{relativeTime(signal.time)}
							</span>
						</div>
					</div>
				{/each}
			</div>
		</div>
	</div>

	<!-- Footer: metadata -->
	<div class="footer">
		<div class="footer-meta">
			<span>Sector: {result.sector}</span>
			<span class="footer-separator">&middot;</span>
			<span>Category: {result.category}</span>
		</div>
		<span class="footer-timestamp mono-nums">
			Last updated: {formatTimestamp(result.timestamp)}
		</span>
	</div>
</div>

<style>
	/* Root container */
	.scan-detail-root {
		border-radius: var(--radius-lg);
		border: 1px solid var(--border-default);
		background-color: var(--bg-surface);
	}

	/* ── Header ── */
	.header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		border-bottom: 1px solid var(--border-subtle);
		padding-inline: 20px;
		padding-block: 12px;
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: 12px;
	}

	.symbol-label {
		font-family: var(--font-mono);
		font-size: var(--text-xl);
		font-weight: 700;
		text-transform: uppercase;
		color: var(--text-primary);
		letter-spacing: 0.03em;
	}

	.name-label {
		font-size: var(--text-sm);
		color: var(--text-tertiary);
	}

	.direction-badge {
		display: inline-flex;
		align-items: center;
		border-radius: var(--radius-full);
		padding-inline: 8px;
		padding-block: 2px;
		font-size: 10px;
		font-weight: 500;
	}

	.header-right {
		display: flex;
		align-items: center;
		gap: 16px;
		text-align: right;
	}

	.price-value {
		font-size: var(--text-xl);
		font-weight: 700;
		color: var(--text-primary);
	}

	.change-value {
		font-size: var(--text-sm);
		font-weight: 500;
	}

	/* ── Dynamic color classes ── */
	.color-bullish {
		color: var(--bullish);
	}

	.color-bearish {
		color: var(--bearish);
	}

	.color-tertiary {
		color: var(--text-tertiary);
	}

	/* ── Badge variants ── */
	.badge-bullish {
		/* Inherits direction-badge or signal-badge base styles from context */
	}

	.badge-bearish {
		/* Inherits direction-badge or signal-badge base styles from context */
	}

	.badge-neutral {
		/* Inherits direction-badge or signal-badge base styles from context */
	}

	/* ── Strength color classes ── */
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

	/* ── Signal dot variants ── */
	.dot-bullish {
		background-color: var(--bullish);
	}

	.dot-bearish {
		background-color: var(--bearish);
	}

	.dot-neutral {
		background-color: var(--neutral);
	}

	/* ── Two-column body grid ── */
	.body-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: 0;
	}

	@media (min-width: 768px) {
		.body-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	/* ── Left column ── */
	.left-column {
		border-bottom: 1px solid var(--border-subtle);
		padding: 20px;
	}

	@media (min-width: 768px) {
		.left-column {
			border-bottom: none;
			border-right: 1px solid var(--border-subtle);
		}
	}

	.section-heading {
		margin-bottom: 12px;
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-tertiary);
	}

	.metrics-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		column-gap: 24px;
		row-gap: 12px;
	}

	.metric-label {
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-disabled);
	}

	.metric-value {
		font-size: var(--text-sm);
		font-weight: 500;
		color: var(--text-primary);
	}

	/* ── Signal strip ── */
	.signal-strip {
		margin-top: 16px;
		display: flex;
		align-items: center;
		gap: 16px;
		border-top: 1px solid var(--border-subtle);
		padding-top: 12px;
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

	.strength-display {
		font-family: var(--font-mono);
		font-size: var(--text-sm);
		letter-spacing: -0.01em;
	}

	.rel-volume {
		font-size: var(--text-sm);
		font-weight: 500;
	}

	.vol-warning {
		color: var(--warning);
	}

	.vol-normal {
		color: var(--text-secondary);
	}

	/* ── Right column ── */
	.right-column {
		padding: 20px;
	}

	.chart-heading {
		margin-bottom: 8px;
	}

	.chart-container {
		margin-bottom: 16px;
		border-radius: var(--radius-md);
		border: 1px solid var(--border-subtle);
		background-color: var(--bg-base);
		padding: 8px;
	}

	.chart-empty {
		display: flex;
		height: 120px;
		align-items: center;
		justify-content: center;
		font-size: var(--text-sm);
		color: var(--text-disabled);
	}

	.signal-history-heading {
		margin-bottom: 8px;
	}

	/* ── Signal history list ── */
	.signal-history-list {
		/* space-y-0: no extra spacing between children */
	}

	.signal-row {
		display: flex;
		align-items: center;
		gap: 12px;
		border-radius: var(--radius-md);
		padding-inline: 8px;
		padding-block: 6px;
		transition: color 150ms, background-color 150ms, border-color 150ms;
	}

	.signal-row:hover {
		background-color: var(--bg-overlay);
	}

	.timeline-column {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
	}

	.timeline-dot {
		height: 8px;
		width: 8px;
		border-radius: var(--radius-full);
	}

	.timeline-connector {
		margin-top: 2px;
		height: 12px;
		width: 1px;
		background-color: var(--border-subtle);
	}

	.signal-content {
		display: flex;
		flex: 1;
		align-items: center;
		justify-content: space-between;
		min-width: 0;
	}

	.signal-info {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}

	.signal-name {
		font-size: var(--text-sm);
		color: var(--text-primary);
	}

	.signal-strength {
		font-family: var(--font-mono);
		font-size: 10px;
		letter-spacing: -0.01em;
	}

	.signal-time {
		font-size: var(--text-2xs);
		color: var(--text-disabled);
		flex-shrink: 0;
	}

	/* ── Footer ── */
	.footer {
		display: flex;
		align-items: center;
		justify-content: space-between;
		border-top: 1px solid var(--border-subtle);
		padding-inline: 20px;
		padding-block: 8px;
	}

	.footer-meta {
		display: flex;
		align-items: center;
		gap: 12px;
		font-size: var(--text-2xs);
		color: var(--text-disabled);
	}

	.footer-separator {
		color: var(--border-default);
	}

	.footer-timestamp {
		font-size: var(--text-2xs);
		color: var(--text-disabled);
	}
</style>
