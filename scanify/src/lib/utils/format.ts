// ---------------------------------------------------------------------------
// Number / currency / percentage formatting utilities
// ---------------------------------------------------------------------------

/**
 * Options for the generic {@link formatNumber} helper.
 */
export interface FormatNumberOptions {
  /** Number of decimal places (default: 2). */
  readonly decimals?: number;
  /** Use compact notation (e.g. 1.2M, 345K). */
  readonly compact?: boolean;
  /** Prefix positive values with "+". */
  readonly signed?: boolean;
}

// ---------------------------------------------------------------------------
// Shared Intl.NumberFormat instances (lazily cached)
// ---------------------------------------------------------------------------

const compactFormatter = new Intl.NumberFormat('en-US', {
  notation: 'compact',
  maximumFractionDigits: 2,
});

function getCurrencyFormatter(decimals: number): Intl.NumberFormat {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

// Pre-build the two most common currency formatters.
const currencyFormatters: Record<number, Intl.NumberFormat> = {
  2: getCurrencyFormatter(2),
  0: getCurrencyFormatter(0),
};

function currencyFormatter(decimals: number): Intl.NumberFormat {
  let f = currencyFormatters[decimals];
  if (!f) {
    f = getCurrencyFormatter(decimals);
    currencyFormatters[decimals] = f;
  }
  return f;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Format a price value with a dollar sign, commas, and a configurable number
 * of decimal places.
 *
 * ```ts
 * formatPrice(1234.5)    // "$1,234.50"
 * formatPrice(0.0045, 4) // "$0.0045"
 * ```
 */
export function formatPrice(value: number, decimals: number = 2): string {
  if (!Number.isFinite(value)) return '$--';
  return `$${currencyFormatter(decimals).format(value)}`;
}

/**
 * Format a percentage value.
 *
 * @param value   The raw numeric percentage (e.g. 12.5 for 12.5 %).
 * @param signed  If `true`, prefix positive values with "+".
 *
 * ```ts
 * formatPercent(12.5)        // "12.50%"
 * formatPercent(-3.2, true)  // "-3.20%"
 * formatPercent(3.2, true)   // "+3.20%"
 * ```
 */
export function formatPercent(value: number, signed: boolean = false): string {
  if (!Number.isFinite(value)) return '--%';
  const formatted = Math.abs(value).toFixed(2);
  if (value > 0 && signed) return `+${formatted}%`;
  if (value < 0) return `-${formatted}%`;
  return `${formatted}%`;
}

/**
 * Format a volume number in compact notation (e.g. 1.2M, 345K).
 *
 * ```ts
 * formatVolume(1_234_567)  // "1.23M"
 * formatVolume(345_000)    // "345K"
 * ```
 */
export function formatVolume(value: number): string {
  if (!Number.isFinite(value)) return '--';
  if (value < 0) return `-${formatVolume(-value)}`;

  if (value >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toFixed(2)}B`;
  }
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(2)}K`;
  }
  return value.toFixed(0);
}

/**
 * Format a market-capitalisation value in compact dollar notation.
 *
 * ```ts
 * formatMarketCap(1_200_000_000_000) // "$1.20T"
 * formatMarketCap(345_000_000)       // "$345.00M"
 * ```
 */
export function formatMarketCap(value: number): string {
  if (!Number.isFinite(value)) return '$--';
  if (value < 0) return `-${formatMarketCap(-value)}`;

  if (value >= 1_000_000_000_000) {
    return `$${(value / 1_000_000_000_000).toFixed(2)}T`;
  }
  if (value >= 1_000_000_000) {
    return `$${(value / 1_000_000_000).toFixed(2)}B`;
  }
  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(2)}M`;
  }
  if (value >= 1_000) {
    return `$${(value / 1_000).toFixed(2)}K`;
  }
  return `$${value.toFixed(2)}`;
}

/**
 * Generic number formatting with optional compact notation and sign prefix.
 */
export function formatNumber(
  value: number,
  opts?: FormatNumberOptions,
): string {
  if (!Number.isFinite(value)) return '--';

  const decimals = opts?.decimals ?? 2;
  const compact = opts?.compact ?? false;
  const signed = opts?.signed ?? false;

  let result: string;

  if (compact) {
    result = compactFormatter.format(value);
  } else {
    result = currencyFormatter(decimals).format(Math.abs(value));
    if (value < 0) result = `-${result}`;
  }

  if (signed && value > 0) {
    result = `+${result}`;
  }

  return result;
}

// ---------------------------------------------------------------------------
// Time-based formatters
// ---------------------------------------------------------------------------

const SECOND = 1_000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const WEEK = 7 * DAY;

/**
 * Produce a human-readable relative time string such as "2s ago" or "3h ago".
 *
 * @param timestamp  A Unix-epoch millisecond timestamp or a `Date` instance.
 */
export function formatRelativeTime(timestamp: number | Date): string {
  const ts = timestamp instanceof Date ? timestamp.getTime() : timestamp;
  const delta = Date.now() - ts;

  if (delta < 0) return 'just now';
  if (delta < SECOND) return 'just now';
  if (delta < MINUTE) return `${Math.floor(delta / SECOND)}s ago`;
  if (delta < HOUR) return `${Math.floor(delta / MINUTE)}m ago`;
  if (delta < DAY) return `${Math.floor(delta / HOUR)}h ago`;
  if (delta < WEEK) return `${Math.floor(delta / DAY)}d ago`;

  return `${Math.floor(delta / WEEK)}w ago`;
}

const timeOnlyFormatter = new Intl.DateTimeFormat('en-US', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

const dateOnlyFormatter = new Intl.DateTimeFormat('en-US', {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
});

const dateTimeFormatter = new Intl.DateTimeFormat('en-US', {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

/**
 * Format a timestamp as a locale-aware time, date, or datetime string.
 *
 * @param timestamp  A Unix-epoch millisecond timestamp or a `Date`.
 * @param format     One of `'time'`, `'date'`, or `'datetime'` (default: `'time'`).
 */
export function formatTime(
  timestamp: number | Date,
  format: 'time' | 'date' | 'datetime' = 'time',
): string {
  const date = timestamp instanceof Date ? timestamp : new Date(timestamp);

  switch (format) {
    case 'time':
      return timeOnlyFormatter.format(date);
    case 'date':
      return dateOnlyFormatter.format(date);
    case 'datetime':
      return dateTimeFormatter.format(date);
  }
}
