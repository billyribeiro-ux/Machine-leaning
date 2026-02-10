<!--
  Filing13F.svelte
  Table showing 13F institutional filing data with new position badges,
  increased/decreased indicators, and sortable columns.
-->
<script lang="ts">
  import { formatMarketCap } from '$lib/utils/format';

  interface Filing {
    institution: string;
    symbol: string;
    shares: number;
    value: number;
    changePercent: number;
    quarter: string;
  }

  interface Props {
    filings: Filing[];
    class?: string;
  }

  let {
    filings = [],
    class: className = ''
  }: Props = $props();

  type SortKey = 'institution' | 'symbol' | 'value' | 'changePercent' | 'shares';
  let sortBy = $state<SortKey>('value');
  let sortDir = $state<'asc' | 'desc'>('desc');

  let sorted = $derived(() => {
    const copy = [...filings];
    copy.sort((a, b) => {
      let cmp = 0;
      switch (sortBy) {
        case 'institution':
          cmp = a.institution.localeCompare(b.institution);
          break;
        case 'symbol':
          cmp = a.symbol.localeCompare(b.symbol);
          break;
        case 'value':
          cmp = a.value - b.value;
          break;
        case 'changePercent':
          cmp = a.changePercent - b.changePercent;
          break;
        case 'shares':
          cmp = a.shares - b.shares;
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

  function isNewPosition(f: Filing): boolean {
    return f.changePercent >= 999;
  }

  function changeColor(pct: number): string {
    if (pct >= 999) return 'text-[var(--accent-bright)]';
    if (pct > 10) return 'text-[var(--bullish-bright)]';
    if (pct > 0) return 'text-[var(--bullish)]';
    if (pct > -10) return 'text-[var(--bearish)]';
    return 'text-[var(--bearish-bright)]';
  }

  function changeIcon(pct: number): string {
    if (pct >= 999) return 'NEW';
    if (pct > 0) return '\u25B2';
    if (pct < 0) return '\u25BC';
    return '--';
  }
</script>

<div class="panel flex flex-col overflow-hidden {className}">
  <!-- Header -->
  <div class="flex items-center justify-between px-4 py-2.5 border-b border-[var(--border-subtle)]">
    <span class="text-sm font-semibold text-[var(--text-primary)]">13F Filings</span>
    <span class="text-2xs text-[var(--text-tertiary)]">{filings.length} positions</span>
  </div>

  <!-- Table -->
  <div class="flex-1 overflow-auto">
    <table class="w-full min-w-[680px]">
      <thead class="sticky top-0 z-10 bg-[var(--bg-elevated)]">
        <tr class="border-b border-[var(--border-subtle)]">
          <th class="px-3 py-2 text-left">
            <button
              type="button"
              class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
              onclick={() => handleSort('institution')}
            >
              Institution{sortIndicator('institution')}
            </button>
          </th>
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
              onclick={() => handleSort('shares')}
            >
              Shares{sortIndicator('shares')}
            </button>
          </th>
          <th class="px-3 py-2 text-right">
            <button
              type="button"
              class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
              onclick={() => handleSort('value')}
            >
              Value{sortIndicator('value')}
            </button>
          </th>
          <th class="px-3 py-2 text-right">
            <button
              type="button"
              class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
              onclick={() => handleSort('changePercent')}
            >
              Change %{sortIndicator('changePercent')}
            </button>
          </th>
          <th class="px-3 py-2 text-center">
            <span class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">Quarter</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {#each sorted() as filing, idx (filing.institution + filing.symbol + idx)}
          {@const isNew = isNewPosition(filing)}
          <tr
            class="border-b border-[var(--border-subtle)] transition-colors duration-75 hover:bg-[var(--hover-overlay)]
              {isNew ? 'bg-[oklch(0.14_0.02_290/0.3)]' : ''}"
          >
            <td class="px-3 py-2 text-xs text-[var(--text-secondary)] truncate max-w-[200px]">{filing.institution}</td>
            <td class="px-3 py-2">
              <div class="flex items-center gap-1.5">
                <span class="text-xs font-semibold text-[var(--text-primary)]">{filing.symbol}</span>
                {#if isNew}
                  <span class="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-sm bg-[var(--accent-bg)] text-[var(--accent-bright)] border border-[oklch(0.44_0.14_290/0.3)]">
                    NEW
                  </span>
                {/if}
              </div>
            </td>
            <td class="px-3 py-2 mono-nums text-xs text-right text-[var(--text-secondary)]">{filing.shares.toLocaleString()}</td>
            <td class="px-3 py-2 mono-nums text-xs text-right font-semibold text-[var(--text-primary)]">{formatMarketCap(filing.value)}</td>
            <td class="px-3 py-2 mono-nums text-xs text-right font-semibold {changeColor(filing.changePercent)}">
              {#if isNew}
                <span class="text-[9px] font-bold">NEW</span>
              {:else}
                <span class="mr-0.5">{changeIcon(filing.changePercent)}</span>{Math.abs(filing.changePercent).toFixed(1)}%
              {/if}
            </td>
            <td class="px-3 py-2 text-2xs text-center text-[var(--text-tertiary)]">{filing.quarter}</td>
          </tr>
        {/each}
      </tbody>
    </table>

    {#if filings.length === 0}
      <div class="flex items-center justify-center h-32 text-sm text-[var(--text-tertiary)]">
        No 13F filing data available
      </div>
    {/if}
  </div>
</div>
