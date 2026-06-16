<script lang="ts">
  import InternalsBar from '$components/market/InternalsBar.svelte';
  import ExportToolbar from '$lib/components/ui/ExportToolbar.svelte';

  const indices = [
    { symbol: 'SPY', price: 502.34, change: 2.25, changePercent: 0.45 },
    { symbol: 'QQQ', price: 435.12, change: -1.02, changePercent: -0.23 },
    { symbol: 'IWM', price: 198.45, change: 0.24, changePercent: 0.12 },
    { symbol: 'DIA', price: 389.67, change: 1.45, changePercent: 0.37 },
  ];

  const topSignals = [
    { symbol: 'NVDA', direction: 'bullish' as const, name: 'Momentum Breakout', strength: 5, price: 875.30 },
    { symbol: 'TSLA', direction: 'bearish' as const, name: 'Volume Divergence', strength: 4, price: 245.10 },
    { symbol: 'AMD', direction: 'bullish' as const, name: 'Unusual Options', strength: 4, price: 165.40 },
    { symbol: 'META', direction: 'bullish' as const, name: 'Institutional Flow', strength: 3, price: 505.80 },
    { symbol: 'AMZN', direction: 'neutral' as const, name: 'Range Compression', strength: 3, price: 185.60 },
  ];

  const sectors = [
    { name: 'Technology', change: 1.2 },
    { name: 'Healthcare', change: -0.3 },
    { name: 'Financials', change: 0.8 },
    { name: 'Energy', change: -0.5 },
    { name: 'Consumer Disc.', change: 0.4 },
    { name: 'Industrials', change: 0.2 },
  ];

  function changeColor(val: number): string {
    if (val > 0) return 'var(--bullish)';
    if (val < 0) return 'var(--bearish)';
    return 'var(--text-secondary)';
  }

  function dirColor(dir: string): string {
    if (dir === 'bullish') return 'var(--bullish)';
    if (dir === 'bearish') return 'var(--bearish)';
    return 'var(--neutral)';
  }

  function dirBg(dir: string): string {
    if (dir === 'bullish') return 'var(--bullish-bg)';
    if (dir === 'bearish') return 'var(--bearish-bg)';
    return 'var(--neutral-bg)';
  }
</script>

<svelte:head>
  <title>Dashboard - Scanify</title>
</svelte:head>

<div class="dashboard-page">
  <!-- Page header -->
  <div class="page-header">
    <h1 class="page-title" style="color: var(--text-primary);">Dashboard</h1>
    <div class="header-actions">
      <ExportToolbar source="dashboard" />
      <div class="header-divider" style="background: var(--border-subtle);"></div>
      <span class="header-date" style="color: var(--text-tertiary);">
        {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric', year: 'numeric' })}
      </span>
    </div>
  </div>

  <!-- Grid layout -->
  <div class="dashboard-grid">

    <!-- Market Status panel - spans 2 cols -->
    <div class="market-status-panel panel">
      <div class="panel-header">
        <h2 class="panel-title" style="color: var(--text-primary);">Market Status</h2>
        <div class="market-status-indicator">
          <div class="status-dot" style="background: var(--bullish);"></div>
          <span class="status-label" style="color: var(--bullish);">Regular Hours</span>
        </div>
      </div>

      <!-- Indices row -->
      <div class="indices-grid">
        {#each indices as idx (idx.symbol)}
          <div class="index-card" style="background: var(--bg-base); border: 1px solid var(--border-subtle);">
            <span class="index-symbol" style="color: var(--text-primary);">{idx.symbol}</span>
            <div class="index-values">
              <span class="index-price" style="color: var(--text-primary);">
                {idx.price.toFixed(2)}
              </span>
              <span class="index-change" style="color: {changeColor(idx.changePercent)};">
                {idx.changePercent >= 0 ? '+' : ''}{idx.changePercent.toFixed(2)}%
              </span>
            </div>
          </div>
        {/each}
      </div>
    </div>

    <!-- Internals panel -->
    <div class="internals-panel panel">
      <h2 class="panel-title" style="color: var(--text-primary);">Market Internals</h2>
      <InternalsBar tick={456} trin={0.87} vix={15.2} advDecRatio={1.40} />
    </div>

    <!-- Top Signals panel - spans 2 cols -->
    <div class="signals-panel panel">
      <div class="panel-header">
        <h2 class="panel-title" style="color: var(--text-primary);">Top Signals</h2>
        <a href="/scanner" class="view-all-link" style="color: var(--accent);">View all</a>
      </div>
      <div class="signals-list">
        {#each topSignals as signal (signal.symbol)}
          <div
            class="signal-row"
            style="background: var(--bg-base); border: 1px solid var(--border-subtle);"
          >
            <!-- Direction dot -->
            <div class="direction-dot" style="background: {dirColor(signal.direction)};"></div>

            <!-- Symbol + name -->
            <div class="signal-info">
              <div class="signal-meta">
                <span class="signal-symbol" style="color: var(--text-primary);">{signal.symbol}</span>
                <span class="signal-name" style="color: var(--text-tertiary);">{signal.name}</span>
              </div>
            </div>

            <!-- Strength dots -->
            <div class="strength-dots">
              {#each Array(5) as _, si}
                <div
                  class="strength-bar"
                  style="background: {si < signal.strength ? dirColor(signal.direction) : 'var(--bg-overlay)'};"
                ></div>
              {/each}
            </div>

            <!-- Price -->
            <div class="signal-price-wrapper">
              <div class="signal-price" style="color: var(--text-primary);">${signal.price.toFixed(2)}</div>
            </div>
          </div>
        {/each}
      </div>
    </div>

    <!-- Sector Performance panel -->
    <div class="sectors-panel panel">
      <h2 class="panel-title" style="color: var(--text-primary);">Sector Performance</h2>
      <div class="sectors-list">
        {#each sectors as sector (sector.name)}
          <div class="sector-row" style="background: var(--bg-base); border: 1px solid var(--border-subtle);">
            <span class="sector-name" style="color: var(--text-primary);">{sector.name}</span>
            <span class="sector-change" style="color: {changeColor(sector.change)};">
              {sector.change >= 0 ? '+' : ''}{sector.change.toFixed(1)}%
            </span>
          </div>
        {/each}
      </div>
    </div>
  </div>
</div>

<style>
  /* Page layout */
  .dashboard-page {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: auto;
    padding: 20px;
    gap: 20px;
  }

  /* Page header */
  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }

  .page-title {
    font-size: var(--text-xl);
    font-weight: 700;
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .header-divider {
    width: 1px;
    height: 20px;
  }

  .header-date {
    font-size: var(--text-xs);
    font-family: var(--font-mono);
  }

  /* Dashboard grid */
  .dashboard-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 16px;
  }

  @media (min-width: 1024px) {
    .dashboard-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
  }

  /* Panel shared styles */
  .market-status-panel,
  .internals-panel,
  .signals-panel,
  .sectors-panel {
    padding: 20px;
  }

  .market-status-panel > * + *,
  .internals-panel > * + *,
  .signals-panel > * + *,
  .sectors-panel > * + * {
    margin-top: 16px;
  }

  @media (min-width: 1024px) {
    .market-status-panel,
    .signals-panel {
      grid-column: span 2;
    }
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .panel-title {
    font-size: var(--text-sm);
    font-weight: 600;
  }

  /* Market status indicator */
  .market-status-indicator {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
  }

  .status-label {
    font-size: var(--text-xs);
    font-weight: 500;
  }

  /* Indices grid */
  .indices-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }

  @media (min-width: 768px) {
    .indices-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
  }

  .index-card {
    border-radius: var(--radius-lg);
    padding: 12px;
  }

  .index-card > * + * {
    margin-top: 4px;
  }

  .index-symbol {
    font-size: var(--text-xs);
    font-weight: 700;
    font-family: var(--font-mono);
  }

  .index-values {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }

  .index-price {
    font-size: var(--text-lg);
    font-weight: 700;
    font-family: var(--font-mono);
  }

  .index-change {
    font-size: var(--text-xs);
    font-family: var(--font-mono);
    font-weight: 600;
  }

  /* Top Signals */
  .view-all-link {
    font-size: var(--text-xs);
    font-weight: 500;
    transition: color 150ms, background-color 150ms;
  }

  .signals-list > * + * {
    margin-top: 8px;
  }

  .signal-row {
    display: flex;
    align-items: center;
    gap: 12px;
    border-radius: var(--radius-lg);
    padding: 12px 16px;
    transition: color 150ms, background-color 150ms;
  }

  .direction-dot {
    width: 10px;
    height: 10px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
  }

  .signal-info {
    flex: 1;
    min-width: 0;
  }

  .signal-meta {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .signal-symbol {
    font-size: var(--text-sm);
    font-weight: 700;
    font-family: var(--font-mono);
  }

  .signal-name {
    font-size: 11px;
  }

  .strength-dots {
    display: flex;
    align-items: center;
    gap: 2px;
  }

  .strength-bar {
    height: 6px;
    width: 10px;
    border-radius: var(--radius-full);
  }

  .signal-price-wrapper {
    text-align: right;
    flex-shrink: 0;
  }

  .signal-price {
    font-size: var(--text-sm);
    font-family: var(--font-mono);
    font-weight: 700;
  }

  /* Sector Performance */
  .sectors-list > * + * {
    margin-top: 8px;
  }

  .sector-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-radius: var(--radius-lg);
    padding: 8px 12px;
  }

  .sector-name {
    font-size: var(--text-xs);
    font-weight: 500;
  }

  .sector-change {
    font-size: var(--text-xs);
    font-family: var(--font-mono);
    font-weight: 700;
  }
</style>
