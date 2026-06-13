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
    if (sortBy !== key) return ' △';
    return sortDir === 'asc' ? ' ▲' : ' ▼';
  }

  function formatDate(dateStr: string): string {
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
  }
</script>

<div class="panel insider-wrapper {className}">
  <!-- Header -->
  <div class="insider-header">
    <span class="insider-header-title">Insider Transactions</span>
    <span class="insider-header-count">{transactions.length} transactions</span>
  </div>

  <!-- Table -->
  <div class="insider-table-scroll">
    <table class="insider-table">
      <thead class="insider-thead">
        <tr class="insider-thead-row">
          <th class="insider-th insider-th--left">
            <button
              type="button"
              class="insider-sort-btn"
              onclick={() => handleSort('date')}
            >
              Date{sortIndicator('date')}
            </button>
          </th>
          <th class="insider-th insider-th--left">
            <button
              type="button"
              class="insider-sort-btn"
              onclick={() => handleSort('symbol')}
            >
              Symbol{sortIndicator('symbol')}
            </button>
          </th>
          <th class="insider-th insider-th--left">
            <span class="insider-th-label">Insider</span>
          </th>
          <th class="insider-th insider-th--left">
            <span class="insider-th-label">Title</span>
          </th>
          <th class="insider-th insider-th--center">
            <span class="insider-th-label">Type</span>
          </th>
          <th class="insider-th insider-th--right">
            <button
              type="button"
              class="insider-sort-btn"
              onclick={() => handleSort('shares')}
            >
              Shares{sortIndicator('shares')}
            </button>
          </th>
          <th class="insider-th insider-th--right">
            <span class="insider-th-label">Price</span>
          </th>
          <th class="insider-th insider-th--right">
            <button
              type="button"
              class="insider-sort-btn"
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
          <tr class="insider-row {isBuy ? 'insider-row--buy' : 'insider-row--sell'}">
            <td class="insider-td mono-nums insider-td--date">{formatDate(tx.date)}</td>
            <td class="insider-td insider-td--symbol">{tx.symbol}</td>
            <td class="insider-td insider-td--name">{tx.insiderName}</td>
            <td class="insider-td insider-td--title">{tx.title}</td>
            <td class="insider-td insider-td--type-cell">
              <span class="insider-badge {isBuy ? 'insider-badge--buy' : 'insider-badge--sell'}">
                {tx.type}
              </span>
            </td>
            <td class="insider-td mono-nums insider-td--numeric">{tx.shares.toLocaleString()}</td>
            <td class="insider-td mono-nums insider-td--numeric">{formatPrice(tx.price)}</td>
            <td class="insider-td mono-nums insider-td--value {isBuy ? 'insider-td--bullish' : 'insider-td--bearish'}">
              {formatMarketCap(tx.value)}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>

    {#if transactions.length === 0}
      <div class="insider-empty">
        No insider transactions to display
      </div>
    {/if}
  </div>
</div>

<style>
  /* Wrapper */
  .insider-wrapper {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* Header */
  .insider-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border-subtle);
  }

  .insider-header-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .insider-header-count {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
  }

  /* Table scroll container */
  .insider-table-scroll {
    flex: 1;
    overflow: auto;
  }

  /* Table */
  .insider-table {
    width: 100%;
    min-width: 700px;
  }

  /* Thead */
  .insider-thead {
    position: sticky;
    top: 0;
    z-index: 10;
    background-color: var(--bg-elevated);
  }

  .insider-thead-row {
    border-bottom: 1px solid var(--border-subtle);
  }

  /* Th */
  .insider-th {
    padding: 8px 12px;
  }

  .insider-th--left {
    text-align: left;
  }

  .insider-th--center {
    text-align: center;
  }

  .insider-th--right {
    text-align: right;
  }

  /* Th label (non-sortable) */
  .insider-th-label {
    font-size: var(--text-2xs);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
  }

  /* Sort button */
  .insider-sort-btn {
    font-size: var(--text-2xs);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
    transition: color 150ms, background-color 150ms, border-color 150ms;
  }

  .insider-sort-btn:hover {
    color: var(--text-secondary);
  }

  /* Body row */
  .insider-row {
    border-bottom: 1px solid var(--border-subtle);
    transition: color 150ms, background-color 150ms, border-color 150ms;
    transition-duration: 75ms;
  }

  .insider-row:hover {
    background-color: var(--hover-overlay);
  }

  .insider-row--buy {
    background-color: oklch(0.13 0.02 155 / 0.3);
  }

  .insider-row--sell {
    background-color: oklch(0.13 0.02 25 / 0.3);
  }

  /* Td base */
  .insider-td {
    padding: 8px 12px;
  }

  /* Date cell */
  .insider-td--date {
    font-size: var(--text-xs);
    color: var(--text-secondary);
  }

  /* Symbol cell */
  .insider-td--symbol {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-primary);
  }

  /* Insider name cell */
  .insider-td--name {
    font-size: var(--text-xs);
    color: var(--text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 140px;
  }

  /* Title cell */
  .insider-td--title {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100px;
  }

  /* Type cell (container) */
  .insider-td--type-cell {
    text-align: center;
  }

  /* Type badge */
  .insider-badge {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    padding: 2px 6px;
    border-radius: var(--radius-sm);
  }

  .insider-badge--buy {
    background-color: var(--bullish-bg);
    color: var(--bullish-bright);
    border: 1px solid oklch(0.45 0.12 155 / 0.3);
  }

  .insider-badge--sell {
    background-color: var(--bearish-bg);
    color: var(--bearish-bright);
    border: 1px solid oklch(0.42 0.12 25 / 0.3);
  }

  /* Numeric cells (shares, price) */
  .insider-td--numeric {
    font-size: var(--text-xs);
    text-align: right;
    color: var(--text-secondary);
  }

  /* Value cell */
  .insider-td--value {
    font-size: var(--text-xs);
    text-align: right;
    font-weight: 600;
  }

  .insider-td--bullish {
    color: var(--bullish);
  }

  .insider-td--bearish {
    color: var(--bearish);
  }

  /* Empty state */
  .insider-empty {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 128px;
    font-size: var(--text-sm);
    color: var(--text-tertiary);
  }
</style>
