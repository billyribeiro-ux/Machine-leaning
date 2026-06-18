<script lang="ts">
  import { onMount } from 'svelte';
  import ExportToolbar from '$lib/components/ui/ExportToolbar.svelte';
  import {
    ChartLineUp,
    TrendUp,
    TrendDown,
    ArrowUp,
    ArrowDown,
    Pulse,
    Timer,
    ArrowsClockwise,
    WarningCircle,
    GearSix,
    Gauge,
    ChartBar,
    Heartbeat,
  } from 'phosphor-svelte';

  const API_BASE = 'http://localhost:8000';

  // --- Reactive state ---
  let loading = $state(false);
  let connected = $state(false);
  let needsApiKey = $state(false);
  let currentTime = $state(new Date());

  // Update clock every second
  $effect(() => {
    const interval = setInterval(() => {
      currentTime = new Date();
    }, 1000);
    return () => clearInterval(interval);
  });

  // ========== SAMPLE DATA ==========

  // Index Tickers
  const indexTickers = $state([
    { symbol: 'SPX', name: 'S&P 500', value: 5842.31, change: 38.72, changePct: 0.67 },
    { symbol: 'NDX', name: 'NASDAQ 100', value: 20917.84, change: 187.43, changePct: 0.90 },
    { symbol: 'DJI', name: 'Dow Jones', value: 43127.56, change: -42.18, changePct: -0.10 },
    { symbol: 'RUT', name: 'Russell 2000', value: 2087.43, change: 21.35, changePct: 1.03 },
    { symbol: 'VIX', name: 'Volatility', value: 14.28, change: -1.42, changePct: -9.05 },
  ]);

  // Market Breadth
  let breadthData = $state({
    advancing: 2847,
    declining: 1653,
    unchanged: 312,
    newHighs: 187,
    newLows: 34,
    upVolume: 7.82,
    downVolume: 4.31,
    advDecRatio: 1.72,
  });

  const totalIssues = $derived(breadthData.advancing + breadthData.declining + breadthData.unchanged);
  const advPct = $derived(totalIssues > 0 ? (breadthData.advancing / totalIssues) * 100 : 50);
  const decPct = $derived(totalIssues > 0 ? (breadthData.declining / totalIssues) * 100 : 50);
  const totalVolume = $derived(breadthData.upVolume + breadthData.downVolume);
  const upVolPct = $derived(totalVolume > 0 ? (breadthData.upVolume / totalVolume) * 100 : 50);
  const hiLoTotal = $derived(breadthData.newHighs + breadthData.newLows);
  const hiPct = $derived(hiLoTotal > 0 ? (breadthData.newHighs / hiLoTotal) * 100 : 50);

  // Sector Performance (11 GICS Sectors)
  const sectorData = $state([
    { name: 'Technology', symbol: 'XLK', change: 1.42 },
    { name: 'Healthcare', symbol: 'XLV', change: 0.38 },
    { name: 'Financials', symbol: 'XLF', change: 0.85 },
    { name: 'Consumer Disc.', symbol: 'XLY', change: -0.27 },
    { name: 'Communication', symbol: 'XLC', change: 1.12 },
    { name: 'Industrials', symbol: 'XLI', change: 0.63 },
    { name: 'Consumer Staples', symbol: 'XLP', change: -0.51 },
    { name: 'Energy', symbol: 'XLE', change: -1.18 },
    { name: 'Utilities', symbol: 'XLU', change: 0.22 },
    { name: 'Real Estate', symbol: 'XLRE', change: -0.34 },
    { name: 'Materials', symbol: 'XLB', change: 0.47 },
  ]);

  const maxSectorAbsChange = $derived.by(() => {
    return Math.max(...sectorData.map(s => Math.abs(s.change)), 0.01);
  });

  // Market Movers
  const topGainers = $state([
    { symbol: 'NVDA', name: 'NVIDIA Corp', price: 892.47, changePct: 5.82 },
    { symbol: 'SMCI', name: 'Super Micro', price: 743.21, changePct: 4.67 },
    { symbol: 'ANET', name: 'Arista Networks', price: 312.84, changePct: 3.91 },
    { symbol: 'CRWD', name: 'CrowdStrike', price: 348.92, changePct: 3.44 },
    { symbol: 'META', name: 'Meta Platforms', price: 512.38, changePct: 2.87 },
  ]);

  const topLosers = $state([
    { symbol: 'PFE', name: 'Pfizer Inc', price: 26.43, changePct: -4.21 },
    { symbol: 'BA', name: 'Boeing Co', price: 187.62, changePct: -3.58 },
    { symbol: 'INTC', name: 'Intel Corp', price: 31.24, changePct: -2.93 },
    { symbol: 'DIS', name: 'Walt Disney', price: 98.71, changePct: -2.41 },
    { symbol: 'NKE', name: 'Nike Inc', price: 94.38, changePct: -1.87 },
  ]);

  // Sentiment / Fear & Greed (0-100 scale)
  let sentimentValue = $state(62);
  const sentimentLabel = $derived.by(() => {
    if (sentimentValue <= 20) return 'Extreme Fear';
    if (sentimentValue <= 40) return 'Fear';
    if (sentimentValue <= 60) return 'Neutral';
    if (sentimentValue <= 80) return 'Greed';
    return 'Extreme Greed';
  });
  const sentimentColor = $derived.by(() => {
    if (sentimentValue <= 20) return 'oklch(0.58 0.18 25)';
    if (sentimentValue <= 40) return 'oklch(0.72 0.16 50)';
    if (sentimentValue <= 60) return 'oklch(0.78 0.14 85)';
    if (sentimentValue <= 80) return 'oklch(0.70 0.16 155)';
    return 'oklch(0.64 0.16 155)';
  });

  // Gauge needle angle: -90deg (0) to +90deg (100)
  const needleAngle = $derived((sentimentValue / 100) * 180 - 90);
  const needleRad = $derived(((needleAngle - 90) * Math.PI) / 180);

  // Market internals
  let tick = $state(342);
  let trin = $state(0.87);
  let vix = $state(14.28);
  let advDecRatio = $state(1.72);

  // --- Data fetching ---
  async function fetchMarketData() {
    // Health check first
    try {
      const health = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(1500) });
      connected = health.ok;
    } catch {
      connected = false;
      return;
    }

    let anyProviderError = false;

    // Breadth
    try {
      const breadthRes = await fetch(`${API_BASE}/api/equity/internals/breadth`, { signal: AbortSignal.timeout(3000) });
      if (breadthRes.ok) {
        const raw = await breadthRes.json();
        const d = raw.data ?? raw;
        breadthData = {
          advancing: d.advancers ?? d.advancing ?? breadthData.advancing,
          declining: d.decliners ?? d.declining ?? breadthData.declining,
          unchanged: d.unchanged ?? breadthData.unchanged,
          newHighs: d.newHighs ?? d.new_highs ?? breadthData.newHighs,
          newLows: d.newLows ?? d.new_lows ?? breadthData.newLows,
          upVolume: d.upVolume ?? d.up_volume ?? breadthData.upVolume,
          downVolume: d.downVolume ?? d.down_volume ?? breadthData.downVolume,
          advDecRatio: d.advDecRatio ?? d.ad_ratio ?? breadthData.advDecRatio,
        };
      }
    } catch { /* non-critical */ }

    // Direction / sentiment
    try {
      const directionRes = await fetch(`${API_BASE}/api/equity/internals/direction`, { signal: AbortSignal.timeout(3000) });
      if (directionRes.ok) {
        const raw = await directionRes.json();
        const d = raw.data ?? raw;
        sentimentValue = d.sentiment ?? d.value ?? d.score ?? sentimentValue;
        tick = d.tick ?? d.TICK ?? tick;
        trin = d.trin ?? d.TRIN ?? trin;
        advDecRatio = d.advDecRatio ?? d.advance_decline ?? d.ad_ratio ?? advDecRatio;
      }
    } catch { /* non-critical */ }

    // Macro snapshot -> VIX
    try {
      const macroRes = await fetch(`${API_BASE}/api/equity/macro/snapshot`, { signal: AbortSignal.timeout(3000) });
      if (macroRes.ok) {
        const raw = await macroRes.json();
        const d = raw.data ?? raw;
        vix = d.vix ?? d.VIX ?? vix;
        if (tick === 342) tick = d.tick ?? d.TICK ?? tick;
        if (trin === 0.87) trin = d.trin ?? d.TRIN ?? trin;
      } else {
        anyProviderError = true;
      }
    } catch { anyProviderError = true; }

    // Sectors
    try {
      const sectorRes = await fetch(`${API_BASE}/api/equity/market/sectors`, { signal: AbortSignal.timeout(3000) });
      if (sectorRes.ok) {
        const raw = await sectorRes.json();
        const rawSectors = Array.isArray(raw) ? raw : raw.data ?? raw.sectors ?? [];
        if (rawSectors.length > 0) {
          sectorData.length = 0;
          rawSectors.forEach((s: any) => {
            sectorData.push({
              name: s.name ?? s.sector ?? '',
              symbol: s.symbol ?? s.ticker ?? '',
              change: s.change ?? s.changePercent ?? s.change_percent ?? 0,
            });
          });
        }
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

  // Helper: format number with sign
  function formatChange(val: number, decimals = 2): string {
    const sign = val >= 0 ? '+' : '';
    return `${sign}${val.toFixed(decimals)}`;
  }
</script>

<svelte:head>
  <title>Market Overview - Scanify</title>
</svelte:head>

<div class="page-root">
  <!-- Connection / API key banners -->
  {#if !loading && !connected}
    <div class="connection-banner">
      <div class="banner-left">
        <WarningCircle size={16} weight="fill" />
        <span class="banner-text">Backend server is not running -- start the API server to see live data</span>
      </div>
      <button class="retry-btn" onclick={() => fetchMarketData()}>
        <ArrowsClockwise size={12} weight="bold" />
        Retry
      </button>
    </div>
  {:else if !loading && needsApiKey}
    <div class="connection-banner api-key-banner">
      <div class="banner-left">
        <WarningCircle size={16} weight="fill" />
        <span class="banner-text">Some data providers need API keys -- configure in Settings for full data</span>
      </div>
      <a href="/settings" class="retry-btn">
        <GearSix size={12} weight="bold" />
        Configure
      </a>
    </div>
  {/if}

  <!-- ========== INDEX TICKER BAR ========== -->
  <div class="ticker-bar">
    {#each indexTickers as idx (idx.symbol)}
      <div class="ticker-item" class:ticker-up={idx.change >= 0} class:ticker-down={idx.change < 0}>
        <div class="ticker-header">
          <span class="ticker-symbol">{idx.symbol}</span>
          <span class="ticker-name">{idx.name}</span>
        </div>
        <div class="ticker-values">
          <span class="ticker-price mono-nums">{idx.value.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
          <span class="ticker-change mono-nums">
            {#if idx.change >= 0}<ArrowUp size={10} weight="bold" />{:else}<ArrowDown size={10} weight="bold" />{/if}
            {formatChange(idx.change)}
          </span>
          <span class="ticker-pct mono-nums">({formatChange(idx.changePct)}%)</span>
        </div>
      </div>
    {/each}
  </div>

  <!-- Header -->
  <div class="page-header">
    <div class="header-left">
      <ChartLineUp size={20} weight="duotone" />
      <h1 class="page-title">Market Overview</h1>
      <span class="header-badge">LIVE</span>
    </div>
    <div class="header-actions">
      <ExportToolbar source="market" />
      <div class="header-divider"></div>
      <span class="header-timestamp">
        <Timer size={12} />
        {currentTime.toLocaleTimeString('en-US', { hour12: false })}
      </span>
      <button class="refresh-btn" onclick={() => fetchMarketData()} title="Refresh data">
        <ArrowsClockwise size={14} weight="bold" />
      </button>
    </div>
  </div>

  {#if loading}
    <div class="loading-state">
      <Pulse size={24} />
      <span class="loading-text">Loading market data...</span>
    </div>
  {:else}
    <div class="page-content">
      <!-- ROW 1: Market Breadth + Sentiment -->
      <div class="content-row content-row--top">
        <!-- Market Breadth Panel -->
        <div class="glass-panel breadth-panel">
          <div class="panel-header">
            <Heartbeat size={16} weight="duotone" />
            <h2 class="panel-title">Market Breadth</h2>
          </div>
          <div class="breadth-content">
            <!-- Advancing / Declining -->
            <div class="breadth-row">
              <div class="breadth-label-row">
                <span class="breadth-label breadth-label--bull">Advancing</span>
                <span class="breadth-vs">vs</span>
                <span class="breadth-label breadth-label--bear">Declining</span>
              </div>
              <div class="breadth-bar-container">
                <div class="breadth-bar breadth-bar--adv" style="width: {advPct}%">
                  <span class="breadth-bar-value">{breadthData.advancing.toLocaleString()}</span>
                </div>
                <div class="breadth-bar breadth-bar--dec" style="width: {decPct}%">
                  <span class="breadth-bar-value">{breadthData.declining.toLocaleString()}</span>
                </div>
              </div>
              <div class="breadth-ratio mono-nums">
                A/D Ratio: <strong>{breadthData.advDecRatio.toFixed(2)}</strong>
              </div>
            </div>

            <!-- New Highs / New Lows -->
            <div class="breadth-row">
              <div class="breadth-label-row">
                <span class="breadth-label breadth-label--bull">New Highs</span>
                <span class="breadth-vs">vs</span>
                <span class="breadth-label breadth-label--bear">New Lows</span>
              </div>
              <div class="breadth-bar-container">
                <div class="breadth-bar breadth-bar--adv" style="width: {hiPct}%">
                  <span class="breadth-bar-value">{breadthData.newHighs}</span>
                </div>
                <div class="breadth-bar breadth-bar--dec" style="width: {100 - hiPct}%">
                  <span class="breadth-bar-value">{breadthData.newLows}</span>
                </div>
              </div>
            </div>

            <!-- Up Volume / Down Volume -->
            <div class="breadth-row">
              <div class="breadth-label-row">
                <span class="breadth-label breadth-label--bull">Up Volume</span>
                <span class="breadth-vs">vs</span>
                <span class="breadth-label breadth-label--bear">Down Volume</span>
              </div>
              <div class="breadth-bar-container">
                <div class="breadth-bar breadth-bar--adv" style="width: {upVolPct}%">
                  <span class="breadth-bar-value">{breadthData.upVolume.toFixed(2)}B</span>
                </div>
                <div class="breadth-bar breadth-bar--dec" style="width: {100 - upVolPct}%">
                  <span class="breadth-bar-value">{breadthData.downVolume.toFixed(2)}B</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Internals strip -->
          <div class="internals-strip">
            <div class="internal-item">
              <span class="internal-label">TICK</span>
              <span class="internal-value mono-nums" class:val-bull={tick > 0} class:val-bear={tick < 0}>{formatChange(tick, 0)}</span>
            </div>
            <div class="internal-divider"></div>
            <div class="internal-item">
              <span class="internal-label">TRIN</span>
              <span class="internal-value mono-nums" class:val-bull={trin < 1} class:val-bear={trin > 1}>{trin.toFixed(2)}</span>
            </div>
            <div class="internal-divider"></div>
            <div class="internal-item">
              <span class="internal-label">VIX</span>
              <span class="internal-value mono-nums" class:val-bull={vix < 20} class:val-bear={vix >= 20} class:val-extreme={vix >= 30}>{vix.toFixed(2)}</span>
            </div>
            <div class="internal-divider"></div>
            <div class="internal-item">
              <span class="internal-label">A/D</span>
              <span class="internal-value mono-nums" class:val-bull={advDecRatio > 1} class:val-bear={advDecRatio < 1}>{advDecRatio.toFixed(2)}</span>
            </div>
          </div>
        </div>

        <!-- Sentiment Gauge Panel -->
        <div class="glass-panel sentiment-panel">
          <div class="panel-header">
            <Gauge size={16} weight="duotone" />
            <h2 class="panel-title">Fear & Greed Index</h2>
          </div>
          <div class="gauge-container">
            <!-- SVG Semicircle Gauge -->
            <svg viewBox="0 0 200 120" class="gauge-svg">
              <defs>
                <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stop-color="oklch(0.58 0.18 25)" />
                  <stop offset="25%" stop-color="oklch(0.72 0.16 50)" />
                  <stop offset="50%" stop-color="oklch(0.78 0.14 85)" />
                  <stop offset="75%" stop-color="oklch(0.70 0.16 155)" />
                  <stop offset="100%" stop-color="oklch(0.64 0.16 155)" />
                </linearGradient>
              </defs>
              <!-- Background arc -->
              <path
                d="M 20 105 A 80 80 0 0 1 180 105"
                fill="none"
                stroke="oklch(0.20 0.01 260)"
                stroke-width="12"
                stroke-linecap="round"
              />
              <!-- Colored arc -->
              <path
                d="M 20 105 A 80 80 0 0 1 180 105"
                fill="none"
                stroke="url(#gaugeGrad)"
                stroke-width="12"
                stroke-linecap="round"
              />
              <!-- Tick marks -->
              {#each [0, 25, 50, 75, 100] as mark}
                {@const angle = (mark / 100) * 180 - 180}
                {@const rad = (angle * Math.PI) / 180}
                {@const x1 = 100 + 72 * Math.cos(rad)}
                {@const y1 = 105 + 72 * Math.sin(rad)}
                {@const x2 = 100 + 64 * Math.cos(rad)}
                {@const y2 = 105 + 64 * Math.sin(rad)}
                <line {x1} {y1} {x2} {y2} stroke="oklch(0.52 0.01 260)" stroke-width="1.5" />
                <text
                  x={100 + 58 * Math.cos(rad)}
                  y={105 + 58 * Math.sin(rad)}
                  text-anchor="middle"
                  dominant-baseline="middle"
                  fill="oklch(0.52 0.01 260)"
                  font-size="7"
                  font-family="var(--font-mono)"
                >{mark}</text>
              {/each}
              <!-- Needle -->
              <line
                x1="100"
                y1="105"
                x2={100 + 62 * Math.cos(needleRad)}
                y2={105 + 62 * Math.sin(needleRad)}
                stroke={sentimentColor}
                stroke-width="2.5"
                stroke-linecap="round"
              />
              <!-- Center dot -->
              <circle cx="100" cy="105" r="5" fill={sentimentColor} />
              <circle cx="100" cy="105" r="2.5" fill="oklch(0.14 0.02 260)" />
            </svg>
            <div class="gauge-readout">
              <span class="gauge-value mono-nums" style="color: {sentimentColor}">{sentimentValue}</span>
              <span class="gauge-label" style="color: {sentimentColor}">{sentimentLabel}</span>
            </div>
          </div>

          <!-- Sentiment sub-metrics -->
          <div class="sentiment-metrics">
            <div class="sentiment-metric">
              <span class="sm-label">Put/Call</span>
              <span class="sm-value mono-nums">0.82</span>
            </div>
            <div class="sentiment-metric">
              <span class="sm-label">VIX Term</span>
              <span class="sm-value mono-nums val-bull">Contango</span>
            </div>
            <div class="sentiment-metric">
              <span class="sm-label">Junk Bond</span>
              <span class="sm-value mono-nums val-bull">+0.12%</span>
            </div>
            <div class="sentiment-metric">
              <span class="sm-label">Safe Haven</span>
              <span class="sm-value mono-nums">Low</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ROW 2: Sector Performance -->
      <div class="glass-panel sector-panel">
        <div class="panel-header">
          <ChartBar size={16} weight="duotone" />
          <h2 class="panel-title">Sector Performance</h2>
          <span class="panel-subtitle">GICS Sectors -- Intraday Change</span>
        </div>
        <div class="sector-grid">
          {#each sectorData as sector (sector.symbol)}
            <div class="sector-card" class:sector-up={sector.change >= 0} class:sector-down={sector.change < 0}>
              <div class="sector-info">
                <span class="sector-name">{sector.name}</span>
                <span class="sector-symbol">{sector.symbol}</span>
              </div>
              <div class="sector-perf">
                <span class="sector-change mono-nums">
                  {formatChange(sector.change)}%
                </span>
                <div class="sector-bar-track">
                  {#if sector.change >= 0}
                    <div class="sector-bar sector-bar--pos" style="width: {(sector.change / maxSectorAbsChange) * 100}%"></div>
                  {:else}
                    <div class="sector-bar sector-bar--neg" style="width: {(Math.abs(sector.change) / maxSectorAbsChange) * 100}%"></div>
                  {/if}
                </div>
              </div>
            </div>
          {/each}
        </div>
      </div>

      <!-- ROW 3: Market Movers -->
      <div class="content-row content-row--movers">
        <!-- Top Gainers -->
        <div class="glass-panel movers-panel">
          <div class="panel-header">
            <TrendUp size={16} weight="duotone" />
            <h2 class="panel-title">Top Gainers</h2>
          </div>
          <div class="movers-table">
            <div class="movers-header-row">
              <span class="mh-symbol">Symbol</span>
              <span class="mh-price">Price</span>
              <span class="mh-change">Change %</span>
            </div>
            {#each topGainers as stock, i (stock.symbol)}
              <div class="mover-row">
                <div class="mover-symbol-col">
                  <span class="mover-rank">{i + 1}</span>
                  <div class="mover-id">
                    <span class="mover-symbol">{stock.symbol}</span>
                    <span class="mover-name">{stock.name}</span>
                  </div>
                </div>
                <span class="mover-price mono-nums">${stock.price.toFixed(2)}</span>
                <span class="mover-change mover-change--gain mono-nums">
                  <ArrowUp size={10} weight="bold" />
                  +{stock.changePct.toFixed(2)}%
                </span>
              </div>
            {/each}
          </div>
        </div>

        <!-- Top Losers -->
        <div class="glass-panel movers-panel">
          <div class="panel-header">
            <TrendDown size={16} weight="duotone" />
            <h2 class="panel-title">Top Losers</h2>
          </div>
          <div class="movers-table">
            <div class="movers-header-row">
              <span class="mh-symbol">Symbol</span>
              <span class="mh-price">Price</span>
              <span class="mh-change">Change %</span>
            </div>
            {#each topLosers as stock, i (stock.symbol)}
              <div class="mover-row">
                <div class="mover-symbol-col">
                  <span class="mover-rank">{i + 1}</span>
                  <div class="mover-id">
                    <span class="mover-symbol">{stock.symbol}</span>
                    <span class="mover-name">{stock.name}</span>
                  </div>
                </div>
                <span class="mover-price mono-nums">${stock.price.toFixed(2)}</span>
                <span class="mover-change mover-change--loss mono-nums">
                  <ArrowDown size={10} weight="bold" />
                  {stock.changePct.toFixed(2)}%
                </span>
              </div>
            {/each}
          </div>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  /* ===== Page Root ===== */
  .page-root {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: auto;
    background: var(--bg-void);
  }

  /* ===== Connection Banner ===== */
  .connection-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 16px;
    margin: 8px 16px 0;
    border-radius: var(--radius-md);
    background: oklch(0.14 0.02 260 / 0.8);
    backdrop-filter: blur(8px);
    border: 1px solid var(--border-subtle);
  }

  .api-key-banner {
    border-color: var(--warning-dim);
    background: oklch(0.24 0.05 85 / 0.15);
  }

  .banner-left {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--warning);
  }

  .banner-text {
    font-size: var(--text-xs);
    color: var(--text-secondary);
    font-weight: 500;
  }

  .retry-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--accent);
    background: none;
    border: 1px solid var(--accent-dim);
    border-radius: var(--radius-md);
    padding: 4px 12px;
    cursor: pointer;
    text-decoration: none;
    transition: all 150ms;
  }

  .retry-btn:hover {
    background: var(--accent-bg);
    border-color: var(--accent);
  }

  /* ===== Index Ticker Bar ===== */
  .ticker-bar {
    display: flex;
    gap: 1px;
    background: var(--border-subtle);
    border-bottom: 1px solid var(--border-subtle);
    overflow-x: auto;
    flex-shrink: 0;
  }

  .ticker-item {
    flex: 1;
    min-width: 160px;
    padding: 10px 16px;
    background: var(--bg-base);
    display: flex;
    flex-direction: column;
    gap: 4px;
    transition: background 150ms;
  }

  .ticker-item:hover {
    background: var(--bg-surface);
  }

  .ticker-header {
    display: flex;
    align-items: baseline;
    gap: 6px;
  }

  .ticker-symbol {
    font-size: var(--text-xs);
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: 0.03em;
  }

  .ticker-name {
    font-size: 10px;
    color: var(--text-tertiary);
    white-space: nowrap;
  }

  .ticker-values {
    display: flex;
    align-items: baseline;
    gap: 8px;
    flex-wrap: wrap;
  }

  .ticker-price {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .ticker-change,
  .ticker-pct {
    font-size: var(--text-xs);
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    gap: 2px;
  }

  .ticker-up .ticker-change,
  .ticker-up .ticker-pct {
    color: var(--bullish);
  }

  .ticker-down .ticker-change,
  .ticker-down .ticker-pct {
    color: var(--bearish);
  }

  /* ===== Page Header ===== */
  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    flex-shrink: 0;
    border-bottom: 1px solid var(--border-subtle);
    background: var(--bg-base);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--accent);
  }

  .page-title {
    font-size: var(--text-base);
    font-weight: 700;
    color: var(--text-primary);
    margin: 0;
  }

  .header-badge {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--bullish);
    background: var(--bullish-bg);
    border: 1px solid var(--bullish-dim);
    border-radius: var(--radius-sm);
    padding: 1px 6px;
    animation: pulse-badge 2s ease-in-out infinite;
  }

  @keyframes pulse-badge {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .header-divider {
    width: 1px;
    height: 18px;
    background: var(--border-subtle);
  }

  .header-timestamp {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: var(--text-xs);
    font-family: var(--font-mono);
    color: var(--text-tertiary);
  }

  .refresh-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: var(--radius-md);
    border: 1px solid var(--border-subtle);
    background: transparent;
    color: var(--text-tertiary);
    cursor: pointer;
    transition: all 150ms;
  }

  .refresh-btn:hover {
    color: var(--text-primary);
    border-color: var(--border-default);
    background: var(--bg-surface);
  }

  /* ===== Loading State ===== */
  .loading-state {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    flex: 1;
    color: var(--text-tertiary);
  }

  .loading-text {
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--text-tertiary);
  }

  /* ===== Page Content ===== */
  .page-content {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  /* ===== Glass Panel ===== */
  .glass-panel {
    background: oklch(0.14 0.02 260 / 0.7);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
  }

  .panel-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 16px;
    border-bottom: 1px solid oklch(0.20 0.01 260 / 0.5);
    color: var(--text-tertiary);
  }

  .panel-title {
    font-size: var(--text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-secondary);
    margin: 0;
  }

  .panel-subtitle {
    font-size: 10px;
    color: var(--text-tertiary);
    margin-left: auto;
    font-weight: 400;
  }

  /* ===== Layout Rows ===== */
  .content-row {
    display: grid;
    gap: 16px;
  }

  .content-row--top {
    grid-template-columns: 1fr;
  }

  .content-row--movers {
    grid-template-columns: 1fr;
  }

  @media (min-width: 1024px) {
    .content-row--top {
      grid-template-columns: 3fr 2fr;
    }

    .content-row--movers {
      grid-template-columns: 1fr 1fr;
    }
  }

  /* ===== Market Breadth Panel ===== */
  .breadth-panel {
    display: flex;
    flex-direction: column;
  }

  .breadth-content {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .breadth-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .breadth-label-row {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    font-weight: 500;
  }

  .breadth-label--bull {
    color: var(--bullish);
  }

  .breadth-label--bear {
    color: var(--bearish);
  }

  .breadth-vs {
    color: var(--text-disabled);
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .breadth-bar-container {
    display: flex;
    height: 26px;
    border-radius: var(--radius-sm);
    overflow: hidden;
    gap: 2px;
  }

  .breadth-bar {
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 40px;
    transition: width 500ms var(--ease-out-expo);
  }

  .breadth-bar--adv {
    background: var(--bullish-dim);
    border-radius: var(--radius-sm) 0 0 var(--radius-sm);
  }

  .breadth-bar--dec {
    background: var(--bearish-dim);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  }

  .breadth-bar-value {
    font-size: 10px;
    font-weight: 600;
    font-family: var(--font-mono);
    color: var(--text-primary);
    white-space: nowrap;
  }

  .breadth-ratio {
    font-size: 10px;
    color: var(--text-tertiary);
  }

  .breadth-ratio strong {
    color: var(--text-secondary);
  }

  /* ===== Internals Strip ===== */
  .internals-strip {
    display: flex;
    align-items: center;
    justify-content: space-around;
    padding: 10px 16px;
    border-top: 1px solid oklch(0.20 0.01 260 / 0.5);
    background: oklch(0.11 0.02 260 / 0.4);
    border-radius: 0 0 var(--radius-lg) var(--radius-lg);
  }

  .internal-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
  }

  .internal-label {
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-tertiary);
  }

  .internal-value {
    font-size: var(--text-sm);
    font-weight: 700;
    color: var(--text-secondary);
  }

  .internal-divider {
    width: 1px;
    height: 28px;
    background: var(--border-subtle);
  }

  .val-bull {
    color: var(--bullish) !important;
  }

  .val-bear {
    color: var(--bearish) !important;
  }

  .val-extreme {
    color: var(--bearish-bright) !important;
    text-shadow: 0 0 8px oklch(0.72 0.20 25 / 0.4);
  }

  /* ===== Sentiment Gauge Panel ===== */
  .sentiment-panel {
    display: flex;
    flex-direction: column;
  }

  .gauge-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 20px 16px 8px;
  }

  .gauge-svg {
    width: 100%;
    max-width: 240px;
    height: auto;
  }

  .gauge-readout {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin-top: -8px;
  }

  .gauge-value {
    font-size: var(--text-3xl);
    font-weight: 800;
    line-height: 1;
  }

  .gauge-label {
    font-size: var(--text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-top: 4px;
  }

  .sentiment-metrics {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1px;
    background: oklch(0.20 0.01 260 / 0.5);
    border-top: 1px solid oklch(0.20 0.01 260 / 0.5);
    border-radius: 0 0 var(--radius-lg) var(--radius-lg);
    overflow: hidden;
  }

  .sentiment-metric {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 10px 8px;
    background: oklch(0.11 0.02 260 / 0.6);
  }

  .sm-label {
    font-size: 9px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
  }

  .sm-value {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-secondary);
  }

  /* ===== Sector Performance Panel ===== */
  .sector-panel {
    display: flex;
    flex-direction: column;
  }

  .sector-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1px;
    background: oklch(0.20 0.01 260 / 0.3);
    border-radius: 0 0 var(--radius-lg) var(--radius-lg);
    overflow: hidden;
  }

  @media (min-width: 768px) {
    .sector-grid {
      grid-template-columns: repeat(3, 1fr);
    }
  }

  @media (min-width: 1200px) {
    .sector-grid {
      grid-template-columns: repeat(4, 1fr);
    }
  }

  .sector-card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 14px;
    background: oklch(0.12 0.02 260 / 0.8);
    transition: background 150ms;
    gap: 10px;
  }

  .sector-card:hover {
    background: oklch(0.16 0.02 260 / 0.8);
  }

  .sector-info {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
  }

  .sector-name {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sector-symbol {
    font-size: 10px;
    font-weight: 400;
    color: var(--text-tertiary);
    font-family: var(--font-mono);
  }

  .sector-perf {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 4px;
    min-width: 70px;
  }

  .sector-change {
    font-size: var(--text-xs);
    font-weight: 700;
  }

  .sector-up .sector-change {
    color: var(--bullish);
  }

  .sector-down .sector-change {
    color: var(--bearish);
  }

  .sector-bar-track {
    width: 100%;
    height: 3px;
    background: oklch(0.20 0.01 260 / 0.6);
    border-radius: 2px;
    overflow: hidden;
    display: flex;
  }

  .sector-bar {
    height: 100%;
    border-radius: 2px;
    transition: width 500ms var(--ease-out-expo);
  }

  .sector-bar--pos {
    background: var(--bullish);
    margin-left: auto;
  }

  .sector-bar--neg {
    background: var(--bearish);
  }

  /* ===== Market Movers ===== */
  .movers-panel {
    display: flex;
    flex-direction: column;
  }

  .movers-table {
    display: flex;
    flex-direction: column;
  }

  .movers-header-row {
    display: flex;
    align-items: center;
    padding: 8px 16px;
    border-bottom: 1px solid oklch(0.20 0.01 260 / 0.5);
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-tertiary);
  }

  .mh-symbol {
    flex: 1;
  }

  .mh-price {
    width: 90px;
    text-align: right;
  }

  .mh-change {
    width: 80px;
    text-align: right;
  }

  .mover-row {
    display: flex;
    align-items: center;
    padding: 8px 16px;
    border-bottom: 1px solid oklch(0.20 0.01 260 / 0.2);
    transition: background 100ms;
  }

  .mover-row:last-child {
    border-bottom: none;
  }

  .mover-row:hover {
    background: oklch(0.95 0.01 260 / 0.03);
  }

  .mover-symbol-col {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }

  .mover-rank {
    font-size: 10px;
    font-weight: 600;
    color: var(--text-disabled);
    width: 16px;
    text-align: center;
    flex-shrink: 0;
  }

  .mover-id {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .mover-symbol {
    font-size: var(--text-xs);
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: 0.02em;
  }

  .mover-name {
    font-size: 10px;
    color: var(--text-tertiary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .mover-price {
    width: 90px;
    text-align: right;
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--text-secondary);
  }

  .mover-change {
    width: 80px;
    text-align: right;
    font-size: var(--text-xs);
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    justify-content: flex-end;
    gap: 3px;
  }

  .mover-change--gain {
    color: var(--bullish);
  }

  .mover-change--loss {
    color: var(--bearish);
  }

  /* ===== Utility ===== */
  .mono-nums {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
  }

  /* ===== Scrollbar ===== */
  .page-root::-webkit-scrollbar {
    width: 6px;
  }

  .page-root::-webkit-scrollbar-track {
    background: transparent;
  }

  .page-root::-webkit-scrollbar-thumb {
    background: oklch(0.28 0.01 260);
    border-radius: 3px;
  }

  .page-root::-webkit-scrollbar-thumb:hover {
    background: oklch(0.38 0.02 260);
  }

  /* ===== Responsive ===== */
  @media (max-width: 640px) {
    .ticker-bar {
      flex-wrap: nowrap;
    }

    .ticker-item {
      min-width: 140px;
    }

    .page-content {
      padding: 12px;
      gap: 12px;
    }

    .sentiment-metrics {
      grid-template-columns: repeat(2, 1fr);
    }

    .sector-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
