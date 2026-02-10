<!--
  CorrelationView.svelte
  Wrapper around CorrelationMatrix chart with symbol selector,
  timeframe toggle, title and description.
-->
<script lang="ts">
  import CorrelationMatrix from '$lib/components/charts/CorrelationMatrix.svelte';

  interface Props {
    symbols: string[];
    data: number[][];
    class?: string;
  }

  let {
    symbols = [],
    data = [],
    class: className = ''
  }: Props = $props();

  const TIMEFRAMES = ['1W', '1M', '3M', '6M', '1Y'] as const;
  type Timeframe = typeof TIMEFRAMES[number];

  let selectedTimeframe = $state<Timeframe>('1M');
  let searchQuery = $state('');

  let filteredIndices = $derived(() => {
    if (!searchQuery.trim()) return symbols.map((_, i) => i);
    const q = searchQuery.toUpperCase().trim();
    return symbols
      .map((s, i) => ({ s, i }))
      .filter(({ s }) => s.toUpperCase().includes(q))
      .map(({ i }) => i);
  });

  let filteredSymbols = $derived(filteredIndices().map((i) => symbols[i]));

  let filteredData = $derived(() => {
    const indices = filteredIndices();
    return indices.map((r) => indices.map((c) => data[r]?.[c] ?? (r === c ? 1 : 0)));
  });
</script>

<div class="panel flex flex-col gap-4 p-4 {className}">
  <!-- Header -->
  <div class="flex flex-col gap-1">
    <h3 class="text-sm font-semibold text-[var(--text-primary)]">Correlation Matrix</h3>
    <p class="text-2xs text-[var(--text-tertiary)]">
      Cross-asset correlation analysis. Values range from -1 (inverse) to +1 (perfectly correlated).
    </p>
  </div>

  <!-- Controls -->
  <div class="flex items-center gap-3 flex-wrap">
    <!-- Symbol search -->
    <div class="relative flex-1 min-w-[160px] max-w-[240px]">
      <input
        type="text"
        placeholder="Filter symbols..."
        bind:value={searchQuery}
        class="w-full h-8 pl-3 pr-8 text-xs bg-[var(--bg-void)] border border-[var(--border-subtle)]
               rounded-md text-[var(--text-primary)] placeholder:text-[var(--text-disabled)]
               focus:outline-none focus:border-[var(--accent-dim)]
               transition-colors duration-150"
      />
      {#if searchQuery}
        <button
          type="button"
          class="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
          onclick={() => (searchQuery = '')}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          </svg>
        </button>
      {/if}
    </div>

    <!-- Timeframe toggle -->
    <div class="flex items-center bg-[var(--bg-void)] rounded-md border border-[var(--border-subtle)] p-0.5">
      {#each TIMEFRAMES as tf}
        <button
          type="button"
          class="px-2.5 py-1 text-2xs font-medium rounded-sm transition-colors duration-150
            {selectedTimeframe === tf
              ? 'bg-[var(--accent-bg)] text-[var(--accent-bright)]'
              : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'}"
          onclick={() => (selectedTimeframe = tf)}
        >
          {tf}
        </button>
      {/each}
    </div>

    <span class="text-2xs text-[var(--text-tertiary)] ml-auto">
      {filteredSymbols.length} of {symbols.length} symbols
    </span>
  </div>

  <!-- Matrix -->
  <div class="overflow-auto">
    {#if filteredSymbols.length > 0}
      <CorrelationMatrix
        symbols={filteredSymbols}
        correlations={filteredData()}
        height={Math.min(500, Math.max(250, filteredSymbols.length * 40 + 80))}
      />
    {:else}
      <div class="flex items-center justify-center h-48 text-sm text-[var(--text-tertiary)]">
        No matching symbols found
      </div>
    {/if}
  </div>
</div>
