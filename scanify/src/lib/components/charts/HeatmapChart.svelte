<script lang="ts">
	interface HeatmapCell {
		x: string;
		y: string;
		value: number;
	}

	interface Props {
		data: HeatmapCell[];
		xLabels: string[];
		yLabels: string[];
		title?: string;
		height?: number;
	}

	let { data, xLabels, yLabels, title = '', height = 400 }: Props = $props();

	let hoveredCell = $state<HeatmapCell | null>(null);
	let mouseX = $state(0);
	let mouseY = $state(0);

	// Layout
	const Y_LABEL_WIDTH = 72;
	const X_LABEL_HEIGHT = 48;
	const TITLE_HEIGHT = 28;
	const PADDING_RIGHT = 60; // For color legend
	const PADDING_TOP = 8;
	const CELL_GAP = 1.5;

	let chartTop = $derived(title ? TITLE_HEIGHT + PADDING_TOP : PADDING_TOP);
	let gridHeight = $derived(height - chartTop - X_LABEL_HEIGHT);
	let gridWidth = $derived.by(() => {
		// Will compute actual width from container - for now assume 500
		return 500 - Y_LABEL_WIDTH - PADDING_RIGHT;
	});

	let svgWidth = $derived(Y_LABEL_WIDTH + gridWidth + PADDING_RIGHT);

	let cellWidth = $derived(
		xLabels.length > 0 ? (gridWidth - CELL_GAP * (xLabels.length - 1)) / xLabels.length : 0
	);

	let cellHeight = $derived(
		yLabels.length > 0 ? (gridHeight - CELL_GAP * (yLabels.length - 1)) / yLabels.length : 0
	);

	// Value range for color mapping
	let minValue = $derived(data.length > 0 ? Math.min(...data.map((d) => d.value)) : -1);
	let maxValue = $derived(data.length > 0 ? Math.max(...data.map((d) => d.value)) : 1);
	let absMax = $derived(Math.max(Math.abs(minValue), Math.abs(maxValue), 0.001));

	function getCellValue(x: string, y: string): number {
		const cell = data.find((d) => d.x === x && d.y === y);
		return cell?.value ?? 0;
	}

	function getColor(value: number): string {
		// Normalize to [-1, 1]
		const normalized = Math.max(-1, Math.min(1, value / absMax));

		if (normalized > 0) {
			// Positive (bullish green)
			const intensity = normalized;
			const lightness = 0.18 + intensity * 0.22;
			const chroma = intensity * 0.15;
			return `oklch(${lightness} ${chroma} 145)`;
		} else if (normalized < 0) {
			// Negative (bearish red)
			const intensity = -normalized;
			const lightness = 0.18 + intensity * 0.2;
			const chroma = intensity * 0.16;
			return `oklch(${lightness} ${chroma} 25)`;
		}
		// Neutral
		return 'oklch(0.18 0 0)';
	}

	function getCellX(colIndex: number): number {
		return Y_LABEL_WIDTH + colIndex * (cellWidth + CELL_GAP);
	}

	function getCellY(rowIndex: number): number {
		return chartTop + rowIndex * (cellHeight + CELL_GAP);
	}

	function handleCellHover(e: MouseEvent, cell: HeatmapCell) {
		hoveredCell = cell;
		const svgEl = (e.target as SVGElement).closest('svg');
		if (svgEl) {
			const rect = svgEl.getBoundingClientRect();
			mouseX = e.clientX - rect.left;
			mouseY = e.clientY - rect.top;
		}
	}

	function handleCellLeave() {
		hoveredCell = null;
	}
</script>

<div class="heatmap-container">
	<svg
		width={svgWidth}
		{height}
		viewBox="0 0 {svgWidth} {height}"
		class="chart-svg"
		role="img"
		aria-label={title || 'Heatmap Chart'}
	>
		<!-- Title -->
		{#if title}
			<text
				x={Y_LABEL_WIDTH + gridWidth / 2}
				y={18}
				text-anchor="middle"
				class="chart-title"
			>
				{title}
			</text>
		{/if}

		<!-- Y-axis labels -->
		{#each yLabels as label, rowIdx}
			<text
				x={Y_LABEL_WIDTH - 6}
				y={getCellY(rowIdx) + cellHeight / 2}
				text-anchor="end"
				dominant-baseline="middle"
				class="axis-label"
			>
				{label}
			</text>
		{/each}

		<!-- X-axis labels (rotated) -->
		{#each xLabels as label, colIdx}
			<text
				x={getCellX(colIdx) + cellWidth / 2}
				y={chartTop + gridHeight + 8}
				text-anchor="start"
				dominant-baseline="hanging"
				transform="rotate(45 {getCellX(colIdx) + cellWidth / 2} {chartTop + gridHeight + 8})"
				class="axis-label"
			>
				{label}
			</text>
		{/each}

		<!-- Grid cells -->
		{#each yLabels as yLabel, rowIdx}
			{#each xLabels as xLabel, colIdx}
				{@const value = getCellValue(xLabel, yLabel)}
				<rect
					x={getCellX(colIdx)}
					y={getCellY(rowIdx)}
					width={cellWidth}
					height={cellHeight}
					fill={getColor(value)}
					rx="2"
					class="cell"
					opacity={hoveredCell && (hoveredCell.x !== xLabel || hoveredCell.y !== yLabel)
						? 0.6
						: 1}
					onmouseenter={(e) => handleCellHover(e, { x: xLabel, y: yLabel, value })}
					onmousemove={(e) => handleCellHover(e, { x: xLabel, y: yLabel, value })}
					onmouseleave={handleCellLeave}
				/>
			{/each}
		{/each}

		<!-- Color legend -->
		<defs>
			<linearGradient id="heatmap-legend-gradient" x1="0" y1="1" x2="0" y2="0">
				<stop offset="0%" stop-color="oklch(0.38 0.16 25)" />
				<stop offset="50%" stop-color="oklch(0.18 0 0)" />
				<stop offset="100%" stop-color="oklch(0.40 0.15 145)" />
			</linearGradient>
		</defs>

		<rect
			x={svgWidth - PADDING_RIGHT + 16}
			y={chartTop}
			width={10}
			height={gridHeight}
			fill="url(#heatmap-legend-gradient)"
			rx="2"
		/>

		<!-- Legend labels -->
		<text
			x={svgWidth - PADDING_RIGHT + 32}
			y={chartTop + 4}
			dominant-baseline="hanging"
			class="legend-label"
		>
			+{absMax.toFixed(1)}
		</text>
		<text
			x={svgWidth - PADDING_RIGHT + 32}
			y={chartTop + gridHeight / 2}
			dominant-baseline="middle"
			class="legend-label"
		>
			0
		</text>
		<text
			x={svgWidth - PADDING_RIGHT + 32}
			y={chartTop + gridHeight - 2}
			dominant-baseline="auto"
			class="legend-label"
		>
			-{absMax.toFixed(1)}
		</text>
	</svg>

	<!-- Tooltip -->
	{#if hoveredCell}
		<div
			class="tooltip"
			style="left: {mouseX + 14}px; top: {mouseY - 50}px;"
		>
			<div class="tooltip-header">
				{hoveredCell.x} / {hoveredCell.y}
			</div>
			<div
				class="tooltip-value {hoveredCell.value > 0
					? 'tooltip-positive'
					: hoveredCell.value < 0
						? 'tooltip-negative'
						: 'tooltip-neutral'}"
			>
				{hoveredCell.value >= 0 ? '+' : ''}{hoveredCell.value.toFixed(2)}
			</div>
		</div>
	{/if}
</div>

<style>
	.heatmap-container {
		position: relative;
		display: inline-block;
	}

	.chart-svg {
		user-select: none;
	}

	.chart-title {
		font-size: var(--text-xs, 0.75rem);
		fill: oklch(0.75 0 0);
		font-weight: 500;
	}

	.axis-label {
		font-size: 9px;
		fill: oklch(0.55 0 0);
		font-family: var(--font-mono);
	}

	.cell {
		cursor: crosshair;
		transition: opacity 100ms;
	}

	.legend-label {
		font-size: 8px;
		fill: oklch(0.50 0 0);
		font-family: var(--font-mono);
	}

	.tooltip {
		pointer-events: none;
		position: absolute;
		z-index: 50;
		border-radius: var(--radius-lg, 8px);
		border: 1px solid oklch(0.25 0 0);
		background: oklch(0.14 0 0 / 0.94);
		padding-inline: 12px;
		padding-block: 8px;
		box-shadow: 0 20px 25px -5px oklch(0 0 0 / 0.25);
		backdrop-filter: blur(4px);
		font-family: var(--font-mono);
		font-size: 10px;
	}

	.tooltip-header {
		color: oklch(0.50 0 0);
		margin-bottom: 4px;
	}

	.tooltip-value {
		font-size: var(--text-sm, 0.875rem);
		font-weight: 600;
	}

	.tooltip-positive {
		color: oklch(0.75 0.15 145);
	}

	.tooltip-negative {
		color: oklch(0.70 0.16 25);
	}

	.tooltip-neutral {
		color: oklch(0.70 0 0);
	}
</style>
