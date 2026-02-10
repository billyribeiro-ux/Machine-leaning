// ---------------------------------------------------------------------------
// Keyboard shortcuts store – Svelte 5 rune-based reactive state
// ---------------------------------------------------------------------------

/** Modifier keys that can accompany a shortcut. */
export type ModifierKey = 'ctrl' | 'alt' | 'shift' | 'meta';

/** A registered keyboard shortcut. */
export interface KeyboardShortcut {
  /** Unique shortcut identifier. */
  id: string;
  /** The key (e.g. "k", "Enter", "Escape", "ArrowUp"). */
  key: string;
  /** Required modifier keys (order-independent). */
  modifiers: ModifierKey[];
  /** Human-readable description shown in the shortcut palette. */
  description: string;
  /** The scope(s) this shortcut is active in. Empty = global. */
  scopes: string[];
  /** Callback to execute when the shortcut fires. */
  handler: (event: KeyboardEvent) => void;
  /** Whether this shortcut is currently enabled. */
  enabled: boolean;
  /** Display category for grouping in the shortcut palette. */
  category: string;
  /** Whether to prevent the default browser behavior. */
  preventDefault: boolean;
  /** Whether to stop event propagation. */
  stopPropagation: boolean;
}

/** Compact registration options (handler is separate). */
export interface ShortcutRegistration {
  id: string;
  key: string;
  modifiers?: ModifierKey[];
  description: string;
  scopes?: string[];
  handler: (event: KeyboardEvent) => void;
  enabled?: boolean;
  category?: string;
  preventDefault?: boolean;
  stopPropagation?: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a canonical string key for matching (e.g. "ctrl+shift+k"). */
function buildComboKey(key: string, modifiers: ModifierKey[]): string {
  const mods = [...modifiers].sort();
  return [...mods, key.toLowerCase()].join('+');
}

/** Check if a keyboard event matches a set of modifiers. */
function modifiersMatch(event: KeyboardEvent, modifiers: ModifierKey[]): boolean {
  const has = (mod: ModifierKey): boolean => modifiers.includes(mod);
  return (
    event.ctrlKey === has('ctrl') &&
    event.altKey === has('alt') &&
    event.shiftKey === has('shift') &&
    event.metaKey === has('meta')
  );
}

/** Format a shortcut for display (e.g. "Ctrl+Shift+K"). */
function formatShortcut(shortcut: KeyboardShortcut): string {
  const parts: string[] = [];
  const isMac =
    typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.platform);

  for (const mod of [...shortcut.modifiers].sort()) {
    switch (mod) {
      case 'ctrl':
        parts.push(isMac ? '\u2318' : 'Ctrl');
        break;
      case 'alt':
        parts.push(isMac ? '\u2325' : 'Alt');
        break;
      case 'shift':
        parts.push(isMac ? '\u21E7' : 'Shift');
        break;
      case 'meta':
        parts.push(isMac ? '\u2318' : 'Win');
        break;
    }
  }

  // Prettify the key name
  let keyDisplay = shortcut.key;
  switch (shortcut.key) {
    case ' ':
      keyDisplay = 'Space';
      break;
    case 'ArrowUp':
      keyDisplay = '\u2191';
      break;
    case 'ArrowDown':
      keyDisplay = '\u2193';
      break;
    case 'ArrowLeft':
      keyDisplay = '\u2190';
      break;
    case 'ArrowRight':
      keyDisplay = '\u2192';
      break;
    case 'Escape':
      keyDisplay = 'Esc';
      break;
    case 'Enter':
      keyDisplay = '\u21B5';
      break;
    case 'Backspace':
      keyDisplay = '\u232B';
      break;
    case 'Delete':
      keyDisplay = 'Del';
      break;
    case 'Tab':
      keyDisplay = '\u21B9';
      break;
    default:
      keyDisplay = shortcut.key.length === 1 ? shortcut.key.toUpperCase() : shortcut.key;
  }

  parts.push(keyDisplay);
  return parts.join(isMac ? '' : '+');
}

// ---------------------------------------------------------------------------
// Store factory
// ---------------------------------------------------------------------------

function createKeyboardStore() {
  // ---- reactive state ----
  let shortcuts = $state<Map<string, KeyboardShortcut>>(new Map());
  let activeScope = $state<string>('global');
  let isListening = $state(false);
  let lastTriggered = $state<string | null>(null);
  let paletteOpen = $state(false);

  // ---- derived ----

  /** All registered shortcuts as a flat list. */
  let shortcutList = $derived([...shortcuts.values()]);

  /** Shortcuts active in the current scope (includes global shortcuts). */
  let activeShortcuts = $derived(
    shortcutList.filter(
      (s) =>
        s.enabled &&
        (s.scopes.length === 0 || s.scopes.includes(activeScope))
    )
  );

  /** Shortcuts grouped by category. */
  let shortcutsByCategory = $derived.by(() => {
    const groups = new Map<string, KeyboardShortcut[]>();
    for (const shortcut of activeShortcuts) {
      const cat = shortcut.category || 'General';
      if (!groups.has(cat)) {
        groups.set(cat, []);
      }
      groups.get(cat)!.push(shortcut);
    }
    return groups;
  });

  /** Total number of registered shortcuts. */
  let shortcutCount = $derived(shortcuts.size);

  // Private: lookup by combo key for O(1) matching
  let comboIndex = $derived.by(() => {
    const index = new Map<string, KeyboardShortcut[]>();
    for (const shortcut of shortcutList) {
      if (!shortcut.enabled) continue;
      const combo = buildComboKey(shortcut.key, shortcut.modifiers);
      if (!index.has(combo)) {
        index.set(combo, []);
      }
      index.get(combo)!.push(shortcut);
    }
    return index;
  });

  // ---- event handler ----

  function handleKeyDown(event: KeyboardEvent): void {
    // Skip if typing in an input element
    const target = event.target as HTMLElement;
    if (
      target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.tagName === 'SELECT' ||
      target.isContentEditable
    ) {
      // Still allow Escape in input fields
      if (event.key !== 'Escape') return;
    }

    const combo = buildComboKey(
      event.key,
      [
        ...(event.ctrlKey ? ['ctrl' as const] : []),
        ...(event.altKey ? ['alt' as const] : []),
        ...(event.shiftKey ? ['shift' as const] : []),
        ...(event.metaKey ? ['meta' as const] : []),
      ]
    );

    const candidates = comboIndex.get(combo);
    if (!candidates) return;

    for (const shortcut of candidates) {
      // Check scope
      if (
        shortcut.scopes.length > 0 &&
        !shortcut.scopes.includes(activeScope)
      ) {
        continue;
      }

      // Verify modifier exact match
      if (!modifiersMatch(event, shortcut.modifiers)) continue;

      if (shortcut.preventDefault) event.preventDefault();
      if (shortcut.stopPropagation) event.stopPropagation();

      lastTriggered = shortcut.id;
      shortcut.handler(event);
      return; // first match wins
    }
  }

  // ---- actions ----

  /** Register a keyboard shortcut. Returns an unregister function. */
  function registerShortcut(registration: ShortcutRegistration): () => void {
    const shortcut: KeyboardShortcut = {
      id: registration.id,
      key: registration.key,
      modifiers: registration.modifiers ?? [],
      description: registration.description,
      scopes: registration.scopes ?? [],
      handler: registration.handler,
      enabled: registration.enabled ?? true,
      category: registration.category ?? 'General',
      preventDefault: registration.preventDefault ?? true,
      stopPropagation: registration.stopPropagation ?? false,
    };

    shortcuts.set(shortcut.id, shortcut);
    shortcuts = new Map(shortcuts);

    return () => unregisterShortcut(shortcut.id);
  }

  /** Register multiple shortcuts at once. Returns a single cleanup function. */
  function registerShortcuts(registrations: ShortcutRegistration[]): () => void {
    const cleanups = registrations.map((r) => registerShortcut(r));
    return () => cleanups.forEach((fn) => fn());
  }

  /** Unregister a shortcut by id. */
  function unregisterShortcut(id: string): void {
    shortcuts.delete(id);
    shortcuts = new Map(shortcuts);
  }

  /** Set the active scope (e.g. "scanner", "chart", "modal"). */
  function setScope(scope: string): void {
    activeScope = scope;
  }

  /** Get all shortcuts registered for a specific scope. */
  function getShortcutsForScope(scope: string): KeyboardShortcut[] {
    return shortcutList.filter(
      (s) => s.enabled && (s.scopes.length === 0 || s.scopes.includes(scope))
    );
  }

  /** Enable or disable a shortcut. */
  function setEnabled(id: string, enabled: boolean): void {
    const shortcut = shortcuts.get(id);
    if (shortcut) {
      shortcuts.set(id, { ...shortcut, enabled });
      shortcuts = new Map(shortcuts);
    }
  }

  /** Get a formatted display string for a shortcut by id. */
  function getDisplayString(id: string): string {
    const shortcut = shortcuts.get(id);
    return shortcut ? formatShortcut(shortcut) : '';
  }

  /** Open the shortcut palette / cheat sheet. */
  function openPalette(): void {
    paletteOpen = true;
  }

  /** Close the shortcut palette. */
  function closePalette(): void {
    paletteOpen = false;
  }

  /** Toggle the shortcut palette. */
  function togglePalette(): void {
    paletteOpen = !paletteOpen;
  }

  /** Start listening for keyboard events on the document. */
  function startListening(): void {
    if (isListening) return;
    if (typeof document !== 'undefined') {
      document.addEventListener('keydown', handleKeyDown, { capture: true });
      isListening = true;
    }
  }

  /** Stop listening for keyboard events. */
  function stopListening(): void {
    if (!isListening) return;
    if (typeof document !== 'undefined') {
      document.removeEventListener('keydown', handleKeyDown, { capture: true });
      isListening = false;
    }
  }

  /** Clear all registered shortcuts. */
  function clearAll(): void {
    shortcuts = new Map();
  }

  // ---- public API ----
  return {
    // reactive getters
    get shortcuts() {
      return shortcuts;
    },
    get shortcutList() {
      return shortcutList;
    },
    get activeShortcuts() {
      return activeShortcuts;
    },
    get shortcutsByCategory() {
      return shortcutsByCategory;
    },
    get shortcutCount() {
      return shortcutCount;
    },
    get activeScope() {
      return activeScope;
    },
    get isListening() {
      return isListening;
    },
    get lastTriggered() {
      return lastTriggered;
    },
    get paletteOpen() {
      return paletteOpen;
    },

    // actions
    registerShortcut,
    registerShortcuts,
    unregisterShortcut,
    setScope,
    getShortcutsForScope,
    setEnabled,
    getDisplayString,
    openPalette,
    closePalette,
    togglePalette,
    startListening,
    stopListening,
    clearAll,

    // utility
    formatShortcut,
  };
}

export const keyboardStore = createKeyboardStore();
