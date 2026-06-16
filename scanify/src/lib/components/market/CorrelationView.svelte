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

  let filteredIndices = $derived.by(() => {
    if (!searchQuery.trim()) return symbols.map((_, i) => i);
    const q = searchQuery.toUpperCase().trim();
    return symbols
      .map((s, i) => ({ s, i }))
      .filter(({ s }) => s.toUpperCase().includes(q))
      .map(({ i }) => i);
  });

  let filteredSymbols = $derived(filteredIndices.map((i) => symbols[i]));

  let filteredData = $derived.by(() => {
    const indices = filteredIndices;
    return indices.map((r) => indices.map((c) => data[r]?.[c] ?? (r === c ? 1 : 0)));
  });
</script>

<div class="panel correlation-view {className}">
  <!-- Header -->
  <div class="view-header">
    <h3 class="view-title">Correlation Matrix</h3>
    <p class="view-description">
      Cross-asset correlation analysis. Values range from -1 (inverse) to +1 (perfectly correlated).
    </p>
  </div>

  <!-- Controls -->
  <div class="controls-row">
    <!-- Symbol search -->
    <div class="search-wrapper">
      <input
        type="text"
        placeholder="Filter symbols..."
        bind:value={searchQuery}
        class="search-input"
      />
      {#if searchQuery}
        <button
          type="button"
          class="search-clear"
          onclick={() => (searchQuery = '')}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          </svg>
        </button>
      {/if}
    </div>

    <!-- Timeframe toggle -->
    <div class="timeframe-group">
      {#each TIMEFRAMES as tf}
        <button
          type="button"
          class="tf-button {selectedTimeframe === tf ? 'tf-active' : ''}"
          onclick={() => (selectedTimeframe = tf)}
        >
          {tf}
        </button>
      {/each}
    </div>

    <span class="symbol-count">
      {filteredSymbols.length} of {symbols.length} symbols
    </span>
  </div>

  <!-- Matrix -->
  <div class="matrix-container">
    {#if filteredSymbols.length > 0}
      <CorrelationMatrix
        symbols={filteredSymbols}
        correlations={filteredData}
        height={Math.min(500, Math.max(250, filteredSymbols.length * 40 + 80))}
      />
    {:else}
      <div class="empty-state">
        No matching symbols found
      </div>
    {/if}
  </div>
</div>

<style>
  .correlation-view {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 16px;
  }

  .view-header {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .view-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .view-description {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
  }

  .controls-row {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }

  .search-wrapper {
    position: relative;
    flex: 1;
    min-width: 160px;
    max-width: 240px;
  }

  .search-input {
    width: 100%;
    height: 32px;
    padding-left: 12px;
    padding-right: 32px;
    font-size: var(--text-xs);
    background-color: var(--bg-void);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-DEFAULT, 6px);
    color: var(--text-primary);
    transition: border-color 150ms;
  }

  .search-input::placeholder {
    color: var(--text-disabled);
  }

  .search-input:focus {
    outline: none;
    border-color: var(--accent-dim);
  }

  .search-clear {
    position: absolute;
    right: 8px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-tertiary);
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    display: flex;
    align-items: center;
  }

  .search-clear:hover {
    color: var(--text-secondary);
  }

  .timeframe-group {
    display: flex;
    align-items: center;
    background-color: var(--bg-void);
    border-radius: var(--radius-DEFAULT, 6px);
    border: 1px solid var(--border-subtle);
    padding: 2px;
  }

  .tf-button {
    padding-inline: 10px;
    padding-block: 4px;
    font-size: var(--text-2xs);
    font-weight: 500;
    border-radius: var(--radius-sm);
    transition: color 150ms, background-color 150ms;
    color: var(--text-tertiary);
    background: none;
    border: none;
    cursor: pointer;
  }

  .tf-button:hover {
    color: var(--text-secondary);
  }

  .tf-active {
    background-color: var(--accent-bg);
    color: var(--accent-bright);
  }

  .symbol-count {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    margin-left: auto;
  }

  .matrix-container {
    overflow: auto;
  }

  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 192px;
    font-size: var(--text-sm);
    color: var(--text-tertiary);
  }
</style>
