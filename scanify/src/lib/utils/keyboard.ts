// ---------------------------------------------------------------------------
// Keyboard shortcut manager
// ---------------------------------------------------------------------------

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

/** A registered keyboard shortcut. */
export interface Shortcut {
  /** Key combo string, e.g. "Cmd+K", "Ctrl+Shift+P", "Escape". */
  readonly keys: string;
  /** Callback invoked when the shortcut fires. */
  readonly action: () => void;
  /** Human-readable description shown in a help overlay. */
  readonly description: string;
  /** Logical scope used to group shortcuts (e.g. "global", "scanner"). */
  readonly scope: string;
  /** Whether this shortcut is currently active. */
  readonly enabled: boolean;
}

/** The public interface exposed by {@link createKeyboardManager}. */
export interface KeyboardManager {
  /** Register a new shortcut (or overwrite an existing one with the same keys). */
  register(shortcut: Shortcut): void;
  /** Remove a previously registered shortcut by its key combo. */
  unregister(keys: string): void;
  /** Process a `KeyboardEvent` and fire matching actions. */
  handleKeyDown(event: KeyboardEvent): void;
  /** Return all currently registered shortcuts. */
  getShortcuts(): readonly Shortcut[];
  /** Whether an input / textarea / contenteditable element is focused. */
  isInputFocused(): boolean;
  /** Tear down the manager (remove the global event listener). */
  destroy(): void;
}

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
 * Examples:
 * ```ts
 * parseShortcut('Cmd+K')          // { key: 'k', ctrl: false, meta: true, shift: false, alt: false }
 * parseShortcut('Ctrl+Shift+P')   // { key: 'p', ctrl: true, meta: false, shift: true, alt: false }
 * parseShortcut('Escape')         // { key: 'escape', ctrl: false, meta: false, shift: false, alt: false }
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
// Internal helpers
// ---------------------------------------------------------------------------

/** Canonical string representation of modifiers + key (used as map key). */
function shortcutId(parsed: ParsedShortcut): string {
  const mods: string[] = [];
  if (parsed.ctrl) mods.push('ctrl');
  if (parsed.meta) mods.push('meta');
  if (parsed.shift) mods.push('shift');
  if (parsed.alt) mods.push('alt');
  mods.push(parsed.key);
  return mods.join('+');
}

function eventToId(event: KeyboardEvent): string {
  const mods: string[] = [];
  if (event.ctrlKey) mods.push('ctrl');
  if (event.metaKey) mods.push('meta');
  if (event.shiftKey) mods.push('shift');
  if (event.altKey) mods.push('alt');
  mods.push(event.key.toLowerCase());
  return mods.join('+');
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

/**
 * Create a new {@link KeyboardManager} instance.
 *
 * Call `.destroy()` when you no longer need it to remove the global
 * `keydown` listener.
 *
 * ```ts
 * const km = createKeyboardManager();
 * km.register({
 *   keys: 'Cmd+K',
 *   action: () => openCommandPalette(),
 *   description: 'Open command palette',
 *   scope: 'global',
 *   enabled: true,
 * });
 * ```
 */
export function createKeyboardManager(): KeyboardManager {
  const registry = new Map<string, { shortcut: Shortcut; parsed: ParsedShortcut }>();

  // -----------------------------------------------------------------------
  // Public methods
  // -----------------------------------------------------------------------

  function register(shortcut: Shortcut): void {
    const parsed = parseShortcut(shortcut.keys);
    const id = shortcutId(parsed);
    registry.set(id, { shortcut, parsed });
  }

  function unregister(keys: string): void {
    const parsed = parseShortcut(keys);
    const id = shortcutId(parsed);
    registry.delete(id);
  }

  function isInputFocused(): boolean {
    const el = document.activeElement;
    if (!el) return false;

    const tag = el.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
    if ((el as HTMLElement).isContentEditable) return true;

    return false;
  }

  function handleKeyDown(event: KeyboardEvent): void {
    const id = eventToId(event);
    const entry = registry.get(id);

    if (!entry) return;
    if (!entry.shortcut.enabled) return;

    // When an input element is focused, only fire shortcuts that include a
    // modifier key (to avoid hijacking regular typing).
    if (isInputFocused()) {
      const { ctrl, meta, alt } = entry.parsed;
      if (!ctrl && !meta && !alt) return;
    }

    event.preventDefault();
    event.stopPropagation();
    entry.shortcut.action();
  }

  function getShortcuts(): readonly Shortcut[] {
    return Array.from(registry.values()).map((e) => e.shortcut);
  }

  // -----------------------------------------------------------------------
  // Auto-attach to the global keydown listener
  // -----------------------------------------------------------------------

  const onKeyDown = (e: KeyboardEvent): void => handleKeyDown(e);

  if (typeof window !== 'undefined') {
    window.addEventListener('keydown', onKeyDown, { capture: true });
  }

  function destroy(): void {
    if (typeof window !== 'undefined') {
      window.removeEventListener('keydown', onKeyDown, { capture: true });
    }
    registry.clear();
  }

  return {
    register,
    unregister,
    handleKeyDown,
    getShortcuts,
    isInputFocused,
    destroy,
  };
}
