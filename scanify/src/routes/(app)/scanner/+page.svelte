<script lang="ts">
  import { onMount } from 'svelte';
  import ExportToolbar from '$lib/components/ui/ExportToolbar.svelte';

  const API_BASE = 'http://localhost:8000';

  // ---- Types ----
  interface ScanResult {
    id: number;
    symbol: string;
    name: string;
    price: number;
    change: number;
    changePercent: number;
    volume: number;
    signalType: 'Gamma' | 'Volume' | 'Flow';
    strength: number;
    score: number;
    sector: string;
    marketCap: 'Large' | 'Mid' | 'Small';
    timestamp: string;
  }

  // ---- Scan state ----
  let scanStatus = $state<'scanning' | 'paused'>('scanning');
  let scanCount = $state(0);
  let lastScanTime = $state('');
  let selectedRowId = $state<number | null>(null);

  // ---- Connection state ----
  let loading = $state(false);
  let connected = $state(false);
  let needsApiKey = $state(false);

  // ---- Filter state ----
  let marketCapFilter = $state<'All' | 'Large' | 'Mid' | 'Small'>('All');
  let sectorFilter = $state('All');
  let signalTypeFilter = $state<'All' | 'Gamma' | 'Volume' | 'Flow'>('All');
  let strengthFilter = $state(0);

  // ---- Sort state ----
  let sortBy = $state<string>('rank');
  let sortDir = $state<'asc' | 'desc'>('asc');

  // ---- Realistic simulated stock data ----
  const stockPool: Array<{ sym: string; name: string; sector: string; cap: 'Large' | 'Mid' | 'Small'; basePrice: number }> = [
    { sym: 'SPY',   name: 'SPDR S&P 500 ETF',         sector: 'ETF',           cap: 'Large', basePrice: 587.42 },
    { sym: 'QQQ',   name: 'Invesco QQQ Trust',         sector: 'ETF',           cap: 'Large', basePrice: 513.18 },
    { sym: 'AAPL',  name: 'Apple Inc',                  sector: 'Technology',    cap: 'Large', basePrice: 234.56 },
    { sym: 'NVDA',  name: 'NVIDIA Corporation',         sector: 'Technology',    cap: 'Large', basePrice: 141.28 },
    { sym: 'TSLA',  name: 'Tesla Inc',                  sector: 'Consumer Disc', cap: 'Large', basePrice: 352.74 },
    { sym: 'AMD',   name: 'Advanced Micro Devices',     sector: 'Technology',    cap: 'Large', basePrice: 168.93 },
    { sym: 'META',  name: 'Meta Platforms Inc',          sector: 'Technology',    cap: 'Large', basePrice: 627.14 },
    { sym: 'MSFT',  name: 'Microsoft Corporation',      sector: 'Technology',    cap: 'Large', basePrice: 468.35 },
    { sym: 'AMZN',  name: 'Amazon.com Inc',             sector: 'Consumer Disc', cap: 'Large', basePrice: 213.47 },
    { sym: 'GOOGL', name: 'Alphabet Inc',               sector: 'Technology',    cap: 'Large', basePrice: 182.65 },
    { sym: 'JPM',   name: 'JPMorgan Chase & Co',        sector: 'Financials',    cap: 'Large', basePrice: 247.82 },
    { sym: 'V',     name: 'Visa Inc',                   sector: 'Financials',    cap: 'Large', basePrice: 312.19 },
    { sym: 'UNH',   name: 'UnitedHealth Group',         sector: 'Healthcare',    cap: 'Large', basePrice: 543.67 },
    { sym: 'JNJ',   name: 'Johnson & Johnson',          sector: 'Healthcare',    cap: 'Large', basePrice: 158.42 },
    { sym: 'WMT',   name: 'Walmart Inc',                sector: 'Consumer Stpl', cap: 'Large', basePrice: 93.28 },
    { sym: 'PG',    name: 'Procter & Gamble',           sector: 'Consumer Stpl', cap: 'Large', basePrice: 172.84 },
    { sym: 'XOM',   name: 'Exxon Mobil Corp',           sector: 'Energy',        cap: 'Large', basePrice: 108.53 },
    { sym: 'CVX',   name: 'Chevron Corporation',        sector: 'Energy',        cap: 'Large', basePrice: 153.67 },
    { sym: 'NFLX',  name: 'Netflix Inc',                sector: 'Technology',    cap: 'Large', basePrice: 912.34 },
    { sym: 'CRM',   name: 'Salesforce Inc',             sector: 'Technology',    cap: 'Large', basePrice: 342.57 },
    { sym: 'COIN',  name: 'Coinbase Global',            sector: 'Financials',    cap: 'Mid',   basePrice: 278.93 },
    { sym: 'PLTR',  name: 'Palantir Technologies',      sector: 'Technology',    cap: 'Mid',   basePrice: 82.15 },
    { sym: 'SOFI',  name: 'SoFi Technologies',          sector: 'Financials',    cap: 'Mid',   basePrice: 14.87 },
    { sym: 'MARA',  name: 'Marathon Digital Holdings',   sector: 'Technology',    cap: 'Small', basePrice: 23.41 },
    { sym: 'RIVN',  name: 'Rivian Automotive',           sector: 'Consumer Disc', cap: 'Mid',   basePrice: 16.32 },
    { sym: 'SNAP',  name: 'Snap Inc',                   sector: 'Technology',    cap: 'Mid',   basePrice: 11.28 },
    { sym: 'RIOT',  name: 'Riot Platforms Inc',          sector: 'Technology',    cap: 'Small', basePrice: 12.56 },
    { sym: 'DKNG',  name: 'DraftKings Inc',             sector: 'Consumer Disc', cap: 'Mid',   basePrice: 47.83 },
    { sym: 'SQ',    name: 'Block Inc',                  sector: 'Financials',    cap: 'Mid',   basePrice: 82.46 },
    { sym: 'RBLX',  name: 'Roblox Corporation',         sector: 'Technology',    cap: 'Mid',   basePrice: 62.37 },
  ];

  const signalTypes: Array<'Gamma' | 'Volume' | 'Flow'> = ['Gamma', 'Volume', 'Flow'];
  const sectorList = ['All', 'Technology', 'Financials', 'Healthcare', 'Consumer Disc', 'Consumer Stpl', 'Energy', 'ETF'];

  function generateScanData(): ScanResult[] {
    const now = new Date();
    return stockPool.map((s, i) => {
      const changePct = Math.round(((Math.random() - 0.42) * 8) * 100) / 100;
      const change = Math.round((s.basePrice * (changePct / 100)) * 100) / 100;
      const price = Math.round((s.basePrice + change) * 100) / 100;
      const signal = signalTypes[Math.floor(Math.random() * 3)]!;
      const strength = Math.min(5, Math.max(1, Math.round(Math.abs(changePct) * 0.8 + Math.random() * 2)));
      const score = Math.min(100, Math.round(strength * 17 + Math.random() * 15));
      const ts = new Date(now.getTime() - Math.random() * 300_000);

      return {
        id: i + 1,
        symbol: s.sym,
        name: s.name,
        price,
        change,
        changePercent: changePct,
        volume: Math.round((Math.random() * 80 + 5) * 1_000_000),
        signalType: signal,
        strength,
        score,
        sector: s.sector,
        marketCap: s.cap,
        timestamp: ts.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      };
    });
  }

  let scanResults: ScanResult[] = $state(generateScanData());

  // ---- API health check first, then data fetch ----
  async function fetchScannerData() {
    try {
      const health = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(5000) });
      connected = health.ok;
    } catch {
      connected = false;
    }

    if (connected) {
      try {
        const response = await fetch(`${API_BASE}/api/equity/market/movers?limit=30`, { signal: AbortSignal.timeout(3000) });
        if (!response.ok) {
          needsApiKey = true;
        } else {
          const data = await response.json();
          const mapped: ScanResult[] = [];
          const seen = new Set<string>();
          let idx = 0;
          for (const [, items] of Object.entries(data)) {
            if (!Array.isArray(items)) continue;
            for (const item of items) {
              const sym = item.symbol ?? item.ticker ?? '';
              if (!sym || seen.has(sym)) continue;
              seen.add(sym);
              idx++;
              const price = item.price ?? item.last_price ?? 0;
              const change = item.change ?? item.price_change ?? 0;
              const pct = item.change_percent ?? item.percent_change ?? (price > 0 ? (change / (price - change)) * 100 : 0);
              const str = Math.min(5, Math.max(1, Math.round(Math.abs(pct) * 0.8 + 1)));
              mapped.push({
                id: idx,
                symbol: sym,
                name: item.name ?? item.company_name ?? sym,
                price,
                change,
                changePercent: Math.round(pct * 100) / 100,
                volume: item.volume ?? 0,
                signalType: signalTypes[idx % 3]!,
                strength: str,
                score: Math.min(100, Math.round(str * 17 + Math.random() * 15)),
                sector: item.sector ?? 'Unknown',
                marketCap: 'Large',
                timestamp: new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }),
              });
            }
          }
          if (mapped.length > 0) {
            scanResults = mapped;
            needsApiKey = false;
            loading = false;
            scanCount++;
            lastScanTime = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
            return;
          }
        }
      } catch {
        // Fall through to simulated data
      }
    }

    // Simulated data as fallback
    scanResults = generateScanData();
    scanCount++;
    lastScanTime = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    loading = false;
  }

  onMount(() => {
    fetchScannerData();
    const interval = setInterval(() => {
      if (scanStatus === 'scanning') {
        scanResults = generateScanData();
        scanCount++;
        lastScanTime = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
        loading = false;
      }
    }, 15_000);
    // Safety: ensure loading is cleared after a max of 5 seconds
    setTimeout(() => {
      if (loading) {
        scanResults = generateScanData();
        scanCount++;
        lastScanTime = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
        loading = false;
      }
    }, 5000);
    return () => clearInterval(interval);
  });

  // ---- Filtered + sorted results ----
  let filteredResults = $derived.by(() => {
    let results = scanResults;
    if (marketCapFilter !== 'All') results = results.filter(r => r.marketCap === marketCapFilter);
    if (sectorFilter !== 'All') results = results.filter(r => r.sector === sectorFilter);
    if (signalTypeFilter !== 'All') results = results.filter(r => r.signalType === signalTypeFilter);
    if (strengthFilter > 0) results = results.filter(r => r.strength >= strengthFilter);

    results = [...results].sort((a, b) => {
      let av: number, bv: number;
      switch (sortBy) {
        case 'symbol': return sortDir === 'asc' ? a.symbol.localeCompare(b.symbol) : b.symbol.localeCompare(a.symbol);
        case 'price': av = a.price; bv = b.price; break;
        case 'change': av = a.changePercent; bv = b.changePercent; break;
        case 'volume': av = a.volume; bv = b.volume; break;
        case 'signal': return sortDir === 'asc' ? a.signalType.localeCompare(b.signalType) : b.signalType.localeCompare(a.signalType);
        case 'strength': av = a.strength; bv = b.strength; break;
        case 'score': av = a.score; bv = b.score; break;
        case 'time': return sortDir === 'asc' ? a.timestamp.localeCompare(b.timestamp) : b.timestamp.localeCompare(a.timestamp);
        case 'rank': default: av = a.id; bv = b.id; break;
      }
      return sortDir === 'asc' ? av! - bv! : bv! - av!;
    });

    return results;
  });

  // ---- Stats ----
  let avgStrength = $derived.by(() => {
    if (filteredResults.length === 0) return 0;
    return Math.round((filteredResults.reduce((s, r) => s + r.strength, 0) / filteredResults.length) * 10) / 10;
  });

  // ---- Helpers ----
  function toggleSort(col: string) {
    if (sortBy === col) {
      sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      sortBy = col;
      sortDir = col === 'rank' ? 'asc' : 'desc';
    }
  }

  function formatVolume(vol: number): string {
    if (vol >= 1_000_000_000) return (vol / 1_000_000_000).toFixed(1) + 'B';
    if (vol >= 1_000_000) return (vol / 1_000_000).toFixed(1) + 'M';
    if (vol >= 1_000) return (vol / 1_000).toFixed(0) + 'K';
    return vol.toString();
  }

  function toggleScanStatus() {
    scanStatus = scanStatus === 'scanning' ? 'paused' : 'scanning';
  }

  function selectRow(id: number) {
    selectedRowId = selectedRowId === id ? null : id;
  }

  // ---- Column config ----
  type ColAlign = 'left' | 'right' | 'center';
  const columns: Array<{ key: string; label: string; align: ColAlign; sortable: boolean; width: string }> = [
    { key: 'rank',     label: '#',        align: 'center', sortable: true,  width: '42px' },
    { key: 'symbol',   label: 'Symbol',   align: 'left',   sortable: true,  width: '1fr' },
    { key: 'price',    label: 'Price',    align: 'right',  sortable: true,  width: '88px' },
    { key: 'change',   label: 'Chg%',     align: 'right',  sortable: true,  width: '78px' },
    { key: 'volume',   label: 'Volume',   align: 'right',  sortable: true,  width: '88px' },
    { key: 'signal',   label: 'Signal',   align: 'center', sortable: true,  width: '78px' },
    { key: 'strength', label: 'Strength', align: 'center', sortable: true,  width: '96px' },
    { key: 'score',    label: 'Score',    align: 'right',  sortable: true,  width: '60px' },
    { key: 'time',     label: 'Time',     align: 'right',  sortable: true,  width: '72px' },
  ];
</script>

<svelte:head>
  <title>Scanner - Scanify</title>
</svelte:head>

<div class="scanner-page">
  <!-- ====== HEADER ROW ====== -->
  <header class="scanner-header">
    <div class="hdr-left">
      <h1 class="hdr-title">Scanner</h1>
      <button
        type="button"
        class="status-chip"
        onclick={toggleScanStatus}
        title={scanStatus === 'scanning' ? 'Click to pause' : 'Click to resume'}
      >
        <span
          class="status-dot"
          class:status-dot--live={scanStatus === 'scanning'}
          class:status-dot--paused={scanStatus === 'paused'}
        ></span>
        <span
          class="status-text"
          class:status-text--live={scanStatus === 'scanning'}
          class:status-text--paused={scanStatus === 'paused'}
        >
          {scanStatus === 'scanning' ? 'Scanning' : 'Paused'}
        </span>
      </button>
      <span class="scan-badge">{scanCount}</span>
    </div>
    <div class="hdr-right">
      <ExportToolbar source="scanner" />
    </div>
  </header>

  <!-- ====== FILTER BAR ====== -->
  <div class="filter-bar">
    <!-- Market Cap -->
    <div class="flt-group">
      <span class="flt-label">Market Cap</span>
      <div class="pill-row">
        {#each ['All', 'Large', 'Mid', 'Small'] as cap}
          <button
            type="button"
            class="pill"
            class:pill--on={marketCapFilter === cap}
            onclick={() => marketCapFilter = cap as typeof marketCapFilter}
          >{cap}</button>
        {/each}
      </div>
    </div>

    <span class="flt-sep"></span>

    <!-- Sector -->
    <div class="flt-group">
      <span class="flt-label">Sector</span>
      <select class="flt-select" bind:value={sectorFilter}>
        {#each sectorList as sec}
          <option value={sec}>{sec}</option>
        {/each}
      </select>
    </div>

    <span class="flt-sep"></span>

    <!-- Signal Type -->
    <div class="flt-group">
      <span class="flt-label">Signal Type</span>
      <div class="pill-row">
        {#each ['All', 'Gamma', 'Volume', 'Flow'] as sig}
          <button
            type="button"
            class="pill"
            class:pill--on={signalTypeFilter === sig}
            onclick={() => signalTypeFilter = sig as typeof signalTypeFilter}
          >{sig}</button>
        {/each}
      </div>
    </div>

    <span class="flt-sep"></span>

    <!-- Strength (star selector) -->
    <div class="flt-group">
      <span class="flt-label">Strength</span>
      <div class="star-row">
        {#each [1, 2, 3, 4, 5] as star}
          <button
            type="button"
            class="star-btn"
            class:star-btn--on={strengthFilter >= star}
            onclick={() => strengthFilter = strengthFilter === star ? 0 : star}
            title="Min strength {star}"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill={strengthFilter >= star ? 'currentColor' : 'none'} stroke="currentColor" stroke-width="1.5">
              <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
            </svg>
          </button>
        {/each}
        {#if strengthFilter > 0}
          <button type="button" class="star-clr" onclick={() => strengthFilter = 0}>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        {/if}
      </div>
    </div>
  </div>

  <!-- ====== DATA TABLE (glass panel) ====== -->
  <div class="table-panel">
    <div class="table-scroll">
      <table class="scan-table">
        <thead>
          <tr>
            {#each columns as col (col.key)}
              <th
                class="col-th col-th--{col.align}"
                class:col-th--sortable={col.sortable}
                class:col-th--active={sortBy === col.key}
                onclick={() => col.sortable && toggleSort(col.key)}
              >
                <span class="col-th-inner">
                  {col.label}
                  {#if sortBy === col.key}
                    <span class="sort-arrow">{sortDir === 'asc' ? '▲' : '▼'}</span>
                  {:else if col.sortable}
                    <span class="sort-arrow sort-arrow--ghost">▼</span>
                  {/if}
                </span>
              </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#if loading}
            <tr>
              <td colspan={columns.length} class="td-empty">
                <div class="state-loading">
                  <div class="spinner"></div>
                  <span>Initializing scanner...</span>
                </div>
              </td>
            </tr>
          {:else if filteredResults.length === 0}
            <tr>
              <td colspan={columns.length} class="td-empty">
                {#if scanResults.length === 0}
                  No scan results available
                {:else}
                  No results match current filters
                {/if}
              </td>
            </tr>
          {:else}
            {#each filteredResults as row, idx (row.id)}
              {@const rank = idx + 1}
              <tr
                class="tbl-row"
                class:tbl-row--alt={idx % 2 === 1}
                class:tbl-row--sel={selectedRowId === row.id}
                onclick={() => selectRow(row.id)}
              >
                <!-- # -->
                <td class="td td--center td--mono td--rank">{rank}</td>
                <!-- Symbol -->
                <td class="td td--left">
                  <div class="sym-cell">
                    <span class="sym-ticker">{row.symbol}</span>
                    <span class="sym-name">{row.name}</span>
                  </div>
                </td>
                <!-- Price -->
                <td class="td td--right td--mono">${row.price.toFixed(2)}</td>
                <!-- Chg% -->
                <td
                  class="td td--right td--mono td--bold"
                  class:td--green={row.changePercent > 0}
                  class:td--red={row.changePercent < 0}
                >
                  {row.changePercent > 0 ? '+' : ''}{row.changePercent.toFixed(2)}%
                </td>
                <!-- Volume -->
                <td class="td td--right td--mono">{formatVolume(row.volume)}</td>
                <!-- Signal -->
                <td class="td td--center">
                  <span class="sig-badge sig-badge--{row.signalType.toLowerCase()}">{row.signalType}</span>
                </td>
                <!-- Strength pips -->
                <td class="td td--center">
                  <div class="str-pips">
                    {#each [1, 2, 3, 4, 5] as p}
                      <span
                        class="pip"
                        class:pip--lit={p <= row.strength}
                        style={p <= row.strength ? `background: var(--strength-${row.strength})` : ''}
                      ></span>
                    {/each}
                  </div>
                </td>
                <!-- Score -->
                <td class="td td--right td--mono">
                  <span
                    class="score-val"
                    class:score-val--hi={row.score >= 80}
                    class:score-val--mid={row.score >= 50 && row.score < 80}
                  >{row.score}</span>
                </td>
                <!-- Timestamp -->
                <td class="td td--right td--mono td--dim">{row.timestamp}</td>
              </tr>
            {/each}
          {/if}
        </tbody>
      </table>
    </div>
  </div>

  <!-- ====== STATS BAR ====== -->
  <footer class="stats-bar">
    <div class="sbar-item">
      <span class="sbar-label">Total</span>
      <span class="sbar-value">{scanResults.length}</span>
    </div>
    <span class="sbar-sep"></span>
    <div class="sbar-item">
      <span class="sbar-label">Filtered</span>
      <span class="sbar-value">{filteredResults.length}</span>
    </div>
    <span class="sbar-sep"></span>
    <div class="sbar-item">
      <span class="sbar-label">Last Scan</span>
      <span class="sbar-value sbar-value--mono">{lastScanTime || '--:--:--'}</span>
    </div>
    <span class="sbar-sep"></span>
    <div class="sbar-item">
      <span class="sbar-label">Avg Strength</span>
      <span class="sbar-value">{avgStrength.toFixed(1)}</span>
    </div>
    <span class="sbar-sep"></span>
    <div class="sbar-item">
      <span class="sbar-label">Feed</span>
      <span class="sbar-value" class:sbar-value--live={connected} class:sbar-value--sim={!connected && !loading}>
        {loading ? 'Connecting...' : connected ? 'Live' : 'Simulated'}
      </span>
    </div>
  </footer>
</div>

<style>
  /* ================================================================
     SCANNER PAGE
     Enterprise stock scanner -- OKLCH, scoped CSS, glass-morphism
     ================================================================ */

  .scanner-page {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }

  /* ----------------------------------------------------------------
     HEADER ROW
     ---------------------------------------------------------------- */
  .scanner-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 20px;
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
  }

  .hdr-left {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .hdr-right {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .hdr-title {
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.01em;
  }

  /* Status chip (scanning / paused) */
  .status-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px 3px 8px;
    border-radius: var(--radius-full);
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    cursor: pointer;
    transition: background var(--duration-fast, 100ms);
  }

  .status-chip:hover {
    background: var(--bg-elevated);
  }

  .status-dot {
    width: 7px;
    height: 7px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
  }

  .status-dot--live {
    background: var(--bullish);
    box-shadow: 0 0 6px var(--bullish-dim);
    animation: signal-ping 2s ease-in-out infinite;
  }

  .status-dot--paused {
    background: var(--warning);
    box-shadow: 0 0 6px var(--warning-dim);
  }

  .status-text {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.02em;
  }

  .status-text--live  { color: var(--bullish); }
  .status-text--paused { color: var(--warning); }

  /* Scan count badge */
  .scan-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 22px;
    height: 20px;
    padding: 0 6px;
    border-radius: var(--radius-full);
    background: var(--accent-bg);
    color: var(--accent-bright);
    font-size: 10px;
    font-weight: 700;
    font-family: var(--font-mono);
    border: 1px solid var(--accent-dim);
  }

  /* ----------------------------------------------------------------
     FILTER BAR
     ---------------------------------------------------------------- */
  .filter-bar {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 8px 20px;
    border-bottom: 1px solid var(--border-subtle);
    background: oklch(0.13 0.015 260 / 0.6);
    flex-shrink: 0;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .filter-bar::-webkit-scrollbar { display: none; }

  .flt-group {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }

  .flt-label {
    font-size: 10px;
    font-weight: 600;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    white-space: nowrap;
  }

  .flt-sep {
    display: block;
    width: 1px;
    height: 20px;
    background: var(--border-subtle);
    flex-shrink: 0;
  }

  /* Pill row (segmented control) */
  .pill-row {
    display: flex;
    gap: 2px;
    background: var(--bg-surface);
    border-radius: var(--radius-md);
    padding: 2px;
    border: 1px solid var(--border-subtle);
  }

  .pill {
    padding: 3px 10px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
    color: var(--text-tertiary);
    background: transparent;
    border: none;
    cursor: pointer;
    transition: all 120ms;
    white-space: nowrap;
  }

  .pill:hover {
    color: var(--text-secondary);
    background: var(--hover-overlay);
  }

  .pill--on {
    color: var(--accent-bright);
    background: var(--accent-bg);
  }

  /* Sector dropdown */
  .flt-select {
    padding: 3px 24px 3px 8px;
    border-radius: var(--radius-md);
    font-size: 11px;
    font-weight: 500;
    color: var(--text-secondary);
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    cursor: pointer;
    outline: none;
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' fill='none'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%23888' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 8px center;
  }

  .flt-select:focus {
    border-color: var(--accent-dim);
  }

  /* Star selector */
  .star-row {
    display: flex;
    align-items: center;
    gap: 2px;
  }

  .star-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border-radius: 4px;
    background: transparent;
    color: var(--text-disabled);
    border: none;
    cursor: pointer;
    transition: color 120ms;
    padding: 0;
  }

  .star-btn:hover {
    color: var(--warning);
  }

  .star-btn--on {
    color: var(--warning);
  }

  .star-clr {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    margin-left: 4px;
    border-radius: var(--radius-full);
    background: var(--bg-overlay);
    color: var(--text-tertiary);
    border: none;
    cursor: pointer;
    transition: all 120ms;
    padding: 0;
  }

  .star-clr:hover {
    background: var(--bg-elevated);
    color: var(--text-secondary);
  }

  /* ----------------------------------------------------------------
     TABLE PANEL (glass-morphism)
     ---------------------------------------------------------------- */
  .table-panel {
    flex: 1;
    min-height: 0;
    margin: 8px 12px;
    background: oklch(0.14 0.02 260 / 0.7);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .table-scroll {
    flex: 1;
    overflow: auto;
    min-height: 0;
  }

  .table-scroll::-webkit-scrollbar {
    width: 6px;
    height: 6px;
  }

  .table-scroll::-webkit-scrollbar-track {
    background: transparent;
  }

  .table-scroll::-webkit-scrollbar-thumb {
    background: var(--scrollbar-thumb);
    border-radius: var(--radius-full);
  }

  .table-scroll::-webkit-scrollbar-thumb:hover {
    background: var(--scrollbar-thumb-hover);
  }

  .scan-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: var(--text-xs);
  }

  /* ---- Column headers ---- */
  .col-th {
    position: sticky;
    top: 0;
    z-index: 10;
    padding: 8px 10px;
    font-size: 10px;
    font-weight: 600;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    white-space: nowrap;
    background: oklch(0.12 0.02 260 / 0.95);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--border-subtle);
    user-select: none;
  }

  .col-th--left   { text-align: left; }
  .col-th--right  { text-align: right; }
  .col-th--center { text-align: center; }

  .col-th--sortable {
    cursor: pointer;
  }

  .col-th--sortable:hover {
    color: var(--text-secondary);
    background: oklch(0.15 0.02 260 / 0.95);
  }

  .col-th--active {
    color: var(--accent-bright);
  }

  .col-th-inner {
    display: inline-flex;
    align-items: center;
    gap: 3px;
  }

  .sort-arrow {
    font-size: 8px;
    line-height: 1;
  }

  .sort-arrow--ghost {
    opacity: 0;
    transition: opacity 120ms;
  }

  .col-th--sortable:hover .sort-arrow--ghost {
    opacity: 0.3;
  }

  /* ---- Table rows ---- */
  .tbl-row {
    cursor: pointer;
    transition: background 100ms;
    border-left: 3px solid transparent;
  }

  .tbl-row--alt {
    background: oklch(0.15 0.01 260 / 0.3);
  }

  .tbl-row:hover {
    background: oklch(0.20 0.02 260 / 0.5);
  }

  .tbl-row--sel {
    background: oklch(0.18 0.03 290 / 0.3);
    border-left-color: var(--accent-bright);
  }

  .tbl-row--sel:hover {
    background: oklch(0.20 0.03 290 / 0.35);
  }

  /* ---- Table cells ---- */
  .td {
    padding: 7px 10px;
    border-bottom: 1px solid oklch(0.20 0.01 260 / 0.4);
    color: var(--text-secondary);
    vertical-align: middle;
    white-space: nowrap;
  }

  .td--left   { text-align: left; }
  .td--right  { text-align: right; }
  .td--center { text-align: center; }
  .td--mono   { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
  .td--bold   { font-weight: 600; }
  .td--dim    { color: var(--text-tertiary); font-size: 10px; }
  .td--rank   { color: var(--text-tertiary); font-size: 10px; }

  .td--green { color: var(--bullish); }
  .td--red   { color: var(--bearish); }

  /* Symbol cell */
  .sym-cell {
    display: flex;
    flex-direction: column;
    gap: 1px;
  }

  .sym-ticker {
    font-weight: 700;
    font-family: var(--font-mono);
    color: var(--text-primary);
    font-size: 12px;
    letter-spacing: 0.01em;
  }

  .sym-name {
    font-size: 10px;
    color: var(--text-disabled);
    max-width: 150px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    line-height: 1.2;
  }

  /* Signal badge */
  .sig-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 2px 8px;
    border-radius: var(--radius-full);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.03em;
    text-transform: uppercase;
  }

  .sig-badge--gamma {
    background: oklch(0.35 0.12 290 / 0.3);
    color: oklch(0.78 0.15 290);
    border: 1px solid oklch(0.45 0.12 290 / 0.3);
  }

  .sig-badge--volume {
    background: oklch(0.30 0.10 200 / 0.3);
    color: oklch(0.75 0.12 200);
    border: 1px solid oklch(0.45 0.10 200 / 0.3);
  }

  .sig-badge--flow {
    background: oklch(0.30 0.10 85 / 0.3);
    color: oklch(0.78 0.12 85);
    border: 1px solid oklch(0.45 0.10 85 / 0.3);
  }

  /* Strength pips */
  .str-pips {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 3px;
  }

  .pip {
    width: 12px;
    height: 5px;
    border-radius: var(--radius-full);
    background: var(--bg-overlay);
    transition: background 120ms;
  }

  .pip--lit {
    box-shadow: 0 0 4px oklch(0.5 0.1 155 / 0.2);
  }

  /* Score */
  .score-val {
    color: var(--text-secondary);
  }

  .score-val--hi {
    color: var(--bullish);
    font-weight: 700;
  }

  .score-val--mid {
    color: var(--warning);
    font-weight: 600;
  }

  /* Empty / loading states */
  .td-empty {
    text-align: center;
    padding: 48px 20px;
    color: var(--text-tertiary);
    font-size: var(--text-sm);
  }

  .state-loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    padding: 24px 0;
  }

  .spinner {
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

  /* ----------------------------------------------------------------
     STATS BAR
     ---------------------------------------------------------------- */
  .stats-bar {
    display: flex;
    align-items: center;
    padding: 6px 20px;
    border-top: 1px solid var(--border-subtle);
    background: oklch(0.12 0.01 260 / 0.8);
    flex-shrink: 0;
  }

  .sbar-item {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 0 12px;
  }

  .sbar-label {
    font-size: 10px;
    font-weight: 500;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .sbar-value {
    font-size: 11px;
    font-weight: 700;
    color: var(--text-primary);
  }

  .sbar-value--mono {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
  }

  .sbar-value--live {
    color: var(--bullish);
  }

  .sbar-value--sim {
    color: var(--text-tertiary);
  }

  .sbar-sep {
    display: block;
    width: 1px;
    height: 14px;
    background: var(--border-subtle);
    flex-shrink: 0;
  }
</style>
