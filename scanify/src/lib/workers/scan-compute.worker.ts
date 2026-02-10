// ---------------------------------------------------------------------------
// Scan Compute Worker — off-main-thread technical indicator calculation
// Scanify trading scanner
//
// Receives price / volume data arrays and returns computed indicator values.
// All implementations are pure functions operating on number arrays.
//
// Message-based API:
//   Receives:  { type: 'compute', indicator, data, params }
//   Returns:   { type: 'result', indicator, result }
// ---------------------------------------------------------------------------

/// <reference lib="webworker" />
declare const self: DedicatedWorkerGlobalScope;

// ---------------------------------------------------------------------------
// Technical indicator implementations
// ---------------------------------------------------------------------------

/**
 * Simple Moving Average.
 *
 * For each index i >= period - 1, SMA[i] = mean of data[i - period + 1 .. i].
 * Earlier indices are filled with NaN.
 */
function computeSMA(data: number[], period: number): number[] {
  const length = data.length;
  const result: number[] = new Array<number>(length).fill(NaN);

  if (period <= 0 || period > length) return result;

  // Seed the running sum with the first window.
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += data[i] as number;
  }
  result[period - 1] = sum / period;

  // Slide the window forward.
  for (let i = period; i < length; i++) {
    sum += (data[i] as number) - (data[i - period] as number);
    result[i] = sum / period;
  }

  return result;
}

/**
 * Exponential Moving Average.
 *
 * Uses the standard multiplier k = 2 / (period + 1).
 * The first period values are seeded with the SMA.
 */
function computeEMA(data: number[], period: number): number[] {
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

/**
 * Relative Strength Index (Wilder's smoothed method).
 *
 * Period defaults to 14 in most charting packages.  The first `period`
 * values of the output are NaN; the value at index `period` is the
 * initial RSI seeded with an average of the first `period` gains/losses.
 */
function computeRSI(data: number[], period: number): number[] {
  const length = data.length;
  const result: number[] = new Array<number>(length).fill(NaN);

  if (period <= 0 || length < period + 1) return result;

  // Collect initial gains / losses.
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

/**
 * MACD (Moving Average Convergence Divergence).
 *
 * Returns { macd, signal, histogram } arrays — all the same length as data.
 * Standard defaults: fast=12, slow=26, signal=9.
 */
function computeMACD(
  data: number[],
  fast: number,
  slow: number,
  signal: number,
): { macd: number[]; signal: number[]; histogram: number[] } {
  const length = data.length;

  const emaFast = computeEMA(data, fast);
  const emaSlow = computeEMA(data, slow);

  // MACD line = EMA(fast) - EMA(slow).
  const macdLine: number[] = new Array<number>(length).fill(NaN);
  for (let i = 0; i < length; i++) {
    const f = emaFast[i] as number;
    const s = emaSlow[i] as number;
    if (!isNaN(f) && !isNaN(s)) {
      macdLine[i] = f - s;
    }
  }

  // Find the first non-NaN index in macdLine to seed the signal EMA.
  let firstValid = -1;
  for (let i = 0; i < length; i++) {
    if (!isNaN(macdLine[i] as number)) {
      firstValid = i;
      break;
    }
  }

  const signalLine: number[] = new Array<number>(length).fill(NaN);
  const histogram: number[] = new Array<number>(length).fill(NaN);

  if (firstValid === -1 || firstValid + signal > length) {
    return { macd: macdLine, signal: signalLine, histogram };
  }

  // Seed signal line with SMA of the first `signal` valid MACD values.
  let seedSum = 0;
  for (let i = firstValid; i < firstValid + signal; i++) {
    seedSum += macdLine[i] as number;
  }
  const seedIdx = firstValid + signal - 1;
  signalLine[seedIdx] = seedSum / signal;

  const k = 2 / (signal + 1);

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

/**
 * Bollinger Bands.
 *
 * Returns { upper, middle, lower } arrays, each the same length as data.
 * Middle band = SMA(period).
 * Upper  = middle + stddev * stdDeviation.
 * Lower  = middle - stddev * stdDeviation.
 */
function computeBollingerBands(
  data: number[],
  period: number,
  stddev: number,
): { upper: number[]; middle: number[]; lower: number[] } {
  const length = data.length;
  const middle = computeSMA(data, period);
  const upper: number[] = new Array<number>(length).fill(NaN);
  const lower: number[] = new Array<number>(length).fill(NaN);

  for (let i = period - 1; i < length; i++) {
    const mean = middle[i] as number;
    if (isNaN(mean)) continue;

    // Compute standard deviation over the window.
    let sumSq = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const diff = (data[j] as number) - mean;
      sumSq += diff * diff;
    }
    const sd = Math.sqrt(sumSq / period);

    upper[i] = mean + stddev * sd;
    lower[i] = mean - stddev * sd;
  }

  return { upper, middle, lower };
}

/**
 * Volume Weighted Average Price (VWAP).
 *
 * Cumulative (price * volume) / cumulative volume.
 */
function computeVWAP(prices: number[], volumes: number[]): number[] {
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

// ---------------------------------------------------------------------------
// Message handler
// ---------------------------------------------------------------------------

interface ComputeMessage {
  type: 'compute';
  indicator: string;
  data: number[];
  params: Record<string, number | number[]>;
  requestId?: string;
}

self.onmessage = (event: MessageEvent<ComputeMessage>): void => {
  const msg = event.data;
  if (msg.type !== 'compute') return;

  const { indicator, data, params, requestId } = msg;
  let result: unknown;

  const startTime = performance.now();

  switch (indicator) {
    case 'sma':
      result = computeSMA(data, params['period'] as number);
      break;

    case 'ema':
      result = computeEMA(data, params['period'] as number);
      break;

    case 'rsi':
      result = computeRSI(data, (params['period'] as number) ?? 14);
      break;

    case 'macd':
      result = computeMACD(
        data,
        (params['fast'] as number) ?? 12,
        (params['slow'] as number) ?? 26,
        (params['signal'] as number) ?? 9,
      );
      break;

    case 'bollinger':
      result = computeBollingerBands(
        data,
        (params['period'] as number) ?? 20,
        (params['stddev'] as number) ?? 2,
      );
      break;

    case 'vwap':
      result = computeVWAP(data, params['volumes'] as number[]);
      break;

    default:
      result = null;
      console.warn(`[scan-compute] Unknown indicator: ${indicator}`);
      break;
  }

  const elapsed = performance.now() - startTime;

  self.postMessage({
    type: 'result',
    indicator,
    result,
    requestId: requestId ?? null,
    computeTimeMs: elapsed,
  });
};

export {};
