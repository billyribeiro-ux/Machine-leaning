<script lang="ts">
  import BreadthDashboard from '$components/market/BreadthDashboard.svelte';
  import InternalsBar from '$components/market/InternalsBar.svelte';
  import SentimentGauge from '$components/market/SentimentGauge.svelte';
  import SectorRotation from '$components/market/SectorRotation.svelte';

  const breadthData = {
    advancers: 1850,
    decliners: 1320,
    newHighs: 45,
    newLows: 12,
    percentAbove200ma: 62,
    percentAbove50ma: 54,
  };

  const sectorData = [
    { name: 'Technology',       change: 1.82,  relativeStrength: 78, momentum: 65 },
    { name: 'Healthcare',       change: -0.45, relativeStrength: 42, momentum: -15 },
    { name: 'Financials',       change: 0.92,  relativeStrength: 62, momentum: 35 },
    { name: 'Energy',           change: 1.35,  relativeStrength: 71, momentum: 55 },
    { name: 'Consumer Disc.',   change: -1.12, relativeStrength: 35, momentum: -40 },
    { name: 'Industrials',      change: 0.68,  relativeStrength: 58, momentum: 25 },
    { name: 'Communication',    change: 0.24,  relativeStrength: 50, momentum: 10 },
    { name: 'Utilities',        change: -0.15, relativeStrength: 38, momentum: -8 },
    { name: 'Consumer Staples', change: 0.32,  relativeStrength: 45, momentum: 5 },
    { name: 'Materials',        change: 0.78,  relativeStrength: 55, momentum: 30 },
    { name: 'Real Estate',      change: -0.62, relativeStrength: 32, momentum: -25 },
  ];
</script>

<svelte:head>
  <title>Market - Scanify</title>
</svelte:head>

<div class="flex flex-col h-full overflow-auto">
  <!-- Header -->
  <div class="flex items-center justify-between px-5 py-3 shrink-0" style="border-bottom: 1px solid var(--border-subtle);">
    <h1 class="text-lg font-bold" style="color: var(--text-primary);">Market Overview</h1>
    <span class="text-xs font-mono" style="color: var(--text-tertiary);">
      {new Date().toLocaleTimeString('en-US', { hour12: false })}
    </span>
  </div>

  <div class="p-5 space-y-5">
    <!-- 2x2 Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">

      <!-- Breadth Dashboard -->
      <div class="panel p-5 space-y-3">
        <h2 class="text-xs font-semibold uppercase tracking-wider" style="color: var(--text-tertiary);">Market Breadth</h2>
        <BreadthDashboard internals={breadthData} />
      </div>

      <!-- Internals Bar -->
      <div class="panel p-5 space-y-3">
        <h2 class="text-xs font-semibold uppercase tracking-wider" style="color: var(--text-tertiary);">Market Internals</h2>
        <InternalsBar tick={456} trin={0.87} vix={15.2} advDecRatio={1.40} />
        <!-- Supplementary metric cards -->
        <div class="grid grid-cols-2 gap-3 mt-3">
          <div class="rounded-lg p-3 text-center" style="background: var(--bg-base); border: 1px solid var(--border-subtle);">
            <div class="text-[10px] uppercase tracking-wider" style="color: var(--text-tertiary);">Advancers</div>
            <div class="text-lg font-bold font-mono" style="color: var(--bullish);">1,850</div>
          </div>
          <div class="rounded-lg p-3 text-center" style="background: var(--bg-base); border: 1px solid var(--border-subtle);">
            <div class="text-[10px] uppercase tracking-wider" style="color: var(--text-tertiary);">Decliners</div>
            <div class="text-lg font-bold font-mono" style="color: var(--bearish);">1,320</div>
          </div>
        </div>
      </div>

      <!-- Sentiment Gauge -->
      <div class="panel p-5 flex flex-col items-center justify-center">
        <SentimentGauge value={35} label="Market Sentiment" />
      </div>

      <!-- Sector Rotation -->
      <div class="panel p-5">
        <SectorRotation sectors={sectorData} />
      </div>

    </div>
  </div>
</div>
