<script lang="ts">
	interface Props {
		value: number;
		average: number;
		maxWidth?: number;
		class?: string;
	}

	let {
		value,
		average,
		maxWidth = 80,
		class: className = ''
	}: Props = $props();

	let ratio = $derived(average > 0 ? value / average : 0);

	let barWidth = $derived.by(() => {
		const pct = ratio * 50;
		return Math.min(pct, maxWidth);
	});

	let barColor = $derived.by(() => {
		if (ratio >= 2) return 'oklch(0.72 0.16 145)';
		if (ratio >= 1.5) return 'oklch(0.58 0.12 145)';
		if (ratio >= 1) return 'oklch(0.50 0.04 250)';
		return 'oklch(0.35 0.02 250)';
	});

	let ratioText = $derived.by(() => {
		if (ratio === 0) return '0x';
		return ratio.toFixed(1) + 'x';
	});
</script>

<div
	class="volume-bar {className}"
	style="width: {maxWidth + 40}px;"
>
	<div
		class="bar-track"
		style="width: {maxWidth}px;"
	>
		<div class="bar-bg"></div>
		<div
			class="bar-fill"
			style="width: {barWidth}px; background-color: {barColor};"
		></div>
	</div>
	<span
		class="bar-label"
		style="color: {barColor}; font-variant-numeric: tabular-nums;"
	>
		{ratioText}
	</span>
</div>

<style>
	.volume-bar {
		position: relative;
		display: inline-flex;
		align-items: center;
		gap: 8px;
	}

	.bar-track {
		position: relative;
		height: 16px;
		overflow: hidden;
		border-radius: var(--radius-sm);
	}

	.bar-bg {
		position: absolute;
		inset: 0;
		border-radius: var(--radius-sm);
		background-color: oklch(0.18 0.005 270);
	}

	.bar-fill {
		position: absolute;
		inset-block: 0;
		left: 0;
		border-radius: var(--radius-sm);
		transition: all 300ms ease-out;
	}

	.bar-label {
		white-space: nowrap;
		font-family: var(--font-mono);
		font-size: var(--text-xs);
		font-variant-numeric: tabular-nums;
	}
</style>
