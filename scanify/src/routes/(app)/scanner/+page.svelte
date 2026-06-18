<script lang="ts">
  import { onMount } from 'svelte';
  import SparkLine from '$lib/components/data/SparkLine.svelte';
  import ExportToolbar from '$lib/components/ui/ExportToolbar.svelte';

  // ---- Filter state ----
  let selectedPreset = $state('momentum');
  let directionFilter = $state<'all' | 'bullish' | 'bearish' | 'neutral'>('all');
  let minStrength = $state(1);
  let searchQuery = $state('');
  let sortBy = $state('strength');
  let sortDir = $state<'asc' | 'desc'>('desc');

  // ---- Presets ----
  const presets = [
    { id: 'momentum', name: 'Momentum', icon: '>>', description: 'Strong directional momentum' },
    { id: 'volume', name: 'Volume Surge', icon: 'V+', description: 'Unusual volume spikes' },
    { id: 'breakout', name: 'Breakouts', icon: '/\\', description: 'Breaking key price levels' },
    { id: 'gap', name: 'Gap Scanner', icon: '||', description: 'Pre-market gaps' },
    { id: 'squeeze', name: 'Squeeze', icon: '<>', description: 'Bollinger Band squeeze' },
    { id: 'reversal', name: 'Reversals', icon: 'R', description: 'Potential trend reversals' },
  ];

  // ---- Scan result type ----
  interface ScanResult {
    id: string;
    symbol: string;
    name: string;
    price: number;
    change: number;
    changePercent: number;
    volume: number;
    relativeVolume: number;
    direction: 'bullish' | 'bearish' | 'neutral';
    strength: number;
    sector: string;
    category: string;
    sparklineData: number[];
    timestamp: string;
  }

  // ---- Live data state ----
  let scanResults: ScanResult[] = $state([]);
  let loading = $state(true);
  let connected = $state(false);
  let needsApiKey = $state(false);

  // ---- Derive direction & strength from change percent ----
  function deriveDirection(changePercent: number): 'bullish' | 'bearish' | 'neutral' {
    if (changePercent > 0.5) return 'bullish';
    if (changePercent < -0.5) return 'bearish';
    return 'neutral';
  }

  function deriveStrength(changePercent: number): number {
    const abs = Math.abs(changePercent);
    if (abs >= 5) return 5;
    if (abs >= 3) return 4;
    if (abs >= 2) return 3;
    if (abs >= 1) return 2;
    return 1;
  }

  // ---- Generate simple sparkline from price ----
  function generateSparkline(base: number): number[] {
    const points: number[] = [base];
    const volatility = base * 0.01;
    for (let i = 1; i < 20; i++) {
      const prev = points[i - 1] ?? base;
      const delta = (Math.random() - 0.48) * volatility;
      points.push(prev + delta);
    }
    return points;
  }

  // ---- Map a raw API item into ScanResult ----
  function mapItem(item: any, index: number, category: string): ScanResult {
    const price = item.price ?? item.last_price ?? 0;
    const change = item.change ?? item.price_change ?? 0;
    const changePercent = item.change_percent ?? item.percent_change ?? (price > 0 ? (change / (price - change)) * 100 : 0);
    const volume = item.volume ?? 0;

    return {
      id: `${category}-${index}`,
      symbol: item.symbol ?? item.ticker ?? '',
      name: item.name ?? item.company_name ?? item.symbol ?? '',
      price,
      change,
      changePercent,
      volume,
      relativeVolume: item.relative_volume ?? item.rvol ?? 1.0,
      direction: deriveDirection(changePercent),
      strength: deriveStrength(changePercent),
      sector: item.sector ?? '',
      category,
      sparklineData: generateSparkline(price),
      timestamp: item.timestamp ?? new Date().toISOString(),
    };
  }

  // ---- Fetch data from API ----
  async function fetchScannerData() {
    // Health check first
    try {
      const health = await fetch('http://localhost:8000/health', { signal: AbortSignal.timeout(3000) });
      connected = health.ok;
    } catch {
      connected = false;
      loading = false;
      return;
    }

    try {
      const response = await fetch('http://localhost:8000/api/equity/market/movers?limit=25');
      if (!response.ok) {
        needsApiKey = true;
        loading = false;
        return;
      }
      const data = await response.json();

      const allItems: ScanResult[] = [];
      const seen = new Set<string>();

      for (const [category, items] of Object.entries(data)) {
        if (!Array.isArray(items)) continue;
        for (let i = 0; i < items.length; i++) {
          const mapped = mapItem(items[i], allItems.length, category);
          if (mapped.symbol && !seen.has(mapped.symbol)) {
            seen.add(mapped.symbol);
            allItems.push(mapped);
          }
        }
      }

      scanResults = allItems;
      needsApiKey = false;
    } catch {
      needsApiKey = true;
      scanResults = [];
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    fetchScannerData();
  });

  // ---- Filtered + sorted results ----
  let filteredResults = $derived.by(() => {
    let results = scanResults;
    if (directionFilter !== 'all') {
      results = results.filter(r => r.direction === directionFilter);
    }
    if (minStrength > 1) {
      results = results.filter(r => r.strength >= minStrength);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      results = results.filter(r =>
        r.symbol.toLowerCase().includes(q) ||
        r.name.toLowerCase().includes(q) ||
        r.sector.toLowerCase().includes(q)
      );
    }
    // Sort
    results = [...results].sort((a, b) => {
      let av: number, bv: number;
      switch (sortBy) {
        case 'symbol': return sortDir === 'asc' ? a.symbol.localeCompare(b.symbol) : b.symbol.localeCompare(a.symbol);
        case 'price': av = a.price; bv = b.price; break;
        case 'change': av = a.changePercent; bv = b.changePercent; break;
        case 'volume': av = a.volume; bv = b.volume; break;
        case 'rvol': av = a.relativeVolume; bv = b.relativeVolume; break;
        case 'strength': default: av = a.strength; bv = b.strength; break;
      }
      return sortDir === 'asc' ? av! - bv! : bv! - av!;
    });
    return results;
  });

  function toggleSort(col: string) {
    if (sortBy === col) {
      sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      sortBy = col;
      sortDir = 'desc';
    }
  }

  function sortArrow(col: string): string {
    if (sortBy !== col) return '';
    return sortDir === 'asc' ? ' ▲' : ' ▼';
  }

  function formatVolume(vol: number): string {
    if (vol >= 1_000_000) return (vol / 1_000_000).toFixed(1) + 'M';
    if (vol >= 1_000) return (vol / 1_000).toFixed(0) + 'K';
    return vol.toString();
  }

  function directionColor(dir: string): string {
    if (dir === 'bullish') return 'var(--bullish)';
    if (dir === 'bearish') return 'var(--bearish)';
    return 'var(--neutral)';
  }

  function strengthBg(s: number): string {
    const colors: Record<number, string> = {
      1: 'var(--strength-1)',
      2: 'var(--strength-2)',
      3: 'var(--strength-3)',
      4: 'var(--strength-4)',
      5: 'var(--strength-5)',
    };
    return colors[s] ?? 'var(--strength-1)';
  }
</script>

<svelte:head>
  <title>Scanner - Scanify</title>
</svelte:head>

<div class="scanner-layout">
  <!-- Header -->
  <div class="scanner-header" style="border-bottom: 1px solid var(--border-subtle);">
    <div class="header-left">
      <h1 class="scanner-title" style="color: var(--text-primary);">Scanner</h1>
      <span class="scanner-meta" style="color: var(--text-tertiary);">
        {filteredResults.length} signals &bull; Updated 2s ago
      </span>
    </div>
    <div class="header-right">
      <ExportToolbar source="scanner" />
      <div class="header-divider" style="background: var(--border-subtle);"></div>
      <div class="live-indicator">
        <div class="live-dot {connected && !needsApiKey ? 'signal-ping' : ''}" style="background: {connected ? (needsApiKey ? 'var(--warning-bright, oklch(0.75 0.15 85))' : 'var(--bullish)') : 'var(--text-disabled)'};"></div>
        <span class="live-label" style="color: {connected ? (needsApiKey ? 'var(--warning-bright, oklch(0.75 0.15 85))' : 'var(--bullish)') : 'var(--text-disabled)'};">{connected ? (needsApiKey ? 'No Feed' : 'Live') : 'Offline'}</span>
      </div>
    </div>
  </div>

  <!-- Presets bar -->
  <div class="presets-bar" style="border-bottom: 1px solid var(--border-subtle);">
    {#each presets as preset (preset.id)}
      <button
        type="button"
        onclick={() => selectedPreset = preset.id}
        class="preset-button"
        style="background: {selectedPreset === preset.id ? 'var(--accent-bg)' : 'var(--bg-elevated)'};
               color: {selectedPreset === preset.id ? 'var(--accent-bright)' : 'var(--text-secondary)'};
               border: 1px solid {selectedPreset === preset.id ? 'var(--accent-dim)' : 'var(--border-subtle)'};"
      >
        <span class="preset-icon" style="color: {selectedPreset === preset.id ? 'var(--accent-bright)' : 'var(--text-tertiary)'};">
          {preset.icon}
        </span>
        {preset.name}
      </button>
    {/each}
  </div>

  <!-- Filters bar -->
  <div class="filters-bar" style="border-bottom: 1px solid var(--border-subtle); background: var(--bg-base);">
    <!-- Search -->
    <div class="search-wrapper">
      <input
        type="text"
        bind:value={searchQuery}
        placeholder="Search symbols..."
        class="search-input"
        style="background: var(--bg-surface); color: var(--text-primary); border: 1px solid var(--border-subtle);"
      />
    </div>

    <!-- Direction filter -->
    <div class="direction-filter-group" style="background: var(--bg-surface);">
      {#each ['all', 'bullish', 'bearish', 'neutral'] as dir}
        <button
          type="button"
          onclick={() => directionFilter = dir as typeof directionFilter}
          class="direction-button"
          style="background: {directionFilter === dir ? 'var(--bg-elevated)' : 'transparent'};
                 color: {directionFilter === dir ? 'var(--text-primary)' : 'var(--text-tertiary)'};"
        >
          {dir.charAt(0).toUpperCase() + dir.slice(1)}
        </button>
      {/each}
    </div>

    <!-- Min strength -->
    <div class="strength-filter">
      <span class="strength-label" style="color: var(--text-tertiary);">Min Str:</span>
      <div class="strength-buttons">
        {#each [1, 2, 3, 4, 5] as s}
          <button
            type="button"
            onclick={() => minStrength = s}
            class="strength-button"
            style="background: {minStrength <= s ? strengthBg(s) : 'var(--bg-overlay)'};
                   color: {minStrength <= s ? 'white' : 'var(--text-disabled)'};"
          >
            {s}
          </button>
        {/each}
      </div>
    </div>
  </div>

  <!-- Scanner table -->
  <div class="table-container">
    <table class="scanner-table" style="border-collapse: separate; border-spacing: 0;">
      <!-- Table header -->
      <thead class="table-head">
        <tr style="background: var(--bg-base);">
          <th class="th-left th-sortable" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);" onclick={() => toggleSort('symbol')}>
            Symbol{sortArrow('symbol')}
          </th>
          <th class="th-right th-sortable" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);" onclick={() => toggleSort('price')}>
            Price{sortArrow('price')}
          </th>
          <th class="th-right th-sortable" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);" onclick={() => toggleSort('change')}>
            Change{sortArrow('change')}
          </th>
          <th class="th-right th-sortable" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);" onclick={() => toggleSort('volume')}>
            Volume{sortArrow('volume')}
          </th>
          <th class="th-right th-sortable" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);" onclick={() => toggleSort('rvol')}>
            RVol{sortArrow('rvol')}
          </th>
          <th class="th-center" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">
            Direction
          </th>
          <th class="th-center th-sortable" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);" onclick={() => toggleSort('strength')}>
            Strength{sortArrow('strength')}
          </th>
          <th class="th-left-nosort" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">
            Sector
          </th>
          <th class="th-center" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">
            Spark
          </th>
        </tr>
      </thead>
      <tbody>
        {#if loading}
          <tr>
            <td colspan="9" class="td-empty" style="color: var(--text-tertiary);">
              <div class="loading-state">
                <div class="loading-spinner"></div>
                <span>Loading scanner...</span>
              </div>
            </td>
          </tr>
        {:else if !connected}
          <tr>
            <td colspan="9" class="td-empty" style="color: var(--text-tertiary);">
              <div class="disconnected-state">
                <span class="disconnected-icon">!</span>
                <strong>Backend Offline</strong>
                <span>Start the backend server to see live scanner data</span>
              </div>
            </td>
          </tr>
        {:else if needsApiKey}
          <tr>
            <td colspan="9" class="td-empty" style="color: var(--text-tertiary);">
              <div class="disconnected-state">
                <span class="disconnected-icon" style="color: var(--warning-bright, oklch(0.75 0.15 85));">!</span>
                <strong>Data Provider Not Configured</strong>
                <span>Configure an FMP or other market data API key in <a href="/settings" style="color: var(--accent);">Settings</a></span>
              </div>
            </td>
          </tr>
        {:else if filteredResults.length === 0}
          <tr>
            <td colspan="9" class="td-empty" style="color: var(--text-tertiary);">
              {#if scanResults.length === 0}
                No signals found
              {:else}
                No results match current filters
              {/if}
            </td>
          </tr>
        {:else}
          {#each filteredResults as result, i (result.id)}
            <tr
              class="table-row"
              style="background: {i % 2 === 0 ? 'var(--bg-surface)' : 'transparent'}; border-bottom: 1px solid var(--border-subtle);"
            >
              <!-- Symbol + Name -->
              <td class="td-symbol">
                <div class="symbol-cell">
                  <span class="symbol-ticker" style="color: var(--text-primary);">{result.symbol}</span>
                  <span class="symbol-name" style="color: var(--text-tertiary);">{result.name}</span>
                </div>
              </td>
              <!-- Price -->
              <td class="td-right td-mono" style="color: var(--text-primary);">
                ${result.price.toFixed(2)}
              </td>
              <!-- Change -->
              <td class="td-right td-mono td-medium" style="color: {result.changePercent >= 0 ? 'var(--bullish)' : 'var(--bearish)'};">
                {result.changePercent >= 0 ? '+' : ''}{result.changePercent.toFixed(2)}%
              </td>
              <!-- Volume -->
              <td class="td-right td-mono" style="color: var(--text-secondary);">
                {formatVolume(result.volume)}
              </td>
              <!-- Relative Volume -->
              <td class="td-right td-mono" style="color: {result.relativeVolume >= 2 ? 'var(--warning-bright)' : 'var(--text-secondary)'};">
                {result.relativeVolume.toFixed(1)}x
              </td>
              <!-- Direction -->
              <td class="td-center">
                <span
                  class="direction-badge"
                  style="background: {result.direction === 'bullish' ? 'var(--bullish-bg)' : result.direction === 'bearish' ? 'var(--bearish-bg)' : 'var(--neutral-bg)'};
                         color: {directionColor(result.direction)};
                         border: 1px solid {result.direction === 'bullish' ? 'oklch(0.45 0.12 155 / 0.3)' : result.direction === 'bearish' ? 'oklch(0.42 0.12 25 / 0.3)' : 'oklch(0.45 0.08 250 / 0.3)'};"
                >
                  {result.direction === 'bullish' ? 'BULL' : result.direction === 'bearish' ? 'BEAR' : 'NEUT'}
                </span>
              </td>
              <!-- Strength -->
              <td class="td-center">
                <div class="strength-meter">
                  {#each Array(5) as _, si}
                    <div
                      class="strength-pip"
                      style="background: {si < result.strength ? strengthBg(result.strength) : 'var(--bg-overlay)'};"
                    ></div>
                  {/each}
                </div>
              </td>
              <!-- Sector -->
              <td class="td-sector" style="color: var(--text-tertiary);">
                {result.sector}
              </td>
              <!-- Sparkline -->
              <td class="td-center">
                <SparkLine data={result.sparklineData} width={80} height={20} showLastPoint={true} />
              </td>
            </tr>
          {/each}
        {/if}
      </tbody>
    </table>
  </div>
</div>

<style>
  /* ---- Layout ---- */
  .scanner-layout {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }

  /* ---- Header ---- */
  .scanner-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-inline: 20px;
    padding-block: 12px;
    flex-shrink: 0;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .scanner-title {
    font-size: var(--text-lg);
    font-weight: 700;
  }

  .scanner-meta {
    font-size: var(--text-xs);
    font-family: var(--font-mono);
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

  .live-indicator {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .live-dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
  }

  .live-label {
    font-size: var(--text-xs);
  }

  /* ---- Presets bar ---- */
  .presets-bar {
    display: flex;
    gap: 8px;
    padding-inline: 20px;
    padding-block: 12px;
    overflow-x: auto;
    flex-shrink: 0;
  }

  .preset-button {
    display: flex;
    align-items: center;
    gap: 8px;
    border-radius: var(--radius-lg);
    padding-inline: 12px;
    padding-block: 8px;
    font-size: var(--text-xs);
    font-weight: 500;
    white-space: nowrap;
    transition: all 150ms;
  }

  .preset-icon {
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 700;
  }

  /* ---- Filters bar ---- */
  .filters-bar {
    display: flex;
    align-items: center;
    gap: 16px;
    padding-inline: 20px;
    padding-block: 12px;
    flex-shrink: 0;
  }

  .search-wrapper {
    position: relative;
    flex: 1;
    max-width: 20rem;
  }

  .search-input {
    width: 100%;
    border-radius: var(--radius-md);
    padding-inline: 12px;
    padding-block: 6px;
    font-size: var(--text-xs);
    outline: none;
  }

  .direction-filter-group {
    display: flex;
    gap: 4px;
    border-radius: var(--radius-lg);
    padding: 2px;
  }

  .direction-button {
    border-radius: var(--radius-md);
    padding-inline: 10px;
    padding-block: 4px;
    font-size: 11px;
    font-weight: 500;
    transition: all 150ms;
  }

  .strength-filter {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .strength-label {
    font-size: 11px;
  }

  .strength-buttons {
    display: flex;
    gap: 2px;
  }

  .strength-button {
    width: 20px;
    height: 20px;
    border-radius: var(--radius-md);
    font-size: 10px;
    font-weight: 700;
    transition: all 150ms;
  }

  /* ---- Scanner table ---- */
  .table-container {
    flex: 1;
    overflow: auto;
    min-height: 0;
  }

  .scanner-table {
    width: 100%;
    font-size: var(--text-xs);
  }

  .table-head {
    position: sticky;
    top: 0;
    z-index: 10;
  }

  /* ---- Table header cells ---- */
  .th-left,
  .th-left-nosort {
    text-align: left;
    padding-inline: 12px;
    padding-block: 10px;
    font-weight: 500;
  }

  .th-left {
    padding-left: 16px;
  }

  .th-right {
    text-align: right;
    padding-inline: 12px;
    padding-block: 10px;
    font-weight: 500;
  }

  .th-center {
    text-align: center;
    padding-inline: 12px;
    padding-block: 10px;
    font-weight: 500;
  }

  .th-sortable {
    cursor: pointer;
    user-select: none;
  }

  /* ---- Table body rows ---- */
  .table-row {
    transition: color 150ms, background-color 150ms;
    cursor: pointer;
  }

  /* ---- Table body cells ---- */
  .td-symbol {
    padding-left: 16px;
    padding-right: 12px;
    padding-block: 10px;
  }

  .symbol-cell {
    display: flex;
    flex-direction: column;
  }

  .symbol-ticker {
    font-weight: 700;
    font-family: var(--font-mono);
  }

  .symbol-name {
    font-size: 10px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 140px;
  }

  .td-right {
    text-align: right;
    padding-inline: 12px;
    padding-block: 10px;
  }

  .td-center {
    text-align: center;
    padding-inline: 12px;
    padding-block: 10px;
  }

  .td-mono {
    font-family: var(--font-mono);
  }

  .td-medium {
    font-weight: 500;
  }

  .td-sector {
    text-align: left;
    padding-inline: 12px;
    padding-block: 10px;
    font-size: 10px;
  }

  .td-empty {
    text-align: center;
    padding-block: 48px;
    font-size: var(--text-sm);
  }

  /* ---- Direction badge ---- */
  .direction-badge {
    display: inline-flex;
    align-items: center;
    border-radius: var(--radius-full);
    padding-inline: 8px;
    padding-block: 2px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
  }

  /* ---- Strength meter ---- */
  .strength-meter {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 2px;
  }

  .strength-pip {
    height: 6px;
    width: 10px;
    border-radius: var(--radius-full);
  }

  /* ---- Loading state ---- */
  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    padding-block: 24px;
  }

  .loading-spinner {
    width: 24px;
    height: 24px;
    border: 2px solid var(--border-subtle);
    border-top-color: var(--accent-bright);
    border-radius: var(--radius-full);
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* ---- Disconnected state ---- */
  .disconnected-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    padding-block: 24px;
  }

  .disconnected-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: var(--radius-full);
    background: var(--bg-overlay);
    color: var(--text-tertiary);
    font-weight: 700;
    font-size: var(--text-lg);
  }
</style>
