<!--
  OptionsChain.svelte
  Full options chain table with two-sided layout: Calls | Strike | Puts.
  Supports expiration selection, ITM highlighting, and virtual scrolling.
-->
<script lang="ts">
  import type { OptionContract } from '$lib/types/options';

  interface ChainData {
    expirations: string[];
    strikes: number[];
    calls: OptionContract[][];
    puts: OptionContract[][];
  }

  interface Props {
    symbol: string;
    chain?: ChainData;
    selectedExpiry?: string;
    class?: string;
  }

  let {
    symbol,
    chain,
    selectedExpiry = $bindable(''),
    class: className = ''
  }: Props = $props();

  // ---- Mock data when no chain provided ----
  const mockStrikes = [
    380, 385, 390, 395, 400, 405, 410, 415, 420, 425,
    430, 435, 440, 445, 450, 455, 460, 465, 470, 475
  ];
  const mockExpirations = ['2026-02-20', '2026-02-27', '2026-03-06', '2026-03-20', '2026-04-17', '2026-06-19'];
  const currentPrice = 432.50;

  function mockContract(strike: number, type: 'call' | 'put', _expiryIdx: number): OptionContract {
    const itm = type === 'call' ? strike < currentPrice : strike > currentPrice;
    const dist = Math.abs(strike - currentPrice);
    const iv = 0.25 + (dist / 200) + Math.random() * 0.05;
    const delta = type === 'call'
      ? Math.max(0.01, Math.min(0.99, 0.5 + (currentPrice - strike) / 80))
      : Math.min(-0.01, Math.max(-0.99, -0.5 + (currentPrice - strike) / 80));
    const last = Math.max(0.01, (itm ? dist : 0) + Math.random() * 8);
    const bid = Math.max(0, last - 0.05 - Math.random() * 0.15);
    const ask = last + 0.05 + Math.random() * 0.15;

    return {
      symbol: `${symbol}${type === 'call' ? 'C' : 'P'}${strike}`,
      strike,
      expiration: mockExpirations[_expiryIdx] ?? mockExpirations[0],
      type,
      bid: +bid.toFixed(2),
      ask: +ask.toFixed(2),
      last: +last.toFixed(2),
      volume: Math.floor(Math.random() * 5000),
      openInterest: Math.floor(Math.random() * 20000),
      iv: +iv.toFixed(4),
      delta: +delta.toFixed(4),
      gamma: +(Math.random() * 0.05).toFixed(4),
      theta: +(-Math.random() * 0.5).toFixed(4),
      vega: +(Math.random() * 0.3).toFixed(4),
      rho: +(Math.random() * 0.1 - 0.05).toFixed(4),
      inTheMoney: itm
    };
  }

  const defaultChain: ChainData = {
    expirations: mockExpirations,
    strikes: mockStrikes,
    calls: mockExpirations.map((_, ei) => mockStrikes.map((s) => mockContract(s, 'call', ei))),
    puts: mockExpirations.map((_, ei) => mockStrikes.map((s) => mockContract(s, 'put', ei)))
  };

  let activeChain = $derived(chain ?? defaultChain);
  let expirations = $derived(activeChain.expirations);
  let strikes = $derived(activeChain.strikes);

  // Initialize selectedExpiry
  $effect(() => {
    if (!selectedExpiry && expirations.length > 0) {
      selectedExpiry = expirations[0];
    }
  });

  let expiryIndex = $derived(Math.max(0, expirations.indexOf(selectedExpiry)));
  let calls = $derived(activeChain.calls[expiryIndex] ?? []);
  let puts = $derived(activeChain.puts[expiryIndex] ?? []);

  // ---- Virtual scrolling ----
  const ROW_HEIGHT = 32;
  const OVERSCAN = 6;
  let scrollContainer: HTMLDivElement | undefined = $state(undefined);
  let scrollTop = $state(0);
  let containerHeight = $state(400);

  function handleScroll() {
    if (scrollContainer) {
      scrollTop = scrollContainer.scrollTop;
    }
  }

  let totalHeight = $derived(strikes.length * ROW_HEIGHT);
  let startIdx = $derived(Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN));
  let endIdx = $derived(
    Math.min(strikes.length, Math.ceil((scrollTop + containerHeight) / ROW_HEIGHT) + OVERSCAN)
  );
  let visibleStrikes = $derived(strikes.slice(startIdx, endIdx));
  let offsetY = $derived(startIdx * ROW_HEIGHT);

  function formatExpiry(dateStr: string): string {
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  function formatIV(iv: number): string {
    return (iv * 100).toFixed(1) + '%';
  }

  function formatDelta(d: number): string {
    return d.toFixed(2);
  }

  const COLUMNS = ['Last', 'Chg', 'Bid', 'Ask', 'Vol', 'OI', 'IV', 'Delta'] as const;
</script>

<div class="panel flex flex-col overflow-hidden {className}">
  <!-- Header with symbol -->
  <div class="flex items-center gap-3 px-4 py-2 border-b border-[var(--border-subtle)]">
    <span class="text-sm font-semibold text-[var(--text-primary)]">{symbol}</span>
    <span class="text-xs text-[var(--text-tertiary)]">Options Chain</span>
  </div>

  <!-- Expiration tabs -->
  <div class="flex items-center gap-1 px-3 py-2 border-b border-[var(--border-subtle)] overflow-x-auto scrollbar-hidden">
    {#each expirations as exp}
      <button
        type="button"
        class="px-3 py-1.5 rounded text-xs font-medium whitespace-nowrap transition-colors duration-100
          {selectedExpiry === exp
            ? 'bg-[var(--accent-bg)] text-[var(--accent-bright)] border border-[oklch(0.44_0.14_290/0.3)]'
            : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--hover-overlay)]'
          }"
        onclick={() => (selectedExpiry = exp)}
      >
        {formatExpiry(exp)}
      </button>
    {/each}
  </div>

  <!-- Column headers -->
  <div class="grid chain-grid text-2xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider border-b border-[var(--border-subtle)] px-1">
    <!-- Call headers (reversed for right-alignment feel) -->
    {#each COLUMNS as col}
      <div class="px-1.5 py-1.5 text-right">{col}</div>
    {/each}
    <!-- Strike center -->
    <div class="px-2 py-1.5 text-center font-semibold text-[var(--text-secondary)]">Strike</div>
    <!-- Put headers -->
    {#each COLUMNS as col}
      <div class="px-1.5 py-1.5 text-right">{col}</div>
    {/each}
  </div>

  <!-- Virtual-scrolled rows -->
  <div
    class="flex-1 overflow-y-auto min-h-0"
    bind:this={scrollContainer}
    onscroll={handleScroll}
    bind:clientHeight={containerHeight}
  >
    <div style="height: {totalHeight}px; position: relative;">
      <div style="transform: translateY({offsetY}px);">
        {#each visibleStrikes as strike, vi}
          {@const idx = startIdx + vi}
          {@const call = calls[idx]}
          {@const put = puts[idx]}
          {@const callItm = call?.inTheMoney ?? false}
          {@const putItm = put?.inTheMoney ?? false}
          <div
            class="grid chain-grid text-xs mono-nums hover:bg-[var(--hover-overlay)] transition-colors duration-75 border-b border-[oklch(0.16_0.01_260)]"
            style="height: {ROW_HEIGHT}px;"
          >
            <!-- Call side -->
            {#if call}
              <div class="px-1.5 flex items-center justify-end {callItm ? 'bg-[oklch(0.15_0.04_155/0.4)]' : ''}">
                <span class="text-[var(--text-primary)]">{call.last.toFixed(2)}</span>
              </div>
              <div class="px-1.5 flex items-center justify-end {callItm ? 'bg-[oklch(0.15_0.04_155/0.4)]' : ''}">
                <span class="{call.last > call.bid ? 'text-[var(--bullish)]' : 'text-[var(--bearish)]'}">
                  {call.last > 0 ? (call.last - call.bid > 0 ? '+' : '') + (call.last - call.bid).toFixed(2) : '0.00'}
                </span>
              </div>
              <div class="px-1.5 flex items-center justify-end {callItm ? 'bg-[oklch(0.15_0.04_155/0.4)]' : ''}">
                <span class="text-[var(--text-secondary)]">{call.bid.toFixed(2)}</span>
              </div>
              <div class="px-1.5 flex items-center justify-end {callItm ? 'bg-[oklch(0.15_0.04_155/0.4)]' : ''}">
                <span class="text-[var(--text-secondary)]">{call.ask.toFixed(2)}</span>
              </div>
              <div class="px-1.5 flex items-center justify-end {callItm ? 'bg-[oklch(0.15_0.04_155/0.4)]' : ''}">
                <span class="text-[var(--text-secondary)]">{call.volume.toLocaleString()}</span>
              </div>
              <div class="px-1.5 flex items-center justify-end {callItm ? 'bg-[oklch(0.15_0.04_155/0.4)]' : ''}">
                <span class="text-[var(--text-tertiary)]">{call.openInterest.toLocaleString()}</span>
              </div>
              <div class="px-1.5 flex items-center justify-end {callItm ? 'bg-[oklch(0.15_0.04_155/0.4)]' : ''}">
                <span class="text-[var(--warning-dim)]">{formatIV(call.iv)}</span>
              </div>
              <div class="px-1.5 flex items-center justify-end {callItm ? 'bg-[oklch(0.15_0.04_155/0.4)]' : ''}">
                <span class="text-[var(--neutral)]">{formatDelta(call.delta)}</span>
              </div>
            {:else}
              {#each { length: 8 } as _}
                <div class="px-1.5 flex items-center justify-end">
                  <span class="text-[var(--text-disabled)]">--</span>
                </div>
              {/each}
            {/if}

            <!-- Strike center -->
            <div class="px-2 flex items-center justify-center bg-[var(--bg-elevated)] border-x border-[var(--border-subtle)]">
              <span class="font-semibold text-[var(--text-primary)] text-xs">{strike.toFixed(0)}</span>
            </div>

            <!-- Put side -->
            {#if put}
              <div class="px-1.5 flex items-center justify-end {putItm ? 'bg-[oklch(0.15_0.04_25/0.4)]' : ''}">
                <span class="text-[var(--text-primary)]">{put.last.toFixed(2)}</span>
              </div>
              <div class="px-1.5 flex items-center justify-end {putItm ? 'bg-[oklch(0.15_0.04_25/0.4)]' : ''}">
                <span class="{put.last > put.bid ? 'text-[var(--bullish)]' : 'text-[var(--bearish)]'}">
                  {put.last > 0 ? (put.last - put.bid > 0 ? '+' : '') + (put.last - put.bid).toFixed(2) : '0.00'}
                </span>
              </div>
              <div class="px-1.5 flex items-center justify-end {putItm ? 'bg-[oklch(0.15_0.04_25/0.4)]' : ''}">
                <span class="text-[var(--text-secondary)]">{put.bid.toFixed(2)}</span>
              </div>
              <div class="px-1.5 flex items-center justify-end {putItm ? 'bg-[oklch(0.15_0.04_25/0.4)]' : ''}">
                <span class="text-[var(--text-secondary)]">{put.ask.toFixed(2)}</span>
              </div>
              <div class="px-1.5 flex items-center justify-end {putItm ? 'bg-[oklch(0.15_0.04_25/0.4)]' : ''}">
                <span class="text-[var(--text-secondary)]">{put.volume.toLocaleString()}</span>
              </div>
              <div class="px-1.5 flex items-center justify-end {putItm ? 'bg-[oklch(0.15_0.04_25/0.4)]' : ''}">
                <span class="text-[var(--text-tertiary)]">{put.openInterest.toLocaleString()}</span>
              </div>
              <div class="px-1.5 flex items-center justify-end {putItm ? 'bg-[oklch(0.15_0.04_25/0.4)]' : ''}">
                <span class="text-[var(--warning-dim)]">{formatIV(put.iv)}</span>
              </div>
              <div class="px-1.5 flex items-center justify-end {putItm ? 'bg-[oklch(0.15_0.04_25/0.4)]' : ''}">
                <span class="text-[var(--neutral)]">{formatDelta(put.delta)}</span>
              </div>
            {:else}
              {#each { length: 8 } as _}
                <div class="px-1.5 flex items-center justify-end">
                  <span class="text-[var(--text-disabled)]">--</span>
                </div>
              {/each}
            {/if}
          </div>
        {/each}
      </div>
    </div>
  </div>

  <!-- Footer -->
  <div class="flex items-center justify-between px-4 py-1.5 border-t border-[var(--border-subtle)] text-2xs text-[var(--text-tertiary)]">
    <span>{strikes.length} strikes</span>
    <span>Exp: {selectedExpiry}</span>
  </div>
</div>

<style>
  .chain-grid {
    grid-template-columns:
      repeat(8, minmax(48px, 1fr))  /* calls */
      64px                           /* strike */
      repeat(8, minmax(48px, 1fr)); /* puts */
  }
</style>
