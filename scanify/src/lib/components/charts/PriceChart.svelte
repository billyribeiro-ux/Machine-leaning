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
				textColor: '#7a7a7a',
				fontSize: 11,
				fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace'
			},
			grid: {
				vertLines: { color: '#2a2a2a' },
				horzLines: { color: '#2a2a2a' }
			},
			crosshair: {
				mode: CrosshairMode.Normal,
				vertLine: {
					color: '#555555',
					width: 1,
					style: 2,
					labelBackgroundColor: '#333333'
				},
				horzLine: {
					color: '#555555',
					width: 1,
					style: 2,
					labelBackgroundColor: '#333333'
				}
			},
			rightPriceScale: {
				borderColor: '#2e2e2e',
				scaleMargins: {
					top: 0.05,
					bottom: showVolume ? 0.25 : 0.05
				}
			},
			timeScale: {
				borderColor: '#2e2e2e',
				timeVisible: true,
				secondsVisible: false
			},
			handleScale: true,
			handleScroll: true
		});

		chartInstance = chart;

		// Candlestick series
		const candles = chart.addSeries(CandlestickSeries, {
			upColor: '#26a69a',
			downColor: '#ef5350',
			borderUpColor: '#26a69a',
			borderDownColor: '#ef5350',
			wickUpColor: '#26a69a',
			wickDownColor: '#ef5350'
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
							? 'rgba(38, 166, 154, 0.4)'
							: 'rgba(239, 83, 80, 0.4)'
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
						? 'rgba(38, 166, 154, 0.4)'
						: 'rgba(239, 83, 80, 0.4)'
			}));
			volumeSeries.setData(volData);
		}
	});
</script>

<div class="chart-wrapper">
	<!-- Timeframe selector bar -->
	<div class="timeframe-bar">
		<span class="symbol-label">
			{symbol}
		</span>

		<div class="timeframe-group">
			{#each timeframes as tf}
				<button
					type="button"
					class="tf-btn {tf === timeframe ? 'tf-btn-active' : ''}"
					onclick={() => selectTimeframe(tf)}
				>
					{tf}
				</button>
			{/each}
		</div>

		{#if tooltipData}
			<div class="ohlc-bar">
				<span class="ohlc-label">O</span>
				<span class="ohlc-value">{tooltipData.open}</span>
				<span class="ohlc-label">H</span>
				<span class="ohlc-value">{tooltipData.high}</span>
				<span class="ohlc-label">L</span>
				<span class="ohlc-value">{tooltipData.low}</span>
				<span class="ohlc-label">C</span>
				<span class="ohlc-value">{tooltipData.close}</span>
				<span class={tooltipData.bullish ? 'change-bullish' : 'change-bearish'}>
					{tooltipData.changePercent}
				</span>
				{#if tooltipData.volume}
					<span class="ohlc-label">V</span>
					<span class="ohlc-value">{tooltipData.volume}</span>
				{/if}
			</div>
		{/if}
	</div>

	<!-- Chart container -->
	<div class="chart-area" style="height: {height}px;">
		<div bind:this={container} class="chart-container"></div>

		<!-- Floating tooltip -->
		{#if tooltipVisible && tooltipData}
			<div
				class="tooltip"
				style="left: {Math.min(tooltipX + 16, (container?.clientWidth ?? 500) - 200)}px;
					top: {Math.max(tooltipY - 80, 8)}px;"
			>
				<div class="tooltip-time">{tooltipData.time}</div>
				<div class="tooltip-grid">
					<span class="ohlc-label">Open</span>
					<span class="ohlc-value tooltip-value-right">{tooltipData.open}</span>
					<span class="ohlc-label">High</span>
					<span class="ohlc-value tooltip-value-right">{tooltipData.high}</span>
					<span class="ohlc-label">Low</span>
					<span class="ohlc-value tooltip-value-right">{tooltipData.low}</span>
					<span class="ohlc-label">Close</span>
					<span class="ohlc-value tooltip-value-right">{tooltipData.close}</span>
					{#if tooltipData.volume}
						<span class="ohlc-label">Vol</span>
						<span class="ohlc-value tooltip-value-right">{tooltipData.volume}</span>
					{/if}
				</div>
				<div
					class="tooltip-change {tooltipData.bullish ? 'change-bullish' : 'change-bearish'}"
				>
					{tooltipData.change} ({tooltipData.changePercent})
				</div>
			</div>
		{/if}
	</div>
</div>

<style>
	.chart-wrapper {
		display: flex;
		flex-direction: column;
		width: 100%;
	}

	.timeframe-bar {
		display: flex;
		align-items: center;
		gap: 4px;
		padding-inline: 12px;
		padding-block: 8px;
		border-bottom: 1px solid oklch(0.22 0 0);
	}

	.symbol-label {
		font-size: var(--text-xs, 0.75rem);
		font-weight: 600;
		color: oklch(0.90 0 0);
		letter-spacing: 0.05em;
		margin-right: 12px;
		font-family: var(--font-mono, ui-monospace, SFMono-Regular, 'SF Mono', Menlo, monospace);
	}

	.timeframe-group {
		display: flex;
		align-items: center;
		gap: 2px;
		border-radius: 6px;
		background-color: oklch(0.14 0 0);
		padding: 2px;
	}

	.tf-btn {
		padding-inline: 10px;
		padding-block: 4px;
		font-size: 11px;
		font-weight: 500;
		border-radius: var(--radius-lg, 8px);
		transition: all 150ms;
		color: oklch(0.55 0 0);
		background: transparent;
		border: none;
		cursor: pointer;
	}

	.tf-btn:hover {
		color: oklch(0.75 0 0);
		background-color: oklch(0.18 0 0);
	}

	.tf-btn-active {
		background-color: oklch(0.24 0.005 270);
		color: white;
		box-shadow: 0 1px 2px oklch(0 0 0 / 0.05);
	}

	.tf-btn-active:hover {
		background-color: oklch(0.24 0.005 270);
		color: white;
	}

	.ohlc-bar {
		margin-left: auto;
		display: flex;
		align-items: center;
		gap: 12px;
		font-size: 11px;
		font-family: var(--font-mono, ui-monospace, SFMono-Regular, 'SF Mono', Menlo, monospace);
	}

	.ohlc-label {
		color: oklch(0.50 0 0);
	}

	.ohlc-value {
		color: oklch(0.80 0 0);
	}

	.change-bullish {
		color: oklch(0.62 0.17 145);
	}

	.change-bearish {
		color: oklch(0.55 0.2 25);
	}

	.chart-area {
		position: relative;
		width: 100%;
	}

	.chart-container {
		width: 100%;
		height: 100%;
	}

	.tooltip {
		pointer-events: none;
		position: absolute;
		z-index: 50;
		border-radius: var(--radius-lg, 8px);
		border: 1px solid oklch(0.25 0 0);
		background-color: oklch(0.14 0 0 / 0.92);
		padding-inline: 12px;
		padding-block: 8px;
		box-shadow: 0 20px 25px -5px oklch(0 0 0 / 0.25);
		backdrop-filter: blur(4px);
	}

	.tooltip-time {
		font-size: 10px;
		color: oklch(0.50 0 0);
		margin-bottom: 6px;
	}

	.tooltip-grid {
		display: grid;
		grid-template-columns: auto 1fr;
		column-gap: 12px;
		row-gap: 2px;
		font-size: 11px;
		font-family: var(--font-mono, ui-monospace, SFMono-Regular, 'SF Mono', Menlo, monospace);
	}

	.tooltip-value-right {
		text-align: right;
	}

	.tooltip-change {
		margin-top: 6px;
		padding-top: 6px;
		border-top: 1px solid oklch(0.22 0 0);
		font-size: 11px;
		font-family: var(--font-mono, ui-monospace, SFMono-Regular, 'SF Mono', Menlo, monospace);
		text-align: right;
	}
</style>
