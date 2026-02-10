// ---------------------------------------------------------------------------
// Technical indicator implementations — WASM / JS fallback layer
//
// Each exported function checks if the WASM module is loaded.  When it is,
// the WASM implementation is used for maximum performance; otherwise, the
// pure-JavaScript fallback runs.  All algorithms are fully implemented and
// produce identical results regardless of the execution path.
// ---------------------------------------------------------------------------

import { isReady, getModule } from './scanify-core';

// ---------------------------------------------------------------------------
// Internal WASM bridge helpers
// ---------------------------------------------------------------------------

/** Safely call a WASM export by name, returning `undefined` on failure. */
function callWasm<T>(fn: string, ...args: unknown[]): T | undefined {
  if (!isReady()) return undefined;
  const mod = getModule() as Record<string, (...a: unknown[]) => T> | null;
  if (!mod || typeof mod[fn] !== 'function') return undefined;
  try {
    return mod[fn](...args);
  } catch {
    return undefined;
  }
}

// ---------------------------------------------------------------------------
// SMA — Simple Moving Average
// ---------------------------------------------------------------------------

/**
 * Compute the Simple Moving Average.
 *
 * For each index i >= period - 1, SMA[i] = mean of data[i - period + 1 .. i].
 * Earlier indices are filled with NaN.
 *
 * @param data    Array of numeric values (typically close prices).
 * @param period  Window length (must be >= 1).
 */
export function computeSMA(data: number[], period: number): number[] {
  // Try WASM first.
  const wasmResult = callWasm<number[]>('compute_sma', data, period);
  if (wasmResult !== undefined) return wasmResult;

  // JS fallback.
  const length = data.length;
  const result: number[] = new Array<number>(length).fill(NaN);

  if (period <= 0 || period > length) return result;

  // Seed with the first window.
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += data[i] as number;
  }
  result[period - 1] = sum / period;

  // Slide the window.
  for (let i = period; i < length; i++) {
    sum += (data[i] as number) - (data[i - period] as number);
    result[i] = sum / period;
  }

  return result;
}

// ---------------------------------------------------------------------------
// EMA — Exponential Moving Average
// ---------------------------------------------------------------------------

/**
 * Compute the Exponential Moving Average.
 *
 * Uses the standard multiplier k = 2 / (period + 1).
 * The first `period` values are seeded with the SMA.
 *
 * @param data    Array of numeric values.
 * @param period  Smoothing window (must be >= 1).
 */
export function computeEMA(data: number[], period: number): number[] {
  const wasmResult = callWasm<number[]>('compute_ema', data, period);
  if (wasmResult !== undefined) return wasmResult;

  const length = data.length;
  const result: number[] = new Array<number>(length).fill(NaN);

  if (period <= 0 || period > length) return result;

  // Seed: SMA of the first `period` values.
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += data[i] as number;
  }
  const sma = sum / period;
  result[period - 1] = sma;

  const k = 2 / (period + 1);

  for (let i = period; i < length; i++) {
    const prev = result[i - 1] as number;
    result[i] = (data[i] as number) * k + prev * (1 - k);
  }

  return result;
}

// ---------------------------------------------------------------------------
// RSI — Relative Strength Index (Wilder's smoothed)
// ---------------------------------------------------------------------------

/**
 * Compute the Relative Strength Index using Wilder's smoothing method.
 *
 * The first `period` values of the output are NaN.  The value at index
 * `period` is seeded from the average of the first `period` gains/losses.
 *
 * @param data    Array of numeric values (typically close prices).
 * @param period  Look-back period (standard: 14).
 */
export function computeRSI(data: number[], period: number = 14): number[] {
  const wasmResult = callWasm<number[]>('compute_rsi', data, period);
  if (wasmResult !== undefined) return wasmResult;

  const length = data.length;
  const result: number[] = new Array<number>(length).fill(NaN);

  if (period <= 0 || length < period + 1) return result;

  // Collect initial gains / losses over the first `period` changes.
  let avgGain = 0;
  let avgLoss = 0;

  for (let i = 1; i <= period; i++) {
    const change = (data[i] as number) - (data[i - 1] as number);
    if (change >= 0) {
      avgGain += change;
    } else {
      avgLoss += Math.abs(change);
    }
  }

  avgGain /= period;
  avgLoss /= period;

  // First RSI value.
  if (avgLoss === 0) {
    result[period] = 100;
  } else {
    const rs = avgGain / avgLoss;
    result[period] = 100 - 100 / (1 + rs);
  }

  // Wilder's smoothing for the remaining values.
  for (let i = period + 1; i < length; i++) {
    const change = (data[i] as number) - (data[i - 1] as number);
    const gain = change >= 0 ? change : 0;
    const loss = change < 0 ? Math.abs(change) : 0;

    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;

    if (avgLoss === 0) {
      result[i] = 100;
    } else {
      const rs = avgGain / avgLoss;
      result[i] = 100 - 100 / (1 + rs);
    }
  }

  return result;
}

// ---------------------------------------------------------------------------
// MACD — Moving Average Convergence Divergence
// ---------------------------------------------------------------------------

export interface MACDResult {
  readonly macd: number[];
  readonly signal: number[];
  readonly histogram: number[];
}

/**
 * Compute MACD, signal line, and histogram.
 *
 * Standard defaults: fast = 12, slow = 26, signal = 9.
 *
 * @param data          Array of numeric values (typically close prices).
 * @param fastPeriod    Fast EMA period.
 * @param slowPeriod    Slow EMA period.
 * @param signalPeriod  Signal EMA period.
 */
export function computeMACD(
  data: number[],
  fastPeriod: number = 12,
  slowPeriod: number = 26,
  signalPeriod: number = 9,
): MACDResult {
  const wasmResult = callWasm<MACDResult>(
    'compute_macd',
    data,
    fastPeriod,
    slowPeriod,
    signalPeriod,
  );
  if (wasmResult !== undefined) return wasmResult;

  const length = data.length;
  const emaFast = computeEMA(data, fastPeriod);
  const emaSlow = computeEMA(data, slowPeriod);

  // MACD line = EMA(fast) - EMA(slow).
  const macdLine: number[] = new Array<number>(length).fill(NaN);
  for (let i = 0; i < length; i++) {
    const f = emaFast[i] as number;
    const s = emaSlow[i] as number;
    if (!isNaN(f) && !isNaN(s)) {
      macdLine[i] = f - s;
    }
  }

  // Find the first valid MACD value to seed the signal EMA.
  let firstValid = -1;
  for (let i = 0; i < length; i++) {
    if (!isNaN(macdLine[i] as number)) {
      firstValid = i;
      break;
    }
  }

  const signalLine: number[] = new Array<number>(length).fill(NaN);
  const histogram: number[] = new Array<number>(length).fill(NaN);

  if (firstValid === -1 || firstValid + signalPeriod > length) {
    return { macd: macdLine, signal: signalLine, histogram };
  }

  // Seed signal line with SMA of the first `signalPeriod` valid MACD values.
  let seedSum = 0;
  for (let i = firstValid; i < firstValid + signalPeriod; i++) {
    seedSum += macdLine[i] as number;
  }
  const seedIdx = firstValid + signalPeriod - 1;
  signalLine[seedIdx] = seedSum / signalPeriod;

  const k = 2 / (signalPeriod + 1);

  for (let i = seedIdx + 1; i < length; i++) {
    const m = macdLine[i] as number;
    if (isNaN(m)) continue;
    const prev = signalLine[i - 1] as number;
    signalLine[i] = m * k + prev * (1 - k);
  }

  // Histogram = MACD - signal.
  for (let i = 0; i < length; i++) {
    const m = macdLine[i] as number;
    const s = signalLine[i] as number;
    if (!isNaN(m) && !isNaN(s)) {
      histogram[i] = m - s;
    }
  }

  return { macd: macdLine, signal: signalLine, histogram };
}

// ---------------------------------------------------------------------------
// Bollinger Bands
// ---------------------------------------------------------------------------

export interface BollingerResult {
  readonly upper: number[];
  readonly middle: number[];
  readonly lower: number[];
}

/**
 * Compute Bollinger Bands.
 *
 * Middle band = SMA(period).
 * Upper  = middle + stdDevMultiplier * population stddev.
 * Lower  = middle - stdDevMultiplier * population stddev.
 *
 * @param data              Array of numeric values.
 * @param period            SMA window (standard: 20).
 * @param stdDevMultiplier  Standard deviation multiplier (standard: 2).
 */
export function computeBollingerBands(
  data: number[],
  period: number = 20,
  stdDevMultiplier: number = 2,
): BollingerResult {
  const wasmResult = callWasm<BollingerResult>(
    'compute_bollinger',
    data,
    period,
    stdDevMultiplier,
  );
  if (wasmResult !== undefined) return wasmResult;

  const length = data.length;
  const middle = computeSMA(data, period);
  const upper: number[] = new Array<number>(length).fill(NaN);
  const lower: number[] = new Array<number>(length).fill(NaN);

  for (let i = period - 1; i < length; i++) {
    const mean = middle[i] as number;
    if (isNaN(mean)) continue;

    // Population standard deviation over the window.
    let sumSq = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const diff = (data[j] as number) - mean;
      sumSq += diff * diff;
    }
    const sd = Math.sqrt(sumSq / period);

    upper[i] = mean + stdDevMultiplier * sd;
    lower[i] = mean - stdDevMultiplier * sd;
  }

  return { upper, middle, lower };
}

// ---------------------------------------------------------------------------
// VWAP — Volume Weighted Average Price
// ---------------------------------------------------------------------------

/**
 * Compute the cumulative Volume Weighted Average Price.
 *
 * VWAP[i] = sum(price[0..i] * volume[0..i]) / sum(volume[0..i]).
 * Typically reset daily by the caller.
 *
 * @param prices   Array of price values (e.g. typical price = (H+L+C)/3).
 * @param volumes  Corresponding volume values.
 */
export function computeVWAP(prices: number[], volumes: number[]): number[] {
  const wasmResult = callWasm<number[]>('compute_vwap', prices, volumes);
  if (wasmResult !== undefined) return wasmResult;

  const length = Math.min(prices.length, volumes.length);
  const result: number[] = new Array<number>(length).fill(NaN);

  let cumulativePV = 0;
  let cumulativeV = 0;

  for (let i = 0; i < length; i++) {
    const price = prices[i] as number;
    const volume = volumes[i] as number;

    cumulativePV += price * volume;
    cumulativeV += volume;

    result[i] = cumulativeV === 0 ? NaN : cumulativePV / cumulativeV;
  }

  return result;
}
