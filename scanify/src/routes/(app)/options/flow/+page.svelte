<script lang="ts">
  import { onMount } from 'svelte';
  import ExportToolbar from '$lib/components/ui/ExportToolbar.svelte';

  let typeFilter = $state<'all' | 'calls' | 'puts'>('all');
  let minPremium = $state('');

  interface FlowItem {
    id: string;
    symbol: string;
    timestamp: string;
    type: 'call' | 'put';
    strike: number;
    expiration: string;
    side: 'buy' | 'sell';
    size: number;
    premium: number;
    isUnusual: boolean;
    isSweep: boolean;
    exchange: string;
  }

  const API_BASE = 'http://localhost:8000';

  function generateSampleFlow(): FlowItem[] {
    const symbols = ['SPY', 'QQQ', 'NVDA', 'AAPL', 'TSLA', 'AMD', 'META', 'MSFT', 'AMZN', 'SPX'];
    const exchanges = ['CBOE', 'PHLX', 'ISE', 'AMEX', 'BATS', 'MIAX'];
    const items: FlowItem[] = [];
    const now = Date.now();

    for (let i = 0; i < 30; i++) {
      const sym = symbols[Math.floor(Math.random() * symbols.length)];
      const isCall = Math.random() > 0.45;
      const basePrice: Record<string, number> = { SPY: 585, QQQ: 510, NVDA: 142, AAPL: 198, TSLA: 285, AMD: 178, META: 545, MSFT: 468, AMZN: 210, SPX: 5850 };
      const base = basePrice[sym] ?? 100;
      const strike = Math.round((base + (Math.random() - 0.5) * base * 0.06) / 5) * 5;
      const size = Math.floor(50 + Math.random() * 2000);
      const premium = size * (1 + Math.random() * 15) * 100;

      items.push({
        id: `flow-${i}`,
        symbol: sym,
        timestamp: new Date(now - i * 45000 - Math.random() * 30000).toISOString(),
        type: isCall ? 'call' : 'put',
        strike,
        expiration: `${new Date(now + (1 + Math.floor(Math.random() * 30)) * 86400000).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`,
        side: Math.random() > 0.4 ? 'buy' : 'sell',
        size,
        premium,
        isUnusual: Math.random() > 0.7,
        isSweep: Math.random() > 0.75,
        exchange: exchanges[Math.floor(Math.random() * exchanges.length)],
      });
    }
    return items;
  }

  let allFlowItems = $state<FlowItem[]>(generateSampleFlow());
  let loading = $state(false);
  let connected = $state(false);

  onMount(async () => {
    try {
      const health = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });
      connected = health.ok;
    } catch {
      connected = false;
    }
    allFlowItems = generateSampleFlow();
    loading = false;
  });

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

  let totalPremium = $derived(filteredItems.reduce((s, i) => s + i.premium, 0));
  let callCount = $derived(filteredItems.filter(i => i.type === 'call').length);
  let putCount = $derived(filteredItems.filter(i => i.type === 'put').length);
  let callPutRatio = $derived(putCount > 0 ? (callCount / putCount).toFixed(2) : 'N/A');
  let sweepCount = $derived(filteredItems.filter(i => i.isSweep).length);
  let unusualCount = $derived(filteredItems.filter(i => i.isUnusual).length);

  function formatPremium(p: number): string {
    if (p >= 1_000_000) return '$' + (p / 1_000_000).toFixed(1) + 'M';
    if (p >= 1_000) return '$' + (p / 1_000).toFixed(0) + 'K';
    return '$' + p.toFixed(0);
  }

  function formatTime(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  }

  function relativeTime(iso: string): string {
    const diff = (Date.now() - new Date(iso).getTime()) / 1000;
    if (diff < 60) return `${Math.floor(diff)}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  }
</script>

<svelte:head>
  <title>Options Flow - Scanify</title>
</svelte:head>

<div class="flow-layout">
  <!-- Header -->
  <div class="flow-header">
    <div class="header-left">
      <h1 class="flow-title">Options Flow</h1>
      <div class="live-indicator">
        <div class="live-dot" class:live-dot--active={connected}></div>
        <span class="live-label" style="color: {connected ? 'var(--bullish)' : 'var(--text-disabled)'};">{connected ? 'Live' : 'Sample Data'}</span>
      </div>
    </div>
    <div class="header-right">
      <ExportToolbar source="options-flow" />
      <a href="/options" class="back-link">Back to Options</a>
    </div>
  </div>

  <!-- KPI Stats Bar -->
  <div class="stats-bar">
    <div class="stat-card">
      <span class="stat-label">Total Premium</span>
      <span class="stat-value">{formatPremium(totalPremium)}</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">Calls</span>
      <span class="stat-value" style="color: var(--bullish);">{callCount}</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">Puts</span>
      <span class="stat-value" style="color: var(--bearish);">{putCount}</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">C/P Ratio</span>
      <span class="stat-value" style="color: {Number(callPutRatio) > 1 ? 'var(--bullish)' : 'var(--bearish)'};">{callPutRatio}</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">Sweeps</span>
      <span class="stat-value" style="color: var(--accent-bright);">{sweepCount}</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">Unusual</span>
      <span class="stat-value" style="color: var(--warning-bright);">{unusualCount}</span>
    </div>
  </div>

  <!-- Filter Row -->
  <div class="filter-row">
    <div class="filter-group-pills">
      {#each [['all', 'All'], ['calls', 'Calls'], ['puts', 'Puts']] as [key, label]}
        <button
          class="filter-pill"
          class:filter-pill--active={typeFilter === key}
          onclick={() => typeFilter = key as typeof typeFilter}
        >
          {label}
        </button>
      {/each}
    </div>
    <div class="filter-input-group">
      <span class="filter-label">Min Premium ($K):</span>
      <input type="text" bind:value={minPremium} placeholder="0" class="filter-input" />
    </div>
    <span class="filter-count">{filteredItems.length} orders</span>
  </div>

  <!-- Flow Table -->
  <div class="table-container">
    <table class="flow-table">
      <thead>
        <tr>
          <th class="th-left">Time</th>
          <th class="th-left">Symbol</th>
          <th class="th-center">Type</th>
          <th class="th-right">Strike</th>
          <th class="th-left">Expiry</th>
          <th class="th-center">Side</th>
          <th class="th-right">Size</th>
          <th class="th-right">Premium</th>
          <th class="th-center">Exch</th>
          <th class="th-center">Flags</th>
        </tr>
      </thead>
      <tbody>
        {#if loading}
          <tr><td colspan="10" class="td-empty"><div class="skeleton" style="width: 60%; height: 20px; margin: 20px auto;"></div></td></tr>
        {:else}
          {#each filteredItems as item, i (item.id)}
            <tr class="flow-row" class:flow-row--call={item.type === 'call'} class:flow-row--put={item.type === 'put'}>
              <td class="td-time">
                <span class="time-main">{formatTime(item.timestamp)}</span>
                <span class="time-rel">{relativeTime(item.timestamp)}</span>
              </td>
              <td class="td-symbol">{item.symbol}</td>
              <td class="td-center">
                <span class="type-badge" class:type-badge--call={item.type === 'call'} class:type-badge--put={item.type === 'put'}>
                  {item.type === 'call' ? 'C' : 'P'}
                </span>
              </td>
              <td class="td-right td-mono">${item.strike}</td>
              <td class="td-left td-secondary">{item.expiration}</td>
              <td class="td-center">
                <span class="side-badge" class:side-badge--buy={item.side === 'buy'} class:side-badge--sell={item.side === 'sell'}>
                  {item.side.toUpperCase()}
                </span>
              </td>
              <td class="td-right td-mono">{item.size.toLocaleString()}</td>
              <td class="td-right td-mono td-premium">{formatPremium(item.premium)}</td>
              <td class="td-center td-secondary">{item.exchange}</td>
              <td class="td-center">
                {#if item.isSweep}
                  <span class="flag-badge flag-sweep">SWEEP</span>
                {/if}
                {#if item.isUnusual}
                  <span class="flag-badge flag-unusual">UOA</span>
                {/if}
              </td>
            </tr>
          {/each}
        {/if}
      </tbody>
    </table>
  </div>
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
    border-bottom: 1px solid var(--border-subtle);
    background: var(--bg-base);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .flow-title {
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--text-primary);
  }

  .live-indicator {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .live-dot {
    width: 7px;
    height: 7px;
    border-radius: var(--radius-full);
    background: var(--text-disabled);
  }

  .live-dot--active {
    background: var(--bullish);
    box-shadow: 0 0 8px var(--bullish-dim);
    animation: signal-ping 2s ease-in-out infinite;
  }

  .live-label {
    font-size: var(--text-2xs);
    font-weight: 500;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .back-link {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    text-decoration: none;
    transition: color 150ms;
  }

  .back-link:hover {
    color: var(--text-primary);
  }

  /* Stats bar */
  .stats-bar {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 1px;
    background: var(--border-subtle);
    border-bottom: 1px solid var(--border-subtle);
  }

  .stat-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 10px 8px;
    background: var(--bg-base);
  }

  .stat-label {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .stat-value {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    font-weight: 700;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }

  /* Filter row */
  .filter-row {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 8px 20px;
    background: var(--bg-surface);
    border-bottom: 1px solid var(--border-subtle);
  }

  .filter-group-pills {
    display: flex;
    gap: 2px;
    background: var(--bg-base);
    border-radius: var(--radius-md);
    padding: 2px;
  }

  .filter-pill {
    padding: 4px 12px;
    border-radius: var(--radius-sm);
    font-size: var(--text-2xs);
    font-weight: 500;
    color: var(--text-tertiary);
    background: transparent;
    border: none;
    cursor: pointer;
    transition: all 150ms;
  }

  .filter-pill:hover {
    color: var(--text-secondary);
  }

  .filter-pill--active {
    background: var(--bg-elevated);
    color: var(--text-primary);
  }

  .filter-input-group {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .filter-label {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
  }

  .filter-input {
    width: 60px;
    padding: 3px 8px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: var(--bg-base);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
  }

  .filter-count {
    margin-left: auto;
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    font-family: var(--font-mono);
  }

  /* Table */
  .table-container {
    flex: 1;
    overflow: auto;
    min-height: 0;
  }

  .flow-table {
    width: 100%;
    font-size: var(--text-2xs);
    border-collapse: separate;
    border-spacing: 0;
  }

  thead {
    position: sticky;
    top: 0;
    z-index: 10;
  }

  th {
    padding: 8px 10px;
    font-weight: 500;
    color: var(--text-tertiary);
    background: var(--bg-base);
    border-bottom: 1px solid var(--border-subtle);
    white-space: nowrap;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .th-left { text-align: left; }
  .th-right { text-align: right; }
  .th-center { text-align: center; }

  .flow-row {
    transition: background-color 100ms;
    cursor: pointer;
  }

  .flow-row:hover {
    background: var(--hover-overlay);
  }

  .flow-row--call {
    border-left: 2px solid oklch(0.64 0.16 155 / 0.3);
  }

  .flow-row--put {
    border-left: 2px solid oklch(0.58 0.18 25 / 0.3);
  }

  td {
    padding: 7px 10px;
    border-bottom: 1px solid oklch(0.15 0.01 260);
    vertical-align: middle;
  }

  .td-time {
    display: flex;
    flex-direction: column;
  }

  .time-main {
    font-family: var(--font-mono);
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }

  .time-rel {
    font-size: 9px;
    color: var(--text-disabled);
  }

  .td-symbol {
    font-family: var(--font-mono);
    font-weight: 700;
    color: var(--text-primary);
  }

  .td-mono {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    color: var(--text-secondary);
  }

  .td-right { text-align: right; }
  .td-left { text-align: left; }
  .td-center { text-align: center; }
  .td-secondary { color: var(--text-tertiary); }

  .td-premium {
    font-weight: 600;
    color: var(--text-primary);
  }

  .td-empty {
    text-align: center;
    padding: 40px;
  }

  /* Badges */
  .type-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 18px;
    border-radius: var(--radius-xs);
    font-weight: 700;
    font-size: 10px;
    font-family: var(--font-mono);
  }

  .type-badge--call {
    background: var(--bullish-bg);
    color: var(--bullish-bright);
    border: 1px solid oklch(0.45 0.12 155 / 0.3);
  }

  .type-badge--put {
    background: var(--bearish-bg);
    color: var(--bearish-bright);
    border: 1px solid oklch(0.42 0.12 25 / 0.3);
  }

  .side-badge {
    font-size: 9px;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: var(--radius-xs);
  }

  .side-badge--buy {
    color: var(--bullish);
    background: oklch(0.64 0.16 155 / 0.1);
  }

  .side-badge--sell {
    color: var(--bearish);
    background: oklch(0.58 0.18 25 / 0.1);
  }

  .flag-badge {
    display: inline-flex;
    padding: 1px 5px;
    border-radius: var(--radius-xs);
    font-size: 8px;
    font-weight: 700;
    letter-spacing: 0.03em;
    margin: 0 1px;
  }

  .flag-sweep {
    background: var(--accent-bg);
    color: var(--accent-bright);
    border: 1px solid oklch(0.44 0.14 290 / 0.3);
  }

  .flag-unusual {
    background: var(--warning-bg);
    color: var(--warning-bright);
    border: 1px solid oklch(0.52 0.10 85 / 0.3);
  }
</style>
