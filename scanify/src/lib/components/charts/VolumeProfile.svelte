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

<div class="relative inline-block">
	<svg
		{width}
		{height}
		viewBox="0 0 {width} {height}"
		class="select-none"
		role="img"
		aria-label="Volume Profile"
	>
		<!-- Title -->
		<text
			x={width / 2}
			y={14}
			text-anchor="middle"
			class="text-[10px] fill-[oklch(0.50_0_0)] font-mono"
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
				class="text-[9px] font-mono {isPoc
					? 'fill-[oklch(0.85_0.12_80)]'
					: 'fill-[oklch(0.50_0_0)]'}"
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
				class="cursor-crosshair transition-[fill] duration-100"
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
				class="cursor-crosshair transition-[fill] duration-100"
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
					class="text-[8px] fill-[oklch(0.85_0.12_80)] font-mono font-bold"
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
					class="text-[7px] fill-[oklch(0.60_0.10_250)] font-mono"
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
					class="text-[7px] fill-[oklch(0.60_0.10_250)] font-mono"
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
			class="pointer-events-none absolute z-50 rounded-lg border border-[oklch(0.25_0_0)]
				bg-[oklch(0.14_0_0/0.94)] px-3 py-2 shadow-xl backdrop-blur-sm"
			style="left: {mouseX + 12}px; top: {mouseY - 60}px;"
		>
			<div class="text-[10px] text-[oklch(0.50_0_0)] mb-1">
				Price: <span class="text-[oklch(0.85_0_0)] font-mono">{formatPrice(level.price)}</span>
			</div>
			<div class="flex flex-col gap-0.5 text-[10px] font-mono">
				<div class="flex items-center gap-2">
					<span class="w-1.5 h-1.5 rounded-full bg-[oklch(0.55_0.15_145)]"></span>
					<span class="text-[oklch(0.55_0_0)]">Buy</span>
					<span class="text-[oklch(0.75_0.15_145)] ml-auto">{formatVolume(level.buyVolume)}</span>
				</div>
				<div class="flex items-center gap-2">
					<span class="w-1.5 h-1.5 rounded-full bg-[oklch(0.50_0.18_25)]"></span>
					<span class="text-[oklch(0.55_0_0)]">Sell</span>
					<span class="text-[oklch(0.70_0.16_25)] ml-auto">{formatVolume(level.sellVolume)}</span>
				</div>
				<div
					class="flex items-center gap-2 pt-1 mt-1 border-t border-[oklch(0.22_0_0)]"
				>
					<span class="text-[oklch(0.55_0_0)]">Total</span>
					<span class="text-[oklch(0.80_0_0)] ml-auto">{formatVolume(level.volume)}</span>
				</div>
			</div>
		</div>
	{/if}
</div>
