<script lang="ts">
  let activeTab = $state<'darkpool' | 'short' | 'etf'>('darkpool');

  const tabs: { id: 'darkpool' | 'short' | 'etf'; label: string; icon: string }[] = [
    { id: 'darkpool', label: 'Dark Pool', icon: 'DP' },
    { id: 'short', label: 'Short Interest', icon: 'SI' },
    { id: 'etf', label: 'ETF Flows', icon: 'EF' },
  ];

  // ── Dark Pool KPIs ──
  const dpKpis = [
    { label: 'Total Dark Pool Volume', value: '$2.4B', change: '+12.3%', up: true },
    { label: 'Block Trades Today', value: '847', change: '+64', up: true },
    { label: 'Avg Block Size', value: '$2.8M', change: '-$0.2M', up: false },
    { label: 'Dark/Lit Ratio', value: '38.2%', change: '+1.8%', up: true },
  ];

  // ── Dark Pool Trades ──
  const darkPoolTrades = [
    { time: '15:42:18', symbol: 'SPY', price: 585.42, size: 850000, notional: 49762000, exchange: 'FINRA ADF', side: 'buy' },
    { time: '15:41:05', symbol: 'NVDA', price: 142.50, size: 280000, notional: 39900000, exchange: 'IEX', side: 'buy' },
    { time: '15:39:33', symbol: 'AAPL', price: 198.75, size: 150000, notional: 29812500, exchange: 'FINRA ADF', side: 'sell' },
    { time: '15:37:12', symbol: 'MSFT', price: 448.20, size: 55000, notional: 24651000, exchange: 'CBOE BYX', side: 'buy' },
    { time: '15:34:48', symbol: 'TSLA', price: 268.90, size: 75000, notional: 20167500, exchange: 'IEX', side: 'sell' },
    { time: '15:32:21', symbol: 'AMD', price: 178.30, size: 95000, notional: 16938500, exchange: 'FINRA ADF', side: 'buy' },
    { time: '15:29:55', symbol: 'META', price: 542.60, size: 28000, notional: 15192800, exchange: 'CBOE EDGX', side: 'buy' },
    { time: '15:27:10', symbol: 'AMZN', price: 198.45, size: 62000, notional: 12303900, exchange: 'IEX', side: 'sell' },
    { time: '15:24:38', symbol: 'GOOGL', price: 178.90, size: 55000, notional: 9839500, exchange: 'FINRA ADF', side: 'buy' },
    { time: '15:21:44', symbol: 'QQQ', price: 505.80, size: 15000, notional: 7587000, exchange: 'CBOE BYX', side: 'sell' },
    { time: '15:18:22', symbol: 'JPM', price: 215.30, size: 22000, notional: 4736600, exchange: 'IEX', side: 'buy' },
    { time: '15:15:07', symbol: 'NFLX', price: 785.20, size: 5200, notional: 4083040, exchange: 'FINRA ADF', side: 'buy' },
  ];

  // ── Short Interest KPIs ──
  const siKpis = [
    { label: 'Most Shorted', value: 'GME', change: '42.1% SI', up: false },
    { label: 'Avg Short Interest', value: '8.2%', change: '+0.4%', up: false },
    { label: 'Highest SI Change', value: '+3.4%', change: 'CVNA', up: false },
    { label: 'Cost to Borrow', value: '12.5%', change: 'Avg CTB', up: false },
  ];

  // ── Short Interest Data ──
  const shortInterestData = [
    { symbol: 'GME', si: 42.1, shortFloat: 68.5, daysToCover: 8.2, borrowRate: 45.2, siChange: 3.4, squeezeScore: 92 },
    { symbol: 'AMC', si: 28.7, shortFloat: 52.3, daysToCover: 5.6, borrowRate: 32.8, siChange: 1.2, squeezeScore: 78 },
    { symbol: 'CVNA', si: 24.3, shortFloat: 41.2, daysToCover: 4.8, borrowRate: 28.5, siChange: 3.4, squeezeScore: 85 },
    { symbol: 'BBBY', si: 19.8, shortFloat: 35.7, daysToCover: 3.9, borrowRate: 22.1, siChange: -1.1, squeezeScore: 64 },
    { symbol: 'MARA', si: 16.2, shortFloat: 28.4, daysToCover: 3.2, borrowRate: 18.7, siChange: 0.8, squeezeScore: 58 },
    { symbol: 'RIVN', si: 14.5, shortFloat: 24.1, daysToCover: 2.8, borrowRate: 15.3, siChange: -0.5, squeezeScore: 45 },
    { symbol: 'PLTR', si: 8.3, shortFloat: 12.6, daysToCover: 1.9, borrowRate: 4.2, siChange: 0.3, squeezeScore: 32 },
    { symbol: 'SOFI', si: 7.1, shortFloat: 11.8, daysToCover: 1.7, borrowRate: 3.8, siChange: -0.2, squeezeScore: 28 },
    { symbol: 'NIO', si: 5.8, shortFloat: 9.4, daysToCover: 1.4, borrowRate: 2.9, siChange: 0.6, squeezeScore: 22 },
    { symbol: 'AAPL', si: 0.7, shortFloat: 1.2, daysToCover: 0.8, borrowRate: 0.3, siChange: -0.1, squeezeScore: 5 },
  ];

  // ── ETF Flows KPIs ──
  const efKpis = [
    { label: 'Total Inflows', value: '+$1.2B', change: '+18.5%', up: true },
    { label: 'Total Outflows', value: '-$890M', change: '-4.2%', up: false },
    { label: 'Net Flow', value: '+$310M', change: 'Bullish', up: true },
    { label: 'Most Active', value: 'SPY', change: '$420M flow', up: true },
  ];

  // ── ETF Flows Data ──
  const etfFlowData = [
    { etf: 'SPY', name: 'SPDR S&P 500', aum: 562.4, flow1d: 420, flow5d: 1850, direction: 'inflow', sentiment: 'Bullish' },
    { etf: 'QQQ', name: 'Invesco QQQ Trust', aum: 312.8, flow1d: 280, flow5d: 920, direction: 'inflow', sentiment: 'Bullish' },
    { etf: 'IWM', name: 'iShares Russell 2000', aum: 72.1, flow1d: -145, flow5d: -380, direction: 'outflow', sentiment: 'Bearish' },
    { etf: 'DIA', name: 'SPDR Dow Jones', aum: 35.6, flow1d: 85, flow5d: 210, direction: 'inflow', sentiment: 'Neutral' },
    { etf: 'XLF', name: 'Financial Select SPDR', aum: 42.3, flow1d: 120, flow5d: 450, direction: 'inflow', sentiment: 'Bullish' },
    { etf: 'XLK', name: 'Technology Select SPDR', aum: 68.9, flow1d: 195, flow5d: 680, direction: 'inflow', sentiment: 'Bullish' },
    { etf: 'GLD', name: 'SPDR Gold Shares', aum: 58.2, flow1d: -210, flow5d: -520, direction: 'outflow', sentiment: 'Bearish' },
    { etf: 'TLT', name: 'iShares 20+ Year Treasury', aum: 48.7, flow1d: -185, flow5d: -410, direction: 'outflow', sentiment: 'Bearish' },
    { etf: 'HYG', name: 'iShares iBoxx HY Corp', aum: 15.3, flow1d: 65, flow5d: 180, direction: 'inflow', sentiment: 'Neutral' },
    { etf: 'ARKK', name: 'ARK Innovation', aum: 6.8, flow1d: -350, flow5d: -890, direction: 'outflow', sentiment: 'Bearish' },
  ];

  // ── Formatters ──
  function fmtNotional(n: number): string {
    if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
    if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
    if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
    return `$${n}`;
  }

  function fmtShares(n: number): string {
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
    return `${n}`;
  }

  function fmtAUM(n: number): string {
    return `$${n.toFixed(1)}B`;
  }

  function fmtFlow(n: number): string {
    const prefix = n >= 0 ? '+' : '';
    if (Math.abs(n) >= 1000) return `${prefix}$${(n / 1000).toFixed(1)}B`;
    return `${prefix}$${n}M`;
  }

  function squeezeColor(score: number): string {
    if (score >= 80) return 'var(--bearish-bright)';
    if (score >= 60) return 'var(--warning-bright)';
    if (score >= 40) return 'var(--warning)';
    return 'var(--text-tertiary)';
  }
</script>

<svelte:head>
  <title>Institutional - Scanify</title>
</svelte:head>

<div class="page-root">
  <!-- Header -->
  <header class="page-header">
    <div class="header-left">
      <h1 class="page-title">Institutional</h1>
      <span class="page-subtitle">Dark pool, short interest & ETF flow analytics</span>
    </div>
    <div class="header-right">
      <div class="live-badge">
        <span class="live-dot"></span>
        LIVE
      </div>
    </div>
  </header>

  <!-- Tab Bar -->
  <nav class="tab-bar" role="tablist">
    {#each tabs as tab (tab.id)}
      <button
        type="button"
        role="tab"
        aria-selected={activeTab === tab.id}
        onclick={() => activeTab = tab.id}
        class="tab-btn"
        class:tab-btn--active={activeTab === tab.id}
      >
        <span class="tab-icon">{tab.icon}</span>
        {tab.label}
      </button>
    {/each}
  </nav>

  <!-- Content -->
  <div class="content-area">

    <!-- Dark Pool Tab -->
    {#if activeTab === 'darkpool'}
      <div class="tab-panel">
        <div class="kpi-row">
          {#each dpKpis as kpi}
            <div class="kpi-card glass-panel">
              <span class="kpi-label">{kpi.label}</span>
              <span class="kpi-value mono-nums">{kpi.value}</span>
              <span class="kpi-change mono-nums" class:kpi-up={kpi.up} class:kpi-down={!kpi.up}>
                {kpi.change}
              </span>
            </div>
          {/each}
        </div>

        <div class="feed-panel glass-panel">
          <div class="feed-header">
            <h2 class="feed-title">Recent Block Trades</h2>
            <span class="feed-count mono-nums">{darkPoolTrades.length} prints</span>
          </div>
          <div class="table-scroll">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Symbol</th>
                  <th class="col-right">Price</th>
                  <th class="col-right">Size</th>
                  <th class="col-right">Notional</th>
                  <th>Exchange</th>
                  <th class="col-center">Side</th>
                </tr>
              </thead>
              <tbody>
                {#each darkPoolTrades as trade, i}
                  <tr class="trade-row" style="animation-delay: {i * 40}ms">
                    <td class="mono-nums cell-time">{trade.time}</td>
                    <td class="cell-symbol">{trade.symbol}</td>
                    <td class="mono-nums col-right">${trade.price.toFixed(2)}</td>
                    <td class="mono-nums col-right">{fmtShares(trade.size)}</td>
                    <td class="mono-nums col-right cell-notional">{fmtNotional(trade.notional)}</td>
                    <td class="cell-exchange">{trade.exchange}</td>
                    <td class="col-center">
                      <span class="side-badge" class:side-buy={trade.side === 'buy'} class:side-sell={trade.side === 'sell'}>
                        {trade.side === 'buy' ? 'BUY' : 'SELL'}
                      </span>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
      </div>

    <!-- Short Interest Tab -->
    {:else if activeTab === 'short'}
      <div class="tab-panel">
        <div class="kpi-row">
          {#each siKpis as kpi}
            <div class="kpi-card glass-panel">
              <span class="kpi-label">{kpi.label}</span>
              <span class="kpi-value mono-nums">{kpi.value}</span>
              <span class="kpi-change mono-nums kpi-neutral">
                {kpi.change}
              </span>
            </div>
          {/each}
        </div>

        <div class="feed-panel glass-panel">
          <div class="feed-header">
            <h2 class="feed-title">Short Interest Rankings</h2>
            <span class="feed-count mono-nums">{shortInterestData.length} symbols</span>
          </div>
          <div class="table-scroll">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th class="col-right">Short Interest %</th>
                  <th class="col-right">Short Float</th>
                  <th class="col-right">Days to Cover</th>
                  <th class="col-right">Borrow Rate</th>
                  <th class="col-right">SI Change</th>
                  <th class="col-center">Squeeze Score</th>
                </tr>
              </thead>
              <tbody>
                {#each shortInterestData as row, i}
                  <tr class="trade-row" style="animation-delay: {i * 40}ms">
                    <td class="cell-symbol">{row.symbol}</td>
                    <td class="mono-nums col-right" style="color: {row.si > 20 ? 'var(--bearish-bright)' : row.si > 10 ? 'var(--warning-bright)' : 'var(--text-primary)'}">
                      {row.si.toFixed(1)}%
                    </td>
                    <td class="mono-nums col-right">{row.shortFloat.toFixed(1)}%</td>
                    <td class="mono-nums col-right">{row.daysToCover.toFixed(1)}</td>
                    <td class="mono-nums col-right" style="color: {row.borrowRate > 20 ? 'var(--bearish-bright)' : 'var(--text-primary)'}">
                      {row.borrowRate.toFixed(1)}%
                    </td>
                    <td class="mono-nums col-right">
                      <span class:si-up={row.siChange > 0} class:si-down={row.siChange < 0}>
                        {row.siChange > 0 ? '+' : ''}{row.siChange.toFixed(1)}%
                      </span>
                    </td>
                    <td class="col-center">
                      <div class="squeeze-cell">
                        <div class="squeeze-bar-track">
                          <div class="squeeze-bar-fill" style="width: {row.squeezeScore}%; background: {squeezeColor(row.squeezeScore)}"></div>
                        </div>
                        <span class="squeeze-value mono-nums" style="color: {squeezeColor(row.squeezeScore)}">{row.squeezeScore}</span>
                      </div>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
      </div>

    <!-- ETF Flows Tab -->
    {:else if activeTab === 'etf'}
      <div class="tab-panel">
        <div class="kpi-row">
          {#each efKpis as kpi}
            <div class="kpi-card glass-panel">
              <span class="kpi-label">{kpi.label}</span>
              <span class="kpi-value mono-nums">{kpi.value}</span>
              <span class="kpi-change mono-nums" class:kpi-up={kpi.up} class:kpi-down={!kpi.up}>
                {kpi.change}
              </span>
            </div>
          {/each}
        </div>

        <div class="feed-panel glass-panel">
          <div class="feed-header">
            <h2 class="feed-title">ETF Fund Flows</h2>
            <span class="feed-count mono-nums">{etfFlowData.length} funds</span>
          </div>
          <div class="table-scroll">
            <table class="data-table">
              <thead>
                <tr>
                  <th>ETF</th>
                  <th>Name</th>
                  <th class="col-right">AUM</th>
                  <th class="col-right">1D Flow</th>
                  <th class="col-right">5D Flow</th>
                  <th class="col-center">Direction</th>
                  <th class="col-center">Sentiment</th>
                </tr>
              </thead>
              <tbody>
                {#each etfFlowData as row, i}
                  <tr class="trade-row" style="animation-delay: {i * 40}ms">
                    <td class="cell-symbol">{row.etf}</td>
                    <td class="cell-name">{row.name}</td>
                    <td class="mono-nums col-right">{fmtAUM(row.aum)}</td>
                    <td class="mono-nums col-right">
                      <span class:flow-positive={row.flow1d >= 0} class:flow-negative={row.flow1d < 0}>
                        {fmtFlow(row.flow1d)}
                      </span>
                    </td>
                    <td class="mono-nums col-right">
                      <span class:flow-positive={row.flow5d >= 0} class:flow-negative={row.flow5d < 0}>
                        {fmtFlow(row.flow5d)}
                      </span>
                    </td>
                    <td class="col-center">
                      <span class="direction-badge" class:direction-in={row.direction === 'inflow'} class:direction-out={row.direction === 'outflow'}>
                        {#if row.direction === 'inflow'}
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 19V5m-7 7l7-7 7 7"/></svg>
                          Inflow
                        {:else}
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14m7-7l-7 7-7-7"/></svg>
                          Outflow
                        {/if}
                      </span>
                    </td>
                    <td class="col-center">
                      <span class="sentiment-badge"
                        class:sentiment-bull={row.sentiment === 'Bullish'}
                        class:sentiment-bear={row.sentiment === 'Bearish'}
                        class:sentiment-neutral={row.sentiment === 'Neutral'}
                      >
                        {row.sentiment}
                      </span>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    {/if}
  </div>
</div>

<style>
  /* ── Page Layout ── */
  .page-root {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }

  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 24px;
    flex-shrink: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .header-left {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .page-title {
    font-size: var(--text-xl);
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.02em;
  }

  .page-subtitle {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .live-badge {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: var(--text-2xs);
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--bullish-bright);
    background: var(--bullish-bg);
    border: 1px solid oklch(0.45 0.12 155 / 0.3);
    padding: 4px 10px;
    border-radius: var(--radius-full);
  }

  .live-dot {
    width: 6px;
    height: 6px;
    border-radius: var(--radius-full);
    background: var(--bullish-bright);
    animation: pulse-loading 1.5s ease-in-out infinite;
  }

  /* ── Tab Bar ── */
  .tab-bar {
    display: flex;
    gap: 4px;
    padding: 12px 24px;
    flex-shrink: 0;
    border-bottom: 1px solid var(--border-subtle);
    background: var(--bg-base);
  }

  .tab-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    border-radius: var(--radius-lg);
    padding: 8px 18px;
    font-size: var(--text-xs);
    font-weight: 600;
    transition: all var(--duration-normal) var(--ease-out-expo);
    background: transparent;
    color: var(--text-tertiary);
    border: 1px solid transparent;
    cursor: pointer;
  }

  .tab-btn:hover {
    color: var(--text-secondary);
    background: var(--bg-elevated);
  }

  .tab-btn--active {
    background: var(--accent-bg);
    color: var(--accent-bright);
    border-color: oklch(0.44 0.14 290 / 0.3);
  }

  .tab-icon {
    font-size: var(--text-2xs);
    font-weight: 800;
    font-family: var(--font-mono);
    background: oklch(0.95 0.01 260 / 0.06);
    padding: 2px 5px;
    border-radius: var(--radius-sm);
    letter-spacing: 0.04em;
  }

  .tab-btn--active .tab-icon {
    background: oklch(0.62 0.20 290 / 0.15);
    color: var(--accent-bright);
  }

  /* ── Content Area ── */
  .content-area {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    min-height: 0;
  }

  .tab-panel {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 20px 24px 32px;
    animation: fadeInPanel 300ms var(--ease-out-expo) both;
  }

  @keyframes fadeInPanel {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
  }

  /* ── Glass Panel ── */
  .glass-panel {
    background: oklch(0.14 0.02 260 / 0.7);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-xl);
    backdrop-filter: blur(var(--blur-panel));
    -webkit-backdrop-filter: blur(var(--blur-panel));
    box-shadow: var(--glow-xs);
  }

  /* ── KPI Row ── */
  .kpi-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
  }

  .kpi-card {
    padding: 16px 18px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    transition: box-shadow var(--duration-normal) ease, border-color var(--duration-normal) ease;
  }

  .kpi-card:hover {
    border-color: var(--border-default);
    box-shadow: var(--glow-sm);
  }

  .kpi-label {
    font-size: var(--text-2xs);
    font-weight: 500;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .kpi-value {
    font-size: var(--text-2xl);
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.1;
    letter-spacing: -0.02em;
  }

  .kpi-change {
    font-size: var(--text-2xs);
    font-weight: 600;
  }

  .kpi-up {
    color: var(--bullish-bright);
  }

  .kpi-down {
    color: var(--bearish-bright);
  }

  .kpi-neutral {
    color: var(--text-secondary);
  }

  /* ── Feed Panel ── */
  .feed-panel {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .feed-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 18px;
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
  }

  .feed-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .feed-count {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
  }

  /* ── Data Table ── */
  .table-scroll {
    overflow-x: auto;
    overflow-y: auto;
    max-height: 520px;
  }

  .data-table {
    width: 100%;
    border-spacing: 0;
  }

  .data-table thead {
    position: sticky;
    top: 0;
    z-index: var(--z-raised);
  }

  .data-table th {
    padding: 10px 14px;
    font-size: var(--text-2xs);
    font-weight: 600;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    text-align: left;
    background: var(--bg-surface);
    border-bottom: 1px solid var(--border-subtle);
    white-space: nowrap;
  }

  .data-table td {
    padding: 10px 14px;
    font-size: var(--text-sm);
    color: var(--text-secondary);
    border-bottom: 1px solid oklch(0.20 0.01 260 / 0.5);
    white-space: nowrap;
  }

  .col-right {
    text-align: right;
  }

  .col-center {
    text-align: center;
  }

  .trade-row {
    transition: background-color var(--duration-fast) ease;
    animation: rowFadeIn 400ms var(--ease-out-expo) both;
  }

  .trade-row:hover {
    background: var(--hover-overlay);
  }

  @keyframes rowFadeIn {
    from { opacity: 0; transform: translateX(-4px); }
    to { opacity: 1; transform: translateX(0); }
  }

  /* ── Cell Variants ── */
  .cell-time {
    color: var(--text-tertiary);
    font-size: var(--text-xs);
  }

  .cell-symbol {
    font-weight: 700;
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    letter-spacing: 0.02em;
  }

  .cell-notional {
    font-weight: 600;
    color: var(--accent-bright);
  }

  .cell-exchange {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
  }

  .cell-name {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    max-width: 180px;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* ── Side Badge ── */
  .side-badge {
    display: inline-flex;
    align-items: center;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    padding: 3px 10px;
    border-radius: var(--radius-full);
  }

  .side-buy {
    color: var(--bullish-bright);
    background: var(--bullish-bg);
    border: 1px solid oklch(0.45 0.12 155 / 0.3);
  }

  .side-sell {
    color: var(--bearish-bright);
    background: var(--bearish-bg);
    border: 1px solid oklch(0.42 0.12 25 / 0.3);
  }

  /* ── SI Change ── */
  .si-up {
    color: var(--bearish-bright);
  }

  .si-down {
    color: var(--bullish-bright);
  }

  /* ── Squeeze Score ── */
  .squeeze-cell {
    display: flex;
    align-items: center;
    gap: 8px;
    justify-content: center;
  }

  .squeeze-bar-track {
    width: 60px;
    height: 5px;
    background: oklch(0.20 0.01 260);
    border-radius: var(--radius-full);
    overflow: hidden;
  }

  .squeeze-bar-fill {
    height: 100%;
    border-radius: var(--radius-full);
    transition: width var(--duration-moderate) var(--ease-out-expo);
  }

  .squeeze-value {
    font-size: var(--text-2xs);
    font-weight: 700;
    min-width: 20px;
    text-align: right;
  }

  /* ── Flow Direction ── */
  .flow-positive {
    color: var(--bullish-bright);
  }

  .flow-negative {
    color: var(--bearish-bright);
  }

  .direction-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
    padding: 3px 10px;
    border-radius: var(--radius-full);
  }

  .direction-in {
    color: var(--bullish-bright);
    background: var(--bullish-bg);
    border: 1px solid oklch(0.45 0.12 155 / 0.3);
  }

  .direction-out {
    color: var(--bearish-bright);
    background: var(--bearish-bg);
    border: 1px solid oklch(0.42 0.12 25 / 0.3);
  }

  /* ── Sentiment Badge ── */
  .sentiment-badge {
    display: inline-flex;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
    padding: 3px 10px;
    border-radius: var(--radius-full);
  }

  .sentiment-bull {
    color: var(--bullish-bright);
    background: var(--bullish-bg);
    border: 1px solid oklch(0.45 0.12 155 / 0.3);
  }

  .sentiment-bear {
    color: var(--bearish-bright);
    background: var(--bearish-bg);
    border: 1px solid oklch(0.42 0.12 25 / 0.3);
  }

  .sentiment-neutral {
    color: var(--neutral-bright);
    background: var(--neutral-bg);
    border: 1px solid oklch(0.45 0.08 250 / 0.3);
  }

  /* ── Responsive ── */
  @media (max-width: 900px) {
    .kpi-row {
      grid-template-columns: repeat(2, 1fr);
    }
  }

  @media (max-width: 600px) {
    .kpi-row {
      grid-template-columns: 1fr;
    }

    .tab-bar {
      padding: 10px 16px;
      overflow-x: auto;
    }

    .tab-panel {
      padding: 16px;
    }
  }
</style>
