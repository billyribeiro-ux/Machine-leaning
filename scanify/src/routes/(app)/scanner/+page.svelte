<script lang="ts">
  import SparkLine from '$lib/components/data/SparkLine.svelte';
  import ExportToolbar from '$lib/components/ui/ExportToolbar.svelte';

  // ---- Filter state ----
  let selectedPreset = $state('momentum');
  let directionFilter = $state<'all' | 'bullish' | 'bearish' | 'neutral'>('all');
  let minStrength = $state(1);
  let searchQuery = $state('');
  let sortBy = $state('strength');
  let sortDir = $state<'asc' | 'desc'>('desc');

  // ---- Sparkline random walk generator ----
  function generateSparkline(base: number, volatility: number): number[] {
    const points: number[] = [base];
    for (let i = 1; i < 20; i++) {
      const delta = (Math.random() - 0.48) * volatility;
      points.push(points[i - 1] + delta);
    }
    return points;
  }

  // ---- Presets ----
  const presets = [
    { id: 'momentum', name: 'Momentum', icon: '>>', description: 'Strong directional momentum' },
    { id: 'volume', name: 'Volume Surge', icon: 'V+', description: 'Unusual volume spikes' },
    { id: 'breakout', name: 'Breakouts', icon: '/\\', description: 'Breaking key price levels' },
    { id: 'gap', name: 'Gap Scanner', icon: '||', description: 'Pre-market gaps' },
    { id: 'squeeze', name: 'Squeeze', icon: '<>', description: 'Bollinger Band squeeze' },
    { id: 'reversal', name: 'Reversals', icon: 'R', description: 'Potential trend reversals' },
  ];

  // ---- Mock scan results (25 items) ----
  interface MockScanResult {
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

  const mockResults: MockScanResult[] = [
    { id: '1',  symbol: 'AAPL',  name: 'Apple Inc.',            price: 178.50, change: 3.25,   changePercent: 1.85,  volume: 42_500_000, relativeVolume: 1.8, direction: 'bullish',  strength: 4, sector: 'Technology',     category: 'momentum', sparklineData: generateSparkline(175, 2),    timestamp: new Date().toISOString() },
    { id: '2',  symbol: 'NVDA',  name: 'NVIDIA Corporation',    price: 875.30, change: 28.70,  changePercent: 3.39,  volume: 38_200_000, relativeVolume: 2.4, direction: 'bullish',  strength: 5, sector: 'Technology',     category: 'momentum', sparklineData: generateSparkline(850, 15),   timestamp: new Date().toISOString() },
    { id: '3',  symbol: 'TSLA',  name: 'Tesla Inc.',            price: 245.10, change: -8.30,  changePercent: -3.27, volume: 48_300_000, relativeVolume: 2.1, direction: 'bearish',  strength: 4, sector: 'Consumer Disc.', category: 'momentum', sparklineData: generateSparkline(252, 5),    timestamp: new Date().toISOString() },
    { id: '4',  symbol: 'MSFT',  name: 'Microsoft Corporation', price: 415.20, change: 5.80,   changePercent: 1.42,  volume: 22_100_000, relativeVolume: 1.2, direction: 'bullish',  strength: 3, sector: 'Technology',     category: 'momentum', sparklineData: generateSparkline(410, 3),    timestamp: new Date().toISOString() },
    { id: '5',  symbol: 'AMD',   name: 'Advanced Micro Devices',price: 165.40, change: 6.20,   changePercent: 3.89,  volume: 35_600_000, relativeVolume: 2.8, direction: 'bullish',  strength: 5, sector: 'Technology',     category: 'volume',   sparklineData: generateSparkline(160, 4),    timestamp: new Date().toISOString() },
    { id: '6',  symbol: 'META',  name: 'Meta Platforms Inc.',   price: 505.80, change: 12.40,  changePercent: 2.51,  volume: 18_700_000, relativeVolume: 1.5, direction: 'bullish',  strength: 4, sector: 'Technology',     category: 'breakout', sparklineData: generateSparkline(495, 6),    timestamp: new Date().toISOString() },
    { id: '7',  symbol: 'AMZN',  name: 'Amazon.com Inc.',       price: 185.60, change: 2.10,   changePercent: 1.14,  volume: 28_400_000, relativeVolume: 1.3, direction: 'bullish',  strength: 3, sector: 'Consumer Disc.', category: 'momentum', sparklineData: generateSparkline(183, 2),    timestamp: new Date().toISOString() },
    { id: '8',  symbol: 'GOOGL', name: 'Alphabet Inc.',         price: 152.30, change: -1.20,  changePercent: -0.78, volume: 19_800_000, relativeVolume: 0.9, direction: 'neutral',  strength: 2, sector: 'Technology',     category: 'momentum', sparklineData: generateSparkline(153, 1.5),  timestamp: new Date().toISOString() },
    { id: '9',  symbol: 'JPM',   name: 'JPMorgan Chase & Co.',  price: 198.75, change: 4.50,   changePercent: 2.32,  volume: 12_300_000, relativeVolume: 1.6, direction: 'bullish',  strength: 3, sector: 'Financials',     category: 'breakout', sparklineData: generateSparkline(195, 2),    timestamp: new Date().toISOString() },
    { id: '10', symbol: 'V',     name: 'Visa Inc.',             price: 282.90, change: -2.40,  changePercent: -0.84, volume: 6_500_000,  relativeVolume: 0.8, direction: 'bearish',  strength: 2, sector: 'Financials',     category: 'momentum', sparklineData: generateSparkline(284, 2),    timestamp: new Date().toISOString() },
    { id: '11', symbol: 'UNH',   name: 'UnitedHealth Group',    price: 527.40, change: -14.20, changePercent: -2.62, volume: 8_900_000,  relativeVolume: 2.3, direction: 'bearish',  strength: 4, sector: 'Healthcare',     category: 'volume',   sparklineData: generateSparkline(540, 8),    timestamp: new Date().toISOString() },
    { id: '12', symbol: 'XOM',   name: 'Exxon Mobil Corp.',     price: 104.80, change: 1.95,   changePercent: 1.90,  volume: 15_200_000, relativeVolume: 1.4, direction: 'bullish',  strength: 3, sector: 'Energy',         category: 'momentum', sparklineData: generateSparkline(103, 1.2),  timestamp: new Date().toISOString() },
    { id: '13', symbol: 'LLY',   name: 'Eli Lilly and Co.',     price: 782.50, change: 22.30,  changePercent: 2.93,  volume: 5_800_000,  relativeVolume: 2.0, direction: 'bullish',  strength: 5, sector: 'Healthcare',     category: 'breakout', sparklineData: generateSparkline(762, 12),   timestamp: new Date().toISOString() },
    { id: '14', symbol: 'AVGO',  name: 'Broadcom Inc.',         price: 1285.40,change: 45.60,  changePercent: 3.68,  volume: 4_200_000,  relativeVolume: 2.6, direction: 'bullish',  strength: 5, sector: 'Technology',     category: 'volume',   sparklineData: generateSparkline(1240, 25),  timestamp: new Date().toISOString() },
    { id: '15', symbol: 'CRM',   name: 'Salesforce Inc.',       price: 272.30, change: -5.40,  changePercent: -1.94, volume: 7_100_000,  relativeVolume: 1.1, direction: 'bearish',  strength: 3, sector: 'Technology',     category: 'momentum', sparklineData: generateSparkline(276, 3),    timestamp: new Date().toISOString() },
    { id: '16', symbol: 'BA',    name: 'Boeing Company',        price: 198.20, change: 8.90,   changePercent: 4.70,  volume: 11_400_000, relativeVolume: 3.2, direction: 'bullish',  strength: 4, sector: 'Industrials',    category: 'volume',   sparklineData: generateSparkline(190, 5),    timestamp: new Date().toISOString() },
    { id: '17', symbol: 'DIS',   name: 'Walt Disney Co.',       price: 112.60, change: -3.80,  changePercent: -3.27, volume: 14_600_000, relativeVolume: 1.9, direction: 'bearish',  strength: 3, sector: 'Communication', category: 'momentum', sparklineData: generateSparkline(116, 2),    timestamp: new Date().toISOString() },
    { id: '18', symbol: 'NFLX',  name: 'Netflix Inc.',          price: 628.40, change: 15.70,  changePercent: 2.56,  volume: 6_800_000,  relativeVolume: 1.7, direction: 'bullish',  strength: 4, sector: 'Communication', category: 'breakout', sparklineData: generateSparkline(614, 8),    timestamp: new Date().toISOString() },
    { id: '19', symbol: 'COIN',  name: 'Coinbase Global Inc.',  price: 225.80, change: 18.50,  changePercent: 8.93,  volume: 22_500_000, relativeVolume: 3.8, direction: 'bullish',  strength: 5, sector: 'Financials',     category: 'volume',   sparklineData: generateSparkline(208, 10),   timestamp: new Date().toISOString() },
    { id: '20', symbol: 'PLTR',  name: 'Palantir Technologies', price: 24.50,  change: 1.80,   changePercent: 7.93,  volume: 45_200_000, relativeVolume: 2.9, direction: 'bullish',  strength: 4, sector: 'Technology',     category: 'momentum', sparklineData: generateSparkline(23, 0.8),   timestamp: new Date().toISOString() },
    { id: '21', symbol: 'SMCI',  name: 'Super Micro Computer',  price: 745.20, change: -32.10, changePercent: -4.13, volume: 9_300_000,  relativeVolume: 2.2, direction: 'bearish',  strength: 4, sector: 'Technology',     category: 'volume',   sparklineData: generateSparkline(775, 18),   timestamp: new Date().toISOString() },
    { id: '22', symbol: 'INTC',  name: 'Intel Corporation',     price: 43.20,  change: -1.50,  changePercent: -3.36, volume: 32_100_000, relativeVolume: 1.8, direction: 'bearish',  strength: 3, sector: 'Technology',     category: 'momentum', sparklineData: generateSparkline(44.5, 1),   timestamp: new Date().toISOString() },
    { id: '23', symbol: 'RIVN',  name: 'Rivian Automotive',     price: 17.80,  change: 1.20,   changePercent: 7.23,  volume: 28_900_000, relativeVolume: 3.1, direction: 'bullish',  strength: 3, sector: 'Consumer Disc.', category: 'volume',   sparklineData: generateSparkline(16.8, 0.6), timestamp: new Date().toISOString() },
    { id: '24', symbol: 'PANW',  name: 'Palo Alto Networks',    price: 312.60, change: 7.40,   changePercent: 2.42,  volume: 5_100_000,  relativeVolume: 1.3, direction: 'bullish',  strength: 3, sector: 'Technology',     category: 'breakout', sparklineData: generateSparkline(306, 4),    timestamp: new Date().toISOString() },
    { id: '25', symbol: 'SQ',    name: 'Block Inc.',            price: 78.90,  change: -2.60,  changePercent: -3.19, volume: 10_800_000, relativeVolume: 1.6, direction: 'bearish',  strength: 2, sector: 'Financials',     category: 'momentum', sparklineData: generateSparkline(81, 1.8),   timestamp: new Date().toISOString() },
  ];

  // ---- Filtered + sorted results ----
  let filteredResults = $derived.by(() => {
    let results = mockResults;
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
    const colors = ['', 'var(--strength-1)', 'var(--strength-2)', 'var(--strength-3)', 'var(--strength-4)', 'var(--strength-5)'];
    return colors[s] ?? colors[1];
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
        <div class="live-dot signal-ping" style="background: var(--bullish);"></div>
        <span class="live-label" style="color: var(--bullish);">Live</span>
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

        {#if filteredResults.length === 0}
          <tr>
            <td colspan="9" class="td-empty" style="color: var(--text-tertiary);">
              No results match current filters
            </td>
          </tr>
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
</style>
