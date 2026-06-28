<script lang="ts">
  import { onMount } from 'svelte';
  import ExportToolbar from '$lib/components/ui/ExportToolbar.svelte';
  import { fetchOptionsData } from '$lib/api';

  // ── Types ──

  interface GEXEntry {
    strike: number;
    callGex: number;
    putGex: number;
    netGex: number;
  }

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

  interface GreekValues {
    delta: number;
    gamma: number;
    theta: number;
    vega: number;
    rho: number;
  }

  // ── Constants ──

  const API_BASE = 'http://localhost:8000';
  const CURRENT_PRICE = 5512.40;
  const SPOT_SYMBOL = 'SPX';

  // ── Connection state ──

  let loading = $state(false);
  let connected = $state(false);
  let needsApiKey = $state(false);

  // ── Data generators ──

  function generateGEXProfile(): GEXEntry[] {
    const entries: GEXEntry[] = [];
    const baseStrike = 5400;
    const step = 15;

    for (let i = 0; i < 15; i++) {
      const strike = baseStrike + i * step;
      const dist = (strike - CURRENT_PRICE) / 100;

      const callBase = Math.max(0.06, 1.9 - Math.abs(dist - 0.3) * 1.2) * (0.82 + Math.sin(strike * 0.07) * 0.18);
      const putBase = Math.max(0.05, 1.6 - Math.abs(dist + 0.4) * 1.0) * (0.80 + Math.sin(strike * 0.05) * 0.15);

      const callGex = +(callBase * 0.85).toFixed(3);
      const putGex = +(-putBase * 0.72).toFixed(3);

      entries.push({
        strike,
        callGex,
        putGex,
        netGex: +(callGex + putGex).toFixed(3),
      });
    }
    return entries;
  }

  function generateFlowData(): FlowItem[] {
    const configs: Array<{
      sym: string; type: 'call' | 'put'; side: 'buy' | 'sell';
      strike: number; size: number; premium: number;
      isSweep: boolean; isUnusual: boolean; minutesAgo: number; expDays: number;
    }> = [
      { sym: 'SPX',  type: 'call', side: 'buy',  strike: 5520, size: 2500, premium: 4_850_000, isSweep: true,  isUnusual: true,  minutesAgo: 1,  expDays: 1 },
      { sym: 'SPY',  type: 'call', side: 'buy',  strike: 553,  size: 4200, premium: 2_340_000, isSweep: true,  isUnusual: true,  minutesAgo: 2,  expDays: 3 },
      { sym: 'QQQ',  type: 'put',  side: 'buy',  strike: 475,  size: 1800, premium: 920_000,   isSweep: false, isUnusual: true,  minutesAgo: 3,  expDays: 7 },
      { sym: 'NVDA', type: 'call', side: 'buy',  strike: 145,  size: 3100, premium: 1_150_000, isSweep: true,  isUnusual: false, minutesAgo: 4,  expDays: 1 },
      { sym: 'SPX',  type: 'put',  side: 'sell', strike: 5480, size: 1200, premium: 3_445_000, isSweep: false, isUnusual: false, minutesAgo: 5,  expDays: 14 },
      { sym: 'AAPL', type: 'call', side: 'buy',  strike: 215,  size: 890,  premium: 312_000,   isSweep: false, isUnusual: true,  minutesAgo: 6,  expDays: 30 },
      { sym: 'TSLA', type: 'call', side: 'buy',  strike: 360,  size: 650,  premium: 487_000,   isSweep: false, isUnusual: false, minutesAgo: 8,  expDays: 7 },
      { sym: 'META', type: 'put',  side: 'buy',  strike: 505,  size: 2200, premium: 1_680_000, isSweep: true,  isUnusual: true,  minutesAgo: 9,  expDays: 3 },
      { sym: 'MSFT', type: 'call', side: 'sell', strike: 455,  size: 400,  premium: 198_000,   isSweep: false, isUnusual: false, minutesAgo: 11, expDays: 1 },
      { sym: 'SPX',  type: 'call', side: 'buy',  strike: 5550, size: 5000, premium: 6_100_000, isSweep: true,  isUnusual: true,  minutesAgo: 13, expDays: 7 },
      { sym: 'AMD',  type: 'put',  side: 'buy',  strike: 165,  size: 1500, premium: 567_000,   isSweep: false, isUnusual: false, minutesAgo: 15, expDays: 14 },
      { sym: 'AMZN', type: 'call', side: 'buy',  strike: 215,  size: 780,  premium: 245_000,   isSweep: false, isUnusual: false, minutesAgo: 18, expDays: 30 },
      { sym: 'SPY',  type: 'put',  side: 'sell', strike: 548,  size: 320,  premium: 78_000,    isSweep: false, isUnusual: false, minutesAgo: 22, expDays: 3 },
      { sym: 'SPX',  type: 'put',  side: 'buy',  strike: 5450, size: 1750, premium: 2_825_000, isSweep: true,  isUnusual: true,  minutesAgo: 27, expDays: 1 },
    ];

    const now = Date.now();
    return configs.map((c, i) => ({
      id: `flow-${i}-${c.sym}`,
      symbol: c.sym,
      timestamp: new Date(now - c.minutesAgo * 60_000).toISOString(),
      type: c.type,
      strike: c.strike,
      expiration: new Date(now + c.expDays * 86_400_000)
        .toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      side: c.side,
      size: c.size,
      premium: c.premium,
      isUnusual: c.isUnusual,
      isSweep: c.isSweep,
    }));
  }

  function generateGreeks(): GreekValues {
    return {
      delta: 0.2341,
      gamma: 0.0387,
      theta: -0.4218,
      vega: 0.2764,
      rho: 0.0512,
    };
  }

  // ── Reactive state ──

  let gexProfile = $state<GEXEntry[]>(generateGEXProfile());
  let flowItems = $state<FlowItem[]>(generateFlowData());
  let greeks = $state<GreekValues>(generateGreeks());

  // ── Derived KPIs ──

  let totalCallGex = $derived.by(() =>
    gexProfile.reduce((sum, e) => sum + e.callGex, 0)
  );

  let totalPutGex = $derived.by(() =>
    gexProfile.reduce((sum, e) => sum + e.putGex, 0)
  );

  let totalGex = $derived(+(totalCallGex + totalPutGex).toFixed(2));

  let netGex = $derived(totalGex);

  let dealerPositioning = $derived.by((): 'Long Gamma' | 'Short Gamma' | 'Neutral' => {
    if (netGex > 1.5) return 'Long Gamma';
    if (netGex < -0.5) return 'Short Gamma';
    return 'Neutral';
  });

  let keyStrike = $derived.by(() => {
    if (gexProfile.length === 0) return 0;
    let maxIdx = 0;
    let maxAbs = Math.abs(gexProfile[0]!.netGex);
    for (let i = 1; i < gexProfile.length; i++) {
      const abs = Math.abs(gexProfile[i]!.netGex);
      if (abs > maxAbs) { maxAbs = abs; maxIdx = i; }
    }
    return gexProfile[maxIdx]!.strike;
  });

  // ── GEX bar scaling ──

  let maxAbsGex = $derived.by(() => {
    let max = 0.001;
    for (const e of gexProfile) {
      if (Math.abs(e.callGex) > max) max = Math.abs(e.callGex);
      if (Math.abs(e.putGex) > max) max = Math.abs(e.putGex);
    }
    return max;
  });

  // ── Greeks metadata ──

  interface GreekMeta {
    key: keyof GreekValues;
    label: string;
    symbol: string;
    trend: 'up' | 'down' | 'flat';
    hue: number;
  }

  let greeksMeta = $derived.by((): GreekMeta[] => [
    { key: 'delta', label: 'Delta', symbol: 'Δ', trend: greeks.delta > 0.2 ? 'up' : 'flat', hue: 155 },
    { key: 'gamma', label: 'Gamma', symbol: 'Γ', trend: greeks.gamma > 0.03 ? 'up' : 'flat', hue: 250 },
    { key: 'theta', label: 'Theta', symbol: 'Θ', trend: 'down', hue: 25 },
    { key: 'vega',  label: 'Vega',  symbol: 'ν', trend: greeks.vega > 0.25 ? 'up' : 'flat', hue: 290 },
    { key: 'rho',   label: 'Rho',   symbol: 'ρ', trend: 'flat', hue: 85 },
  ]);

  // ── API health + data fetch ──

  onMount(async () => {
    try {
      const health = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(5000) });
      connected = health.ok;
    } catch {
      connected = false;
    }

    try {
      const result = await fetchOptionsData();
      if (result === null) {
        needsApiKey = true;
      } else {
        if (result.chainSummary && Array.isArray(result.chainSummary)) {
          flowItems = result.chainSummary as FlowItem[];
        }
        if (result.gexLevels && Array.isArray(result.gexLevels)) {
          gexProfile = (result.gexLevels as { strike: number; gex: number }[]).map((g) => ({
            strike: g.strike,
            callGex: g.gex > 0 ? g.gex : 0,
            putGex: g.gex < 0 ? g.gex : 0,
            netGex: g.gex,
          }));
        }
      }
    } catch {
      // Simulated data already loaded
    } finally {
      loading = false;
    }
  });

  // ── Helpers ──

  function fmtBillions(v: number): string {
    return (v >= 0 ? '+' : '') + v.toFixed(2) + 'B';
  }

  function fmtPremium(v: number): string {
    if (v >= 1_000_000) return '$' + (v / 1_000_000).toFixed(1) + 'M';
    if (v >= 1_000) return '$' + (v / 1_000).toFixed(0) + 'K';
    return '$' + v.toFixed(0);
  }

  function fmtTime(ts: string | number): string {
    const d = new Date(ts);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  }

  function barPct(gex: number): number {
    return Math.min(100, (Math.abs(gex) / maxAbsGex) * 100);
  }

  function gaugePosition(): number {
    if (dealerPositioning === 'Long Gamma') return 78;
    if (dealerPositioning === 'Short Gamma') return 22;
    return 50;
  }
</script>

<svelte:head>
  <title>Options Analytics - Scanify</title>
</svelte:head>

<div class="page-root">

  <!-- ═══════════ PAGE HEADER ═══════════ -->
  <header class="page-header">
    <div class="header-left">
      <h1 class="page-title">Options Analytics</h1>
      <span class="header-tag">{SPOT_SYMBOL}</span>
      <span class="header-price">{CURRENT_PRICE.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
      <span class="live-dot"></span>
    </div>
    <div class="header-right">
      <a href="/options/flow" class="flow-link">View Full Flow &rarr;</a>
      <ExportToolbar source="options-flow" />
    </div>
  </header>

  {#if loading}
    <div class="loading-state">
      <div class="spinner-box">
        <div class="spinner"></div>
      </div>
      <p class="loading-label">Loading options analytics...</p>
    </div>
  {:else if !connected && needsApiKey}
    <div class="loading-state">
      <p class="loading-label">
        Using simulated data &mdash; configure a provider in
        <a href="/settings" style="color: var(--accent);">Settings</a>
        for live feed.
      </p>
    </div>
  {/if}

  {#if !loading}
    <div class="page-scroll">

      <!-- ═══════════ GEX KPI STRIP ═══════════ -->
      <section class="kpi-strip">
        <div class="kpi-card">
          <span class="kpi-label">Total GEX</span>
          <span class="kpi-value" style="color: {totalGex >= 0 ? 'var(--bullish-bright)' : 'var(--bearish-bright)'};">
            {fmtBillions(totalGex)}
          </span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Call GEX</span>
          <span class="kpi-value kpi-bullish">+{totalCallGex.toFixed(2)}B</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Put GEX</span>
          <span class="kpi-value kpi-bearish">{totalPutGex.toFixed(2)}B</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Net GEX</span>
          <span class="kpi-value" style="color: {netGex >= 0 ? 'var(--bullish-bright)' : 'var(--bearish-bright)'};">
            {fmtBillions(netGex)}
          </span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Dealer Position</span>
          <span class="kpi-value kpi-dealer"
            class:kpi-val-long={dealerPositioning === 'Long Gamma'}
            class:kpi-val-short={dealerPositioning === 'Short Gamma'}
            class:kpi-val-neutral={dealerPositioning === 'Neutral'}
          >
            {dealerPositioning}
          </span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Key Strike</span>
          <span class="kpi-value kpi-accent">{keyStrike.toLocaleString()}</span>
        </div>
      </section>

      <!-- ═══════════ MAIN GRID ═══════════ -->
      <div class="main-grid">

        <!-- ── GEX Profile ── -->
        <section class="glass-panel gex-panel">
          <div class="panel-header">
            <h2 class="panel-title">GEX Profile</h2>
            <span class="panel-subtitle">{SPOT_SYMBOL} Gamma Exposure by Strike</span>
          </div>
          <div class="gex-chart">
            {#each gexProfile as entry (entry.strike)}
              {@const isNearSpot = Math.abs(entry.strike - CURRENT_PRICE) < 10}
              <div class="gex-row" class:gex-row-spot={isNearSpot}>
                <span class="gex-strike" class:gex-strike-spot={isNearSpot}>
                  {entry.strike.toLocaleString()}
                </span>
                <div class="gex-bars">
                  <!-- Put bar: grows leftward from center -->
                  <div class="gex-track gex-track-left">
                    <div class="gex-bar gex-bar-put" style="width: {barPct(entry.putGex)}%;"></div>
                  </div>
                  <div class="gex-center-line"></div>
                  <!-- Call bar: grows rightward from center -->
                  <div class="gex-track gex-track-right">
                    <div class="gex-bar gex-bar-call" style="width: {barPct(entry.callGex)}%;"></div>
                  </div>
                </div>
                <span class="gex-net" style="color: {entry.netGex >= 0 ? 'var(--bullish)' : 'var(--bearish)'};">
                  {entry.netGex >= 0 ? '+' : ''}{entry.netGex.toFixed(2)}
                </span>
              </div>
            {/each}
            <div class="gex-legend">
              <span class="legend-item"><span class="legend-swatch legend-put"></span>Put GEX</span>
              <span class="legend-item"><span class="legend-swatch legend-call"></span>Call GEX</span>
              <span class="legend-item legend-spot-label">
                <span class="legend-spot-marker"></span>Spot {CURRENT_PRICE.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </span>
            </div>
          </div>
        </section>

        <!-- ── Right column: Greeks + Dealer ── -->
        <div class="right-stack">

          <!-- Greeks Summary -->
          <section class="glass-panel greeks-panel">
            <div class="panel-header">
              <h2 class="panel-title">Aggregate Greeks</h2>
            </div>
            <div class="greeks-grid">
              {#each greeksMeta as gm (gm.key)}
                <div class="greek-card" style="--g-hue: {gm.hue};">
                  <div class="greek-top-row">
                    <span class="greek-sym">{gm.symbol}</span>
                    <span class="greek-trend"
                      class:trend-up={gm.trend === 'up'}
                      class:trend-down={gm.trend === 'down'}
                    >
                      {#if gm.trend === 'up'}
                        <svg width="10" height="10" viewBox="0 0 10 10"><path d="M5 1L9 7H1z" fill="currentColor"/></svg>
                      {:else if gm.trend === 'down'}
                        <svg width="10" height="10" viewBox="0 0 10 10"><path d="M5 9L1 3h8z" fill="currentColor"/></svg>
                      {:else}
                        <svg width="10" height="10" viewBox="0 0 10 10"><rect x="1" y="4" width="8" height="2" rx="1" fill="currentColor"/></svg>
                      {/if}
                    </span>
                  </div>
                  <span class="greek-val">{greeks[gm.key].toFixed(4)}</span>
                  <span class="greek-lbl">{gm.label}</span>
                </div>
              {/each}
            </div>
          </section>

          <!-- Dealer Positioning Indicator -->
          <section class="glass-panel dealer-panel">
            <div class="panel-header">
              <h2 class="panel-title">Dealer Positioning</h2>
            </div>
            <div class="dealer-body">
              <!-- Gauge -->
              <div class="gauge-wrap">
                <div class="gauge-track">
                  <div class="gauge-fill"
                    class:gauge-long={dealerPositioning === 'Long Gamma'}
                    class:gauge-short={dealerPositioning === 'Short Gamma'}
                    class:gauge-neutral={dealerPositioning === 'Neutral'}
                    style="width: {gaugePosition()}%;"
                  ></div>
                  <div class="gauge-marker" style="left: {gaugePosition()}%;"></div>
                </div>
                <div class="gauge-ends">
                  <span style="color: var(--bearish);">Short</span>
                  <span style="color: var(--text-tertiary);">Neutral</span>
                  <span style="color: var(--bullish);">Long</span>
                </div>
              </div>
              <!-- Status badge -->
              <div class="dealer-badge"
                class:dealer-badge-long={dealerPositioning === 'Long Gamma'}
                class:dealer-badge-short={dealerPositioning === 'Short Gamma'}
                class:dealer-badge-neutral={dealerPositioning === 'Neutral'}
              >
                {dealerPositioning}
              </div>
              <!-- Explanation -->
              <p class="dealer-explanation">
                {#if dealerPositioning === 'Long Gamma'}
                  Dealers are long gamma. They sell into rallies and buy dips, acting as a volatility dampener. Expect mean-reversion and compression toward the key strike at {keyStrike.toLocaleString()}.
                {:else if dealerPositioning === 'Short Gamma'}
                  Dealers are short gamma. They must buy rallies and sell dips, amplifying moves. Expect increased volatility and potential for outsized directional swings.
                {:else}
                  Dealers are near gamma-neutral. Market is balanced between stabilizing and destabilizing flows. Watch for a shift as positioning changes around {keyStrike.toLocaleString()}.
                {/if}
              </p>
            </div>
          </section>

        </div>
      </div>

      <!-- ═══════════ OPTIONS FLOW FEED ═══════════ -->
      <section class="glass-panel flow-panel">
        <div class="panel-header">
          <div class="panel-header-group">
            <h2 class="panel-title">Options Flow</h2>
            <span class="panel-count">{flowItems.length} notable trades</span>
          </div>
          <a href="/options/flow" class="panel-link">View Full Flow &rarr;</a>
        </div>
        <div class="flow-scroll">
          <table class="flow-table">
            <thead>
              <tr>
                <th class="th-l">Time</th>
                <th class="th-l">Symbol</th>
                <th class="th-c">C/P</th>
                <th class="th-r">Strike</th>
                <th class="th-l">Expiry</th>
                <th class="th-r">Size</th>
                <th class="th-r">Premium</th>
                <th class="th-c">Side</th>
                <th class="th-c">Flags</th>
              </tr>
            </thead>
            <tbody>
              {#each flowItems as item (item.id)}
                <tr class="flow-row" class:flow-row-call={item.type === 'call'} class:flow-row-put={item.type === 'put'}>
                  <td class="td-mono td-dim">{fmtTime(item.timestamp)}</td>
                  <td class="td-symbol">{item.symbol}</td>
                  <td class="td-center">
                    <span class="badge-type" class:badge-call={item.type === 'call'} class:badge-put={item.type === 'put'}>
                      {item.type === 'call' ? 'C' : 'P'}
                    </span>
                  </td>
                  <td class="td-mono td-right">{item.strike.toLocaleString()}</td>
                  <td class="td-dim">{item.expiration}</td>
                  <td class="td-mono td-right">{item.size.toLocaleString()}</td>
                  <td class="td-mono td-right td-premium">{fmtPremium(item.premium)}</td>
                  <td class="td-center">
                    <span class="badge-side" class:badge-buy={item.side === 'buy'} class:badge-sell={item.side === 'sell'}>
                      {item.side === 'buy' ? 'BUY' : 'SELL'}
                    </span>
                  </td>
                  <td class="td-center td-flags">
                    {#if item.isSweep}
                      <span class="badge-flag badge-sweep">SWP</span>
                    {/if}
                    {#if item.isUnusual}
                      <span class="badge-flag badge-unusual">UNU</span>
                    {/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </section>

    </div>
  {/if}
</div>

<style>
  /* ══════════════════════════════════════════════════
     Page Root & Scroll
     ══════════════════════════════════════════════════ */

  .page-root {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }

  .page-scroll {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 16px 20px 36px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  /* ══════════════════════════════════════════════════
     Page Header
     ══════════════════════════════════════════════════ */

  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 20px;
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
    background: oklch(0.11 0.02 260 / 0.88);
    backdrop-filter: blur(10px);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .page-title {
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.01em;
  }

  .header-tag {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--accent-bright);
    background: var(--accent-bg);
    border: 1px solid var(--accent-dim);
    border-radius: var(--radius-sm);
    padding: 2px 8px;
  }

  .header-price {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }

  .live-dot {
    width: 6px;
    height: 6px;
    border-radius: var(--radius-full);
    background: var(--bullish-bright);
    box-shadow: 0 0 6px oklch(0.78 0.18 155 / 0.6);
    animation: pulse-dot 2s ease-in-out infinite;
  }

  @keyframes pulse-dot {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.35; }
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .flow-link {
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--accent);
    text-decoration: none;
    transition: color 150ms;
  }

  .flow-link:hover {
    color: var(--accent-bright);
  }

  /* ══════════════════════════════════════════════════
     KPI Strip
     ══════════════════════════════════════════════════ */

  .kpi-strip {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 1px;
    background: oklch(0.22 0.02 260 / 0.3);
    border-radius: var(--radius-lg);
    overflow: hidden;
    flex-shrink: 0;
  }

  .kpi-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    padding: 14px 8px;
    background: oklch(0.13 0.02 260 / 0.65);
    backdrop-filter: blur(16px);
    transition: background 150ms;
  }

  .kpi-card:hover {
    background: oklch(0.16 0.02 260 / 0.70);
  }

  .kpi-label {
    font-size: var(--text-2xs);
    font-weight: 500;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .kpi-value {
    font-family: var(--font-mono);
    font-size: var(--text-base);
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: var(--text-primary);
  }

  .kpi-bullish  { color: var(--bullish-bright); }
  .kpi-bearish  { color: var(--bearish-bright); }
  .kpi-accent   { color: var(--accent-bright); }

  .kpi-dealer {
    font-family: var(--font-sans, inherit);
    font-size: var(--text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .kpi-val-long    { color: var(--bullish-bright); }
  .kpi-val-short   { color: var(--bearish-bright); }
  .kpi-val-neutral { color: var(--text-secondary); }

  /* ══════════════════════════════════════════════════
     Glass Panel
     ══════════════════════════════════════════════════ */

  .glass-panel {
    background: oklch(0.14 0.02 260 / 0.7);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-subtle);
  }

  .panel-header-group {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .panel-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
    letter-spacing: -0.01em;
  }

  .panel-subtitle {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
  }

  .panel-count {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    font-variant-numeric: tabular-nums;
  }

  .panel-link {
    font-size: var(--text-2xs);
    font-weight: 500;
    color: var(--accent);
    text-decoration: none;
    transition: color 150ms;
  }

  .panel-link:hover {
    color: var(--accent-bright);
  }

  /* ══════════════════════════════════════════════════
     Main Grid (GEX + Right Stack)
     ══════════════════════════════════════════════════ */

  .main-grid {
    display: grid;
    grid-template-columns: 1fr 360px;
    gap: 16px;
    min-height: 0;
  }

  .right-stack {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  /* ══════════════════════════════════════════════════
     GEX Profile Chart (inline SVG bars)
     ══════════════════════════════════════════════════ */

  .gex-chart {
    padding: 12px 16px 10px;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .gex-row {
    display: grid;
    grid-template-columns: 56px 1fr 56px;
    align-items: center;
    gap: 8px;
    height: 24px;
    border-radius: 2px;
    padding: 0 4px;
    transition: background 100ms;
  }

  .gex-row:hover {
    background: oklch(0.20 0.02 260 / 0.4);
  }

  .gex-row-spot {
    background: oklch(0.18 0.04 260 / 0.50);
    border-left: 2px solid var(--accent);
  }

  .gex-strike {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: 500;
    color: var(--text-secondary);
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .gex-strike-spot {
    color: var(--accent-bright);
    font-weight: 700;
  }

  .gex-bars {
    display: flex;
    align-items: center;
    height: 14px;
    position: relative;
  }

  .gex-track {
    flex: 1;
    height: 100%;
    position: relative;
  }

  .gex-track-left {
    display: flex;
    justify-content: flex-end;
  }

  .gex-track-right {
    display: flex;
    justify-content: flex-start;
  }

  .gex-bar {
    height: 100%;
    border-radius: 2px;
    transition: width 400ms cubic-bezier(0.16, 1, 0.3, 1);
    min-width: 1px;
  }

  .gex-bar-call {
    background: oklch(0.55 0.15 155);
    box-shadow: 0 0 6px oklch(0.55 0.15 155 / 0.25);
  }

  .gex-bar-put {
    background: oklch(0.55 0.15 25);
    box-shadow: 0 0 6px oklch(0.55 0.15 25 / 0.25);
  }

  .gex-center-line {
    width: 1px;
    height: 100%;
    background: oklch(0.35 0.02 260);
    flex-shrink: 0;
  }

  .gex-net {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: 500;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .gex-legend {
    display: flex;
    gap: 18px;
    justify-content: center;
    align-items: center;
    padding-top: 10px;
    border-top: 1px solid oklch(0.22 0.02 260 / 0.4);
    margin-top: 6px;
  }

  .legend-item {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    display: flex;
    align-items: center;
    gap: 5px;
  }

  .legend-swatch {
    width: 10px;
    height: 6px;
    border-radius: 1px;
  }

  .legend-call { background: oklch(0.55 0.15 155); }
  .legend-put  { background: oklch(0.55 0.15 25); }

  .legend-spot-label {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    display: flex;
    align-items: center;
    gap: 5px;
    margin-left: 6px;
  }

  .legend-spot-marker {
    width: 8px;
    height: 2px;
    background: var(--accent);
    border-radius: 1px;
  }

  /* ══════════════════════════════════════════════════
     Greeks Panel
     ══════════════════════════════════════════════════ */

  .greeks-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 1px;
    background: oklch(0.22 0.02 260 / 0.3);
  }

  .greek-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    padding: 12px 4px;
    background: oklch(0.14 0.02 260 / 0.9);
    transition: background 150ms;
  }

  .greek-card:hover {
    background: oklch(0.17 0.02 260 / 0.9);
  }

  .greek-top-row {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .greek-sym {
    font-size: var(--text-base);
    font-weight: 700;
    color: oklch(0.65 0.12 var(--g-hue));
  }

  .greek-trend {
    display: flex;
    align-items: center;
    color: var(--text-tertiary);
  }

  .trend-up   { color: var(--bullish-bright); }
  .trend-down { color: var(--bearish-bright); }

  .greek-val {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }

  .greek-lbl {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    font-weight: 500;
  }

  /* ══════════════════════════════════════════════════
     Dealer Positioning Panel
     ══════════════════════════════════════════════════ */

  .dealer-body {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .gauge-wrap {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .gauge-track {
    position: relative;
    height: 8px;
    background: oklch(0.20 0.02 260);
    border-radius: var(--radius-full);
    overflow: visible;
  }

  .gauge-fill {
    height: 100%;
    border-radius: var(--radius-full);
    transition: width 500ms cubic-bezier(0.16, 1, 0.3, 1);
  }

  .gauge-long {
    background: linear-gradient(90deg, oklch(0.28 0.06 155), oklch(0.55 0.15 155));
  }

  .gauge-short {
    background: linear-gradient(90deg, oklch(0.55 0.15 25), oklch(0.28 0.06 25));
  }

  .gauge-neutral {
    background: linear-gradient(90deg, oklch(0.28 0.03 260), oklch(0.42 0.05 260));
  }

  .gauge-marker {
    position: absolute;
    top: -3px;
    width: 14px;
    height: 14px;
    background: var(--text-primary);
    border-radius: var(--radius-full);
    border: 2px solid oklch(0.14 0.02 260);
    transform: translateX(-50%);
    box-shadow: 0 0 8px oklch(0.95 0.01 260 / 0.3);
    transition: left 500ms cubic-bezier(0.16, 1, 0.3, 1);
  }

  .gauge-ends {
    display: flex;
    justify-content: space-between;
    font-size: var(--text-2xs);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .dealer-badge {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    font-weight: 700;
    text-align: center;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 6px;
    border-radius: var(--radius-sm);
  }

  .dealer-badge-long {
    color: var(--bullish-bright);
    background: var(--bullish-bg);
    border: 1px solid oklch(0.45 0.12 155 / 0.3);
  }

  .dealer-badge-short {
    color: var(--bearish-bright);
    background: var(--bearish-bg);
    border: 1px solid oklch(0.42 0.12 25 / 0.3);
  }

  .dealer-badge-neutral {
    color: var(--text-secondary);
    background: oklch(0.18 0.02 260 / 0.6);
    border: 1px solid oklch(0.30 0.02 260 / 0.4);
  }

  .dealer-explanation {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    line-height: 1.65;
    padding: 0 2px;
  }

  /* ══════════════════════════════════════════════════
     Options Flow Table
     ══════════════════════════════════════════════════ */

  .flow-scroll {
    overflow-x: auto;
  }

  .flow-table {
    width: 100%;
    font-size: var(--text-xs);
    border-collapse: collapse;
  }

  .flow-table thead {
    position: sticky;
    top: 0;
    z-index: 2;
  }

  .flow-table th {
    padding: 8px 10px;
    font-weight: 500;
    color: var(--text-tertiary);
    background: oklch(0.16 0.02 260 / 0.95);
    border-bottom: 1px solid var(--border-subtle);
    white-space: nowrap;
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .th-l { text-align: left; }
  .th-r { text-align: right; }
  .th-c { text-align: center; }

  .flow-table th:first-child { padding-left: 16px; }
  .flow-table td:first-child { padding-left: 16px; }

  .flow-row {
    border-bottom: 1px solid oklch(0.20 0.02 260 / 0.4);
    transition: background 100ms;
  }

  .flow-row:hover {
    background: oklch(0.18 0.02 260 / 0.6);
  }

  .flow-row-call {
    background: oklch(0.13 0.02 155 / 0.15);
  }

  .flow-row-put {
    background: oklch(0.13 0.02 25 / 0.15);
  }

  .flow-row-call:hover {
    background: oklch(0.15 0.03 155 / 0.25);
  }

  .flow-row-put:hover {
    background: oklch(0.15 0.03 25 / 0.25);
  }

  .flow-table td {
    padding: 7px 10px;
    white-space: nowrap;
    color: var(--text-secondary);
  }

  .td-mono {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
  }

  .td-symbol {
    font-family: var(--font-mono);
    font-weight: 700;
    color: var(--text-primary);
  }

  .td-dim {
    color: var(--text-tertiary);
  }

  .td-right {
    text-align: right;
  }

  .td-center {
    text-align: center;
  }

  .td-premium {
    color: var(--text-primary);
    font-weight: 600;
  }

  .td-flags {
    display: flex;
    gap: 4px;
    justify-content: center;
    align-items: center;
  }

  /* ══════════════════════════════════════════════════
     Badges (Type, Side, Flags)
     ══════════════════════════════════════════════════ */

  .badge-type {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 18px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 700;
    font-family: var(--font-mono);
  }

  .badge-call {
    color: var(--bullish-bright);
    background: var(--bullish-bg);
    border: 1px solid oklch(0.45 0.12 155 / 0.3);
  }

  .badge-put {
    color: var(--bearish-bright);
    background: var(--bearish-bg);
    border: 1px solid oklch(0.42 0.12 25 / 0.3);
  }

  .badge-side {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.04em;
    font-family: var(--font-mono);
  }

  .badge-buy {
    color: var(--bullish-bright);
    background: oklch(0.22 0.06 155 / 0.4);
  }

  .badge-sell {
    color: var(--bearish-bright);
    background: oklch(0.22 0.06 25 / 0.4);
  }

  .badge-flag {
    display: inline-flex;
    align-items: center;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 8px;
    font-weight: 700;
    letter-spacing: 0.06em;
    font-family: var(--font-mono);
  }

  .badge-sweep {
    color: var(--accent-bright);
    background: var(--accent-bg);
    border: 1px solid oklch(0.40 0.10 280 / 0.3);
  }

  .badge-unusual {
    color: oklch(0.82 0.15 85);
    background: oklch(0.22 0.06 85 / 0.4);
    border: 1px solid oklch(0.40 0.10 85 / 0.3);
  }

  /* ══════════════════════════════════════════════════
     Loading / Status State
     ══════════════════════════════════════════════════ */

  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 48px 20px;
    gap: 16px;
  }

  .spinner-box {
    width: 52px;
    height: 52px;
    border-radius: var(--radius-xl);
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-elevated);
    border: 1px solid var(--border-subtle);
  }

  .spinner {
    width: 22px;
    height: 22px;
    border: 2px solid var(--border-subtle);
    border-top-color: var(--accent);
    border-radius: var(--radius-full);
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .loading-label {
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--text-secondary);
  }

  /* ══════════════════════════════════════════════════
     Responsive
     ══════════════════════════════════════════════════ */

  @media (max-width: 1100px) {
    .main-grid {
      grid-template-columns: 1fr;
    }

    .right-stack {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
  }

  @media (max-width: 768px) {
    .kpi-strip {
      grid-template-columns: repeat(3, 1fr);
    }

    .right-stack {
      grid-template-columns: 1fr;
    }

    .page-header {
      flex-direction: column;
      gap: 8px;
      align-items: flex-start;
    }

    .header-right {
      width: 100%;
      justify-content: space-between;
    }

    .greeks-grid {
      grid-template-columns: repeat(3, 1fr);
    }
  }

  @media (max-width: 480px) {
    .kpi-strip {
      grid-template-columns: repeat(2, 1fr);
    }

    .greeks-grid {
      grid-template-columns: repeat(2, 1fr);
    }

    .page-scroll {
      padding: 12px 12px 24px;
    }
  }
</style>
