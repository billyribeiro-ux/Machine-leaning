// ---------------------------------------------------------------------------
// Signal & alert types for the Scanify trading scanner
// ---------------------------------------------------------------------------

import type { ScanCategory, SignalDirection, SignalStrength } from './scan';

// ---------------------------------------------------------------------------
// Signal
// ---------------------------------------------------------------------------

/** A single signal emitted by a scan. */
export interface Signal {
  /** Unique signal identifier. */
  readonly id: string;
  /** The scan that produced this signal. */
  readonly scanId: string;
  /** Ticker symbol. */
  readonly symbol: string;
  /** Directional bias. */
  readonly direction: SignalDirection;
  /** 1-5 strength rating. */
  readonly strength: SignalStrength;
  /** Scan category that sourced this signal. */
  readonly category: ScanCategory;
  /** Short signal name (e.g. "MACD Cross"). */
  readonly name: string;
  /** Human-readable description of the signal. */
  readonly description: string;
  /** Price at the time the signal fired. */
  readonly price: number;
  /** ISO-8601 timestamp. */
  readonly timestamp: string;
  /** Arbitrary metadata attached to the signal. */
  readonly metadata: Record<string, string | number | boolean>;
  /** Whether this signal was generated in the most recent scan tick. */
  readonly isNew: boolean;
  /** Whether the signal is older than the configured freshness window. */
  readonly isStale: boolean;
}

// ---------------------------------------------------------------------------
// Signal feed
// ---------------------------------------------------------------------------

/** Priority bucket for ordering items in the signal feed. */
export type DisplayPriority = 'critical' | 'high' | 'medium' | 'low';

/** Sound identifiers for alert audio cues. */
export type SoundType =
  | 'chime'
  | 'ding'
  | 'alert'
  | 'sweep'
  | 'bell'
  | 'custom';

/** Notification delivery channel. */
export type NotificationType = 'sound' | 'push' | 'email';

/** A signal enriched with feed-specific display metadata. */
export interface SignalFeedItem extends Signal {
  /** How prominently to display this item in the feed. */
  readonly displayPriority: DisplayPriority;
  /** Whether an audible alert should fire for this item. */
  readonly soundAlert: boolean;
  /** ISO-8601 timestamp after which the item should be hidden. */
  readonly expiresAt: string;
}

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

/** User-configurable alert rule. */
export interface AlertConfig {
  /** Unique alert identifier. */
  readonly id: string;
  /** Human-readable alert name. */
  readonly name: string;
  /** Scan IDs this alert subscribes to. */
  readonly scanIds: readonly string[];
  /** Minimum signal strength required to fire. */
  readonly minStrength: SignalStrength;
  /** Directional filters (empty = all directions). */
  readonly directions: readonly SignalDirection[];
  /** Category filters (empty = all categories). */
  readonly categories: readonly ScanCategory[];
  /** Whether to play a sound when the alert fires. */
  readonly soundEnabled: boolean;
  /** Which sound to play. */
  readonly soundType: SoundType;
  /** Whether to send a browser push notification. */
  readonly pushEnabled: boolean;
  /** Whether to send an email notification. */
  readonly emailEnabled: boolean;
  /** Whether this alert rule is currently active. */
  readonly isActive: boolean;
}

/** Historical record of a delivered alert. */
export interface AlertHistory {
  /** Unique history entry identifier. */
  readonly id: string;
  /** The signal that triggered the alert. */
  readonly signal: Signal;
  /** ISO-8601 timestamp when the user acknowledged the alert (null if unread). */
  readonly acknowledgedAt: string | null;
  /** The channel through which the notification was delivered. */
  readonly notificationType: NotificationType;
}
