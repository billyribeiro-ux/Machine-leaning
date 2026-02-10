<script lang="ts">
  import InternalsBar from '$components/market/InternalsBar.svelte';

  const indices = [
    { symbol: 'SPY', price: 502.34, change: 2.25, changePercent: 0.45 },
    { symbol: 'QQQ', price: 435.12, change: -1.02, changePercent: -0.23 },
    { symbol: 'IWM', price: 198.45, change: 0.24, changePercent: 0.12 },
    { symbol: 'DIA', price: 389.67, change: 1.45, changePercent: 0.37 },
  ];

  const topSignals = [
    { symbol: 'NVDA', direction: 'bullish' as const, name: 'Momentum Breakout', strength: 5, price: 875.30 },
    { symbol: 'TSLA', direction: 'bearish' as const, name: 'Volume Divergence', strength: 4, price: 245.10 },
    { symbol: 'AMD', direction: 'bullish' as const, name: 'Unusual Options', strength: 4, price: 165.40 },
    { symbol: 'META', direction: 'bullish' as const, name: 'Institutional Flow', strength: 3, price: 505.80 },
    { symbol: 'AMZN', direction: 'neutral' as const, name: 'Range Compression', strength: 3, price: 185.60 },
  ];

  const sectors = [
    { name: 'Technology', change: 1.2 },
    { name: 'Healthcare', change: -0.3 },
    { name: 'Financials', change: 0.8 },
    { name: 'Energy', change: -0.5 },
    { name: 'Consumer Disc.', change: 0.4 },
    { name: 'Industrials', change: 0.2 },
  ];

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

  function dirBg(dir: string): string {
    if (dir === 'bullish') return 'var(--bullish-bg)';
    if (dir === 'bearish') return 'var(--bearish-bg)';
    return 'var(--neutral-bg)';
  }
</script>

<svelte:head>
  <title>Dashboard - Scanify</title>
</svelte:head>

<div class="flex flex-col h-full overflow-auto p-5 gap-5">
  <!-- Page header -->
  <div class="flex items-center justify-between shrink-0">
    <h1 class="text-xl font-bold" style="color: var(--text-primary);">Dashboard</h1>
    <span class="text-xs font-mono" style="color: var(--text-tertiary);">
      {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric', year: 'numeric' })}
    </span>
  </div>

  <!-- Grid layout -->
  <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">

    <!-- Market Status panel - spans 2 cols -->
    <div class="lg:col-span-2 panel p-5 space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold" style="color: var(--text-primary);">Market Status</h2>
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full" style="background: var(--bullish);"></div>
          <span class="text-xs font-medium" style="color: var(--bullish);">Regular Hours</span>
        </div>
      </div>

      <!-- Indices row -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        {#each indices as idx (idx.symbol)}
          <div class="rounded-lg p-3 space-y-1" style="background: var(--bg-base); border: 1px solid var(--border-subtle);">
            <span class="text-xs font-bold font-mono" style="color: var(--text-primary);">{idx.symbol}</span>
            <div class="flex items-baseline gap-2">
              <span class="text-lg font-bold font-mono" style="color: var(--text-primary);">
                {idx.price.toFixed(2)}
              </span>
              <span class="text-xs font-mono font-semibold" style="color: {changeColor(idx.changePercent)};">
                {idx.changePercent >= 0 ? '+' : ''}{idx.changePercent.toFixed(2)}%
              </span>
            </div>
          </div>
        {/each}
      </div>
    </div>

    <!-- Internals panel -->
    <div class="panel p-5 space-y-4">
      <h2 class="text-sm font-semibold" style="color: var(--text-primary);">Market Internals</h2>
      <InternalsBar tick={456} trin={0.87} vix={15.2} advDecRatio={1.40} />
    </div>

    <!-- Top Signals panel - spans 2 cols -->
    <div class="lg:col-span-2 panel p-5 space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold" style="color: var(--text-primary);">Top Signals</h2>
        <a href="/scanner" class="text-xs font-medium transition-colors" style="color: var(--accent);">View all</a>
      </div>
      <div class="space-y-2">
        {#each topSignals as signal (signal.symbol)}
          <div
            class="flex items-center gap-3 rounded-lg px-4 py-3 transition-colors"
            style="background: var(--bg-base); border: 1px solid var(--border-subtle);"
          >
            <!-- Direction dot -->
            <div class="w-2.5 h-2.5 rounded-full shrink-0" style="background: {dirColor(signal.direction)};"></div>

            <!-- Symbol + name -->
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-sm font-bold font-mono" style="color: var(--text-primary);">{signal.symbol}</span>
                <span class="text-[11px]" style="color: var(--text-tertiary);">{signal.name}</span>
              </div>
            </div>

            <!-- Strength dots -->
            <div class="flex items-center gap-0.5">
              {#each Array(5) as _, si}
                <div
                  class="h-1.5 w-2.5 rounded-full"
                  style="background: {si < signal.strength ? dirColor(signal.direction) : 'var(--bg-overlay)'};"
                ></div>
              {/each}
            </div>

            <!-- Price -->
            <div class="text-right shrink-0">
              <div class="text-sm font-mono font-bold" style="color: var(--text-primary);">${signal.price.toFixed(2)}</div>
            </div>
          </div>
        {/each}
      </div>
    </div>

    <!-- Sector Performance panel -->
    <div class="panel p-5 space-y-4">
      <h2 class="text-sm font-semibold" style="color: var(--text-primary);">Sector Performance</h2>
      <div class="space-y-2">
        {#each sectors as sector (sector.name)}
          <div class="flex items-center justify-between rounded-lg px-3 py-2" style="background: var(--bg-base); border: 1px solid var(--border-subtle);">
            <span class="text-xs font-medium" style="color: var(--text-primary);">{sector.name}</span>
            <span class="text-xs font-mono font-bold" style="color: {changeColor(sector.change)};">
              {sector.change >= 0 ? '+' : ''}{sector.change.toFixed(1)}%
            </span>
          </div>
        {/each}
      </div>
    </div>
  </div>
</div>
