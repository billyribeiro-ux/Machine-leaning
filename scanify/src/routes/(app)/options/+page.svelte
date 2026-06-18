<script lang="ts">
  import { onMount } from 'svelte';
  import FlowFeed from '$components/options/FlowFeed.svelte';
  import { fetchOptionsData } from '$lib/api';

  let activeTab = $state<'flow' | 'unusual' | 'chain'>('flow');

  const tabs: { id: 'flow' | 'unusual' | 'chain'; label: string }[] = [
    { id: 'flow', label: 'Flow' },
    { id: 'unusual', label: 'Unusual Activity' },
    { id: 'chain', label: 'Chain' },
  ];

  // ── Data state ──

  interface FlowItem {
    id: string;
    symbol: string;
    timestamp: string | number;
    type: 'call' | 'put';
    strike: number;
    expiration: string;
    side: 'buy' | 'sell';
    size: number;
    premium: number;
    isUnusual: boolean;
    isSweep: boolean;
  }

  interface UnusualRow {
    symbol: string;
    strike: string;
    expiry: string;
    volume: number;
    oi: number;
    ratio: number;
    premium: string;
    sentiment: string;
  }

  let flowItems = $state<FlowItem[]>([]);
  let unusualData = $state<UnusualRow[]>([]);
  let loading = $state(true);
  let connected = $state(false);
  let needsApiKey = $state(false);

  const API_BASE = 'http://localhost:8000';

  // ── Fetch live data ──

  onMount(async () => {
    // Health check first
    try {
      const health = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });
      connected = health.ok;
    } catch {
      connected = false;
      loading = false;
      return;
    }

    try {
      const result = await fetchOptionsData();

      if (result === null) {
        needsApiKey = true;
        loading = false;
        return;
      }

      if (result.chainSummary && Array.isArray(result.chainSummary)) {
        flowItems = result.chainSummary as FlowItem[];
      }

      if (result.gexLevels && Array.isArray(result.gexLevels)) {
        unusualData = result.gexLevels as UnusualRow[];
      }
    } catch {
      needsApiKey = true;
    } finally {
      loading = false;
    }
  });

  // ── Helpers ──

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
    {#if loading}
      <div class="status-message">
        <div class="status-icon-box" style="background: var(--bg-elevated); border: 1px solid var(--border-subtle);">
          <div class="spinner"></div>
        </div>
        <p class="status-title" style="color: var(--text-secondary);">Loading options data...</p>
      </div>
    {:else if !connected}
      <div class="status-message">
        <div class="status-icon-box" style="background: var(--bg-elevated); border: 1px solid var(--border-subtle);">
          <svg class="status-icon" style="color: var(--text-disabled);" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
        </div>
        <p class="status-title" style="color: var(--text-secondary);">Backend Offline</p>
        <p class="status-subtitle" style="color: var(--text-tertiary);">Start the backend server to see options data</p>
      </div>
    {:else if needsApiKey}
      <div class="status-message">
        <div class="status-icon-box" style="background: var(--bg-elevated); border: 1px solid var(--border-subtle);">
          <svg class="status-icon" style="color: var(--warning-bright, oklch(0.75 0.15 85));" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z" />
          </svg>
        </div>
        <p class="status-title" style="color: var(--text-secondary);">Options Data Provider Required</p>
        <p class="status-subtitle" style="color: var(--text-tertiary);">Configure an options data provider (FMP, Tradier, or CBOE) in <a href="/settings" style="color: var(--accent);">Settings</a> to see live options flow</p>
      </div>
    {:else if activeTab === 'flow'}
      {#if flowItems.length === 0}
        <div class="status-message">
          <p class="status-title" style="color: var(--text-secondary);">No options flow data available</p>
        </div>
      {:else}
        <FlowFeed items={flowItems} />
      {/if}

    {:else if activeTab === 'unusual'}
      {#if unusualData.length === 0}
        <div class="status-message">
          <p class="status-title" style="color: var(--text-secondary);">No options flow data available</p>
        </div>
      {:else}
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
      {/if}

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

  /* Status message (loading / disconnected / empty) */
  .status-message {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    gap: 16px;
    padding: 40px 20px;
    text-align: center;
  }

  .status-icon-box {
    width: 64px;
    height: 64px;
    border-radius: var(--radius-xl);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .status-icon {
    height: 32px;
    width: 32px;
  }

  .status-title {
    font-size: var(--text-sm);
    font-weight: 500;
  }

  .status-subtitle {
    font-size: var(--text-xs);
    max-width: 420px;
    line-height: 1.5;
  }

  .spinner {
    width: 24px;
    height: 24px;
    border: 2px solid var(--border-subtle);
    border-top-color: var(--accent);
    border-radius: var(--radius-full);
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
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
