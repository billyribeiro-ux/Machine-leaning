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

<div class="panel flex flex-col overflow-hidden {className}">
  <!-- Header -->
  <div class="flex items-center justify-between px-4 py-2.5 border-b border-[var(--border-subtle)]">
    <div class="flex items-center gap-2">
      <div class="w-2 h-2 rounded-full bg-[var(--accent)] signal-ping"></div>
      <span class="text-sm font-semibold text-[var(--text-primary)]">Dark Pool Feed</span>
      <span class="text-2xs text-[var(--text-tertiary)]">({trades.length})</span>
    </div>
    <button
      type="button"
      class="text-2xs px-2 py-1 rounded transition-colors
        {autoScroll
          ? 'bg-[var(--accent-bg)] text-[var(--accent-bright)]'
          : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'}"
      onclick={() => (autoScroll = !autoScroll)}
    >
      {autoScroll ? 'AUTO' : 'PAUSED'}
    </button>
  </div>

  <!-- Summary bar -->
  <div class="flex items-center gap-4 px-4 py-2 bg-[var(--bg-elevated)] border-b border-[var(--border-subtle)]">
    <div class="flex items-center gap-1.5">
      <span class="text-2xs text-[var(--text-tertiary)]">Total Vol:</span>
      <span class="mono-nums text-xs font-bold text-[var(--text-primary)]">{formatNotional(runningTotal)}</span>
    </div>
    <div class="flex items-center gap-1.5">
      <span class="text-2xs text-[var(--text-tertiary)]">Large Blocks:</span>
      <span class="mono-nums text-xs font-bold text-[var(--accent-bright)]">{largeBlockCount}</span>
    </div>
  </div>

  <!-- Feed -->
  <div
    class="flex-1 overflow-y-auto min-h-0 space-y-1 p-2"
    bind:this={feedContainer}
    onmouseenter={() => (isHovered = true)}
    onmouseleave={() => (isHovered = false)}
  >
    {#each sortedTrades as trade, idx (trade.timestamp + '-' + trade.symbol + '-' + idx)}
      {@const large = isLargeBlock(trade)}
      {@const notional = notionalValue(trade)}

      <div
        class="flex items-center gap-2 px-3 py-2 rounded-md border transition-all duration-150 hover:bg-[var(--hover-overlay)]
          {large
            ? 'bg-[oklch(0.14_0.03_290/0.4)] border-[var(--accent-dim)] shadow-[0_0_12px_0_oklch(0.6_0.15_290/0.12)]'
            : 'bg-[var(--bg-surface)] border-[var(--border-subtle)]'}"
      >
        <!-- Time -->
        <span class="text-2xs mono-nums text-[var(--text-tertiary)] w-16 shrink-0">
          {formatTime(trade.timestamp)}
        </span>

        <!-- Symbol -->
        <span class="text-xs font-semibold text-[var(--text-primary)] w-14 shrink-0">{trade.symbol}</span>

        <!-- Price -->
        <span class="mono-nums text-xs text-[var(--text-secondary)] w-20 text-right shrink-0">
          {formatPrice(trade.price)}
        </span>

        <!-- Size -->
        <span class="mono-nums text-xs text-[var(--text-secondary)] w-16 text-right shrink-0">
          {trade.size.toLocaleString()}
        </span>

        <!-- Spacer -->
        <div class="flex-1"></div>

        <!-- Large block badge -->
        {#if large}
          <span class="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-sm bg-[var(--accent-bg)] text-[var(--accent-bright)] border border-[oklch(0.44_0.14_290/0.3)]">
            BLOCK
          </span>
        {/if}

        <!-- Notional -->
        <span class="mono-nums text-xs font-semibold w-20 text-right shrink-0 {large ? 'text-[var(--accent-bright)]' : 'text-[var(--text-primary)]'}">
          {formatNotional(notional)}
        </span>

        <!-- Exchange -->
        <span class="text-2xs text-[var(--text-tertiary)] w-12 text-right shrink-0 uppercase">
          {trade.exchange}
        </span>
      </div>
    {/each}

    {#if trades.length === 0}
      <div class="flex items-center justify-center h-32 text-sm text-[var(--text-tertiary)]">
        Waiting for dark pool data...
      </div>
    {/if}
  </div>
</div>
