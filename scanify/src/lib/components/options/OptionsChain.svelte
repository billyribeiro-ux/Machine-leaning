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

<div class="panel chain-wrapper {className}">
  <!-- Header with symbol -->
  <div class="chain-header">
    <span class="chain-symbol">{symbol}</span>
    <span class="chain-label">Options Chain</span>
  </div>

  <!-- Expiration tabs -->
  <div class="expiry-tabs">
    {#each expirations as exp}
      <button
        type="button"
        class="expiry-btn {selectedExpiry === exp ? 'expiry-btn--active' : ''}"
        onclick={() => (selectedExpiry = exp)}
      >
        {formatExpiry(exp)}
      </button>
    {/each}
  </div>

  <!-- Column headers -->
  <div class="chain-grid col-headers">
    <!-- Call headers (reversed for right-alignment feel) -->
    {#each COLUMNS as col}
      <div class="col-header-cell">{col}</div>
    {/each}
    <!-- Strike center -->
    <div class="col-header-strike">Strike</div>
    <!-- Put headers -->
    {#each COLUMNS as col}
      <div class="col-header-cell">{col}</div>
    {/each}
  </div>

  <!-- Virtual-scrolled rows -->
  <div
    class="chain-scroll"
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
            class="chain-grid chain-row mono-nums"
            style="height: {ROW_HEIGHT}px;"
          >
            <!-- Call side -->
            {#if call}
              <div class="data-cell {callItm ? 'itm-call' : ''}">
                <span class="text-primary">{call.last.toFixed(2)}</span>
              </div>
              <div class="data-cell {callItm ? 'itm-call' : ''}">
                <span class="{call.last > call.bid ? 'text-bullish' : 'text-bearish'}">
                  {call.last > 0 ? (call.last - call.bid > 0 ? '+' : '') + (call.last - call.bid).toFixed(2) : '0.00'}
                </span>
              </div>
              <div class="data-cell {callItm ? 'itm-call' : ''}">
                <span class="text-secondary">{call.bid.toFixed(2)}</span>
              </div>
              <div class="data-cell {callItm ? 'itm-call' : ''}">
                <span class="text-secondary">{call.ask.toFixed(2)}</span>
              </div>
              <div class="data-cell {callItm ? 'itm-call' : ''}">
                <span class="text-secondary">{call.volume.toLocaleString()}</span>
              </div>
              <div class="data-cell {callItm ? 'itm-call' : ''}">
                <span class="text-tertiary">{call.openInterest.toLocaleString()}</span>
              </div>
              <div class="data-cell {callItm ? 'itm-call' : ''}">
                <span class="text-warning">{formatIV(call.iv)}</span>
              </div>
              <div class="data-cell {callItm ? 'itm-call' : ''}">
                <span class="text-neutral">{formatDelta(call.delta)}</span>
              </div>
            {:else}
              {#each { length: 8 } as _}
                <div class="data-cell">
                  <span class="text-disabled">--</span>
                </div>
              {/each}
            {/if}

            <!-- Strike center -->
            <div class="strike-cell">
              <span class="strike-value">{strike.toFixed(0)}</span>
            </div>

            <!-- Put side -->
            {#if put}
              <div class="data-cell {putItm ? 'itm-put' : ''}">
                <span class="text-primary">{put.last.toFixed(2)}</span>
              </div>
              <div class="data-cell {putItm ? 'itm-put' : ''}">
                <span class="{put.last > put.bid ? 'text-bullish' : 'text-bearish'}">
                  {put.last > 0 ? (put.last - put.bid > 0 ? '+' : '') + (put.last - put.bid).toFixed(2) : '0.00'}
                </span>
              </div>
              <div class="data-cell {putItm ? 'itm-put' : ''}">
                <span class="text-secondary">{put.bid.toFixed(2)}</span>
              </div>
              <div class="data-cell {putItm ? 'itm-put' : ''}">
                <span class="text-secondary">{put.ask.toFixed(2)}</span>
              </div>
              <div class="data-cell {putItm ? 'itm-put' : ''}">
                <span class="text-secondary">{put.volume.toLocaleString()}</span>
              </div>
              <div class="data-cell {putItm ? 'itm-put' : ''}">
                <span class="text-tertiary">{put.openInterest.toLocaleString()}</span>
              </div>
              <div class="data-cell {putItm ? 'itm-put' : ''}">
                <span class="text-warning">{formatIV(put.iv)}</span>
              </div>
              <div class="data-cell {putItm ? 'itm-put' : ''}">
                <span class="text-neutral">{formatDelta(put.delta)}</span>
              </div>
            {:else}
              {#each { length: 8 } as _}
                <div class="data-cell">
                  <span class="text-disabled">--</span>
                </div>
              {/each}
            {/if}
          </div>
        {/each}
      </div>
    </div>
  </div>

  <!-- Footer -->
  <div class="chain-footer">
    <span>{strikes.length} strikes</span>
    <span>Exp: {selectedExpiry}</span>
  </div>
</div>

<style>
  /* ---- Layout ---- */
  .chain-wrapper {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .chain-grid {
    display: grid;
    grid-template-columns:
      repeat(8, minmax(48px, 1fr))  /* calls */
      64px                           /* strike */
      repeat(8, minmax(48px, 1fr)); /* puts */
  }

  /* ---- Header ---- */
  .chain-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 16px;
    border-bottom: 1px solid var(--border-subtle);
  }

  .chain-symbol {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .chain-label {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
  }

  /* ---- Expiration tabs ---- */
  .expiry-tabs {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border-subtle);
    overflow-x: auto;
    scrollbar-width: none;
  }

  .expiry-tabs::-webkit-scrollbar {
    display: none;
  }

  .expiry-btn {
    padding: 6px 12px;
    border-radius: var(--radius-sm);
    font-size: var(--text-xs);
    font-weight: 500;
    white-space: nowrap;
    transition: color 150ms, background-color 150ms, border-color 150ms;
    color: var(--text-secondary);
    border: 1px solid transparent;
    background: transparent;
    cursor: pointer;
  }

  .expiry-btn:hover {
    color: var(--text-primary);
    background-color: var(--hover-overlay);
  }

  .expiry-btn--active {
    background-color: var(--accent-bg);
    color: var(--accent-bright);
    border-color: oklch(0.44 0.14 290 / 0.3);
  }

  .expiry-btn--active:hover {
    background-color: var(--accent-bg);
    color: var(--accent-bright);
  }

  /* ---- Column headers ---- */
  .col-headers {
    font-size: var(--text-2xs);
    font-weight: 500;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid var(--border-subtle);
    padding-left: 4px;
    padding-right: 4px;
  }

  .col-header-cell {
    padding: 6px;
    text-align: right;
  }

  .col-header-strike {
    padding: 6px 8px;
    text-align: center;
    font-weight: 600;
    color: var(--text-secondary);
  }

  /* ---- Scroll container ---- */
  .chain-scroll {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
  }

  /* ---- Data rows ---- */
  .chain-row {
    font-size: var(--text-xs);
    transition: background-color 75ms;
    border-bottom: 1px solid oklch(0.16 0.01 260);
  }

  .chain-row:hover {
    background-color: var(--hover-overlay);
  }

  .data-cell {
    padding-left: 6px;
    padding-right: 6px;
    display: flex;
    align-items: center;
    justify-content: flex-end;
  }

  .itm-call {
    background-color: oklch(0.15 0.04 155 / 0.4);
  }

  .itm-put {
    background-color: oklch(0.15 0.04 25 / 0.4);
  }

  /* ---- Strike column ---- */
  .strike-cell {
    padding-left: 8px;
    padding-right: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: var(--bg-elevated);
    border-left: 1px solid var(--border-subtle);
    border-right: 1px solid var(--border-subtle);
  }

  .strike-value {
    font-weight: 600;
    color: var(--text-primary);
    font-size: var(--text-xs);
  }

  /* ---- Text color utilities ---- */
  .text-primary {
    color: var(--text-primary);
  }

  .text-secondary {
    color: var(--text-secondary);
  }

  .text-tertiary {
    color: var(--text-tertiary);
  }

  .text-disabled {
    color: var(--text-disabled);
  }

  .text-bullish {
    color: var(--bullish);
  }

  .text-bearish {
    color: var(--bearish);
  }

  .text-warning {
    color: var(--warning-dim);
  }

  .text-neutral {
    color: var(--neutral);
  }

  /* ---- Footer ---- */
  .chain-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 16px;
    border-top: 1px solid var(--border-subtle);
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
  }
</style>
