<!--
  DarkPoolFeed.svelte
  Scrollable feed of dark pool prints with large block highlighting.
  Blocks > $1M (price * size) get accent border. Running total at top.
-->
<script lang="ts">
  import { formatPrice, formatTime, formatVolume } from '$lib/utils/format';

  interface DarkPoolTrade {
    symbol: string;
    price: number;
    size: number;
    timestamp: number;
    exchange: string;
  }

  interface Props {
    trades: DarkPoolTrade[];
    class?: string;
  }

  let {
    trades = [],
    class: className = ''
  }: Props = $props();

  let feedContainer: HTMLDivElement | undefined = $state(undefined);
  let isHovered = $state(false);
  let autoScroll = $state(true);

  const LARGE_BLOCK_THRESHOLD = 1_000_000;

  let sortedTrades = $derived(
    [...trades].sort((a, b) => b.timestamp - a.timestamp)
  );

  let runningTotal = $derived(
    trades.reduce((sum, t) => sum + t.price * t.size, 0)
  );

  let largeBlockCount = $derived(
    trades.filter((t) => t.price * t.size >= LARGE_BLOCK_THRESHOLD).length
  );

  function notionalValue(trade: DarkPoolTrade): number {
    return trade.price * trade.size;
  }

  function formatNotional(val: number): string {
    if (val >= 1_000_000_000) return '$' + (val / 1_000_000_000).toFixed(2) + 'B';
    if (val >= 1_000_000) return '$' + (val / 1_000_000).toFixed(2) + 'M';
    if (val >= 1_000) return '$' + (val / 1_000).toFixed(0) + 'K';
    return '$' + val.toFixed(0);
  }

  function isLargeBlock(trade: DarkPoolTrade): boolean {
    return notionalValue(trade) >= LARGE_BLOCK_THRESHOLD;
  }

  $effect(() => {
    const _len = trades.length;
    if (autoScroll && !isHovered && feedContainer) {
      requestAnimationFrame(() => {
        if (feedContainer) {
          feedContainer.scrollTop = 0;
        }
      });
    }
  });
</script>

<div class="panel dark-pool-root {className}">
  <!-- Header -->
  <div class="header">
    <div class="header-left">
      <div class="indicator signal-ping"></div>
      <span class="header-title">Dark Pool Feed</span>
      <span class="header-count">({trades.length})</span>
    </div>
    <button
      type="button"
      class="scroll-toggle {autoScroll ? 'scroll-toggle--active' : 'scroll-toggle--paused'}"
      onclick={() => (autoScroll = !autoScroll)}
    >
      {autoScroll ? 'AUTO' : 'PAUSED'}
    </button>
  </div>

  <!-- Summary bar -->
  <div class="summary-bar">
    <div class="summary-item">
      <span class="summary-label">Total Vol:</span>
      <span class="mono-nums summary-value">{formatNotional(runningTotal)}</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">Large Blocks:</span>
      <span class="mono-nums summary-value summary-value--accent">{largeBlockCount}</span>
    </div>
  </div>

  <!-- Feed -->
  <div
    class="feed-list"
    bind:this={feedContainer}
    onmouseenter={() => (isHovered = true)}
    onmouseleave={() => (isHovered = false)}
  >
    {#each sortedTrades as trade, idx (trade.timestamp + '-' + trade.symbol + '-' + idx)}
      {@const large = isLargeBlock(trade)}
      {@const notional = notionalValue(trade)}

      <div
        class="trade-row {large ? 'trade-row--large' : 'trade-row--normal'}"
      >
        <!-- Time -->
        <span class="mono-nums trade-time">
          {formatTime(trade.timestamp)}
        </span>

        <!-- Symbol -->
        <span class="trade-symbol">{trade.symbol}</span>

        <!-- Price -->
        <span class="mono-nums trade-price">
          {formatPrice(trade.price)}
        </span>

        <!-- Size -->
        <span class="mono-nums trade-size">
          {trade.size.toLocaleString()}
        </span>

        <!-- Spacer -->
        <div class="trade-spacer"></div>

        <!-- Large block badge -->
        {#if large}
          <span class="block-badge">
            BLOCK
          </span>
        {/if}

        <!-- Notional -->
        <span class="mono-nums trade-notional {large ? 'trade-notional--large' : 'trade-notional--normal'}">
          {formatNotional(notional)}
        </span>

        <!-- Exchange -->
        <span class="trade-exchange">
          {trade.exchange}
        </span>
      </div>
    {/each}

    {#if trades.length === 0}
      <div class="empty-state">
        Waiting for dark pool data...
      </div>
    {/if}
  </div>
</div>

<style>
  .dark-pool-root {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* ── Header ── */
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border-subtle);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .indicator {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    background-color: var(--accent);
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

  .scroll-toggle {
    font-size: var(--text-2xs);
    padding: 4px 8px;
    border-radius: var(--radius-md);
    transition: color 150ms, background-color 150ms;
    border: none;
    cursor: pointer;
    background: none;
  }

  .scroll-toggle--active {
    background-color: var(--accent-bg);
    color: var(--accent-bright);
  }

  .scroll-toggle--paused {
    color: var(--text-tertiary);
  }

  .scroll-toggle--paused:hover {
    color: var(--text-secondary);
  }

  /* ── Summary Bar ── */
  .summary-bar {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 8px 16px;
    background-color: var(--bg-elevated);
    border-bottom: 1px solid var(--border-subtle);
  }

  .summary-item {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .summary-label {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
  }

  .summary-value {
    font-size: var(--text-xs);
    font-weight: 700;
    color: var(--text-primary);
  }

  .summary-value--accent {
    color: var(--accent-bright);
  }

  /* ── Feed List ── */
  .feed-list {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
    padding: 8px;
  }

  .feed-list > :global(* + *) {
    margin-top: 4px;
  }

  /* ── Trade Row ── */
  .trade-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    border-radius: var(--radius-md);
    border: 1px solid;
    transition: all 150ms;
  }

  .trade-row:hover {
    background-color: var(--hover-overlay);
  }

  .trade-row--normal {
    background-color: var(--bg-surface);
    border-color: var(--border-subtle);
  }

  .trade-row--large {
    background-color: oklch(0.14 0.03 290 / 0.4);
    border-color: var(--accent-dim);
    box-shadow: 0 0 12px 0 oklch(0.6 0.15 290 / 0.12);
  }

  /* ── Trade Fields ── */
  .trade-time {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    width: 64px;
    flex-shrink: 0;
  }

  .trade-symbol {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-primary);
    width: 56px;
    flex-shrink: 0;
  }

  .trade-price {
    font-size: var(--text-xs);
    color: var(--text-secondary);
    width: 80px;
    text-align: right;
    flex-shrink: 0;
  }

  .trade-size {
    font-size: var(--text-xs);
    color: var(--text-secondary);
    width: 64px;
    text-align: right;
    flex-shrink: 0;
  }

  .trade-spacer {
    flex: 1;
  }

  /* ── Block Badge ── */
  .block-badge {
    font-size: 9px;
    font-weight: 700;
    text-transform: uppercase;
    padding: 2px 6px;
    border-radius: var(--radius-sm);
    background-color: var(--accent-bg);
    color: var(--accent-bright);
    border: 1px solid oklch(0.44 0.14 290 / 0.3);
  }

  /* ── Notional ── */
  .trade-notional {
    font-size: var(--text-xs);
    font-weight: 600;
    width: 80px;
    text-align: right;
    flex-shrink: 0;
  }

  .trade-notional--large {
    color: var(--accent-bright);
  }

  .trade-notional--normal {
    color: var(--text-primary);
  }

  /* ── Exchange ── */
  .trade-exchange {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    width: 48px;
    text-align: right;
    flex-shrink: 0;
    text-transform: uppercase;
  }

  /* ── Empty State ── */
  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 128px;
    font-size: var(--text-sm);
    color: var(--text-tertiary);
  }
</style>
