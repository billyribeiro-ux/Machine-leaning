<!--
  InsiderTracker.svelte
  Table of insider transactions (buys highlighted green, sells red).
  Sortable by date and value columns.
-->
<script lang="ts">
  import { formatPrice, formatMarketCap } from '$lib/utils/format';

  interface InsiderTransaction {
    symbol: string;
    insiderName: string;
    title: string;
    type: 'buy' | 'sell';
    shares: number;
    price: number;
    value: number;
    date: string;
  }

  interface Props {
    transactions: InsiderTransaction[];
    class?: string;
  }

  let {
    transactions = [],
    class: className = ''
  }: Props = $props();

  type SortKey = 'date' | 'value' | 'symbol' | 'shares';
  let sortBy = $state<SortKey>('date');
  let sortDir = $state<'asc' | 'desc'>('desc');

  let sorted = $derived.by(() => {
    const copy = [...transactions];
    copy.sort((a, b) => {
      let cmp = 0;
      switch (sortBy) {
        case 'date':
          cmp = new Date(a.date).getTime() - new Date(b.date).getTime();
          break;
        case 'value':
          cmp = a.value - b.value;
          break;
        case 'symbol':
          cmp = a.symbol.localeCompare(b.symbol);
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

  function formatDate(dateStr: string): string {
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
  }
</script>

<div class="panel flex flex-col overflow-hidden {className}">
  <!-- Header -->
  <div class="flex items-center justify-between px-4 py-2.5 border-b border-[var(--border-subtle)]">
    <span class="text-sm font-semibold text-[var(--text-primary)]">Insider Transactions</span>
    <span class="text-2xs text-[var(--text-tertiary)]">{transactions.length} transactions</span>
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
              onclick={() => handleSort('date')}
            >
              Date{sortIndicator('date')}
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
          <th class="px-3 py-2 text-left">
            <span class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">Insider</span>
          </th>
          <th class="px-3 py-2 text-left">
            <span class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">Title</span>
          </th>
          <th class="px-3 py-2 text-center">
            <span class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">Type</span>
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
            <span class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">Price</span>
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
        </tr>
      </thead>
      <tbody>
        {#each sorted as tx, idx (tx.symbol + tx.date + tx.insiderName + idx)}
          {@const isBuy = tx.type === 'buy'}
          <tr
            class="border-b border-[var(--border-subtle)] transition-colors duration-75 hover:bg-[var(--hover-overlay)]
              {isBuy ? 'bg-[oklch(0.13_0.02_155/0.3)]' : 'bg-[oklch(0.13_0.02_25/0.3)]'}"
          >
            <td class="px-3 py-2 mono-nums text-xs text-[var(--text-secondary)]">{formatDate(tx.date)}</td>
            <td class="px-3 py-2 text-xs font-semibold text-[var(--text-primary)]">{tx.symbol}</td>
            <td class="px-3 py-2 text-xs text-[var(--text-secondary)] truncate max-w-[140px]">{tx.insiderName}</td>
            <td class="px-3 py-2 text-2xs text-[var(--text-tertiary)] truncate max-w-[100px]">{tx.title}</td>
            <td class="px-3 py-2 text-center">
              <span
                class="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded-sm
                  {isBuy
                    ? 'bg-[var(--bullish-bg)] text-[var(--bullish-bright)] border border-[oklch(0.45_0.12_155/0.3)]'
                    : 'bg-[var(--bearish-bg)] text-[var(--bearish-bright)] border border-[oklch(0.42_0.12_25/0.3)]'}"
              >
                {tx.type}
              </span>
            </td>
            <td class="px-3 py-2 mono-nums text-xs text-right text-[var(--text-secondary)]">{tx.shares.toLocaleString()}</td>
            <td class="px-3 py-2 mono-nums text-xs text-right text-[var(--text-secondary)]">{formatPrice(tx.price)}</td>
            <td class="px-3 py-2 mono-nums text-xs text-right font-semibold {isBuy ? 'text-[var(--bullish)]' : 'text-[var(--bearish)]'}">
              {formatMarketCap(tx.value)}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>

    {#if transactions.length === 0}
      <div class="flex items-center justify-center h-32 text-sm text-[var(--text-tertiary)]">
        No insider transactions to display
      </div>
    {/if}
  </div>
</div>
