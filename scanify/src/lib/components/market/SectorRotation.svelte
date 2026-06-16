<!--
  SectorRotation.svelte
  Responsive 3-column grid of sector cards sorted by change.
  Each card shows sector name, color-coded change %, and relative strength bar.
-->
<script lang="ts">
  interface Sector {
    name: string;
    change: number;
    relativeStrength: number;
    momentum: number;
  }

  interface Props {
    sectors: Sector[];
    class?: string;
  }

  let {
    sectors = [],
    class: className = ''
  }: Props = $props();

  let sortedSectors = $derived(
    [...sectors].sort((a, b) => b.change - a.change)
  );

  function changeColor(change: number): string {
    if (change > 1.5) return 'change-strong-bull';
    if (change > 0) return 'change-bull';
    if (change > -1.5) return 'change-bear';
    return 'change-strong-bear';
  }

  function changeBg(change: number): string {
    if (change > 0) return 'change-bg-bull';
    return 'change-bg-bear';
  }

  function rsBarColor(rs: number): string {
    if (rs >= 70) return 'var(--bullish)';
    if (rs >= 50) return 'var(--bullish-dim)';
    if (rs >= 30) return 'var(--warning)';
    return 'var(--bearish)';
  }

  function momentumLabel(m: number): string {
    if (m > 50) return 'Strong';
    if (m > 20) return 'Moderate';
    if (m > -20) return 'Neutral';
    if (m > -50) return 'Weak';
    return 'Very Weak';
  }

  function momentumColor(m: number): string {
    if (m > 50) return 'momentum-strong-bull';
    if (m > 20) return 'momentum-bull';
    if (m > -20) return 'momentum-neutral';
    if (m > -50) return 'momentum-bear';
    return 'momentum-strong-bear';
  }
</script>

<div class="sector-wrapper {className}">
  <div class="header">
    <span class="header-title">Sector Rotation</span>
    <span class="text-2xs header-count">{ sectors.length } sectors</span>
  </div>

  <div class="sector-grid">
    {#each sortedSectors as sector (sector.name)}
      <div class="panel sector-card">
        <!-- Header -->
        <div class="sector-card-header">
          <span class="sector-name">{sector.name}</span>
          <span
            class="mono-nums change-badge {changeColor(sector.change)} {changeBg(sector.change)}"
          >
            {sector.change > 0 ? '+' : ''}{sector.change.toFixed(2)}%
          </span>
        </div>

        <!-- Relative Strength bar -->
        <div class="rs-section">
          <div class="rs-header">
            <span class="text-2xs rs-label">Relative Strength</span>
            <span class="mono-nums text-2xs rs-value">{sector.relativeStrength.toFixed(0)}</span>
          </div>
          <div class="rs-bar-bg">
            <div
              class="rs-bar-fill"
              style="width: {Math.min(100, Math.max(0, sector.relativeStrength))}%; background-color: {rsBarColor(sector.relativeStrength)};"
            ></div>
          </div>
        </div>

        <!-- Momentum -->
        <div class="momentum-row">
          <span class="text-2xs momentum-label">Momentum</span>
          <span class="text-2xs {momentumColor(sector.momentum)}">{momentumLabel(sector.momentum)}</span>
        </div>
      </div>
    {/each}
  </div>

  {#if sectors.length === 0}
    <div class="empty-state">
      No sector data available
    </div>
  {/if}
</div>

<style>
  .sector-wrapper {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-inline: 4px;
  }

  .header-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .header-count {
    color: var(--text-tertiary);
  }

  .sector-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 12px;
  }

  @media (min-width: 640px) {
    .sector-grid {
      grid-template-columns: repeat(2, 1fr);
    }
  }

  @media (min-width: 1024px) {
    .sector-grid {
      grid-template-columns: repeat(3, 1fr);
    }
  }

  .sector-card {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    transition: color 150ms, background-color 150ms;
  }

  .sector-card:hover {
    background: var(--hover-overlay);
  }

  .sector-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .sector-name {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .change-badge {
    font-size: var(--text-sm);
    font-weight: 700;
    padding-inline: 8px;
    padding-block: 2px;
    border-radius: 2px;
  }

  .rs-section {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .rs-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .rs-label {
    color: var(--text-tertiary);
  }

  .rs-value {
    color: var(--text-secondary);
  }

  .rs-bar-bg {
    width: 100%;
    height: 8px;
    border-radius: 9999px;
    background-color: var(--bg-void);
    overflow: hidden;
  }

  .rs-bar-fill {
    height: 100%;
    border-radius: 9999px;
    transition: all 500ms;
  }

  .momentum-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .momentum-label {
    color: var(--text-tertiary);
  }

  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 128px;
    font-size: var(--text-sm);
    color: var(--text-tertiary);
  }

  /* Dynamic change color classes */
  .change-strong-bull {
    color: var(--bullish-bright);
  }

  .change-bull {
    color: var(--bullish);
  }

  .change-bear {
    color: var(--bearish);
  }

  .change-strong-bear {
    color: var(--bearish-bright);
  }

  /* Dynamic change background classes */
  .change-bg-bull {
    background-color: var(--bullish-bg);
  }

  .change-bg-bear {
    background-color: var(--bearish-bg);
  }

  /* Dynamic momentum color classes */
  .momentum-strong-bull {
    color: var(--bullish-bright);
  }

  .momentum-bull {
    color: var(--bullish);
  }

  .momentum-neutral {
    color: var(--text-secondary);
  }

  .momentum-bear {
    color: var(--bearish);
  }

  .momentum-strong-bear {
    color: var(--bearish-bright);
  }
</style>
