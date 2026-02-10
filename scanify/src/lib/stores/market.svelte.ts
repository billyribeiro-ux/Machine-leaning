// ---------------------------------------------------------------------------
// Market data store – Svelte 5 rune-based reactive state
// ---------------------------------------------------------------------------

/** NYSE TICK, TRIN, and VIX index values. */
export interface MarketInternals {
  /** NYSE TICK – net upticking vs downticking stocks. */
  tick: number;
  /** NYSE TRIN (Arms Index) – breadth-weighted advance/decline. */
  trin: number;
  /** CBOE Volatility Index. */
  vix: number;
  /** Advance/decline ratio. */
  advanceDeclineRatio: number;
  /** Number of advancing issues. */
  advancingIssues: number;
  /** Number of declining issues. */
  decliningIssues: number;
  /** Number of unchanged issues. */
  unchangedIssues: number;
  /** New 52-week highs. */
  newHighs: number;
  /** New 52-week lows. */
  newLows: number;
  /** Total market volume. */
  totalVolume: number;
  /** Up volume. */
  upVolume: number;
  /** Down volume. */
  downVolume: number;
  /** ISO-8601 timestamp of last update. */
  updatedAt: string;
}

export interface SectorData {
  /** Sector name (e.g. "Technology", "Healthcare"). */
  name: string;
  /** Sector ETF symbol (e.g. "XLK"). */
  symbol: string;
  /** Percent change for the session. */
  changePercent: number;
  /** Sector relative strength vs SPY. */
  relativeStrength: number;
  /** Intra-sector breadth (pct of stocks above VWAP). */
  breadth: number;
  /** Volume relative to 20-day average. */
  relativeVolume: number;
}

/** Broad market regime classification. */
export type MarketRegime =
  | 'strong-bull'
  | 'bull'
  | 'neutral'
  | 'bear'
  | 'strong-bear'
  | 'volatile'
  | 'unknown';

/** Intraday session phase. */
export type MarketPhase =
  | 'pre-market'
  | 'opening-auction'
  | 'morning-session'
  | 'midday'
  | 'afternoon-session'
  | 'closing-auction'
  | 'after-hours'
  | 'closed';

// ---------------------------------------------------------------------------
// US equity market schedule helpers
// ---------------------------------------------------------------------------

function getCurrentMarketPhase(): MarketPhase {
  const now = new Date();
  const eastern = new Date(
    now.toLocaleString('en-US', { timeZone: 'America/New_York' })
  );
  const day = eastern.getDay();
  const h = eastern.getHours();
  const m = eastern.getMinutes();
  const time = h * 60 + m;

  // Weekend
  if (day === 0 || day === 6) return 'closed';

  if (time < 240) return 'closed';          // before 4:00 AM
  if (time < 570) return 'pre-market';       // 4:00 AM – 9:29 AM
  if (time < 585) return 'opening-auction';  // 9:30 AM – 9:44 AM
  if (time < 720) return 'morning-session';  // 9:45 AM – 11:59 AM
  if (time < 810) return 'midday';           // 12:00 PM – 1:29 PM
  if (time < 955) return 'afternoon-session';// 1:30 PM – 3:54 PM
  if (time < 960) return 'closing-auction';  // 3:55 PM – 3:59 PM
  if (time < 1200) return 'after-hours';     // 4:00 PM – 7:59 PM
  return 'closed';
}

function isMarketOpenNow(): boolean {
  const phase = getCurrentMarketPhase();
  return (
    phase === 'opening-auction' ||
    phase === 'morning-session' ||
    phase === 'midday' ||
    phase === 'afternoon-session' ||
    phase === 'closing-auction'
  );
}

// ---------------------------------------------------------------------------
// Default internals
// ---------------------------------------------------------------------------

function defaultInternals(): MarketInternals {
  return {
    tick: 0,
    trin: 1.0,
    vix: 0,
    advanceDeclineRatio: 1.0,
    advancingIssues: 0,
    decliningIssues: 0,
    unchangedIssues: 0,
    newHighs: 0,
    newLows: 0,
    totalVolume: 0,
    upVolume: 0,
    downVolume: 0,
    updatedAt: new Date().toISOString(),
  };
}

// ---------------------------------------------------------------------------
// Store factory
// ---------------------------------------------------------------------------

function createMarketStore() {
  // ---- reactive state ----
  let internals = $state<MarketInternals>(defaultInternals());
  let sectors = $state<SectorData[]>([]);
  let regime = $state<MarketRegime>('unknown');
  let lastUpdated = $state<number>(0);

  // ---- derived ----

  let isMarketOpen = $derived(isMarketOpenNow());

  let marketPhase = $derived<MarketPhase>(getCurrentMarketPhase());

  /** Overall market breadth score: -100 (extreme bearish) to +100 (extreme bullish). */
  let overallBreadth = $derived.by(() => {
    const total = internals.advancingIssues + internals.decliningIssues + internals.unchangedIssues;
    if (total === 0) return 0;
    // Weighted composite: AD ratio component + TICK component + TRIN component
    const adComponent =
      ((internals.advancingIssues - internals.decliningIssues) / total) * 50;

    // TICK normalized: extreme values are ~+/-2000 on NYSE
    const tickComponent = Math.max(-50, Math.min(50, (internals.tick / 2000) * 25));

    // TRIN inverted: < 1 is bullish, > 1 is bearish, capped
    const trinClamped = Math.max(0.3, Math.min(3, internals.trin));
    const trinComponent = ((1 - trinClamped) / 2) * 25;

    return Math.round(adComponent + tickComponent + trinComponent);
  });

  /** VIX regime classification. */
  let vixRegime = $derived.by((): 'low' | 'normal' | 'elevated' | 'high' | 'extreme' => {
    const v = internals.vix;
    if (v < 12) return 'low';
    if (v < 18) return 'normal';
    if (v < 25) return 'elevated';
    if (v < 35) return 'high';
    return 'extreme';
  });

  /** Top 3 strongest sectors by relative strength. */
  let leadingSectors = $derived(
    [...sectors].sort((a, b) => b.relativeStrength - a.relativeStrength).slice(0, 3)
  );

  /** Bottom 3 weakest sectors by relative strength. */
  let laggingSectors = $derived(
    [...sectors].sort((a, b) => a.relativeStrength - b.relativeStrength).slice(0, 3)
  );

  /** Average sector breadth across all sectors. */
  let averageSectorBreadth = $derived(
    sectors.length > 0
      ? Math.round(sectors.reduce((sum, s) => sum + s.breadth, 0) / sectors.length)
      : 0
  );

  /** High/Low ratio for quick breadth glance. */
  let highLowRatio = $derived(
    internals.newLows > 0
      ? Math.round((internals.newHighs / internals.newLows) * 100) / 100
      : internals.newHighs > 0
        ? Infinity
        : 1
  );

  // ---- actions ----

  /** Replace market internals wholesale. */
  function updateInternals(update: Partial<MarketInternals>): void {
    internals = {
      ...internals,
      ...update,
      updatedAt: new Date().toISOString(),
    };
    lastUpdated = Date.now();
  }

  /** Replace the full sector data array. */
  function updateSectorData(data: SectorData[]): void {
    sectors = data;
    lastUpdated = Date.now();
  }

  /** Update a single sector entry by symbol. */
  function updateSector(symbol: string, update: Partial<SectorData>): void {
    const idx = sectors.findIndex((s) => s.symbol === symbol);
    if (idx >= 0) {
      sectors[idx] = { ...sectors[idx], ...update };
    }
  }

  /** Set the current market regime classification. */
  function setRegime(newRegime: MarketRegime): void {
    regime = newRegime;
  }

  /** Reset all market data to defaults. */
  function reset(): void {
    internals = defaultInternals();
    sectors = [];
    regime = 'unknown';
    lastUpdated = 0;
  }

  // ---- public API ----
  return {
    // reactive getters
    get internals() {
      return internals;
    },
    get sectors() {
      return sectors;
    },
    get regime() {
      return regime;
    },
    get isMarketOpen() {
      return isMarketOpen;
    },
    get marketPhase() {
      return marketPhase;
    },
    get overallBreadth() {
      return overallBreadth;
    },
    get vixRegime() {
      return vixRegime;
    },
    get leadingSectors() {
      return leadingSectors;
    },
    get laggingSectors() {
      return laggingSectors;
    },
    get averageSectorBreadth() {
      return averageSectorBreadth;
    },
    get highLowRatio() {
      return highLowRatio;
    },
    get lastUpdated() {
      return lastUpdated;
    },

    // actions
    updateInternals,
    updateSectorData,
    updateSector,
    setRegime,
    reset,
  };
}

export const marketStore = createMarketStore();
