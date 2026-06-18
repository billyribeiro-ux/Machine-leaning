<script lang="ts">
  import { onMount } from 'svelte';
  import BreadthDashboard from '$components/market/BreadthDashboard.svelte';
  import InternalsBar from '$components/market/InternalsBar.svelte';
  import SentimentGauge from '$components/market/SentimentGauge.svelte';
  import SectorRotation from '$components/market/SectorRotation.svelte';
  import ExportToolbar from '$lib/components/ui/ExportToolbar.svelte';

  const API_BASE = 'http://localhost:8000';

  // --- Reactive state ---
  let loading = $state(true);
  let connected = $state(false);

  // Breadth data
  let breadthData = $state({
    advancers: 0,
    decliners: 0,
    newHighs: 0,
    newLows: 0,
    percentAbove200ma: 0,
    percentAbove50ma: 0,
  });

  // Internals / direction
  let tick = $state(0);
  let trin = $state(1.0);
  let vix = $state(0);
  let advDecRatio = $state(1.0);

  // Sentiment
  let sentimentValue = $state(0);

  // Sectors
  let sectorData = $state<{ name: string; change: number; relativeStrength: number; momentum: number }[]>([]);

  let needsApiKey = $state(false);

  // --- Data fetching ---
  async function fetchMarketData() {
    loading = true;

    // Health check first
    try {
      const health = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });
      connected = health.ok;
    } catch {
      connected = false;
      loading = false;
      return;
    }

    let anyProviderError = false;

    // Breadth (works without FMP)
    try {
      const breadthRes = await fetch(`${API_BASE}/api/equity/internals/breadth`);
      if (breadthRes.ok) {
        const raw = await breadthRes.json();
        const d = raw.data ?? raw;
        breadthData = {
          advancers: d.advancers ?? d.advancing ?? 0,
          decliners: d.decliners ?? d.declining ?? 0,
          newHighs: d.newHighs ?? d.new_highs ?? 0,
          newLows: d.newLows ?? d.new_lows ?? 0,
          percentAbove200ma: d.percentAbove200ma ?? d.percent_above_200ma ?? d.pct_above_200ma ?? 0,
          percentAbove50ma: d.percentAbove50ma ?? d.percent_above_50ma ?? d.pct_above_50ma ?? 0,
        };
      }
    } catch { /* non-critical */ }

    // Direction / sentiment (works without FMP)
    try {
      const directionRes = await fetch(`${API_BASE}/api/equity/internals/direction`);
      if (directionRes.ok) {
        const raw = await directionRes.json();
        const d = raw.data ?? raw;
        sentimentValue = d.sentiment ?? d.value ?? d.score ?? 0;
        tick = d.tick ?? d.TICK ?? tick;
        trin = d.trin ?? d.TRIN ?? trin;
        advDecRatio = d.advDecRatio ?? d.advance_decline ?? d.ad_ratio ?? advDecRatio;
      }
    } catch { /* non-critical */ }

    // Macro snapshot -> VIX (needs FMP)
    try {
      const macroRes = await fetch(`${API_BASE}/api/equity/macro/snapshot`);
      if (macroRes.ok) {
        const raw = await macroRes.json();
        const d = raw.data ?? raw;
        vix = d.vix ?? d.VIX ?? 0;
        if (tick === 0) tick = d.tick ?? d.TICK ?? 0;
        if (trin === 1.0) trin = d.trin ?? d.TRIN ?? 1.0;
        if (advDecRatio === 1.0) advDecRatio = d.advDecRatio ?? d.advance_decline ?? d.ad_ratio ?? 1.0;
      } else {
        anyProviderError = true;
      }
    } catch { anyProviderError = true; }

    // Sectors (needs FMP)
    try {
      const sectorRes = await fetch(`${API_BASE}/api/equity/market/sectors`);
      if (sectorRes.ok) {
        const raw = await sectorRes.json();
        const rawSectors = Array.isArray(raw) ? raw : raw.data ?? raw.sectors ?? [];
        sectorData = rawSectors.map((s: any) => ({
          name: s.name ?? s.sector ?? '',
          change: s.change ?? s.changePercent ?? s.change_percent ?? 0,
          relativeStrength: s.relativeStrength ?? s.relative_strength ?? s.rs ?? 50,
          momentum: s.momentum ?? s.mom ?? 0,
        }));
      } else {
        anyProviderError = true;
      }
    } catch { anyProviderError = true; }

    needsApiKey = anyProviderError;
    loading = false;
  }

  onMount(() => {
    fetchMarketData();
  });
</script>

<svelte:head>
  <title>Market - Scanify</title>
</svelte:head>

<div class="page-root">
  <!-- Connection / API key banners -->
  {#if !loading && !connected}
    <div class="connection-banner">
      <span class="banner-text">Backend server is not running -- start the API server to see live data</span>
      <button class="retry-btn" onclick={() => fetchMarketData()}>Retry</button>
    </div>
  {:else if !loading && needsApiKey}
    <div class="connection-banner api-key-banner">
      <span class="banner-text">Some data providers need API keys -- configure in Settings for full data</span>
      <a href="/settings" class="retry-btn">Configure</a>
    </div>
  {/if}

  <!-- Header -->
  <div class="page-header">
    <h1 class="page-title">Market Overview</h1>
    <div class="header-actions">
      <ExportToolbar source="market" />
      <div class="header-divider"></div>
      <span class="header-timestamp">
        {new Date().toLocaleTimeString('en-US', { hour12: false })}
      </span>
    </div>
  </div>

  {#if loading}
    <div class="loading-state">
      <span class="loading-text">Loading market data...</span>
    </div>
  {:else}
    <div class="page-content">
      <!-- 2x2 Grid -->
      <div class="overview-grid">

        <!-- Breadth Dashboard -->
        <div class="panel section-panel">
          <h2 class="section-label">Market Breadth</h2>
          <BreadthDashboard internals={breadthData} />
        </div>

        <!-- Internals Bar -->
        <div class="panel section-panel">
          <h2 class="section-label">Market Internals</h2>
          <InternalsBar {tick} {trin} {vix} {advDecRatio} />
          <div class="metric-grid">
            <div class="metric-card">
              <div class="metric-label">Advancers</div>
              <div class="metric-value metric-value--bullish">
                {breadthData.advancers.toLocaleString()}
              </div>
            </div>
            <div class="metric-card">
              <div class="metric-label">Decliners</div>
              <div class="metric-value metric-value--bearish">
                {breadthData.decliners.toLocaleString()}
              </div>
            </div>
          </div>
        </div>

        <!-- Sentiment Gauge -->
        <div class="panel sentiment-panel">
          <SentimentGauge value={sentimentValue} label="Market Sentiment" />
        </div>

        <!-- Sector Rotation -->
        <div class="panel sector-panel">
          {#if sectorData.length > 0}
            <SectorRotation sectors={sectorData} />
          {:else}
            <p class="empty-text">{needsApiKey ? 'Configure a data provider API key to see sector data' : 'No sector data available'}</p>
          {/if}
        </div>

      </div>
    </div>
  {/if}
</div>

<style>
  .page-root {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: auto;
  }

  /* Connection banner */
  .connection-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    margin: 12px 20px 0;
    border-radius: var(--radius-lg);
    background-color: var(--bg-overlay);
    border: 1px solid var(--border-subtle);
  }

  .api-key-banner {
    border-color: var(--warning-bright, oklch(0.75 0.15 85));
    background-color: oklch(0.75 0.15 85 / 0.08);
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
    color: var(--text-tertiary);
  }

  /* Empty text for disconnected panels */
  .empty-text {
    font-size: var(--text-xs);
    font-style: italic;
    color: var(--text-tertiary);
    margin: 0;
  }

  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    flex-shrink: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .page-title {
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--text-primary);
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .header-divider {
    width: 1px;
    height: 20px;
    background: var(--border-subtle);
  }

  .header-timestamp {
    font-size: var(--text-xs);
    font-family: var(--font-mono);
    color: var(--text-tertiary);
  }

  .page-content {
    padding: 20px;
  }

  .overview-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 20px;
  }

  @media (min-width: 1024px) {
    .overview-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  .section-panel {
    padding: 20px;
  }

  .section-panel > * + * {
    margin-top: 12px;
  }

  .section-label {
    font-size: var(--text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
  }

  .metric-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    margin-top: 12px;
  }

  .metric-card {
    border-radius: var(--radius-lg);
    padding: 12px;
    text-align: center;
    background: var(--bg-base);
    border: 1px solid var(--border-subtle);
  }

  .metric-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
  }

  .metric-value {
    font-size: var(--text-lg);
    font-weight: 700;
    font-family: var(--font-mono);
  }

  .metric-value--bullish {
    color: var(--bullish);
  }

  .metric-value--bearish {
    color: var(--bearish);
  }

  .sentiment-panel {
    padding: 20px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
  }

  .sector-panel {
    padding: 20px;
  }
</style>
