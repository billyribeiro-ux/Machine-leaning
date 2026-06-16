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

  let sorted = $derived.by(() => {
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
    if (sortBy !== key) return ' △';
    return sortDir === 'asc' ? ' ▲' : ' ▼';
  }

  function siColor(pct: number): string {
    if (pct >= 30) return 'color: var(--bearish-bright)';
    if (pct >= 20) return 'color: var(--bearish)';
    if (pct >= 10) return 'color: var(--warning-bright)';
    return 'color: var(--text-secondary)';
  }

  function rowHighlight(pct: number): string {
    if (pct >= 30) return 'background-color: oklch(0.14 0.03 25 / 0.4)';
    if (pct >= 20) return 'background-color: oklch(0.13 0.02 85 / 0.3)';
    return '';
  }

  function formatSI(val: number): string {
    if (val >= 1_000_000) return (val / 1_000_000).toFixed(2) + 'M';
    if (val >= 1_000) return (val / 1_000).toFixed(0) + 'K';
    return val.toLocaleString();
  }

  function changeColor(change: number): string {
    if (change > 0) return 'color: var(--bearish)';
    if (change < 0) return 'color: var(--bullish)';
    return 'color: var(--text-tertiary)';
  }
</script>

<div class="panel short-interest-wrapper {className}">
  <!-- Header -->
  <div class="header">
    <span class="header-title">Short Interest</span>
    <span class="header-count">{data.length} symbols</span>
  </div>

  <!-- Table -->
  <div class="table-scroll">
    <table class="data-table">
      <thead class="table-head">
        <tr class="head-row">
          <th class="col-header col-left">
            <button
              type="button"
              class="sort-btn"
              onclick={() => handleSort('symbol')}
            >
              Symbol{sortIndicator('symbol')}
            </button>
          </th>
          <th class="col-header col-right">
            <button
              type="button"
              class="sort-btn"
              onclick={() => handleSort('shortInterest')}
            >
              Short Interest{sortIndicator('shortInterest')}
            </button>
          </th>
          <th class="col-header col-right">
            <button
              type="button"
              class="sort-btn"
              onclick={() => handleSort('shortPercent')}
            >
              SI %{sortIndicator('shortPercent')}
            </button>
          </th>
          <th class="col-header col-right">
            <button
              type="button"
              class="sort-btn"
              onclick={() => handleSort('daysToCover')}
            >
              Days to Cover{sortIndicator('daysToCover')}
            </button>
          </th>
          <th class="col-header col-right">
            <button
              type="button"
              class="sort-btn"
              onclick={() => handleSort('change')}
            >
              Change{sortIndicator('change')}
            </button>
          </th>
        </tr>
      </thead>
      <tbody>
        {#each sorted as entry, idx (entry.symbol + idx)}
          <tr
            class="data-row"
            style={rowHighlight(entry.shortPercent)}
          >
            <td class="cell cell-symbol">{entry.symbol}</td>
            <td class="cell cell-numeric mono-nums">{formatSI(entry.shortInterest)}</td>
            <td class="cell cell-numeric cell-si-pct mono-nums" style={siColor(entry.shortPercent)}>
              {entry.shortPercent.toFixed(1)}%
            </td>
            <td class="cell cell-numeric mono-nums">{entry.daysToCover.toFixed(1)}</td>
            <td class="cell cell-numeric cell-change mono-nums" style={changeColor(entry.change)}>
              {entry.change > 0 ? '+' : ''}{entry.change.toFixed(1)}%
            </td>
          </tr>
        {/each}
      </tbody>
    </table>

    {#if data.length === 0}
      <div class="empty-state">
        No short interest data available
      </div>
    {/if}
  </div>
</div>

<style>
  .short-interest-wrapper {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border-subtle);
  }

  .header-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .header-count {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
  }

  .table-scroll {
    flex: 1;
    overflow: auto;
  }

  .data-table {
    width: 100%;
    min-width: 560px;
  }

  .table-head {
    position: sticky;
    top: 0;
    z-index: 10;
    background-color: var(--bg-elevated);
  }

  .head-row {
    border-bottom: 1px solid var(--border-subtle);
  }

  .col-header {
    padding: 8px 12px;
  }

  .col-left {
    text-align: left;
  }

  .col-right {
    text-align: right;
  }

  .sort-btn {
    font-size: var(--text-2xs);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
    transition: color 150ms, background-color 150ms;
  }

  .sort-btn:hover {
    color: var(--text-secondary);
  }

  .data-row {
    border-bottom: 1px solid var(--border-subtle);
    transition-duration: 75ms;
    transition-property: color, background-color;
  }

  .data-row:hover {
    background: var(--hover-overlay);
  }

  .cell {
    padding: 8px 12px;
    font-size: var(--text-xs);
  }

  .cell-symbol {
    font-weight: 600;
    color: var(--text-primary);
  }

  .cell-numeric {
    text-align: right;
    color: var(--text-secondary);
  }

  .cell-si-pct {
    font-weight: 700;
  }

  .cell-change {
    font-weight: 600;
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
