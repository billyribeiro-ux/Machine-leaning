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
		isSelected?: boolean;
		onclick?: (result: ScanResult) => void;
		class?: string;
	}

	let { result, isSelected = false, onclick: onclickHandler, class: className = '' }: Props = $props();

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

	function changeColor(val: number): string {
		if (val > 0) return 'change-bullish';
		if (val < 0) return 'change-bearish';
		return 'change-neutral';
	}

	function borderColor(dir: string, selected: boolean): string {
		if (selected) {
			if (dir === 'bullish') return 'border-bullish-selected';
			if (dir === 'bearish') return 'border-bearish-selected';
			return 'border-accent-selected';
		}
		if (dir === 'bullish') return 'border-bullish-dim';
		if (dir === 'bearish') return 'border-bearish-dim';
		return 'border-default';
	}

	function glowClass(dir: string, selected: boolean): string {
		if (!selected) return '';
		if (dir === 'bullish') return 'glow-ring-bullish';
		if (dir === 'bearish') return 'glow-ring-bearish';
		return 'glow-ring-accent';
	}

	function signalBadgeClass(dir: string): string {
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
		return map[s] || 'strength-default';
	}

	// Sparkline SVG path computation
	let sparklinePath = $derived.by(() => {
		const data = result.sparklineData;
		if (!data || data.length < 2) return '';
		const w = 120;
		const h = 32;
		const pad = 2;
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

	let sparklineColor = $derived.by(() => {
		const data = result.sparklineData;
		if (!data || data.length < 2) return 'var(--text-tertiary)';
		const last = data[data.length - 1] ?? 0;
		const first = data[0] ?? 0;
		return last >= first ? 'var(--bullish)' : 'var(--bearish)';
	});

	function handleClick() {
		onclickHandler?.(result);
	}
</script>

<button
	type="button"
	class="scan-card {borderColor(result.direction, isSelected)} {glowClass(result.direction, isSelected)} {className}"
	onclick={handleClick}
	aria-selected={isSelected}
	role="option"
>
	<!-- Top row: Ticker + Price + Change -->
	<div class="top-row">
		<div class="ticker-info">
			<div class="ticker-symbol">
				{result.symbol}
			</div>
			<div class="ticker-name">
				{result.name}
			</div>
		</div>
		<div class="price-info">
			<div class="price-value mono-nums">
				{formatPrice(result.price)}
			</div>
			<div class="price-change mono-nums {changeColor(result.changePercent)}">
				{formatPercent(result.changePercent)}
			</div>
		</div>
	</div>

	<!-- Signal badge row -->
	<div class="signal-row">
		<span class="signal-badge {signalBadgeClass(result.direction)}">
			{result.signalName}
		</span>
		<span class="strength-indicator {strengthColor(result.strength)}" title="Strength: {result.strength}/5">
			{strengthDots(result.strength)}
		</span>
	</div>

	<!-- Sparkline -->
	{#if sparklinePath}
		<div class="sparkline-container">
			<svg width="120" height="32" viewBox="0 0 120 32" class="sparkline-svg" preserveAspectRatio="none" role="img" aria-label="Price trend">
				<path
					d={sparklinePath}
					fill="none"
					stroke={sparklineColor}
					stroke-width="1.5"
					stroke-linecap="round"
					stroke-linejoin="round"
				/>
			</svg>
		</div>
	{/if}

	<!-- Bottom row: Volume + RelVol -->
	<div class="bottom-row">
		<div class="volume-group">
			<div>
				<div class="volume-label">Vol</div>
				<div class="volume-value mono-nums">{formatVolume(result.volume)}</div>
			</div>
			<div>
				<div class="volume-label">RVol</div>
				<div class="rvol-value mono-nums {result.relativeVolume >= 2 ? 'rvol-high' : 'rvol-normal'}">
					{result.relativeVolume.toFixed(1)}x
				</div>
			</div>
		</div>
		<span class="sector-label">{result.sector}</span>
	</div>
</button>

<style>
	/* ── Card container ── */
	.scan-card {
		display: flex;
		flex-direction: column;
		width: 100%;
		border-radius: var(--radius-lg);
		border: 1px solid;
		background-color: var(--bg-surface);
		padding: 14px;
		text-align: left;
		transition: all 150ms;
		cursor: pointer;
	}

	.scan-card:hover {
		background-color: var(--bg-elevated);
	}

	/* ── Border color variants ── */
	.scan-card.border-bullish-selected {
		border-color: var(--bullish);
	}
	.scan-card.border-bearish-selected {
		border-color: var(--bearish);
	}
	.scan-card.border-accent-selected {
		border-color: var(--accent);
	}
	.scan-card.border-bullish-dim {
		border-color: var(--bullish-dim);
	}
	.scan-card.border-bearish-dim {
		border-color: var(--bearish-dim);
	}
	.scan-card.border-default {
		border-color: var(--border-default);
	}

	/* ── Glow ring variants ── */
	.scan-card :global(.glow-ring-bullish) {
		/* handled by global styles or keep as-is */
	}
	.scan-card.glow-ring-bullish {
		/* preserve existing glow-ring-bullish global class */
	}
	.scan-card.glow-ring-bearish {
		/* preserve existing glow-ring-bearish global class */
	}
	.scan-card.glow-ring-accent {
		/* preserve existing glow-ring-accent global class */
	}

	/* ── Top row ── */
	.top-row {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 8px;
	}

	.ticker-info {
		min-width: 0;
	}

	.ticker-symbol {
		font-family: var(--font-mono);
		font-size: var(--text-lg);
		font-weight: 700;
		text-transform: uppercase;
		color: var(--text-primary);
		letter-spacing: 0.02em;
	}

	.ticker-name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: var(--text-xs);
		color: var(--text-tertiary);
		max-width: 140px;
	}

	.price-info {
		text-align: right;
		flex-shrink: 0;
	}

	.price-value {
		font-size: var(--text-base);
		font-weight: 600;
		color: var(--text-primary);
	}

	.price-change {
		font-size: var(--text-sm);
		font-weight: 500;
	}

	/* ── Change color variants ── */
	.change-bullish {
		color: var(--bullish);
	}
	.change-bearish {
		color: var(--bearish);
	}
	.change-neutral {
		color: var(--text-tertiary);
	}

	/* ── Signal badge row ── */
	.signal-row {
		margin-top: 10px;
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.signal-badge {
		display: inline-flex;
		align-items: center;
		border-radius: var(--radius-full);
		padding: 2px 8px;
		font-size: 10px;
		font-weight: 500;
		line-height: 1;
	}

	.strength-indicator {
		font-family: var(--font-mono);
		font-size: 10px;
		letter-spacing: -0.01em;
	}

	/* ── Strength color variants ── */
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
	.strength-default {
		color: var(--text-tertiary);
	}

	/* ── Sparkline ── */
	.sparkline-container {
		margin-top: 10px;
	}

	.sparkline-svg {
		width: 100%;
	}

	/* ── Bottom row ── */
	.bottom-row {
		margin-top: 10px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		border-top: 1px solid var(--border-subtle);
		padding-top: 8px;
	}

	.volume-group {
		display: flex;
		align-items: center;
		gap: 12px;
	}

	.volume-label {
		font-size: 10px;
		text-transform: uppercase;
		color: var(--text-disabled);
	}

	.volume-value {
		font-size: var(--text-xs);
		color: var(--text-secondary);
	}

	.rvol-value {
		font-size: var(--text-xs);
		font-weight: 500;
	}

	.rvol-normal {
		color: var(--text-secondary);
	}

	.rvol-high {
		color: var(--warning);
	}

	.sector-label {
		font-size: 10px;
		color: var(--text-disabled);
	}
</style>
