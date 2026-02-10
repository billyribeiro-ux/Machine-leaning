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
		if (dir === 'bullish') return 'bg-[var(--bullish)]';
		if (dir === 'bearish') return 'bg-[var(--bearish)]';
		return 'bg-[var(--neutral)]';
	}

	function relativeTime(ts: number): string {
		const delta = Date.now() - ts;
		if (delta < 60_000) return 'just now';
		if (delta < 3_600_000) return Math.floor(delta / 60_000) + 'm ago';
		if (delta < 86_400_000) return Math.floor(delta / 3_600_000) + 'h ago';
		return Math.floor(delta / 86_400_000) + 'd ago';
	}

	// Sparkline for chart placeholder
	let chartPath = $derived(() => {
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

	let chartAreaPath = $derived(() => {
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

	let chartColor = $derived(() => {
		const data = result.sparklineData;
		if (!data || data.length < 2) return 'var(--text-tertiary)';
		const last = data[data.length - 1] ?? 0;
		const first = data[0] ?? 0;
		return last >= first ? 'var(--bullish)' : 'var(--bearish)';
	});

	let chartFillColor = $derived(() => {
		const data = result.sparklineData;
		if (!data || data.length < 2) return 'var(--text-tertiary)';
		const last = data[data.length - 1] ?? 0;
		const first = data[0] ?? 0;
		return last >= first ? 'var(--bullish-bg)' : 'var(--bearish-bg)';
	});
</script>

<div class="rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] {className}">
	<!-- Header -->
	<div class="flex items-center justify-between border-b border-[var(--border-subtle)] px-5 py-3">
		<div class="flex items-center gap-3">
			<span class="font-mono text-xl font-bold uppercase text-[var(--text-primary)]" style="letter-spacing: 0.03em;">
				{result.symbol}
			</span>
			<span class="text-sm text-[var(--text-tertiary)]">{result.name}</span>
			<span class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium {directionBadgeClass(result.direction)}">
				{result.direction}
			</span>
		</div>
		<div class="flex items-center gap-4 text-right">
			<div>
				<div class="mono-nums text-xl font-bold text-[var(--text-primary)]">{formatPrice(result.price)}</div>
				<div class="mono-nums text-sm font-medium {changeColor(result.changePercent)}">
					{formatPercent(result.changePercent)} ({result.change > 0 ? '+' : ''}{result.change.toFixed(2)})
				</div>
			</div>
		</div>
	</div>

	<!-- Two-column body -->
	<div class="grid grid-cols-1 gap-0 md:grid-cols-2">
		<!-- Left column: Key Metrics -->
		<div class="border-b border-[var(--border-subtle)] p-5 md:border-b-0 md:border-r">
			<h4 class="mb-3 text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">Key Metrics</h4>
			<div class="grid grid-cols-2 gap-x-6 gap-y-3">
				{#each keyMetrics as metric}
					<div>
						<div class="text-[10px] uppercase tracking-wider text-[var(--text-disabled)]">{metric.label}</div>
						<div class="mono-nums text-sm font-medium text-[var(--text-primary)]">{metric.value}</div>
					</div>
				{/each}
			</div>

			<!-- Strength & Signal -->
			<div class="mt-4 flex items-center gap-4 border-t border-[var(--border-subtle)] pt-3">
				<div>
					<div class="text-[10px] uppercase tracking-wider text-[var(--text-disabled)]">Signal</div>
					<span class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium leading-none {directionBadgeClass(result.direction)}">
						{result.signalName}
					</span>
				</div>
				<div>
					<div class="text-[10px] uppercase tracking-wider text-[var(--text-disabled)]">Strength</div>
					<span class="font-mono text-sm tracking-tight {strengthColor(result.strength)}" title="Strength: {result.strength}/5">
						{strengthDots(result.strength)}
					</span>
				</div>
				<div>
					<div class="text-[10px] uppercase tracking-wider text-[var(--text-disabled)]">Rel Volume</div>
					<span class="mono-nums text-sm font-medium {result.relativeVolume >= 2 ? 'text-[var(--warning)]' : 'text-[var(--text-secondary)]'}">
						{result.relativeVolume.toFixed(1)}x
					</span>
				</div>
			</div>
		</div>

		<!-- Right column: Chart + Signal History -->
		<div class="p-5">
			<!-- Chart placeholder -->
			<h4 class="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">Price Chart</h4>
			<div class="mb-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-base)] p-2">
				{#if chartPath()}
					<svg width="100%" height="120" viewBox="0 0 400 120" preserveAspectRatio="none" role="img" aria-label="Price chart for {result.symbol}">
						<!-- Area fill -->
						<path d={chartAreaPath()} fill={chartFillColor()} opacity="0.3" />
						<!-- Line -->
						<path d={chartPath()} fill="none" stroke={chartColor()} stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
					</svg>
				{:else}
					<div class="flex h-[120px] items-center justify-center text-sm text-[var(--text-disabled)]">
						No chart data available
					</div>
				{/if}
			</div>

			<!-- Signal History -->
			<h4 class="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">Signal History</h4>
			<div class="space-y-0">
				{#each signalHistory as signal, i}
					<div class="flex items-center gap-3 rounded-md px-2 py-1.5 transition-colors hover:bg-[var(--bg-overlay)]">
						<!-- Timeline dot + connector -->
						<div class="relative flex flex-col items-center">
							<div class="h-2 w-2 rounded-full {signalDotClass(signal.direction)}"></div>
							{#if i < signalHistory.length - 1}
								<div class="mt-0.5 h-3 w-px bg-[var(--border-subtle)]"></div>
							{/if}
						</div>

						<!-- Content -->
						<div class="flex flex-1 items-center justify-between min-w-0">
							<div class="flex items-center gap-2 min-w-0">
								<span class="text-sm text-[var(--text-primary)]">{signal.name}</span>
								<span class="font-mono text-[10px] tracking-tight {strengthColor(signal.strength)}">
									{strengthDots(signal.strength)}
								</span>
							</div>
							<span class="mono-nums text-2xs text-[var(--text-disabled)] flex-shrink-0">
								{relativeTime(signal.time)}
							</span>
						</div>
					</div>
				{/each}
			</div>
		</div>
	</div>

	<!-- Footer: metadata -->
	<div class="flex items-center justify-between border-t border-[var(--border-subtle)] px-5 py-2">
		<div class="flex items-center gap-3 text-2xs text-[var(--text-disabled)]">
			<span>Sector: {result.sector}</span>
			<span class="text-[var(--border-default)]">&middot;</span>
			<span>Category: {result.category}</span>
		</div>
		<span class="mono-nums text-2xs text-[var(--text-disabled)]">
			Last updated: {formatTimestamp(result.timestamp)}
		</span>
	</div>
</div>
