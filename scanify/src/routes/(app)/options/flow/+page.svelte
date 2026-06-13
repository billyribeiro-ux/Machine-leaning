<script lang="ts">
  import FlowFeed from '$components/options/FlowFeed.svelte';
  import ExportToolbar from '$lib/components/ui/ExportToolbar.svelte';

  let typeFilter = $state<'all' | 'calls' | 'puts'>('all');
  let minPremium = $state('');

  const now = Date.now();

  const allFlowItems = [
    { id: 'fl1',  symbol: 'NVDA',  timestamp: new Date(now - 10_000).toISOString(),  type: 'call' as const, strike: 900,  expiration: '2026-03-21', side: 'buy' as const,  size: 1500, premium: 2_250_000, isUnusual: true,  isSweep: true },
    { id: 'fl2',  symbol: 'AAPL',  timestamp: new Date(now - 30_000).toISOString(),  type: 'put' as const,  strike: 180,  expiration: '2026-02-28', side: 'buy' as const,  size: 800,  premium: 480_000,   isUnusual: false, isSweep: false },
    { id: 'fl3',  symbol: 'TSLA',  timestamp: new Date(now - 60_000).toISOString(),  type: 'call' as const, strike: 260,  expiration: '2026-03-21', side: 'buy' as const,  size: 2200, premium: 1_980_000, isUnusual: true,  isSweep: true },
    { id: 'fl4',  symbol: 'META',  timestamp: new Date(now - 95_000).toISOString(),  type: 'call' as const, strike: 520,  expiration: '2026-04-17', side: 'buy' as const,  size: 500,  premium: 750_000,   isUnusual: false, isSweep: false },
    { id: 'fl5',  symbol: 'SPY',   timestamp: new Date(now - 130_000).toISOString(), type: 'put' as const,  strike: 495,  expiration: '2026-02-21', side: 'sell' as const, size: 3000, premium: 1_200_000, isUnusual: true,  isSweep: false },
    { id: 'fl6',  symbol: 'AMD',   timestamp: new Date(now - 170_000).toISOString(), type: 'call' as const, strike: 175,  expiration: '2026-03-21', side: 'buy' as const,  size: 1200, premium: 840_000,   isUnusual: true,  isSweep: true },
    { id: 'fl7',  symbol: 'AMZN',  timestamp: new Date(now - 210_000).toISOString(), type: 'call' as const, strike: 190,  expiration: '2026-04-17', side: 'buy' as const,  size: 650,  premium: 520_000,   isUnusual: false, isSweep: false },
    { id: 'fl8',  symbol: 'GOOGL', timestamp: new Date(now - 250_000).toISOString(), type: 'put' as const,  strike: 148,  expiration: '2026-02-28', side: 'buy' as const,  size: 400,  premium: 180_000,   isUnusual: false, isSweep: false },
    { id: 'fl9',  symbol: 'COIN',  timestamp: new Date(now - 290_000).toISOString(), type: 'call' as const, strike: 240,  expiration: '2026-03-21', side: 'buy' as const,  size: 1800, premium: 2_700_000, isUnusual: true,  isSweep: true },
    { id: 'fl10', symbol: 'QQQ',   timestamp: new Date(now - 330_000).toISOString(), type: 'put' as const,  strike: 430,  expiration: '2026-02-21', side: 'sell' as const, size: 2500, premium: 1_625_000, isUnusual: false, isSweep: false },
    { id: 'fl11', symbol: 'NFLX',  timestamp: new Date(now - 370_000).toISOString(), type: 'call' as const, strike: 650,  expiration: '2026-04-17', side: 'buy' as const,  size: 350,  premium: 630_000,   isUnusual: false, isSweep: false },
    { id: 'fl12', symbol: 'MSFT',  timestamp: new Date(now - 410_000).toISOString(), type: 'call' as const, strike: 425,  expiration: '2026-03-21', side: 'buy' as const,  size: 900,  premium: 810_000,   isUnusual: true,  isSweep: false },
    { id: 'fl13', symbol: 'BA',    timestamp: new Date(now - 450_000).toISOString(), type: 'call' as const, strike: 210,  expiration: '2026-03-21', side: 'buy' as const,  size: 1100, premium: 550_000,   isUnusual: false, isSweep: true },
    { id: 'fl14', symbol: 'PLTR',  timestamp: new Date(now - 490_000).toISOString(), type: 'call' as const, strike: 27,   expiration: '2026-04-17', side: 'buy' as const,  size: 5000, premium: 400_000,   isUnusual: true,  isSweep: false },
    { id: 'fl15', symbol: 'SMCI',  timestamp: new Date(now - 530_000).toISOString(), type: 'put' as const,  strike: 700,  expiration: '2026-02-28', side: 'buy' as const,  size: 600,  premium: 960_000,   isUnusual: true,  isSweep: true },
  ];

  let totalPremium = $derived(allFlowItems.reduce((s, i) => s + i.premium, 0));
  let callCount = $derived(allFlowItems.filter(i => i.type === 'call').length);
  let putCount = $derived(allFlowItems.filter(i => i.type === 'put').length);
  let callPutRatio = $derived(putCount > 0 ? (callCount / putCount).toFixed(2) : 'N/A');
  let sweepCount = $derived(allFlowItems.filter(i => i.isSweep).length);

  let filteredItems = $derived.by(() => {
    let items = allFlowItems;
    if (typeFilter === 'calls') items = items.filter(i => i.type === 'call');
    if (typeFilter === 'puts') items = items.filter(i => i.type === 'put');
    if (minPremium && !isNaN(Number(minPremium))) {
      const min = Number(minPremium) * 1000;
      items = items.filter(i => i.premium >= min);
    }
    return items;
  });

  function formatPremiumLarge(p: number): string {
    return '$' + (p / 1_000_000).toFixed(1) + 'M';
  }
</script>

<svelte:head>
  <title>Options Flow - Scanify</title>
</svelte:head>

<div class="flow-layout">
  <!-- Header -->
  <div class="flow-header" style="border-bottom: 1px solid var(--border-subtle);">
    <div class="header-left">
      <h1 class="flow-title" style="color: var(--text-primary);">Options Flow</h1>
      <div class="live-indicator">
        <div class="live-dot signal-ping" style="background: var(--bullish);"></div>
        <span class="live-label" style="color: var(--bullish);">Live</span>
      </div>
    </div>
    <div class="header-right">
      <ExportToolbar source="options-flow" />
      <div class="header-divider" style="background: var(--border-subtle);"></div>
      <a href="/options" class="back-link" style="color: var(--text-tertiary);">Back to Options</a>
    </div>
  </div>

  <!-- Stats bar -->
  <div class="stats-bar" style="background: var(--bg-base); border-bottom: 1px solid var(--border-subtle);">
    <div class="stat-item">
      <span class="stat-label" style="color: var(--text-tertiary);">Total Premium</span>
      <span class="stat-value" style="color: var(--text-primary);">{formatPremiumLarge(totalPremium)}</span>
    </div>
    <div class="stats-divider" style="background: var(--border-subtle);"></div>
    <div class="stat-item">
      <span class="stat-label" style="color: var(--text-tertiary);">Call/Put</span>
      <span class="stat-value" style="color: var(--bullish);">{callPutRatio}</span>
    </div>
    <div class="stats-divider" style="background: var(--border-subtle);"></div>
    <div class="stat-item">
      <span class="stat-label" style="color: var(--text-tertiary);">Sweeps</span>
      <span class="stat-value" style="color: var(--accent-bright);">{sweepCount}</span>
    </div>
    <div class="stats-divider" style="background: var(--border-subtle);"></div>
    <div class="stat-item">
      <span class="stat-label" style="color: var(--text-tertiary);">Count</span>
      <span class="stat-value" style="color: var(--text-primary);">{filteredItems.length}</span>
    </div>
  </div>

  <!-- Filter row -->
  <div class="filter-row" style="border-bottom: 1px solid var(--border-subtle);">
    <!-- Type dropdown -->
    <div class="filter-group">
      <span class="filter-label" style="color: var(--text-tertiary);">Type:</span>
      <div class="filter-buttons" style="background: var(--bg-surface);">
        {#each [['all', 'All'], ['calls', 'Calls'], ['puts', 'Puts']] as [key, label]}
          <button
            type="button"
            onclick={() => typeFilter = key as typeof typeFilter}
            class="filter-button"
            style="background: {typeFilter === key ? 'var(--bg-elevated)' : 'transparent'};
                   color: {typeFilter === key ? 'var(--text-primary)' : 'var(--text-tertiary)'};"
          >
            {label}
          </button>
        {/each}
      </div>
    </div>

    <!-- Min premium input -->
    <div class="filter-group">
      <span class="filter-label" style="color: var(--text-tertiary);">Min Premium ($K):</span>
      <input
        type="number"
        bind:value={minPremium}
        placeholder="0"
        class="premium-input"
        style="background: var(--bg-surface); color: var(--text-primary); border: 1px solid var(--border-subtle);"
      />
    </div>
  </div>

  <!-- Flow Feed -->
  <FlowFeed items={filteredItems} class="flow-embed" />
</div>

<style>
  .flow-layout {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }

  .flow-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    flex-shrink: 0;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .flow-title {
    font-size: var(--text-lg);
    font-weight: 700;
  }

  .live-indicator {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .live-dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
  }

  .live-label {
    font-size: var(--text-xs);
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .header-divider {
    width: 1px;
    height: 20px;
  }

  .back-link {
    font-size: var(--text-xs);
  }

  /* Stats bar */
  .stats-bar {
    display: flex;
    align-items: center;
    gap: 24px;
    padding: 12px 20px;
    flex-shrink: 0;
  }

  .stat-item {
    display: flex;
    flex-direction: column;
  }

  .stat-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .stat-value {
    font-size: var(--text-sm);
    font-weight: 700;
    font-family: var(--font-mono);
  }

  .stats-divider {
    width: 1px;
    height: 32px;
  }

  /* Filter row */
  .filter-row {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px 20px;
    flex-shrink: 0;
  }

  .filter-group {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .filter-label {
    font-size: 11px;
  }

  .filter-buttons {
    display: flex;
    gap: 4px;
    border-radius: var(--radius-lg);
    padding: 2px;
  }

  .filter-button {
    border-radius: var(--radius-md);
    padding: 6px 12px;
    font-size: var(--text-xs);
    font-weight: 500;
    transition: all 150ms;
  }

  .premium-input {
    width: 80px;
    border-radius: var(--radius-md);
    padding: 6px 8px;
    font-size: var(--text-xs);
    outline: none;
    font-family: var(--font-mono);
  }

  :global(.flow-embed) {
    flex: 1;
    min-height: 0;
  }
</style>
