// ---------------------------------------------------------------------------
// Technical Indicator Compute Shaders — Scanify trading scanner
//
// GPU-parallel computation of common technical indicators:
//   - Simple Moving Average  (SMA)
//   - Exponential Moving Average (EMA)
//
// Each invocation computes the indicator value for a single data point,
// enabling massive parallelism across the price series.
//
// Input:
//   params — indicator parameters (period, alpha, data length, mode)
//   prices — array of f32 close prices, chronological order
//
// Output:
//   output — array of f32 indicator values, same length as prices
// ---------------------------------------------------------------------------

struct IndicatorParams {
  data_length : u32,   // number of price data points
  period      : u32,   // indicator lookback period
  alpha       : f32,   // EMA smoothing factor (2 / (period + 1))
  mode        : u32,   // 0 = SMA, 1 = EMA
};

@group(0) @binding(0) var<uniform>            params : IndicatorParams;
@group(0) @binding(1) var<storage, read>      prices : array<f32>;
@group(0) @binding(2) var<storage, read_write> output : array<f32>;

// ---------------------------------------------------------------------------
// SMA compute shader
//
// Each thread computes SMA for one index by averaging the preceding
// `period` values.  Indices before the first full window output 0.
//
// Dispatch: ceil(data_length / 256) workgroups.
// ---------------------------------------------------------------------------

@compute @workgroup_size(256)
fn cs_sma(@builtin(global_invocation_id) gid : vec3<u32>) {
  let idx = gid.x;
  if (idx >= params.data_length) { return; }

  let period = params.period;

  // Not enough data points for a full window yet.
  if (idx < period - 1u) {
    output[idx] = 0.0;
    return;
  }

  // Sum the last `period` prices.
  var sum = 0.0;
  let start = idx - period + 1u;
  for (var k = start; k <= idx; k = k + 1u) {
    sum = sum + prices[k];
  }

  output[idx] = sum / f32(period);
}

// ---------------------------------------------------------------------------
// EMA compute shader
//
// EMA is inherently sequential (each value depends on the previous).
// To parallelise, we use a two-pass approach:
//
//   Pass 1 (cs_ema_seed):  Compute the initial SMA seed for the first
//                          `period` values.  Run with 1 workgroup of 1 thread.
//
//   Pass 2 (cs_ema_scan):  Sequential scan from index `period` onwards.
//                          Run with 1 workgroup of 1 thread.
//                          (For very long series a parallel prefix-sum
//                          variant could be used, but the sequential scan
//                          is simpler and sufficient for typical lengths.)
//
// For a fully parallel EMA on very large datasets, a work-efficient
// parallel scan could be implemented in a future iteration.
// ---------------------------------------------------------------------------

@compute @workgroup_size(1)
fn cs_ema_seed() {
  let period = params.period;
  let len    = params.data_length;

  if (len == 0u || period == 0u) { return; }

  // Zero-fill everything first.
  for (var i = 0u; i < len; i = i + 1u) {
    output[i] = 0.0;
  }

  // Compute the initial SMA as the seed value.
  var sum = 0.0;
  let seed_end = min(period, len);
  for (var k = 0u; k < seed_end; k = k + 1u) {
    sum = sum + prices[k];
  }
  let seed = sum / f32(seed_end);
  output[seed_end - 1u] = seed;
}

@compute @workgroup_size(1)
fn cs_ema_scan() {
  let period = params.period;
  let len    = params.data_length;
  let alpha  = params.alpha;

  if (len <= period || period == 0u) { return; }

  // The seed value was written by cs_ema_seed.
  var prev = output[period - 1u];

  // Sequential scan.
  for (var i = period; i < len; i = i + 1u) {
    let price = prices[i];
    let ema = alpha * price + (1.0 - alpha) * prev;
    output[i] = ema;
    prev = ema;
  }
}

// ---------------------------------------------------------------------------
// RSI helper — compute gains and losses
//
// Computes parallel per-bar gain/loss and then a sequential average.
// This shader writes to two regions of the output buffer:
//   output[0..N-1]       = RSI values
//
// We use a sequential approach here for the smoothed averages.
//
// Dispatch: 1 workgroup of 1 thread (sequential due to RSI's nature).
// ---------------------------------------------------------------------------

@compute @workgroup_size(1)
fn cs_rsi() {
  let len    = params.data_length;
  let period = params.period;

  if (len < period + 1u) { return; }

  // Compute initial average gain / loss over the first `period` bars.
  var avg_gain = 0.0;
  var avg_loss = 0.0;
  for (var i = 1u; i <= period; i = i + 1u) {
    let change = prices[i] - prices[i - 1u];
    if (change > 0.0) {
      avg_gain = avg_gain + change;
    } else {
      avg_loss = avg_loss - change; // make positive
    }
  }
  avg_gain = avg_gain / f32(period);
  avg_loss = avg_loss / f32(period);

  // Fill output[0..period-1] with 0 (insufficient data).
  for (var i = 0u; i <= period; i = i + 1u) {
    output[i] = 0.0;
  }

  // First RSI value.
  if (avg_loss == 0.0) {
    output[period] = 100.0;
  } else {
    let rs = avg_gain / avg_loss;
    output[period] = 100.0 - 100.0 / (1.0 + rs);
  }

  // Smoothed RSI for remaining bars.
  for (var i = period + 1u; i < len; i = i + 1u) {
    let change = prices[i] - prices[i - 1u];
    var gain = 0.0;
    var loss = 0.0;
    if (change > 0.0) { gain = change; }
    else { loss = -change; }

    avg_gain = (avg_gain * f32(period - 1u) + gain) / f32(period);
    avg_loss = (avg_loss * f32(period - 1u) + loss) / f32(period);

    if (avg_loss == 0.0) {
      output[i] = 100.0;
    } else {
      let rs = avg_gain / avg_loss;
      output[i] = 100.0 - 100.0 / (1.0 + rs);
    }
  }
}
