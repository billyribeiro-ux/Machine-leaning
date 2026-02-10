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

<div class="relative w-full" bind:this={containerEl}>
	<svg
		width={containerWidth}
		{height}
		viewBox="0 0 {containerWidth} {height}"
		class="select-none"
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
			class="text-[11px] fill-[oklch(0.65_0_0)] font-medium"
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
				class="text-[8px] fill-[oklch(0.42_0_0)] font-mono"
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
				class="transition-[fill] duration-75"
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
				class="transition-[fill] duration-75"
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
				class="text-[8px] fill-[oklch(0.80_0.14_80)] font-mono font-semibold"
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
				class="text-[8px] fill-[oklch(0.45_0_0)] font-mono"
			>
				{sortedData[idx].strike}
			</text>
		{/each}

		<!-- Axis labels -->
		<text
			x={PADDING_LEFT - 4}
			y={PADDING_TOP - 6}
			text-anchor="end"
			class="text-[7px] fill-[oklch(0.40_0_0)] font-mono"
		>
			Gamma ($)
		</text>

		<text
			x={PADDING_LEFT + chartWidth / 2}
			y={height - 4}
			text-anchor="middle"
			class="text-[8px] fill-[oklch(0.40_0_0)] font-mono"
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
			<text x="18" y="8" class="text-[8px] fill-[oklch(0.60_0_0)] font-mono">Call GEX</text>
			<rect x="68" y="0" width="8" height="8" rx="1" fill="oklch(0.42 0.15 25 / 0.7)" />
			<text x="80" y="8" class="text-[8px] fill-[oklch(0.60_0_0)] font-mono">Put GEX</text>
			<line x1="130" y1="4" x2="146" y2="4" stroke="oklch(0.70 0.12 250)" stroke-width="2" />
			<text x="150" y="8" class="text-[8px] fill-[oklch(0.60_0_0)] font-mono">Net</text>
		</g>
	</svg>

	<!-- Tooltip -->
	{#if hoveredIndex !== null && sortedData[hoveredIndex]}
		{@const point = sortedData[hoveredIndex]}
		<div
			class="pointer-events-none absolute z-50 rounded-lg border border-[oklch(0.25_0_0)]
				bg-[oklch(0.14_0_0/0.94)] px-3 py-2 shadow-xl backdrop-blur-sm"
			style="left: {Math.min(mouseX + 14, containerWidth - 180)}px;
				top: {Math.max(mouseY - 90, 4)}px;"
		>
			<div class="text-[10px] text-[oklch(0.50_0_0)] mb-1.5 font-mono">
				Strike: <span class="text-[oklch(0.85_0_0)] font-semibold">{point.strike}</span>
			</div>
			<div class="flex flex-col gap-1 text-[10px] font-mono">
				<div class="flex items-center gap-2">
					<span class="w-2 h-2 rounded-sm bg-[oklch(0.55_0.15_145)]"></span>
					<span class="text-[oklch(0.55_0_0)]">Call GEX</span>
					<span class="text-[oklch(0.75_0.15_145)] ml-auto">{formatGamma(point.callGamma)}</span>
				</div>
				<div class="flex items-center gap-2">
					<span class="w-2 h-2 rounded-sm bg-[oklch(0.50_0.18_25)]"></span>
					<span class="text-[oklch(0.55_0_0)]">Put GEX</span>
					<span class="text-[oklch(0.70_0.16_25)] ml-auto">{formatGamma(point.putGamma)}</span>
				</div>
				<div class="flex items-center gap-2 pt-1 mt-0.5 border-t border-[oklch(0.22_0_0)]">
					<span class="w-2 h-2 rounded-sm bg-[oklch(0.65_0.12_250)]"></span>
					<span class="text-[oklch(0.55_0_0)]">Net GEX</span>
					<span
						class="ml-auto {point.netGamma >= 0
							? 'text-[oklch(0.75_0.15_145)]'
							: 'text-[oklch(0.70_0.16_25)]'}"
					>
						{point.netGamma >= 0 ? '+' : ''}{formatGamma(point.netGamma)}
					</span>
				</div>
			</div>
		</div>
	{/if}
</div>
