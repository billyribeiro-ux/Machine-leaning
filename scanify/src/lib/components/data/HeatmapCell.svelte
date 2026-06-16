<script lang="ts">
	interface Props {
		value: number;
		min: number;
		max: number;
		format?: string;
		class?: string;
	}

	let {
		value,
		min,
		max,
		format,
		class: className = ''
	}: Props = $props();

	let bgColor = $derived.by(() => {
		const range = max - min || 1;
		const normalized = Math.max(-1, Math.min(1, (2 * (value - min)) / range - 1));

		if (normalized > 0) {
			const intensity = normalized;
			const l = 0.18 + intensity * 0.12;
			const c = intensity * 0.14;
			return `oklch(${l} ${c} 145)`;
		} else if (normalized < 0) {
			const intensity = Math.abs(normalized);
			const l = 0.18 + intensity * 0.12;
			const c = intensity * 0.14;
			return `oklch(${l} ${c} 25)`;
		}
		return 'oklch(0.18 0 0)';
	});

	let textColor = $derived.by(() => {
		const range = max - min || 1;
		const normalized = Math.max(-1, Math.min(1, (2 * (value - min)) / range - 1));
		const absNorm = Math.abs(normalized);

		if (absNorm > 0.5) return 'oklch(0.92 0 0)';
		return 'oklch(0.72 0 0)';
	});

	let formattedValue = $derived.by(() => {
		if (value == null || isNaN(value)) return '--';

		if (format === 'percent') return value.toFixed(2) + '%';
		if (format === 'integer') return Math.round(value).toString();
		if (format === 'price') return '$' + value.toFixed(2);
		if (format === 'compact') {
			if (Math.abs(value) >= 1e9) return (value / 1e9).toFixed(1) + 'B';
			if (Math.abs(value) >= 1e6) return (value / 1e6).toFixed(1) + 'M';
			if (Math.abs(value) >= 1e3) return (value / 1e3).toFixed(1) + 'K';
			return value.toFixed(1);
		}
		return value.toFixed(2);
	});
</script>

<div
	class="heatmap-cell {className}"
	style="background-color: {bgColor}; color: {textColor};"
	title={String(value)}
>
	{formattedValue}
</div>

<style>
	.heatmap-cell {
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: var(--radius-sm);
		padding-inline: 8px;
		padding-block: 4px;
		font-family: var(--font-mono);
		font-size: var(--text-xs);
		font-variant-numeric: tabular-nums;
		transition: color 150ms, background-color 150ms;
	}
</style>
