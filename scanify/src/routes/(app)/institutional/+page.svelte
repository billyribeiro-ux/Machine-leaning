<script lang="ts">
  import Tabs from '$lib/components/ui/Tabs.svelte';

  let activeTab = $state('darkpool');

  const tabs = [
    { id: 'darkpool', label: 'Dark Pool' },
    { id: 'short', label: 'Short Interest' },
    { id: 'etf', label: 'ETF Flows' },
  ];

  // ---- 15 mock dark pool trades ----
  const now = Date.now();
  const darkPoolTrades = [
    { id: 'dp1',  symbol: 'NVDA',  price: 876.20, size: 125_000,  premium: 109_525_000, time: now - 12_000,  sentiment: 'bullish' as const },
    { id: 'dp2',  symbol: 'AAPL',  price: 178.90, size: 450_000,  premium: 80_505_000,  time: now - 45_000,  sentiment: 'neutral' as const },
    { id: 'dp3',  symbol: 'TSLA',  price: 244.50, size: 200_000,  premium: 48_900_000,  time: now - 78_000,  sentiment: 'bearish' as const },
    { id: 'dp4',  symbol: 'MSFT',  price: 416.10, size: 180_000,  premium: 74_898_000,  time: now - 120_000, sentiment: 'bullish' as const },
    { id: 'dp5',  symbol: 'META',  price: 506.30, size: 95_000,   premium: 48_098_500,  time: now - 165_000, sentiment: 'bullish' as const },
    { id: 'dp6',  symbol: 'AMZN',  price: 185.20, size: 320_000,  premium: 59_264_000,  time: now - 210_000, sentiment: 'neutral' as const },
    { id: 'dp7',  symbol: 'GOOGL', price: 152.80, size: 275_000,  premium: 42_020_000,  time: now - 260_000, sentiment: 'bearish' as const },
    { id: 'dp8',  symbol: 'JPM',   price: 199.10, size: 150_000,  premium: 29_865_000,  time: now - 310_000, sentiment: 'bullish' as const },
    { id: 'dp9',  symbol: 'AMD',   price: 166.20, size: 280_000,  premium: 46_536_000,  time: now - 360_000, sentiment: 'bullish' as const },
    { id: 'dp10', symbol: 'COIN',  price: 226.40, size: 110_000,  premium: 24_904_000,  time: now - 420_000, sentiment: 'bullish' as const },
    { id: 'dp11', symbol: 'NFLX',  price: 629.10, size: 65_000,   premium: 40_891_500,  time: now - 480_000, sentiment: 'neutral' as const },
    { id: 'dp12', symbol: 'BA',    price: 199.50, size: 185_000,  premium: 36_907_500,  time: now - 540_000, sentiment: 'bullish' as const },
    { id: 'dp13', symbol: 'XOM',   price: 105.20, size: 220_000,  premium: 23_144_000,  time: now - 600_000, sentiment: 'neutral' as const },
    { id: 'dp14', symbol: 'LLY',   price: 783.40, size: 42_000,   premium: 32_902_800,  time: now - 660_000, sentiment: 'bullish' as const },
    { id: 'dp15', symbol: 'AVGO',  price: 1286.80,size: 28_000,   premium: 36_030_400,  time: now - 720_000, sentiment: 'bullish' as const },
  ];

  // ---- 10 mock short interest stocks ----
  const shortInterestData = [
    { symbol: 'SMCI',  name: 'Super Micro Computer', shortPercent: 22.4, daysTocover: 3.2, change: -4.13 },
    { symbol: 'RIVN',  name: 'Rivian Automotive',    shortPercent: 18.7, daysTocover: 4.1, change: 7.23 },
    { symbol: 'PLTR',  name: 'Palantir Technologies',shortPercent: 12.8, daysTocover: 2.5, change: 7.93 },
    { symbol: 'COIN',  name: 'Coinbase Global',      shortPercent: 11.2, daysTocover: 1.8, change: 8.93 },
    { symbol: 'INTC',  name: 'Intel Corporation',    shortPercent: 9.8,  daysTocover: 2.1, change: -3.36 },
    { symbol: 'SQ',    name: 'Block Inc.',            shortPercent: 8.5,  daysTocover: 3.4, change: -3.19 },
    { symbol: 'DIS',   name: 'Walt Disney Co.',       shortPercent: 7.2,  daysTocover: 2.8, change: -3.27 },
    { symbol: 'BA',    name: 'Boeing Company',        shortPercent: 6.9,  daysTocover: 1.6, change: 4.70 },
    { symbol: 'NFLX',  name: 'Netflix Inc.',          shortPercent: 5.4,  daysTocover: 1.2, change: 2.56 },
    { symbol: 'TSLA',  name: 'Tesla Inc.',            shortPercent: 4.8,  daysTocover: 0.9, change: -3.27 },
  ];

  // ---- 10 mock ETF flows ----
  const etfFlows = [
    { symbol: 'SPY',  name: 'SPDR S&P 500',        flow: 2_400_000_000,  aum: 510_000_000_000, change: 0.45 },
    { symbol: 'QQQ',  name: 'Invesco QQQ Trust',    flow: 1_800_000_000,  aum: 240_000_000_000, change: -0.23 },
    { symbol: 'IWM',  name: 'iShares Russell 2000', flow: -850_000_000,   aum: 62_000_000_000,  change: 0.12 },
    { symbol: 'XLK',  name: 'Technology Select',    flow: 920_000_000,    aum: 58_000_000_000,  change: 1.82 },
    { symbol: 'XLF',  name: 'Financial Select',     flow: 450_000_000,    aum: 38_000_000_000,  change: 0.92 },
    { symbol: 'XLE',  name: 'Energy Select',        flow: -320_000_000,   aum: 35_000_000_000,  change: 1.35 },
    { symbol: 'XLV',  name: 'Health Care Select',   flow: 180_000_000,    aum: 40_000_000_000,  change: -0.45 },
    { symbol: 'TLT',  name: 'iShares 20+ Treasury', flow: -1_200_000_000, aum: 48_000_000_000,  change: -0.82 },
    { symbol: 'GLD',  name: 'SPDR Gold Shares',     flow: 650_000_000,    aum: 62_000_000_000,  change: 0.35 },
    { symbol: 'HYG',  name: 'iShares High Yield',   flow: -420_000_000,   aum: 18_000_000_000,  change: -0.15 },
  ];

  function formatMoney(v: number): string {
    const abs = Math.abs(v);
    if (abs >= 1_000_000_000) return (v / 1_000_000_000).toFixed(1) + 'B';
    if (abs >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M';
    if (abs >= 1_000) return (v / 1_000).toFixed(0) + 'K';
    return v.toFixed(0);
  }

  function formatTime(ts: number): string {
    const d = new Date(ts);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  }

  function changeColor(val: number): string {
    if (val > 0) return 'var(--bullish)';
    if (val < 0) return 'var(--bearish)';
    return 'var(--text-secondary)';
  }

  function sentimentColor(s: string): string {
    if (s === 'bullish') return 'var(--bullish)';
    if (s === 'bearish') return 'var(--bearish)';
    return 'var(--neutral)';
  }

  function sentimentBg(s: string): string {
    if (s === 'bullish') return 'var(--bullish-bg)';
    if (s === 'bearish') return 'var(--bearish-bg)';
    return 'var(--neutral-bg)';
  }
</script>

<svelte:head>
  <title>Institutional - Scanify</title>
</svelte:head>

<div class="flex flex-col h-full overflow-hidden">
  <!-- Header -->
  <div class="flex items-center justify-between px-5 py-3 shrink-0" style="border-bottom: 1px solid var(--border-subtle);">
    <h1 class="text-lg font-bold" style="color: var(--text-primary);">Institutional Flow</h1>
  </div>

  <!-- Tabs -->
  <div class="px-5 shrink-0">
    <Tabs {tabs} bind:activeTab />
  </div>

  <!-- Tab content -->
  <div class="flex-1 overflow-auto min-h-0">
    {#if activeTab === 'darkpool'}
      <!-- Dark Pool Feed -->
      <div class="p-5 space-y-2">
        <div class="flex items-center gap-2 mb-3">
          <div class="w-2 h-2 rounded-full signal-ping" style="background: var(--accent);"></div>
          <span class="text-sm font-semibold" style="color: var(--text-primary);">Dark Pool Prints ({darkPoolTrades.length})</span>
        </div>

        {#each darkPoolTrades as trade (trade.id)}
          <div
            class="flex items-center gap-3 rounded-lg px-4 py-3 transition-colors"
            style="background: var(--bg-surface); border: 1px solid var(--border-subtle);"
          >
            <!-- Symbol -->
            <span class="text-sm font-bold font-mono w-14 shrink-0" style="color: var(--text-primary);">{trade.symbol}</span>

            <!-- Sentiment dot -->
            <div class="w-2 h-2 rounded-full shrink-0" style="background: {sentimentColor(trade.sentiment)};"></div>

            <!-- Price -->
            <span class="text-xs font-mono" style="color: var(--text-secondary);">${trade.price.toFixed(2)}</span>

            <!-- Size -->
            <span class="text-xs font-mono" style="color: var(--text-secondary);">{trade.size.toLocaleString()} shr</span>

            <div class="flex-1"></div>

            <!-- Sentiment badge -->
            <span
              class="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full"
              style="background: {sentimentBg(trade.sentiment)}; color: {sentimentColor(trade.sentiment)};"
            >
              {trade.sentiment}
            </span>

            <!-- Premium -->
            <span class="text-sm font-mono font-bold w-20 text-right shrink-0" style="color: var(--text-primary);">
              ${formatMoney(trade.premium)}
            </span>

            <!-- Time -->
            <span class="text-[10px] font-mono w-16 text-right shrink-0" style="color: var(--text-tertiary);">
              {formatTime(trade.time)}
            </span>
          </div>
        {/each}
      </div>

    {:else if activeTab === 'short'}
      <!-- Short Interest -->
      <div class="p-5">
        <table class="w-full text-xs">
          <thead>
            <tr style="background: var(--bg-base);">
              <th class="text-left px-4 py-2.5 font-medium" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">Symbol</th>
              <th class="text-left px-3 py-2.5 font-medium" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">Name</th>
              <th class="text-right px-3 py-2.5 font-medium" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">Short %</th>
              <th class="text-right px-3 py-2.5 font-medium" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">Days to Cover</th>
              <th class="text-right px-3 py-2.5 font-medium" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">Change</th>
              <th class="text-center px-3 py-2.5 font-medium" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">Squeeze Risk</th>
            </tr>
          </thead>
          <tbody>
            {#each shortInterestData as stock, i (stock.symbol)}
              {@const squeezeRisk = stock.shortPercent > 15 ? 'High' : stock.shortPercent > 8 ? 'Medium' : 'Low'}
              {@const squeezeColor = squeezeRisk === 'High' ? 'var(--bearish)' : squeezeRisk === 'Medium' ? 'var(--warning)' : 'var(--bullish)'}
              <tr style="background: {i % 2 === 0 ? 'var(--bg-surface)' : 'transparent'}; border-bottom: 1px solid var(--border-subtle);">
                <td class="px-4 py-2.5 font-bold font-mono" style="color: var(--text-primary);">{stock.symbol}</td>
                <td class="px-3 py-2.5" style="color: var(--text-secondary);">{stock.name}</td>
                <td class="text-right px-3 py-2.5 font-mono font-bold" style="color: var(--bearish-bright);">
                  {stock.shortPercent.toFixed(1)}%
                </td>
                <td class="text-right px-3 py-2.5 font-mono" style="color: var(--text-secondary);">
                  {stock.daysTocover.toFixed(1)}
                </td>
                <td class="text-right px-3 py-2.5 font-mono font-semibold" style="color: {changeColor(stock.change)};">
                  {stock.change >= 0 ? '+' : ''}{stock.change.toFixed(2)}%
                </td>
                <td class="text-center px-3 py-2.5">
                  <span
                    class="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full"
                    style="background: {squeezeRisk === 'High' ? 'var(--bearish-bg)' : squeezeRisk === 'Medium' ? 'var(--warning-bg)' : 'var(--bullish-bg)'};
                           color: {squeezeColor};"
                  >
                    {squeezeRisk}
                  </span>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

    {:else if activeTab === 'etf'}
      <!-- ETF Flows -->
      <div class="p-5">
        <table class="w-full text-xs">
          <thead>
            <tr style="background: var(--bg-base);">
              <th class="text-left px-4 py-2.5 font-medium" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">ETF</th>
              <th class="text-left px-3 py-2.5 font-medium" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">Name</th>
              <th class="text-right px-3 py-2.5 font-medium" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">Flow (Today)</th>
              <th class="text-right px-3 py-2.5 font-medium" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">AUM</th>
              <th class="text-right px-3 py-2.5 font-medium" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">Change</th>
              <th class="text-center px-3 py-2.5 font-medium" style="color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle);">Flow Dir.</th>
            </tr>
          </thead>
          <tbody>
            {#each etfFlows as etf, i (etf.symbol)}
              <tr style="background: {i % 2 === 0 ? 'var(--bg-surface)' : 'transparent'}; border-bottom: 1px solid var(--border-subtle);">
                <td class="px-4 py-2.5 font-bold font-mono" style="color: var(--text-primary);">{etf.symbol}</td>
                <td class="px-3 py-2.5" style="color: var(--text-secondary);">{etf.name}</td>
                <td class="text-right px-3 py-2.5 font-mono font-bold" style="color: {changeColor(etf.flow)};">
                  {etf.flow >= 0 ? '+' : ''}${formatMoney(etf.flow)}
                </td>
                <td class="text-right px-3 py-2.5 font-mono" style="color: var(--text-secondary);">
                  ${formatMoney(etf.aum)}
                </td>
                <td class="text-right px-3 py-2.5 font-mono font-semibold" style="color: {changeColor(etf.change)};">
                  {etf.change >= 0 ? '+' : ''}{etf.change.toFixed(2)}%
                </td>
                <td class="text-center px-3 py-2.5">
                  <div class="inline-flex items-center gap-1">
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke={etf.flow >= 0 ? 'var(--bullish)' : 'var(--bearish)'} stroke-width="2.5">
                      <path stroke-linecap="round" stroke-linejoin="round" d={etf.flow >= 0 ? 'M5 15l7-7 7 7' : 'M19 9l-7 7-7-7'} />
                    </svg>
                    <span class="text-[10px] font-bold uppercase" style="color: {etf.flow >= 0 ? 'var(--bullish)' : 'var(--bearish)'};">
                      {etf.flow >= 0 ? 'Inflow' : 'Outflow'}
                    </span>
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </div>
</div>
