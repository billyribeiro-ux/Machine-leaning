<!--
  InternalsBar.svelte
  Compact horizontal bar showing TICK, TRIN, VIX, and A/D Ratio
  with color-coded values based on market thresholds.
-->
<script lang="ts">
  interface Props {
    tick: number;
    trin: number;
    vix: number;
    advDecRatio: number;
    class?: string;
  }

  let {
    tick,
    trin,
    vix,
    advDecRatio,
    class: className = ''
  }: Props = $props();

  let tickColor = $derived(
    tick > 500
      ? 'text-[var(--bullish-bright)]'
      : tick < -500
        ? 'text-[var(--bearish-bright)]'
        : 'text-[var(--warning-bright)]'
  );

  let trinColor = $derived(
    trin < 0.8
      ? 'text-[var(--bullish-bright)]'
      : trin > 1.2
        ? 'text-[var(--bearish-bright)]'
        : 'text-[var(--text-primary)]'
  );

  let vixColor = $derived(
    vix < 15
      ? 'text-[var(--bullish-bright)]'
      : vix < 20
        ? 'text-[var(--bullish)]'
        : vix < 25
          ? 'text-[var(--warning)]'
          : vix < 30
            ? 'text-[var(--warning-bright)]'
            : vix < 40
              ? 'text-[var(--bearish)]'
              : 'text-[var(--bearish-bright)]'
  );

  let adColor = $derived(
    advDecRatio >= 1.5
      ? 'text-[var(--bullish-bright)]'
      : advDecRatio >= 1.0
        ? 'text-[var(--bullish)]'
        : advDecRatio >= 0.7
          ? 'text-[var(--warning)]'
          : 'text-[var(--bearish-bright)]'
  );

  function formatTick(val: number): string {
    const sign = val > 0 ? '+' : '';
    return `${sign}${val.toFixed(0)}`;
  }
</script>

<div
  class="flex items-center gap-4 px-4 py-2 rounded-lg bg-[var(--bg-surface)] border border-[var(--border-subtle)] overflow-x-auto {className}"
>
  <!-- TICK -->
  <div class="flex items-center gap-2 shrink-0">
    <span class="text-2xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">TICK</span>
    <span class="mono-nums text-sm font-bold {tickColor}">
      {formatTick(tick)}
    </span>
  </div>

  <div class="w-px h-4 bg-[var(--border-subtle)] shrink-0"></div>

  <!-- TRIN -->
  <div class="flex items-center gap-2 shrink-0">
    <span class="text-2xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">TRIN</span>
    <span class="mono-nums text-sm font-bold {trinColor}">
      {trin.toFixed(2)}
    </span>
  </div>

  <div class="w-px h-4 bg-[var(--border-subtle)] shrink-0"></div>

  <!-- VIX -->
  <div class="flex items-center gap-2 shrink-0">
    <span class="text-2xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">VIX</span>
    <span class="mono-nums text-sm font-bold {vixColor}">
      {vix.toFixed(2)}
    </span>
  </div>

  <div class="w-px h-4 bg-[var(--border-subtle)] shrink-0"></div>

  <!-- A/D Ratio -->
  <div class="flex items-center gap-2 shrink-0">
    <span class="text-2xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">A/D</span>
    <span class="mono-nums text-sm font-bold {adColor}">
      {advDecRatio.toFixed(2)}
    </span>
  </div>
</div>
