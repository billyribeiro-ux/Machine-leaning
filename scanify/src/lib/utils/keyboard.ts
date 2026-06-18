// ---------------------------------------------------------------------------
// Keyboard shortcut utilities
// Platform-aware key parsing, display formatting, and event matching.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Platform detection
// ---------------------------------------------------------------------------

/** Whether the current platform is macOS / iOS. */
export const isMac: boolean =
  typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.platform);

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Parsed representation of a keyboard shortcut combo. */
export interface ParsedShortcut {
  readonly key: string;
  readonly ctrl: boolean;
  readonly meta: boolean;
  readonly shift: boolean;
  readonly alt: boolean;
}

/** Modifier descriptor used by the keyboard store. */
export type ModifierKey = 'ctrl' | 'alt' | 'shift' | 'meta';

// ---------------------------------------------------------------------------
// Shortcut string parser
// ---------------------------------------------------------------------------

/**
 * Parse a human-friendly key-combo string into its constituent modifiers and
 * the base key.
 *
 * Supported modifier tokens (case-insensitive):
 *   `Cmd` / `Meta` / `Win`, `Ctrl` / `Control`, `Shift`, `Alt` / `Option`
 *
 * The special token `CmdOrCtrl` / `CommandOrControl` maps to `meta` on Mac
 * and `ctrl` everywhere else, mirroring Electron's convention.
 *
 * Examples:
 * ```ts
 * parseShortcut('Cmd+K')          // { key: 'k', ctrl: false, meta: true, ... }
 * parseShortcut('Ctrl+Shift+P')   // { key: 'p', ctrl: true,  meta: false, shift: true, ... }
 * parseShortcut('CmdOrCtrl+K')    // meta on Mac, ctrl on Windows
 * parseShortcut('Escape')         // { key: 'escape', ... }
 * ```
 */
export function parseShortcut(keys: string): ParsedShortcut {
  const parts = keys.split('+').map((s) => s.trim());

  let ctrl = false;
  let meta = false;
  let shift = false;
  let alt = false;
  let key = '';

  for (const part of parts) {
    const lower = part.toLowerCase();
    switch (lower) {
      case 'cmd':
      case 'meta':
      case 'win':
        meta = true;
        break;
      case 'ctrl':
      case 'control':
        ctrl = true;
        break;
      case 'cmdorctrl':
      case 'commandorcontrol':
        if (isMac) {
          meta = true;
        } else {
          ctrl = true;
        }
        break;
      case 'shift':
        shift = true;
        break;
      case 'alt':
      case 'option':
        alt = true;
        break;
      default:
        key = lower;
    }
  }

  return { key, ctrl, meta, shift, alt };
}

// ---------------------------------------------------------------------------
// Modifier array helpers
// ---------------------------------------------------------------------------

/**
 * Convert a `ParsedShortcut` modifier state back into a `ModifierKey[]` array
 * compatible with the keyboard store.
 */
export function parsedToModifiers(parsed: ParsedShortcut): ModifierKey[] {
  const mods: ModifierKey[] = [];
  if (parsed.ctrl) mods.push('ctrl');
  if (parsed.meta) mods.push('meta');
  if (parsed.shift) mods.push('shift');
  if (parsed.alt) mods.push('alt');
  return mods;
}

/**
 * Convert a human-readable shortcut string directly to `{ key, modifiers }`.
 *
 * ```ts
 * shortcutToKeyAndModifiers('CmdOrCtrl+Shift+K')
 * // On Mac: { key: 'k', modifiers: ['meta', 'shift'] }
 * // On Win: { key: 'k', modifiers: ['ctrl', 'shift'] }
 * ```
 */
export function shortcutToKeyAndModifiers(shortcutStr: string): {
  key: string;
  modifiers: ModifierKey[];
} {
  const parsed = parseShortcut(shortcutStr);
  return { key: parsed.key, modifiers: parsedToModifiers(parsed) };
}

// ---------------------------------------------------------------------------
// Canonical combo key (for O(1) lookups)
// ---------------------------------------------------------------------------

/** Build a canonical string key for matching (e.g. "ctrl+shift+k"). */
export function buildComboKey(key: string, modifiers: ModifierKey[]): string {
  const mods = [...modifiers].sort();
  return [...mods, key.toLowerCase()].join('+');
}

/** Build a canonical combo key directly from a `KeyboardEvent`. */
export function eventToComboKey(event: KeyboardEvent): string {
  const mods: ModifierKey[] = [];
  if (event.ctrlKey) mods.push('ctrl');
  if (event.metaKey) mods.push('meta');
  if (event.shiftKey) mods.push('shift');
  if (event.altKey) mods.push('alt');
  return buildComboKey(event.key, mods);
}

// ---------------------------------------------------------------------------
// Event matching
// ---------------------------------------------------------------------------

/** Check if a keyboard event exactly matches a set of modifiers. */
export function modifiersMatch(event: KeyboardEvent, modifiers: ModifierKey[]): boolean {
  const has = (mod: ModifierKey): boolean => modifiers.includes(mod);
  return (
    event.ctrlKey === has('ctrl') &&
    event.altKey === has('alt') &&
    event.shiftKey === has('shift') &&
    event.metaKey === has('meta')
  );
}

/**
 * Check whether a `KeyboardEvent` matches a shortcut description.
 *
 * ```ts
 * matchesShortcut(event, { key: 'k', modifiers: ['meta'] })
 * ```
 */
export function matchesShortcut(
  event: KeyboardEvent,
  shortcut: { key: string; modifiers: ModifierKey[] },
): boolean {
  if (event.key.toLowerCase() !== shortcut.key.toLowerCase()) return false;
  return modifiersMatch(event, shortcut.modifiers);
}

// ---------------------------------------------------------------------------
// Input element detection
// ---------------------------------------------------------------------------

/** Returns `true` when focus is inside an input / textarea / contenteditable. */
export function isInputFocused(): boolean {
  if (typeof document === 'undefined') return false;
  const el = document.activeElement;
  if (!el) return false;
  const tag = el.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  return (el as HTMLElement).isContentEditable;
}

// ---------------------------------------------------------------------------
// Platform-aware display labels
// ---------------------------------------------------------------------------

/** Map of special key names to their display symbols. */
const KEY_DISPLAY_MAP: Record<string, string> = {
  ' ': 'Space',
  arrowup: '↑',
  arrowdown: '↓',
  arrowleft: '←',
  arrowright: '→',
  escape: 'Esc',
  enter: '↵',
  backspace: '⌫',
  delete: 'Del',
  tab: '↹',
  '[': '[',
  ']': ']',
};

/** Mac modifier symbols in conventional order. */
const MAC_MODIFIER_SYMBOLS: Record<ModifierKey, string> = {
  ctrl: '⌃',
  alt: '⌥',
  shift: '⇧',
  meta: '⌘',
};

/** Windows modifier labels in conventional order. */
const WIN_MODIFIER_LABELS: Record<ModifierKey, string> = {
  ctrl: 'Ctrl',
  alt: 'Alt',
  shift: 'Shift',
  meta: 'Win',
};

/** Canonical modifier order for display. */
const MODIFIER_ORDER: ModifierKey[] = ['ctrl', 'meta', 'alt', 'shift'];

/**
 * Format a shortcut for display. On Mac uses symbols (e.g. "⌘K"), on
 * Windows uses labels with "+" separators (e.g. "Ctrl+K").
 */
export function formatShortcutDisplay(
  key: string,
  modifiers: ModifierKey[],
): string {
  const parts: string[] = [];
  const modSet = new Set(modifiers);

  for (const mod of MODIFIER_ORDER) {
    if (!modSet.has(mod)) continue;
    parts.push(isMac ? MAC_MODIFIER_SYMBOLS[mod] : WIN_MODIFIER_LABELS[mod]);
  }

  // Prettify the key name
  const lower = key.toLowerCase();
  let keyDisplay = KEY_DISPLAY_MAP[lower] ?? KEY_DISPLAY_MAP[key] ?? null;
  if (keyDisplay === null) {
    keyDisplay = key.length === 1 ? key.toUpperCase() : key;
  }

  parts.push(keyDisplay);
  return parts.join(isMac ? '' : '+');
}

/**
 * A convenience that takes a human-readable shortcut string and produces a
 * platform-aware display label.
 *
 * ```ts
 * formatShortcutString('CmdOrCtrl+Shift+K')
 * // Mac:    "⇧⌘K"
 * // Windows: "Ctrl+Shift+K"
 * ```
 */
export function formatShortcutString(shortcutStr: string): string {
  const { key, modifiers } = shortcutToKeyAndModifiers(shortcutStr);
  return formatShortcutDisplay(key, modifiers);
}

// ---------------------------------------------------------------------------
// Conflict detection helper
// ---------------------------------------------------------------------------

/**
 * Check for shortcut conflicts within a list of registrations. Returns an
 * array of `{ combo, ids }` for any combo key that has more than one
 * registration.
 */
export function detectConflicts(
  shortcuts: Array<{ id: string; key: string; modifiers: ModifierKey[] }>,
): Array<{ combo: string; ids: string[] }> {
  const map = new Map<string, string[]>();
  for (const s of shortcuts) {
    const combo = buildComboKey(s.key, s.modifiers);
    if (!map.has(combo)) map.set(combo, []);
    map.get(combo)!.push(s.id);
  }
  const conflicts: Array<{ combo: string; ids: string[] }> = [];
  for (const [combo, ids] of map) {
    if (ids.length > 1) {
      conflicts.push({ combo, ids });
    }
  }
  return conflicts;
}
