<script lang="ts">
  import { onMount } from 'svelte';
  import InternalsBar from '$lib/components/market/InternalsBar.svelte';
  import ExportToolbar from '$lib/components/ui/ExportToolbar.svelte';
  import {
    TrendUp,
    TrendDown,
    Pulse,
    ChartBar,
    Lightning,
    Clock,
    Gauge,
    Globe,
    Eye,
    Target,
    Fire,
    Broadcast,
    CaretUp,
    CaretDown,
    ChartLine,
    Warning,
  } from 'phosphor-svelte';

  const API_BASE = 'http://localhost:8000';

  // ---------------------------------------------------------------------------
  // SIMULATED DATA (fallback when API unreachable)
  // ---------------------------------------------------------------------------

  function generateSparkline(base: number, volatility: number, trend: number = 0.5, points = 24): number[] {
    const data: number[] = [];
    let val = base - volatility * 3;
    for (let i = 0; i < points; i++) {
      val += (Math.random() - (0.5 - trend * 0.04)) * volatility;
      val = Math.max(base - volatility * 5, Math.min(base + volatility * 4, val));
      data.push(val);
    }
    return data;
  }

  const SIM_SPARKLINES = {
    'SPX':     generateSparkline(5823, 18, 0.6),
    'VIX':     generateSparkline(16.4, 0.8, -0.5),
    'volume':  generateSparkline(3.5, 0.4, 0.3),
    'breadth': generateSparkline(1.45, 0.15, 0.6),
    'pcr':     generateSparkline(0.78, 0.06, -0.4),
    'DJI':     generateSparkline(38920, 120, 0.5),
  };

  const SIM_KPI = {
    marketStatus: 'open' as 'open' | 'pre' | 'post' | 'closed',
    spx:         { price: 5823.47, change: 32.15, changePct: 0.56 },
    vix:         { price: 16.42, change: -0.83, changePct: -4.81 },
    putCallRatio: 0.78,
    totalVolume:  3.72,
    breadth:      1.42,
    advancers:    1847,
    decliners:    1142,
    unchanged:    89,
    newHighs:     142,
    newLows:      28,
    tickVal:      487,
    trinVal:      0.87,
  };

  const SIM_SIGNALS: {
    id: number;
    timestamp: string;
    symbol: string;
    signalType: string;
    direction: 'bullish' | 'bearish' | 'neutral';
    strength: number;
    price: number;
    change: number;
  }[] = [
    { id: 1,  timestamp: '15:42:18', symbol: 'NVDA',  signalType: 'Momentum Breakout',  direction: 'bullish',  strength: 5, price: 924.68,  change: 4.82 },
    { id: 2,  timestamp: '15:41:05', symbol: 'TSLA',  signalType: 'Volume Surge',        direction: 'bullish',  strength: 4, price: 248.52,  change: 3.14 },
    { id: 3,  timestamp: '15:39:47', symbol: 'META',  signalType: 'Golden Cross',        direction: 'bullish',  strength: 4, price: 512.30,  change: 1.87 },
    { id: 4,  timestamp: '15:38:22', symbol: 'AAPL',  signalType: 'RSI Divergence',      direction: 'bearish',  strength: 3, price: 189.84,  change: -0.42 },
    { id: 5,  timestamp: '15:36:51', symbol: 'AMZN',  signalType: 'VWAP Reclaim',        direction: 'bullish',  strength: 4, price: 186.92,  change: 2.15 },
    { id: 6,  timestamp: '15:35:10', symbol: 'JPM',   signalType: 'Relative Strength',   direction: 'bullish',  strength: 3, price: 198.44,  change: 1.22 },
    { id: 7,  timestamp: '15:33:42', symbol: 'XOM',   signalType: 'Bearish Engulfing',   direction: 'bearish',  strength: 4, price: 104.28,  change: -1.85 },
    { id: 8,  timestamp: '15:31:18', symbol: 'MSFT',  signalType: 'Squeeze Firing',      direction: 'bullish',  strength: 5, price: 428.72,  change: 2.94 },
    { id: 9,  timestamp: '15:29:55', symbol: 'AMD',   signalType: 'Dark Pool Print',     direction: 'neutral',  strength: 3, price: 174.56,  change: 0.68 },
    { id: 10, timestamp: '15:28:02', symbol: 'GOOGL', signalType: 'Options Flow Alert',  direction: 'bullish',  strength: 4, price: 176.48,  change: 1.52 },
    { id: 11, timestamp: '15:26:30', symbol: 'V',     signalType: 'Sector Rotation',     direction: 'bullish',  strength: 3, price: 282.14,  change: 0.92 },
    { id: 12, timestamp: '15:24:15', symbol: 'CRM',   signalType: 'Earnings Drift',      direction: 'bearish',  strength: 3, price: 248.86,  change: -1.28 },
    { id: 13, timestamp: '15:22:48', symbol: 'NFLX',  signalType: 'Gap Fill',            direction: 'neutral',  strength: 2, price: 638.40,  change: 0.34 },
    { id: 14, timestamp: '15:20:32', symbol: 'BA',    signalType: 'Unusual Volume',      direction: 'bearish',  strength: 4, price: 172.95,  change: -2.62 },
    { id: 15, timestamp: '15:18:05', symbol: 'COIN',  signalType: 'Momentum Ignition',   direction: 'bullish',  strength: 5, price: 264.30,  change: 6.18 },
  ];

  const SIM_SECTORS: { name: string; ticker: string; change: number; weight: number }[] = [
    { name: 'Technology',       ticker: 'XLK',  change: 1.24,  weight: 29.2 },
    { name: 'Healthcare',       ticker: 'XLV',  change: -0.31, weight: 13.1 },
    { name: 'Financials',       ticker: 'XLF',  change: 0.52,  weight: 12.8 },
    { name: 'Consumer Disc.',   ticker: 'XLY',  change: 0.87,  weight: 10.5 },
    { name: 'Communication',    ticker: 'XLC',  change: 1.05,  weight: 8.9 },
    { name: 'Industrials',      ticker: 'XLI',  change: 0.33,  weight: 8.4 },
    { name: 'Consumer Staples', ticker: 'XLP',  change: -0.18, weight: 6.2 },
    { name: 'Energy',           ticker: 'XLE',  change: -0.72, weight: 3.9 },
    { name: 'Utilities',        ticker: 'XLU',  change: 0.14,  weight: 2.6 },
    { name: 'Real Estate',      ticker: 'XLRE', change: -0.44, weight: 2.4 },
    { name: 'Materials',        ticker: 'XLB',  change: 0.21,  weight: 2.0 },
  ];

  // ---------------------------------------------------------------------------
  // REACTIVE STATE
  // ---------------------------------------------------------------------------

  let loading = $state(false);
  let connected = $state(false);
  let needsApiKey = $state(false);

  let indices = $state<{ symbol: string; price: number; change: number; changePercent: number }[]>([
    { symbol: 'SPX', price: SIM_KPI.spx.price, change: SIM_KPI.spx.change, changePercent: SIM_KPI.spx.changePct },
    { symbol: 'VIX', price: SIM_KPI.vix.price, change: SIM_KPI.vix.change, changePercent: SIM_KPI.vix.changePct },
    { symbol: 'DJI', price: 38920.14, change: 127.43, changePercent: 0.33 },
    { symbol: 'NDX', price: 20417.62, change: 185.28, changePercent: 0.92 },
    { symbol: 'RUT', price: 2087.35, change: -12.47, changePercent: -0.59 },
  ]);
  let topSignals = $state<{ symbol: string; direction: 'bullish' | 'bearish' | 'neutral'; name: string; strength: number; price: number }[]>(
    SIM_SIGNALS.slice(0, 5).map(s => ({ symbol: s.symbol, direction: s.direction, name: s.signalType, strength: s.strength, price: s.price }))
  );
  let sectors = $state<{ name: string; change: number }[]>(
    SIM_SECTORS.map(s => ({ name: s.name, change: s.change }))
  );

  let tick = $state(SIM_KPI.tickVal);
  let trin = $state(SIM_KPI.trinVal);
  let vix = $state(SIM_KPI.vix.price);
  let advDecRatio = $state(SIM_KPI.breadth);

  let currentTime = $state(new Date().toLocaleTimeString('en-US', { hour12: false }));

  // ---------------------------------------------------------------------------
  // SPARKLINE HELPERS
  // ---------------------------------------------------------------------------

  function sparklinePath(data: number[], width: number, height: number, pad = 2): string {
    if (!data || data.length < 2) return '';
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const step = (width - pad * 2) / (data.length - 1);
    return data
      .map((v, i) => `${(pad + i * step).toFixed(1)},${(pad + (1 - (v - min) / range) * (height - pad * 2)).toFixed(1)}`)
      .join(' ');
  }

  function sparklineArea(data: number[], width: number, height: number, pad = 2): string {
    if (!data || data.length < 2) return '';
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const step = (width - pad * 2) / (data.length - 1);
    const pts = data.map((v, i) => ({
      x: pad + i * step,
      y: pad + (1 - (v - min) / range) * (height - pad * 2),
    }));
    let d = `M ${pts[0]!.x.toFixed(1)} ${pts[0]!.y.toFixed(1)}`;
    for (let i = 1; i < pts.length; i++) d += ` L ${pts[i]!.x.toFixed(1)} ${pts[i]!.y.toFixed(1)}`;
    d += ` L ${pts[pts.length - 1]!.x.toFixed(1)} ${(height - pad).toFixed(1)}`;
    d += ` L ${pts[0]!.x.toFixed(1)} ${(height - pad).toFixed(1)} Z`;
    return d;
  }

  // ---------------------------------------------------------------------------
  // DERIVED
  // ---------------------------------------------------------------------------

  let breadthTotal = $derived(SIM_KPI.advancers + SIM_KPI.decliners + SIM_KPI.unchanged);
  let advPct = $derived((SIM_KPI.advancers / breadthTotal) * 100);
  let decPct = $derived((SIM_KPI.decliners / breadthTotal) * 100);
  let unchPct = $derived((SIM_KPI.unchanged / breadthTotal) * 100);

  let sortedSectors = $derived.by(() => [...SIM_SECTORS].sort((a, b) => b.change - a.change));

  let statusColor = $derived.by(() => {
    const s = SIM_KPI.marketStatus;
    if (s === 'open') return 'var(--bullish-bright)';
    if (s === 'pre') return 'var(--warning-bright)';
    if (s === 'post') return 'var(--warning)';
    return 'var(--text-tertiary)';
  });

  let statusLabel = $derived.by(() => {
    const s = SIM_KPI.marketStatus;
    if (s === 'open') return 'MARKET OPEN';
    if (s === 'pre') return 'PRE-MARKET';
    if (s === 'post') return 'AFTER HOURS';
    return 'CLOSED';
  });

  // ---------------------------------------------------------------------------
  // DATA FETCHING (preserved from original)
  // ---------------------------------------------------------------------------

  async function fetchDashboardData() {
    try {
      const health = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(1500) });
      connected = health.ok;
    } catch {
      connected = false;
      return;
    }

    let anyProviderError = false;

    try {
      const priceRes = await fetch(`${API_BASE}/api/equity/price/snapshot`, { signal: AbortSignal.timeout(3000) });
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
      } else {
        anyProviderError = true;
      }
    } catch { anyProviderError = true; }

    try {
      const macroRes = await fetch(`${API_BASE}/api/equity/macro/snapshot`, { signal: AbortSignal.timeout(3000) });
      if (macroRes.ok) {
        const macroData = await macroRes.json();
        const macro = macroData.data ?? macroData;
        vix = macro.vix ?? macro.VIX ?? 0;
        tick = macro.tick ?? macro.TICK ?? 0;
        trin = macro.trin ?? macro.TRIN ?? 1.0;
        advDecRatio = macro.advDecRatio ?? macro.advance_decline ?? macro.ad_ratio ?? 1.0;
      } else {
        anyProviderError = true;
      }
    } catch { anyProviderError = true; }

    try {
      const sectorRes = await fetch(`${API_BASE}/api/equity/market/sectors`, { signal: AbortSignal.timeout(3000) });
      if (sectorRes.ok) {
        const sectorData = await sectorRes.json();
        const rawSectors = Array.isArray(sectorData) ? sectorData : sectorData.data ?? sectorData.sectors ?? [];
        sectors = rawSectors.map((s: any) => ({
          name: s.name ?? s.sector ?? '',
          change: s.change ?? s.changePercent ?? s.change_percent ?? 0,
        }));
      } else {
        anyProviderError = true;
      }
    } catch { anyProviderError = true; }

    try {
      const moversRes = await fetch(`${API_BASE}/api/equity/market/movers?limit=5`, { signal: AbortSignal.timeout(3000) });
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
      } else {
        anyProviderError = true;
      }
    } catch { anyProviderError = true; }

    needsApiKey = anyProviderError;
    loading = false;
  }

  onMount(() => {
    fetchDashboardData();
    const clockInterval = setInterval(() => {
      currentTime = new Date().toLocaleTimeString('en-US', { hour12: false });
    }, 1000);
    return () => clearInterval(clockInterval);
  });

  // ---------------------------------------------------------------------------
  // HELPERS
  // ---------------------------------------------------------------------------

  function changeColor(val: number): string {
    if (val > 0) return 'var(--bullish)';
    if (val < 0) return 'var(--bearish)';
    return 'var(--text-secondary)';
  }

  function changeBright(val: number): string {
    if (val > 0) return 'var(--bullish-bright)';
    if (val < 0) return 'var(--bearish-bright)';
    return 'var(--text-secondary)';
  }

  function dirBright(dir: string): string {
    if (dir === 'bullish') return 'var(--bullish-bright)';
    if (dir === 'bearish') return 'var(--bearish-bright)';
    return 'var(--neutral-bright)';
  }

  function sectorHeatBg(change: number): string {
    if (change >= 1.0)  return 'oklch(0.38 0.14 155)';
    if (change >= 0.5)  return 'oklch(0.30 0.10 155)';
    if (change >= 0.0)  return 'oklch(0.22 0.06 155)';
    if (change >= -0.5) return 'oklch(0.22 0.06 25)';
    if (change >= -1.0) return 'oklch(0.30 0.10 25)';
    return 'oklch(0.38 0.14 25)';
  }

  function sectorHeatText(change: number): string {
    if (change >= 0.5)  return 'var(--bullish-bright)';
    if (change >= 0.0)  return 'var(--bullish)';
    if (change >= -0.5) return 'var(--bearish)';
    return 'var(--bearish-bright)';
  }

  function sectorHeatBorder(change: number): string {
    if (change >= 0) return 'oklch(0.45 0.12 155 / 0.25)';
    return 'oklch(0.42 0.12 25 / 0.25)';
  }

  function signalIconKind(s: string): string {
    if (s.includes('Momentum') || s.includes('Breakout') || s.includes('Ignition')) return 'lightning';
    if (s.includes('Volume'))     return 'chart-bar';
    if (s.includes('RSI'))        return 'gauge';
    if (s.includes('VWAP') || s.includes('Cross')) return 'target';
    if (s.includes('Options') || s.includes('Dark Pool')) return 'eye';
    if (s.includes('Squeeze'))    return 'fire';
    if (s.includes('Sector') || s.includes('Rotation')) return 'globe';
    if (s.includes('Engulfing') || s.includes('Support') || s.includes('Bearish')) return 'trend-down';
    return 'pulse';
  }
</script>

<svelte:head>
  <title>Dashboard - Scanify</title>
</svelte:head>

<div class="dashboard-page">
  <!-- ================================================================
       CONNECTION / API KEY BANNERS
       ================================================================ -->
  {#if !loading && !connected}
    <div class="conn-banner">
      <div class="banner-left">
        <Warning size={15} weight="fill" />
        <span class="banner-text">Backend offline -- displaying simulated data. Start the API server for live feeds.</span>
      </div>
      <button class="banner-btn" onclick={() => fetchDashboardData()}>
        <Broadcast size={13} />
        Reconnect
      </button>
    </div>
  {:else if !loading && needsApiKey}
    <div class="conn-banner warn-banner">
      <div class="banner-left">
        <Warning size={15} weight="fill" />
        <span class="banner-text">Data provider API key required -- configure vendor keys in Settings</span>
      </div>
      <a href="/settings" class="banner-btn">Configure</a>
    </div>
  {/if}

  <!-- ================================================================
       PAGE HEADER
       ================================================================ -->
  <header class="page-header">
    <div class="hdr-left">
      <h1 class="page-title">Dashboard</h1>
      <div class="status-chip">
        <span class="status-dot-wrap">
          <span class="status-dot" style="background:{statusColor};"></span>
          {#if SIM_KPI.marketStatus === 'open'}
            <span class="status-ring" style="border-color:{statusColor};"></span>
          {/if}
        </span>
        <span class="status-text" style="color:{statusColor};">{statusLabel}</span>
      </div>
    </div>
    <div class="hdr-right">
      <ExportToolbar source="dashboard" />
      <div class="hdr-sep"></div>
      <div class="hdr-clock">
        <Clock size={13} />
        <span class="clock-val mono-nums">{currentTime}</span>
      </div>
      <div class="hdr-sep"></div>
      <span class="hdr-date">
        {new Date().toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}
      </span>
    </div>
  </header>

  {#if loading}
    <!-- ================================================================
         LOADING SKELETON
         ================================================================ -->
    <div class="skel-kpi-row stagger-fade">
      {#each Array(6) as _}
        <div class="skel-card">
          <div class="skeleton" style="width:55%;height:10px;"></div>
          <div class="skeleton" style="width:75%;height:22px;margin-top:8px;"></div>
          <div class="skeleton" style="width:100%;height:28px;margin-top:10px;"></div>
        </div>
      {/each}
    </div>
    <div class="skel-main-row">
      <div class="skel-card skel-tall"><div class="skeleton" style="width:100%;height:100%;"></div></div>
      <div class="skel-card skel-tall"><div class="skeleton" style="width:100%;height:100%;"></div></div>
      <div class="skel-card skel-tall"><div class="skeleton" style="width:100%;height:100%;"></div></div>
    </div>
  {:else}
    <!-- ================================================================
         KPI CARDS ROW
         ================================================================ -->
    <div class="kpi-row stagger-fade">

      <!-- Market Status -->
      <div class="kpi-card">
        <div class="kpi-hdr">
          <Globe size={13} weight="duotone" />
          <span class="kpi-label">Market Status</span>
        </div>
        <div class="kpi-val-row">
          <span class="kpi-val" style="color:{statusColor}; font-size: var(--text-base);">{statusLabel}</span>
        </div>
        <div class="kpi-meta">
          <span>NYSE</span>
          <span class="kpi-meta-sep">|</span>
          <span>NASDAQ</span>
        </div>
      </div>

      <!-- S&P 500 -->
      <div class="kpi-card">
        <div class="kpi-hdr">
          <ChartLine size={13} weight="duotone" />
          <span class="kpi-label">S&P 500</span>
        </div>
        <div class="kpi-val-row">
          <span class="kpi-val mono-nums">{SIM_KPI.spx.price.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
          <span class="kpi-delta mono-nums" style="color:{changeBright(SIM_KPI.spx.changePct)};">
            {#if SIM_KPI.spx.changePct >= 0}<CaretUp size={11} weight="fill" />{:else}<CaretDown size={11} weight="fill" />{/if}
            {SIM_KPI.spx.changePct >= 0 ? '+' : ''}{SIM_KPI.spx.changePct.toFixed(2)}%
          </span>
        </div>
        <div class="kpi-spark">
          <svg viewBox="0 0 120 30" preserveAspectRatio="none">
            <defs>
              <linearGradient id="g-spx" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="oklch(0.64 0.16 155)" stop-opacity="0.30" />
                <stop offset="100%" stop-color="oklch(0.64 0.16 155)" stop-opacity="0.02" />
              </linearGradient>
            </defs>
            <path d={sparklineArea(SIM_SPARKLINES['SPX'], 120, 30)} fill="url(#g-spx)" />
            <polyline points={sparklinePath(SIM_SPARKLINES['SPX'], 120, 30)} fill="none" stroke="var(--bullish)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>
      </div>

      <!-- VIX -->
      <div class="kpi-card">
        <div class="kpi-hdr">
          <Pulse size={13} weight="duotone" />
          <span class="kpi-label">VIX</span>
        </div>
        <div class="kpi-val-row">
          <span class="kpi-val mono-nums">{SIM_KPI.vix.price.toFixed(2)}</span>
          <span class="kpi-delta mono-nums" style="color:{changeBright(-SIM_KPI.vix.changePct)};">
            {#if SIM_KPI.vix.changePct >= 0}<CaretUp size={11} weight="fill" />{:else}<CaretDown size={11} weight="fill" />{/if}
            {SIM_KPI.vix.changePct >= 0 ? '+' : ''}{SIM_KPI.vix.changePct.toFixed(2)}%
          </span>
        </div>
        <div class="kpi-spark">
          <svg viewBox="0 0 120 30" preserveAspectRatio="none">
            <defs>
              <linearGradient id="g-vix" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="oklch(0.64 0.16 155)" stop-opacity="0.30" />
                <stop offset="100%" stop-color="oklch(0.64 0.16 155)" stop-opacity="0.02" />
              </linearGradient>
            </defs>
            <path d={sparklineArea(SIM_SPARKLINES['VIX'], 120, 30)} fill="url(#g-vix)" />
            <polyline points={sparklinePath(SIM_SPARKLINES['VIX'], 120, 30)} fill="none" stroke="var(--bullish)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>
      </div>

      <!-- Put/Call Ratio -->
      <div class="kpi-card">
        <div class="kpi-hdr">
          <Gauge size={13} weight="duotone" />
          <span class="kpi-label">Put/Call Ratio</span>
        </div>
        <div class="kpi-val-row">
          <span class="kpi-val mono-nums">{SIM_KPI.putCallRatio.toFixed(2)}</span>
          <span class="kpi-tag" style="background:var(--bullish-bg);color:var(--bullish-bright);">Bullish</span>
        </div>
        <div class="kpi-spark">
          <svg viewBox="0 0 120 30" preserveAspectRatio="none">
            <defs>
              <linearGradient id="g-pcr" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="oklch(0.62 0.20 290)" stop-opacity="0.30" />
                <stop offset="100%" stop-color="oklch(0.62 0.20 290)" stop-opacity="0.02" />
              </linearGradient>
            </defs>
            <path d={sparklineArea(SIM_SPARKLINES['pcr'], 120, 30)} fill="url(#g-pcr)" />
            <polyline points={sparklinePath(SIM_SPARKLINES['pcr'], 120, 30)} fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>
      </div>

      <!-- Total Volume -->
      <div class="kpi-card">
        <div class="kpi-hdr">
          <ChartBar size={13} weight="duotone" />
          <span class="kpi-label">Total Volume</span>
        </div>
        <div class="kpi-val-row">
          <span class="kpi-val mono-nums">{SIM_KPI.totalVolume.toFixed(1)}B</span>
          <span class="kpi-sub-val">shares</span>
        </div>
        <div class="kpi-spark">
          <svg viewBox="0 0 120 30" preserveAspectRatio="none">
            <defs>
              <linearGradient id="g-vol" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="oklch(0.78 0.14 250)" stop-opacity="0.30" />
                <stop offset="100%" stop-color="oklch(0.78 0.14 250)" stop-opacity="0.02" />
              </linearGradient>
            </defs>
            <path d={sparklineArea(SIM_SPARKLINES['volume'], 120, 30)} fill="url(#g-vol)" />
            <polyline points={sparklinePath(SIM_SPARKLINES['volume'], 120, 30)} fill="none" stroke="var(--neutral-bright)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>
      </div>

      <!-- Market Breadth -->
      <div class="kpi-card">
        <div class="kpi-hdr">
          <TrendUp size={13} weight="duotone" />
          <span class="kpi-label">Breadth (A/D)</span>
        </div>
        <div class="kpi-val-row">
          <span class="kpi-val mono-nums">{SIM_KPI.breadth.toFixed(2)}</span>
          <span class="kpi-tag" style="background:var(--bullish-bg);color:var(--bullish-bright);">Strong</span>
        </div>
        <div class="kpi-spark">
          <svg viewBox="0 0 120 30" preserveAspectRatio="none">
            <defs>
              <linearGradient id="g-brd" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="oklch(0.64 0.16 155)" stop-opacity="0.30" />
                <stop offset="100%" stop-color="oklch(0.64 0.16 155)" stop-opacity="0.02" />
              </linearGradient>
            </defs>
            <path d={sparklineArea(SIM_SPARKLINES['breadth'], 120, 30)} fill="url(#g-brd)" />
            <polyline points={sparklinePath(SIM_SPARKLINES['breadth'], 120, 30)} fill="none" stroke="var(--bullish)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>
      </div>
    </div>

    <!-- ================================================================
         MAIN 3-COLUMN GRID
         ================================================================ -->
    <div class="main-grid">

      <!-- ============================================================
           LEFT: Market Internals
           ============================================================ -->
      <div class="glass-panel internals-col">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <Pulse size={15} weight="duotone" />
            <h2 class="panel-title">Market Internals</h2>
          </div>
          <span class="live-badge">LIVE</span>
        </div>

        <InternalsBar tick={SIM_KPI.tickVal} trin={SIM_KPI.trinVal} vix={SIM_KPI.vix.price} advDecRatio={SIM_KPI.breadth} />

        <!-- Breadth bar -->
        <div class="breadth-section">
          <div class="breadth-hdr">
            <span class="breadth-title">Market Breadth</span>
            <span class="breadth-stats mono-nums">
              <span style="color:var(--bullish-bright);">{SIM_KPI.advancers}</span>
              <span class="sep">/</span>
              <span style="color:var(--bearish-bright);">{SIM_KPI.decliners}</span>
              <span class="sep">/</span>
              <span style="color:var(--text-tertiary);">{SIM_KPI.unchanged}</span>
            </span>
          </div>
          <div class="breadth-bar">
            <div class="bar-seg bar-adv" style="width:{advPct.toFixed(1)}%;" title="Advancing: {SIM_KPI.advancers} ({advPct.toFixed(1)}%)"></div>
            <div class="bar-seg bar-unch" style="width:{unchPct.toFixed(1)}%;" title="Unchanged: {SIM_KPI.unchanged}"></div>
            <div class="bar-seg bar-dec" style="width:{decPct.toFixed(1)}%;" title="Declining: {SIM_KPI.decliners} ({decPct.toFixed(1)}%)"></div>
          </div>
          <div class="breadth-labels">
            <span class="breadth-lbl" style="color:var(--bullish);">
              <CaretUp size={10} weight="fill" />
              {advPct.toFixed(0)}% Adv
            </span>
            <span class="breadth-lbl" style="color:var(--bearish);">
              <CaretDown size={10} weight="fill" />
              {decPct.toFixed(0)}% Dec
            </span>
          </div>
        </div>

        <!-- New Highs / Lows -->
        <div class="hilo-row">
          <div class="hilo-cell">
            <span class="hilo-label">New Highs</span>
            <span class="hilo-val mono-nums" style="color:var(--bullish-bright);">{SIM_KPI.newHighs}</span>
          </div>
          <div class="hilo-sep"></div>
          <div class="hilo-cell">
            <span class="hilo-label">New Lows</span>
            <span class="hilo-val mono-nums" style="color:var(--bearish-bright);">{SIM_KPI.newLows}</span>
          </div>
          <div class="hilo-sep"></div>
          <div class="hilo-cell">
            <span class="hilo-label">H/L Ratio</span>
            <span class="hilo-val mono-nums" style="color:var(--bullish-bright);">{(SIM_KPI.newHighs / SIM_KPI.newLows).toFixed(1)}</span>
          </div>
        </div>
      </div>

      <!-- ============================================================
           CENTER: Recent Signals Feed
           ============================================================ -->
      <div class="glass-panel signals-col">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <Lightning size={15} weight="duotone" />
            <h2 class="panel-title">Recent Signals</h2>
            <span class="count-badge mono-nums">{SIM_SIGNALS.length}</span>
          </div>
          <a href="/scanner" class="link-all">
            View all
            <CaretUp size={11} style="transform:rotate(90deg);" />
          </a>
        </div>

        <div class="signals-feed">
          {#each SIM_SIGNALS as sig (sig.id)}
            <div class="sig-row">
              <!-- Time -->
              <span class="sig-time mono-nums">{sig.timestamp}</span>

              <!-- Icon -->
              <span class="sig-icon" style="color:{dirBright(sig.direction)};">
                {#if signalIconKind(sig.signalType) === 'lightning'}
                  <Lightning size={13} weight="fill" />
                {:else if signalIconKind(sig.signalType) === 'chart-bar'}
                  <ChartBar size={13} weight="fill" />
                {:else if signalIconKind(sig.signalType) === 'gauge'}
                  <Gauge size={13} weight="fill" />
                {:else if signalIconKind(sig.signalType) === 'target'}
                  <Target size={13} weight="fill" />
                {:else if signalIconKind(sig.signalType) === 'eye'}
                  <Eye size={13} weight="fill" />
                {:else if signalIconKind(sig.signalType) === 'fire'}
                  <Fire size={13} weight="fill" />
                {:else if signalIconKind(sig.signalType) === 'globe'}
                  <Globe size={13} weight="fill" />
                {:else if signalIconKind(sig.signalType) === 'trend-down'}
                  <TrendDown size={13} weight="fill" />
                {:else}
                  <Pulse size={13} weight="fill" />
                {/if}
              </span>

              <!-- Symbol + Type -->
              <span class="sig-sym mono-nums">{sig.symbol}</span>
              <span class="sig-type">{sig.signalType}</span>

              <!-- Strength -->
              <span class="sig-str">
                {#each Array(5) as _, si}
                  <span class="str-pip" style="background:{si < sig.strength ? dirBright(sig.direction) : 'var(--bg-overlay)'};"></span>
                {/each}
              </span>

              <!-- Price + Change -->
              <span class="sig-price-col">
                <span class="sig-price mono-nums">${sig.price.toFixed(2)}</span>
                <span class="sig-chg mono-nums" style="color:{changeBright(sig.change)};">
                  {sig.change >= 0 ? '+' : ''}{sig.change.toFixed(2)}%
                </span>
              </span>
            </div>
          {/each}
        </div>
      </div>

      <!-- ============================================================
           RIGHT: Sector Performance Heatmap
           ============================================================ -->
      <div class="glass-panel sectors-col">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <ChartBar size={15} weight="duotone" />
            <h2 class="panel-title">Sector Performance</h2>
          </div>
          <span class="panel-sub-lbl">GICS 11</span>
        </div>

        <div class="sector-grid">
          {#each sortedSectors as sec (sec.ticker)}
            <div class="sector-tile" style="background:{sectorHeatBg(sec.change)};border-color:{sectorHeatBorder(sec.change)};">
              <div class="sector-tile-hdr">
                <span class="sector-ticker mono-nums">{sec.ticker}</span>
                <span class="sector-chg mono-nums" style="color:{sectorHeatText(sec.change)};">
                  {sec.change >= 0 ? '+' : ''}{sec.change.toFixed(2)}%
                </span>
              </div>
              <span class="sector-name">{sec.name}</span>
              <span class="sector-wt mono-nums">{sec.weight.toFixed(1)}%</span>
            </div>
          {/each}
        </div>

        <div class="sector-summary">
          <div class="summary-item">
            <CaretUp size={11} weight="fill" style="color:var(--bullish-bright);" />
            <span class="summary-ct mono-nums" style="color:var(--bullish-bright);">
              {SIM_SECTORS.filter(s => s.change > 0).length}
            </span>
            <span class="summary-lbl">advancing</span>
          </div>
          <div class="summary-item">
            <CaretDown size={11} weight="fill" style="color:var(--bearish-bright);" />
            <span class="summary-ct mono-nums" style="color:var(--bearish-bright);">
              {SIM_SECTORS.filter(s => s.change < 0).length}
            </span>
            <span class="summary-lbl">declining</span>
          </div>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  /* ===================================================================
     PAGE LAYOUT
     =================================================================== */
  .dashboard-page {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: auto;
    padding: 14px 20px 24px;
    gap: 14px;
  }

  /* ===================================================================
     CONNECTION BANNER
     =================================================================== */
  .conn-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 14px;
    border-radius: var(--radius-lg);
    background: oklch(0.14 0.02 260 / 0.7);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border-subtle);
  }

  .warn-banner {
    border-color: oklch(0.52 0.10 85 / 0.40);
    background: oklch(0.16 0.04 85 / 0.15);
  }

  .banner-left {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-secondary);
  }

  .banner-text {
    font-size: var(--text-xs);
    font-weight: 500;
  }

  .banner-btn {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--accent);
    background: none;
    border: 1px solid var(--accent);
    border-radius: var(--radius-md);
    padding: 4px 12px;
    cursor: pointer;
    transition: background-color 150ms, color 150ms;
    text-decoration: none;
  }

  .banner-btn:hover {
    background: var(--accent);
    color: var(--bg-base);
  }

  /* ===================================================================
     PAGE HEADER
     =================================================================== */
  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }

  .hdr-left {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .page-title {
    font-size: var(--text-xl);
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.02em;
  }

  .status-chip {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 3px 11px 3px 7px;
    border-radius: var(--radius-full);
    background: oklch(0.14 0.02 260 / 0.6);
    border: 1px solid var(--border-subtle);
  }

  .status-dot-wrap {
    position: relative;
    width: 8px;
    height: 8px;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    position: relative;
    z-index: 1;
    display: block;
  }

  .status-ring {
    position: absolute;
    inset: -3px;
    border-radius: var(--radius-full);
    border: 1.5px solid;
    opacity: 0.5;
    animation: signal-ping 2s cubic-bezier(0, 0, 0.2, 1) infinite;
    display: block;
  }

  .status-text {
    font-size: var(--text-2xs);
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .hdr-right {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .hdr-sep {
    width: 1px;
    height: 20px;
    background: var(--border-subtle);
  }

  .hdr-clock {
    display: flex;
    align-items: center;
    gap: 5px;
    color: var(--text-secondary);
  }

  .clock-val {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-primary);
  }

  .hdr-date {
    font-size: var(--text-xs);
    font-family: var(--font-mono);
    color: var(--text-tertiary);
  }

  /* ===================================================================
     LOADING SKELETON
     =================================================================== */
  .skel-kpi-row {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 10px;
  }

  .skel-main-row {
    display: grid;
    grid-template-columns: 1fr 1.4fr 1fr;
    gap: 12px;
    flex: 1;
  }

  .skel-card {
    padding: 14px;
    border-radius: var(--radius-lg);
    background: oklch(0.14 0.02 260 / 0.7);
    border: 1px solid var(--border-subtle);
  }

  .skel-tall {
    min-height: 280px;
  }

  /* ===================================================================
     KPI CARDS ROW
     =================================================================== */
  .kpi-row {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 10px;
    flex-shrink: 0;
  }

  .kpi-card {
    background: oklch(0.14 0.02 260 / 0.7);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 12px 14px 8px;
    display: flex;
    flex-direction: column;
    gap: 5px;
    transition: border-color var(--duration-normal) ease,
                box-shadow var(--duration-normal) ease;
  }

  .kpi-card:hover {
    border-color: oklch(0.30 0.04 260 / 0.60);
    box-shadow: var(--glow-sm);
  }

  .kpi-hdr {
    display: flex;
    align-items: center;
    gap: 5px;
    color: var(--text-tertiary);
  }

  .kpi-label {
    font-size: var(--text-2xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-tertiary);
  }

  .kpi-val-row {
    display: flex;
    align-items: baseline;
    gap: 8px;
    flex-wrap: wrap;
  }

  .kpi-val {
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.2;
  }

  .kpi-delta {
    display: inline-flex;
    align-items: center;
    gap: 1px;
    font-size: var(--text-2xs);
    font-weight: 600;
  }

  .kpi-tag {
    font-size: 9px;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: var(--radius-full);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .kpi-sub-val {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    font-weight: 500;
  }

  .kpi-meta {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
  }

  .kpi-meta-sep {
    color: var(--text-disabled);
  }

  .kpi-spark {
    margin-top: auto;
    height: 30px;
    width: 100%;
  }

  .kpi-spark svg {
    width: 100%;
    height: 100%;
    display: block;
  }

  /* ===================================================================
     MAIN GRID (3-column)
     =================================================================== */
  .main-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 12px;
    flex: 1;
    min-height: 0;
  }

  @media (min-width: 1024px) {
    .main-grid {
      grid-template-columns: 1fr 1.4fr 1fr;
    }
  }

  /* ===================================================================
     GLASS PANEL (shared)
     =================================================================== */
  .glass-panel {
    background: oklch(0.14 0.02 260 / 0.7);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    overflow: hidden;
  }

  .panel-hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }

  .panel-title-grp {
    display: flex;
    align-items: center;
    gap: 7px;
    color: var(--text-secondary);
  }

  .panel-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .live-badge {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.10em;
    color: var(--bullish-bright);
    background: var(--bullish-bg);
    padding: 2px 8px;
    border-radius: var(--radius-full);
    border: 1px solid oklch(0.45 0.12 155 / 0.25);
  }

  .panel-sub-lbl {
    font-size: var(--text-2xs);
    font-weight: 600;
    color: var(--text-tertiary);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  /* ===================================================================
     MARKET INTERNALS (left column)
     =================================================================== */
  .internals-col {
    overflow: visible;
  }

  .breadth-section {
    display: flex;
    flex-direction: column;
    gap: 7px;
  }

  .breadth-hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .breadth-title {
    font-size: var(--text-2xs);
    font-weight: 600;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .breadth-stats {
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: var(--text-2xs);
    font-weight: 600;
  }

  .sep {
    color: var(--text-disabled);
  }

  .breadth-bar {
    display: flex;
    height: 10px;
    border-radius: var(--radius-full);
    overflow: hidden;
    background: var(--bg-base);
  }

  .bar-seg {
    height: 100%;
    transition: width 300ms ease;
  }

  .bar-adv {
    background: var(--bullish);
    border-radius: var(--radius-full) 0 0 var(--radius-full);
  }

  .bar-unch {
    background: var(--text-disabled);
  }

  .bar-dec {
    background: var(--bearish);
    border-radius: 0 var(--radius-full) var(--radius-full) 0;
  }

  .breadth-labels {
    display: flex;
    justify-content: space-between;
  }

  .breadth-lbl {
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: var(--text-2xs);
    font-weight: 600;
  }

  .hilo-row {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 16px;
    padding-top: 10px;
    border-top: 1px solid var(--border-subtle);
  }

  .hilo-cell {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
  }

  .hilo-label {
    font-size: 9px;
    font-weight: 600;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .hilo-val {
    font-size: var(--text-sm);
    font-weight: 700;
  }

  .hilo-sep {
    width: 1px;
    height: 28px;
    background: var(--border-subtle);
  }

  /* ===================================================================
     RECENT SIGNALS FEED (center column)
     =================================================================== */
  .signals-col {
    min-height: 0;
  }

  .count-badge {
    font-size: var(--text-2xs);
    font-weight: 700;
    color: var(--accent);
    background: var(--accent-bg);
    padding: 1px 7px;
    border-radius: var(--radius-full);
  }

  .link-all {
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--accent);
    transition: color 150ms;
    text-decoration: none;
  }

  .link-all:hover {
    color: var(--accent-bright);
  }

  .signals-feed {
    display: flex;
    flex-direction: column;
    gap: 1px;
    overflow-y: auto;
    flex: 1;
    min-height: 0;
  }

  .sig-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    border-radius: var(--radius-md);
    transition: background-color 120ms ease;
    flex-shrink: 0;
  }

  .sig-row:hover {
    background: var(--hover-overlay);
  }

  .sig-time {
    flex-shrink: 0;
    width: 54px;
    font-size: 10px;
    color: var(--text-tertiary);
    font-weight: 500;
  }

  .sig-icon {
    flex-shrink: 0;
    width: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .sig-sym {
    font-size: var(--text-xs);
    font-weight: 700;
    color: var(--text-primary);
    flex-shrink: 0;
    width: 44px;
  }

  .sig-type {
    font-size: 10px;
    color: var(--text-tertiary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
    min-width: 0;
  }

  .sig-str {
    display: flex;
    align-items: center;
    gap: 2px;
    flex-shrink: 0;
  }

  .str-pip {
    width: 3px;
    height: 10px;
    border-radius: 1px;
    display: block;
  }

  .sig-price-col {
    flex-shrink: 0;
    text-align: right;
    min-width: 68px;
  }

  .sig-price {
    display: block;
    font-size: var(--text-xs);
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.2;
  }

  .sig-chg {
    display: block;
    font-size: 10px;
    font-weight: 600;
    line-height: 1.2;
  }

  /* ===================================================================
     SECTOR HEATMAP (right column)
     =================================================================== */
  .sector-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 5px;
    flex: 1;
    min-height: 0;
    align-content: start;
  }

  .sector-tile {
    border-radius: var(--radius-md);
    padding: 8px 10px;
    border: 1px solid;
    display: flex;
    flex-direction: column;
    gap: 2px;
    transition: transform 120ms ease, box-shadow 120ms ease;
  }

  .sector-tile:hover {
    transform: translateY(-1px);
    box-shadow: var(--glow-sm);
  }

  .sector-tile-hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .sector-ticker {
    font-size: var(--text-2xs);
    font-weight: 700;
    color: var(--text-primary);
  }

  .sector-chg {
    font-size: var(--text-xs);
    font-weight: 700;
  }

  .sector-name {
    font-size: 9px;
    color: var(--text-secondary);
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sector-wt {
    font-size: 9px;
    color: var(--text-disabled);
    font-weight: 500;
  }

  .sector-summary {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 24px;
    padding-top: 8px;
    border-top: 1px solid var(--border-subtle);
    flex-shrink: 0;
  }

  .summary-item {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .summary-ct {
    font-size: var(--text-xs);
    font-weight: 700;
  }

  .summary-lbl {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    font-weight: 500;
  }

  /* ===================================================================
     RESPONSIVE
     =================================================================== */
  @media (max-width: 1280px) {
    .kpi-row {
      grid-template-columns: repeat(3, 1fr);
    }

    .skel-kpi-row {
      grid-template-columns: repeat(3, 1fr);
    }
  }

  @media (max-width: 1023px) {
    .main-grid {
      grid-template-columns: 1fr;
    }

    .skel-main-row {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 768px) {
    .dashboard-page {
      padding: 12px;
      gap: 10px;
    }

    .kpi-row,
    .skel-kpi-row {
      grid-template-columns: repeat(2, 1fr);
    }

    .page-header {
      flex-direction: column;
      align-items: flex-start;
      gap: 8px;
    }

    .hdr-date {
      display: none;
    }

    .sector-grid {
      grid-template-columns: repeat(2, 1fr);
    }

    .skel-main-row {
      grid-template-columns: 1fr;
    }
  }
</style>
