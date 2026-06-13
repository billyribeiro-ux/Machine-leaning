<script lang="ts">
  import FlowFeed from '$components/options/FlowFeed.svelte';

  let activeTab = $state<'flow' | 'unusual' | 'chain'>('flow');

  const tabs: { id: 'flow' | 'unusual' | 'chain'; label: string }[] = [
    { id: 'flow', label: 'Flow' },
    { id: 'unusual', label: 'Unusual Activity' },
    { id: 'chain', label: 'Chain' },
  ];

  const now = Date.now();

  const flowItems = [
    { id: 'f1',  symbol: 'AAPL',  timestamp: new Date(now - 12_000).toISOString(),  type: 'call' as const, strike: 180, expiration: '2026-03-21', side: 'buy' as const,  size: 500,  premium: 245_000,   isUnusual: true,  isSweep: false },
    { id: 'f2',  symbol: 'NVDA',  timestamp: new Date(now - 25_000).toISOString(),  type: 'call' as const, strike: 900, expiration: '2026-04-17', side: 'buy' as const,  size: 1500, premium: 2_250_000, isUnusual: true,  isSweep: true },
    { id: 'f3',  symbol: 'TSLA',  timestamp: new Date(now - 38_000).toISOString(),  type: 'put' as const,  strike: 240, expiration: '2026-03-14', side: 'buy' as const,  size: 1200, premium: 456_000,   isUnusual: false, isSweep: false },
    { id: 'f4',  symbol: 'MSFT',  timestamp: new Date(now - 52_000).toISOString(),  type: 'call' as const, strike: 420, expiration: '2026-03-21', side: 'sell' as const, size: 200,  premium: 178_000,   isUnusual: false, isSweep: false },
    { id: 'f5',  symbol: 'AMD',   timestamp: new Date(now - 68_000).toISOString(),  type: 'call' as const, strike: 170, expiration: '2026-04-17', side: 'buy' as const,  size: 800,  premium: 320_000,   isUnusual: true,  isSweep: true },
    { id: 'f6',  symbol: 'META',  timestamp: new Date(now - 79_000).toISOString(),  type: 'put' as const,  strike: 500, expiration: '2026-03-14', side: 'sell' as const, size: 150,  premium: 195_000,   isUnusual: false, isSweep: false },
    { id: 'f7',  symbol: 'GOOGL', timestamp: new Date(now - 95_000).toISOString(),  type: 'call' as const, strike: 155, expiration: '2026-04-17', side: 'buy' as const,  size: 600,  premium: 210_000,   isUnusual: false, isSweep: false },
    { id: 'f8',  symbol: 'AMZN',  timestamp: new Date(now - 112_000).toISOString(), type: 'call' as const, strike: 190, expiration: '2026-03-21', side: 'buy' as const,  size: 400,  premium: 168_000,   isUnusual: true,  isSweep: false },
    { id: 'f9',  symbol: 'SPY',   timestamp: new Date(now - 130_000).toISOString(), type: 'put' as const,  strike: 495, expiration: '2026-03-14', side: 'buy' as const,  size: 2000, premium: 540_000,   isUnusual: true,  isSweep: true },
    { id: 'f10', symbol: 'QQQ',   timestamp: new Date(now - 145_000).toISOString(), type: 'call' as const, strike: 440, expiration: '2026-04-17', side: 'buy' as const,  size: 350,  premium: 287_000,   isUnusual: false, isSweep: false },
  ];

  const unusualData = [
    { symbol: 'NVDA', strike: '900C', expiry: 'Apr 17', volume: 12_500, oi: 3200, ratio: 3.9, premium: '$8.9M', sentiment: 'Bullish' },
    { symbol: 'AAPL', strike: '185C', expiry: 'Mar 21', volume: 8_400,  oi: 5100, ratio: 1.6, premium: '$2.1M', sentiment: 'Bullish' },
    { symbol: 'TSLA', strike: '230P', expiry: 'Mar 14', volume: 6_200,  oi: 1800, ratio: 3.4, premium: '$3.4M', sentiment: 'Bearish' },
    { symbol: 'SPY',  strike: '490P', expiry: 'Mar 21', volume: 15_600, oi: 8900, ratio: 1.8, premium: '$5.2M', sentiment: 'Bearish' },
    { symbol: 'AMD',  strike: '175C', expiry: 'Apr 17', volume: 9_800,  oi: 2400, ratio: 4.1, premium: '$1.8M', sentiment: 'Bullish' },
  ];

  function sentimentColor(s: string): string {
    return s === 'Bullish' ? 'var(--bullish)' : 'var(--bearish)';
  }

  function sentimentBg(s: string): string {
    return s === 'Bullish' ? 'var(--bullish-bg)' : 'var(--bearish-bg)';
  }
</script>

<svelte:head>
  <title>Options - Scanify</title>
</svelte:head>

<div class="options-layout">
  <!-- Header -->
  <div class="options-header" style="border-bottom: 1px solid var(--border-subtle);">
    <h1 class="options-title" style="color: var(--text-primary);">Options</h1>
    <a href="/options/flow" class="flow-link" style="color: var(--accent);">Full Flow View</a>
  </div>

  <!-- Tab switcher -->
  <div class="tab-bar" style="border-bottom: 1px solid var(--border-subtle);">
    {#each tabs as tab (tab.id)}
      <button
        type="button"
        onclick={() => activeTab = tab.id}
        class="tab-button"
        style="background: {activeTab === tab.id ? 'var(--accent-bg)' : 'var(--bg-elevated)'};
               color: {activeTab === tab.id ? 'var(--accent-bright)' : 'var(--text-secondary)'};
               border: 1px solid {activeTab === tab.id ? 'var(--accent-dim)' : 'var(--border-subtle)'};"
      >
        {tab.label}
      </button>
    {/each}
  </div>

  <!-- Tab content -->
  <div class="tab-content">
    {#if activeTab === 'flow'}
      <FlowFeed items={flowItems} />

    {:else if activeTab === 'unusual'}
      <!-- Unusual Activity Table -->
      <div class="unusual-scroll">
        <div class="panel unusual-panel">
          <div class="unusual-header" style="border-bottom: 1px solid var(--border-subtle);">
            <span class="unusual-title" style="color: var(--text-primary);">Unusual Options Activity</span>
            <span class="unusual-count" style="color: var(--text-tertiary);">{unusualData.length} entries</span>
          </div>
          <div class="table-scroll">
            <table class="unusual-table">
              <thead class="table-head" style="background: var(--bg-elevated);">
                <tr style="border-bottom: 1px solid var(--border-subtle);">
                  <th class="th-cell th-left th-first" style="color: var(--text-tertiary);">Symbol</th>
                  <th class="th-cell th-left" style="color: var(--text-tertiary);">Strike</th>
                  <th class="th-cell th-left" style="color: var(--text-tertiary);">Expiry</th>
                  <th class="th-cell th-right" style="color: var(--text-tertiary);">Volume</th>
                  <th class="th-cell th-right" style="color: var(--text-tertiary);">OI</th>
                  <th class="th-cell th-right" style="color: var(--text-tertiary);">Vol/OI</th>
                  <th class="th-cell th-right" style="color: var(--text-tertiary);">Premium</th>
                  <th class="th-cell th-center" style="color: var(--text-tertiary);">Sentiment</th>
                </tr>
              </thead>
              <tbody>
                {#each unusualData as row, i (row.symbol + row.strike)}
                  <tr
                    class="table-row"
                    style="background: {i % 2 === 0 ? 'var(--bg-surface)' : 'transparent'}; border-bottom: 1px solid var(--border-subtle);"
                  >
                    <td class="td-symbol" style="color: var(--text-primary);">{row.symbol}</td>
                    <td class="td-cell td-mono" style="color: var(--text-secondary);">{row.strike}</td>
                    <td class="td-cell" style="color: var(--text-tertiary);">{row.expiry}</td>
                    <td class="td-cell td-right td-mono" style="color: var(--text-secondary);">{row.volume.toLocaleString()}</td>
                    <td class="td-cell td-right td-mono" style="color: var(--text-secondary);">{row.oi.toLocaleString()}</td>
                    <td class="td-cell td-right td-mono td-bold" style="color: var(--warning-bright);">{row.ratio.toFixed(1)}x</td>
                    <td class="td-cell td-right td-mono td-semibold" style="color: var(--text-primary);">{row.premium}</td>
                    <td class="td-cell td-center">
                      <span
                        class="sentiment-badge"
                        style="background: {sentimentBg(row.sentiment)};
                               color: {sentimentColor(row.sentiment)};
                               border: 1px solid {row.sentiment === 'Bullish' ? 'oklch(0.45 0.12 155 / 0.3)' : 'oklch(0.42 0.12 25 / 0.3)'};"
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

    {:else if activeTab === 'chain'}
      <!-- Chain placeholder -->
      <div class="chain-placeholder">
        <div class="chain-icon-box" style="background: var(--bg-elevated); border: 1px solid var(--border-subtle);">
          <svg class="chain-icon" style="color: var(--text-disabled);" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <p class="chain-title" style="color: var(--text-secondary);">Select a symbol to view options chain</p>
        <p class="chain-subtitle" style="color: var(--text-tertiary);">Use the search bar or click a symbol from the flow</p>
      </div>
    {/if}
  </div>
</div>

<style>
  .options-layout {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }

  .options-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    flex-shrink: 0;
  }

  .options-title {
    font-size: var(--text-lg);
    font-weight: 700;
  }

  .flow-link {
    font-size: var(--text-xs);
    font-weight: 500;
  }

  .tab-bar {
    display: flex;
    gap: 4px;
    padding: 12px 20px;
    flex-shrink: 0;
  }

  .tab-button {
    border-radius: var(--radius-lg);
    padding: 8px 16px;
    font-size: var(--text-xs);
    font-weight: 500;
    transition: all 150ms;
  }

  .tab-content {
    flex: 1;
    overflow: hidden;
    min-height: 0;
  }

  /* Unusual Activity */
  .unusual-scroll {
    height: 100%;
    overflow: auto;
  }

  .unusual-panel {
    margin: 20px;
    overflow: hidden;
  }

  .unusual-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
  }

  .unusual-title {
    font-size: var(--text-sm);
    font-weight: 600;
  }

  .unusual-count {
    font-size: var(--text-2xs);
  }

  .table-scroll {
    overflow: auto;
  }

  .unusual-table {
    width: 100%;
    font-size: var(--text-xs);
  }

  .table-head {
    position: sticky;
    top: 0;
    z-index: 10;
  }

  .th-cell {
    padding: 10px 12px;
    font-weight: 500;
  }

  .th-first {
    padding-left: 16px;
  }

  .th-left {
    text-align: left;
  }

  .th-right {
    text-align: right;
  }

  .th-center {
    text-align: center;
  }

  .table-row {
    transition: color 150ms, background-color 150ms;
  }

  .td-symbol {
    padding: 10px 16px;
    font-weight: 700;
    font-family: var(--font-mono);
  }

  .td-cell {
    padding: 10px 12px;
  }

  .td-mono {
    font-family: var(--font-mono);
  }

  .td-right {
    text-align: right;
  }

  .td-center {
    text-align: center;
  }

  .td-bold {
    font-weight: 700;
  }

  .td-semibold {
    font-weight: 600;
  }

  .sentiment-badge {
    display: inline-flex;
    align-items: center;
    border-radius: var(--radius-full);
    padding: 2px 8px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
  }

  /* Chain placeholder */
  .chain-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    gap: 16px;
  }

  .chain-icon-box {
    width: 64px;
    height: 64px;
    border-radius: var(--radius-xl);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .chain-icon {
    height: 32px;
    width: 32px;
  }

  .chain-title {
    font-size: var(--text-sm);
    font-weight: 500;
  }

  .chain-subtitle {
    font-size: var(--text-xs);
  }
</style>
