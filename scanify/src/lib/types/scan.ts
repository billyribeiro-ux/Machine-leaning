// ---------------------------------------------------------------------------
// Scan result types for the Scanify trading scanner
// ---------------------------------------------------------------------------

import type { Signal } from './signal';

/** Categories of scans the platform supports. */
export type ScanCategory =
  | 'momentum'
  | 'volatility'
  | 'flow'
  | 'technical'
  | 'institutional'
  | 'options'
  | 'breadth'
  | 'custom';

/** Directional bias of a signal or scan result. */
export type SignalDirection = 'bullish' | 'bearish' | 'neutral';

/** Discrete 1-5 strength rating. */
export type SignalStrength = 1 | 2 | 3 | 4 | 5;

/** Sort direction for scan result ordering. */
export type SortDirection = 'asc' | 'desc';

/** Comparison operators available for scan filters. */
export type ScanFilterOperator =
  | 'gt'
  | 'lt'
  | 'eq'
  | 'gte'
  | 'lte'
  | 'between'
  | 'in'
  | 'contains';

// ---------------------------------------------------------------------------
// Core interfaces
// ---------------------------------------------------------------------------

/** A single scan result representing one matched symbol. */
export interface ScanResult {
  /** Unique identifier for this result. */
  readonly id: string;
  /** Ticker symbol (e.g. "AAPL"). */
  readonly symbol: string;
  /** Company / instrument display name. */
  readonly name: string;
  /** Which scan category produced this result. */
  readonly category: ScanCategory;
  /** Directional bias. */
  readonly direction: SignalDirection;
  /** Signal strength rating. */
  readonly strength: SignalStrength;
  /** Last traded price. */
  readonly price: number;
  /** Absolute price change. */
  readonly change: number;
  /** Percentage price change. */
  readonly changePercent: number;
  /** Trading volume. */
  readonly volume: number;
  /** Volume relative to the average (e.g. 2.5 = 250 % of avg). */
  readonly relativeVolume: number;
  /** Market capitalisation in USD. */
  readonly marketCap: number;
  /** Sector classification. */
  readonly sector: string;
  /** Industry classification. */
  readonly industry: string;
  /** ISO-8601 timestamp when the result was generated. */
  readonly timestamp: string;
  /** Arbitrary key/value metadata attached to the result. */
  readonly metadata: Record<string, string | number | boolean>;
  /** Mini price series used to render an inline sparkline. */
  readonly sparklineData: readonly number[];
  /** Signals that contributed to this scan result. */
  readonly signals: readonly Signal[];
}

/**
 * A filter predicate applied to a scan.
 *
 * `value` is typed as a discriminated union:
 *   - single-operand operators use `string | number | boolean`
 *   - `between` uses a two-element tuple
 *   - `in` uses an array
 */
export interface ScanFilter {
  /** The data field this filter targets (e.g. "price", "volume"). */
  readonly field: string;
  /** Comparison operator. */
  readonly operator: ScanFilterOperator;
  /** The comparison value(s). */
  readonly value: ScanFilterValue;
  /** Whether this filter is currently active. */
  readonly enabled: boolean;
}

/** Possible value shapes for a ScanFilter depending on operator. */
export type ScanFilterValue =
  | string
  | number
  | boolean
  | readonly [number, number]
  | readonly (string | number | boolean)[];

/** Persisted configuration for a scan. */
export interface ScanConfig {
  /** Unique identifier. */
  readonly id: string;
  /** Human-readable name. */
  readonly name: string;
  /** Optional longer description. */
  readonly description: string;
  /** Scan category this config belongs to. */
  readonly category: ScanCategory;
  /** Ordered list of filters. */
  readonly filters: readonly ScanFilter[];
  /** Field name used to sort results. */
  readonly sortBy: string;
  /** Sort direction. */
  readonly sortDirection: SortDirection;
  /** Whether the scan is actively running. */
  readonly isActive: boolean;
  /** ISO-8601 creation timestamp. */
  readonly createdAt: string;
  /** ISO-8601 last-update timestamp. */
  readonly updatedAt: string;
}

/** A pre-built scan preset shipped with the app or created by the user. */
export interface ScanPreset {
  /** Unique identifier. */
  readonly id: string;
  /** Display name shown in the preset picker. */
  readonly name: string;
  /** Short description of what this preset scans for. */
  readonly description: string;
  /** The underlying scan configuration. */
  readonly config: ScanConfig;
  /** Whether this preset is the default selection. */
  readonly isDefault: boolean;
  /** Icon identifier used in the UI (e.g. an icon-library key). */
  readonly icon: string;
}
