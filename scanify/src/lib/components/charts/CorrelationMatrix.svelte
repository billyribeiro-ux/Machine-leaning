<script lang="ts">
	interface Props {
		symbols: string[];
		correlations: number[][];
		height?: number;
	}

	let { symbols, correlations, height = 400 }: Props = $props();

	let hoveredCell = $state<{ row: number; col: number } | null>(null);
	let mouseX = $state(0);
	let mouseY = $state(0);

	// Layout
	const LABEL_SIZE = 52;
	const PADDING = 8;
	const CELL_GAP = 1.5;

	let gridSize = $derived(height - LABEL_SIZE - PADDING * 2);
	let svgWidth = $derived(gridSize + LABEL_SIZE + PADDING * 2 + 50); // extra for legend

	let cellSize = $derived(
		symbols.length > 0
			? (gridSize - CELL_GAP * (symbols.length - 1)) / symbols.length
			: 0
	);

	function getCellX(col: number): number {
		return LABEL_SIZE + PADDING + col * (cellSize + CELL_GAP);
	}

	function getCellY(row: number): number {
		return PADDING + row * (cellSize + CELL_GAP);
	}

	function getCorrelation(row: number, col: number): number {
		if (
			row >= 0 &&
			row < correlations.length &&
			col >= 0 &&
			col < (correlations[row]?.length ?? 0)
		) {
			return correlations[row][col];
		}
		return row === col ? 1 : 0;
	}

	function getColor(value: number): string {
		const clamped = Math.max(-1, Math.min(1, value));

		if (clamped > 0) {
			// Positive correlation: green
			const t = clamped;
			const lightness = 0.18 + t * 0.24;
			const chroma = t * 0.15;
			return `oklch(${lightness} ${chroma} 145)`;
		} else if (clamped < 0) {
			// Negative correlation: red
			const t = -clamped;
			const lightness = 0.18 + t * 0.22;
			const chroma = t * 0.16;
			return `oklch(${lightness} ${chroma} 25)`;
		}
		// Zero
		return 'oklch(0.18 0 0)';
	}

	function getCorrelationText(value: number): string {
		if (value === 1) return '1.00';
		if (value === -1) return '-1.00';
		return value.toFixed(2);
	}

	function handleCellHover(e: MouseEvent, row: number, col: number) {
		hoveredCell = { row, col };
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

<div class="corr-container">
	<svg
		width={svgWidth}
		{height}
		viewBox="0 0 {svgWidth} {height}"
		class="chart-svg"
		role="img"
		aria-label="Correlation Matrix"
	>
		<!-- Y-axis labels (row symbols, left side) -->
		{#each symbols as sym, rowIdx}
			<text
				x={LABEL_SIZE - 4}
				y={getCellY(rowIdx) + cellSize / 2}
				text-anchor="end"
				dominant-baseline="middle"
				class="axis-label {hoveredCell?.row === rowIdx ? 'axis-label-highlight' : ''}"
			>
				{sym}
			</text>
		{/each}

		<!-- X-axis labels (column symbols, bottom) -->
		{#each symbols as sym, colIdx}
			<text
				x={getCellX(colIdx) + cellSize / 2}
				y={PADDING + gridSize + 16}
				text-anchor="middle"
				class="axis-label {hoveredCell?.col === colIdx ? 'axis-label-highlight' : ''}"
			>
				{sym}
			</text>
		{/each}

		<!-- Matrix cells -->
		{#each symbols as _, rowIdx}
			{#each symbols as _, colIdx}
				{@const value = getCorrelation(rowIdx, colIdx)}
				{@const isHovered =
					hoveredCell?.row === rowIdx && hoveredCell?.col === colIdx}
				{@const isHighlighted =
					hoveredCell !== null &&
					(hoveredCell.row === rowIdx || hoveredCell.col === colIdx)}

				<rect
					x={getCellX(colIdx)}
					y={getCellY(rowIdx)}
					width={cellSize}
					height={cellSize}
					fill={getColor(value)}
					rx="2"
					opacity={hoveredCell !== null && !isHighlighted && !isHovered ? 0.4 : 1}
					stroke={isHovered ? 'oklch(0.70 0 0)' : 'none'}
					stroke-width={isHovered ? 1.5 : 0}
					class="cell"
					onmouseenter={(e) => handleCellHover(e, rowIdx, colIdx)}
					onmousemove={(e) => handleCellHover(e, rowIdx, colIdx)}
					onmouseleave={handleCellLeave}
				/>

				<!-- Show value text inside cell if large enough -->
				{#if cellSize >= 32}
					<text
						x={getCellX(colIdx) + cellSize / 2}
						y={getCellY(rowIdx) + cellSize / 2}
						text-anchor="middle"
						dominant-baseline="middle"
						class="cell-text {Math.abs(value) > 0.5 ? 'cell-text-bright' : ''}"
					>
						{getCorrelationText(value)}
					</text>
				{/if}
			{/each}
		{/each}

		<!-- Color legend -->
		<defs>
			<linearGradient id="corr-legend-gradient" x1="0" y1="1" x2="0" y2="0">
				<stop offset="0%" stop-color="oklch(0.40 0.16 25)" />
				<stop offset="50%" stop-color="oklch(0.18 0 0)" />
				<stop offset="100%" stop-color="oklch(0.42 0.15 145)" />
			</linearGradient>
		</defs>

		<rect
			x={LABEL_SIZE + PADDING + gridSize + 16}
			y={PADDING}
			width={10}
			height={gridSize}
			fill="url(#corr-legend-gradient)"
			rx="2"
		/>

		<!-- Legend labels -->
		<text
			x={LABEL_SIZE + PADDING + gridSize + 32}
			y={PADDING + 4}
			dominant-baseline="hanging"
			class="legend-label"
		>
			+1.0
		</text>
		<text
			x={LABEL_SIZE + PADDING + gridSize + 32}
			y={PADDING + gridSize / 2}
			dominant-baseline="middle"
			class="legend-label"
		>
			0.0
		</text>
		<text
			x={LABEL_SIZE + PADDING + gridSize + 32}
			y={PADDING + gridSize - 2}
			dominant-baseline="auto"
			class="legend-label"
		>
			-1.0
		</text>
	</svg>

	<!-- Tooltip -->
	{#if hoveredCell !== null}
		{@const value = getCorrelation(hoveredCell.row, hoveredCell.col)}
		<div
			class="tooltip"
			style="left: {mouseX + 14}px; top: {mouseY - 50}px;"
		>
			<div class="tooltip-header">
				<div class="tooltip-sym">
					<span class="tooltip-sym-name">{symbols[hoveredCell.row]}</span>
					<span class="tooltip-sym-vs">vs</span>
					<span class="tooltip-sym-name">{symbols[hoveredCell.col]}</span>
				</div>
				<div
					class="tooltip-value {value > 0.3
						? 'tooltip-positive'
						: value < -0.3
							? 'tooltip-negative'
							: 'tooltip-neutral'}"
				>
					{value >= 0 ? '+' : ''}{value.toFixed(4)}
				</div>
				<div class="tooltip-desc">
					{#if Math.abs(value) >= 0.8}
						Very strong {value > 0 ? 'positive' : 'negative'}
					{:else if Math.abs(value) >= 0.6}
						Strong {value > 0 ? 'positive' : 'negative'}
					{:else if Math.abs(value) >= 0.4}
						Moderate {value > 0 ? 'positive' : 'negative'}
					{:else if Math.abs(value) >= 0.2}
						Weak {value > 0 ? 'positive' : 'negative'}
					{:else}
						Negligible
					{/if}
				</div>
			</div>
		</div>
	{/if}
</div>

<style>
	.corr-container {
		position: relative;
		display: inline-block;
	}

	.chart-svg {
		user-select: none;
	}

	.axis-label {
		font-size: 9px;
		font-family: var(--font-mono);
		fill: oklch(0.55 0 0);
	}

	.axis-label-highlight {
		fill: oklch(0.90 0 0);
	}

	.cell {
		cursor: crosshair;
		transition: opacity 100ms;
	}

	.cell-text {
		font-size: 8px;
		font-family: var(--font-mono);
		pointer-events: none;
		fill: oklch(0.50 0 0);
	}

	.cell-text-bright {
		fill: oklch(0.90 0 0);
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
	}

	.tooltip-header {
		font-size: 10px;
		font-family: var(--font-mono);
	}

	.tooltip-sym {
		color: oklch(0.50 0 0);
		margin-bottom: 4px;
	}

	.tooltip-sym-name {
		color: oklch(0.85 0 0);
		font-weight: 600;
	}

	.tooltip-sym-vs {
		margin-inline: 4px;
	}

	.tooltip-value {
		font-size: 0.875rem;
		font-weight: 700;
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

	.tooltip-desc {
		font-size: 9px;
		color: oklch(0.45 0 0);
		margin-top: 2px;
	}
</style>
