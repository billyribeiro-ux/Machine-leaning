<script lang="ts">
  import SparkLine from '$lib/components/data/SparkLine.svelte';

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
    return sortDir === 'asc' ? ' \u25B2' : ' \u25BC';
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

<div class="flex flex-col h-full overflow-hidden">
  <!-- Header -->
  <div class="flex items-center justify-between px-5 py-3 shrink-0" style="border-bottom: 1px solid var(--border-subtle);">
    <div class="flex items-center gap-3">
      <h1 class="text-lg font-bold" style="color: var(--text-primary);">Scanner</h1>
      <span class="text-xs font-mono" style="color: var(--text-tertiary);">
        {filteredResults.length} signals &bull; Updated 2s ago
      </span>
    </div>
    <div class="flex items-center gap-2">
      <div class="w-2 h-2 rounded-full signal-ping" style="background: var(--bullish);"></div>
      <span class="text-xs" style="color: var(--bullish);">Live</span>
    </div>
  </div>

  <!-- Presets bar -->
  <div class="flex gap-2 px-5 py-3 overflow-x-auto shrink-0" style="border-bottom: 1px solid var(--border-subtle);">
    {#each presets as preset (preset.id)}
      <button
        type="button"
        onclick={() => selectedPreset = preset.id}
        class="flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium whitespace-nowrap transition-all"
        style="background: {selectedPreset === preset.id ? 'var(--accent-bg)' : 'var(--bg-elevated)'};
               color: {selectedPreset === preset.id ? 'var(--accent-bright)' : 'var(--text-secondary)'};
               border: 1px solid {selectedPreset === preset.id ? 'var(--accent-dim)' : 'var(--border-subtle)'};"
      >
        <span class="font-mono text-[10px] font-bold" style="color: {selectedPreset === preset.id ? 'var(--accent-bright)' : 'var(--text-tertiary)'};">
          {preset.icon}
        </span>
        {preset.name}
      </button>
    {/each}
  </div>

  <!-- Filters bar -->
  <div class="flex items-center gap-4 px-5 py-3 shrink-0" style="border-bottom: 1px solid var(--border-subtle); background: var(--bg-base);">
    <!-- Search -->
    <div class="relative flex-1 max-w-xs">
      <input
        type="text"
        bind:value={searchQuery}
        placeholder="Search symbols..."
        class="w-full rounded-md px-3 py-1.5 text-xs outline-none"
        style="background: var(--bg-surface); color: var(--text-primary); border: 1px solid var(--border-subtle);"
      />
    </div>

    <!-- Direction filter -->
    <div class="flex gap-1 rounded-lg p-0.5" style="background: var(--bg-surface);">
      {#each ['all', 'bullish', 'bearish', 'neutral'] as dir}
        <button
          type="button"
          onclick={() => directionFilter = dir as typeof directionFilter}
          class="rounded-md px-2.5 py-1 text-[11px] font-medium transition-all"
          style="background: {directionFilter === dir ? 'var(--bg-elevated)' : 'transparent'};
                 color: {directionFilter === dir ? 'var(--text-primary)' : 'var(--text-tertiary)'};"
        >
          {dir.charAt(0).toUpperCase() + dir.slice(1)}
        </button>
      {/each}
    </div>

    <!-- Min strength -->
    <div class="flex items-center gap-2">
      <span class="text-[11px]" style="color: var(--text-tertiary);">Min Str:</span>
      <div class="flex gap-0.5">
        {#each [1, 2, 3, 4, 5] as s}
          <button
            type="button"
            onclick={() => minStrength = s}
            class="w-5 h-5 rounded text-[10px] font-bold transition-all"
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
  <div class="flex-1 overflow-auto min-h-0">
    <table class="w-full text-xs" style="border-collapse: separate; border-spacing: 0;">
      <!-- Table header -->
      <thead class="sticky top-0 z-10">
        <tr style="background: var(--bg-base);">
          <th class="text-left px-4 py-2.5 font-medium cursor-pointer select-none" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);" onclick={() => toggleSort('symbol')}>
            Symbol{sortArrow('symbol')}
          </th>
          <th class="text-right px-3 py-2.5 font-medium cursor-pointer select-none" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);" onclick={() => toggleSort('price')}>
            Price{sortArrow('price')}
          </th>
          <th class="text-right px-3 py-2.5 font-medium cursor-pointer select-none" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);" onclick={() => toggleSort('change')}>
            Change{sortArrow('change')}
          </th>
          <th class="text-right px-3 py-2.5 font-medium cursor-pointer select-none" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);" onclick={() => toggleSort('volume')}>
            Volume{sortArrow('volume')}
          </th>
          <th class="text-right px-3 py-2.5 font-medium cursor-pointer select-none" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);" onclick={() => toggleSort('rvol')}>
            RVol{sortArrow('rvol')}
          </th>
          <th class="text-center px-3 py-2.5 font-medium" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">
            Direction
          </th>
          <th class="text-center px-3 py-2.5 font-medium cursor-pointer select-none" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);" onclick={() => toggleSort('strength')}>
            Strength{sortArrow('strength')}
          </th>
          <th class="text-left px-3 py-2.5 font-medium" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">
            Sector
          </th>
          <th class="text-center px-3 py-2.5 font-medium" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">
            Spark
          </th>
        </tr>
      </thead>
      <tbody>
        {#each filteredResults() as result, i (result.id)}
          <tr
            class="transition-colors cursor-pointer"
            style="background: {i % 2 === 0 ? 'var(--bg-surface)' : 'transparent'}; border-bottom: 1px solid var(--border-subtle);"
          >
            <!-- Symbol + Name -->
            <td class="px-4 py-2.5">
              <div class="flex flex-col">
                <span class="font-bold font-mono" style="color: var(--text-primary);">{result.symbol}</span>
                <span class="text-[10px] truncate max-w-[140px]" style="color: var(--text-tertiary);">{result.name}</span>
              </div>
            </td>
            <!-- Price -->
            <td class="text-right px-3 py-2.5 font-mono" style="color: var(--text-primary);">
              ${result.price.toFixed(2)}
            </td>
            <!-- Change -->
            <td class="text-right px-3 py-2.5 font-mono font-medium" style="color: {result.changePercent >= 0 ? 'var(--bullish)' : 'var(--bearish)'};">
              {result.changePercent >= 0 ? '+' : ''}{result.changePercent.toFixed(2)}%
            </td>
            <!-- Volume -->
            <td class="text-right px-3 py-2.5 font-mono" style="color: var(--text-secondary);">
              {formatVolume(result.volume)}
            </td>
            <!-- Relative Volume -->
            <td class="text-right px-3 py-2.5 font-mono" style="color: {result.relativeVolume >= 2 ? 'var(--warning-bright)' : 'var(--text-secondary)'};">
              {result.relativeVolume.toFixed(1)}x
            </td>
            <!-- Direction -->
            <td class="text-center px-3 py-2.5">
              <span
                class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase"
                style="background: {result.direction === 'bullish' ? 'var(--bullish-bg)' : result.direction === 'bearish' ? 'var(--bearish-bg)' : 'var(--neutral-bg)'};
                       color: {directionColor(result.direction)};
                       border: 1px solid {result.direction === 'bullish' ? 'oklch(0.45 0.12 155 / 0.3)' : result.direction === 'bearish' ? 'oklch(0.42 0.12 25 / 0.3)' : 'oklch(0.45 0.08 250 / 0.3)'};"
              >
                {result.direction === 'bullish' ? 'BULL' : result.direction === 'bearish' ? 'BEAR' : 'NEUT'}
              </span>
            </td>
            <!-- Strength -->
            <td class="text-center px-3 py-2.5">
              <div class="flex items-center justify-center gap-0.5">
                {#each Array(5) as _, si}
                  <div
                    class="h-1.5 w-2.5 rounded-full"
                    style="background: {si < result.strength ? strengthBg(result.strength) : 'var(--bg-overlay)'};"
                  ></div>
                {/each}
              </div>
            </td>
            <!-- Sector -->
            <td class="text-left px-3 py-2.5 text-[10px]" style="color: var(--text-tertiary);">
              {result.sector}
            </td>
            <!-- Sparkline -->
            <td class="text-center px-3 py-2.5">
              <SparkLine data={result.sparklineData} width={80} height={20} showLastPoint={true} />
            </td>
          </tr>
        {/each}

        {#if filteredResults().length === 0}
          <tr>
            <td colspan="9" class="text-center py-12 text-sm" style="color: var(--text-tertiary);">
              No results match current filters
            </td>
          </tr>
        {/if}
      </tbody>
    </table>
  </div>
</div>
