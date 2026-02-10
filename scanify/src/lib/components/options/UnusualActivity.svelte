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

  let sorted = $derived(() => {
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
    if (sortBy !== key) return ' \u25B3';
    return sortDir === 'asc' ? ' \u25B2' : ' \u25BC';
  }

  function ratioColor(ratio: number): string {
    if (ratio >= 5) return 'text-[var(--warning-bright)]';
    if (ratio >= 3) return 'text-[var(--warning)]';
    if (ratio >= 2) return 'text-[var(--text-primary)]';
    return 'text-[var(--text-secondary)]';
  }

  function rowHighlight(ratio: number): string {
    if (ratio >= 5) return 'bg-[oklch(0.14_0.03_85/0.35)]';
    if (ratio >= 3) return 'bg-[oklch(0.13_0.02_85/0.2)]';
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

<div class="panel flex flex-col overflow-hidden {className}">
  <!-- Header -->
  <div class="flex items-center justify-between px-4 py-2.5 border-b border-[var(--border-subtle)]">
    <div class="flex items-center gap-2">
      <div class="w-2 h-2 rounded-full bg-[var(--warning)] signal-ping"></div>
      <span class="text-sm font-semibold text-[var(--text-primary)]">Unusual Activity</span>
      <span class="text-2xs text-[var(--text-tertiary)]">({activities.length})</span>
    </div>
  </div>

  <!-- Table -->
  <div class="flex-1 overflow-auto">
    <table class="w-full min-w-[740px]">
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
          <th class="px-3 py-2 text-center">
            <span class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">Type</span>
          </th>
          <th class="px-3 py-2 text-right">
            <button
              type="button"
              class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
              onclick={() => handleSort('strike')}
            >
              Strike{sortIndicator('strike')}
            </button>
          </th>
          <th class="px-3 py-2 text-center">
            <span class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">Expiry</span>
          </th>
          <th class="px-3 py-2 text-right">
            <button
              type="button"
              class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
              onclick={() => handleSort('volume')}
            >
              Volume{sortIndicator('volume')}
            </button>
          </th>
          <th class="px-3 py-2 text-right">
            <span class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">OI</span>
          </th>
          <th class="px-3 py-2 text-right">
            <button
              type="button"
              class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
              onclick={() => handleSort('volOiRatio')}
            >
              Vol/OI{sortIndicator('volOiRatio')}
            </button>
          </th>
          <th class="px-3 py-2 text-right">
            <button
              type="button"
              class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
              onclick={() => handleSort('premium')}
            >
              Premium{sortIndicator('premium')}
            </button>
          </th>
        </tr>
      </thead>
      <tbody>
        {#each sorted() as act, idx (act.symbol + act.strike + act.expiry + act.type + idx)}
          {@const isCall = act.type === 'call'}
          <tr
            class="border-b border-[var(--border-subtle)] transition-colors duration-75 hover:bg-[var(--hover-overlay)]
              {rowHighlight(act.volOiRatio)}"
          >
            <td class="px-3 py-2 text-xs font-semibold text-[var(--text-primary)]">{act.symbol}</td>
            <td class="px-3 py-2 text-center">
              <span
                class="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded-sm
                  {isCall
                    ? 'bg-[var(--bullish-bg)] text-[var(--bullish-bright)] border border-[oklch(0.45_0.12_155/0.3)]'
                    : 'bg-[var(--bearish-bg)] text-[var(--bearish-bright)] border border-[oklch(0.42_0.12_25/0.3)]'}"
              >
                {act.type}
              </span>
            </td>
            <td class="px-3 py-2 mono-nums text-xs text-right text-[var(--text-secondary)]">{formatPrice(act.strike)}</td>
            <td class="px-3 py-2 mono-nums text-xs text-center text-[var(--text-secondary)]">{formatExpiry(act.expiry)}</td>
            <td class="px-3 py-2 mono-nums text-xs text-right text-[var(--text-secondary)]">{act.volume.toLocaleString()}</td>
            <td class="px-3 py-2 mono-nums text-xs text-right text-[var(--text-tertiary)]">{act.oi.toLocaleString()}</td>
            <td class="px-3 py-2 mono-nums text-xs text-right font-bold {ratioColor(act.volOiRatio)}">
              {act.volOiRatio.toFixed(1)}x
            </td>
            <td class="px-3 py-2 mono-nums text-xs text-right font-semibold text-[var(--text-primary)]">
              {formatPremium(act.premium)}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>

    {#if activities.length === 0}
      <div class="flex items-center justify-center h-32 text-sm text-[var(--text-tertiary)]">
        No unusual options activity detected
      </div>
    {/if}
  </div>
</div>
