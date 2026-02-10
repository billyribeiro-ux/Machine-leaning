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

<div class="panel flex flex-col gap-3 p-4 {className}">
  <div class="flex items-center justify-between">
    <span class="text-sm font-semibold text-[var(--text-primary)]">Institutional Flow Heatmap</span>
    <div class="flex items-center gap-2 text-2xs text-[var(--text-tertiary)]">
      <span class="flex items-center gap-1">
        <span class="w-3 h-3 rounded-xs" style="background-color: oklch(0.30 0.14 155);"></span> Inflow
      </span>
      <span class="flex items-center gap-1">
        <span class="w-3 h-3 rounded-xs" style="background-color: oklch(0.28 0.14 25);"></span> Outflow
      </span>
    </div>
  </div>

  <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-1.5">
    {#each sortedData as entry (entry.sector)}
      <div
        class="relative rounded-md px-3 py-4 flex flex-col items-center justify-center gap-1 transition-all duration-200 hover:scale-[1.02] cursor-default"
        style="background-color: {cellColor(entry.flow)};"
      >
        <span
          class="text-xs font-semibold text-center truncate w-full"
          style="color: {textColor(entry.flow)};"
        >
          {entry.sector}
        </span>
        <span
          class="mono-nums text-sm font-bold"
          style="color: {textColor(entry.flow)};"
        >
          {formatFlow(entry.flow)}
        </span>
      </div>
    {/each}
  </div>

  {#if data.length === 0}
    <div class="flex items-center justify-center h-32 text-sm text-[var(--text-tertiary)]">
      No institutional flow data available
    </div>
  {/if}
</div>
