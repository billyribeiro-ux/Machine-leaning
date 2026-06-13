<!--
  FlowFeed.svelte
  Real-time feed of options flow activity with auto-scroll,
  unusual activity highlighting, and sweep badge indicators.
-->
<script lang="ts">
  import { formatVolume, formatPrice, formatTime } from '$lib/utils/format';

  interface FlowItem {
    id: string;
    symbol: string;
    timestamp: string | number;
    type: 'call' | 'put';
    strike: number;
    expiration: string;
    side: 'buy' | 'sell';
    size: number;
    premium: number;
    isUnusual: boolean;
    isSweep: boolean;
  }

  interface Props {
    items: FlowItem[];
    class?: string;
  }

  let {
    items = [],
    class: className = ''
  }: Props = $props();

  let feedContainer: HTMLDivElement | undefined = $state(undefined);
  let isHovered = $state(false);
  let autoScroll = $state(true);

  // Auto-scroll to newest entry
  $effect(() => {
    const _len = items.length;
    if (autoScroll && !isHovered && feedContainer) {
      requestAnimationFrame(() => {
        if (feedContainer) {
          feedContainer.scrollTop = 0;
        }
      });
    }
  });

  function handleMouseEnter() {
    isHovered = true;
  }

  function handleMouseLeave() {
    isHovered = false;
  }

  function formatExpShort(dateStr: string): string {
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'numeric', day: 'numeric' });
  }

  function formatPremium(premium: number): string {
    if (premium >= 1_000_000) return '$' + (premium / 1_000_000).toFixed(1) + 'M';
    if (premium >= 1_000) return '$' + (premium / 1_000).toFixed(0) + 'K';
    return '$' + premium.toFixed(0);
  }

  // Sort items newest-first
  let sortedItems = $derived(
    [...items].sort((a, b) => {
      const ta = typeof a.timestamp === 'string' ? new Date(a.timestamp).getTime() : a.timestamp;
      const tb = typeof b.timestamp === 'string' ? new Date(b.timestamp).getTime() : b.timestamp;
      return tb - ta;
    })
  );
</script>

<div class="panel flow-panel {className}">
  <!-- Header -->
  <div class="flow-header">
    <div class="header-left">
      <div class="live-dot signal-ping"></div>
      <span class="header-title">Options Flow</span>
      <span class="text-2xs header-count">({items.length})</span>
    </div>
    <button
      type="button"
      class="auto-btn text-2xs {autoScroll ? 'auto-btn-active' : ''}"
      onclick={() => (autoScroll = !autoScroll)}
    >
      {autoScroll ? 'AUTO' : 'PAUSED'}
    </button>
  </div>

  <!-- Feed -->
  <div
    class="feed-scroll"
    bind:this={feedContainer}
    onmouseenter={handleMouseEnter}
    onmouseleave={handleMouseLeave}
  >
    {#each sortedItems as item (item.id)}
      {@const isCall = item.type === 'call'}

      <div
        class="flow-row {isCall ? 'flow-row-call' : 'flow-row-put'}
          {item.isUnusual ? (isCall ? 'flow-row-unusual flow-row-unusual-call' : 'flow-row-unusual flow-row-unusual-put') : ''}"
      >
        <!-- Symbol -->
        <span class="symbol-col">{item.symbol}</span>

        <!-- Type badge -->
        <span class="type-badge {isCall ? 'type-badge-call' : 'type-badge-put'}">
          {item.type === 'call' ? 'C' : 'P'}
        </span>

        <!-- Strike @ Expiration -->
        <span class="strike-col mono-nums">
          {item.strike}@{formatExpShort(item.expiration)}
        </span>

        <!-- Side -->
        <span class="side-col {item.side === 'buy' ? 'side-buy' : 'side-sell'}">
          {item.side}
        </span>

        <!-- Spacer -->
        <div class="spacer"></div>

        <!-- Badges -->
        {#if item.isSweep}
          <span class="badge-sweep">SWEEP</span>
        {/if}
        {#if item.isUnusual}
          <span class="badge-unusual">UNUSUAL</span>
        {/if}

        <!-- Size -->
        <span class="size-col mono-nums">
          {item.size.toLocaleString()}
        </span>

        <!-- Premium -->
        <span class="premium-col mono-nums">
          {formatPremium(item.premium)}
        </span>

        <!-- Time -->
        <span class="text-2xs time-col">
          {formatTime(typeof item.timestamp === 'string' ? new Date(item.timestamp).getTime() : item.timestamp)}
        </span>
      </div>
    {/each}

    {#if items.length === 0}
      <div class="empty-state">
        Waiting for options flow data...
      </div>
    {/if}
  </div>
</div>

<style>
  /* ── Layout ── */
  .flow-panel {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* ── Header ── */
  .flow-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-inline: 16px;
    padding-block: 8px;
    border-bottom: 1px solid var(--border-subtle);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .live-dot {
    width: 8px;
    height: 8px;
    border-radius: 9999px;
    background-color: var(--bullish);
  }

  .header-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .header-count {
    color: var(--text-tertiary);
  }

  /* ── Auto-scroll button ── */
  .auto-btn {
    padding-inline: 8px;
    padding-block: 4px;
    border-radius: 4px;
    transition: color 150ms, background-color 150ms;
    color: var(--text-tertiary);
  }

  .auto-btn:hover {
    color: var(--text-secondary);
  }

  .auto-btn-active {
    background-color: var(--accent-bg);
    color: var(--accent-bright);
  }

  .auto-btn-active:hover {
    color: var(--accent-bright);
  }

  /* ── Feed scroll area ── */
  .feed-scroll {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
    padding: 8px;
  }

  .feed-scroll > :global(* + *) {
    margin-top: 4px;
  }

  /* ── Flow row (shared) ── */
  .flow-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding-inline: 12px;
    padding-block: 8px;
    border-radius: 6px;
    border: 1px solid var(--border-subtle);
    transition: all 150ms;
  }

  .flow-row:hover {
    background-color: var(--hover-overlay);
  }

  /* ── Row tint variants ── */
  .flow-row-call {
    background-color: oklch(0.13 0.03 155 / 0.5);
  }

  .flow-row-put {
    background-color: oklch(0.13 0.03 25 / 0.5);
  }

  /* ── Unusual activity ── */
  .flow-row-unusual {
    box-shadow: 0 0 12px 0 oklch(0.6 0.15 85 / 0.15);
  }

  .flow-row-unusual-call {
    border-color: var(--bullish-dim);
  }

  .flow-row-unusual-put {
    border-color: var(--bearish-dim);
  }

  /* ── Symbol column ── */
  .symbol-col {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-primary);
    width: 56px;
    flex-shrink: 0;
  }

  /* ── Type badge ── */
  .type-badge {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    padding-inline: 6px;
    padding-block: 2px;
    border-radius: 2px;
    flex-shrink: 0;
    border: 1px solid;
  }

  .type-badge-call {
    background-color: var(--bullish-bg);
    color: var(--bullish-bright);
    border-color: oklch(0.45 0.12 155 / 0.3);
  }

  .type-badge-put {
    background-color: var(--bearish-bg);
    color: var(--bearish-bright);
    border-color: oklch(0.42 0.12 25 / 0.3);
  }

  /* ── Strike column ── */
  .strike-col {
    font-size: var(--text-xs);
    color: var(--text-secondary);
    flex-shrink: 0;
  }

  /* ── Side column ── */
  .side-col {
    font-size: 10px;
    text-transform: uppercase;
    font-weight: 500;
    flex-shrink: 0;
  }

  .side-buy {
    color: var(--bullish);
  }

  .side-sell {
    color: var(--bearish);
  }

  /* ── Spacer ── */
  .spacer {
    flex: 1;
  }

  /* ── Badges ── */
  .badge-sweep {
    font-size: 9px;
    font-weight: 700;
    text-transform: uppercase;
    padding-inline: 6px;
    padding-block: 2px;
    border-radius: 2px;
    background-color: var(--accent-bg);
    color: var(--accent-bright);
    border: 1px solid oklch(0.44 0.14 290 / 0.3);
  }

  .badge-unusual {
    font-size: 9px;
    font-weight: 700;
    text-transform: uppercase;
    padding-inline: 6px;
    padding-block: 2px;
    border-radius: 2px;
    background-color: var(--warning-bg);
    color: var(--warning-bright);
    border: 1px solid oklch(0.52 0.10 85 / 0.3);
  }

  /* ── Size column ── */
  .size-col {
    font-size: var(--text-xs);
    color: var(--text-secondary);
    width: 48px;
    text-align: right;
    flex-shrink: 0;
  }

  /* ── Premium column ── */
  .premium-col {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-primary);
    width: 64px;
    text-align: right;
    flex-shrink: 0;
  }

  /* ── Time column ── */
  .time-col {
    color: var(--text-tertiary);
    width: 64px;
    text-align: right;
    flex-shrink: 0;
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
