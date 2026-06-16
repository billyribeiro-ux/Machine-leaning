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

<div class="dashboard-grid {className}">
  <!-- Advance / Decline Ratio -->
  <div class="panel card">
    <div class="card-header">
      <span class="card-label">A/D Ratio</span>
      <span
        class="mono-nums card-value"
        style="color: {adRatio >= 1 ? 'var(--bullish-bright)' : 'var(--bearish-bright)'}"
      >
        {formatRatio(adRatio)}
      </span>
    </div>
    <!-- Stacked bar -->
    <div class="stacked-bar">
      <div
        class="bar-fill"
        style="width: {advPercent}%; background-color: var(--bullish);"
      ></div>
      <div
        class="bar-fill"
        style="width: {decPercent}%; background-color: var(--bearish);"
      ></div>
    </div>
    <div class="bar-legend text-2xs mono-nums">
      <span style="color: var(--bullish)">{internals.advancers.toLocaleString()} adv</span>
      <span style="color: var(--bearish)">{internals.decliners.toLocaleString()} dec</span>
    </div>
  </div>

  <!-- New Highs / New Lows -->
  <div class="panel card">
    <div class="card-header">
      <span class="card-label">NH / NL</span>
      <span
        class="mono-nums card-value"
        style="color: {nhNlDiff >= 0 ? 'var(--bullish-bright)' : 'var(--bearish-bright)'}"
      >
        {nhNlDiff >= 0 ? '+' : ''}{nhNlDiff}
      </span>
    </div>
    <div class="nhnl-cols">
      <div class="nhnl-value">
        <div class="mono-nums nhnl-number" style="color: var(--bullish)">{internals.newHighs}</div>
        <div class="text-2xs nhnl-label">New Highs</div>
      </div>
      <div class="divider"></div>
      <div class="nhnl-value">
        <div class="mono-nums nhnl-number" style="color: var(--bearish)">{internals.newLows}</div>
        <div class="text-2xs nhnl-label">New Lows</div>
      </div>
    </div>
    <!-- Gauge bar -->
    {#if true}
      {@const nhTotal = internals.newHighs + internals.newLows}
      {@const nhPct = nhTotal > 0 ? (internals.newHighs / nhTotal) * 100 : 50}
      <div class="gauge-bar">
        <div class="bar-fill" style="width: {nhPct}%; background-color: var(--bullish-dim);"></div>
        <div class="bar-fill" style="width: {100 - nhPct}%; background-color: var(--bearish-dim);"></div>
      </div>
    {/if}
  </div>

  <!-- % Above 200-day MA -->
  <div class="panel card">
    <div class="card-header">
      <span class="card-label">% Above 200 MA</span>
      <span class="mono-nums card-value" style="color: var(--text-primary)">
        {internals.percentAbove200ma.toFixed(1)}%
      </span>
    </div>
    <!-- Progress bar -->
    <div class="progress-bar">
      <div
        class="progress-fill"
        style="width: {Math.min(100, Math.max(0, internals.percentAbove200ma))}%;
               background-color: {internals.percentAbove200ma >= 60
                 ? 'var(--bullish)'
                 : internals.percentAbove200ma >= 40
                   ? 'var(--warning)'
                   : 'var(--bearish)'};"
      ></div>
    </div>
    <!-- Scale labels -->
    <div class="scale-labels text-2xs">
      <span>0%</span>
      <span>50%</span>
      <span>100%</span>
    </div>
  </div>

  <!-- % Above 50-day MA -->
  <div class="panel card">
    <div class="card-header">
      <span class="card-label">% Above 50 MA</span>
      <span class="mono-nums card-value" style="color: var(--text-primary)">
        {internals.percentAbove50ma.toFixed(1)}%
      </span>
    </div>
    <!-- Progress bar -->
    <div class="progress-bar">
      <div
        class="progress-fill"
        style="width: {Math.min(100, Math.max(0, internals.percentAbove50ma))}%;
               background-color: {internals.percentAbove50ma >= 60
                 ? 'var(--bullish)'
                 : internals.percentAbove50ma >= 40
                   ? 'var(--warning)'
                   : 'var(--bearish)'};"
      ></div>
    </div>
    <div class="scale-labels text-2xs">
      <span>0%</span>
      <span>50%</span>
      <span>100%</span>
    </div>
  </div>

  <!-- Breadth Summary -->
  <div class="panel card summary-card">
    <span class="card-label">Breadth Summary</span>
    <div class="summary-grid">
      {#each [
        { label: 'A/D Ratio', value: formatRatio(adRatio), bullish: adRatio >= 1 },
        { label: 'NH-NL', value: `${nhNlDiff >= 0 ? '+' : ''}${nhNlDiff}`, bullish: nhNlDiff >= 0 },
        { label: '>200MA', value: `${internals.percentAbove200ma.toFixed(0)}%`, bullish: internals.percentAbove200ma >= 50 },
        { label: '>50MA', value: `${internals.percentAbove50ma.toFixed(0)}%`, bullish: internals.percentAbove50ma >= 50 }
      ] as m}
        <div class="summary-item">
          <div
            class="mono-nums summary-value"
            style="color: {m.bullish ? 'var(--bullish)' : 'var(--bearish)'}"
          >
            {m.value}
          </div>
          <div class="text-2xs summary-label">{m.label}</div>
        </div>
      {/each}
    </div>
  </div>
</div>

<style>
  .dashboard-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .card {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .card-label {
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .card-value {
    font-size: 1.125rem;
    font-weight: 700;
  }

  /* A/D Ratio stacked bar */
  .stacked-bar {
    display: flex;
    height: 20px;
    border-radius: 2px;
    overflow: hidden;
    background-color: var(--bg-void);
  }

  .bar-fill {
    height: 100%;
    transition: all 300ms;
  }

  .bar-legend {
    display: flex;
    justify-content: space-between;
  }

  /* New Highs / New Lows */
  .nhnl-cols {
    display: flex;
    align-items: flex-end;
    gap: 16px;
  }

  .nhnl-value {
    flex: 1;
    text-align: center;
  }

  .nhnl-number {
    font-size: 1.5rem;
    font-weight: 700;
  }

  .nhnl-label {
    color: var(--text-tertiary);
    margin-top: 4px;
  }

  .divider {
    width: 1px;
    height: 40px;
    background-color: var(--border-subtle);
  }

  /* Gauge bar (NH/NL) */
  .gauge-bar {
    display: flex;
    height: 8px;
    border-radius: 9999px;
    overflow: hidden;
    background-color: var(--bg-void);
  }

  /* Progress bars (MA%) */
  .progress-bar {
    width: 100%;
    height: 12px;
    border-radius: 9999px;
    background-color: var(--bg-void);
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    border-radius: 9999px;
    transition: all 500ms;
  }

  .scale-labels {
    display: flex;
    justify-content: space-between;
    color: var(--text-tertiary);
  }

  /* Breadth Summary card */
  .summary-card {
    /* responsive span handled below */
  }

  .summary-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
  }

  .summary-item {
    text-align: center;
  }

  .summary-value {
    font-size: 1rem;
    font-weight: 700;
  }

  .summary-label {
    color: var(--text-tertiary);
    margin-top: 2px;
  }

  /* Responsive breakpoints */
  @media (min-width: 640px) {
    .dashboard-grid {
      grid-template-columns: repeat(2, 1fr);
    }

    .summary-card {
      grid-column: span 2;
    }
  }

  @media (min-width: 1024px) {
    .dashboard-grid {
      grid-template-columns: repeat(3, 1fr);
    }

    .summary-card {
      grid-column: span 2;
    }
  }
</style>
