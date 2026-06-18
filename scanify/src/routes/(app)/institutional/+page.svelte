<script lang="ts">
  import { onMount } from 'svelte';
  import DarkPoolFeed from '$components/institutional/DarkPoolFeed.svelte';
  import ShortInterest from '$components/institutional/ShortInterest.svelte';
  import ETFFlows from '$components/institutional/ETFFlows.svelte';
  import ExportToolbar from '$lib/components/ui/ExportToolbar.svelte';

  const API_BASE = 'http://localhost:8000';

  // --- Reactive state ---
  let loading = $state(true);
  let connected = $state(false);

  let activeTab = $state<'darkpool' | 'short' | 'etf'>('darkpool');

  const tabs: { id: 'darkpool' | 'short' | 'etf'; label: string }[] = [
    { id: 'darkpool', label: 'Dark Pool' },
    { id: 'short', label: 'Short Interest' },
    { id: 'etf', label: 'ETF Flows' },
  ];

  // Institutional data from API
  let holdersData = $state<any>(null);
  let sentimentData = $state<any>(null);

  // Mapped display arrays
  let darkPoolTrades = $derived<any[]>(
    holdersData?.darkPool ?? holdersData?.dark_pool ?? holdersData?.trades ?? []
  );

  let shortInterestData = $derived<any[]>(
    holdersData?.shortInterest ?? holdersData?.short_interest ?? holdersData?.shorts ?? []
  );

  let etfFlowData = $derived<any[]>(
    holdersData?.etfFlows ?? holdersData?.etf_flows ?? holdersData?.flows ?? []
  );

  // Whether premium data sources are available
  let hasDarkPool = $derived(darkPoolTrades.length > 0);
  let hasShortInterest = $derived(shortInterestData.length > 0);
  let hasEtfFlows = $derived(etfFlowData.length > 0);

  let needsApiKey = $state(false);

  // --- Data fetching ---
  async function fetchInstitutionalData() {
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

    try {
      const holdersRes = await fetch(`${API_BASE}/api/equity/institutional/holders`);
      if (holdersRes.ok) {
        const raw = await holdersRes.json();
        holdersData = raw.data ?? raw;
      } else {
        anyProviderError = true;
      }
    } catch { anyProviderError = true; }

    try {
      const sentimentRes = await fetch(`${API_BASE}/api/equity/institutional/sentiment`);
      if (sentimentRes.ok) {
        const raw = await sentimentRes.json();
        sentimentData = raw.data ?? raw;
      } else {
        anyProviderError = true;
      }
    } catch { anyProviderError = true; }

    needsApiKey = anyProviderError;
    loading = false;
  }

  onMount(() => {
    fetchInstitutionalData();
  });
</script>

<svelte:head>
  <title>Institutional - Scanify</title>
</svelte:head>

<div class="page-layout">
  <!-- Connection / API key banners -->
  {#if !loading && !connected}
    <div class="connection-banner">
      <span class="banner-text">Backend server is not running -- start the API server to see institutional data</span>
      <button class="retry-btn" onclick={() => fetchInstitutionalData()}>Retry</button>
    </div>
  {:else if !loading && needsApiKey}
    <div class="connection-banner api-key-banner">
      <span class="banner-text">Dark pool, short interest, and ETF flow data require a premium data provider API key</span>
      <a href="/settings" class="retry-btn">Configure</a>
    </div>
  {/if}

  <!-- Header -->
  <div class="page-header">
    <h1 class="page-title">Institutional</h1>
    <ExportToolbar source="institutional" />
  </div>

  <!-- Tab switcher -->
  <div class="tab-bar">
    {#each tabs as tab (tab.id)}
      <button
        type="button"
        onclick={() => activeTab = tab.id}
        class="tab-button"
        class:tab-button--active={activeTab === tab.id}
      >
        {tab.label}
      </button>
    {/each}
  </div>

  <!-- Tab content -->
  {#if loading}
    <div class="loading-state">
      <span class="loading-text">Loading institutional data...</span>
    </div>
  {:else}
    <div class="tab-content">
      {#if activeTab === 'darkpool'}
        {#if hasDarkPool}
          <DarkPoolFeed trades={darkPoolTrades} />
        {:else}
          <div class="provider-notice">
            <div class="notice-icon">&#9679;</div>
            <h3 class="notice-title">Dark Pool Data</h3>
            <p class="notice-description">
              Dark pool trade data requires a premium data provider.
              Configure a supported vendor in <a href="/settings" style="color: var(--accent);">Settings</a> to view real-time dark pool prints.
            </p>
          </div>
        {/if}

      {:else if activeTab === 'short'}
        {#if hasShortInterest}
          <ShortInterest data={shortInterestData} />
        {:else}
          <div class="provider-notice">
            <div class="notice-icon">&#9679;</div>
            <h3 class="notice-title">Short Interest Data</h3>
            <p class="notice-description">
              Short interest data requires a premium data provider.
              Configure a supported vendor in <a href="/settings" style="color: var(--accent);">Settings</a> to view short interest metrics.
            </p>
          </div>
        {/if}

      {:else if activeTab === 'etf'}
        {#if hasEtfFlows}
          <ETFFlows data={etfFlowData} />
        {:else}
          <div class="provider-notice">
            <div class="notice-icon">&#9679;</div>
            <h3 class="notice-title">ETF Flow Data</h3>
            <p class="notice-description">
              ETF flow data requires a premium data provider.
              Configure a supported vendor in <a href="/settings" style="color: var(--accent);">Settings</a> to view fund flows.
            </p>
          </div>
        {/if}
      {/if}
    </div>
  {/if}
</div>

<style>
  .page-layout {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
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
    flex-shrink: 0;
    text-decoration: none;
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

  .tab-bar {
    display: flex;
    gap: 4px;
    padding: 12px 20px;
    flex-shrink: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .tab-button {
    border-radius: var(--radius-lg);
    padding: 8px 16px;
    font-size: var(--text-xs);
    font-weight: 500;
    transition: all 150ms;
    background: var(--bg-elevated);
    color: var(--text-secondary);
    border: 1px solid var(--border-subtle);
  }

  .tab-button--active {
    background: var(--accent-bg);
    color: var(--accent-bright);
    border-color: var(--accent-dim);
  }

  .tab-content {
    flex: 1;
    overflow: hidden;
    min-height: 0;
  }

  /* Provider notice for unavailable data */
  .provider-notice {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 48px 32px;
    height: 100%;
  }

  .notice-icon {
    font-size: 24px;
    color: var(--text-disabled);
    margin-bottom: 12px;
  }

  .notice-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
    margin: 0 0 8px;
  }

  .notice-description {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    max-width: 360px;
    line-height: 1.5;
    margin: 0;
  }
</style>
