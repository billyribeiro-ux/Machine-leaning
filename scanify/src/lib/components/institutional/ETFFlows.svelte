<!--
  ETFFlows.svelte
  Table of ETF fund flows with bar visualization for relative flow.
  Inflows green, outflows red.
-->
<script lang="ts">
  import { formatMarketCap } from '$lib/utils/format';

  interface ETFFlowEntry {
    symbol: string;
    name: string;
    flow: number;
    aum: number;
    flowPercent: number;
  }

  interface Props {
    data: ETFFlowEntry[];
    class?: string;
  }

  let {
    data = [],
    class: className = ''
  }: Props = $props();

  type SortKey = 'symbol' | 'flow' | 'aum' | 'flowPercent';
  let sortBy = $state<SortKey>('flow');
  let sortDir = $state<'asc' | 'desc'>('desc');

  let sorted = $derived.by(() => {
    const copy = [...data];
    copy.sort((a, b) => {
      let cmp = 0;
      switch (sortBy) {
        case 'symbol':
          cmp = a.symbol.localeCompare(b.symbol);
          break;
        case 'flow':
          cmp = a.flow - b.flow;
          break;
        case 'aum':
          cmp = a.aum - b.aum;
          break;
        case 'flowPercent':
          cmp = a.flowPercent - b.flowPercent;
          break;
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return copy;
  });

  let maxAbsFlow = $derived(
    data.length > 0 ? Math.max(...data.map((d) => Math.abs(d.flow)), 1) : 1
  );

  function handleSort(key: SortKey) {
    if (sortBy === key) {
      sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      sortBy = key;
      sortDir = 'desc';
    }
  }

  function sortIndicator(key: SortKey): string {
    if (sortBy !== key) return ' \u25B3';
    return sortDir === 'asc' ? ' \u25B2' : ' \u25BC';
  }

  function flowBarWidth(flow: number): number {
    return (Math.abs(flow) / maxAbsFlow) * 100;
  }
</script>

<div class="panel flex flex-col overflow-hidden {className}">
  <!-- Header -->
  <div class="flex items-center justify-between px-4 py-2.5 border-b border-[var(--border-subtle)]">
    <span class="text-sm font-semibold text-[var(--text-primary)]">ETF Flows</span>
    <span class="text-2xs text-[var(--text-tertiary)]">{data.length} funds</span>
  </div>

  <!-- Table -->
  <div class="flex-1 overflow-auto">
    <table class="w-full min-w-[700px]">
      <thead class="sticky top-0 z-10 bg-[var(--bg-elevated)]">
        <tr class="border-b border-[var(--border-subtle)]">
          <th class="px-3 py-2 text-left">
            <button
              type="button"
              class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
              onclick={() => handleSort('symbol')}
            >
              Symbol{sortIndicator('symbol')}
            </button>
          </th>
          <th class="px-3 py-2 text-left">
            <span class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">Name</span>
          </th>
          <th class="px-3 py-2 text-right">
            <button
              type="button"
              class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
              onclick={() => handleSort('flow')}
            >
              Flow ($){sortIndicator('flow')}
            </button>
          </th>
          <th class="px-3 py-2 text-left w-[140px]">
            <span class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">Flow Bar</span>
          </th>
          <th class="px-3 py-2 text-right">
            <button
              type="button"
              class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
              onclick={() => handleSort('aum')}
            >
              AUM{sortIndicator('aum')}
            </button>
          </th>
          <th class="px-3 py-2 text-right">
            <button
              type="button"
              class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
              onclick={() => handleSort('flowPercent')}
            >
              Flow %{sortIndicator('flowPercent')}
            </button>
          </th>
        </tr>
      </thead>
      <tbody>
        {#each sorted as entry, idx (entry.symbol + idx)}
          {@const isInflow = entry.flow >= 0}
          <tr class="border-b border-[var(--border-subtle)] transition-colors duration-75 hover:bg-[var(--hover-overlay)]">
            <td class="px-3 py-2 text-xs font-semibold text-[var(--text-primary)]">{entry.symbol}</td>
            <td class="px-3 py-2 text-xs text-[var(--text-secondary)] truncate max-w-[180px]">{entry.name}</td>
            <td class="px-3 py-2 mono-nums text-xs text-right font-semibold {isInflow ? 'text-[var(--bullish)]' : 'text-[var(--bearish)]'}">
              {isInflow ? '+' : ''}{formatMarketCap(entry.flow)}
            </td>
            <td class="px-3 py-2">
              <div class="w-full h-3 bg-[var(--bg-void)] rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all duration-300 {isInflow ? 'bg-[var(--bullish-dim)]' : 'bg-[var(--bearish-dim)]'}"
                  style="width: {flowBarWidth(entry.flow)}%;"
                ></div>
              </div>
            </td>
            <td class="px-3 py-2 mono-nums text-xs text-right text-[var(--text-secondary)]">{formatMarketCap(entry.aum)}</td>
            <td class="px-3 py-2 mono-nums text-xs text-right font-semibold {isInflow ? 'text-[var(--bullish)]' : 'text-[var(--bearish)]'}">
              {entry.flowPercent > 0 ? '+' : ''}{entry.flowPercent.toFixed(2)}%
            </td>
          </tr>
        {/each}
      </tbody>
    </table>

    {#if data.length === 0}
      <div class="flex items-center justify-center h-32 text-sm text-[var(--text-tertiary)]">
        No ETF flow data available
      </div>
    {/if}
  </div>
</div>
