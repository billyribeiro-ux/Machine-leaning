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
    if (change > 1.5) return 'text-[var(--bullish-bright)]';
    if (change > 0) return 'text-[var(--bullish)]';
    if (change > -1.5) return 'text-[var(--bearish)]';
    return 'text-[var(--bearish-bright)]';
  }

  function changeBg(change: number): string {
    if (change > 0) return 'bg-[var(--bullish-bg)]';
    return 'bg-[var(--bearish-bg)]';
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
    if (m > 50) return 'text-[var(--bullish-bright)]';
    if (m > 20) return 'text-[var(--bullish)]';
    if (m > -20) return 'text-[var(--text-secondary)]';
    if (m > -50) return 'text-[var(--bearish)]';
    return 'text-[var(--bearish-bright)]';
  }
</script>

<div class="flex flex-col gap-3 {className}">
  <div class="flex items-center justify-between px-1">
    <span class="text-sm font-semibold text-[var(--text-primary)]">Sector Rotation</span>
    <span class="text-2xs text-[var(--text-tertiary)]">{sectors.length} sectors</span>
  </div>

  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
    {#each sortedSectors as sector (sector.name)}
      <div class="panel p-4 flex flex-col gap-3 hover:bg-[var(--hover-overlay)] transition-colors duration-150">
        <!-- Header -->
        <div class="flex items-center justify-between">
          <span class="text-sm font-semibold text-[var(--text-primary)] truncate">{sector.name}</span>
          <span
            class="mono-nums text-sm font-bold px-2 py-0.5 rounded-sm {changeColor(sector.change)} {changeBg(sector.change)}"
          >
            {sector.change > 0 ? '+' : ''}{sector.change.toFixed(2)}%
          </span>
        </div>

        <!-- Relative Strength bar -->
        <div class="flex flex-col gap-1.5">
          <div class="flex items-center justify-between">
            <span class="text-2xs text-[var(--text-tertiary)]">Relative Strength</span>
            <span class="mono-nums text-2xs text-[var(--text-secondary)]">{sector.relativeStrength.toFixed(0)}</span>
          </div>
          <div class="w-full h-2 rounded-full bg-[var(--bg-void)] overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-500"
              style="width: {Math.min(100, Math.max(0, sector.relativeStrength))}%; background-color: {rsBarColor(sector.relativeStrength)};"
            ></div>
          </div>
        </div>

        <!-- Momentum -->
        <div class="flex items-center justify-between">
          <span class="text-2xs text-[var(--text-tertiary)]">Momentum</span>
          <span class="text-2xs font-medium {momentumColor(sector.momentum)}">{momentumLabel(sector.momentum)}</span>
        </div>
      </div>
    {/each}
  </div>

  {#if sectors.length === 0}
    <div class="flex items-center justify-center h-32 text-sm text-[var(--text-tertiary)]">
      No sector data available
    </div>
  {/if}
</div>
