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

  let sorted = $derived.by(() => {
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
    if (sortBy !== key) return ' △';
    return sortDir === 'asc' ? ' ▲' : ' ▼';
  }

  function isNewPosition(f: Filing): boolean {
    return f.changePercent >= 999;
  }

  function changeColor(pct: number): string {
    if (pct >= 999) return 'change-accent';
    if (pct > 10) return 'change-bullish-bright';
    if (pct > 0) return 'change-bullish';
    if (pct > -10) return 'change-bearish';
    return 'change-bearish-bright';
  }

  function changeIcon(pct: number): string {
    if (pct >= 999) return 'NEW';
    if (pct > 0) return '▲';
    if (pct < 0) return '▼';
    return '--';
  }
</script>

<div class="panel filing-wrapper {className}">
  <!-- Header -->
  <div class="filing-header">
    <span class="filing-title">13F Filings</span>
    <span class="filing-count">{filings.length} positions</span>
  </div>

  <!-- Table -->
  <div class="table-scroll">
    <table class="filing-table">
      <thead class="table-head">
        <tr class="head-row">
          <th class="th-cell th-left">
            <button
              type="button"
              class="sort-btn"
              onclick={() => handleSort('institution')}
            >
              Institution{sortIndicator('institution')}
            </button>
          </th>
          <th class="th-cell th-left">
            <button
              type="button"
              class="sort-btn"
              onclick={() => handleSort('symbol')}
            >
              Symbol{sortIndicator('symbol')}
            </button>
          </th>
          <th class="th-cell th-right">
            <button
              type="button"
              class="sort-btn"
              onclick={() => handleSort('shares')}
            >
              Shares{sortIndicator('shares')}
            </button>
          </th>
          <th class="th-cell th-right">
            <button
              type="button"
              class="sort-btn"
              onclick={() => handleSort('value')}
            >
              Value{sortIndicator('value')}
            </button>
          </th>
          <th class="th-cell th-right">
            <button
              type="button"
              class="sort-btn"
              onclick={() => handleSort('changePercent')}
            >
              Change %{sortIndicator('changePercent')}
            </button>
          </th>
          <th class="th-cell th-center">
            <span class="col-label">Quarter</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {#each sorted as filing, idx (filing.institution + filing.symbol + idx)}
          {@const isNew = isNewPosition(filing)}
          <tr
            class="body-row {isNew ? 'new-position-row' : ''}"
          >
            <td class="td-cell institution-cell">{filing.institution}</td>
            <td class="td-cell">
              <div class="symbol-wrap">
                <span class="symbol-text">{filing.symbol}</span>
                {#if isNew}
                  <span class="new-badge">
                    NEW
                  </span>
                {/if}
              </div>
            </td>
            <td class="td-cell mono-nums td-right td-secondary">{filing.shares.toLocaleString()}</td>
            <td class="td-cell mono-nums td-right td-value">{formatMarketCap(filing.value)}</td>
            <td class="td-cell mono-nums td-right td-change {changeColor(filing.changePercent)}">
              {#if isNew}
                <span class="change-new-label">NEW</span>
              {:else}
                <span class="change-icon">{changeIcon(filing.changePercent)}</span>{Math.abs(filing.changePercent).toFixed(1)}%
              {/if}
            </td>
            <td class="td-cell td-quarter">{filing.quarter}</td>
          </tr>
        {/each}
      </tbody>
    </table>

    {#if filings.length === 0}
      <div class="empty-state">
        No 13F filing data available
      </div>
    {/if}
  </div>
</div>

<style>
  /* ── Wrapper ── */
  .filing-wrapper {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* ── Header ── */
  .filing-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border-subtle);
  }

  .filing-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .filing-count {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
  }

  /* ── Table scroll area ── */
  .table-scroll {
    flex: 1;
    overflow: auto;
  }

  /* ── Table ── */
  .filing-table {
    width: 100%;
    min-width: 680px;
  }

  /* ── Table head ── */
  .table-head {
    position: sticky;
    top: 0;
    z-index: 10;
    background-color: var(--bg-elevated);
  }

  .head-row {
    border-bottom: 1px solid var(--border-subtle);
  }

  /* ── Header cells ── */
  .th-cell {
    padding: 8px 12px;
  }

  .th-left {
    text-align: left;
  }

  .th-right {
    text-align: right;
  }

  .th-center {
    text-align: center;
  }

  /* ── Sort button ── */
  .sort-btn {
    font-size: var(--text-2xs);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
    transition: color 150ms, background-color 150ms, border-color 150ms;
  }

  .sort-btn:hover {
    color: var(--text-secondary);
  }

  /* ── Non-interactive column label ── */
  .col-label {
    font-size: var(--text-2xs);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
  }

  /* ── Body rows ── */
  .body-row {
    border-bottom: 1px solid var(--border-subtle);
    transition: color 150ms, background-color 150ms, border-color 150ms;
    transition-duration: 75ms;
  }

  .body-row:hover {
    background-color: var(--hover-overlay);
  }

  .new-position-row {
    background-color: oklch(0.14 0.02 290 / 0.3);
  }

  /* ── Body cells ── */
  .td-cell {
    padding: 8px 12px;
    font-size: var(--text-xs);
  }

  .td-right {
    text-align: right;
  }

  .td-secondary {
    color: var(--text-secondary);
  }

  .td-value {
    font-weight: 600;
    color: var(--text-primary);
  }

  .td-change {
    font-weight: 600;
  }

  .td-quarter {
    font-size: var(--text-2xs);
    text-align: center;
    color: var(--text-tertiary);
  }

  /* ── Institution cell ── */
  .institution-cell {
    color: var(--text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 200px;
  }

  /* ── Symbol column ── */
  .symbol-wrap {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .symbol-text {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-primary);
  }

  /* ── NEW badge ── */
  .new-badge {
    font-size: 9px;
    font-weight: 700;
    text-transform: uppercase;
    padding: 2px 6px;
    border-radius: var(--radius-sm);
    background-color: var(--accent-bg);
    color: var(--accent-bright);
    border: 1px solid oklch(0.44 0.14 290 / 0.3);
  }

  /* ── Change percent colors ── */
  .change-accent {
    color: var(--accent-bright);
  }

  .change-bullish-bright {
    color: var(--bullish-bright);
  }

  .change-bullish {
    color: var(--bullish);
  }

  .change-bearish {
    color: var(--bearish);
  }

  .change-bearish-bright {
    color: var(--bearish-bright);
  }

  /* ── Change cell helpers ── */
  .change-new-label {
    font-size: 9px;
    font-weight: 700;
  }

  .change-icon {
    margin-right: 2px;
  }

  /* ── Empty state ── */
  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 128px;
    font-size: var(--text-sm);
    color: var(--text-tertiary);
  }
</style>
