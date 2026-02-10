// ---------------------------------------------------------------------------
// Layout configuration types for the Scanify trading scanner
// ---------------------------------------------------------------------------

/**
 * Well-known panel identifiers used across the UI.
 *
 * Defined as a string literal union so that only valid panel IDs can be
 * referenced in layout configurations.
 */
export type PanelId =
  | 'scanner'
  | 'chart'
  | 'watchlist'
  | 'signals'
  | 'options-chain'
  | 'options-flow'
  | 'market-internals'
  | 'sector-map'
  | 'news'
  | 'alerts'
  | 'settings'
  | 'gex'
  | 'details';

// ---------------------------------------------------------------------------
// Panel configuration
// ---------------------------------------------------------------------------

/** Geometry and visibility state for a single panel. */
export interface PanelConfig {
  /** Which panel this configuration belongs to. */
  readonly id: PanelId;
  /** Horizontal grid position (px or grid units). */
  readonly x: number;
  /** Vertical grid position (px or grid units). */
  readonly y: number;
  /** Panel width (px or grid units). */
  readonly width: number;
  /** Panel height (px or grid units). */
  readonly height: number;
  /** Minimum allowed width (px or grid units). */
  readonly minWidth: number;
  /** Minimum allowed height (px or grid units). */
  readonly minHeight: number;
  /** Whether the panel is currently collapsed to its title bar. */
  readonly isCollapsed: boolean;
  /** Whether the panel is visible at all. */
  readonly isVisible: boolean;
  /** Stacking order (higher = on top). */
  readonly zIndex: number;
}

// ---------------------------------------------------------------------------
// Layout presets
// ---------------------------------------------------------------------------

/** A named, saveable arrangement of panels. */
export interface LayoutPreset {
  /** Unique preset identifier. */
  readonly id: string;
  /** Human-readable name (e.g. "Default", "Options Focus"). */
  readonly name: string;
  /** Short description of the layout. */
  readonly description: string;
  /** Ordered list of panel configurations making up this layout. */
  readonly panels: readonly PanelConfig[];
  /** Whether this preset is the factory default. */
  readonly isDefault: boolean;
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

/** Payload emitted when a panel is resized by the user. */
export interface PanelResizeEvent {
  /** The panel that was resized. */
  readonly panelId: PanelId;
  /** New width after resize. */
  readonly width: number;
  /** New height after resize. */
  readonly height: number;
}

// ---------------------------------------------------------------------------
// Runtime state
// ---------------------------------------------------------------------------

/** The current runtime layout state held in the store. */
export interface LayoutState {
  /** The currently active preset (null if user has a custom unsaved layout). */
  readonly activePreset: string | null;
  /** Live panel configurations keyed by panel ID. */
  readonly panels: ReadonlyMap<PanelId, PanelConfig>;
  /** When true the user cannot drag or resize panels. */
  readonly isLocked: boolean;
}
