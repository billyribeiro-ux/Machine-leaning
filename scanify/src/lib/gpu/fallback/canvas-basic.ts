// ---------------------------------------------------------------------------
// Canvas 2D fallback renderer
//
// Provides simple but functional 2D drawing primitives for heatmaps,
// bar charts, and line charts when neither WebGPU nor WebGL is available.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Point {
  readonly x: number;
  readonly y: number;
}

/**
 * A function that maps a normalised value in [0, 1] to a CSS colour string.
 */
export type ColorScale = (t: number) => string;

// ---------------------------------------------------------------------------
// Built-in colour scales
// ---------------------------------------------------------------------------

/**
 * Five-stop heat colour scale: deep blue -> cyan -> green -> yellow -> red.
 * Input `t` should be in [0, 1].
 */
export function defaultHeatScale(t: number): string {
  const clamped = Math.max(0, Math.min(1, t));

  // RGB stops matching the WebGL heatmap ramp.
  const stops: readonly [number, number, number][] = [
    [13, 13, 89],    // deep blue
    [0, 153, 191],   // cyan
    [26, 191, 64],   // green
    [242, 217, 26],  // yellow
    [230, 38, 26],   // red
  ];

  const segment = clamped * (stops.length - 1);
  const idx = Math.min(Math.floor(segment), stops.length - 2);
  const frac = segment - idx;

  const a = stops[idx] as [number, number, number];
  const b = stops[idx + 1] as [number, number, number];

  const r = Math.round(a[0] + (b[0] - a[0]) * frac);
  const g = Math.round(a[1] + (b[1] - a[1]) * frac);
  const bl = Math.round(a[2] + (b[2] - a[2]) * frac);

  return `rgb(${r},${g},${bl})`;
}

/**
 * Diverging red-grey-green scale centred at 0.5.
 * Useful for price-change heatmaps.
 */
export function divergingScale(t: number): string {
  const clamped = Math.max(0, Math.min(1, t));

  if (clamped < 0.5) {
    // Red side: t=0 is full red, t=0.5 is dark grey.
    const intensity = 1 - clamped * 2;
    const r = Math.round(180 + 60 * intensity);
    const g = Math.round(60 * (1 - intensity));
    const b = Math.round(60 * (1 - intensity));
    return `rgb(${r},${g},${b})`;
  }

  // Green side: t=0.5 is dark grey, t=1 is full green.
  const intensity = (clamped - 0.5) * 2;
  const r = Math.round(60 * (1 - intensity));
  const g = Math.round(180 + 60 * intensity);
  const b = Math.round(60 * (1 - intensity));
  return `rgb(${r},${g},${b})`;
}

// ---------------------------------------------------------------------------
// Heatmap
// ---------------------------------------------------------------------------

/**
 * Draw a heatmap grid onto a Canvas 2D context.
 *
 * @param ctx         The 2D rendering context.
 * @param data        A 2D array (rows x cols) or flat array of length w * h.
 * @param w           Number of columns.
 * @param h           Number of rows.
 * @param colorScale  A function mapping [0, 1] to a CSS colour string.
 * @param minValue    Data value that maps to t = 0 (default: auto-detect).
 * @param maxValue    Data value that maps to t = 1 (default: auto-detect).
 */
export function drawHeatmap(
  ctx: CanvasRenderingContext2D,
  data: number[] | number[][],
  w: number,
  h: number,
  colorScale: ColorScale = defaultHeatScale,
  minValue?: number,
  maxValue?: number,
): void {
  // Flatten if 2D.
  const flat: number[] = Array.isArray(data[0])
    ? (data as number[][]).flat()
    : (data as number[]);

  // Auto-detect range if not provided.
  let lo = minValue ?? Infinity;
  let hi = maxValue ?? -Infinity;

  if (minValue === undefined || maxValue === undefined) {
    for (const v of flat) {
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
  }

  const range = hi - lo || 1;
  const canvasW = ctx.canvas.width;
  const canvasH = ctx.canvas.height;
  const cellW = canvasW / w;
  const cellH = canvasH / h;

  // Clear canvas.
  ctx.fillStyle = '#0d0d12';
  ctx.fillRect(0, 0, canvasW, canvasH);

  for (let row = 0; row < h; row++) {
    for (let col = 0; col < w; col++) {
      const idx = row * w + col;
      const value = flat[idx] ?? 0;
      const t = Math.max(0, Math.min(1, (value - lo) / range));

      ctx.fillStyle = colorScale(t);
      ctx.fillRect(
        Math.floor(col * cellW),
        Math.floor(row * cellH),
        Math.ceil(cellW),
        Math.ceil(cellH),
      );
    }
  }
}

// ---------------------------------------------------------------------------
// Bar chart
// ---------------------------------------------------------------------------

export interface BarChartOptions {
  /** Bar colour (CSS string). Default: 'rgba(59, 130, 246, 0.8)'. */
  readonly color?: string;
  /** Negative-bar colour. Default: 'rgba(239, 68, 68, 0.8)'. */
  readonly negativeColor?: string;
  /** Gap between bars in pixels. Default: 1. */
  readonly gap?: number;
  /** Whether to draw a zero baseline. Default: true. */
  readonly baseline?: boolean;
  /** Whether to draw value labels above bars. Default: false. */
  readonly labels?: boolean;
}

/**
 * Draw a simple vertical bar chart.
 *
 * @param ctx   The 2D rendering context.
 * @param data  An array of numeric values (one per bar).
 * @param w     Canvas width to use.
 * @param h     Canvas height to use.
 * @param opts  Optional styling configuration.
 */
export function drawBars(
  ctx: CanvasRenderingContext2D,
  data: number[],
  w: number,
  h: number,
  opts?: BarChartOptions,
): void {
  if (data.length === 0) return;

  const color = opts?.color ?? 'rgba(59, 130, 246, 0.8)';
  const negativeColor = opts?.negativeColor ?? 'rgba(239, 68, 68, 0.8)';
  const gap = opts?.gap ?? 1;
  const drawBaseline = opts?.baseline ?? true;
  const drawLabels = opts?.labels ?? false;

  let maxVal = -Infinity;
  let minVal = Infinity;
  for (const v of data) {
    if (v > maxVal) maxVal = v;
    if (v < minVal) minVal = v;
  }

  // Determine the zero line position.
  const hasNegative = minVal < 0;
  const rangeTop = Math.max(maxVal, 0);
  const rangeBottom = Math.min(minVal, 0);
  const totalRange = rangeTop - rangeBottom || 1;

  const barWidth = Math.max(1, (w - gap * (data.length - 1)) / data.length);
  const zeroY = (rangeTop / totalRange) * h;

  // Clear area.
  ctx.fillStyle = '#0d0d12';
  ctx.fillRect(0, 0, w, h);

  // Draw baseline.
  if (drawBaseline && hasNegative) {
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, zeroY);
    ctx.lineTo(w, zeroY);
    ctx.stroke();
  }

  // Draw bars.
  for (let i = 0; i < data.length; i++) {
    const value = data[i] as number;
    const barHeight = (Math.abs(value) / totalRange) * h;
    const x = i * (barWidth + gap);

    ctx.fillStyle = value >= 0 ? color : negativeColor;

    if (value >= 0) {
      ctx.fillRect(x, zeroY - barHeight, barWidth, barHeight);
    } else {
      ctx.fillRect(x, zeroY, barWidth, barHeight);
    }

    // Optional value labels.
    if (drawLabels) {
      ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
      ctx.font = '9px monospace';
      ctx.textAlign = 'center';
      const labelY = value >= 0 ? zeroY - barHeight - 4 : zeroY + barHeight + 10;
      ctx.fillText(value.toFixed(1), x + barWidth / 2, labelY);
    }
  }
}

// ---------------------------------------------------------------------------
// Line chart
// ---------------------------------------------------------------------------

export interface LineOptions {
  /** Line width in pixels. Default: 2. */
  readonly width?: number;
  /** Whether to draw a filled area under the line. Default: false. */
  readonly fill?: boolean;
  /** Fill colour (used when `fill` is true). Default: translucent version of `color`. */
  readonly fillColor?: string;
  /** Draw circles at each data point. Default: false. */
  readonly dots?: boolean;
  /** Radius of data-point circles. Default: 3. */
  readonly dotRadius?: number;
}

/**
 * Draw a line through an array of points.
 *
 * @param ctx     The 2D rendering context.
 * @param points  Array of {x, y} coordinates in pixel space.
 * @param color   CSS colour string for the stroke.
 * @param opts    Optional styling configuration.
 */
export function drawLine(
  ctx: CanvasRenderingContext2D,
  points: readonly Point[],
  color: string = 'rgba(59, 130, 246, 1)',
  opts?: LineOptions,
): void {
  if (points.length < 2) return;

  const lineWidth = opts?.width ?? 2;
  const doFill = opts?.fill ?? false;
  const drawDots = opts?.dots ?? false;
  const dotRadius = opts?.dotRadius ?? 3;
  const first = points[0] as Point;
  const last = points[points.length - 1] as Point;

  // Filled area under the line.
  if (doFill) {
    const fillColor = opts?.fillColor ?? color.replace(/[\d.]+\)$/, '0.15)');
    ctx.beginPath();
    ctx.moveTo(first.x, ctx.canvas.height);
    for (const pt of points) {
      ctx.lineTo(pt.x, pt.y);
    }
    ctx.lineTo(last.x, ctx.canvas.height);
    ctx.closePath();
    ctx.fillStyle = fillColor;
    ctx.fill();
  }

  // Line stroke.
  ctx.beginPath();
  ctx.moveTo(first.x, first.y);
  for (let i = 1; i < points.length; i++) {
    const pt = points[i] as Point;
    ctx.lineTo(pt.x, pt.y);
  }
  ctx.strokeStyle = color;
  ctx.lineWidth = lineWidth;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.stroke();

  // Optional data-point circles.
  if (drawDots) {
    ctx.fillStyle = color;
    for (const pt of points) {
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, dotRadius, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

// ---------------------------------------------------------------------------
// Utility: convert data array to pixel-space points
// ---------------------------------------------------------------------------

/**
 * Convert a simple array of numeric values into pixel-space points,
 * evenly distributed across the given width and auto-scaled to height.
 *
 * @param data    Numeric values.
 * @param width   Canvas width in pixels.
 * @param height  Canvas height in pixels.
 * @param padding Pixel padding from top and bottom.
 */
export function dataToPoints(
  data: number[],
  width: number,
  height: number,
  padding: number = 4,
): Point[] {
  if (data.length === 0) return [];
  if (data.length === 1) return [{ x: width / 2, y: height / 2 }];

  let min = Infinity;
  let max = -Infinity;
  for (const v of data) {
    if (v < min) min = v;
    if (v > max) max = v;
  }
  const range = max - min || 1;
  const usableHeight = height - padding * 2;

  const points: Point[] = [];
  const step = width / (data.length - 1);

  for (let i = 0; i < data.length; i++) {
    const value = data[i] as number;
    const x = i * step;
    // Invert Y so higher values are at the top.
    const y = padding + usableHeight * (1 - (value - min) / range);
    points.push({ x, y });
  }

  return points;
}
