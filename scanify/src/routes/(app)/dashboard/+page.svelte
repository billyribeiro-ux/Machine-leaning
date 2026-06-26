<script lang="ts">
  import { onMount } from 'svelte';
  import InternalsBar from '$lib/components/market/InternalsBar.svelte';
  import ExportToolbar from '$lib/components/ui/ExportToolbar.svelte';
  import {
    TrendUp,
    TrendDown,
    Pulse,
    ChartBar,
    Lightning,
    Clock,
    Gauge,
    Globe,
    Eye,
    Target,
    Fire,
    Broadcast,
    CaretUp,
    CaretDown,
    ChartLine,
    Warning,
    MagnifyingGlass,
    GitDiff,
    Bank,
    Bell,
    Swap,
    Funnel,
    ArrowUp,
    ArrowDown,
  } from 'phosphor-svelte';

  const API_BASE = 'http://localhost:8000';

  // ---------------------------------------------------------------------------
  // SIMULATED DATA (fallback when API unreachable)
  // ---------------------------------------------------------------------------

  function generateSparkline(base: number, volatility: number, trend: number = 0.5, points = 24): number[] {
    const data: number[] = [];
    let val = base - volatility * 3;
    for (let i = 0; i < points; i++) {
      val += (Math.random() - (0.5 - trend * 0.04)) * volatility;
      val = Math.max(base - volatility * 5, Math.min(base + volatility * 4, val));
      data.push(val);
    }
    return data;
  }

  const SIM_SPARKLINES = {
    'SPX':     generateSparkline(5823, 18, 0.6),
    'VIX':     generateSparkline(16.4, 0.8, -0.5),
    'volume':  generateSparkline(3.5, 0.4, 0.3),
    'breadth': generateSparkline(1.45, 0.15, 0.6),
    'pcr':     generateSparkline(0.78, 0.06, -0.4),
    'DJI':     generateSparkline(38920, 120, 0.5),
  };

  const SIM_KPI = {
    marketStatus: 'open' as 'open' | 'pre' | 'post' | 'closed',
    spx:         { price: 5823.47, change: 32.15, changePct: 0.56 },
    vix:         { price: 16.42, change: -0.83, changePct: -4.81 },
    putCallRatio: 0.78,
    totalVolume:  3.72,
    breadth:      1.42,
    advancers:    1847,
    decliners:    1142,
    unchanged:    89,
    newHighs:     142,
    newLows:      28,
    tickVal:      487,
    trinVal:      0.87,
  };

  const SIM_SIGNALS: {
    id: number;
    timestamp: string;
    symbol: string;
    signalType: string;
    direction: 'bullish' | 'bearish' | 'neutral';
    strength: number;
    price: number;
    change: number;
  }[] = [
    { id: 1,  timestamp: '15:42:18', symbol: 'NVDA',  signalType: 'Momentum Breakout',  direction: 'bullish',  strength: 5, price: 924.68,  change: 4.82 },
    { id: 2,  timestamp: '15:41:05', symbol: 'TSLA',  signalType: 'Volume Surge',        direction: 'bullish',  strength: 4, price: 248.52,  change: 3.14 },
    { id: 3,  timestamp: '15:39:47', symbol: 'META',  signalType: 'Golden Cross',        direction: 'bullish',  strength: 4, price: 512.30,  change: 1.87 },
    { id: 4,  timestamp: '15:38:22', symbol: 'AAPL',  signalType: 'RSI Divergence',      direction: 'bearish',  strength: 3, price: 189.84,  change: -0.42 },
    { id: 5,  timestamp: '15:36:51', symbol: 'AMZN',  signalType: 'VWAP Reclaim',        direction: 'bullish',  strength: 4, price: 186.92,  change: 2.15 },
    { id: 6,  timestamp: '15:35:10', symbol: 'JPM',   signalType: 'Relative Strength',   direction: 'bullish',  strength: 3, price: 198.44,  change: 1.22 },
    { id: 7,  timestamp: '15:33:42', symbol: 'XOM',   signalType: 'Bearish Engulfing',   direction: 'bearish',  strength: 4, price: 104.28,  change: -1.85 },
    { id: 8,  timestamp: '15:31:18', symbol: 'MSFT',  signalType: 'Squeeze Firing',      direction: 'bullish',  strength: 5, price: 428.72,  change: 2.94 },
    { id: 9,  timestamp: '15:29:55', symbol: 'AMD',   signalType: 'Dark Pool Print',     direction: 'neutral',  strength: 3, price: 174.56,  change: 0.68 },
    { id: 10, timestamp: '15:28:02', symbol: 'GOOGL', signalType: 'Options Flow Alert',  direction: 'bullish',  strength: 4, price: 176.48,  change: 1.52 },
    { id: 11, timestamp: '15:26:30', symbol: 'V',     signalType: 'Sector Rotation',     direction: 'bullish',  strength: 3, price: 282.14,  change: 0.92 },
    { id: 12, timestamp: '15:24:15', symbol: 'CRM',   signalType: 'Earnings Drift',      direction: 'bearish',  strength: 3, price: 248.86,  change: -1.28 },
    { id: 13, timestamp: '15:22:48', symbol: 'NFLX',  signalType: 'Gap Fill',            direction: 'neutral',  strength: 2, price: 638.40,  change: 0.34 },
    { id: 14, timestamp: '15:20:32', symbol: 'BA',    signalType: 'Unusual Volume',      direction: 'bearish',  strength: 4, price: 172.95,  change: -2.62 },
    { id: 15, timestamp: '15:18:05', symbol: 'COIN',  signalType: 'Momentum Ignition',   direction: 'bullish',  strength: 5, price: 264.30,  change: 6.18 },
  ];

  const SIM_SECTORS: { name: string; ticker: string; change: number; weight: number }[] = [
    { name: 'Technology',       ticker: 'XLK',  change: 1.24,  weight: 29.2 },
    { name: 'Healthcare',       ticker: 'XLV',  change: -0.31, weight: 13.1 },
    { name: 'Financials',       ticker: 'XLF',  change: 0.52,  weight: 12.8 },
    { name: 'Consumer Disc.',   ticker: 'XLY',  change: 0.87,  weight: 10.5 },
    { name: 'Communication',    ticker: 'XLC',  change: 1.05,  weight: 8.9 },
    { name: 'Industrials',      ticker: 'XLI',  change: 0.33,  weight: 8.4 },
    { name: 'Consumer Staples', ticker: 'XLP',  change: -0.18, weight: 6.2 },
    { name: 'Energy',           ticker: 'XLE',  change: -0.72, weight: 3.9 },
    { name: 'Utilities',        ticker: 'XLU',  change: 0.14,  weight: 2.6 },
    { name: 'Real Estate',      ticker: 'XLRE', change: -0.44, weight: 2.4 },
    { name: 'Materials',        ticker: 'XLB',  change: 0.21,  weight: 2.0 },
  ];

  // ---------------------------------------------------------------------------
  // SCANNER RESULTS (top 10 from the scanner page)
  // ---------------------------------------------------------------------------

  const SIM_SCANNER: {
    rank: number; symbol: string; name: string; price: number;
    changePct: number; volume: number; signal: 'Gamma' | 'Volume' | 'Flow';
    strength: number; score: number;
  }[] = [
    { rank: 1,  symbol: 'NVDA',  name: 'NVIDIA Corp',         price: 141.28, changePct: 4.82,  volume: 87_200_000, signal: 'Gamma',  strength: 5, score: 96 },
    { rank: 2,  symbol: 'TSLA',  name: 'Tesla Inc',           price: 352.74, changePct: 3.14,  volume: 65_800_000, signal: 'Volume', strength: 5, score: 94 },
    { rank: 3,  symbol: 'META',  name: 'Meta Platforms',      price: 627.14, changePct: 1.87,  volume: 26_300_000, signal: 'Flow',   strength: 4, score: 88 },
    { rank: 4,  symbol: 'AMD',   name: 'AMD',                 price: 168.93, changePct: 2.05,  volume: 36_400_000, signal: 'Gamma',  strength: 4, score: 85 },
    { rank: 5,  symbol: 'MSFT',  name: 'Microsoft',           price: 468.35, changePct: 2.94,  volume: 54_600_000, signal: 'Flow',   strength: 5, score: 92 },
    { rank: 6,  symbol: 'COIN',  name: 'Coinbase',            price: 278.93, changePct: 6.18,  volume: 42_100_000, signal: 'Volume', strength: 5, score: 91 },
    { rank: 7,  symbol: 'AAPL',  name: 'Apple Inc',           price: 234.56, changePct: -0.42, volume: 81_200_000, signal: 'Gamma',  strength: 3, score: 72 },
    { rank: 8,  symbol: 'SPY',   name: 'SPDR S&P 500',       price: 587.42, changePct: 0.56,  volume: 39_500_000, signal: 'Flow',   strength: 3, score: 68 },
    { rank: 9,  symbol: 'AMZN',  name: 'Amazon',              price: 213.47, changePct: 2.15,  volume: 28_800_000, signal: 'Volume', strength: 4, score: 82 },
    { rank: 10, symbol: 'GOOGL', name: 'Alphabet',            price: 182.65, changePct: 1.52,  volume: 43_000_000, signal: 'Gamma',  strength: 4, score: 79 },
  ];

  // ---------------------------------------------------------------------------
  // GEX SCANNER DATA
  // ---------------------------------------------------------------------------

  const SIM_GEX = {
    totalGex:  3.43,
    callGex:   12.13,
    putGex:    -8.70,
    netGex:    3.43,
    dealerPos: 'Long Gamma' as 'Long Gamma' | 'Short Gamma' | 'Neutral',
    keyStrike: 5580,
    spotPrice: 5512.40,
    spotSymbol: 'SPX',
    profile: [
      { strike: 5400, callGex: 0.42, putGex: -0.38, net: 0.04 },
      { strike: 5420, callGex: 0.58, putGex: -0.52, net: 0.06 },
      { strike: 5440, callGex: 0.91, putGex: -0.73, net: 0.18 },
      { strike: 5460, callGex: 1.24, putGex: -0.96, net: 0.28 },
      { strike: 5480, callGex: 1.52, putGex: -1.18, net: 0.34 },
      { strike: 5500, callGex: 1.78, putGex: -1.42, net: 0.36 },
      { strike: 5520, callGex: 1.62, putGex: -1.28, net: 0.34 },
      { strike: 5540, callGex: 1.34, putGex: -1.08, net: 0.26 },
      { strike: 5560, callGex: 0.98, putGex: -0.82, net: 0.16 },
      { strike: 5580, callGex: 0.74, putGex: -0.43, net: 0.31 },
    ],
  };

  const gexMaxAbs = Math.max(...SIM_GEX.profile.map(g => Math.max(Math.abs(g.callGex), Math.abs(g.putGex))));

  // ---------------------------------------------------------------------------
  // OPTIONS FLOW SCANNER
  // ---------------------------------------------------------------------------

  const SIM_FLOW: {
    time: string; symbol: string; type: 'C' | 'P'; strike: number;
    expiry: string; side: 'BUY' | 'SELL'; premium: number;
    flags: string[];
  }[] = [
    { time: '15:42:18', symbol: 'SPX',  type: 'C', strike: 5520, expiry: 'Jun 20', side: 'BUY',  premium: 4_850_000, flags: ['SWP', 'UNU'] },
    { time: '15:41:05', symbol: 'SPY',  type: 'C', strike: 553,  expiry: 'Jun 22', side: 'BUY',  premium: 2_340_000, flags: ['SWP', 'UNU'] },
    { time: '15:39:47', symbol: 'QQQ',  type: 'P', strike: 475,  expiry: 'Jun 26', side: 'BUY',  premium: 920_000,   flags: ['UNU'] },
    { time: '15:38:22', symbol: 'NVDA', type: 'C', strike: 145,  expiry: 'Jun 20', side: 'BUY',  premium: 1_150_000, flags: ['SWP'] },
    { time: '15:36:51', symbol: 'META', type: 'P', strike: 505,  expiry: 'Jun 22', side: 'BUY',  premium: 1_680_000, flags: ['SWP', 'UNU'] },
    { time: '15:33:42', symbol: 'SPX',  type: 'C', strike: 5550, expiry: 'Jun 27', side: 'BUY',  premium: 6_100_000, flags: ['SWP', 'UNU'] },
  ];

  // ---------------------------------------------------------------------------
  // DARK POOL SCANNER
  // ---------------------------------------------------------------------------

  const SIM_DARKPOOL: {
    time: string; symbol: string; price: number; size: number;
    notional: number; exchange: string; side: 'BUY' | 'SELL';
  }[] = [
    { time: '15:42:18', symbol: 'SPY',  price: 585.42, size: 850_000,  notional: 49_800_000, exchange: 'FINRA ADF', side: 'BUY' },
    { time: '15:41:05', symbol: 'NVDA', price: 142.50, size: 280_000,  notional: 39_900_000, exchange: 'IEX',       side: 'BUY' },
    { time: '15:39:33', symbol: 'AAPL', price: 198.75, size: 150_000,  notional: 29_800_000, exchange: 'FINRA ADF', side: 'SELL' },
    { time: '15:37:12', symbol: 'MSFT', price: 448.20, size: 55_000,   notional: 24_700_000, exchange: 'CBOE BYX',  side: 'BUY' },
    { time: '15:34:48', symbol: 'TSLA', price: 268.90, size: 75_000,   notional: 20_200_000, exchange: 'IEX',       side: 'SELL' },
  ];

  // ---------------------------------------------------------------------------
  // ACTIVE ALERTS
  // ---------------------------------------------------------------------------

  const SIM_ALERTS: {
    time: string; symbol: string; type: string; direction: 'BULL' | 'BEAR';
    description: string; strength: number; price: number;
  }[] = [
    { time: '2m ago',  symbol: 'NVDA', type: 'Momentum Break',  direction: 'BULL', description: 'Broke 20-day high with 3.2x volume', strength: 5, price: 142.50 },
    { time: '8m ago',  symbol: 'TSLA', type: 'Volume Surge',    direction: 'BEAR', description: '4.8x relative volume on decline',     strength: 4, price: 268.90 },
    { time: '15m ago', symbol: 'AMD',  type: 'Squeeze Fire',    direction: 'BULL', description: 'Bollinger squeeze fired bullish',      strength: 4, price: 178.30 },
    { time: '22m ago', symbol: 'SPY',  type: 'GEX Flip',        direction: 'BEAR', description: 'Dealer gamma flipped negative',        strength: 3, price: 585.42 },
    { time: '31m ago', symbol: 'META', type: 'Dark Pool Print',  direction: 'BULL', description: '$28M block at ask',                   strength: 4, price: 542.60 },
  ];

  // ---------------------------------------------------------------------------
  // INSTITUTIONAL: SHORT INTEREST SCANNER
  // ---------------------------------------------------------------------------

  const SIM_SHORT_INTEREST: {
    symbol: string; name: string; shortPct: number; daysToC: number;
    utilization: number; sqScore: number;
  }[] = [
    { symbol: 'GME',  name: 'GameStop',       shortPct: 24.8, daysToC: 2.1, utilization: 94.2, sqScore: 92 },
    { symbol: 'AMC',  name: 'AMC Entertain.', shortPct: 21.3, daysToC: 1.8, utilization: 88.7, sqScore: 85 },
    { symbol: 'CVNA', name: 'Carvana',        shortPct: 18.7, daysToC: 3.2, utilization: 82.4, sqScore: 78 },
    { symbol: 'BBBY', name: 'Beyond Inc',     shortPct: 15.2, daysToC: 2.8, utilization: 76.1, sqScore: 71 },
    { symbol: 'MARA', name: 'Marathon Dig.',   shortPct: 12.6, daysToC: 1.5, utilization: 71.3, sqScore: 68 },
    { symbol: 'RIVN', name: 'Rivian Auto',    shortPct: 10.9, daysToC: 2.4, utilization: 65.8, sqScore: 62 },
  ];

  // ---------------------------------------------------------------------------
  // INSTITUTIONAL: ETF FUND FLOWS
  // ---------------------------------------------------------------------------

  const SIM_ETF_FLOWS: {
    ticker: string; name: string; flow: number; aum: number; flowPct: number;
  }[] = [
    { ticker: 'SPY',  name: 'S&P 500 ETF',    flow: 2840,  aum: 562.4, flowPct: 0.51 },
    { ticker: 'QQQ',  name: 'Nasdaq 100',      flow: 1420,  aum: 285.6, flowPct: 0.50 },
    { ticker: 'IWM',  name: 'Russell 2000',    flow: -680,  aum: 68.2,  flowPct: -1.00 },
    { ticker: 'XLF',  name: 'Financial Sel.',   flow: 540,   aum: 42.8,  flowPct: 1.26 },
    { ticker: 'XLE',  name: 'Energy Sel.',     flow: -320,  aum: 35.1,  flowPct: -0.91 },
    { ticker: 'GLD',  name: 'Gold Trust',      flow: 890,   aum: 58.4,  flowPct: 1.52 },
  ];

  // ---------------------------------------------------------------------------
  // INSTITUTIONAL: INSIDER TRANSACTIONS
  // ---------------------------------------------------------------------------

  const SIM_INSIDER: {
    date: string; symbol: string; insider: string; role: string;
    type: 'BUY' | 'SELL'; shares: number; value: number;
  }[] = [
    { date: 'Jun 18', symbol: 'AAPL', insider: 'T. Cook',    role: 'CEO',  type: 'BUY',  shares: 50_000,  value: 9_920_000 },
    { date: 'Jun 18', symbol: 'MSFT', insider: 'S. Nadella',  role: 'CEO',  type: 'SELL', shares: 25_000,  value: 11_200_000 },
    { date: 'Jun 17', symbol: 'NVDA', insider: 'J. Huang',   role: 'CEO',  type: 'SELL', shares: 120_000, value: 17_100_000 },
    { date: 'Jun 17', symbol: 'JPM',  insider: 'J. Dimon',   role: 'CEO',  type: 'BUY',  shares: 30_000,  value: 5_950_000 },
    { date: 'Jun 16', symbol: 'TSLA', insider: 'R. Taneja',   role: 'CFO',  type: 'SELL', shares: 8_000,   value: 2_140_000 },
  ];

  // ---------------------------------------------------------------------------
  // MARKET INTELLIGENCE: SENTIMENT
  // ---------------------------------------------------------------------------

  const SIM_SENTIMENT = {
    score: 68,
    label: 'Greed' as string,
    prevScore: 62,
    weekAgo: 55,
    monthAgo: 42,
  };

  // ---------------------------------------------------------------------------
  // MARKET INTELLIGENCE: REGIME
  // ---------------------------------------------------------------------------

  const SIM_REGIME = {
    regime: 'Bull' as string,
    vixRegime: 'Normal' as string,
    phase: 'Afternoon' as string,
    trendStr: 72,
    daysInRegime: 18,
  };

  // ---------------------------------------------------------------------------
  // MARKET INTELLIGENCE: LIQUIDITY
  // ---------------------------------------------------------------------------

  const SIM_LIQUIDITY = {
    fedBal: 7.42,
    repoRate: 5.33,
    tga: 742,
    rrp: 438,
    netLiq: 5.84,
    netLiqChg: 0.12,
  };

  // ---------------------------------------------------------------------------
  // MARKET INTELLIGENCE: VIX TERM STRUCTURE
  // ---------------------------------------------------------------------------

  const SIM_VIX_TERM: { label: string; value: number }[] = [
    { label: '1D',  value: 14.2 },
    { label: '1W',  value: 15.8 },
    { label: '1M',  value: 16.4 },
    { label: '2M',  value: 17.1 },
    { label: '3M',  value: 17.9 },
    { label: '6M',  value: 18.6 },
  ];

  // ---------------------------------------------------------------------------
  // TECHNICAL SCANNER
  // ---------------------------------------------------------------------------

  const SIM_TECHNICAL: {
    symbol: string; signal: string; indicator: string;
    value: number; direction: 'bullish' | 'bearish';
  }[] = [
    { symbol: 'NVDA',  signal: 'RSI Oversold Bounce',    indicator: 'RSI',        value: 32.4,   direction: 'bullish' },
    { symbol: 'TSLA',  signal: 'MACD Bull Cross',         indicator: 'MACD',       value: 2.18,   direction: 'bullish' },
    { symbol: 'META',  signal: 'BB Squeeze Fire',         indicator: 'Bollinger',  value: 0.82,   direction: 'bullish' },
    { symbol: 'AMD',   signal: 'VWAP Reclaim',            indicator: 'VWAP',       value: 168.93, direction: 'bullish' },
    { symbol: 'AAPL',  signal: 'Death Cross 50/200',      indicator: 'SMA',        value: 189.84, direction: 'bearish' },
    { symbol: 'XOM',   signal: 'ADX Trend Weakening',     indicator: 'ADX',        value: 18.4,   direction: 'bearish' },
    { symbol: 'JPM',   signal: 'Stochastic Overbought',   indicator: 'Stochastic', value: 84.2,   direction: 'bearish' },
    { symbol: 'GOOGL', signal: 'Keltner Channel Break',   indicator: 'Keltner',    value: 176.48, direction: 'bullish' },
  ];

  // ---------------------------------------------------------------------------
  // UNUSUAL OPTIONS ACTIVITY
  // ---------------------------------------------------------------------------

  const SIM_UNUSUAL_OPT: {
    symbol: string; volOI: number; vol: number; oi: number;
    ivRank: number; sentiment: 'bullish' | 'bearish' | 'neutral';
  }[] = [
    { symbol: 'NVDA',  volOI: 4.8, vol: 142_000, oi: 29_600,  ivRank: 78, sentiment: 'bullish' },
    { symbol: 'TSLA',  volOI: 3.9, vol: 98_400,  oi: 25_200,  ivRank: 85, sentiment: 'bullish' },
    { symbol: 'SPY',   volOI: 3.2, vol: 284_000, oi: 88_800,  ivRank: 42, sentiment: 'neutral' },
    { symbol: 'AMD',   volOI: 2.8, vol: 67_200,  oi: 24_000,  ivRank: 72, sentiment: 'bullish' },
    { symbol: 'META',  volOI: 2.5, vol: 45_600,  oi: 18_200,  ivRank: 68, sentiment: 'bearish' },
    { symbol: 'AAPL',  volOI: 2.1, vol: 112_000, oi: 53_300,  ivRank: 35, sentiment: 'neutral' },
  ];

  // ---------------------------------------------------------------------------
  // TOP GAINERS / LOSERS
  // ---------------------------------------------------------------------------

  const SIM_GAINERS: { symbol: string; price: number; changePct: number; volume: number }[] = [
    { symbol: 'COIN',  price: 278.93, changePct: 6.18,  volume: 42_100_000 },
    { symbol: 'NVDA',  price: 141.28, changePct: 4.82,  volume: 87_200_000 },
    { symbol: 'TSLA',  price: 352.74, changePct: 3.14,  volume: 65_800_000 },
    { symbol: 'MSFT',  price: 468.35, changePct: 2.94,  volume: 54_600_000 },
    { symbol: 'AMZN',  price: 213.47, changePct: 2.15,  volume: 28_800_000 },
  ];

  const SIM_LOSERS: { symbol: string; price: number; changePct: number; volume: number }[] = [
    { symbol: 'BA',    price: 172.95, changePct: -2.62, volume: 18_400_000 },
    { symbol: 'XOM',   price: 104.28, changePct: -1.85, volume: 22_100_000 },
    { symbol: 'CRM',   price: 248.86, changePct: -1.28, volume: 12_600_000 },
    { symbol: 'NFLX',  price: 638.40, changePct: -0.82, volume: 8_400_000 },
    { symbol: 'DIS',   price: 102.35, changePct: -0.59, volume: 15_200_000 },
  ];

  // ---------------------------------------------------------------------------
  // EXPECTED MOVE / MAX PAIN
  // ---------------------------------------------------------------------------

  const SIM_EXPECTED_MOVE = {
    symbol: 'SPX',
    spot: 5823.47,
    expectedMove: 42.5,
    expectedPct: 0.73,
    maxPain: 5800,
    ivRank: 32,
    iv30: 16.8,
    hv30: 14.2,
  };

  // ---------------------------------------------------------------------------
  // REACTIVE STATE
  // ---------------------------------------------------------------------------

  let loading = $state(false);
  let connected = $state(false);
  let needsApiKey = $state(false);

  let indices = $state<{ symbol: string; price: number; change: number; changePercent: number }[]>([
    { symbol: 'SPX', price: SIM_KPI.spx.price, change: SIM_KPI.spx.change, changePercent: SIM_KPI.spx.changePct },
    { symbol: 'VIX', price: SIM_KPI.vix.price, change: SIM_KPI.vix.change, changePercent: SIM_KPI.vix.changePct },
    { symbol: 'DJI', price: 38920.14, change: 127.43, changePercent: 0.33 },
    { symbol: 'NDX', price: 20417.62, change: 185.28, changePercent: 0.92 },
    { symbol: 'RUT', price: 2087.35, change: -12.47, changePercent: -0.59 },
  ]);
  let topSignals = $state<{ symbol: string; direction: 'bullish' | 'bearish' | 'neutral'; name: string; strength: number; price: number }[]>(
    SIM_SIGNALS.slice(0, 5).map(s => ({ symbol: s.symbol, direction: s.direction, name: s.signalType, strength: s.strength, price: s.price }))
  );
  let sectors = $state<{ name: string; change: number }[]>(
    SIM_SECTORS.map(s => ({ name: s.name, change: s.change }))
  );

  let tick = $state(SIM_KPI.tickVal);
  let trin = $state(SIM_KPI.trinVal);
  let vix = $state(SIM_KPI.vix.price);
  let advDecRatio = $state(SIM_KPI.breadth);

  let currentTime = $state(new Date().toLocaleTimeString('en-US', { hour12: false }));

  // ---------------------------------------------------------------------------
  // SPARKLINE HELPERS
  // ---------------------------------------------------------------------------

  function sparklinePath(data: number[], width: number, height: number, pad = 2): string {
    if (!data || data.length < 2) return '';
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const step = (width - pad * 2) / (data.length - 1);
    return data
      .map((v, i) => `${(pad + i * step).toFixed(1)},${(pad + (1 - (v - min) / range) * (height - pad * 2)).toFixed(1)}`)
      .join(' ');
  }

  function sparklineArea(data: number[], width: number, height: number, pad = 2): string {
    if (!data || data.length < 2) return '';
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const step = (width - pad * 2) / (data.length - 1);
    const pts = data.map((v, i) => ({
      x: pad + i * step,
      y: pad + (1 - (v - min) / range) * (height - pad * 2),
    }));
    let d = `M ${pts[0]!.x.toFixed(1)} ${pts[0]!.y.toFixed(1)}`;
    for (let i = 1; i < pts.length; i++) d += ` L ${pts[i]!.x.toFixed(1)} ${pts[i]!.y.toFixed(1)}`;
    d += ` L ${pts[pts.length - 1]!.x.toFixed(1)} ${(height - pad).toFixed(1)}`;
    d += ` L ${pts[0]!.x.toFixed(1)} ${(height - pad).toFixed(1)} Z`;
    return d;
  }

  // ---------------------------------------------------------------------------
  // DERIVED
  // ---------------------------------------------------------------------------

  let breadthTotal = $derived(SIM_KPI.advancers + SIM_KPI.decliners + SIM_KPI.unchanged);
  let advPct = $derived((SIM_KPI.advancers / breadthTotal) * 100);
  let decPct = $derived((SIM_KPI.decliners / breadthTotal) * 100);
  let unchPct = $derived((SIM_KPI.unchanged / breadthTotal) * 100);

  let sortedSectors = $derived.by(() => [...SIM_SECTORS].sort((a, b) => b.change - a.change));

  let statusColor = $derived.by(() => {
    const s = SIM_KPI.marketStatus;
    if (s === 'open') return 'var(--bullish-bright)';
    if (s === 'pre') return 'var(--warning-bright)';
    if (s === 'post') return 'var(--warning)';
    return 'var(--text-tertiary)';
  });

  let statusLabel = $derived.by(() => {
    const s = SIM_KPI.marketStatus;
    if (s === 'open') return 'MARKET OPEN';
    if (s === 'pre') return 'PRE-MARKET';
    if (s === 'post') return 'AFTER HOURS';
    return 'CLOSED';
  });

  // ---------------------------------------------------------------------------
  // DATA FETCHING (preserved from original)
  // ---------------------------------------------------------------------------

  async function fetchDashboardData() {
    try {
      const health = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(5000) });
      connected = health.ok;
    } catch {
      connected = false;
      return;
    }

    let anyProviderError = false;

    try {
      const priceRes = await fetch(`${API_BASE}/api/equity/price/snapshot`, { signal: AbortSignal.timeout(3000) });
      if (priceRes.ok) {
        const priceData = await priceRes.json();
        if (Array.isArray(priceData)) {
          indices = priceData.map((d: any) => ({
            symbol: d.symbol ?? d.ticker ?? '',
            price: d.price ?? d.last ?? 0,
            change: d.change ?? 0,
            changePercent: d.changePercent ?? d.change_percent ?? 0,
          }));
        } else if (priceData.indices) {
          indices = priceData.indices;
        } else if (priceData.data) {
          indices = Array.isArray(priceData.data) ? priceData.data : [];
        }
      } else {
        anyProviderError = true;
      }
    } catch { anyProviderError = true; }

    try {
      const macroRes = await fetch(`${API_BASE}/api/equity/macro/snapshot`, { signal: AbortSignal.timeout(3000) });
      if (macroRes.ok) {
        const macroData = await macroRes.json();
        const macro = macroData.data ?? macroData;
        vix = macro.vix ?? macro.VIX ?? 0;
        tick = macro.tick ?? macro.TICK ?? 0;
        trin = macro.trin ?? macro.TRIN ?? 1.0;
        advDecRatio = macro.advDecRatio ?? macro.advance_decline ?? macro.ad_ratio ?? 1.0;
      } else {
        anyProviderError = true;
      }
    } catch { anyProviderError = true; }

    try {
      const sectorRes = await fetch(`${API_BASE}/api/equity/market/sectors`, { signal: AbortSignal.timeout(3000) });
      if (sectorRes.ok) {
        const sectorData = await sectorRes.json();
        const rawSectors = Array.isArray(sectorData) ? sectorData : sectorData.data ?? sectorData.sectors ?? [];
        sectors = rawSectors.map((s: any) => ({
          name: s.name ?? s.sector ?? '',
          change: s.change ?? s.changePercent ?? s.change_percent ?? 0,
        }));
      } else {
        anyProviderError = true;
      }
    } catch { anyProviderError = true; }

    try {
      const moversRes = await fetch(`${API_BASE}/api/equity/market/movers?limit=5`, { signal: AbortSignal.timeout(3000) });
      if (moversRes.ok) {
        const moversData = await moversRes.json();
        const rawMovers = Array.isArray(moversData) ? moversData : moversData.data ?? moversData.movers ?? [];
        topSignals = rawMovers.map((m: any) => ({
          symbol: m.symbol ?? m.ticker ?? '',
          direction: (m.direction ?? (m.change > 0 ? 'bullish' : m.change < 0 ? 'bearish' : 'neutral')) as 'bullish' | 'bearish' | 'neutral',
          name: m.name ?? m.signal ?? m.reason ?? '',
          strength: m.strength ?? m.score ?? 3,
          price: m.price ?? m.last ?? 0,
        }));
      } else {
        anyProviderError = true;
      }
    } catch { anyProviderError = true; }

    needsApiKey = anyProviderError;
    loading = false;
  }

  onMount(() => {
    fetchDashboardData();
    const clockInterval = setInterval(() => {
      currentTime = new Date().toLocaleTimeString('en-US', { hour12: false });
    }, 1000);
    return () => clearInterval(clockInterval);
  });

  // ---------------------------------------------------------------------------
  // HELPERS
  // ---------------------------------------------------------------------------

  function changeColor(val: number): string {
    if (val > 0) return 'var(--bullish)';
    if (val < 0) return 'var(--bearish)';
    return 'var(--text-secondary)';
  }

  function changeBright(val: number): string {
    if (val > 0) return 'var(--bullish-bright)';
    if (val < 0) return 'var(--bearish-bright)';
    return 'var(--text-secondary)';
  }

  function dirBright(dir: string): string {
    if (dir === 'bullish') return 'var(--bullish-bright)';
    if (dir === 'bearish') return 'var(--bearish-bright)';
    return 'var(--neutral-bright)';
  }

  function fmtPremium(v: number): string {
    if (v >= 1_000_000) return '$' + (v / 1_000_000).toFixed(1) + 'M';
    if (v >= 1_000)     return '$' + (v / 1_000).toFixed(0) + 'K';
    return '$' + v.toFixed(0);
  }

  function fmtVol(v: number): string {
    if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M';
    if (v >= 1_000)     return (v / 1_000).toFixed(0) + 'K';
    return v.toString();
  }

  function sectorHeatBg(change: number): string {
    if (change >= 1.0)  return 'oklch(0.38 0.14 155)';
    if (change >= 0.5)  return 'oklch(0.30 0.10 155)';
    if (change >= 0.0)  return 'oklch(0.22 0.06 155)';
    if (change >= -0.5) return 'oklch(0.22 0.06 25)';
    if (change >= -1.0) return 'oklch(0.30 0.10 25)';
    return 'oklch(0.38 0.14 25)';
  }

  function sectorHeatText(change: number): string {
    if (change >= 0.5)  return 'var(--bullish-bright)';
    if (change >= 0.0)  return 'var(--bullish)';
    if (change >= -0.5) return 'var(--bearish)';
    return 'var(--bearish-bright)';
  }

  function sectorHeatBorder(change: number): string {
    if (change >= 0) return 'oklch(0.45 0.12 155 / 0.25)';
    return 'oklch(0.42 0.12 25 / 0.25)';
  }

  function signalIconKind(s: string): string {
    if (s.includes('Momentum') || s.includes('Breakout') || s.includes('Ignition')) return 'lightning';
    if (s.includes('Volume'))     return 'chart-bar';
    if (s.includes('RSI'))        return 'gauge';
    if (s.includes('VWAP') || s.includes('Cross')) return 'target';
    if (s.includes('Options') || s.includes('Dark Pool')) return 'eye';
    if (s.includes('Squeeze'))    return 'fire';
    if (s.includes('Sector') || s.includes('Rotation')) return 'globe';
    if (s.includes('Engulfing') || s.includes('Support') || s.includes('Bearish')) return 'trend-down';
    return 'pulse';
  }
</script>

<svelte:head>
  <title>Dashboard - Scanify</title>
</svelte:head>

<div class="dashboard-page">
  <!-- ================================================================
       CONNECTION / API KEY BANNERS
       ================================================================ -->
  {#if !loading && !connected}
    <div class="conn-banner">
      <div class="banner-left">
        <Warning size={15} weight="fill" />
        <span class="banner-text">Backend offline -- displaying simulated data. Start the API server for live feeds.</span>
      </div>
      <button class="banner-btn" onclick={() => fetchDashboardData()}>
        <Broadcast size={13} />
        Reconnect
      </button>
    </div>
  {:else if !loading && needsApiKey}
    <div class="conn-banner warn-banner">
      <div class="banner-left">
        <Warning size={15} weight="fill" />
        <span class="banner-text">Data provider API key required -- configure vendor keys in Settings</span>
      </div>
      <a href="/settings" class="banner-btn">Configure</a>
    </div>
  {/if}

  <!-- ================================================================
       PAGE HEADER
       ================================================================ -->
  <header class="page-header">
    <div class="hdr-left">
      <h1 class="page-title">Dashboard</h1>
      <div class="status-chip">
        <span class="status-dot-wrap">
          <span class="status-dot" style="background:{statusColor};"></span>
          {#if SIM_KPI.marketStatus === 'open'}
            <span class="status-ring" style="border-color:{statusColor};"></span>
          {/if}
        </span>
        <span class="status-text" style="color:{statusColor};">{statusLabel}</span>
      </div>
    </div>
    <div class="hdr-right">
      <ExportToolbar source="dashboard" />
      <div class="hdr-sep"></div>
      <div class="hdr-clock">
        <Clock size={13} />
        <span class="clock-val mono-nums">{currentTime}</span>
      </div>
      <div class="hdr-sep"></div>
      <span class="hdr-date">
        {new Date().toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}
      </span>
    </div>
  </header>

  {#if loading}
    <!-- ================================================================
         LOADING SKELETON
         ================================================================ -->
    <div class="skel-kpi-row stagger-fade">
      {#each Array(6) as _}
        <div class="skel-card">
          <div class="skeleton" style="width:55%;height:10px;"></div>
          <div class="skeleton" style="width:75%;height:22px;margin-top:8px;"></div>
          <div class="skeleton" style="width:100%;height:28px;margin-top:10px;"></div>
        </div>
      {/each}
    </div>
    <div class="skel-main-row">
      <div class="skel-card skel-tall"><div class="skeleton" style="width:100%;height:100%;"></div></div>
      <div class="skel-card skel-tall"><div class="skeleton" style="width:100%;height:100%;"></div></div>
      <div class="skel-card skel-tall"><div class="skeleton" style="width:100%;height:100%;"></div></div>
    </div>
  {:else}
    <!-- ================================================================
         KPI CARDS ROW
         ================================================================ -->
    <div class="kpi-row stagger-fade">

      <!-- Market Status -->
      <div class="kpi-card">
        <div class="kpi-hdr">
          <Globe size={13} weight="duotone" />
          <span class="kpi-label">Market Status</span>
        </div>
        <div class="kpi-val-row">
          <span class="kpi-val" style="color:{statusColor}; font-size: var(--text-base);">{statusLabel}</span>
        </div>
        <div class="kpi-meta">
          <span>NYSE</span>
          <span class="kpi-meta-sep">|</span>
          <span>NASDAQ</span>
        </div>
      </div>

      <!-- S&P 500 -->
      <div class="kpi-card">
        <div class="kpi-hdr">
          <ChartLine size={13} weight="duotone" />
          <span class="kpi-label">S&P 500</span>
        </div>
        <div class="kpi-val-row">
          <span class="kpi-val mono-nums">{SIM_KPI.spx.price.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
          <span class="kpi-delta mono-nums" style="color:{changeBright(SIM_KPI.spx.changePct)};">
            {#if SIM_KPI.spx.changePct >= 0}<CaretUp size={11} weight="fill" />{:else}<CaretDown size={11} weight="fill" />{/if}
            {SIM_KPI.spx.changePct >= 0 ? '+' : ''}{SIM_KPI.spx.changePct.toFixed(2)}%
          </span>
        </div>
        <div class="kpi-spark">
          <svg viewBox="0 0 120 30" preserveAspectRatio="none">
            <defs>
              <linearGradient id="g-spx" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="oklch(0.64 0.16 155)" stop-opacity="0.30" />
                <stop offset="100%" stop-color="oklch(0.64 0.16 155)" stop-opacity="0.02" />
              </linearGradient>
            </defs>
            <path d={sparklineArea(SIM_SPARKLINES['SPX'], 120, 30)} fill="url(#g-spx)" />
            <polyline points={sparklinePath(SIM_SPARKLINES['SPX'], 120, 30)} fill="none" stroke="var(--bullish)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>
      </div>

      <!-- VIX -->
      <div class="kpi-card">
        <div class="kpi-hdr">
          <Pulse size={13} weight="duotone" />
          <span class="kpi-label">VIX</span>
        </div>
        <div class="kpi-val-row">
          <span class="kpi-val mono-nums">{SIM_KPI.vix.price.toFixed(2)}</span>
          <span class="kpi-delta mono-nums" style="color:{changeBright(-SIM_KPI.vix.changePct)};">
            {#if SIM_KPI.vix.changePct >= 0}<CaretUp size={11} weight="fill" />{:else}<CaretDown size={11} weight="fill" />{/if}
            {SIM_KPI.vix.changePct >= 0 ? '+' : ''}{SIM_KPI.vix.changePct.toFixed(2)}%
          </span>
        </div>
        <div class="kpi-spark">
          <svg viewBox="0 0 120 30" preserveAspectRatio="none">
            <defs>
              <linearGradient id="g-vix" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="oklch(0.64 0.16 155)" stop-opacity="0.30" />
                <stop offset="100%" stop-color="oklch(0.64 0.16 155)" stop-opacity="0.02" />
              </linearGradient>
            </defs>
            <path d={sparklineArea(SIM_SPARKLINES['VIX'], 120, 30)} fill="url(#g-vix)" />
            <polyline points={sparklinePath(SIM_SPARKLINES['VIX'], 120, 30)} fill="none" stroke="var(--bullish)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>
      </div>

      <!-- Put/Call Ratio -->
      <div class="kpi-card">
        <div class="kpi-hdr">
          <Gauge size={13} weight="duotone" />
          <span class="kpi-label">Put/Call Ratio</span>
        </div>
        <div class="kpi-val-row">
          <span class="kpi-val mono-nums">{SIM_KPI.putCallRatio.toFixed(2)}</span>
          <span class="kpi-tag" style="background:var(--bullish-bg);color:var(--bullish-bright);">Bullish</span>
        </div>
        <div class="kpi-spark">
          <svg viewBox="0 0 120 30" preserveAspectRatio="none">
            <defs>
              <linearGradient id="g-pcr" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="oklch(0.62 0.20 290)" stop-opacity="0.30" />
                <stop offset="100%" stop-color="oklch(0.62 0.20 290)" stop-opacity="0.02" />
              </linearGradient>
            </defs>
            <path d={sparklineArea(SIM_SPARKLINES['pcr'], 120, 30)} fill="url(#g-pcr)" />
            <polyline points={sparklinePath(SIM_SPARKLINES['pcr'], 120, 30)} fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>
      </div>

      <!-- Total Volume -->
      <div class="kpi-card">
        <div class="kpi-hdr">
          <ChartBar size={13} weight="duotone" />
          <span class="kpi-label">Total Volume</span>
        </div>
        <div class="kpi-val-row">
          <span class="kpi-val mono-nums">{SIM_KPI.totalVolume.toFixed(1)}B</span>
          <span class="kpi-sub-val">shares</span>
        </div>
        <div class="kpi-spark">
          <svg viewBox="0 0 120 30" preserveAspectRatio="none">
            <defs>
              <linearGradient id="g-vol" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="oklch(0.78 0.14 250)" stop-opacity="0.30" />
                <stop offset="100%" stop-color="oklch(0.78 0.14 250)" stop-opacity="0.02" />
              </linearGradient>
            </defs>
            <path d={sparklineArea(SIM_SPARKLINES['volume'], 120, 30)} fill="url(#g-vol)" />
            <polyline points={sparklinePath(SIM_SPARKLINES['volume'], 120, 30)} fill="none" stroke="var(--neutral-bright)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>
      </div>

      <!-- Market Breadth -->
      <div class="kpi-card">
        <div class="kpi-hdr">
          <TrendUp size={13} weight="duotone" />
          <span class="kpi-label">Breadth (A/D)</span>
        </div>
        <div class="kpi-val-row">
          <span class="kpi-val mono-nums">{SIM_KPI.breadth.toFixed(2)}</span>
          <span class="kpi-tag" style="background:var(--bullish-bg);color:var(--bullish-bright);">Strong</span>
        </div>
        <div class="kpi-spark">
          <svg viewBox="0 0 120 30" preserveAspectRatio="none">
            <defs>
              <linearGradient id="g-brd" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="oklch(0.64 0.16 155)" stop-opacity="0.30" />
                <stop offset="100%" stop-color="oklch(0.64 0.16 155)" stop-opacity="0.02" />
              </linearGradient>
            </defs>
            <path d={sparklineArea(SIM_SPARKLINES['breadth'], 120, 30)} fill="url(#g-brd)" />
            <polyline points={sparklinePath(SIM_SPARKLINES['breadth'], 120, 30)} fill="none" stroke="var(--bullish)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>
      </div>
    </div>

    <!-- ================================================================
         MAIN 3-COLUMN GRID
         ================================================================ -->
    <div class="main-grid">

      <!-- ============================================================
           LEFT: Market Internals
           ============================================================ -->
      <div class="glass-panel internals-col">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <Pulse size={15} weight="duotone" />
            <h2 class="panel-title">Market Internals</h2>
          </div>
          <span class="live-badge">LIVE</span>
        </div>

        <InternalsBar tick={SIM_KPI.tickVal} trin={SIM_KPI.trinVal} vix={SIM_KPI.vix.price} advDecRatio={SIM_KPI.breadth} />

        <!-- Breadth bar -->
        <div class="breadth-section">
          <div class="breadth-hdr">
            <span class="breadth-title">Market Breadth</span>
            <span class="breadth-stats mono-nums">
              <span style="color:var(--bullish-bright);">{SIM_KPI.advancers}</span>
              <span class="sep">/</span>
              <span style="color:var(--bearish-bright);">{SIM_KPI.decliners}</span>
              <span class="sep">/</span>
              <span style="color:var(--text-tertiary);">{SIM_KPI.unchanged}</span>
            </span>
          </div>
          <div class="breadth-bar">
            <div class="bar-seg bar-adv" style="width:{advPct.toFixed(1)}%;" title="Advancing: {SIM_KPI.advancers} ({advPct.toFixed(1)}%)"></div>
            <div class="bar-seg bar-unch" style="width:{unchPct.toFixed(1)}%;" title="Unchanged: {SIM_KPI.unchanged}"></div>
            <div class="bar-seg bar-dec" style="width:{decPct.toFixed(1)}%;" title="Declining: {SIM_KPI.decliners} ({decPct.toFixed(1)}%)"></div>
          </div>
          <div class="breadth-labels">
            <span class="breadth-lbl" style="color:var(--bullish);">
              <CaretUp size={10} weight="fill" />
              {advPct.toFixed(0)}% Adv
            </span>
            <span class="breadth-lbl" style="color:var(--bearish);">
              <CaretDown size={10} weight="fill" />
              {decPct.toFixed(0)}% Dec
            </span>
          </div>
        </div>

        <!-- New Highs / Lows -->
        <div class="hilo-row">
          <div class="hilo-cell">
            <span class="hilo-label">New Highs</span>
            <span class="hilo-val mono-nums" style="color:var(--bullish-bright);">{SIM_KPI.newHighs}</span>
          </div>
          <div class="hilo-sep"></div>
          <div class="hilo-cell">
            <span class="hilo-label">New Lows</span>
            <span class="hilo-val mono-nums" style="color:var(--bearish-bright);">{SIM_KPI.newLows}</span>
          </div>
          <div class="hilo-sep"></div>
          <div class="hilo-cell">
            <span class="hilo-label">H/L Ratio</span>
            <span class="hilo-val mono-nums" style="color:var(--bullish-bright);">{(SIM_KPI.newHighs / SIM_KPI.newLows).toFixed(1)}</span>
          </div>
        </div>
      </div>

      <!-- ============================================================
           CENTER: Recent Signals Feed
           ============================================================ -->
      <div class="glass-panel signals-col">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <Lightning size={15} weight="duotone" />
            <h2 class="panel-title">Recent Signals</h2>
            <span class="count-badge mono-nums">{SIM_SIGNALS.length}</span>
          </div>
          <a href="/scanner" class="link-all">
            View all
            <CaretUp size={11} style="transform:rotate(90deg);" />
          </a>
        </div>

        <div class="signals-feed">
          {#each SIM_SIGNALS as sig (sig.id)}
            <div class="sig-row">
              <!-- Time -->
              <span class="sig-time mono-nums">{sig.timestamp}</span>

              <!-- Icon -->
              <span class="sig-icon" style="color:{dirBright(sig.direction)};">
                {#if signalIconKind(sig.signalType) === 'lightning'}
                  <Lightning size={13} weight="fill" />
                {:else if signalIconKind(sig.signalType) === 'chart-bar'}
                  <ChartBar size={13} weight="fill" />
                {:else if signalIconKind(sig.signalType) === 'gauge'}
                  <Gauge size={13} weight="fill" />
                {:else if signalIconKind(sig.signalType) === 'target'}
                  <Target size={13} weight="fill" />
                {:else if signalIconKind(sig.signalType) === 'eye'}
                  <Eye size={13} weight="fill" />
                {:else if signalIconKind(sig.signalType) === 'fire'}
                  <Fire size={13} weight="fill" />
                {:else if signalIconKind(sig.signalType) === 'globe'}
                  <Globe size={13} weight="fill" />
                {:else if signalIconKind(sig.signalType) === 'trend-down'}
                  <TrendDown size={13} weight="fill" />
                {:else}
                  <Pulse size={13} weight="fill" />
                {/if}
              </span>

              <!-- Symbol + Type -->
              <span class="sig-sym mono-nums">{sig.symbol}</span>
              <span class="sig-type">{sig.signalType}</span>

              <!-- Strength -->
              <span class="sig-str">
                {#each Array(5) as _, si}
                  <span class="str-pip" style="background:{si < sig.strength ? dirBright(sig.direction) : 'var(--bg-overlay)'};"></span>
                {/each}
              </span>

              <!-- Price + Change -->
              <span class="sig-price-col">
                <span class="sig-price mono-nums">${sig.price.toFixed(2)}</span>
                <span class="sig-chg mono-nums" style="color:{changeBright(sig.change)};">
                  {sig.change >= 0 ? '+' : ''}{sig.change.toFixed(2)}%
                </span>
              </span>
            </div>
          {/each}
        </div>
      </div>

      <!-- ============================================================
           RIGHT: Sector Performance Heatmap
           ============================================================ -->
      <div class="glass-panel sectors-col">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <ChartBar size={15} weight="duotone" />
            <h2 class="panel-title">Sector Performance</h2>
          </div>
          <span class="panel-sub-lbl">GICS 11</span>
        </div>

        <div class="sector-grid">
          {#each sortedSectors as sec (sec.ticker)}
            <div class="sector-tile" style="background:{sectorHeatBg(sec.change)};border-color:{sectorHeatBorder(sec.change)};">
              <div class="sector-tile-hdr">
                <span class="sector-ticker mono-nums">{sec.ticker}</span>
                <span class="sector-chg mono-nums" style="color:{sectorHeatText(sec.change)};">
                  {sec.change >= 0 ? '+' : ''}{sec.change.toFixed(2)}%
                </span>
              </div>
              <span class="sector-name">{sec.name}</span>
              <span class="sector-wt mono-nums">{sec.weight.toFixed(1)}%</span>
            </div>
          {/each}
        </div>

        <div class="sector-summary">
          <div class="summary-item">
            <CaretUp size={11} weight="fill" style="color:var(--bullish-bright);" />
            <span class="summary-ct mono-nums" style="color:var(--bullish-bright);">
              {SIM_SECTORS.filter(s => s.change > 0).length}
            </span>
            <span class="summary-lbl">advancing</span>
          </div>
          <div class="summary-item">
            <CaretDown size={11} weight="fill" style="color:var(--bearish-bright);" />
            <span class="summary-ct mono-nums" style="color:var(--bearish-bright);">
              {SIM_SECTORS.filter(s => s.change < 0).length}
            </span>
            <span class="summary-lbl">declining</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ================================================================
         ROW 2: SCANNER RESULTS + GEX OVERVIEW
         ================================================================ -->
    <div class="scanner-row">

      <!-- Scanner Results (compact table) -->
      <div class="glass-panel scanner-table-panel">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <MagnifyingGlass size={15} weight="duotone" />
            <h2 class="panel-title">Scanner Results</h2>
            <span class="count-badge mono-nums">{SIM_SCANNER.length}</span>
          </div>
          <a href="/scanner" class="link-all">
            Full Scanner
            <CaretUp size={11} style="transform:rotate(90deg);" />
          </a>
        </div>

        <div class="mini-table-wrap">
          <table class="mini-table">
            <thead>
              <tr>
                <th class="th-rank">#</th>
                <th class="th-sym">Symbol</th>
                <th class="th-num">Price</th>
                <th class="th-num">Chg%</th>
                <th class="th-num">Volume</th>
                <th class="th-signal">Signal</th>
                <th class="th-str">Str</th>
                <th class="th-num">Score</th>
              </tr>
            </thead>
            <tbody>
              {#each SIM_SCANNER as row (row.rank)}
                <tr class="tbl-row">
                  <td class="td-rank mono-nums">{row.rank}</td>
                  <td class="td-sym">
                    <span class="sym-ticker">{row.symbol}</span>
                    <span class="sym-name">{row.name}</span>
                  </td>
                  <td class="td-num mono-nums">${row.price.toFixed(2)}</td>
                  <td class="td-num mono-nums" style="color:{changeBright(row.changePct)};">
                    {row.changePct >= 0 ? '+' : ''}{row.changePct.toFixed(2)}%
                  </td>
                  <td class="td-num mono-nums">{fmtVol(row.volume)}</td>
                  <td class="td-signal">
                    <span class="signal-badge signal-badge--{row.signal.toLowerCase()}">{row.signal}</span>
                  </td>
                  <td class="td-str">
                    {#each Array(5) as _, si}
                      <span class="str-pip" style="background:{si < row.strength ? 'var(--accent-bright)' : 'var(--bg-overlay)'};"></span>
                    {/each}
                  </td>
                  <td class="td-num mono-nums td-score" style="color:{row.score >= 90 ? 'var(--bullish-bright)' : row.score >= 75 ? 'var(--text-primary)' : 'var(--text-secondary)'};">
                    {row.score}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>

      <!-- GEX Scanner Overview -->
      <div class="glass-panel gex-panel">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <GitDiff size={15} weight="duotone" />
            <h2 class="panel-title">GEX Scanner</h2>
          </div>
          <a href="/options" class="link-all">
            Full Analytics
            <CaretUp size={11} style="transform:rotate(90deg);" />
          </a>
        </div>

        <!-- GEX KPI strip -->
        <div class="gex-kpis">
          <div class="gex-kpi">
            <span class="gex-kpi-label">Net GEX</span>
            <span class="gex-kpi-val mono-nums" style="color:{SIM_GEX.netGex >= 0 ? 'var(--bullish-bright)' : 'var(--bearish-bright)'};">
              {SIM_GEX.netGex >= 0 ? '+' : ''}{SIM_GEX.netGex.toFixed(2)}B
            </span>
          </div>
          <div class="gex-kpi">
            <span class="gex-kpi-label">Dealer</span>
            <span class="gex-kpi-val mono-nums" style="color:{SIM_GEX.dealerPos === 'Long Gamma' ? 'var(--bullish-bright)' : SIM_GEX.dealerPos === 'Short Gamma' ? 'var(--bearish-bright)' : 'var(--text-secondary)'};">
              {SIM_GEX.dealerPos}
            </span>
          </div>
          <div class="gex-kpi">
            <span class="gex-kpi-label">Key Strike</span>
            <span class="gex-kpi-val mono-nums">{SIM_GEX.keyStrike.toLocaleString()}</span>
          </div>
          <div class="gex-kpi">
            <span class="gex-kpi-label">{SIM_GEX.spotSymbol}</span>
            <span class="gex-kpi-val mono-nums">{SIM_GEX.spotPrice.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
          </div>
        </div>

        <!-- Mini GEX profile chart -->
        <div class="gex-chart">
          {#each SIM_GEX.profile as bar (bar.strike)}
            <div class="gex-bar-row">
              <span class="gex-strike mono-nums">{bar.strike.toLocaleString()}</span>
              <div class="gex-bar-container">
                <div class="gex-bar gex-bar--put" style="width:{(Math.abs(bar.putGex) / gexMaxAbs * 100).toFixed(1)}%;"></div>
                <div class="gex-bar gex-bar--call" style="width:{(bar.callGex / gexMaxAbs * 100).toFixed(1)}%;"></div>
              </div>
              <span class="gex-net mono-nums" style="color:{bar.net >= 0 ? 'var(--bullish)' : 'var(--bearish)'};">
                {bar.net >= 0 ? '+' : ''}{bar.net.toFixed(2)}
              </span>
            </div>
          {/each}
        </div>
      </div>
    </div>

    <!-- ================================================================
         ROW 3: OPTIONS FLOW + DARK POOL + ALERTS
         ================================================================ -->
    <div class="bottom-grid">

      <!-- Options Flow Scanner -->
      <div class="glass-panel flow-panel">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <Swap size={15} weight="duotone" />
            <h2 class="panel-title">Options Flow</h2>
            <span class="count-badge mono-nums">{SIM_FLOW.length}</span>
          </div>
          <a href="/options/flow" class="link-all">
            Full Flow
            <CaretUp size={11} style="transform:rotate(90deg);" />
          </a>
        </div>

        <div class="mini-feed">
          {#each SIM_FLOW as flow, i (i)}
            <div class="feed-row">
              <span class="feed-time mono-nums">{flow.time}</span>
              <span class="feed-sym mono-nums">{flow.symbol}</span>
              <span class="feed-badge feed-badge--{flow.type === 'C' ? 'call' : 'put'}">{flow.type}</span>
              <span class="feed-detail mono-nums">{flow.strike.toLocaleString()}</span>
              <span class="feed-expiry">{flow.expiry}</span>
              <span class="feed-side feed-side--{flow.side.toLowerCase()}">{flow.side}</span>
              <span class="feed-premium mono-nums">{fmtPremium(flow.premium)}</span>
              <span class="feed-flags">
                {#each flow.flags as flag}
                  <span class="flag-chip">{flag}</span>
                {/each}
              </span>
            </div>
          {/each}
        </div>
      </div>

      <!-- Dark Pool Scanner -->
      <div class="glass-panel darkpool-panel">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <Bank size={15} weight="duotone" />
            <h2 class="panel-title">Dark Pool</h2>
            <span class="count-badge mono-nums">{SIM_DARKPOOL.length}</span>
          </div>
          <a href="/institutional" class="link-all">
            Full View
            <CaretUp size={11} style="transform:rotate(90deg);" />
          </a>
        </div>

        <div class="mini-feed">
          {#each SIM_DARKPOOL as dp, i (i)}
            <div class="feed-row">
              <span class="feed-time mono-nums">{dp.time}</span>
              <span class="feed-sym mono-nums">{dp.symbol}</span>
              <span class="feed-detail mono-nums">${dp.price.toFixed(2)}</span>
              <span class="feed-detail mono-nums">{fmtVol(dp.size)}</span>
              <span class="feed-premium mono-nums">{fmtPremium(dp.notional)}</span>
              <span class="feed-side feed-side--{dp.side.toLowerCase()}">{dp.side}</span>
            </div>
          {/each}
        </div>
      </div>

      <!-- Active Alerts -->
      <div class="glass-panel alerts-panel">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <Bell size={15} weight="duotone" />
            <h2 class="panel-title">Active Alerts</h2>
            <span class="count-badge mono-nums">{SIM_ALERTS.length}</span>
          </div>
          <a href="/alerts" class="link-all">
            All Alerts
            <CaretUp size={11} style="transform:rotate(90deg);" />
          </a>
        </div>

        <div class="mini-feed">
          {#each SIM_ALERTS as alert, i (i)}
            <div class="feed-row alert-row">
              <span class="feed-time mono-nums">{alert.time}</span>
              <span class="feed-sym mono-nums">{alert.symbol}</span>
              <span class="alert-dir-badge alert-dir--{alert.direction.toLowerCase()}">{alert.direction}</span>
              <span class="alert-type">{alert.type}</span>
              <span class="alert-desc">{alert.description}</span>
              <span class="feed-premium mono-nums">${alert.price.toFixed(2)}</span>
            </div>
          {/each}
        </div>
      </div>
    </div>

    <!-- ================================================================
         ROW 4: INSTITUTIONAL INTELLIGENCE
         ================================================================ -->
    <div class="inst-row">

      <!-- Short Interest Scanner -->
      <div class="glass-panel">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <ChartBar size={15} weight="duotone" />
            <h2 class="panel-title">Short Interest</h2>
            <span class="count-badge mono-nums">{SIM_SHORT_INTEREST.length}</span>
          </div>
          <a href="/institutional" class="link-all">Details <CaretUp size={11} style="transform:rotate(90deg);" /></a>
        </div>
        <div class="mini-table-wrap">
          <table class="mini-table">
            <thead><tr>
              <th class="th-sym">Symbol</th>
              <th class="th-num">SI%</th>
              <th class="th-num">DTC</th>
              <th class="th-num">Util%</th>
              <th class="th-num">Squeeze</th>
            </tr></thead>
            <tbody>
              {#each SIM_SHORT_INTEREST as row}
                <tr class="tbl-row">
                  <td class="td-sym"><span class="sym-ticker">{row.symbol}</span><span class="sym-name">{row.name}</span></td>
                  <td class="td-num mono-nums" style="color:{row.shortPct >= 20 ? 'var(--bearish-bright)' : row.shortPct >= 10 ? 'oklch(0.80 0.14 85)' : 'var(--text-primary)'};">{row.shortPct.toFixed(1)}%</td>
                  <td class="td-num mono-nums">{row.daysToC.toFixed(1)}</td>
                  <td class="td-num mono-nums">{row.utilization.toFixed(1)}%</td>
                  <td class="td-num mono-nums td-score" style="color:{row.sqScore >= 85 ? 'var(--bearish-bright)' : row.sqScore >= 70 ? 'oklch(0.80 0.14 85)' : 'var(--text-secondary)'};">{row.sqScore}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>

      <!-- ETF Fund Flows -->
      <div class="glass-panel">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <Funnel size={15} weight="duotone" />
            <h2 class="panel-title">ETF Flows</h2>
          </div>
          <a href="/institutional" class="link-all">Details <CaretUp size={11} style="transform:rotate(90deg);" /></a>
        </div>
        <div class="mini-table-wrap">
          <table class="mini-table">
            <thead><tr>
              <th class="th-sym">ETF</th>
              <th class="th-num">Flow ($M)</th>
              <th class="th-num">AUM ($B)</th>
              <th class="th-num">Flow%</th>
            </tr></thead>
            <tbody>
              {#each SIM_ETF_FLOWS as row}
                <tr class="tbl-row">
                  <td class="td-sym"><span class="sym-ticker">{row.ticker}</span><span class="sym-name">{row.name}</span></td>
                  <td class="td-num mono-nums" style="color:{changeBright(row.flow)};">{row.flow >= 0 ? '+' : ''}{row.flow.toLocaleString()}</td>
                  <td class="td-num mono-nums">{row.aum.toFixed(1)}</td>
                  <td class="td-num mono-nums" style="color:{changeBright(row.flowPct)};">{row.flowPct >= 0 ? '+' : ''}{row.flowPct.toFixed(2)}%</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Insider Transactions -->
      <div class="glass-panel">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <Eye size={15} weight="duotone" />
            <h2 class="panel-title">Insider Tracker</h2>
            <span class="count-badge mono-nums">{SIM_INSIDER.length}</span>
          </div>
          <a href="/institutional" class="link-all">Details <CaretUp size={11} style="transform:rotate(90deg);" /></a>
        </div>
        <div class="mini-feed">
          {#each SIM_INSIDER as txn}
            <div class="feed-row">
              <span class="feed-time mono-nums">{txn.date}</span>
              <span class="feed-sym mono-nums">{txn.symbol}</span>
              <span class="feed-side feed-side--{txn.type.toLowerCase()}">{txn.type}</span>
              <span class="feed-detail">{txn.insider}</span>
              <span class="feed-expiry">{txn.role}</span>
              <span class="feed-premium mono-nums">{fmtPremium(txn.value)}</span>
            </div>
          {/each}
        </div>
      </div>
    </div>

    <!-- ================================================================
         ROW 5: MARKET INTELLIGENCE
         ================================================================ -->
    <div class="intel-row">

      <!-- Sentiment Gauge -->
      <div class="glass-panel intel-card">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <Gauge size={15} weight="duotone" />
            <h2 class="panel-title">Sentiment</h2>
          </div>
          <span class="panel-sub-lbl">Fear & Greed</span>
        </div>
        <div class="intel-main">
          <div class="sentiment-gauge">
            <span class="sentiment-score mono-nums" style="color:{SIM_SENTIMENT.score >= 75 ? 'var(--bullish-bright)' : SIM_SENTIMENT.score >= 50 ? 'oklch(0.80 0.14 85)' : SIM_SENTIMENT.score >= 25 ? 'oklch(0.70 0.14 55)' : 'var(--bearish-bright)'};">{SIM_SENTIMENT.score}</span>
            <span class="sentiment-label">{SIM_SENTIMENT.label}</span>
          </div>
          <div class="sentiment-bar">
            <div class="sentiment-marker" style="left:{SIM_SENTIMENT.score}%;"></div>
          </div>
          <div class="sentiment-range">
            <span style="color:var(--bearish);">Extreme Fear</span>
            <span style="color:var(--bullish);">Extreme Greed</span>
          </div>
        </div>
        <div class="intel-sub-metrics">
          <div class="sub-metric"><span class="sub-label">Prev</span><span class="sub-val mono-nums">{SIM_SENTIMENT.prevScore}</span></div>
          <div class="sub-metric"><span class="sub-label">1W Ago</span><span class="sub-val mono-nums">{SIM_SENTIMENT.weekAgo}</span></div>
          <div class="sub-metric"><span class="sub-label">1M Ago</span><span class="sub-val mono-nums">{SIM_SENTIMENT.monthAgo}</span></div>
        </div>
      </div>

      <!-- Market Regime -->
      <div class="glass-panel intel-card">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <Globe size={15} weight="duotone" />
            <h2 class="panel-title">Regime</h2>
          </div>
          <span class="panel-sub-lbl">Classification</span>
        </div>
        <div class="intel-main">
          <div class="regime-display">
            <span class="regime-badge regime--{SIM_REGIME.regime.toLowerCase()}">{SIM_REGIME.regime}</span>
            <span class="regime-days mono-nums">{SIM_REGIME.daysInRegime}d</span>
          </div>
        </div>
        <div class="intel-sub-metrics">
          <div class="sub-metric"><span class="sub-label">VIX</span><span class="sub-val mono-nums">{SIM_REGIME.vixRegime}</span></div>
          <div class="sub-metric"><span class="sub-label">Phase</span><span class="sub-val mono-nums">{SIM_REGIME.phase}</span></div>
          <div class="sub-metric"><span class="sub-label">Trend</span><span class="sub-val mono-nums" style="color:var(--bullish-bright);">{SIM_REGIME.trendStr}%</span></div>
        </div>
      </div>

      <!-- Liquidity Monitor -->
      <div class="glass-panel intel-card">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <Bank size={15} weight="duotone" />
            <h2 class="panel-title">Liquidity</h2>
          </div>
          <span class="panel-sub-lbl">Fed Watch</span>
        </div>
        <div class="intel-main">
          <div class="liq-main-val">
            <span class="liq-label">Net Liquidity</span>
            <span class="liq-val mono-nums">${SIM_LIQUIDITY.netLiq.toFixed(2)}T</span>
            <span class="liq-chg mono-nums" style="color:{changeBright(SIM_LIQUIDITY.netLiqChg)};">
              {SIM_LIQUIDITY.netLiqChg >= 0 ? '+' : ''}{SIM_LIQUIDITY.netLiqChg.toFixed(2)}T
            </span>
          </div>
        </div>
        <div class="intel-sub-metrics">
          <div class="sub-metric"><span class="sub-label">Fed Bal</span><span class="sub-val mono-nums">${SIM_LIQUIDITY.fedBal}T</span></div>
          <div class="sub-metric"><span class="sub-label">RRP</span><span class="sub-val mono-nums">${SIM_LIQUIDITY.rrp}B</span></div>
          <div class="sub-metric"><span class="sub-label">TGA</span><span class="sub-val mono-nums">${SIM_LIQUIDITY.tga}B</span></div>
        </div>
      </div>

      <!-- VIX Term Structure -->
      <div class="glass-panel intel-card">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <ChartLine size={15} weight="duotone" />
            <h2 class="panel-title">VIX Term</h2>
          </div>
          <span class="panel-sub-lbl" style="color:var(--bullish);">Contango</span>
        </div>
        <div class="intel-main">
          <div class="vix-term-chart">
            <svg viewBox="0 0 200 60" preserveAspectRatio="none" class="vix-svg">
              <polyline
                points={SIM_VIX_TERM.map((p, i) => `${(i / (SIM_VIX_TERM.length - 1)) * 190 + 5},${55 - ((p.value - 13) / 7) * 50}`).join(' ')}
                fill="none" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
              />
              {#each SIM_VIX_TERM as p, i}
                <circle cx={(i / (SIM_VIX_TERM.length - 1)) * 190 + 5} cy={55 - ((p.value - 13) / 7) * 50} r="3" fill="var(--accent)" />
              {/each}
            </svg>
          </div>
        </div>
        <div class="intel-sub-metrics vix-labels">
          {#each SIM_VIX_TERM as pt}
            <div class="sub-metric">
              <span class="sub-label">{pt.label}</span>
              <span class="sub-val mono-nums">{pt.value.toFixed(1)}</span>
            </div>
          {/each}
        </div>
      </div>
    </div>

    <!-- ================================================================
         ROW 6: TECHNICAL SCANNER + UNUSUAL OPTIONS
         ================================================================ -->
    <div class="tech-row">

      <!-- Technical Signals -->
      <div class="glass-panel">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <Target size={15} weight="duotone" />
            <h2 class="panel-title">Technical Scanner</h2>
            <span class="count-badge mono-nums">{SIM_TECHNICAL.length}</span>
          </div>
          <a href="/analysis" class="link-all">Analysis <CaretUp size={11} style="transform:rotate(90deg);" /></a>
        </div>
        <div class="mini-table-wrap">
          <table class="mini-table">
            <thead><tr>
              <th class="th-sym">Symbol</th>
              <th>Signal</th>
              <th>Indicator</th>
              <th class="th-num">Value</th>
              <th class="th-signal">Dir</th>
            </tr></thead>
            <tbody>
              {#each SIM_TECHNICAL as row}
                <tr class="tbl-row">
                  <td class="sym-ticker mono-nums" style="padding:5px 8px;">{row.symbol}</td>
                  <td style="padding:5px 8px;font-size:10px;color:var(--text-secondary);">{row.signal}</td>
                  <td style="padding:5px 8px;"><span class="signal-badge signal-badge--tech">{row.indicator}</span></td>
                  <td class="td-num mono-nums">{row.value.toFixed(2)}</td>
                  <td class="td-signal"><span class="signal-badge signal-badge--{row.direction === 'bullish' ? 'volume' : 'gamma'}" style="font-size:8px;">{row.direction === 'bullish' ? 'BULL' : 'BEAR'}</span></td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Unusual Options Activity -->
      <div class="glass-panel">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <Fire size={15} weight="duotone" />
            <h2 class="panel-title">Unusual Options</h2>
            <span class="count-badge mono-nums">{SIM_UNUSUAL_OPT.length}</span>
          </div>
          <a href="/options" class="link-all">Options <CaretUp size={11} style="transform:rotate(90deg);" /></a>
        </div>
        <div class="mini-table-wrap">
          <table class="mini-table">
            <thead><tr>
              <th class="th-sym">Symbol</th>
              <th class="th-num">Vol/OI</th>
              <th class="th-num">Volume</th>
              <th class="th-num">OI</th>
              <th class="th-num">IV Rank</th>
              <th class="th-signal">Sent</th>
            </tr></thead>
            <tbody>
              {#each SIM_UNUSUAL_OPT as row}
                <tr class="tbl-row">
                  <td class="sym-ticker mono-nums" style="padding:5px 8px;">{row.symbol}</td>
                  <td class="td-num mono-nums" style="color:{row.volOI >= 3 ? 'var(--bullish-bright)' : 'var(--text-primary)'};">{row.volOI.toFixed(1)}x</td>
                  <td class="td-num mono-nums">{fmtVol(row.vol)}</td>
                  <td class="td-num mono-nums">{fmtVol(row.oi)}</td>
                  <td class="td-num mono-nums" style="color:{row.ivRank >= 70 ? 'oklch(0.80 0.14 85)' : 'var(--text-secondary)'};">{row.ivRank}</td>
                  <td class="td-signal"><span class="signal-badge signal-badge--{row.sentiment === 'bullish' ? 'volume' : row.sentiment === 'bearish' ? 'gamma' : 'flow'}" style="font-size:8px;">{row.sentiment === 'bullish' ? 'BULL' : row.sentiment === 'bearish' ? 'BEAR' : 'NEUT'}</span></td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ================================================================
         ROW 7: TOP MOVERS + EXPECTED MOVE
         ================================================================ -->
    <div class="movers-row">

      <!-- Top Gainers -->
      <div class="glass-panel">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <ArrowUp size={15} weight="duotone" />
            <h2 class="panel-title">Top Gainers</h2>
          </div>
          <a href="/market" class="link-all">Market <CaretUp size={11} style="transform:rotate(90deg);" /></a>
        </div>
        <div class="mini-feed">
          {#each SIM_GAINERS as row, i}
            <div class="feed-row">
              <span class="mover-rank mono-nums">{i + 1}</span>
              <span class="feed-sym mono-nums">{row.symbol}</span>
              <span class="feed-detail mono-nums">${row.price.toFixed(2)}</span>
              <span class="feed-premium mono-nums" style="color:var(--bullish-bright);">+{row.changePct.toFixed(2)}%</span>
              <span class="feed-detail mono-nums" style="margin-left:auto;">{fmtVol(row.volume)}</span>
            </div>
          {/each}
        </div>
      </div>

      <!-- Top Losers -->
      <div class="glass-panel">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <ArrowDown size={15} weight="duotone" />
            <h2 class="panel-title">Top Losers</h2>
          </div>
          <a href="/market" class="link-all">Market <CaretUp size={11} style="transform:rotate(90deg);" /></a>
        </div>
        <div class="mini-feed">
          {#each SIM_LOSERS as row, i}
            <div class="feed-row">
              <span class="mover-rank mono-nums">{i + 1}</span>
              <span class="feed-sym mono-nums">{row.symbol}</span>
              <span class="feed-detail mono-nums">${row.price.toFixed(2)}</span>
              <span class="feed-premium mono-nums" style="color:var(--bearish-bright);">{row.changePct.toFixed(2)}%</span>
              <span class="feed-detail mono-nums" style="margin-left:auto;">{fmtVol(row.volume)}</span>
            </div>
          {/each}
        </div>
      </div>

      <!-- Expected Move / Max Pain -->
      <div class="glass-panel">
        <div class="panel-hdr">
          <div class="panel-title-grp">
            <Target size={15} weight="duotone" />
            <h2 class="panel-title">Expected Move</h2>
          </div>
          <span class="panel-sub-lbl">{SIM_EXPECTED_MOVE.symbol}</span>
        </div>
        <div class="em-grid">
          <div class="em-cell">
            <span class="em-label">Spot</span>
            <span class="em-val mono-nums">{SIM_EXPECTED_MOVE.spot.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
          </div>
          <div class="em-cell">
            <span class="em-label">Exp Move</span>
            <span class="em-val mono-nums" style="color:var(--accent-bright, var(--accent));">±{SIM_EXPECTED_MOVE.expectedMove.toFixed(1)}</span>
          </div>
          <div class="em-cell">
            <span class="em-label">Max Pain</span>
            <span class="em-val mono-nums">{SIM_EXPECTED_MOVE.maxPain.toLocaleString()}</span>
          </div>
          <div class="em-cell">
            <span class="em-label">IV Rank</span>
            <span class="em-val mono-nums" style="color:{SIM_EXPECTED_MOVE.ivRank >= 50 ? 'oklch(0.80 0.14 85)' : 'var(--text-secondary)'};">{SIM_EXPECTED_MOVE.ivRank}</span>
          </div>
          <div class="em-cell">
            <span class="em-label">IV 30d</span>
            <span class="em-val mono-nums">{SIM_EXPECTED_MOVE.iv30.toFixed(1)}%</span>
          </div>
          <div class="em-cell">
            <span class="em-label">HV 30d</span>
            <span class="em-val mono-nums">{SIM_EXPECTED_MOVE.hv30.toFixed(1)}%</span>
          </div>
        </div>
        <div class="em-range">
          <span class="em-bound mono-nums" style="color:var(--bearish);">{(SIM_EXPECTED_MOVE.spot - SIM_EXPECTED_MOVE.expectedMove).toFixed(0)}</span>
          <div class="em-bar">
            <div class="em-bar-range"></div>
            <div class="em-bar-spot" style="left:50%;"></div>
            <div class="em-bar-maxpain" style="left:{((SIM_EXPECTED_MOVE.maxPain - (SIM_EXPECTED_MOVE.spot - SIM_EXPECTED_MOVE.expectedMove)) / (SIM_EXPECTED_MOVE.expectedMove * 2)) * 100}%;"></div>
          </div>
          <span class="em-bound mono-nums" style="color:var(--bullish);">{(SIM_EXPECTED_MOVE.spot + SIM_EXPECTED_MOVE.expectedMove).toFixed(0)}</span>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  /* ===================================================================
     PAGE LAYOUT
     =================================================================== */
  .dashboard-page {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: auto;
    padding: 14px 20px 24px;
    gap: 14px;
  }

  /* ===================================================================
     CONNECTION BANNER
     =================================================================== */
  .conn-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 14px;
    border-radius: var(--radius-lg);
    background: oklch(0.14 0.02 260 / 0.7);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border-subtle);
  }

  .warn-banner {
    border-color: oklch(0.52 0.10 85 / 0.40);
    background: oklch(0.16 0.04 85 / 0.15);
  }

  .banner-left {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-secondary);
  }

  .banner-text {
    font-size: var(--text-xs);
    font-weight: 500;
  }

  .banner-btn {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--accent);
    background: none;
    border: 1px solid var(--accent);
    border-radius: var(--radius-md);
    padding: 4px 12px;
    cursor: pointer;
    transition: background-color 150ms, color 150ms;
    text-decoration: none;
  }

  .banner-btn:hover {
    background: var(--accent);
    color: var(--bg-base);
  }

  /* ===================================================================
     PAGE HEADER
     =================================================================== */
  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }

  .hdr-left {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .page-title {
    font-size: var(--text-xl);
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.02em;
  }

  .status-chip {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 3px 11px 3px 7px;
    border-radius: var(--radius-full);
    background: oklch(0.14 0.02 260 / 0.6);
    border: 1px solid var(--border-subtle);
  }

  .status-dot-wrap {
    position: relative;
    width: 8px;
    height: 8px;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    position: relative;
    z-index: 1;
    display: block;
  }

  .status-ring {
    position: absolute;
    inset: -3px;
    border-radius: var(--radius-full);
    border: 1.5px solid;
    opacity: 0.5;
    animation: signal-ping 2s cubic-bezier(0, 0, 0.2, 1) infinite;
    display: block;
  }

  .status-text {
    font-size: var(--text-2xs);
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .hdr-right {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .hdr-sep {
    width: 1px;
    height: 20px;
    background: var(--border-subtle);
  }

  .hdr-clock {
    display: flex;
    align-items: center;
    gap: 5px;
    color: var(--text-secondary);
  }

  .clock-val {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-primary);
  }

  .hdr-date {
    font-size: var(--text-xs);
    font-family: var(--font-mono);
    color: var(--text-tertiary);
  }

  /* ===================================================================
     LOADING SKELETON
     =================================================================== */
  .skel-kpi-row {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 10px;
  }

  .skel-main-row {
    display: grid;
    grid-template-columns: 1fr 1.4fr 1fr;
    gap: 12px;
    flex: 1;
  }

  .skel-card {
    padding: 14px;
    border-radius: var(--radius-lg);
    background: oklch(0.14 0.02 260 / 0.7);
    border: 1px solid var(--border-subtle);
  }

  .skel-tall {
    min-height: 280px;
  }

  /* ===================================================================
     KPI CARDS ROW
     =================================================================== */
  .kpi-row {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 10px;
    flex-shrink: 0;
  }

  .kpi-card {
    background: oklch(0.14 0.02 260 / 0.7);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 12px 14px 8px;
    display: flex;
    flex-direction: column;
    gap: 5px;
    transition: border-color var(--duration-normal) ease,
                box-shadow var(--duration-normal) ease;
  }

  .kpi-card:hover {
    border-color: oklch(0.30 0.04 260 / 0.60);
    box-shadow: var(--glow-sm);
  }

  .kpi-hdr {
    display: flex;
    align-items: center;
    gap: 5px;
    color: var(--text-tertiary);
  }

  .kpi-label {
    font-size: var(--text-2xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-tertiary);
  }

  .kpi-val-row {
    display: flex;
    align-items: baseline;
    gap: 8px;
    flex-wrap: wrap;
  }

  .kpi-val {
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.2;
  }

  .kpi-delta {
    display: inline-flex;
    align-items: center;
    gap: 1px;
    font-size: var(--text-2xs);
    font-weight: 600;
  }

  .kpi-tag {
    font-size: 9px;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: var(--radius-full);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .kpi-sub-val {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    font-weight: 500;
  }

  .kpi-meta {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
  }

  .kpi-meta-sep {
    color: var(--text-disabled);
  }

  .kpi-spark {
    margin-top: auto;
    height: 30px;
    width: 100%;
  }

  .kpi-spark svg {
    width: 100%;
    height: 100%;
    display: block;
  }

  /* ===================================================================
     MAIN GRID (3-column)
     =================================================================== */
  .main-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 12px;
    flex: 1;
    min-height: 0;
  }

  @media (min-width: 1024px) {
    .main-grid {
      grid-template-columns: 1fr 1.4fr 1fr;
    }
  }

  /* ===================================================================
     GLASS PANEL (shared)
     =================================================================== */
  .glass-panel {
    background: oklch(0.14 0.02 260 / 0.7);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    overflow: hidden;
  }

  .panel-hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }

  .panel-title-grp {
    display: flex;
    align-items: center;
    gap: 7px;
    color: var(--text-secondary);
  }

  .panel-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .live-badge {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.10em;
    color: var(--bullish-bright);
    background: var(--bullish-bg);
    padding: 2px 8px;
    border-radius: var(--radius-full);
    border: 1px solid oklch(0.45 0.12 155 / 0.25);
  }

  .panel-sub-lbl {
    font-size: var(--text-2xs);
    font-weight: 600;
    color: var(--text-tertiary);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  /* ===================================================================
     MARKET INTERNALS (left column)
     =================================================================== */
  .internals-col {
    overflow: visible;
  }

  .breadth-section {
    display: flex;
    flex-direction: column;
    gap: 7px;
  }

  .breadth-hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .breadth-title {
    font-size: var(--text-2xs);
    font-weight: 600;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .breadth-stats {
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: var(--text-2xs);
    font-weight: 600;
  }

  .sep {
    color: var(--text-disabled);
  }

  .breadth-bar {
    display: flex;
    height: 10px;
    border-radius: var(--radius-full);
    overflow: hidden;
    background: var(--bg-base);
  }

  .bar-seg {
    height: 100%;
    transition: width 300ms ease;
  }

  .bar-adv {
    background: var(--bullish);
    border-radius: var(--radius-full) 0 0 var(--radius-full);
  }

  .bar-unch {
    background: var(--text-disabled);
  }

  .bar-dec {
    background: var(--bearish);
    border-radius: 0 var(--radius-full) var(--radius-full) 0;
  }

  .breadth-labels {
    display: flex;
    justify-content: space-between;
  }

  .breadth-lbl {
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: var(--text-2xs);
    font-weight: 600;
  }

  .hilo-row {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 16px;
    padding-top: 10px;
    border-top: 1px solid var(--border-subtle);
  }

  .hilo-cell {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
  }

  .hilo-label {
    font-size: 9px;
    font-weight: 600;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .hilo-val {
    font-size: var(--text-sm);
    font-weight: 700;
  }

  .hilo-sep {
    width: 1px;
    height: 28px;
    background: var(--border-subtle);
  }

  /* ===================================================================
     RECENT SIGNALS FEED (center column)
     =================================================================== */
  .signals-col {
    min-height: 0;
  }

  .count-badge {
    font-size: var(--text-2xs);
    font-weight: 700;
    color: var(--accent);
    background: var(--accent-bg);
    padding: 1px 7px;
    border-radius: var(--radius-full);
  }

  .link-all {
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--accent);
    transition: color 150ms;
    text-decoration: none;
  }

  .link-all:hover {
    color: var(--accent-bright);
  }

  .signals-feed {
    display: flex;
    flex-direction: column;
    gap: 1px;
    overflow-y: auto;
    flex: 1;
    min-height: 0;
  }

  .sig-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    border-radius: var(--radius-md);
    transition: background-color 120ms ease;
    flex-shrink: 0;
  }

  .sig-row:hover {
    background: var(--hover-overlay);
  }

  .sig-time {
    flex-shrink: 0;
    width: 54px;
    font-size: 10px;
    color: var(--text-tertiary);
    font-weight: 500;
  }

  .sig-icon {
    flex-shrink: 0;
    width: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .sig-sym {
    font-size: var(--text-xs);
    font-weight: 700;
    color: var(--text-primary);
    flex-shrink: 0;
    width: 44px;
  }

  .sig-type {
    font-size: 10px;
    color: var(--text-tertiary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
    min-width: 0;
  }

  .sig-str {
    display: flex;
    align-items: center;
    gap: 2px;
    flex-shrink: 0;
  }

  .str-pip {
    width: 3px;
    height: 10px;
    border-radius: 1px;
    display: block;
  }

  .sig-price-col {
    flex-shrink: 0;
    text-align: right;
    min-width: 68px;
  }

  .sig-price {
    display: block;
    font-size: var(--text-xs);
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.2;
  }

  .sig-chg {
    display: block;
    font-size: 10px;
    font-weight: 600;
    line-height: 1.2;
  }

  /* ===================================================================
     SECTOR HEATMAP (right column)
     =================================================================== */
  .sector-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 5px;
    flex: 1;
    min-height: 0;
    align-content: start;
  }

  .sector-tile {
    border-radius: var(--radius-md);
    padding: 8px 10px;
    border: 1px solid;
    display: flex;
    flex-direction: column;
    gap: 2px;
    transition: transform 120ms ease, box-shadow 120ms ease;
  }

  .sector-tile:hover {
    transform: translateY(-1px);
    box-shadow: var(--glow-sm);
  }

  .sector-tile-hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .sector-ticker {
    font-size: var(--text-2xs);
    font-weight: 700;
    color: var(--text-primary);
  }

  .sector-chg {
    font-size: var(--text-xs);
    font-weight: 700;
  }

  .sector-name {
    font-size: 9px;
    color: var(--text-secondary);
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sector-wt {
    font-size: 9px;
    color: var(--text-disabled);
    font-weight: 500;
  }

  .sector-summary {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 24px;
    padding-top: 8px;
    border-top: 1px solid var(--border-subtle);
    flex-shrink: 0;
  }

  .summary-item {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .summary-ct {
    font-size: var(--text-xs);
    font-weight: 700;
  }

  .summary-lbl {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    font-weight: 500;
  }

  /* ===================================================================
     SCANNER ROW (Scanner + GEX)
     =================================================================== */
  .scanner-row {
    display: grid;
    grid-template-columns: 1.8fr 1fr;
    gap: 12px;
    flex-shrink: 0;
  }

  .mini-table-wrap {
    overflow-x: auto;
    overflow-y: auto;
    flex: 1;
    min-height: 0;
  }

  .mini-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 11px;
  }

  .mini-table thead {
    position: sticky;
    top: 0;
    z-index: 1;
  }

  .mini-table th {
    font-size: 9px;
    font-weight: 700;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 6px 8px;
    text-align: left;
    background: oklch(0.12 0.02 260);
    border-bottom: 1px solid var(--border-subtle);
    white-space: nowrap;
  }

  .th-num, .th-str { text-align: right; }
  .th-rank { width: 28px; text-align: center; }
  .th-signal { text-align: center; }

  .tbl-row {
    transition: background-color 100ms;
  }

  .tbl-row:hover {
    background: var(--hover-overlay);
  }

  .tbl-row td {
    padding: 5px 8px;
    border-bottom: 1px solid oklch(0.18 0 0 / 0.4);
    vertical-align: middle;
  }

  .td-rank { text-align: center; font-size: 10px; color: var(--text-tertiary); font-weight: 600; }
  .td-num { text-align: right; font-size: 11px; font-weight: 600; color: var(--text-primary); }
  .td-score { font-weight: 800; }
  .td-signal { text-align: center; }
  .td-str { text-align: right; display: flex; gap: 2px; justify-content: flex-end; align-items: center; }

  .td-sym {
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .sym-ticker {
    font-weight: 700;
    font-size: 11px;
    color: var(--text-primary);
    font-family: var(--font-mono);
  }

  .sym-name {
    font-size: 9px;
    color: var(--text-tertiary);
    font-weight: 400;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 120px;
  }

  .signal-badge {
    font-size: 9px;
    font-weight: 700;
    padding: 1px 8px;
    border-radius: var(--radius-full);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    display: inline-block;
  }

  .signal-badge--gamma {
    color: oklch(0.80 0.14 290);
    background: oklch(0.20 0.06 290 / 0.50);
    border: 1px solid oklch(0.40 0.10 290 / 0.35);
  }

  .signal-badge--volume {
    color: oklch(0.80 0.14 155);
    background: oklch(0.20 0.06 155 / 0.50);
    border: 1px solid oklch(0.40 0.10 155 / 0.35);
  }

  .signal-badge--flow {
    color: oklch(0.80 0.14 85);
    background: oklch(0.20 0.06 85 / 0.50);
    border: 1px solid oklch(0.40 0.10 85 / 0.35);
  }

  /* GEX Panel */
  .gex-kpis {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
  }

  .gex-kpi {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 6px 4px;
    background: oklch(0.12 0.01 260 / 0.5);
    border-radius: var(--radius-md);
    border: 1px solid oklch(0.20 0.01 260 / 0.4);
  }

  .gex-kpi-label {
    font-size: 8px;
    font-weight: 700;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .gex-kpi-val {
    font-size: 12px;
    font-weight: 700;
    color: var(--text-primary);
  }

  .gex-chart {
    display: flex;
    flex-direction: column;
    gap: 3px;
    flex: 1;
    min-height: 0;
  }

  .gex-bar-row {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .gex-strike {
    flex-shrink: 0;
    width: 38px;
    font-size: 9px;
    color: var(--text-tertiary);
    text-align: right;
    font-weight: 500;
  }

  .gex-bar-container {
    flex: 1;
    display: flex;
    height: 14px;
    gap: 1px;
    position: relative;
  }

  .gex-bar {
    height: 100%;
    border-radius: 2px;
    transition: width 300ms ease;
  }

  .gex-bar--call {
    background: oklch(0.50 0.14 155);
  }

  .gex-bar--put {
    background: oklch(0.50 0.14 25);
  }

  .gex-net {
    flex-shrink: 0;
    width: 36px;
    font-size: 9px;
    text-align: right;
    font-weight: 600;
  }

  /* ===================================================================
     BOTTOM GRID (Flow + Dark Pool + Alerts)
     =================================================================== */
  .bottom-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    flex-shrink: 0;
  }

  .mini-feed {
    display: flex;
    flex-direction: column;
    gap: 1px;
    flex: 1;
    min-height: 0;
    overflow-y: auto;
  }

  .feed-row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 5px 6px;
    border-radius: var(--radius-sm);
    transition: background-color 100ms;
    flex-shrink: 0;
  }

  .feed-row:hover {
    background: var(--hover-overlay);
  }

  .feed-time {
    flex-shrink: 0;
    font-size: 9px;
    color: var(--text-tertiary);
    width: 48px;
    font-weight: 500;
  }

  .feed-sym {
    flex-shrink: 0;
    font-size: 11px;
    font-weight: 700;
    color: var(--text-primary);
    width: 36px;
  }

  .feed-badge {
    flex-shrink: 0;
    font-size: 9px;
    font-weight: 700;
    width: 16px;
    text-align: center;
    padding: 1px 0;
    border-radius: 3px;
  }

  .feed-badge--call {
    color: oklch(0.80 0.14 155);
    background: oklch(0.20 0.06 155 / 0.5);
  }

  .feed-badge--put {
    color: oklch(0.80 0.14 25);
    background: oklch(0.20 0.06 25 / 0.5);
  }

  .feed-detail {
    font-size: 10px;
    color: var(--text-secondary);
    flex-shrink: 0;
  }

  .feed-expiry {
    font-size: 9px;
    color: var(--text-tertiary);
    flex-shrink: 0;
  }

  .feed-side {
    font-size: 9px;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: 3px;
    flex-shrink: 0;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .feed-side--buy {
    color: oklch(0.78 0.14 155);
    background: oklch(0.20 0.06 155 / 0.5);
  }

  .feed-side--sell {
    color: oklch(0.78 0.14 25);
    background: oklch(0.20 0.06 25 / 0.5);
  }

  .feed-premium {
    font-size: 11px;
    font-weight: 700;
    color: var(--text-primary);
    margin-left: auto;
    flex-shrink: 0;
  }

  .feed-flags {
    display: flex;
    gap: 3px;
    flex-shrink: 0;
  }

  .flag-chip {
    font-size: 8px;
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 3px;
    color: oklch(0.85 0.12 250);
    background: oklch(0.20 0.06 250 / 0.5);
    border: 1px solid oklch(0.35 0.08 250 / 0.3);
    letter-spacing: 0.04em;
  }

  /* Alert-specific */
  .alert-row {
    flex-wrap: nowrap;
  }

  .alert-dir-badge {
    font-size: 8px;
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 3px;
    flex-shrink: 0;
    letter-spacing: 0.04em;
  }

  .alert-dir--bull {
    color: oklch(0.78 0.14 155);
    background: oklch(0.20 0.06 155 / 0.5);
  }

  .alert-dir--bear {
    color: oklch(0.78 0.14 25);
    background: oklch(0.20 0.06 25 / 0.5);
  }

  .alert-type {
    font-size: 10px;
    font-weight: 600;
    color: var(--text-primary);
    flex-shrink: 0;
    white-space: nowrap;
  }

  .alert-desc {
    font-size: 9px;
    color: var(--text-tertiary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    min-width: 0;
  }

  /* ===================================================================
     INSTITUTIONAL ROW
     =================================================================== */
  .inst-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    flex-shrink: 0;
  }

  /* ===================================================================
     MARKET INTELLIGENCE ROW
     =================================================================== */
  .intel-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    flex-shrink: 0;
  }

  .intel-card {
    gap: 8px;
  }

  .intel-main {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    gap: 6px;
  }

  .sentiment-gauge {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
  }

  .sentiment-score {
    font-size: 1.5rem;
    font-weight: 800;
    line-height: 1;
  }

  .sentiment-label {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .sentiment-bar {
    width: 100%;
    height: 6px;
    border-radius: var(--radius-full);
    background: linear-gradient(90deg, oklch(0.50 0.18 25), oklch(0.55 0.14 85), oklch(0.50 0.16 155));
    position: relative;
  }

  .sentiment-marker {
    position: absolute;
    top: -3px;
    width: 4px;
    height: 12px;
    background: var(--text-primary);
    border-radius: 2px;
    transform: translateX(-50%);
  }

  .sentiment-range {
    display: flex;
    justify-content: space-between;
    width: 100%;
    font-size: 8px;
    font-weight: 600;
  }

  .intel-sub-metrics {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--border-subtle);
  }

  .sub-metric {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1px;
  }

  .sub-label {
    font-size: 8px;
    font-weight: 700;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .sub-val {
    font-size: 11px;
    font-weight: 700;
    color: var(--text-primary);
  }

  .regime-display {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .regime-badge {
    font-size: var(--text-lg);
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 4px 16px;
    border-radius: var(--radius-md);
  }

  .regime--bull {
    color: var(--bullish-bright);
    background: var(--bullish-bg);
    border: 1px solid oklch(0.45 0.12 155 / 0.3);
  }

  .regime--bear {
    color: var(--bearish-bright);
    background: oklch(0.18 0.04 25 / 0.5);
    border: 1px solid oklch(0.45 0.12 25 / 0.3);
  }

  .regime--neutral {
    color: var(--text-secondary);
    background: oklch(0.18 0.02 260 / 0.5);
    border: 1px solid var(--border-subtle);
  }

  .regime--strong-bull { color: var(--bullish-bright); background: var(--bullish-bg); border: 1px solid oklch(0.45 0.12 155 / 0.3); }
  .regime--strong-bear { color: var(--bearish-bright); background: oklch(0.18 0.04 25 / 0.5); border: 1px solid oklch(0.45 0.12 25 / 0.3); }
  .regime--volatile { color: oklch(0.80 0.14 85); background: oklch(0.18 0.04 85 / 0.5); border: 1px solid oklch(0.45 0.10 85 / 0.3); }

  .regime-days {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    font-weight: 600;
  }

  .liq-main-val {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
  }

  .liq-label {
    font-size: 9px;
    font-weight: 700;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .liq-val {
    font-size: 1.25rem;
    font-weight: 800;
    color: var(--text-primary);
  }

  .liq-chg {
    font-size: var(--text-xs);
    font-weight: 600;
  }

  .vix-term-chart {
    width: 100%;
    height: 60px;
  }

  .vix-svg {
    width: 100%;
    height: 100%;
  }

  .vix-labels {
    flex-wrap: nowrap;
  }

  /* ===================================================================
     TECHNICAL ROW
     =================================================================== */
  .tech-row {
    display: grid;
    grid-template-columns: 1.2fr 1fr;
    gap: 12px;
    flex-shrink: 0;
  }

  .signal-badge--tech {
    color: oklch(0.80 0.14 250);
    background: oklch(0.20 0.06 250 / 0.50);
    border: 1px solid oklch(0.40 0.10 250 / 0.35);
  }

  /* ===================================================================
     MOVERS ROW
     =================================================================== */
  .movers-row {
    display: grid;
    grid-template-columns: 1fr 1fr 1.2fr;
    gap: 12px;
    flex-shrink: 0;
  }

  .mover-rank {
    width: 18px;
    text-align: center;
    color: var(--text-tertiary);
    font-size: 10px;
    font-weight: 600;
    flex-shrink: 0;
  }

  .em-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 6px;
  }

  .em-cell {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 6px 4px;
    background: oklch(0.12 0.01 260 / 0.5);
    border-radius: var(--radius-md);
    border: 1px solid oklch(0.20 0.01 260 / 0.4);
  }

  .em-label {
    font-size: 8px;
    font-weight: 700;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .em-val {
    font-size: 11px;
    font-weight: 700;
    color: var(--text-primary);
  }

  .em-range {
    display: flex;
    align-items: center;
    gap: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--border-subtle);
  }

  .em-bound {
    font-size: 10px;
    font-weight: 700;
    flex-shrink: 0;
  }

  .em-bar {
    flex: 1;
    height: 8px;
    background: oklch(0.18 0.02 260);
    border-radius: var(--radius-full);
    position: relative;
  }

  .em-bar-range {
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, oklch(0.40 0.12 25 / 0.4), oklch(0.18 0.02 260 / 0.2) 50%, oklch(0.40 0.12 155 / 0.4));
    border-radius: var(--radius-full);
  }

  .em-bar-spot {
    position: absolute;
    top: -2px;
    width: 4px;
    height: 12px;
    background: var(--text-primary);
    border-radius: 2px;
    transform: translateX(-50%);
  }

  .em-bar-maxpain {
    position: absolute;
    top: -2px;
    width: 4px;
    height: 12px;
    background: var(--accent);
    border-radius: 2px;
    transform: translateX(-50%);
  }

  /* ===================================================================
     RESPONSIVE
     =================================================================== */
  @media (max-width: 1280px) {
    .kpi-row {
      grid-template-columns: repeat(3, 1fr);
    }

    .skel-kpi-row {
      grid-template-columns: repeat(3, 1fr);
    }

    .intel-row {
      grid-template-columns: repeat(2, 1fr);
    }
  }

  @media (max-width: 1023px) {
    .main-grid {
      grid-template-columns: 1fr;
    }

    .skel-main-row {
      grid-template-columns: 1fr;
    }

    .scanner-row {
      grid-template-columns: 1fr;
    }

    .bottom-grid {
      grid-template-columns: 1fr;
    }

    .inst-row {
      grid-template-columns: 1fr;
    }

    .intel-row {
      grid-template-columns: 1fr;
    }

    .tech-row {
      grid-template-columns: 1fr;
    }

    .movers-row {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 768px) {
    .dashboard-page {
      padding: 12px;
      gap: 10px;
    }

    .kpi-row,
    .skel-kpi-row {
      grid-template-columns: repeat(2, 1fr);
    }

    .page-header {
      flex-direction: column;
      align-items: flex-start;
      gap: 8px;
    }

    .hdr-date {
      display: none;
    }

    .sector-grid {
      grid-template-columns: repeat(2, 1fr);
    }

    .skel-main-row {
      grid-template-columns: 1fr;
    }
  }
</style>
