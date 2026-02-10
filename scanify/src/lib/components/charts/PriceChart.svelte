<script lang="ts">
	import {
		createChart,
		CandlestickSeries,
		HistogramSeries,
		CrosshairMode,
		ColorType,
		type IChartApi,
		type ISeriesApi
	} from 'lightweight-charts';
	import type { OHLCV } from '$lib/types/market';

	interface Props {
		symbol: string;
		data: OHLCV[];
		timeframe?: string;
		height?: number;
		showVolume?: boolean;
		ontimeframechange?: (tf: string) => void;
	}

	let {
		symbol,
		data,
		timeframe = '5m',
		height = 400,
		showVolume = true,
		ontimeframechange
	}: Props = $props();

	const timeframes = ['1m', '5m', '15m', '1H', '4H', 'D', 'W', 'M'];

	let container: HTMLDivElement | undefined = $state(undefined);
	let chartInstance: IChartApi | undefined = $state(undefined);
	let candleSeries: ISeriesApi<'Candlestick'> | undefined = $state(undefined);
	let volumeSeries: ISeriesApi<'Histogram'> | undefined = $state(undefined);

	let tooltipVisible = $state(false);
	let tooltipX = $state(0);
	let tooltipY = $state(0);
	let tooltipData = $state<{
		time: string;
		open: string;
		high: string;
		low: string;
		close: string;
		volume: string;
		change: string;
		changePercent: string;
		bullish: boolean;
	} | null>(null);

	function formatNumber(n: number, decimals = 2): string {
		return n.toLocaleString('en-US', {
			minimumFractionDigits: decimals,
			maximumFractionDigits: decimals
		});
	}

	function formatVolume(v: number): string {
		if (v >= 1_000_000_000) return (v / 1_000_000_000).toFixed(2) + 'B';
		if (v >= 1_000_000) return (v / 1_000_000).toFixed(2) + 'M';
		if (v >= 1_000) return (v / 1_000).toFixed(1) + 'K';
		return v.toString();
	}

	function formatTime(ts: number): string {
		const d = new Date(ts * 1000);
		return d.toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function selectTimeframe(tf: string) {
		ontimeframechange?.(tf);
	}

	// Create chart and series
	$effect(() => {
		if (!container) return;

		const chart = createChart(container, {
			width: container.clientWidth,
			height: height,
			layout: {
				background: { type: ColorType.Solid, color: 'transparent' },
				textColor: 'oklch(0.55 0 0)',
				fontSize: 11,
				fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace'
			},
			grid: {
				vertLines: { color: 'oklch(0.20 0 0)' },
				horzLines: { color: 'oklch(0.20 0 0)' }
			},
			crosshair: {
				mode: CrosshairMode.Normal,
				vertLine: {
					color: 'oklch(0.40 0 0)',
					width: 1,
					style: 2,
					labelBackgroundColor: 'oklch(0.25 0 0)'
				},
				horzLine: {
					color: 'oklch(0.40 0 0)',
					width: 1,
					style: 2,
					labelBackgroundColor: 'oklch(0.25 0 0)'
				}
			},
			rightPriceScale: {
				borderColor: 'oklch(0.22 0 0)',
				scaleMargins: {
					top: 0.05,
					bottom: showVolume ? 0.25 : 0.05
				}
			},
			timeScale: {
				borderColor: 'oklch(0.22 0 0)',
				timeVisible: true,
				secondsVisible: false
			},
			handleScale: true,
			handleScroll: true
		});

		chartInstance = chart;

		// Candlestick series
		const candles = chart.addSeries(CandlestickSeries, {
			upColor: 'oklch(0.62 0.17 145)',
			downColor: 'oklch(0.55 0.2 25)',
			borderUpColor: 'oklch(0.62 0.17 145)',
			borderDownColor: 'oklch(0.55 0.2 25)',
			wickUpColor: 'oklch(0.62 0.17 145)',
			wickDownColor: 'oklch(0.55 0.2 25)'
		});
		candleSeries = candles;

		// Volume histogram
		let volSeries: ISeriesApi<'Histogram'> | undefined;
		if (showVolume) {
			volSeries = chart.addSeries(HistogramSeries, {
				priceFormat: { type: 'volume' },
				priceScaleId: 'volume'
			});
			volumeSeries = volSeries;

			chart.priceScale('volume').applyOptions({
				scaleMargins: {
					top: 0.82,
					bottom: 0
				}
			});
		}

		// Set data
		if (data.length > 0) {
			const candleData = data.map((d) => ({
				time: d.time as any,
				open: d.open,
				high: d.high,
				low: d.low,
				close: d.close
			}));
			candles.setData(candleData);

			if (volSeries && showVolume) {
				const volData = data.map((d) => ({
					time: d.time as any,
					value: d.volume,
					color:
						d.close >= d.open
							? 'oklch(0.62 0.17 145 / 0.4)'
							: 'oklch(0.55 0.2 25 / 0.4)'
				}));
				volSeries.setData(volData);
			}

			chart.timeScale().fitContent();
		}

		// Crosshair tooltip
		chart.subscribeCrosshairMove((param) => {
			if (!param.time || !param.point) {
				tooltipVisible = false;
				return;
			}

			const candleItem = param.seriesData.get(candles) as any;
			if (!candleItem) {
				tooltipVisible = false;
				return;
			}

			const change = candleItem.close - candleItem.open;
			const changePercent = (change / candleItem.open) * 100;

			tooltipData = {
				time: formatTime(param.time as number),
				open: formatNumber(candleItem.open),
				high: formatNumber(candleItem.high),
				low: formatNumber(candleItem.low),
				close: formatNumber(candleItem.close),
				volume: volSeries
					? formatVolume(
							(param.seriesData.get(volSeries) as any)?.value ?? 0
						)
					: '',
				change: (change >= 0 ? '+' : '') + formatNumber(change),
				changePercent:
					(changePercent >= 0 ? '+' : '') +
					changePercent.toFixed(2) +
					'%',
				bullish: change >= 0
			};

			tooltipX = param.point.x;
			tooltipY = param.point.y;
			tooltipVisible = true;
		});

		// Resize observer
		const resizeObserver = new ResizeObserver((entries) => {
			for (const entry of entries) {
				const { width } = entry.contentRect;
				chart.applyOptions({ width });
			}
		});
		resizeObserver.observe(container);

		return () => {
			resizeObserver.disconnect();
			chart.remove();
			chartInstance = undefined;
			candleSeries = undefined;
			volumeSeries = undefined;
		};
	});

	// Update data reactively when data prop changes
	$effect(() => {
		if (!candleSeries || data.length === 0) return;

		const candleData = data.map((d) => ({
			time: d.time as any,
			open: d.open,
			high: d.high,
			low: d.low,
			close: d.close
		}));
		candleSeries.setData(candleData);

		if (volumeSeries && showVolume) {
			const volData = data.map((d) => ({
				time: d.time as any,
				value: d.volume,
				color:
					d.close >= d.open
						? 'oklch(0.62 0.17 145 / 0.4)'
						: 'oklch(0.55 0.2 25 / 0.4)'
			}));
			volumeSeries.setData(volData);
		}
	});
</script>

<div class="flex flex-col w-full">
	<!-- Timeframe selector bar -->
	<div class="flex items-center gap-1 px-3 py-2 border-b border-[oklch(0.22_0_0)]">
		<span
			class="text-xs font-semibold text-[oklch(0.90_0_0)] tracking-wider mr-3 font-mono"
		>
			{symbol}
		</span>

		<div class="flex items-center gap-0.5 rounded-md bg-[oklch(0.14_0_0)] p-0.5">
			{#each timeframes as tf}
				<button
					type="button"
					class="px-2.5 py-1 text-[11px] font-medium rounded transition-all duration-150
						{tf === timeframe
						? 'bg-[oklch(0.24_0.005_270)] text-white shadow-sm'
						: 'text-[oklch(0.55_0_0)] hover:text-[oklch(0.75_0_0)] hover:bg-[oklch(0.18_0_0)]'}"
					onclick={() => selectTimeframe(tf)}
				>
					{tf}
				</button>
			{/each}
		</div>

		{#if tooltipData}
			<div class="ml-auto flex items-center gap-3 text-[11px] font-mono">
				<span class="text-[oklch(0.50_0_0)]">O</span>
				<span class="text-[oklch(0.80_0_0)]">{tooltipData.open}</span>
				<span class="text-[oklch(0.50_0_0)]">H</span>
				<span class="text-[oklch(0.80_0_0)]">{tooltipData.high}</span>
				<span class="text-[oklch(0.50_0_0)]">L</span>
				<span class="text-[oklch(0.80_0_0)]">{tooltipData.low}</span>
				<span class="text-[oklch(0.50_0_0)]">C</span>
				<span class="text-[oklch(0.80_0_0)]">{tooltipData.close}</span>
				<span
					class="{tooltipData.bullish
						? 'text-[oklch(0.62_0.17_145)]'
						: 'text-[oklch(0.55_0.2_25)]'}"
				>
					{tooltipData.changePercent}
				</span>
				{#if tooltipData.volume}
					<span class="text-[oklch(0.50_0_0)]">V</span>
					<span class="text-[oklch(0.80_0_0)]">{tooltipData.volume}</span>
				{/if}
			</div>
		{/if}
	</div>

	<!-- Chart container -->
	<div class="relative w-full" style="height: {height}px;">
		<div bind:this={container} class="w-full h-full"></div>

		<!-- Floating tooltip -->
		{#if tooltipVisible && tooltipData}
			<div
				class="pointer-events-none absolute z-50 rounded-lg border border-[oklch(0.25_0_0)]
					bg-[oklch(0.14_0_0/0.92)] px-3 py-2 shadow-xl backdrop-blur-sm"
				style="left: {Math.min(tooltipX + 16, (container?.clientWidth ?? 500) - 200)}px;
					top: {Math.max(tooltipY - 80, 8)}px;"
			>
				<div class="text-[10px] text-[oklch(0.50_0_0)] mb-1.5">{tooltipData.time}</div>
				<div class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[11px] font-mono">
					<span class="text-[oklch(0.50_0_0)]">Open</span>
					<span class="text-[oklch(0.80_0_0)] text-right">{tooltipData.open}</span>
					<span class="text-[oklch(0.50_0_0)]">High</span>
					<span class="text-[oklch(0.80_0_0)] text-right">{tooltipData.high}</span>
					<span class="text-[oklch(0.50_0_0)]">Low</span>
					<span class="text-[oklch(0.80_0_0)] text-right">{tooltipData.low}</span>
					<span class="text-[oklch(0.50_0_0)]">Close</span>
					<span class="text-[oklch(0.80_0_0)] text-right">{tooltipData.close}</span>
					{#if tooltipData.volume}
						<span class="text-[oklch(0.50_0_0)]">Vol</span>
						<span class="text-[oklch(0.80_0_0)] text-right">{tooltipData.volume}</span>
					{/if}
				</div>
				<div
					class="mt-1.5 pt-1.5 border-t border-[oklch(0.22_0_0)] text-[11px] font-mono text-right
						{tooltipData.bullish
						? 'text-[oklch(0.62_0.17_145)]'
						: 'text-[oklch(0.55_0.2_25)]'}"
				>
					{tooltipData.change} ({tooltipData.changePercent})
				</div>
			</div>
		{/if}
	</div>
</div>
