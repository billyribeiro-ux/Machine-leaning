// ---------------------------------------------------------------------------
// Options data types for the Scanify trading scanner
// ---------------------------------------------------------------------------

/** Option contract type. */
export type OptionType = 'call' | 'put';

/** Trade side for an options flow entry. */
export type OptionSide = 'buy' | 'sell';

/** Sentiment classification derived from options flow. */
export type OptionSentiment = 'bullish' | 'bearish' | 'neutral';

// ---------------------------------------------------------------------------
// Options chain
// ---------------------------------------------------------------------------

/** Full options chain for a single underlying symbol. */
export interface OptionsChain {
  /** Underlying ticker symbol. */
  readonly symbol: string;
  /** Available expiration dates (ISO-8601 date strings, e.g. "2026-03-21"). */
  readonly expirations: readonly string[];
  /** Available strike prices in ascending order. */
  readonly strikes: readonly number[];
  /**
   * Call contracts organised as a 2-D grid:
   *   calls[expirationIndex][strikeIndex]
   */
  readonly calls: readonly (readonly OptionContract[])[];
  /**
   * Put contracts organised as a 2-D grid:
   *   puts[expirationIndex][strikeIndex]
   */
  readonly puts: readonly (readonly OptionContract[])[];
}

// ---------------------------------------------------------------------------
// Option contract
// ---------------------------------------------------------------------------

/** A single option contract with greeks. */
export interface OptionContract {
  /** OCC-style option symbol. */
  readonly symbol: string;
  /** Strike price. */
  readonly strike: number;
  /** Expiration date (ISO-8601 date string). */
  readonly expiration: string;
  /** Call or put. */
  readonly type: OptionType;
  /** Best bid price. */
  readonly bid: number;
  /** Best ask price. */
  readonly ask: number;
  /** Last traded price. */
  readonly last: number;
  /** Session volume. */
  readonly volume: number;
  /** Current open interest. */
  readonly openInterest: number;
  /** Implied volatility (decimal, e.g. 0.35 = 35 %). */
  readonly iv: number;
  /** Delta. */
  readonly delta: number;
  /** Gamma. */
  readonly gamma: number;
  /** Theta (daily decay). */
  readonly theta: number;
  /** Vega. */
  readonly vega: number;
  /** Rho. */
  readonly rho: number;
  /** Whether the contract is currently in the money. */
  readonly inTheMoney: boolean;
}

// ---------------------------------------------------------------------------
// Options flow
// ---------------------------------------------------------------------------

/** A single options flow (dark-pool / exchange) transaction. */
export interface OptionsFlow {
  /** Unique flow entry identifier. */
  readonly id: string;
  /** Underlying ticker symbol. */
  readonly symbol: string;
  /** ISO-8601 timestamp of the trade. */
  readonly timestamp: string;
  /** Call or put. */
  readonly type: OptionType;
  /** Strike price. */
  readonly strike: number;
  /** Expiration date (ISO-8601 date string). */
  readonly expiration: string;
  /** Buy or sell. */
  readonly side: OptionSide;
  /** Number of contracts traded. */
  readonly size: number;
  /** Per-contract price. */
  readonly price: number;
  /** Total premium (size * price * 100). */
  readonly premium: number;
  /** Open interest at the time of the trade. */
  readonly openInterest: number;
  /** Whether the trade size is flagged as unusual activity. */
  readonly isUnusual: boolean;
  /** Whether the trade was executed as a sweep across exchanges. */
  readonly isSweep: boolean;
  /** Inferred sentiment based on trade characteristics. */
  readonly sentiment: OptionSentiment;
}

// ---------------------------------------------------------------------------
// GEX (Gamma Exposure)
// ---------------------------------------------------------------------------

/** Gamma-exposure data for a single strike level. */
export interface GEXData {
  /** Strike price. */
  readonly strike: number;
  /** Net dealer gamma exposure at this strike (in shares). */
  readonly gammaExposure: number;
  /** Gamma contribution from call open interest. */
  readonly callGamma: number;
  /** Gamma contribution from put open interest. */
  readonly putGamma: number;
  /** Net gamma (callGamma - putGamma). */
  readonly netGamma: number;
}
