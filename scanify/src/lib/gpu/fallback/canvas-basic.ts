// ---------------------------------------------------------------------------
// Canvas 2D Fallback Renderer — Scanify trading scanner
//
// Provides simplified 2-D Canvas API visualisations for environments that
// support neither WebGPU nor WebGL2.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Particle data for canvas rendering. */
export interface CanvasParticle {
  readonly x: number;
  readonly y: number;
  readonly radius: number;
  readonly color: string;
  readonly alpha: number;
}

/** Single bar for bar-chart rendering. */
export interface BarData {
  readonly label: string;
  readonly value: number;
  readonly color?: string;
}

/** Configuration for heatmap colour mapping. */
export interface HeatmapConfig {
  readonly colorMode?: 'blue-red' | 'red-green';
}

// ---------------------------------------------------------------------------
// Internal colour helpers
// ---------------------------------------------------------------------------

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function blueRedColor(t: number): string {
  // t in [0,1]: 0 = blue, 0.5 = dark, 1 = red
  let r: number, g: number, b: number;
  if (t < 0.5) {
    const s = t * 2;
    r = Math.round(lerp(59, 22, s));
    g = Math.round(lerp(76, 22, s));
    b = Math.round(lerp(192, 27, s));
  } else {
    const s = (t - 0.5) * 2;
    r = Math.round(lerp(22, 180, s));
    g = Math.round(lerp(22, 4, s));
    b = Math.round(lerp(27, 38, s));
  }
  return `rgb(${r},${g},${b})`;
}

function redGreenColor(t: number): string {
  // t in [0,1]: 0 = red (bearish), 0.5 = dark, 1 = green (bullish)
  let r: number, g: number, b: number;
  if (t < 0.5) {
    const s = t * 2;
    r = Math.round(lerp(204, 31, s));
    g = Math.round(lerp(25, 31, s));
    b = Math.round(lerp(25, 36, s));
  } else {
    const s = (t - 0.5) * 2;
    r = Math.round(lerp(31, 25, s));
    g = Math.round(lerp(31, 179, s));
    b = Math.round(lerp(36, 64, s));
  }
  return `rgb(${r},${g},${b})`;
}

// ---------------------------------------------------------------------------
// Canvas Renderer
// ---------------------------------------------------------------------------

/**
 * CPU-only Canvas 2D renderer providing simplified fallback visualisations.
 *
 * Exposes static-like methods that draw directly to a supplied
 * `CanvasRenderingContext2D`.  No GPU resources are used.
 */
export class CanvasRenderer {
  // -----------------------------------------------------------------------
  // Heatmap
  // -----------------------------------------------------------------------

  /**
   * Draw a heatmap grid onto the canvas context.
   *
   * @param ctx     The 2-D canvas rendering context.
   * @param data    Row-major flat array of scalar values.
   * @param width   Number of columns.
   * @param height  Number of rows.
   * @param config  Optional colour configuration.
   */
  drawHeatmap(
    ctx: CanvasRenderingContext2D,
    data: Float32Array | number[],
    width: number,
    height: number,
    config?: HeatmapConfig,
  ): void {
    const cw = ctx.canvas.width;
    const ch = ctx.canvas.height;
    const cellW = cw / width;
    const cellH = ch / height;
    const colorFn = config?.colorMode === 'blue-red' ? blueRedColor : redGreenColor;

    // Determine data range.
    let min = Infinity;
    let max = -Infinity;
    for (let i = 0; i < data.length; i++) {
      const v = data[i]!;
      if (v < min) min = v;
      if (v > max) max = v;
    }
    if (!Number.isFinite(min)) min = 0;
    if (!Number.isFinite(max)) max = 1;
    const range = max - min || 1;

    // Clear canvas.
    ctx.fillStyle = '#0d0d11';
    ctx.fillRect(0, 0, cw, ch);

    // Draw cells.
    for (let row = 0; row < height; row++) {
      for (let col = 0; col < width; col++) {
        const idx = row * width + col;
        const raw = data[idx] ?? 0;
        const t = Math.max(0, Math.min(1, (raw - min) / range));
        ctx.fillStyle = colorFn(t);
        ctx.fillRect(
          col * cellW + 0.5,
          row * cellH + 0.5,
          cellW - 1,
          cellH - 1,
        );
      }
    }

    // Grid lines.
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.lineWidth = 1;
    for (let col = 1; col < width; col++) {
      const x = Math.round(col * cellW) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, ch);
      ctx.stroke();
    }
    for (let row = 1; row < height; row++) {
      const y = Math.round(row * cellH) + 0.5;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(cw, y);
      ctx.stroke();
    }
  }

  // -----------------------------------------------------------------------
  // Particles
  // -----------------------------------------------------------------------

  /**
   * Draw a set of particles onto the canvas context.
   *
   * @param ctx        The 2-D canvas rendering context.
   * @param particles  Array of particle descriptors.
   */
  drawParticles(
    ctx: CanvasRenderingContext2D,
    particles: readonly CanvasParticle[],
  ): void {
    const cw = ctx.canvas.width;
    const ch = ctx.canvas.height;

    // Clear.
    ctx.fillStyle = '#08080d';
    ctx.fillRect(0, 0, cw, ch);

    for (const p of particles) {
      if (p.alpha <= 0) continue;

      ctx.globalAlpha = Math.max(0, Math.min(1, p.alpha));
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.globalAlpha = 1;
  }

  // -----------------------------------------------------------------------
  // Bar chart
  // -----------------------------------------------------------------------

  /**
   * Draw a simple vertical bar chart.
   *
   * @param ctx   The 2-D canvas rendering context.
   * @param data  Array of bar descriptors.
   */
  drawBars(
    ctx: CanvasRenderingContext2D,
    data: readonly BarData[],
  ): void {
    const cw = ctx.canvas.width;
    const ch = ctx.canvas.height;
    const padding = 40;
    const labelHeight = 20;
    const chartHeight = ch - padding - labelHeight;
    const chartWidth = cw - padding * 2;

    // Clear.
    ctx.fillStyle = '#0d0d11';
    ctx.fillRect(0, 0, cw, ch);

    if (data.length === 0) return;

    // Determine max value.
    let maxVal = 0;
    for (const d of data) {
      const abs = Math.abs(d.value);
      if (abs > maxVal) maxVal = abs;
    }
    if (maxVal === 0) maxVal = 1;

    const barWidth = chartWidth / data.length;
    const gap = Math.max(1, barWidth * 0.15);

    for (let i = 0; i < data.length; i++) {
      const d = data[i]!;
      const barH = (Math.abs(d.value) / maxVal) * chartHeight;
      const x = padding + i * barWidth + gap / 2;
      const w = barWidth - gap;
      const y = padding + chartHeight - barH;

      // Bar fill.
      ctx.fillStyle = d.color ?? (d.value >= 0 ? '#1a8f44' : '#b31630');
      ctx.fillRect(x, y, w, barH);

      // Label.
      ctx.fillStyle = '#888';
      ctx.font = '10px monospace';
      ctx.textAlign = 'center';
      ctx.fillText(
        d.label.substring(0, 6),
        x + w / 2,
        ch - 4,
      );

      // Value on top.
      ctx.fillStyle = '#ccc';
      ctx.font = '9px monospace';
      ctx.fillText(
        d.value.toFixed(1),
        x + w / 2,
        y - 4,
      );
    }
  }

  // -----------------------------------------------------------------------
  // Depth chart (simplified stacked area)
  // -----------------------------------------------------------------------

  /**
   * Draw a simplified order book depth chart.
   *
   * @param ctx   The 2-D canvas rendering context.
   * @param bids  Cumulative bid sizes keyed by price (highest first).
   * @param asks  Cumulative ask sizes keyed by price (lowest first).
   */
  drawDepth(
    ctx: CanvasRenderingContext2D,
    bids: readonly { price: number; cumSize: number }[],
    asks: readonly { price: number; cumSize: number }[],
  ): void {
    const cw = ctx.canvas.width;
    const ch = ctx.canvas.height;

    // Clear.
    ctx.fillStyle = '#0a0a10';
    ctx.fillRect(0, 0, cw, ch);

    if (bids.length === 0 && asks.length === 0) return;

    // Determine ranges.
    const allPrices: number[] = [];
    for (const b of bids) allPrices.push(b.price);
    for (const a of asks) allPrices.push(a.price);
    const minPrice = Math.min(...allPrices);
    const maxPrice = Math.max(...allPrices);
    const priceRange = maxPrice - minPrice || 1;

    let maxDepth = 0;
    for (const b of bids) { if (b.cumSize > maxDepth) maxDepth = b.cumSize; }
    for (const a of asks) { if (a.cumSize > maxDepth) maxDepth = a.cumSize; }
    if (maxDepth === 0) maxDepth = 1;

    const toX = (price: number): number => ((price - minPrice) / priceRange) * cw;
    const toY = (depth: number): number => ch - (depth / maxDepth) * (ch * 0.85);

    // Draw bid area (green).
    if (bids.length > 0) {
      ctx.fillStyle = 'rgba(26, 143, 68, 0.25)';
      ctx.strokeStyle = '#1a8f44';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(toX(bids[0]!.price), ch);
      for (const b of bids) {
        ctx.lineTo(toX(b.price), toY(b.cumSize));
      }
      ctx.lineTo(toX(bids[bids.length - 1]!.price), ch);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }

    // Draw ask area (red).
    if (asks.length > 0) {
      ctx.fillStyle = 'rgba(179, 22, 48, 0.25)';
      ctx.strokeStyle = '#b31630';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(toX(asks[0]!.price), ch);
      for (const a of asks) {
        ctx.lineTo(toX(a.price), toY(a.cumSize));
      }
      ctx.lineTo(toX(asks[asks.length - 1]!.price), ch);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }

    // Mid-price line.
    const midPrice =
      bids.length > 0 && asks.length > 0
        ? (bids[0]!.price + asks[0]!.price) / 2
        : (minPrice + maxPrice) / 2;
    const midX = toX(midPrice);
    ctx.strokeStyle = 'rgba(255,255,255,0.3)';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(midX, 0);
    ctx.lineTo(midX, ch);
    ctx.stroke();
    ctx.setLineDash([]);
  }
}
