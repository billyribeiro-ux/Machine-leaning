<script lang="ts">
  import { onMount } from 'svelte';
  import FlowFeed from '$components/options/FlowFeed.svelte';
  import ExportToolbar from '$lib/components/ui/ExportToolbar.svelte';
  import { fetchOptionsData } from '$lib/api';

  // ── Filter state ──

  let typeFilter = $state<'all' | 'calls' | 'puts'>('all');
  let minPremium = $state('');

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

  let allFlowItems = $state<FlowItem[]>([]);
  let loading = $state(true);
  let connected = $state(false);

  // ── Fetch live data ──
  // There is no dedicated real-time flow endpoint yet.
  // We attempt the options API to check connectivity; if no vendor is
  // configured (502/503), we show the "no provider" message.

  onMount(async () => {
    try {
      const result = await fetchOptionsData();

      if (result === null) {
        connected = false;
        loading = false;
        return;
      }

      // API is reachable but there is no live flow endpoint,
      // so allFlowItems stays empty. connected = true shows "no data" vs "no provider".
      connected = true;
    } catch {
      connected = false;
    } finally {
      loading = false;
    }
  });

  // ── Derived stats & filtering ──

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
      {#if connected && !loading}
        <div class="live-indicator">
          <div class="live-dot signal-ping" style="background: var(--bullish);"></div>
          <span class="live-label" style="color: var(--bullish);">Live</span>
        </div>
      {/if}
    </div>
    <div class="header-right">
      <ExportToolbar source="options-flow" />
      <div class="header-divider" style="background: var(--border-subtle);"></div>
      <a href="/options" class="back-link" style="color: var(--text-tertiary);">Back to Options</a>
    </div>
  </div>

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
      <p class="status-title" style="color: var(--text-secondary);">No Options Data</p>
      <p class="status-subtitle" style="color: var(--text-tertiary);">Connect an options data provider (FMP, Tradier, or CBOE) in Settings &rarr; Vendor API Keys to see live options flow</p>
    </div>
  {:else}
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
    {#if filteredItems.length === 0}
      <div class="status-message">
        <p class="status-title" style="color: var(--text-secondary);">No options flow data available</p>
      </div>
    {:else}
      <FlowFeed items={filteredItems} class="flow-embed" />
    {/if}
  {/if}
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

  /* Status message (loading / disconnected / empty) */
  .status-message {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    flex: 1;
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

  :global(.flow-embed) {
    flex: 1;
    min-height: 0;
  }
</style>
