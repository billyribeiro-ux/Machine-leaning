<script lang="ts">
	interface VolumeLevel {
		price: number;
		volume: number;
		buyVolume: number;
		sellVolume: number;
	}

	interface Props {
		data: VolumeLevel[];
		height?: number;
		width?: number;
	}

	let { data, height = 400, width = 300 }: Props = $props();

	let hoveredIndex = $state<number | null>(null);
	let mouseX = $state(0);
	let mouseY = $state(0);

	// Layout constants
	const PRICE_LABEL_WIDTH = 60;
	const BAR_AREA_LEFT = PRICE_LABEL_WIDTH + 4;
	const PADDING_RIGHT = 12;
	const PADDING_TOP = 24;
	const PADDING_BOTTOM = 12;
	const BAR_GAP = 1;

	// Derived calculations
	let sortedData = $derived([...data].sort((a, b) => b.price - a.price));

	let maxVolume = $derived(
		sortedData.length > 0 ? Math.max(...sortedData.map((d) => d.volume)) : 1
	);

	let pocIndex = $derived(
		sortedData.length > 0
			? sortedData.reduce(
					(maxI, d, i, arr) => (d.volume > arr[maxI].volume ? i : maxI),
					0
				)
			: -1
	);

	// Value Area: 70% of total volume around POC
	let valueArea = $derived.by(() => {
		if (sortedData.length === 0) return { high: 0, low: 0 };

		const totalVolume = sortedData.reduce((s, d) => s + d.volume, 0);
		const targetVolume = totalVolume * 0.7;

		let cumVolume = sortedData[pocIndex]?.volume ?? 0;
		let vaHigh = pocIndex;
		let vaLow = pocIndex;

		while (cumVolume < targetVolume && (vaHigh > 0 || vaLow < sortedData.length - 1)) {
			const upVol = vaHigh > 0 ? sortedData[vaHigh - 1].volume : 0;
			const downVol = vaLow < sortedData.length - 1 ? sortedData[vaLow + 1].volume : 0;

			if (upVol >= downVol && vaHigh > 0) {
				vaHigh--;
				cumVolume += upVol;
			} else if (vaLow < sortedData.length - 1) {
				vaLow++;
				cumVolume += downVol;
			} else {
				break;
			}
		}

		return {
			high: sortedData[vaHigh]?.price ?? 0,
			low: sortedData[vaLow]?.price ?? 0
		};
	});

	let barAreaWidth = $derived(width - BAR_AREA_LEFT - PADDING_RIGHT);
	let chartHeight = $derived(height - PADDING_TOP - PADDING_BOTTOM);

	let barHeight = $derived(
		sortedData.length > 0
			? Math.max(2, (chartHeight - BAR_GAP * (sortedData.length - 1)) / sortedData.length)
			: 0
	);

	function getBarY(index: number): number {
		return PADDING_TOP + index * (barHeight + BAR_GAP);
	}

	function formatPrice(p: number): string {
		return p >= 1000
			? p.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
			: p.toFixed(2);
	}

	function formatVolume(v: number): string {
		if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M';
		if (v >= 1_000) return (v / 1_000).toFixed(1) + 'K';
		return v.toFixed(0);
	}

	function handleMouseMove(e: MouseEvent, index: number) {
		hoveredIndex = index;
		const svgEl = (e.target as SVGElement).closest('svg');
		if (svgEl) {
			const rect = svgEl.getBoundingClientRect();
			mouseX = e.clientX - rect.left;
			mouseY = e.clientY - rect.top;
		}
	}

	function handleMouseLeave() {
		hoveredIndex = null;
	}
</script>

<div class="volume-container">
	<svg
		{width}
		{height}
		viewBox="0 0 {width} {height}"
		class="chart-svg"
		role="img"
		aria-label="Volume Profile"
	>
		<!-- Title -->
		<text
			x={width / 2}
			y={14}
			text-anchor="middle"
			class="chart-title"
		>
			Volume Profile
		</text>

		<!-- Value Area background -->
		{#if sortedData.length > 0}
			{@const vaHighIdx = sortedData.findIndex((d) => d.price === valueArea.high)}
			{@const vaLowIdx = sortedData.findIndex((d) => d.price === valueArea.low)}
			{#if vaHighIdx >= 0 && vaLowIdx >= 0}
				<rect
					x={BAR_AREA_LEFT}
					y={getBarY(vaHighIdx) - 1}
					width={barAreaWidth}
					height={getBarY(vaLowIdx) + barHeight - getBarY(vaHighIdx) + 2}
					fill="oklch(0.50 0.05 250 / 0.06)"
					rx="2"
				/>
			{/if}
		{/if}

		<!-- Bars -->
		{#each sortedData as level, i}
			{@const y = getBarY(i)}
			{@const buyWidth = maxVolume > 0 ? (level.buyVolume / maxVolume) * barAreaWidth : 0}
			{@const sellWidth = maxVolume > 0 ? (level.sellVolume / maxVolume) * barAreaWidth : 0}
			{@const isPoc = i === pocIndex}
			{@const isHovered = hoveredIndex === i}

			<!-- Price label -->
			<text
				x={PRICE_LABEL_WIDTH - 4}
				y={y + barHeight / 2 + 1}
				text-anchor="end"
				dominant-baseline="middle"
				class="price-label"
				style:fill={isPoc ? 'oklch(0.85 0.12 80)' : 'oklch(0.50 0 0)'}
			>
				{formatPrice(level.price)}
			</text>

			<!-- Buy volume (green, from left) -->
			<rect
				x={BAR_AREA_LEFT}
				{y}
				width={buyWidth}
				height={barHeight}
				fill={isPoc
					? 'oklch(0.55 0.15 145 / 0.9)'
					: isHovered
						? 'oklch(0.55 0.15 145 / 0.7)'
						: 'oklch(0.55 0.15 145 / 0.5)'}
				rx="1"
				onmouseenter={(e) => handleMouseMove(e, i)}
				onmousemove={(e) => handleMouseMove(e, i)}
				onmouseleave={handleMouseLeave}
				class="bar-buy"
			/>

			<!-- Sell volume (red, stacked after buy) -->
			<rect
				x={BAR_AREA_LEFT + buyWidth}
				{y}
				width={sellWidth}
				height={barHeight}
				fill={isPoc
					? 'oklch(0.50 0.18 25 / 0.9)'
					: isHovered
						? 'oklch(0.50 0.18 25 / 0.7)'
						: 'oklch(0.50 0.18 25 / 0.5)'}
				rx="1"
				onmouseenter={(e) => handleMouseMove(e, i)}
				onmousemove={(e) => handleMouseMove(e, i)}
				onmouseleave={handleMouseLeave}
				class="bar-sell"
			/>

			<!-- POC indicator -->
			{#if isPoc}
				<line
					x1={BAR_AREA_LEFT}
					y1={y + barHeight / 2}
					x2={BAR_AREA_LEFT + barAreaWidth}
					y2={y + barHeight / 2}
					stroke="oklch(0.85 0.12 80)"
					stroke-width="1"
					stroke-dasharray="3 2"
					opacity="0.6"
				/>
				<text
					x={BAR_AREA_LEFT + barAreaWidth + 2}
					y={y + barHeight / 2}
					dominant-baseline="middle"
					class="poc-label"
				>
					POC
				</text>
			{/if}
		{/each}

		<!-- VAH / VAL markers -->
		{#if sortedData.length > 0}
			{@const vahIdx = sortedData.findIndex((d) => d.price === valueArea.high)}
			{@const valIdx = sortedData.findIndex((d) => d.price === valueArea.low)}

			{#if vahIdx >= 0}
				<line
					x1={BAR_AREA_LEFT}
					y1={getBarY(vahIdx)}
					x2={BAR_AREA_LEFT + barAreaWidth}
					y2={getBarY(vahIdx)}
					stroke="oklch(0.60 0.10 250)"
					stroke-width="0.75"
					stroke-dasharray="4 2"
					opacity="0.5"
				/>
				<text
					x={BAR_AREA_LEFT + barAreaWidth + 2}
					y={getBarY(vahIdx) - 2}
					class="vah-label"
				>
					VAH
				</text>
			{/if}

			{#if valIdx >= 0}
				<line
					x1={BAR_AREA_LEFT}
					y1={getBarY(valIdx) + barHeight}
					x2={BAR_AREA_LEFT + barAreaWidth}
					y2={getBarY(valIdx) + barHeight}
					stroke="oklch(0.60 0.10 250)"
					stroke-width="0.75"
					stroke-dasharray="4 2"
					opacity="0.5"
				/>
				<text
					x={BAR_AREA_LEFT + barAreaWidth + 2}
					y={getBarY(valIdx) + barHeight + 8}
					class="val-label"
				>
					VAL
				</text>
			{/if}
		{/if}
	</svg>

	<!-- Tooltip -->
	{#if hoveredIndex !== null && sortedData[hoveredIndex]}
		{@const level = sortedData[hoveredIndex]}
		<div
			class="tooltip"
			style="left: {mouseX + 12}px; top: {mouseY - 60}px;"
		>
			<div class="tooltip-price">
				Price: <span class="tooltip-price-value">{formatPrice(level.price)}</span>
			</div>
			<div class="tooltip-rows">
				<div class="tooltip-row">
					<span class="tooltip-dot" style="background: oklch(0.55 0.15 145);"></span>
					<span class="tooltip-label">Buy</span>
					<span class="tooltip-value" style="color: oklch(0.75 0.15 145);">{formatVolume(level.buyVolume)}</span>
				</div>
				<div class="tooltip-row">
					<span class="tooltip-dot" style="background: oklch(0.50 0.18 25);"></span>
					<span class="tooltip-label">Sell</span>
					<span class="tooltip-value" style="color: oklch(0.70 0.16 25);">{formatVolume(level.sellVolume)}</span>
				</div>
				<div class="tooltip-row tooltip-divider">
					<span class="tooltip-label">Total</span>
					<span class="tooltip-value" style="color: oklch(0.80 0 0);">{formatVolume(level.volume)}</span>
				</div>
			</div>
		</div>
	{/if}
</div>

<style>
	.volume-container {
		position: relative;
		display: inline-block;
	}

	.chart-svg {
		user-select: none;
	}

	.chart-title {
		font-size: 10px;
		fill: oklch(0.50 0 0);
		font-family: var(--font-mono);
	}

	.price-label {
		font-size: 9px;
		font-family: var(--font-mono);
	}

	.poc-label {
		font-size: 8px;
		fill: oklch(0.85 0.12 80);
		font-family: var(--font-mono);
		font-weight: 700;
	}

	.vah-label {
		font-size: 7px;
		fill: oklch(0.60 0.10 250);
		font-family: var(--font-mono);
	}

	.val-label {
		font-size: 7px;
		fill: oklch(0.60 0.10 250);
		font-family: var(--font-mono);
	}

	.bar-buy,
	.bar-sell {
		cursor: crosshair;
		transition: fill 100ms;
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

	.tooltip-price {
		font-size: 10px;
		color: oklch(0.50 0 0);
		margin-bottom: 4px;
	}

	.tooltip-price-value {
		color: oklch(0.85 0 0);
		font-family: var(--font-mono);
	}

	.tooltip-rows {
		display: flex;
		flex-direction: column;
		gap: 2px;
		font-size: 10px;
		font-family: var(--font-mono);
	}

	.tooltip-row {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.tooltip-dot {
		width: 6px;
		height: 6px;
		border-radius: 9999px;
	}

	.tooltip-label {
		color: oklch(0.55 0 0);
	}

	.tooltip-value {
		margin-left: auto;
	}

	.tooltip-divider {
		padding-top: 4px;
		margin-top: 4px;
		border-top: 1px solid oklch(0.22 0 0);
	}
</style>
