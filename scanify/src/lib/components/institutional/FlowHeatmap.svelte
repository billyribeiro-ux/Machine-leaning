<!--
  FlowHeatmap.svelte
  Simple heatmap grid of institutional flow by sector.
  Green for inflows, red for outflows, intensity by magnitude.
-->
<script lang="ts">
  interface FlowEntry {
    sector: string;
    flow: number;
  }

  interface Props {
    data: FlowEntry[];
    class?: string;
  }

  let {
    data = [],
    class: className = ''
  }: Props = $props();

  let maxAbsFlow = $derived(
    data.length > 0 ? Math.max(...data.map((d) => Math.abs(d.flow)), 1) : 1
  );

  let sortedData = $derived(
    [...data].sort((a, b) => b.flow - a.flow)
  );

  function cellColor(flow: number): string {
    const intensity = Math.min(1, Math.abs(flow) / maxAbsFlow);
    if (flow > 0) {
      const lightness = 0.16 + intensity * 0.20;
      const chroma = intensity * 0.16;
      return `oklch(${lightness} ${chroma} 155)`;
    } else if (flow < 0) {
      const lightness = 0.16 + intensity * 0.18;
      const chroma = intensity * 0.18;
      return `oklch(${lightness} ${chroma} 25)`;
    }
    return 'oklch(0.14 0.02 260)';
  }

  function textColor(flow: number): string {
    const intensity = Math.min(1, Math.abs(flow) / maxAbsFlow);
    if (intensity > 0.5) return 'oklch(0.92 0 0)';
    return 'oklch(0.70 0 0)';
  }

  function formatFlow(val: number): string {
    const sign = val > 0 ? '+' : '';
    if (Math.abs(val) >= 1_000_000_000) return sign + (val / 1_000_000_000).toFixed(1) + 'B';
    if (Math.abs(val) >= 1_000_000) return sign + (val / 1_000_000).toFixed(1) + 'M';
    if (Math.abs(val) >= 1_000) return sign + (val / 1_000).toFixed(0) + 'K';
    return sign + val.toFixed(0);
  }
</script>

<div class="panel heatmap-wrapper {className}">
  <div class="header">
    <span class="header-title">Institutional Flow Heatmap</span>
    <div class="legend">
      <span class="legend-item">
        <span class="legend-swatch legend-inflow"></span> Inflow
      </span>
      <span class="legend-item">
        <span class="legend-swatch legend-outflow"></span> Outflow
      </span>
    </div>
  </div>

  <div class="flow-grid">
    {#each sortedData as entry (entry.sector)}
      <div
        class="flow-cell"
        style="background-color: {cellColor(entry.flow)};"
      >
        <span
          class="cell-sector"
          style="color: {textColor(entry.flow)};"
        >
          {entry.sector}
        </span>
        <span
          class="cell-value mono-nums"
          style="color: {textColor(entry.flow)};"
        >
          {formatFlow(entry.flow)}
        </span>
      </div>
    {/each}
  </div>

  {#if data.length === 0}
    <div class="empty-state">
      No institutional flow data available
    </div>
  {/if}
</div>

<style>
  .heatmap-wrapper {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 16px;
  }

  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .header-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .legend {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .legend-swatch {
    width: 12px;
    height: 12px;
    border-radius: var(--radius-xs);
  }

  .legend-inflow {
    background-color: oklch(0.30 0.14 155);
  }

  .legend-outflow {
    background-color: oklch(0.28 0.14 25);
  }

  .flow-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 6px;
  }

  @media (min-width: 640px) {
    .flow-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
  }

  @media (min-width: 1024px) {
    .flow-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
  }

  .flow-cell {
    position: relative;
    border-radius: var(--radius-md);
    padding: 16px 12px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    transition: all 200ms;
    cursor: default;
  }

  .flow-cell:hover {
    transform: scale(1.02);
  }

  .cell-sector {
    font-size: var(--text-xs);
    font-weight: 600;
    text-align: center;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    width: 100%;
  }

  .cell-value {
    font-size: var(--text-sm);
    font-weight: 700;
  }

  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 128px;
    font-size: var(--text-sm);
    color: var(--text-tertiary);
  }
</style>
