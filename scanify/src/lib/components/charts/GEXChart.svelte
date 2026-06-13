<script lang="ts">
	interface GEXDataPoint {
		strike: number;
		callGamma: number;
		putGamma: number;
		netGamma: number;
	}

	interface Props {
		data: GEXDataPoint[];
		currentPrice?: number;
		height?: number;
	}

	let { data, currentPrice, height = 350 }: Props = $props();

	let containerEl: HTMLDivElement | undefined = $state(undefined);
	let containerWidth = $state(600);
	let hoveredIndex = $state<number | null>(null);
	let mouseX = $state(0);
	let mouseY = $state(0);

	$effect(() => {
		if (!containerEl) return;
		const observer = new ResizeObserver((entries) => {
			for (const entry of entries) {
				containerWidth = entry.contentRect.width;
			}
		});
		observer.observe(containerEl);
		return () => observer.disconnect();
	});

	// Layout
	const PADDING_LEFT = 64;
	const PADDING_RIGHT = 16;
	const PADDING_TOP = 28;
	const PADDING_BOTTOM = 44;

	let chartWidth = $derived(containerWidth - PADDING_LEFT - PADDING_RIGHT);
	let chartHeight = $derived(height - PADDING_TOP - PADDING_BOTTOM);

	// Sort by strike
	let sortedData = $derived([...data].sort((a, b) => a.strike - b.strike));

	// Scales
	let maxGamma = $derived(
		sortedData.length > 0
			? Math.max(
					...sortedData.map((d) => Math.abs(d.callGamma)),
					...sortedData.map((d) => Math.abs(d.putGamma)),
					0.001
				)
			: 1
	);

	let maxNetGamma = $derived(
		sortedData.length > 0
			? Math.max(...sortedData.map((d) => Math.abs(d.netGamma)), 0.001)
			: 1
	);

	let barWidth = $derived(
		sortedData.length > 0
			? Math.max(2, (chartWidth / sortedData.length) * 0.7)
			: 10
	);

	let barGap = $derived(
		sortedData.length > 0
			? (chartWidth / sortedData.length) * 0.3
			: 4
	);

	// Zero line Y position (middle of chart)
	let zeroY = $derived(PADDING_TOP + chartHeight / 2);

	function xScale(index: number): number {
		if (sortedData.length <= 1) return PADDING_LEFT + chartWidth / 2;
		return PADDING_LEFT + (index / (sortedData.length - 1)) * chartWidth;
	}

	function yScaleGamma(value: number): number {
		// Positive values go up from zero line, negative go down
		const normalized = maxGamma > 0 ? value / maxGamma : 0;
		return zeroY - normalized * (chartHeight / 2) * 0.9;
	}

	function yScaleNet(value: number): number {
		const normalized = maxNetGamma > 0 ? value / maxNetGamma : 0;
		return zeroY - normalized * (chartHeight / 2) * 0.85;
	}

	// Current price x-position
	let currentPriceX = $derived.by(() => {
		if (currentPrice === undefined || sortedData.length === 0) return null;

		const minStrike = sortedData[0].strike;
		const maxStrike = sortedData[sortedData.length - 1].strike;
		const range = maxStrike - minStrike;
		if (range <= 0) return PADDING_LEFT + chartWidth / 2;

		const fraction = (currentPrice - minStrike) / range;
		return PADDING_LEFT + fraction * chartWidth;
	});

	// Net gamma line path
	let netGammaPath = $derived.by(() => {
		if (sortedData.length === 0) return '';
		return sortedData
			.map((d, i) => {
				const x = xScale(i);
				const y = yScaleNet(d.netGamma);
				return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
			})
			.join(' ');
	});

	// Y-axis ticks
	let yTicks = $derived.by(() => {
		const ticks: number[] = [];
		const steps = 4;
		for (let i = -steps; i <= steps; i++) {
			ticks.push((i / steps) * maxGamma);
		}
		return ticks;
	});

	// X-axis labels (sample strikes)
	let xTickIndices = $derived.by(() => {
		if (sortedData.length <= 8) return sortedData.map((_, i) => i);
		const count = Math.min(8, sortedData.length);
		const step = (sortedData.length - 1) / (count - 1);
		return Array.from({ length: count }, (_, i) => Math.round(i * step));
	});

	function formatGamma(v: number): string {
		const abs = Math.abs(v);
		if (abs >= 1_000_000_000) return (v / 1_000_000_000).toFixed(1) + 'B';
		if (abs >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M';
		if (abs >= 1_000) return (v / 1_000).toFixed(1) + 'K';
		return v.toFixed(1);
	}

	function handleHover(e: MouseEvent) {
		if (!containerEl || sortedData.length === 0) return;
		const rect = containerEl.getBoundingClientRect();
		const relX = e.clientX - rect.left;
		mouseX = relX;
		mouseY = e.clientY - rect.top;

		const chartX = relX - PADDING_LEFT;
		const fraction = chartX / chartWidth;
		const index = Math.round(fraction * (sortedData.length - 1));
		hoveredIndex = Math.max(0, Math.min(sortedData.length - 1, index));
	}

	function handleLeave() {
		hoveredIndex = null;
	}
</script>

<div class="gex-container" bind:this={containerEl}>
	<svg
		width={containerWidth}
		{height}
		viewBox="0 0 {containerWidth} {height}"
		class="chart-svg"
		role="img"
		aria-label="Gamma Exposure Chart"
		onmousemove={handleHover}
		onmouseleave={handleLeave}
	>
		<!-- Title -->
		<text
			x={containerWidth / 2}
			y={16}
			text-anchor="middle"
			class="chart-title"
		>
			Gamma Exposure (GEX) by Strike
		</text>

		<!-- Y-axis grid and labels -->
		{#each yTicks as tick}
			<line
				x1={PADDING_LEFT}
				y1={yScaleGamma(tick)}
				x2={PADDING_LEFT + chartWidth}
				y2={yScaleGamma(tick)}
				stroke="oklch(0.18 0 0)"
				stroke-width="0.5"
			/>
			<text
				x={PADDING_LEFT - 6}
				y={yScaleGamma(tick)}
				text-anchor="end"
				dominant-baseline="middle"
				class="axis-tick"
			>
				{formatGamma(tick)}
			</text>
		{/each}

		<!-- Zero line -->
		<line
			x1={PADDING_LEFT}
			y1={zeroY}
			x2={PADDING_LEFT + chartWidth}
			y2={zeroY}
			stroke="oklch(0.30 0 0)"
			stroke-width="1"
		/>

		<!-- Call gamma bars (above zero, green) -->
		{#each sortedData as point, i}
			{@const x = xScale(i) - barWidth / 2}
			{@const callBarH = Math.abs(yScaleGamma(point.callGamma) - zeroY)}
			<rect
				{x}
				y={Math.min(yScaleGamma(point.callGamma), zeroY)}
				width={barWidth}
				height={callBarH}
				fill={hoveredIndex === i
					? 'oklch(0.55 0.15 145 / 0.8)'
					: 'oklch(0.45 0.13 145 / 0.6)'}
				rx="1"
				class="bar-fill"
			/>
		{/each}

		<!-- Put gamma bars (below zero, red) -->
		{#each sortedData as point, i}
			{@const x = xScale(i) - barWidth / 2}
			{@const putVal = -Math.abs(point.putGamma)}
			{@const putBarH = Math.abs(yScaleGamma(putVal) - zeroY)}
			<rect
				x={x}
				y={zeroY}
				width={barWidth}
				height={putBarH}
				fill={hoveredIndex === i
					? 'oklch(0.50 0.18 25 / 0.8)'
					: 'oklch(0.42 0.15 25 / 0.6)'}
				rx="1"
				class="bar-fill"
			/>
		{/each}

		<!-- Net gamma line -->
		{#if netGammaPath}
			<path
				d={netGammaPath}
				fill="none"
				stroke="oklch(0.70 0.12 250)"
				stroke-width="2"
				stroke-linejoin="round"
			/>
			<!-- Net gamma dots -->
			{#each sortedData as point, i}
				{#if hoveredIndex === i}
					<circle
						cx={xScale(i)}
						cy={yScaleNet(point.netGamma)}
						r="3.5"
						fill="oklch(0.70 0.12 250)"
						stroke="oklch(0.13 0 0)"
						stroke-width="1.5"
					/>
				{/if}
			{/each}
		{/if}

		<!-- Current price marker -->
		{#if currentPriceX !== null}
			<line
				x1={currentPriceX}
				y1={PADDING_TOP}
				x2={currentPriceX}
				y2={PADDING_TOP + chartHeight}
				stroke="oklch(0.80 0.14 80)"
				stroke-width="1.5"
				stroke-dasharray="5 3"
			/>
			<text
				x={currentPriceX}
				y={PADDING_TOP - 4}
				text-anchor="middle"
				class="price-label"
			>
				${currentPrice?.toFixed(2)}
			</text>
		{/if}

		<!-- X-axis labels -->
		{#each xTickIndices as idx}
			<text
				x={xScale(idx)}
				y={height - PADDING_BOTTOM + 14}
				text-anchor="middle"
				class="axis-tick"
			>
				{sortedData[idx].strike}
			</text>
		{/each}

		<!-- Axis labels -->
		<text
			x={PADDING_LEFT - 4}
			y={PADDING_TOP - 6}
			text-anchor="end"
			class="axis-label"
		>
			Gamma ($)
		</text>

		<text
			x={PADDING_LEFT + chartWidth / 2}
			y={height - 4}
			text-anchor="middle"
			class="axis-label-x"
		>
			Strike Price
		</text>

		<!-- Crosshair -->
		{#if hoveredIndex !== null}
			<line
				x1={xScale(hoveredIndex)}
				y1={PADDING_TOP}
				x2={xScale(hoveredIndex)}
				y2={PADDING_TOP + chartHeight}
				stroke="oklch(0.35 0 0)"
				stroke-width="0.75"
				stroke-dasharray="3 2"
			/>
		{/if}

		<!-- Chart border -->
		<rect
			x={PADDING_LEFT}
			y={PADDING_TOP}
			width={chartWidth}
			height={chartHeight}
			fill="none"
			stroke="oklch(0.20 0 0)"
			stroke-width="0.5"
		/>

		<!-- Legend -->
		<g transform="translate({PADDING_LEFT + chartWidth - 195}, {PADDING_TOP + 6})">
			<rect x="0" y="-4" width="190" height="18" rx="4" fill="oklch(0.12 0 0 / 0.85)" />
			<rect x="6" y="0" width="8" height="8" rx="1" fill="oklch(0.45 0.13 145 / 0.7)" />
			<text x="18" y="8" class="legend-label">Call GEX</text>
			<rect x="68" y="0" width="8" height="8" rx="1" fill="oklch(0.42 0.15 25 / 0.7)" />
			<text x="80" y="8" class="legend-label">Put GEX</text>
			<line x1="130" y1="4" x2="146" y2="4" stroke="oklch(0.70 0.12 250)" stroke-width="2" />
			<text x="150" y="8" class="legend-label">Net</text>
		</g>
	</svg>

	<!-- Tooltip -->
	{#if hoveredIndex !== null && sortedData[hoveredIndex]}
		{@const point = sortedData[hoveredIndex]}
		<div
			class="tooltip"
			style="left: {Math.min(mouseX + 14, containerWidth - 180)}px;
				top: {Math.max(mouseY - 90, 4)}px;"
		>
			<div class="tooltip-strike">
				Strike: <span class="tooltip-strike-value">{point.strike}</span>
			</div>
			<div class="tooltip-rows">
				<div class="tooltip-row">
					<span class="tooltip-dot" style="background: oklch(0.55 0.15 145);"></span>
					<span class="tooltip-label">Call GEX</span>
					<span class="tooltip-value" style="color: oklch(0.75 0.15 145);">{formatGamma(point.callGamma)}</span>
				</div>
				<div class="tooltip-row">
					<span class="tooltip-dot" style="background: oklch(0.50 0.18 25);"></span>
					<span class="tooltip-label">Put GEX</span>
					<span class="tooltip-value" style="color: oklch(0.70 0.16 25);">{formatGamma(point.putGamma)}</span>
				</div>
				<div class="tooltip-divider">
					<span class="tooltip-dot" style="background: oklch(0.65 0.12 250);"></span>
					<span class="tooltip-label">Net GEX</span>
					<span
						class="tooltip-net"
						style="color: {point.netGamma >= 0
							? 'oklch(0.75 0.15 145)'
							: 'oklch(0.70 0.16 25)'};"
					>
						{point.netGamma >= 0 ? '+' : ''}{formatGamma(point.netGamma)}
					</span>
				</div>
			</div>
		</div>
	{/if}
</div>

<style>
	.gex-container {
		position: relative;
		width: 100%;
	}

	.chart-svg {
		user-select: none;
	}

	.chart-title {
		font-size: 11px;
		fill: oklch(0.65 0 0);
		font-weight: 500;
	}

	.axis-tick {
		font-size: 8px;
		fill: oklch(0.42 0 0);
		font-family: var(--font-mono);
	}

	.axis-label {
		font-size: 7px;
		fill: oklch(0.40 0 0);
		font-family: var(--font-mono);
	}

	.axis-label-x {
		font-size: 8px;
		fill: oklch(0.40 0 0);
		font-family: var(--font-mono);
	}

	.price-label {
		font-size: 8px;
		fill: oklch(0.80 0.14 80);
		font-family: var(--font-mono);
		font-weight: 600;
	}

	.legend-label {
		font-size: 8px;
		fill: oklch(0.60 0 0);
		font-family: var(--font-mono);
	}

	.bar-fill {
		transition: fill 75ms;
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

	.tooltip-strike {
		font-size: 10px;
		color: oklch(0.50 0 0);
		margin-bottom: 6px;
		font-family: var(--font-mono);
	}

	.tooltip-strike-value {
		color: oklch(0.85 0 0);
		font-weight: 600;
	}

	.tooltip-rows {
		display: flex;
		flex-direction: column;
		gap: 4px;
		font-size: 10px;
		font-family: var(--font-mono);
	}

	.tooltip-row {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.tooltip-dot {
		width: 8px;
		height: 8px;
		border-radius: 2px;
		flex-shrink: 0;
	}

	.tooltip-label {
		color: oklch(0.55 0 0);
	}

	.tooltip-value {
		margin-left: auto;
	}

	.tooltip-divider {
		display: flex;
		align-items: center;
		gap: 8px;
		padding-top: 4px;
		margin-top: 2px;
		border-top: 1px solid oklch(0.22 0 0);
	}

	.tooltip-net {
		margin-left: auto;
	}
</style>
