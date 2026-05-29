<script lang="ts">
  import DarkPoolFeed from '$components/institutional/DarkPoolFeed.svelte';
  import ShortInterest from '$components/institutional/ShortInterest.svelte';
  import ETFFlows from '$components/institutional/ETFFlows.svelte';
  import ExportToolbar from '$lib/components/ui/ExportToolbar.svelte';

  let activeTab = $state<'darkpool' | 'short' | 'etf'>('darkpool');

  const tabs: { id: 'darkpool' | 'short' | 'etf'; label: string }[] = [
    { id: 'darkpool', label: 'Dark Pool' },
    { id: 'short', label: 'Short Interest' },
    { id: 'etf', label: 'ETF Flows' },
  ];

  const now = Date.now();

  const darkPoolTrades = [
    { symbol: 'AAPL',  price: 178.50, size: 5000,  timestamp: now - 8_000,   exchange: 'FADF' },
    { symbol: 'MSFT',  price: 415.20, size: 12000, timestamp: now - 22_000,  exchange: 'UBSS' },
    { symbol: 'NVDA',  price: 875.30, size: 3500,  timestamp: now - 45_000,  exchange: 'CDRG' },
    { symbol: 'TSLA',  price: 245.10, size: 8200,  timestamp: now - 67_000,  exchange: 'FADF' },
    { symbol: 'AMZN',  price: 185.60, size: 15000, timestamp: now - 89_000,  exchange: 'JNST' },
    { symbol: 'META',  price: 505.80, size: 4200,  timestamp: now - 112_000, exchange: 'UBSS' },
    { symbol: 'GOOGL', price: 152.30, size: 9800,  timestamp: now - 135_000, exchange: 'CDRG' },
    { symbol: 'JPM',   price: 198.75, size: 7500,  timestamp: now - 158_000, exchange: 'FADF' },
    { symbol: 'AMD',   price: 165.40, size: 6300,  timestamp: now - 180_000, exchange: 'JNST' },
    { symbol: 'NFLX',  price: 628.40, size: 2100,  timestamp: now - 205_000, exchange: 'UBSS' },
  ];

  const shortInterestData = [
    { symbol: 'GME',  shortInterest: 45_200_000, shortPercent: 24.5, daysToCover: 4.2, change: 2.3 },
    { symbol: 'AMC',  shortInterest: 92_100_000, shortPercent: 21.8, daysToCover: 3.1, change: -1.5 },
    { symbol: 'CVNA', shortInterest: 28_600_000, shortPercent: 32.4, daysToCover: 5.6, change: 4.8 },
    { symbol: 'BBBY', shortInterest: 15_800_000, shortPercent: 42.1, daysToCover: 7.2, change: 1.2 },
    { symbol: 'RIVN', shortInterest: 38_400_000, shortPercent: 18.6, daysToCover: 2.8, change: -0.8 },
    { symbol: 'MARA', shortInterest: 22_100_000, shortPercent: 27.3, daysToCover: 3.9, change: 3.1 },
    { symbol: 'UPST', shortInterest: 12_500_000, shortPercent: 35.7, daysToCover: 6.4, change: -2.4 },
    { symbol: 'LCID', shortInterest: 48_900_000, shortPercent: 15.2, daysToCover: 2.1, change: 0.6 },
  ];

  const etfFlowData = [
    { symbol: 'SPY',  name: 'SPDR S&P 500 ETF',         flow: 2_800_000_000,  aum: 520_000_000_000, flowPercent: 0.54 },
    { symbol: 'QQQ',  name: 'Invesco QQQ Trust',         flow: 1_200_000_000,  aum: 245_000_000_000, flowPercent: 0.49 },
    { symbol: 'IWM',  name: 'iShares Russell 2000',      flow: -450_000_000,   aum: 62_000_000_000,  flowPercent: -0.73 },
    { symbol: 'XLF',  name: 'Financial Select Sector',   flow: 680_000_000,    aum: 38_000_000_000,  flowPercent: 1.79 },
    { symbol: 'XLK',  name: 'Technology Select Sector',  flow: 920_000_000,    aum: 55_000_000_000,  flowPercent: 1.67 },
    { symbol: 'XLE',  name: 'Energy Select Sector',      flow: -320_000_000,   aum: 28_000_000_000,  flowPercent: -1.14 },
    { symbol: 'GLD',  name: 'SPDR Gold Shares',          flow: 540_000_000,    aum: 58_000_000_000,  flowPercent: 0.93 },
    { symbol: 'TLT',  name: 'iShares 20+ Year Treasury', flow: -780_000_000,   aum: 42_000_000_000,  flowPercent: -1.86 },
  ];
</script>

<svelte:head>
  <title>Institutional - Scanify</title>
</svelte:head>

<div class="flex flex-col h-full overflow-hidden">
  <!-- Header -->
  <div class="flex items-center justify-between px-5 py-3 shrink-0" style="border-bottom: 1px solid var(--border-subtle);">
    <h1 class="text-lg font-bold" style="color: var(--text-primary);">Institutional</h1>
    <ExportToolbar source="institutional" />
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
    {#if activeTab === 'darkpool'}
      <DarkPoolFeed trades={darkPoolTrades} class="h-full" />

    {:else if activeTab === 'short'}
      <ShortInterest data={shortInterestData} class="h-full" />

    {:else if activeTab === 'etf'}
      <ETFFlows data={etfFlowData} class="h-full" />
    {/if}
  </div>
</div>
