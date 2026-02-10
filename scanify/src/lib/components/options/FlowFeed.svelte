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

<div class="panel flex flex-col overflow-hidden {className}">
  <!-- Header -->
  <div class="flex items-center justify-between px-4 py-2 border-b border-[var(--border-subtle)]">
    <div class="flex items-center gap-2">
      <div class="w-2 h-2 rounded-full bg-[var(--bullish)] signal-ping"></div>
      <span class="text-sm font-semibold text-[var(--text-primary)]">Options Flow</span>
      <span class="text-2xs text-[var(--text-tertiary)]">({items.length})</span>
    </div>
    <button
      type="button"
      class="text-2xs px-2 py-1 rounded transition-colors
        {autoScroll
          ? 'bg-[var(--accent-bg)] text-[var(--accent-bright)]'
          : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'
        }"
      onclick={() => (autoScroll = !autoScroll)}
    >
      {autoScroll ? 'AUTO' : 'PAUSED'}
    </button>
  </div>

  <!-- Feed -->
  <div
    class="flex-1 overflow-y-auto min-h-0 space-y-1 p-2"
    bind:this={feedContainer}
    onmouseenter={handleMouseEnter}
    onmouseleave={handleMouseLeave}
  >
    {#each sortedItems as item (item.id)}
      {@const isCall = item.type === 'call'}
      {@const tintBg = isCall ? 'bg-[oklch(0.13_0.03_155/0.5)]' : 'bg-[oklch(0.13_0.03_25/0.5)]'}
      {@const borderColor = item.isUnusual
        ? (isCall ? 'border-[var(--bullish-dim)]' : 'border-[var(--bearish-dim)]')
        : 'border-[var(--border-subtle)]'
      }

      <div
        class="flex items-center gap-2 px-3 py-2 rounded-md border transition-all duration-150 hover:bg-[var(--hover-overlay)]
          {tintBg} {borderColor}
          {item.isUnusual ? 'shadow-[0_0_12px_0_oklch(0.6_0.15_85/0.15)]' : ''}"
      >
        <!-- Symbol -->
        <span class="text-xs font-semibold text-[var(--text-primary)] w-14 shrink-0">{item.symbol}</span>

        <!-- Type badge -->
        <span
          class="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded-sm shrink-0
            {isCall
              ? 'bg-[var(--bullish-bg)] text-[var(--bullish-bright)] border border-[oklch(0.45_0.12_155/0.3)]'
              : 'bg-[var(--bearish-bg)] text-[var(--bearish-bright)] border border-[oklch(0.42_0.12_25/0.3)]'
            }"
        >
          {item.type === 'call' ? 'C' : 'P'}
        </span>

        <!-- Strike @ Expiration -->
        <span class="text-xs mono-nums text-[var(--text-secondary)] shrink-0">
          {item.strike}@{formatExpShort(item.expiration)}
        </span>

        <!-- Side -->
        <span
          class="text-[10px] uppercase font-medium shrink-0
            {item.side === 'buy' ? 'text-[var(--bullish)]' : 'text-[var(--bearish)]'}"
        >
          {item.side}
        </span>

        <!-- Spacer -->
        <div class="flex-1"></div>

        <!-- Badges -->
        {#if item.isSweep}
          <span class="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-sm bg-[var(--accent-bg)] text-[var(--accent-bright)] border border-[oklch(0.44_0.14_290/0.3)]">
            SWEEP
          </span>
        {/if}
        {#if item.isUnusual}
          <span class="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-sm bg-[var(--warning-bg)] text-[var(--warning-bright)] border border-[oklch(0.52_0.10_85/0.3)]">
            UNUSUAL
          </span>
        {/if}

        <!-- Size -->
        <span class="text-xs mono-nums text-[var(--text-secondary)] w-12 text-right shrink-0">
          {item.size.toLocaleString()}
        </span>

        <!-- Premium -->
        <span class="text-xs mono-nums font-semibold text-[var(--text-primary)] w-16 text-right shrink-0">
          {formatPremium(item.premium)}
        </span>

        <!-- Time -->
        <span class="text-2xs text-[var(--text-tertiary)] w-16 text-right shrink-0">
          {formatTime(typeof item.timestamp === 'string' ? new Date(item.timestamp).getTime() : item.timestamp)}
        </span>
      </div>
    {/each}

    {#if items.length === 0}
      <div class="flex items-center justify-center h-32 text-sm text-[var(--text-tertiary)]">
        Waiting for options flow data...
      </div>
    {/if}
  </div>
</div>
