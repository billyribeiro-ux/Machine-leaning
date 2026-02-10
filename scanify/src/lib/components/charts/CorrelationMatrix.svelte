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

<div class="relative inline-block">
	<svg
		width={svgWidth}
		{height}
		viewBox="0 0 {svgWidth} {height}"
		class="select-none"
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
				class="text-[9px] font-mono {hoveredCell?.row === rowIdx
					? 'fill-[oklch(0.90_0_0)]'
					: 'fill-[oklch(0.55_0_0)]'}"
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
				class="text-[9px] font-mono {hoveredCell?.col === colIdx
					? 'fill-[oklch(0.90_0_0)]'
					: 'fill-[oklch(0.55_0_0)]'}"
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
					class="cursor-crosshair transition-opacity duration-100"
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
						class="text-[8px] font-mono pointer-events-none
							{Math.abs(value) > 0.5
							? 'fill-[oklch(0.90_0_0)]'
							: 'fill-[oklch(0.50_0_0)]'}"
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
			class="text-[8px] fill-[oklch(0.50_0_0)] font-mono"
		>
			+1.0
		</text>
		<text
			x={LABEL_SIZE + PADDING + gridSize + 32}
			y={PADDING + gridSize / 2}
			dominant-baseline="middle"
			class="text-[8px] fill-[oklch(0.50_0_0)] font-mono"
		>
			0.0
		</text>
		<text
			x={LABEL_SIZE + PADDING + gridSize + 32}
			y={PADDING + gridSize - 2}
			dominant-baseline="auto"
			class="text-[8px] fill-[oklch(0.50_0_0)] font-mono"
		>
			-1.0
		</text>
	</svg>

	<!-- Tooltip -->
	{#if hoveredCell !== null}
		{@const value = getCorrelation(hoveredCell.row, hoveredCell.col)}
		<div
			class="pointer-events-none absolute z-50 rounded-lg border border-[oklch(0.25_0_0)]
				bg-[oklch(0.14_0_0/0.94)] px-3 py-2 shadow-xl backdrop-blur-sm"
			style="left: {mouseX + 14}px; top: {mouseY - 50}px;"
		>
			<div class="text-[10px] font-mono">
				<div class="text-[oklch(0.50_0_0)] mb-1">
					<span class="text-[oklch(0.85_0_0)] font-semibold">{symbols[hoveredCell.row]}</span>
					<span class="mx-1">vs</span>
					<span class="text-[oklch(0.85_0_0)] font-semibold">{symbols[hoveredCell.col]}</span>
				</div>
				<div
					class="text-sm font-bold
						{value > 0.3
						? 'text-[oklch(0.75_0.15_145)]'
						: value < -0.3
							? 'text-[oklch(0.70_0.16_25)]'
							: 'text-[oklch(0.70_0_0)]'}"
				>
					{value >= 0 ? '+' : ''}{value.toFixed(4)}
				</div>
				<div class="text-[9px] text-[oklch(0.45_0_0)] mt-0.5">
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
