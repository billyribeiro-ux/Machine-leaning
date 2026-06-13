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
      ? 'var(--bullish-bright)'
      : tick < -500
        ? 'var(--bearish-bright)'
        : 'var(--warning-bright)'
  );

  let trinColor = $derived(
    trin < 0.8
      ? 'var(--bullish-bright)'
      : trin > 1.2
        ? 'var(--bearish-bright)'
        : 'var(--text-primary)'
  );

  let vixColor = $derived(
    vix < 15
      ? 'var(--bullish-bright)'
      : vix < 20
        ? 'var(--bullish)'
        : vix < 25
          ? 'var(--warning)'
          : vix < 30
            ? 'var(--warning-bright)'
            : vix < 40
              ? 'var(--bearish)'
              : 'var(--bearish-bright)'
  );

  let adColor = $derived(
    advDecRatio >= 1.5
      ? 'var(--bullish-bright)'
      : advDecRatio >= 1.0
        ? 'var(--bullish)'
        : advDecRatio >= 0.7
          ? 'var(--warning)'
          : 'var(--bearish-bright)'
  );

  function formatTick(val: number): string {
    const sign = val > 0 ? '+' : '';
    return `${sign}${val.toFixed(0)}`;
  }
</script>

<div class="internals-bar {className}">
  <!-- TICK -->
  <div class="metric-group">
    <span class="metric-label">TICK</span>
    <span class="mono-nums metric-value" style="color: {tickColor};">
      {formatTick(tick)}
    </span>
  </div>

  <div class="divider"></div>

  <!-- TRIN -->
  <div class="metric-group">
    <span class="metric-label">TRIN</span>
    <span class="mono-nums metric-value" style="color: {trinColor};">
      {trin.toFixed(2)}
    </span>
  </div>

  <div class="divider"></div>

  <!-- VIX -->
  <div class="metric-group">
    <span class="metric-label">VIX</span>
    <span class="mono-nums metric-value" style="color: {vixColor};">
      {vix.toFixed(2)}
    </span>
  </div>

  <div class="divider"></div>

  <!-- A/D Ratio -->
  <div class="metric-group">
    <span class="metric-label">A/D</span>
    <span class="mono-nums metric-value" style="color: {adColor};">
      {advDecRatio.toFixed(2)}
    </span>
  </div>
</div>

<style>
  .internals-bar {
    display: flex;
    align-items: center;
    gap: 16px;
    padding-inline: 16px;
    padding-block: 8px;
    border-radius: var(--radius-lg);
    background-color: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    overflow-x: auto;
  }

  .metric-group {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }

  .metric-label {
    font-size: var(--text-2xs);
    font-weight: 500;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .metric-value {
    font-size: var(--text-sm);
    font-weight: 700;
  }

  .divider {
    width: 1px;
    height: 16px;
    background-color: var(--border-subtle);
    flex-shrink: 0;
  }
</style>
