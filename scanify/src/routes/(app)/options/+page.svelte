<script lang="ts">
  import FlowFeed from '$components/options/FlowFeed.svelte';

  let activeTab = $state<'flow' | 'unusual' | 'chain'>('flow');

  const tabs: { id: 'flow' | 'unusual' | 'chain'; label: string }[] = [
    { id: 'flow', label: 'Flow' },
    { id: 'unusual', label: 'Unusual Activity' },
    { id: 'chain', label: 'Chain' },
  ];

  const now = Date.now();

  const flowItems = [
    { id: 'f1',  symbol: 'AAPL',  timestamp: new Date(now - 12_000).toISOString(),  type: 'call' as const, strike: 180, expiration: '2026-03-21', side: 'buy' as const,  size: 500,  premium: 245_000,   isUnusual: true,  isSweep: false },
    { id: 'f2',  symbol: 'NVDA',  timestamp: new Date(now - 25_000).toISOString(),  type: 'call' as const, strike: 900, expiration: '2026-04-17', side: 'buy' as const,  size: 1500, premium: 2_250_000, isUnusual: true,  isSweep: true },
    { id: 'f3',  symbol: 'TSLA',  timestamp: new Date(now - 38_000).toISOString(),  type: 'put' as const,  strike: 240, expiration: '2026-03-14', side: 'buy' as const,  size: 1200, premium: 456_000,   isUnusual: false, isSweep: false },
    { id: 'f4',  symbol: 'MSFT',  timestamp: new Date(now - 52_000).toISOString(),  type: 'call' as const, strike: 420, expiration: '2026-03-21', side: 'sell' as const, size: 200,  premium: 178_000,   isUnusual: false, isSweep: false },
    { id: 'f5',  symbol: 'AMD',   timestamp: new Date(now - 68_000).toISOString(),  type: 'call' as const, strike: 170, expiration: '2026-04-17', side: 'buy' as const,  size: 800,  premium: 320_000,   isUnusual: true,  isSweep: true },
    { id: 'f6',  symbol: 'META',  timestamp: new Date(now - 79_000).toISOString(),  type: 'put' as const,  strike: 500, expiration: '2026-03-14', side: 'sell' as const, size: 150,  premium: 195_000,   isUnusual: false, isSweep: false },
    { id: 'f7',  symbol: 'GOOGL', timestamp: new Date(now - 95_000).toISOString(),  type: 'call' as const, strike: 155, expiration: '2026-04-17', side: 'buy' as const,  size: 600,  premium: 210_000,   isUnusual: false, isSweep: false },
    { id: 'f8',  symbol: 'AMZN',  timestamp: new Date(now - 112_000).toISOString(), type: 'call' as const, strike: 190, expiration: '2026-03-21', side: 'buy' as const,  size: 400,  premium: 168_000,   isUnusual: true,  isSweep: false },
    { id: 'f9',  symbol: 'SPY',   timestamp: new Date(now - 130_000).toISOString(), type: 'put' as const,  strike: 495, expiration: '2026-03-14', side: 'buy' as const,  size: 2000, premium: 540_000,   isUnusual: true,  isSweep: true },
    { id: 'f10', symbol: 'QQQ',   timestamp: new Date(now - 145_000).toISOString(), type: 'call' as const, strike: 440, expiration: '2026-04-17', side: 'buy' as const,  size: 350,  premium: 287_000,   isUnusual: false, isSweep: false },
  ];

  const unusualData = [
    { symbol: 'NVDA', strike: '900C', expiry: 'Apr 17', volume: 12_500, oi: 3200, ratio: 3.9, premium: '$8.9M', sentiment: 'Bullish' },
    { symbol: 'AAPL', strike: '185C', expiry: 'Mar 21', volume: 8_400,  oi: 5100, ratio: 1.6, premium: '$2.1M', sentiment: 'Bullish' },
    { symbol: 'TSLA', strike: '230P', expiry: 'Mar 14', volume: 6_200,  oi: 1800, ratio: 3.4, premium: '$3.4M', sentiment: 'Bearish' },
    { symbol: 'SPY',  strike: '490P', expiry: 'Mar 21', volume: 15_600, oi: 8900, ratio: 1.8, premium: '$5.2M', sentiment: 'Bearish' },
    { symbol: 'AMD',  strike: '175C', expiry: 'Apr 17', volume: 9_800,  oi: 2400, ratio: 4.1, premium: '$1.8M', sentiment: 'Bullish' },
  ];

  function sentimentColor(s: string): string {
    return s === 'Bullish' ? 'var(--bullish)' : 'var(--bearish)';
  }

  function sentimentBg(s: string): string {
    return s === 'Bullish' ? 'var(--bullish-bg)' : 'var(--bearish-bg)';
  }
</script>

<svelte:head>
  <title>Options - Scanify</title>
</svelte:head>

<div class="flex flex-col h-full overflow-hidden">
  <!-- Header -->
  <div class="flex items-center justify-between px-5 py-3 shrink-0" style="border-bottom: 1px solid var(--border-subtle);">
    <h1 class="text-lg font-bold" style="color: var(--text-primary);">Options</h1>
    <a href="/options/flow" class="text-xs font-medium" style="color: var(--accent);">Full Flow View</a>
  </div>

  <!-- Tab switcher -->
  <div class="flex gap-1 px-5 py-3 shrink-0" style="border-bottom: 1px solid var(--border-subtle);">
    {#each tabs as tab (tab.id)}
      <button
        type="button"
        onclick={() => activeTab = tab.id}
        class="rounded-lg px-4 py-2 text-xs font-medium transition-all"
        style="background: {activeTab === tab.id ? 'var(--accent-bg)' : 'var(--bg-elevated)'};
               color: {activeTab === tab.id ? 'var(--accent-bright)' : 'var(--text-secondary)'};
               border: 1px solid {activeTab === tab.id ? 'var(--accent-dim)' : 'var(--border-subtle)'};"
      >
        {tab.label}
      </button>
    {/each}
  </div>

  <!-- Tab content -->
  <div class="flex-1 overflow-hidden min-h-0">
    {#if activeTab === 'flow'}
      <FlowFeed items={flowItems} class="h-full" />

    {:else if activeTab === 'unusual'}
      <!-- Unusual Activity Table -->
      <div class="h-full overflow-auto">
        <div class="panel m-5 overflow-hidden">
          <div class="flex items-center justify-between px-4 py-2.5" style="border-bottom: 1px solid var(--border-subtle);">
            <span class="text-sm font-semibold" style="color: var(--text-primary);">Unusual Options Activity</span>
            <span class="text-2xs" style="color: var(--text-tertiary);">{unusualData.length} entries</span>
          </div>
          <div class="overflow-auto">
            <table class="w-full text-xs">
              <thead class="sticky top-0" style="background: var(--bg-elevated);">
                <tr style="border-bottom: 1px solid var(--border-subtle);">
                  <th class="text-left px-4 py-2.5 font-medium" style="color: var(--text-tertiary);">Symbol</th>
                  <th class="text-left px-3 py-2.5 font-medium" style="color: var(--text-tertiary);">Strike</th>
                  <th class="text-left px-3 py-2.5 font-medium" style="color: var(--text-tertiary);">Expiry</th>
                  <th class="text-right px-3 py-2.5 font-medium" style="color: var(--text-tertiary);">Volume</th>
                  <th class="text-right px-3 py-2.5 font-medium" style="color: var(--text-tertiary);">OI</th>
                  <th class="text-right px-3 py-2.5 font-medium" style="color: var(--text-tertiary);">Vol/OI</th>
                  <th class="text-right px-3 py-2.5 font-medium" style="color: var(--text-tertiary);">Premium</th>
                  <th class="text-center px-3 py-2.5 font-medium" style="color: var(--text-tertiary);">Sentiment</th>
                </tr>
              </thead>
              <tbody>
                {#each unusualData as row, i (row.symbol + row.strike)}
                  <tr
                    class="transition-colors"
                    style="background: {i % 2 === 0 ? 'var(--bg-surface)' : 'transparent'}; border-bottom: 1px solid var(--border-subtle);"
                  >
                    <td class="px-4 py-2.5 font-bold font-mono" style="color: var(--text-primary);">{row.symbol}</td>
                    <td class="px-3 py-2.5 font-mono" style="color: var(--text-secondary);">{row.strike}</td>
                    <td class="px-3 py-2.5" style="color: var(--text-tertiary);">{row.expiry}</td>
                    <td class="px-3 py-2.5 text-right font-mono" style="color: var(--text-secondary);">{row.volume.toLocaleString()}</td>
                    <td class="px-3 py-2.5 text-right font-mono" style="color: var(--text-secondary);">{row.oi.toLocaleString()}</td>
                    <td class="px-3 py-2.5 text-right font-mono font-bold" style="color: var(--warning-bright);">{row.ratio.toFixed(1)}x</td>
                    <td class="px-3 py-2.5 text-right font-mono font-semibold" style="color: var(--text-primary);">{row.premium}</td>
                    <td class="px-3 py-2.5 text-center">
                      <span
                        class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase"
                        style="background: {sentimentBg(row.sentiment)};
                               color: {sentimentColor(row.sentiment)};
                               border: 1px solid {row.sentiment === 'Bullish' ? 'oklch(0.45 0.12 155 / 0.3)' : 'oklch(0.42 0.12 25 / 0.3)'};"
                      >
                        {row.sentiment}
                      </span>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
      </div>

    {:else if activeTab === 'chain'}
      <!-- Chain placeholder -->
      <div class="flex flex-col items-center justify-center h-full gap-4">
        <div class="w-16 h-16 rounded-xl flex items-center justify-center" style="background: var(--bg-elevated); border: 1px solid var(--border-subtle);">
          <svg class="h-8 w-8" style="color: var(--text-disabled);" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <p class="text-sm font-medium" style="color: var(--text-secondary);">Select a symbol to view options chain</p>
        <p class="text-xs" style="color: var(--text-tertiary);">Use the search bar or click a symbol from the flow</p>
      </div>
    {/if}
  </div>
</div>
