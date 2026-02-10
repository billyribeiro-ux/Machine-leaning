// ---------------------------------------------------------------------------
// Dynamic color calculation utilities
// ---------------------------------------------------------------------------

import type { SignalDirection, SignalStrength } from '$lib/types/scan';

// ---------------------------------------------------------------------------
// Signal direction colors (CSS variable references)
// ---------------------------------------------------------------------------

const SIGNAL_COLOR_MAP: Record<SignalDirection, string> = {
  bullish: 'var(--color-bullish)',
  bearish: 'var(--color-bearish)',
  neutral: 'var(--color-neutral)',
};

/**
 * Return the CSS custom-property reference for the given signal direction.
 *
 * ```ts
 * getSignalColor('bullish') // "var(--color-bullish)"
 * ```
 */
export function getSignalColor(direction: SignalDirection): string {
  return SIGNAL_COLOR_MAP[direction];
}

// ---------------------------------------------------------------------------
// Strength colors
// ---------------------------------------------------------------------------

const STRENGTH_COLOR_MAP: Record<SignalStrength, string> = {
  1: 'var(--color-strength-1)',
  2: 'var(--color-strength-2)',
  3: 'var(--color-strength-3)',
  4: 'var(--color-strength-4)',
  5: 'var(--color-strength-5)',
};

/**
 * Return the CSS custom-property reference for a 1--5 strength level.
 *
 * ```ts
 * getStrengthColor(3) // "var(--color-strength-3)"
 * ```
 */
export function getStrengthColor(strength: SignalStrength): string {
  return STRENGTH_COLOR_MAP[strength];
}

// ---------------------------------------------------------------------------
// Heatmap color interpolation (OKLCH)
// ---------------------------------------------------------------------------

/**
 * OKLCH color components used for perceptually-uniform interpolation.
 */
interface OklchColor {
  readonly l: number; // Lightness  [0, 1]
  readonly c: number; // Chroma     [0, ~0.4]
  readonly h: number; // Hue        [0, 360)
}

/** Deep red (bearish extreme). */
const HEATMAP_LOW: OklchColor = { l: 0.45, c: 0.2, h: 29 };
/** Neutral midpoint. */
const HEATMAP_MID: OklchColor = { l: 0.7, c: 0.02, h: 250 };
/** Deep green (bullish extreme). */
const HEATMAP_HIGH: OklchColor = { l: 0.6, c: 0.19, h: 145 };

/**
 * Linearly interpolate between two numbers.
 */
function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

/**
 * Interpolate between two OKLCH colours.
 */
function lerpOklch(a: OklchColor, b: OklchColor, t: number): OklchColor {
  return {
    l: lerp(a.l, b.l, t),
    c: lerp(a.c, b.c, t),
    h: lerp(a.h, b.h, t),
  };
}

/**
 * Convert an OKLCH color to a CSS `oklch()` string.
 */
function oklchToString(color: OklchColor): string {
  return `oklch(${color.l.toFixed(3)} ${color.c.toFixed(3)} ${color.h.toFixed(1)})`;
}

/**
 * Map a numeric value within `[min, max]` to an OKLCH-interpolated CSS colour
 * suitable for heat-map visualisations.
 *
 * - `min` maps to deep red.
 * - Midpoint maps to a neutral grey-blue.
 * - `max` maps to deep green.
 *
 * Values outside the range are clamped.
 *
 * ```ts
 * getHeatmapColor(-5, -10, 10) // oklch(0.575 0.110 37.0)  — reddish
 * getHeatmapColor(0, -10, 10)  // oklch(0.700 0.020 250.0) — neutral
 * getHeatmapColor(8, -10, 10)  // oklch(0.620 0.156 145.0) — greenish
 * ```
 */
export function getHeatmapColor(
  value: number,
  min: number,
  max: number,
): string {
  if (min >= max) return oklchToString(HEATMAP_MID);

  // Normalise to [0, 1].
  const clamped = Math.max(min, Math.min(max, value));
  const t = (clamped - min) / (max - min);

  // Two-segment interpolation: 0→0.5 (low→mid), 0.5→1 (mid→high).
  const color =
    t < 0.5
      ? lerpOklch(HEATMAP_LOW, HEATMAP_MID, t * 2)
      : lerpOklch(HEATMAP_MID, HEATMAP_HIGH, (t - 0.5) * 2);

  return oklchToString(color);
}

// ---------------------------------------------------------------------------
// Price-change color
// ---------------------------------------------------------------------------

/**
 * Return a CSS custom-property reference based on whether a price change
 * is positive, negative, or zero.
 *
 * ```ts
 * getPriceChangeColor(1.5)  // "var(--color-bullish)"
 * getPriceChangeColor(-0.3) // "var(--color-bearish)"
 * getPriceChangeColor(0)    // "var(--color-neutral)"
 * ```
 */
export function getPriceChangeColor(change: number): string {
  if (change > 0) return SIGNAL_COLOR_MAP.bullish;
  if (change < 0) return SIGNAL_COLOR_MAP.bearish;
  return SIGNAL_COLOR_MAP.neutral;
}
