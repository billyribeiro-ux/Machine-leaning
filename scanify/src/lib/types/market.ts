// ---------------------------------------------------------------------------
// Market data types for the Scanify trading scanner
// ---------------------------------------------------------------------------

/** Current market regime classification. */
export type MarketRegime =
  | 'risk-on'
  | 'risk-off'
  | 'rotation'
  | 'compression'
  | 'expansion';

// ---------------------------------------------------------------------------
// Quote / tick data
// ---------------------------------------------------------------------------

/** Level-1 market data snapshot for a single symbol. */
export interface MarketData {
  /** Ticker symbol. */
  readonly symbol: string;
  /** Last traded price. */
  readonly last: number;
  /** Best bid price. */
  readonly bid: number;
  /** Best ask price. */
  readonly ask: number;
  /** Session open price. */
  readonly open: number;
  /** Session high price. */
  readonly high: number;
  /** Session low price. */
  readonly low: number;
  /** Previous session close price. */
  readonly close: number;
  /** Cumulative session volume. */
  readonly volume: number;
  /** Average daily volume (e.g. 20-day). */
  readonly avgVolume: number;
  /** Volume-weighted average price. */
  readonly vwap: number;
  /** ISO-8601 timestamp of the last update. */
  readonly timestamp: string;
}

// ---------------------------------------------------------------------------
// Candlestick / bar data
// ---------------------------------------------------------------------------

/** A single OHLCV bar used for charting. */
export interface OHLCV {
  /** Unix epoch timestamp in seconds. */
  readonly time: number;
  /** Opening price. */
  readonly open: number;
  /** Highest price. */
  readonly high: number;
  /** Lowest price. */
  readonly low: number;
  /** Closing price. */
  readonly close: number;
  /** Bar volume. */
  readonly volume: number;
}

// ---------------------------------------------------------------------------
// Market internals / breadth
// ---------------------------------------------------------------------------

/** Real-time market-internal breadth indicators. */
export interface MarketInternals {
  /** NYSE TICK index value. */
  readonly tick: number;
  /** TRIN (Arms Index) value. */
  readonly trin: number;
  /** CBOE Volatility Index (VIX). */
  readonly vix: number;
  /** Number of advancing issues. */
  readonly advancers: number;
  /** Number of declining issues. */
  readonly decliners: number;
  /** Number of unchanged issues. */
  readonly unchanged: number;
  /** Number of issues making new 52-week highs. */
  readonly newHighs: number;
  /** Number of issues making new 52-week lows. */
  readonly newLows: number;
  /** Total volume in advancing issues. */
  readonly upVolume: number;
  /** Total volume in declining issues. */
  readonly downVolume: number;
}

// ---------------------------------------------------------------------------
// Sector data
// ---------------------------------------------------------------------------

/** Aggregated data for one market sector. */
export interface SectorData {
  /** Sector name (e.g. "Technology", "Healthcare"). */
  readonly sector: string;
  /** Percentage change for the session. */
  readonly change: number;
  /** Cumulative sector volume. */
  readonly volume: number;
  /** Relative strength vs. the broad market (> 1 = outperforming). */
  readonly relativeStrength: number;
  /** Breadth ratio (advancers / total issues) within the sector. */
  readonly breadth: number;
}
