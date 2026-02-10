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
		if (val > 0) return 'text-[var(--bullish)]';
		if (val < 0) return 'text-[var(--bearish)]';
		return 'text-[var(--text-tertiary)]';
	}

	function borderColor(dir: string, selected: boolean): string {
		if (selected) {
			if (dir === 'bullish') return 'border-[var(--bullish)]';
			if (dir === 'bearish') return 'border-[var(--bearish)]';
			return 'border-[var(--accent)]';
		}
		if (dir === 'bullish') return 'border-[var(--bullish-dim)]';
		if (dir === 'bearish') return 'border-[var(--bearish-dim)]';
		return 'border-[var(--border-default)]';
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

	// Sparkline SVG path computation
	let sparklinePath = $derived(() => {
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

	let sparklineColor = $derived(() => {
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
	class="group w-full rounded-lg border bg-[var(--bg-surface)] p-3.5 text-left transition-all duration-150 hover:bg-[var(--bg-elevated)]
		{borderColor(result.direction, isSelected)}
		{glowClass(result.direction, isSelected)}
		{className}"
	onclick={handleClick}
	aria-selected={isSelected}
	role="option"
>
	<!-- Top row: Ticker + Price + Change -->
	<div class="flex items-start justify-between gap-2">
		<div class="min-w-0">
			<div class="font-mono text-lg font-bold uppercase text-[var(--text-primary)]" style="letter-spacing: 0.02em;">
				{result.symbol}
			</div>
			<div class="truncate text-xs text-[var(--text-tertiary)]" style="max-width: 140px;">
				{result.name}
			</div>
		</div>
		<div class="text-right flex-shrink-0">
			<div class="mono-nums text-base font-semibold text-[var(--text-primary)]">
				{formatPrice(result.price)}
			</div>
			<div class="mono-nums text-sm font-medium {changeColor(result.changePercent)}">
				{formatPercent(result.changePercent)}
			</div>
		</div>
	</div>

	<!-- Signal badge row -->
	<div class="mt-2.5 flex items-center gap-2">
		<span class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium leading-none {signalBadgeClass(result.direction)}">
			{result.signalName}
		</span>
		<span class="font-mono text-[10px] tracking-tight {strengthColor(result.strength)}" title="Strength: {result.strength}/5">
			{strengthDots(result.strength)}
		</span>
	</div>

	<!-- Sparkline -->
	{#if sparklinePath()}
		<div class="mt-2.5">
			<svg width="120" height="32" viewBox="0 0 120 32" class="w-full" preserveAspectRatio="none" role="img" aria-label="Price trend">
				<path
					d={sparklinePath()}
					fill="none"
					stroke={sparklineColor()}
					stroke-width="1.5"
					stroke-linecap="round"
					stroke-linejoin="round"
				/>
			</svg>
		</div>
	{/if}

	<!-- Bottom row: Volume + RelVol -->
	<div class="mt-2.5 flex items-center justify-between border-t border-[var(--border-subtle)] pt-2">
		<div class="flex items-center gap-3">
			<div>
				<div class="text-[10px] uppercase text-[var(--text-disabled)]">Vol</div>
				<div class="mono-nums text-xs text-[var(--text-secondary)]">{formatVolume(result.volume)}</div>
			</div>
			<div>
				<div class="text-[10px] uppercase text-[var(--text-disabled)]">RVol</div>
				<div class="mono-nums text-xs font-medium {result.relativeVolume >= 2 ? 'text-[var(--warning)]' : 'text-[var(--text-secondary)]'}">
					{result.relativeVolume.toFixed(1)}x
				</div>
			</div>
		</div>
		<span class="text-[10px] text-[var(--text-disabled)]">{result.sector}</span>
	</div>
</button>
