<script lang="ts">
  import { onMount } from 'svelte';
  import PriceChart from '$lib/components/charts/PriceChart.svelte';
  import RadarChart from '$lib/components/charts/RadarChart.svelte';

  let selectedSymbol = $state('SPY');
  let selectedTimeframe = $state('5m');
  let activeIndicators = $state<string[]>(['SMA 20', 'RSI', 'MACD']);

  const watchlist = ['SPY', 'QQQ', 'NVDA', 'AAPL', 'TSLA', 'AMD', 'META', 'MSFT', 'AMZN', 'GOOGL'];

  const indicators = [
    { id: 'sma20', name: 'SMA 20', category: 'Trend', active: true },
    { id: 'sma50', name: 'SMA 50', category: 'Trend', active: false },
    { id: 'ema9', name: 'EMA 9', category: 'Trend', active: false },
    { id: 'vwap', name: 'VWAP', category: 'Trend', active: false },
    { id: 'bb', name: 'Bollinger Bands', category: 'Volatility', active: false },
    { id: 'kc', name: 'Keltner Channels', category: 'Volatility', active: false },
    { id: 'atr', name: 'ATR', category: 'Volatility', active: false },
    { id: 'rsi', name: 'RSI', category: 'Momentum', active: true },
    { id: 'macd', name: 'MACD', category: 'Momentum', active: true },
    { id: 'stoch', name: 'Stochastic', category: 'Momentum', active: false },
    { id: 'obv', name: 'OBV', category: 'Volume', active: false },
    { id: 'mfi', name: 'MFI', category: 'Volume', active: false },
  ];

  interface OHLCV { time: number; open: number; high: number; low: number; close: number; volume: number; }

  function generateSampleOHLCV(symbol: string): OHLCV[] {
    const basePrices: Record<string, number> = {
      SPY: 585, QQQ: 510, NVDA: 142, AAPL: 198, TSLA: 285,
      AMD: 178, META: 545, MSFT: 468, AMZN: 210, GOOGL: 188,
    };
    const base = basePrices[symbol] ?? 100;
    const data: OHLCV[] = [];
    let price = base;
    const now = Math.floor(Date.now() / 1000);
    const dayStart = now - 390 * 60;

    for (let i = 0; i < 78; i++) {
      const time = dayStart + i * 300;
      const volatility = base * 0.003;
      const drift = (Math.random() - 0.48) * volatility;
      const open = price;
      const high = open + Math.random() * volatility * 1.5;
      const low = open - Math.random() * volatility * 1.5;
      const close = open + drift;
      price = close;
      const volume = Math.floor(500000 + Math.random() * 2000000);
      data.push({ time, open, high: Math.max(open, close, high), low: Math.min(open, close, low), close, volume });
    }
    return data;
  }

  let chartData = $state<OHLCV[]>(generateSampleOHLCV('SPY'));

  const radarAxes = [
    { label: 'Momentum', value: 72, max: 100 },
    { label: 'Trend', value: 85, max: 100 },
    { label: 'Volatility', value: 45, max: 100 },
    { label: 'Volume', value: 68, max: 100 },
    { label: 'Support', value: 78, max: 100 },
    { label: 'Sentiment', value: 62, max: 100 },
  ];

  interface TechMetric { label: string; value: string; status: 'bullish' | 'bearish' | 'neutral'; }

  let technicals: TechMetric[] = $state([
    { label: 'RSI (14)', value: '58.4', status: 'neutral' },
    { label: 'MACD', value: '+1.23', status: 'bullish' },
    { label: 'ADX', value: '28.5', status: 'bullish' },
    { label: 'ATR', value: '3.42', status: 'neutral' },
    { label: 'OBV Trend', value: 'Rising', status: 'bullish' },
    { label: 'BB Position', value: '68%', status: 'neutral' },
    { label: 'VWAP vs Price', value: 'Above', status: 'bullish' },
    { label: 'Vol Ratio', value: '1.4x', status: 'neutral' },
  ]);

  let supportResistance = $state([
    { type: 'resistance', level: 592.50, label: 'R3', strength: 2 },
    { type: 'resistance', level: 589.00, label: 'R2', strength: 3 },
    { type: 'resistance', level: 587.20, label: 'R1', strength: 4 },
    { type: 'support', level: 583.50, label: 'S1', strength: 4 },
    { type: 'support', level: 581.00, label: 'S2', strength: 3 },
    { type: 'support', level: 578.50, label: 'S3', strength: 2 },
  ]);

  onMount(() => {
    chartData = generateSampleOHLCV(selectedSymbol);
  });

  function selectSymbol(sym: string) {
    selectedSymbol = sym;
    chartData = generateSampleOHLCV(sym);
  }

  function statusColor(s: string): string {
    if (s === 'bullish') return 'var(--bullish)';
    if (s === 'bearish') return 'var(--bearish)';
    return 'var(--text-secondary)';
  }

  function statusBg(s: string): string {
    if (s === 'bullish') return 'var(--bullish-bg)';
    if (s === 'bearish') return 'var(--bearish-bg)';
    return 'var(--bg-elevated)';
  }
</script>

<svelte:head>
  <title>Analysis - Scanify</title>
</svelte:head>

<div class="analysis-layout">
  <!-- Left: Watchlist sidebar -->
  <aside class="watchlist-sidebar">
    <div class="sidebar-header">
      <h3 class="sidebar-title">Watchlist</h3>
      <span class="sidebar-count">{watchlist.length}</span>
    </div>
    <div class="watchlist-items">
      {#each watchlist as sym (sym)}
        <button
          class="watchlist-item"
          class:watchlist-item--active={selectedSymbol === sym}
          onclick={() => selectSymbol(sym)}
        >
          <span class="watchlist-symbol">{sym}</span>
          <span class="watchlist-change" style="color: {Math.random() > 0.4 ? 'var(--bullish)' : 'var(--bearish)'};">
            {Math.random() > 0.4 ? '+' : '-'}{(Math.random() * 3).toFixed(2)}%
          </span>
        </button>
      {/each}
    </div>
  </aside>

  <!-- Center: Main chart area -->
  <div class="chart-area">
    <!-- Chart -->
    <div class="chart-panel panel-glass">
      {#if chartData.length > 0}
        <PriceChart symbol={selectedSymbol} data={chartData} timeframe={selectedTimeframe} height={460} showVolume={true} ontimeframechange={(tf) => selectedTimeframe = tf} />
      {:else}
        <div class="chart-placeholder">
          <div class="skeleton" style="width: 100%; height: 460px;"></div>
        </div>
      {/if}
    </div>

    <!-- Technical indicators grid -->
    <div class="indicators-panel">
      <h3 class="panel-label">Indicators</h3>
      <div class="indicator-chips">
        {#each indicators as ind (ind.id)}
          <button
            class="indicator-chip"
            class:indicator-chip--active={ind.active}
            onclick={() => ind.active = !ind.active}
          >
            <span class="chip-dot" style="background: {ind.active ? 'var(--accent-bright)' : 'var(--text-disabled)'};"></span>
            {ind.name}
          </button>
        {/each}
      </div>
    </div>
  </div>

  <!-- Right: Analysis panels -->
  <aside class="analysis-sidebar">
    <!-- Technical Summary -->
    <div class="sidebar-panel panel-glass">
      <h3 class="panel-label">Technical Summary</h3>
      <div class="tech-grid">
        {#each technicals as t (t.label)}
          <div class="tech-row">
            <span class="tech-label">{t.label}</span>
            <span class="tech-value" style="color: {statusColor(t.status)}; background: {statusBg(t.status)};">
              {t.value}
            </span>
          </div>
        {/each}
      </div>
    </div>

    <!-- Multi-Factor Radar -->
    <div class="sidebar-panel panel-glass">
      <h3 class="panel-label">Multi-Factor Score</h3>
      <div class="radar-container">
        <RadarChart data={radarAxes} size={200} />
      </div>
    </div>

    <!-- Support & Resistance -->
    <div class="sidebar-panel panel-glass">
      <h3 class="panel-label">Support & Resistance</h3>
      <div class="sr-list">
        {#each supportResistance as sr (sr.label)}
          <div class="sr-row">
            <span class="sr-label" style="color: {sr.type === 'resistance' ? 'var(--bearish)' : 'var(--bullish)'};">
              {sr.label}
            </span>
            <span class="sr-level">${sr.level.toFixed(2)}</span>
            <div class="sr-strength">
              {#each Array(5) as _, i}
                <div class="sr-pip" style="background: {i < sr.strength ? (sr.type === 'resistance' ? 'var(--bearish-dim)' : 'var(--bullish-dim)') : 'var(--bg-overlay)'};"></div>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    </div>
  </aside>
</div>

<style>
  .analysis-layout {
    display: grid;
    grid-template-columns: 160px 1fr 280px;
    height: 100%;
    overflow: hidden;
    gap: 1px;
    background: var(--border-subtle);
  }

  /* Watchlist Sidebar */
  .watchlist-sidebar {
    background: var(--bg-base);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .sidebar-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 14px;
    border-bottom: 1px solid var(--border-subtle);
  }

  .sidebar-title {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .sidebar-count {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    font-family: var(--font-mono);
  }

  .watchlist-items {
    flex: 1;
    overflow-y: auto;
    scrollbar-width: none;
  }

  .watchlist-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 8px 14px;
    border: none;
    background: transparent;
    cursor: pointer;
    transition: background-color 150ms;
    border-left: 2px solid transparent;
  }

  .watchlist-item:hover {
    background: var(--hover-overlay);
  }

  .watchlist-item--active {
    background: var(--accent-bg);
    border-left-color: var(--accent-bright);
  }

  .watchlist-symbol {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-primary);
  }

  .watchlist-change {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: 500;
  }

  /* Chart Area */
  .chart-area {
    background: var(--bg-void);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .chart-panel {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }

  .chart-placeholder {
    padding: 20px;
  }

  .indicators-panel {
    padding: 10px 16px;
    background: var(--bg-base);
    border-top: 1px solid var(--border-subtle);
  }

  .panel-label {
    font-size: var(--text-2xs);
    font-weight: 600;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 8px;
  }

  .indicator-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .indicator-chip {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 3px 10px;
    border-radius: var(--radius-full);
    font-size: var(--text-2xs);
    font-weight: 500;
    color: var(--text-tertiary);
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    cursor: pointer;
    transition: all 150ms;
  }

  .indicator-chip:hover {
    border-color: var(--border-default);
    color: var(--text-secondary);
  }

  .indicator-chip--active {
    color: var(--accent-bright);
    border-color: var(--accent-dim);
    background: var(--accent-bg);
  }

  .chip-dot {
    width: 5px;
    height: 5px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
  }

  /* Analysis Sidebar */
  .analysis-sidebar {
    background: var(--bg-base);
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    scrollbar-width: none;
    gap: 1px;
  }

  .sidebar-panel {
    padding: 14px;
    border-radius: 0;
    border: none;
    border-bottom: 1px solid var(--border-subtle);
    background: var(--bg-base);
    backdrop-filter: none;
  }

  /* Technical grid */
  .tech-grid {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .tech-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .tech-label {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
  }

  .tech-value {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: 600;
    padding: 1px 8px;
    border-radius: var(--radius-sm);
  }

  /* Radar */
  .radar-container {
    display: flex;
    justify-content: center;
    padding: 8px 0;
  }

  /* Support/Resistance */
  .sr-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .sr-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .sr-label {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: 700;
    width: 24px;
  }

  .sr-level {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    color: var(--text-primary);
    flex: 1;
  }

  .sr-strength {
    display: flex;
    gap: 2px;
  }

  .sr-pip {
    width: 8px;
    height: 4px;
    border-radius: var(--radius-full);
  }
</style>
