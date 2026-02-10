<!--
  BreadthDashboard.svelte
  Grid of market breadth metric cards: A/D ratio stacked bar,
  new highs/lows count, percent above moving averages as progress bars.
-->
<script lang="ts">
  interface Internals {
    advancers: number;
    decliners: number;
    newHighs: number;
    newLows: number;
    percentAbove200ma: number;
    percentAbove50ma: number;
  }

  interface Props {
    internals: Internals;
    class?: string;
  }

  let {
    internals,
    class: className = ''
  }: Props = $props();

  let adTotal = $derived(internals.advancers + internals.decliners);
  let adRatio = $derived(adTotal > 0 ? internals.advancers / internals.decliners : 1);
  let advPercent = $derived(adTotal > 0 ? (internals.advancers / adTotal) * 100 : 50);
  let decPercent = $derived(100 - advPercent);

  let nhNlDiff = $derived(internals.newHighs - internals.newLows);

  function formatRatio(val: number): string {
    if (!Number.isFinite(val)) return '--';
    return val.toFixed(2);
  }
</script>

<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 {className}">
  <!-- Advance / Decline Ratio -->
  <div class="panel p-4 flex flex-col gap-3">
    <div class="flex items-center justify-between">
      <span class="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">A/D Ratio</span>
      <span class="mono-nums text-lg font-bold {adRatio >= 1 ? 'text-[var(--bullish-bright)]' : 'text-[var(--bearish-bright)]'}">
        {formatRatio(adRatio)}
      </span>
    </div>
    <!-- Stacked bar -->
    <div class="flex h-5 rounded-sm overflow-hidden bg-[var(--bg-void)]">
      <div
        class="h-full bg-[var(--bullish)] transition-all duration-300"
        style="width: {advPercent}%;"
      ></div>
      <div
        class="h-full bg-[var(--bearish)] transition-all duration-300"
        style="width: {decPercent}%;"
      ></div>
    </div>
    <div class="flex justify-between text-2xs mono-nums">
      <span class="text-[var(--bullish)]">{internals.advancers.toLocaleString()} adv</span>
      <span class="text-[var(--bearish)]">{internals.decliners.toLocaleString()} dec</span>
    </div>
  </div>

  <!-- New Highs / New Lows -->
  <div class="panel p-4 flex flex-col gap-3">
    <div class="flex items-center justify-between">
      <span class="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">NH / NL</span>
      <span class="mono-nums text-lg font-bold {nhNlDiff >= 0 ? 'text-[var(--bullish-bright)]' : 'text-[var(--bearish-bright)]'}">
        {nhNlDiff >= 0 ? '+' : ''}{nhNlDiff}
      </span>
    </div>
    <div class="flex items-end gap-4">
      <div class="flex-1 text-center">
        <div class="mono-nums text-2xl font-bold text-[var(--bullish)]">{internals.newHighs}</div>
        <div class="text-2xs text-[var(--text-tertiary)] mt-1">New Highs</div>
      </div>
      <div class="w-px h-10 bg-[var(--border-subtle)]"></div>
      <div class="flex-1 text-center">
        <div class="mono-nums text-2xl font-bold text-[var(--bearish)]">{internals.newLows}</div>
        <div class="text-2xs text-[var(--text-tertiary)] mt-1">New Lows</div>
      </div>
    </div>
    <!-- Gauge bar -->
    {@const nhTotal = internals.newHighs + internals.newLows}
    {@const nhPct = nhTotal > 0 ? (internals.newHighs / nhTotal) * 100 : 50}
    <div class="flex h-2 rounded-full overflow-hidden bg-[var(--bg-void)]">
      <div class="h-full bg-[var(--bullish-dim)] transition-all duration-300" style="width: {nhPct}%;"></div>
      <div class="h-full bg-[var(--bearish-dim)] transition-all duration-300" style="width: {100 - nhPct}%;"></div>
    </div>
  </div>

  <!-- % Above 200-day MA -->
  <div class="panel p-4 flex flex-col gap-3">
    <div class="flex items-center justify-between">
      <span class="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">% Above 200 MA</span>
      <span class="mono-nums text-lg font-bold text-[var(--text-primary)]">
        {internals.percentAbove200ma.toFixed(1)}%
      </span>
    </div>
    <!-- Progress bar -->
    <div class="w-full h-3 rounded-full bg-[var(--bg-void)] overflow-hidden">
      <div
        class="h-full rounded-full transition-all duration-500"
        style="width: {Math.min(100, Math.max(0, internals.percentAbove200ma))}%;
               background-color: {internals.percentAbove200ma >= 60
                 ? 'var(--bullish)'
                 : internals.percentAbove200ma >= 40
                   ? 'var(--warning)'
                   : 'var(--bearish)'};"
      ></div>
    </div>
    <!-- Scale labels -->
    <div class="flex justify-between text-2xs text-[var(--text-tertiary)]">
      <span>0%</span>
      <span>50%</span>
      <span>100%</span>
    </div>
  </div>

  <!-- % Above 50-day MA -->
  <div class="panel p-4 flex flex-col gap-3">
    <div class="flex items-center justify-between">
      <span class="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">% Above 50 MA</span>
      <span class="mono-nums text-lg font-bold text-[var(--text-primary)]">
        {internals.percentAbove50ma.toFixed(1)}%
      </span>
    </div>
    <!-- Progress bar -->
    <div class="w-full h-3 rounded-full bg-[var(--bg-void)] overflow-hidden">
      <div
        class="h-full rounded-full transition-all duration-500"
        style="width: {Math.min(100, Math.max(0, internals.percentAbove50ma))}%;
               background-color: {internals.percentAbove50ma >= 60
                 ? 'var(--bullish)'
                 : internals.percentAbove50ma >= 40
                   ? 'var(--warning)'
                   : 'var(--bearish)'};"
      ></div>
    </div>
    <div class="flex justify-between text-2xs text-[var(--text-tertiary)]">
      <span>0%</span>
      <span>50%</span>
      <span>100%</span>
    </div>
  </div>

  <!-- Breadth Summary -->
  <div class="panel p-4 flex flex-col gap-3 sm:col-span-2 lg:col-span-2">
    <span class="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">Breadth Summary</span>
    <div class="grid grid-cols-4 gap-3">
      {@const metrics = [
        { label: 'A/D Ratio', value: formatRatio(adRatio), bullish: adRatio >= 1 },
        { label: 'NH-NL', value: `${nhNlDiff >= 0 ? '+' : ''}${nhNlDiff}`, bullish: nhNlDiff >= 0 },
        { label: '>200MA', value: `${internals.percentAbove200ma.toFixed(0)}%`, bullish: internals.percentAbove200ma >= 50 },
        { label: '>50MA', value: `${internals.percentAbove50ma.toFixed(0)}%`, bullish: internals.percentAbove50ma >= 50 }
      ]}
      {#each metrics as m}
        <div class="text-center">
          <div class="mono-nums text-base font-bold {m.bullish ? 'text-[var(--bullish)]' : 'text-[var(--bearish)]'}">
            {m.value}
          </div>
          <div class="text-2xs text-[var(--text-tertiary)] mt-0.5">{m.label}</div>
        </div>
      {/each}
    </div>
  </div>
</div>
