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
	class="relative inline-flex items-center gap-2 {className}"
	style="width: {maxWidth + 40}px;"
>
	<div
		class="relative h-4 overflow-hidden rounded-sm"
		style="width: {maxWidth}px;"
	>
		<div class="absolute inset-0 rounded-sm bg-[oklch(0.18_0.005_270)]"></div>
		<div
			class="absolute inset-y-0 left-0 rounded-sm transition-all duration-300 ease-out"
			style="width: {barWidth}px; background-color: {barColor};"
		></div>
	</div>
	<span
		class="whitespace-nowrap font-mono text-xs tabular-nums"
		style="color: {barColor}; font-variant-numeric: tabular-nums;"
	>
		{ratioText}
	</span>
</div>
