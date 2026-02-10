<!--
  ShortInterest.svelte
  Table of short interest data with sortable columns.
  High SI% highlighted in amber/red.
-->
<script lang="ts">
  interface ShortInterestEntry {
    symbol: string;
    shortInterest: number;
    shortPercent: number;
    daysToCover: number;
    change: number;
  }

  interface Props {
    data: ShortInterestEntry[];
    class?: string;
  }

  let {
    data = [],
    class: className = ''
  }: Props = $props();

  type SortKey = 'symbol' | 'shortPercent' | 'daysToCover' | 'change' | 'shortInterest';
  let sortBy = $state<SortKey>('shortPercent');
  let sortDir = $state<'asc' | 'desc'>('desc');

  let sorted = $derived(() => {
    const copy = [...data];
    copy.sort((a, b) => {
      let cmp = 0;
      switch (sortBy) {
        case 'symbol':
          cmp = a.symbol.localeCompare(b.symbol);
          break;
        case 'shortPercent':
          cmp = a.shortPercent - b.shortPercent;
          break;
        case 'daysToCover':
          cmp = a.daysToCover - b.daysToCover;
          break;
        case 'change':
          cmp = a.change - b.change;
          break;
        case 'shortInterest':
          cmp = a.shortInterest - b.shortInterest;
          break;
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return copy;
  });

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

  function siColor(pct: number): string {
    if (pct >= 30) return 'text-[var(--bearish-bright)]';
    if (pct >= 20) return 'text-[var(--bearish)]';
    if (pct >= 10) return 'text-[var(--warning-bright)]';
    return 'text-[var(--text-secondary)]';
  }

  function rowHighlight(pct: number): string {
    if (pct >= 30) return 'bg-[oklch(0.14_0.03_25/0.4)]';
    if (pct >= 20) return 'bg-[oklch(0.13_0.02_85/0.3)]';
    return '';
  }

  function formatSI(val: number): string {
    if (val >= 1_000_000) return (val / 1_000_000).toFixed(2) + 'M';
    if (val >= 1_000) return (val / 1_000).toFixed(0) + 'K';
    return val.toLocaleString();
  }
</script>

<div class="panel flex flex-col overflow-hidden {className}">
  <!-- Header -->
  <div class="flex items-center justify-between px-4 py-2.5 border-b border-[var(--border-subtle)]">
    <span class="text-sm font-semibold text-[var(--text-primary)]">Short Interest</span>
    <span class="text-2xs text-[var(--text-tertiary)]">{data.length} symbols</span>
  </div>

  <!-- Table -->
  <div class="flex-1 overflow-auto">
    <table class="w-full min-w-[560px]">
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
          <th class="px-3 py-2 text-right">
            <button
              type="button"
              class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
              onclick={() => handleSort('shortInterest')}
            >
              Short Interest{sortIndicator('shortInterest')}
            </button>
          </th>
          <th class="px-3 py-2 text-right">
            <button
              type="button"
              class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
              onclick={() => handleSort('shortPercent')}
            >
              SI %{sortIndicator('shortPercent')}
            </button>
          </th>
          <th class="px-3 py-2 text-right">
            <button
              type="button"
              class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
              onclick={() => handleSort('daysToCover')}
            >
              Days to Cover{sortIndicator('daysToCover')}
            </button>
          </th>
          <th class="px-3 py-2 text-right">
            <button
              type="button"
              class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
              onclick={() => handleSort('change')}
            >
              Change{sortIndicator('change')}
            </button>
          </th>
        </tr>
      </thead>
      <tbody>
        {#each sorted() as entry, idx (entry.symbol + idx)}
          <tr
            class="border-b border-[var(--border-subtle)] transition-colors duration-75 hover:bg-[var(--hover-overlay)]
              {rowHighlight(entry.shortPercent)}"
          >
            <td class="px-3 py-2 text-xs font-semibold text-[var(--text-primary)]">{entry.symbol}</td>
            <td class="px-3 py-2 mono-nums text-xs text-right text-[var(--text-secondary)]">{formatSI(entry.shortInterest)}</td>
            <td class="px-3 py-2 mono-nums text-xs text-right font-bold {siColor(entry.shortPercent)}">
              {entry.shortPercent.toFixed(1)}%
            </td>
            <td class="px-3 py-2 mono-nums text-xs text-right text-[var(--text-secondary)]">{entry.daysToCover.toFixed(1)}</td>
            <td class="px-3 py-2 mono-nums text-xs text-right font-semibold {entry.change > 0 ? 'text-[var(--bearish)]' : entry.change < 0 ? 'text-[var(--bullish)]' : 'text-[var(--text-tertiary)]'}">
              {entry.change > 0 ? '+' : ''}{entry.change.toFixed(1)}%
            </td>
          </tr>
        {/each}
      </tbody>
    </table>

    {#if data.length === 0}
      <div class="flex items-center justify-center h-32 text-sm text-[var(--text-tertiary)]">
        No short interest data available
      </div>
    {/if}
  </div>
</div>
