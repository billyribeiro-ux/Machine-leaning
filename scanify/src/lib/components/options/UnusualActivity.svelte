<!--
  UnusualActivity.svelte
  Table of unusual options activity sorted by vol/oi ratio.
  High ratio rows highlighted. Columns: Symbol, Type, Strike,
  Expiry, Volume, OI, Vol/OI, Premium.
-->
<script lang="ts">
  import { formatPrice, formatMarketCap } from '$lib/utils/format';

  interface Activity {
    symbol: string;
    type: 'call' | 'put';
    strike: number;
    expiry: string;
    volume: number;
    oi: number;
    volOiRatio: number;
    premium: number;
  }

  interface Props {
    activities: Activity[];
    class?: string;
  }

  let {
    activities = [],
    class: className = ''
  }: Props = $props();

  type SortKey = 'symbol' | 'volOiRatio' | 'volume' | 'premium' | 'strike';
  let sortBy = $state<SortKey>('volOiRatio');
  let sortDir = $state<'asc' | 'desc'>('desc');

  let sorted = $derived.by(() => {
    const copy = [...activities];
    copy.sort((a, b) => {
      let cmp = 0;
      switch (sortBy) {
        case 'symbol':
          cmp = a.symbol.localeCompare(b.symbol);
          break;
        case 'volOiRatio':
          cmp = a.volOiRatio - b.volOiRatio;
          break;
        case 'volume':
          cmp = a.volume - b.volume;
          break;
        case 'premium':
          cmp = a.premium - b.premium;
          break;
        case 'strike':
          cmp = a.strike - b.strike;
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

  function ratioColor(ratio: number): string {
    if (ratio >= 5) return 'ratio-warning-bright';
    if (ratio >= 3) return 'ratio-warning';
    if (ratio >= 2) return 'ratio-primary';
    return 'ratio-secondary';
  }

  function rowHighlight(ratio: number): string {
    if (ratio >= 5) return 'row-highlight-high';
    if (ratio >= 3) return 'row-highlight-mid';
    return '';
  }

  function formatExpiry(dateStr: string): string {
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  function formatPremium(val: number): string {
    if (val >= 1_000_000) return '$' + (val / 1_000_000).toFixed(1) + 'M';
    if (val >= 1_000) return '$' + (val / 1_000).toFixed(0) + 'K';
    return '$' + val.toFixed(0);
  }
</script>

<div class="panel ua-container {className}">
  <!-- Header -->
  <div class="ua-header">
    <div class="ua-header-left">
      <div class="ua-indicator signal-ping"></div>
      <span class="ua-title">Unusual Activity</span>
      <span class="ua-count">({activities.length})</span>
    </div>
  </div>

  <!-- Table -->
  <div class="ua-table-wrap">
    <table class="ua-table">
      <thead class="ua-thead">
        <tr class="ua-thead-row">
          <th class="ua-th ua-th-left">
            <button
              type="button"
              class="ua-sort-btn"
              onclick={() => handleSort('symbol')}
            >
              Symbol{sortIndicator('symbol')}
            </button>
          </th>
          <th class="ua-th ua-th-center">
            <span class="ua-col-label">Type</span>
          </th>
          <th class="ua-th ua-th-right">
            <button
              type="button"
              class="ua-sort-btn"
              onclick={() => handleSort('strike')}
            >
              Strike{sortIndicator('strike')}
            </button>
          </th>
          <th class="ua-th ua-th-center">
            <span class="ua-col-label">Expiry</span>
          </th>
          <th class="ua-th ua-th-right">
            <button
              type="button"
              class="ua-sort-btn"
              onclick={() => handleSort('volume')}
            >
              Volume{sortIndicator('volume')}
            </button>
          </th>
          <th class="ua-th ua-th-right">
            <span class="ua-col-label">OI</span>
          </th>
          <th class="ua-th ua-th-right">
            <button
              type="button"
              class="ua-sort-btn"
              onclick={() => handleSort('volOiRatio')}
            >
              Vol/OI{sortIndicator('volOiRatio')}
            </button>
          </th>
          <th class="ua-th ua-th-right">
            <button
              type="button"
              class="ua-sort-btn"
              onclick={() => handleSort('premium')}
            >
              Premium{sortIndicator('premium')}
            </button>
          </th>
        </tr>
      </thead>
      <tbody>
        {#each sorted as act, idx (act.symbol + act.strike + act.expiry + act.type + idx)}
          {@const isCall = act.type === 'call'}
          <tr
            class="ua-row {rowHighlight(act.volOiRatio)}"
          >
            <td class="ua-td ua-td-symbol">{act.symbol}</td>
            <td class="ua-td ua-td-type-cell">
              <span
                class="ua-type-badge {isCall ? 'ua-type-call' : 'ua-type-put'}"
              >
                {act.type}
              </span>
            </td>
            <td class="ua-td mono-nums ua-td-numeric ua-td-right">{formatPrice(act.strike)}</td>
            <td class="ua-td mono-nums ua-td-numeric ua-td-center">{formatExpiry(act.expiry)}</td>
            <td class="ua-td mono-nums ua-td-numeric ua-td-right">{act.volume.toLocaleString()}</td>
            <td class="ua-td mono-nums ua-td-oi ua-td-right">{act.oi.toLocaleString()}</td>
            <td class="ua-td mono-nums ua-td-ratio ua-td-right {ratioColor(act.volOiRatio)}">
              {act.volOiRatio.toFixed(1)}x
            </td>
            <td class="ua-td mono-nums ua-td-premium ua-td-right">
              {formatPremium(act.premium)}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>

    {#if activities.length === 0}
      <div class="ua-empty">
        No unusual options activity detected
      </div>
    {/if}
  </div>
</div>

<style>
  /* Container */
  .ua-container {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* Header */
  .ua-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border-subtle);
  }

  .ua-header-left {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .ua-indicator {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    background-color: var(--warning);
  }

  .ua-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .ua-count {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
  }

  /* Table wrapper */
  .ua-table-wrap {
    flex: 1;
    overflow: auto;
  }

  .ua-table {
    width: 100%;
    min-width: 740px;
  }

  /* Thead */
  .ua-thead {
    position: sticky;
    top: 0;
    z-index: 10;
    background-color: var(--bg-elevated);
  }

  .ua-thead-row {
    border-bottom: 1px solid var(--border-subtle);
  }

  /* Table header cells */
  .ua-th {
    padding: 8px 12px;
  }

  .ua-th-left {
    text-align: left;
  }

  .ua-th-center {
    text-align: center;
  }

  .ua-th-right {
    text-align: right;
  }

  /* Column labels (non-sortable) */
  .ua-col-label {
    font-size: var(--text-2xs);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
  }

  /* Sort buttons */
  .ua-sort-btn {
    font-size: var(--text-2xs);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
    transition: color 150ms, background-color 150ms, border-color 150ms;
  }

  .ua-sort-btn:hover {
    color: var(--text-secondary);
  }

  /* Table body rows */
  .ua-row {
    border-bottom: 1px solid var(--border-subtle);
    transition: color 150ms, background-color 150ms, border-color 150ms;
    transition-duration: 75ms;
  }

  .ua-row:hover {
    background-color: var(--hover-overlay);
  }

  /* Row highlight variants */
  .row-highlight-high {
    background-color: oklch(0.14 0.03 85 / 0.35);
  }

  .row-highlight-mid {
    background-color: oklch(0.13 0.02 85 / 0.2);
  }

  /* Table data cells */
  .ua-td {
    padding: 8px 12px;
    font-size: var(--text-xs);
  }

  .ua-td-right {
    text-align: right;
  }

  .ua-td-center {
    text-align: center;
  }

  .ua-td-symbol {
    font-weight: 600;
    color: var(--text-primary);
  }

  .ua-td-type-cell {
    text-align: center;
  }

  .ua-td-numeric {
    color: var(--text-secondary);
  }

  .ua-td-oi {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
  }

  .ua-td-ratio {
    font-weight: 700;
  }

  .ua-td-premium {
    font-weight: 600;
    color: var(--text-primary);
  }

  /* Type badges */
  .ua-type-badge {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    padding: 2px 6px;
    border-radius: var(--radius-sm);
    border: 1px solid;
  }

  .ua-type-call {
    background-color: var(--bullish-bg);
    color: var(--bullish-bright);
    border-color: oklch(0.45 0.12 155 / 0.3);
  }

  .ua-type-put {
    background-color: var(--bearish-bg);
    color: var(--bearish-bright);
    border-color: oklch(0.42 0.12 25 / 0.3);
  }

  /* Ratio color variants */
  .ratio-warning-bright {
    color: var(--warning-bright);
  }

  .ratio-warning {
    color: var(--warning);
  }

  .ratio-primary {
    color: var(--text-primary);
  }

  .ratio-secondary {
    color: var(--text-secondary);
  }

  /* Empty state */
  .ua-empty {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 128px;
    font-size: var(--text-sm);
    color: var(--text-tertiary);
  }
</style>
