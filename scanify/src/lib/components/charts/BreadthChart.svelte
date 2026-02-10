<script lang="ts">
	interface BreadthDataPoint {
		time: number;
		advancers: number;
		decliners: number;
		unchanged: number;
	}

	interface Props {
		data: BreadthDataPoint[];
		height?: number;
	}

	let { data, height = 300 }: Props = $props();

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
	const PADDING_LEFT = 52;
	const PADDING_RIGHT = 16;
	const PADDING_TOP = 24;
	const PADDING_BOTTOM = 36;

	let chartWidth = $derived(containerWidth - PADDING_LEFT - PADDING_RIGHT);
	let chartHeight = $derived(height - PADDING_TOP - PADDING_BOTTOM);

	// Max total for Y axis
	let maxTotal = $derived(
		data.length > 0
			? Math.max(...data.map((d) => d.advancers + d.decliners + d.unchanged))
			: 100
	);

	// Scale helpers
	function xScale(index: number): number {
		return PADDING_LEFT + (data.length > 1 ? (index / (data.length - 1)) * chartWidth : chartWidth / 2);
	}

	function yScale(value: number): number {
		return PADDING_TOP + chartHeight - (maxTotal > 0 ? (value / maxTotal) * chartHeight : 0);
	}

	// SVG path builders for stacked areas
	function buildAreaPath(
		topValues: number[],
		bottomValues: number[]
	): string {
		if (data.length === 0) return '';

		let path = `M ${xScale(0)} ${yScale(topValues[0])}`;

		// Top edge (left to right)
		for (let i = 1; i < data.length; i++) {
			path += ` L ${xScale(i)} ${yScale(topValues[i])}`;
		}

		// Bottom edge (right to left)
		for (let i = data.length - 1; i >= 0; i--) {
			path += ` L ${xScale(i)} ${yScale(bottomValues[i])}`;
		}

		path += ' Z';
		return path;
	}

	// Stacked values: bottom is decliners, then unchanged, then advancers on top
	let stackedDecliners = $derived(data.map((d) => d.decliners));
	let stackedUnchanged = $derived(data.map((d) => d.decliners + d.unchanged));
	let stackedAdvancers = $derived(data.map((d) => d.decliners + d.unchanged + d.advancers));
	let baselineZeros = $derived(data.map(() => 0));

	let declinerPath = $derived(buildAreaPath(stackedDecliners, baselineZeros));
	let unchangedPath = $derived(buildAreaPath(stackedUnchanged, stackedDecliners));
	let advancerPath = $derived(buildAreaPath(stackedAdvancers, stackedUnchanged));

	// Advance/Decline line (net = advancers - decliners)
	let adLinePath = $derived.by(() => {
		if (data.length === 0) return '';

		const adValues = data.map((d) => d.advancers - d.decliners);
		const maxAd = Math.max(...adValues.map((v) => Math.abs(v)), 1);

		let path = '';
		for (let i = 0; i < data.length; i++) {
			const x = xScale(i);
			// Map A/D line to the top quarter of the chart
			const normalized = adValues[i] / maxAd;
			const y = PADDING_TOP + chartHeight * 0.15 - normalized * chartHeight * 0.12;
			path += i === 0 ? `M ${x} ${y}` : ` L ${x} ${y}`;
		}
		return path;
	});

	// Y-axis ticks
	let yTicks = $derived.by(() => {
		const ticks: number[] = [];
		const step = maxTotal > 0 ? Math.ceil(maxTotal / 5) : 20;
		for (let v = 0; v <= maxTotal; v += step) {
			ticks.push(v);
		}
		return ticks;
	});

	// X-axis labels (sample a few timestamps)
	let xTickIndices = $derived.by(() => {
		if (data.length <= 1) return data.length === 1 ? [0] : [];
		const count = Math.min(6, data.length);
		const step = (data.length - 1) / (count - 1);
		return Array.from({ length: count }, (_, i) => Math.round(i * step));
	});

	function formatTime(ts: number): string {
		const d = new Date(ts * 1000);
		return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
	}

	function formatDate(ts: number): string {
		const d = new Date(ts * 1000);
		return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	}

	function handleHover(e: MouseEvent) {
		if (!containerEl || data.length === 0) return;
		const rect = containerEl.getBoundingClientRect();
		const relX = e.clientX - rect.left;
		mouseX = relX;
		mouseY = e.clientY - rect.top;

		// Find nearest data index
		const chartX = relX - PADDING_LEFT;
		const fraction = chartX / chartWidth;
		const index = Math.round(fraction * (data.length - 1));
		hoveredIndex = Math.max(0, Math.min(data.length - 1, index));
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
		aria-label="Market Breadth Chart"
		onmousemove={handleHover}
		onmouseleave={handleLeave}
	>
		<!-- Title -->
		<text
			x={containerWidth / 2}
			y={14}
			text-anchor="middle"
			class="text-[11px] fill-[oklch(0.65_0_0)] font-medium"
		>
			Market Breadth
		</text>

		<!-- Y-axis grid lines and labels -->
		{#each yTicks as tick}
			<line
				x1={PADDING_LEFT}
				y1={yScale(tick)}
				x2={PADDING_LEFT + chartWidth}
				y2={yScale(tick)}
				stroke="oklch(0.18 0 0)"
				stroke-width="0.5"
			/>
			<text
				x={PADDING_LEFT - 6}
				y={yScale(tick)}
				text-anchor="end"
				dominant-baseline="middle"
				class="text-[9px] fill-[oklch(0.45_0_0)] font-mono"
			>
				{tick}
			</text>
		{/each}

		<!-- Stacked areas -->
		<path d={declinerPath} fill="oklch(0.45 0.16 25 / 0.5)" />
		<path d={unchangedPath} fill="oklch(0.35 0.02 250 / 0.3)" />
		<path d={advancerPath} fill="oklch(0.45 0.14 145 / 0.5)" />

		<!-- Area borders -->
		{#if data.length > 0}
			<path
				d={data
					.map((_, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)} ${yScale(stackedAdvancers[i])}`)
					.join(' ')}
				fill="none"
				stroke="oklch(0.55 0.15 145)"
				stroke-width="1"
			/>
			<path
				d={data
					.map((_, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)} ${yScale(stackedDecliners[i])}`)
					.join(' ')}
				fill="none"
				stroke="oklch(0.50 0.18 25)"
				stroke-width="1"
			/>
		{/if}

		<!-- A/D Line -->
		{#if adLinePath}
			<path
				d={adLinePath}
				fill="none"
				stroke="oklch(0.65 0.12 250)"
				stroke-width="1.5"
				stroke-dasharray="4 2"
				opacity="0.7"
			/>
			<text
				x={PADDING_LEFT + 4}
				y={PADDING_TOP + 6}
				class="text-[8px] fill-[oklch(0.55_0.10_250)] font-mono"
			>
				A/D Line
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
				{formatTime(data[idx].time)}
			</text>
			<text
				x={xScale(idx)}
				y={height - PADDING_BOTTOM + 24}
				text-anchor="middle"
				class="text-[7px] fill-[oklch(0.35_0_0)] font-mono"
			>
				{formatDate(data[idx].time)}
			</text>
		{/each}

		<!-- Crosshair on hover -->
		{#if hoveredIndex !== null}
			<line
				x1={xScale(hoveredIndex)}
				y1={PADDING_TOP}
				x2={xScale(hoveredIndex)}
				y2={PADDING_TOP + chartHeight}
				stroke="oklch(0.40 0 0)"
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
		<g transform="translate({PADDING_LEFT + chartWidth - 180}, {PADDING_TOP + 6})">
			<rect x="0" y="-4" width="175" height="18" rx="4" fill="oklch(0.12 0 0 / 0.85)" />
			<rect x="6" y="0" width="8" height="8" rx="1" fill="oklch(0.45 0.14 145 / 0.6)" />
			<text x="18" y="8" class="text-[8px] fill-[oklch(0.60_0_0)] font-mono">Advancers</text>
			<rect x="68" y="0" width="8" height="8" rx="1" fill="oklch(0.45 0.16 25 / 0.6)" />
			<text x="80" y="8" class="text-[8px] fill-[oklch(0.60_0_0)] font-mono">Decliners</text>
			<rect x="130" y="0" width="8" height="8" rx="1" fill="oklch(0.35 0.02 250 / 0.4)" />
			<text x="142" y="8" class="text-[8px] fill-[oklch(0.60_0_0)] font-mono">Unch</text>
		</g>
	</svg>

	<!-- Tooltip -->
	{#if hoveredIndex !== null && data[hoveredIndex]}
		{@const point = data[hoveredIndex]}
		{@const total = point.advancers + point.decliners + point.unchanged}
		<div
			class="pointer-events-none absolute z-50 rounded-lg border border-[oklch(0.25_0_0)]
				bg-[oklch(0.14_0_0/0.94)] px-3 py-2 shadow-xl backdrop-blur-sm"
			style="left: {Math.min(mouseX + 14, containerWidth - 170)}px;
				top: {Math.max(mouseY - 80, 4)}px;"
		>
			<div class="text-[10px] text-[oklch(0.50_0_0)] mb-1.5 font-mono">
				{formatTime(point.time)} - {formatDate(point.time)}
			</div>
			<div class="flex flex-col gap-1 text-[10px] font-mono">
				<div class="flex items-center gap-2">
					<span class="w-2 h-2 rounded-sm bg-[oklch(0.55_0.15_145)]"></span>
					<span class="text-[oklch(0.55_0_0)]">Adv</span>
					<span class="text-[oklch(0.75_0.15_145)] ml-auto">{point.advancers}</span>
					<span class="text-[oklch(0.45_0_0)] w-10 text-right">
						{total > 0 ? ((point.advancers / total) * 100).toFixed(0) : 0}%
					</span>
				</div>
				<div class="flex items-center gap-2">
					<span class="w-2 h-2 rounded-sm bg-[oklch(0.50_0.18_25)]"></span>
					<span class="text-[oklch(0.55_0_0)]">Dec</span>
					<span class="text-[oklch(0.70_0.16_25)] ml-auto">{point.decliners}</span>
					<span class="text-[oklch(0.45_0_0)] w-10 text-right">
						{total > 0 ? ((point.decliners / total) * 100).toFixed(0) : 0}%
					</span>
				</div>
				<div class="flex items-center gap-2">
					<span class="w-2 h-2 rounded-sm bg-[oklch(0.35_0.02_250)]"></span>
					<span class="text-[oklch(0.55_0_0)]">Unch</span>
					<span class="text-[oklch(0.70_0_0)] ml-auto">{point.unchanged}</span>
					<span class="text-[oklch(0.45_0_0)] w-10 text-right">
						{total > 0 ? ((point.unchanged / total) * 100).toFixed(0) : 0}%
					</span>
				</div>
				<div class="flex items-center gap-2 pt-1 mt-0.5 border-t border-[oklch(0.22_0_0)]">
					<span class="text-[oklch(0.55_0_0)]">A/D</span>
					<span
						class="ml-auto {point.advancers >= point.decliners
							? 'text-[oklch(0.75_0.15_145)]'
							: 'text-[oklch(0.70_0.16_25)]'}"
					>
						{point.advancers - point.decliners > 0 ? '+' : ''}{point.advancers - point.decliners}
					</span>
				</div>
			</div>
		</div>
	{/if}
</div>
