<script lang="ts">
  import { onMount } from 'svelte';
  import InternalsBar from '$lib/components/market/InternalsBar.svelte';
  import ExportToolbar from '$lib/components/ui/ExportToolbar.svelte';

  const API_BASE = 'http://localhost:8000';

  // --- Reactive state ---
  let loading = $state(true);
  let connected = $state(false);

  let indices = $state<{ symbol: string; price: number; change: number; changePercent: number }[]>([]);
  let topSignals = $state<{ symbol: string; direction: 'bullish' | 'bearish' | 'neutral'; name: string; strength: number; price: number }[]>([]);
  let sectors = $state<{ name: string; change: number }[]>([]);

  let tick = $state(0);
  let trin = $state(1.0);
  let vix = $state(0);
  let advDecRatio = $state(1.0);

  // --- Data fetching ---
  async function fetchDashboardData() {
    loading = true;

    try {
      const [priceRes, macroRes, sectorRes, moversRes] = await Promise.all([
        fetch(`${API_BASE}/api/equity/price/snapshot`),
        fetch(`${API_BASE}/api/equity/macro/snapshot`),
        fetch(`${API_BASE}/api/equity/market/sectors`),
        fetch(`${API_BASE}/api/equity/market/movers?limit=5`),
      ]);

      // Price snapshot -> indices
      if (priceRes.ok) {
        const priceData = await priceRes.json();
        if (Array.isArray(priceData)) {
          indices = priceData.map((d: any) => ({
            symbol: d.symbol ?? d.ticker ?? '',
            price: d.price ?? d.last ?? 0,
            change: d.change ?? 0,
            changePercent: d.changePercent ?? d.change_percent ?? 0,
          }));
        } else if (priceData.indices) {
          indices = priceData.indices;
        } else if (priceData.data) {
          indices = Array.isArray(priceData.data) ? priceData.data : [];
        }
      }

      // Macro snapshot -> VIX, internals
      if (macroRes.ok) {
        const macroData = await macroRes.json();
        const macro = macroData.data ?? macroData;
        vix = macro.vix ?? macro.VIX ?? 0;
        tick = macro.tick ?? macro.TICK ?? 0;
        trin = macro.trin ?? macro.TRIN ?? 1.0;
        advDecRatio = macro.advDecRatio ?? macro.advance_decline ?? macro.ad_ratio ?? 1.0;
      }

      // Sectors
      if (sectorRes.ok) {
        const sectorData = await sectorRes.json();
        const rawSectors = Array.isArray(sectorData) ? sectorData : sectorData.data ?? sectorData.sectors ?? [];
        sectors = rawSectors.map((s: any) => ({
          name: s.name ?? s.sector ?? '',
          change: s.change ?? s.changePercent ?? s.change_percent ?? 0,
        }));
      }

      // Top movers -> signals
      if (moversRes.ok) {
        const moversData = await moversRes.json();
        const rawMovers = Array.isArray(moversData) ? moversData : moversData.data ?? moversData.movers ?? [];
        topSignals = rawMovers.map((m: any) => ({
          symbol: m.symbol ?? m.ticker ?? '',
          direction: (m.direction ?? (m.change > 0 ? 'bullish' : m.change < 0 ? 'bearish' : 'neutral')) as 'bullish' | 'bearish' | 'neutral',
          name: m.name ?? m.signal ?? m.reason ?? '',
          strength: m.strength ?? m.score ?? 3,
          price: m.price ?? m.last ?? 0,
        }));
      }

      connected = true;
    } catch {
      connected = false;
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    fetchDashboardData();
  });

  // --- Helpers ---
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
</script>

<svelte:head>
  <title>Dashboard - Scanify</title>
</svelte:head>

<div class="dashboard-page">
  <!-- Connection banner -->
  {#if !loading && !connected}
    <div class="connection-banner">
      <span class="banner-text">No API connection -- market data unavailable</span>
      <button class="retry-btn" onclick={() => fetchDashboardData()}>Retry</button>
    </div>
  {/if}

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

  {#if loading}
    <div class="loading-state">
      <span class="loading-text" style="color: var(--text-tertiary);">Loading...</span>
    </div>
  {:else}
    <!-- Grid layout -->
    <div class="dashboard-grid">

      <!-- Market Status panel - spans 2 cols -->
      <div class="market-status-panel panel">
        <div class="panel-header">
          <h2 class="panel-title" style="color: var(--text-primary);">Market Status</h2>
          <div class="market-status-indicator">
            <div class="status-dot" style="background: {connected ? 'var(--bullish)' : 'var(--text-tertiary)'};"></div>
            <span class="status-label" style="color: {connected ? 'var(--bullish)' : 'var(--text-tertiary)'};">
              {connected ? 'Regular Hours' : 'Disconnected'}
            </span>
          </div>
        </div>

        <!-- Indices row -->
        {#if indices.length > 0}
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
        {:else}
          <p class="empty-text" style="color: var(--text-tertiary);">Connect API to view index data</p>
        {/if}
      </div>

      <!-- Internals panel -->
      <div class="internals-panel panel">
        <h2 class="panel-title" style="color: var(--text-primary);">Market Internals</h2>
        {#if connected}
          <InternalsBar {tick} {trin} {vix} {advDecRatio} />
        {:else}
          <p class="empty-text" style="color: var(--text-tertiary);">Connect API to view internals</p>
        {/if}
      </div>

      <!-- Top Signals panel - spans 2 cols -->
      <div class="signals-panel panel">
        <div class="panel-header">
          <h2 class="panel-title" style="color: var(--text-primary);">Top Signals</h2>
          <a href="/scanner" class="view-all-link" style="color: var(--accent);">View all</a>
        </div>
        {#if topSignals.length > 0}
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
        {:else}
          <p class="empty-text" style="color: var(--text-tertiary);">Connect API to view signals</p>
        {/if}
      </div>

      <!-- Sector Performance panel -->
      <div class="sectors-panel panel">
        <h2 class="panel-title" style="color: var(--text-primary);">Sector Performance</h2>
        {#if sectors.length > 0}
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
        {:else}
          <p class="empty-text" style="color: var(--text-tertiary);">Connect API to view sectors</p>
        {/if}
      </div>
    </div>
  {/if}
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

  /* Connection banner */
  .connection-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    border-radius: var(--radius-lg);
    background-color: var(--bg-overlay);
    border: 1px solid var(--border-subtle);
  }

  .banner-text {
    font-size: var(--text-xs);
    color: var(--text-secondary);
    font-weight: 500;
  }

  .retry-btn {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--accent);
    background: none;
    border: 1px solid var(--accent);
    border-radius: var(--radius-md);
    padding: 4px 12px;
    cursor: pointer;
    transition: background-color 150ms;
  }

  .retry-btn:hover {
    background-color: var(--accent);
    color: var(--bg-base);
  }

  /* Loading state */
  .loading-state {
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 1;
  }

  .loading-text {
    font-size: var(--text-sm);
    font-weight: 500;
  }

  /* Empty text for disconnected panels */
  .empty-text {
    font-size: var(--text-xs);
    font-style: italic;
    margin: 0;
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
