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
    if (sortBy !== key) return ' △';
    return sortDir === 'asc' ? ' ▲' : ' ▼';
  }

  function flowBarWidth(flow: number): number {
    return (Math.abs(flow) / maxAbsFlow) * 100;
  }
</script>

<div class="panel etf-flows-root {className}">
  <!-- Header -->
  <div class="etf-header">
    <span class="etf-header-title">ETF Flows</span>
    <span class="etf-header-count">{data.length} funds</span>
  </div>

  <!-- Table -->
  <div class="etf-table-wrap">
    <table class="etf-table">
      <thead class="etf-thead">
        <tr class="etf-thead-row">
          <th class="etf-th etf-th-left">
            <button
              type="button"
              class="etf-sort-btn"
              onclick={() => handleSort('symbol')}
            >
              Symbol{sortIndicator('symbol')}
            </button>
          </th>
          <th class="etf-th etf-th-left">
            <span class="etf-col-label">Name</span>
          </th>
          <th class="etf-th etf-th-right">
            <button
              type="button"
              class="etf-sort-btn"
              onclick={() => handleSort('flow')}
            >
              Flow ($){sortIndicator('flow')}
            </button>
          </th>
          <th class="etf-th etf-th-left etf-th-flowbar">
            <span class="etf-col-label">Flow Bar</span>
          </th>
          <th class="etf-th etf-th-right">
            <button
              type="button"
              class="etf-sort-btn"
              onclick={() => handleSort('aum')}
            >
              AUM{sortIndicator('aum')}
            </button>
          </th>
          <th class="etf-th etf-th-right">
            <button
              type="button"
              class="etf-sort-btn"
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
          <tr class="etf-row">
            <td class="etf-td etf-td-symbol">{entry.symbol}</td>
            <td class="etf-td etf-td-name">{entry.name}</td>
            <td class="etf-td mono-nums etf-td-flow {isInflow ? 'flow-positive' : 'flow-negative'}">
              {isInflow ? '+' : ''}{formatMarketCap(entry.flow)}
            </td>
            <td class="etf-td">
              <div class="flow-bar-track">
                <div
                  class="flow-bar-fill {isInflow ? 'flow-bar-inflow' : 'flow-bar-outflow'}"
                  style="width: {flowBarWidth(entry.flow)}%;"
                ></div>
              </div>
            </td>
            <td class="etf-td mono-nums etf-td-aum">{formatMarketCap(entry.aum)}</td>
            <td class="etf-td mono-nums etf-td-pct {isInflow ? 'flow-positive' : 'flow-negative'}">
              {entry.flowPercent > 0 ? '+' : ''}{entry.flowPercent.toFixed(2)}%
            </td>
          </tr>
        {/each}
      </tbody>
    </table>

    {#if data.length === 0}
      <div class="etf-empty">
        No ETF flow data available
      </div>
    {/if}
  </div>
</div>

<style>
  .etf-flows-root {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* ── Header ── */
  .etf-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border-subtle);
  }

  .etf-header-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .etf-header-count {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
  }

  /* ── Table wrapper ── */
  .etf-table-wrap {
    flex: 1;
    overflow: auto;
  }

  .etf-table {
    width: 100%;
    min-width: 700px;
  }

  /* ── Thead ── */
  .etf-thead {
    position: sticky;
    top: 0;
    z-index: 10;
    background-color: var(--bg-elevated);
  }

  .etf-thead-row {
    border-bottom: 1px solid var(--border-subtle);
  }

  /* ── Th ── */
  .etf-th {
    padding: 8px 12px;
  }

  .etf-th-left {
    text-align: left;
  }

  .etf-th-right {
    text-align: right;
  }

  .etf-th-flowbar {
    width: 140px;
  }

  /* ── Column labels (non-sortable) ── */
  .etf-col-label {
    font-size: var(--text-2xs);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
  }

  /* ── Sort buttons ── */
  .etf-sort-btn {
    font-size: var(--text-2xs);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
    transition: color 150ms, background-color 150ms, border-color 150ms;
  }

  .etf-sort-btn:hover {
    color: var(--text-secondary);
  }

  /* ── Body rows ── */
  .etf-row {
    border-bottom: 1px solid var(--border-subtle);
    transition: color 150ms, background-color 150ms, border-color 150ms;
  }

  .etf-row:hover {
    background-color: var(--hover-overlay);
  }

  /* ── Td base ── */
  .etf-td {
    padding: 8px 12px;
  }

  .etf-td-symbol {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-primary);
  }

  .etf-td-name {
    font-size: var(--text-xs);
    color: var(--text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 180px;
  }

  .etf-td-flow {
    font-size: var(--text-xs);
    text-align: right;
    font-weight: 600;
  }

  .etf-td-aum {
    font-size: var(--text-xs);
    text-align: right;
    color: var(--text-secondary);
  }

  .etf-td-pct {
    font-size: var(--text-xs);
    text-align: right;
    font-weight: 600;
  }

  /* ── Flow colour modifiers ── */
  .flow-positive {
    color: var(--bullish);
  }

  .flow-negative {
    color: var(--bearish);
  }

  /* ── Flow bar ── */
  .flow-bar-track {
    width: 100%;
    height: 12px;
    background-color: var(--bg-void);
    border-radius: var(--radius-full);
    overflow: hidden;
  }

  .flow-bar-fill {
    height: 100%;
    border-radius: var(--radius-full);
    transition: all 300ms;
  }

  .flow-bar-inflow {
    background-color: var(--bullish-dim);
  }

  .flow-bar-outflow {
    background-color: var(--bearish-dim);
  }

  /* ── Empty state ── */
  .etf-empty {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 128px;
    font-size: var(--text-sm);
    color: var(--text-tertiary);
  }
</style>
