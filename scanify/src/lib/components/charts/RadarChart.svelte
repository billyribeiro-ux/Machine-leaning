<script lang="ts">
	interface RadarAxis {
		label: string;
		value: number;
		max: number;
	}

	interface Props {
		data: RadarAxis[];
		size?: number;
		title?: string;
	}

	let { data, size = 200, title = '' }: Props = $props();

	let hoveredIndex = $state<number | null>(null);

	// Layout
	const CENTER_X = $derived(size / 2);
	const CENTER_Y = $derived(size / 2 + (title ? 10 : 0));
	const RADIUS = $derived((size - 60) / 2);
	const TOTAL_HEIGHT = $derived(size + (title ? 24 : 0));

	const gridLevels = [0.25, 0.5, 0.75, 1.0];

	function getAngle(index: number): number {
		// Start from top (-PI/2), go clockwise
		return (2 * Math.PI * index) / data.length - Math.PI / 2;
	}

	function getPoint(index: number, fraction: number): { x: number; y: number } {
		const angle = getAngle(index);
		return {
			x: CENTER_X + Math.cos(angle) * RADIUS * fraction,
			y: CENTER_Y + Math.sin(angle) * RADIUS * fraction
		};
	}

	// Grid polygon points for each level
	function getGridPolygon(level: number): string {
		return data
			.map((_, i) => {
				const p = getPoint(i, level);
				return `${p.x},${p.y}`;
			})
			.join(' ');
	}

	// Data polygon points
	let dataPolygon = $derived(
		data
			.map((d, i) => {
				const fraction = d.max > 0 ? Math.min(d.value / d.max, 1) : 0;
				const p = getPoint(i, fraction);
				return `${p.x},${p.y}`;
			})
			.join(' ')
	);

	// Data point positions
	let dataPoints = $derived(
		data.map((d, i) => {
			const fraction = d.max > 0 ? Math.min(d.value / d.max, 1) : 0;
			return getPoint(i, fraction);
		})
	);

	// Label positions (slightly outside the chart)
	let labelPositions = $derived(
		data.map((_, i) => {
			const angle = getAngle(i);
			const labelRadius = RADIUS + 18;
			return {
				x: CENTER_X + Math.cos(angle) * labelRadius,
				y: CENTER_Y + Math.sin(angle) * labelRadius,
				anchor: getTextAnchor(angle)
			};
		})
	);

	function getTextAnchor(angle: number): string {
		const deg = ((angle * 180) / Math.PI + 360) % 360;
		if (deg > 45 && deg < 135) return 'middle';
		if (deg >= 135 && deg <= 225) return 'end';
		if (deg > 225 && deg < 315) return 'middle';
		return 'start';
	}

	function getDominantBaseline(angle: number): string {
		const deg = ((angle * 180) / Math.PI + 360) % 360;
		if (deg > 45 && deg < 135) return 'hanging';
		if (deg > 225 && deg < 315) return 'auto';
		return 'middle';
	}
</script>

<div class="radar-container">
	<svg
		width={size}
		height={TOTAL_HEIGHT}
		viewBox="0 0 {size} {TOTAL_HEIGHT}"
		class="chart-svg"
		role="img"
		aria-label={title || 'Radar Chart'}
	>
		<!-- Title -->
		{#if title}
			<text
				x={size / 2}
				y={14}
				text-anchor="middle"
				class="chart-title"
			>
				{title}
			</text>
		{/if}

		<!-- Grid levels -->
		{#each gridLevels as level}
			<polygon
				points={getGridPolygon(level)}
				fill="none"
				stroke="oklch(0.22 0 0)"
				stroke-width="0.75"
			/>
		{/each}

		<!-- Axis lines (from center to each vertex) -->
		{#each data as _, i}
			{@const p = getPoint(i, 1)}
			<line
				x1={CENTER_X}
				y1={CENTER_Y}
				x2={p.x}
				y2={p.y}
				stroke="oklch(0.20 0 0)"
				stroke-width="0.75"
			/>
		{/each}

		<!-- Grid level percentage labels -->
		{#each gridLevels as level}
			{@const p = getPoint(0, level)}
			<text
				x={p.x + 3}
				y={p.y - 3}
				class="grid-label"
			>
				{Math.round(level * 100)}%
			</text>
		{/each}

		<!-- Data polygon fill -->
		{#if data.length >= 3}
			<polygon
				points={dataPolygon}
				fill="oklch(0.55 0.15 145 / 0.15)"
				stroke="oklch(0.60 0.16 145)"
				stroke-width="1.5"
			/>
		{/if}

		<!-- Data points -->
		{#each dataPoints as point, i}
			<circle
				cx={point.x}
				cy={point.y}
				r={hoveredIndex === i ? 5 : 3.5}
				fill={hoveredIndex === i ? 'oklch(0.70 0.17 145)' : 'oklch(0.60 0.16 145)'}
				stroke="oklch(0.13 0 0)"
				stroke-width="1.5"
				class="data-point"
				onmouseenter={() => (hoveredIndex = i)}
				onmouseleave={() => (hoveredIndex = null)}
			/>
		{/each}

		<!-- Axis labels -->
		{#each data as axis, i}
			{@const pos = labelPositions[i]}
			{@const angle = getAngle(i)}
			<text
				x={pos.x}
				y={pos.y}
				text-anchor={pos.anchor}
				dominant-baseline={getDominantBaseline(angle)}
				class="axis-label {hoveredIndex === i ? 'axis-label-highlight' : ''}"
			>
				{axis.label}
			</text>
		{/each}

		<!-- Hovered value label -->
		{#if hoveredIndex !== null && data[hoveredIndex]}
			{@const point = dataPoints[hoveredIndex]}
			{@const axis = data[hoveredIndex]}
			<g>
				<rect
					x={point.x - 28}
					y={point.y - 22}
					width="56"
					height="16"
					rx="4"
					fill="oklch(0.14 0 0 / 0.92)"
					stroke="oklch(0.28 0 0)"
					stroke-width="0.5"
				/>
				<text
					x={point.x}
					y={point.y - 12}
					text-anchor="middle"
					dominant-baseline="middle"
					class="value-label"
				>
					{axis.value.toFixed(1)} / {axis.max.toFixed(0)}
				</text>
			</g>
		{/if}
	</svg>
</div>

<style>
	.radar-container {
		display: inline-block;
		position: relative;
	}

	.chart-svg {
		user-select: none;
	}

	.chart-title {
		font-size: var(--text-xs, 0.75rem);
		fill: oklch(0.75 0 0);
		font-weight: 500;
	}

	.grid-label {
		font-size: 7px;
		fill: oklch(0.40 0 0);
		font-family: var(--font-mono);
	}

	.axis-label {
		font-size: 9px;
		font-family: var(--font-mono);
		fill: oklch(0.55 0 0);
	}

	.axis-label.axis-label-highlight {
		fill: oklch(0.90 0 0);
	}

	.data-point {
		cursor: crosshair;
		transition: all 100ms;
	}

	.value-label {
		font-size: 9px;
		fill: oklch(0.85 0.10 145);
		font-family: var(--font-mono);
		font-weight: 600;
	}
</style>
