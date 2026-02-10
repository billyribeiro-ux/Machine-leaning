<script lang="ts">
	interface Props {
		data: number[];
		width?: number;
		height?: number;
		color?: string;
		showLastPoint?: boolean;
		class?: string;
	}

	let {
		data,
		width = 100,
		height = 24,
		color,
		showLastPoint = false,
		class: className = ''
	}: Props = $props();

	let resolvedColor = $derived(() => {
		if (color) return color;
		if (!data || data.length < 2) return 'oklch(0.60 0 0)';
		return data[data.length - 1] >= data[0]
			? 'oklch(0.65 0.15 145)'
			: 'oklch(0.65 0.18 25)';
	});

	let pathD = $derived(() => {
		if (!data || data.length < 2) return '';

		const min = Math.min(...data);
		const max = Math.max(...data);
		const range = max - min || 1;

		const padding = 2;
		const drawWidth = width - padding * 2;
		const drawHeight = height - padding * 2;

		const points = data.map((val, i) => {
			const x = padding + (i / (data.length - 1)) * drawWidth;
			const y = padding + drawHeight - ((val - min) / range) * drawHeight;
			return { x, y };
		});

		return points
			.map((p, i) => (i === 0 ? `M ${p.x} ${p.y}` : `L ${p.x} ${p.y}`))
			.join(' ');
	});

	let lastPoint = $derived(() => {
		if (!data || data.length < 2) return null;

		const min = Math.min(...data);
		const max = Math.max(...data);
		const range = max - min || 1;

		const padding = 2;
		const drawWidth = width - padding * 2;
		const drawHeight = height - padding * 2;

		const lastVal = data[data.length - 1];
		return {
			x: padding + drawWidth,
			y: padding + drawHeight - ((lastVal - min) / range) * drawHeight
		};
	});
</script>

<svg
	{width}
	{height}
	viewBox="0 0 {width} {height}"
	class="inline-block align-middle {className}"
	role="img"
	aria-label="Sparkline chart"
>
	{#if pathD()}
		<path
			d={pathD()}
			fill="none"
			stroke={resolvedColor()}
			stroke-width="1.5"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		{#if showLastPoint && lastPoint()}
			<circle
				cx={lastPoint()?.x}
				cy={lastPoint()?.y}
				r="2.5"
				fill={resolvedColor()}
			/>
			<circle
				cx={lastPoint()?.x}
				cy={lastPoint()?.y}
				r="4"
				fill={resolvedColor()}
				opacity="0.3"
			/>
		{/if}
	{/if}
</svg>
