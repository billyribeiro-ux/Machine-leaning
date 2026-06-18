// ---------------------------------------------------------------------------
// Keyboard shortcuts store – Svelte 5 rune-based reactive state
// Comprehensive shortcut registry with categories, conflict detection,
// active shortcut tracking, and modifier key support.
// ---------------------------------------------------------------------------

import {
  type ModifierKey,
  buildComboKey,
  modifiersMatch,
  formatShortcutDisplay,
  detectConflicts,
  isInputFocused,
} from '$lib/utils/keyboard';

export type { ModifierKey };

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

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
  /**
   * When true, this shortcut fires even when an input/textarea is focused
   * (regardless of whether it has a modifier key).
   */
  allowInInput: boolean;
}

/** Compact registration options. */
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
  allowInInput?: boolean;
}

/** Category ordering and metadata for the overlay. */
export interface ShortcutCategory {
  id: string;
  label: string;
  icon: string;
}

/** A detected conflict between two or more shortcuts. */
export interface ShortcutConflict {
  combo: string;
  ids: string[];
}

// ---------------------------------------------------------------------------
// Predefined categories (display order)
// ---------------------------------------------------------------------------

export const SHORTCUT_CATEGORIES: ShortcutCategory[] = [
  { id: 'Navigation', label: 'Navigation', icon: '⌗' },
  { id: 'Scanner', label: 'Scanner', icon: '⊙' },
  { id: 'Data', label: 'Data', icon: '⊞' },
  { id: 'System', label: 'System', icon: '⚙' },
];

// ---------------------------------------------------------------------------
// Store factory
// ---------------------------------------------------------------------------

function createKeyboardStore() {
  // ---- reactive state ----
  let shortcuts = $state<Map<string, KeyboardShortcut>>(new Map());
  let activeScope = $state<string>('global');
  let isListening = $state(false);
  let lastTriggered = $state<string | null>(null);
  let lastTriggeredAt = $state<number>(0);
  let paletteOpen = $state(false);

  // ---- derived ----

  /** All registered shortcuts as a flat list. */
  let shortcutList = $derived([...shortcuts.values()]);

  /** Shortcuts active in the current scope (includes global shortcuts). */
  let activeShortcuts = $derived(
    shortcutList.filter(
      (s) =>
        s.enabled &&
        (s.scopes.length === 0 || s.scopes.includes(activeScope)),
    ),
  );

  /** Shortcuts grouped by category in display order. */
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

  /** Detected shortcut conflicts. */
  let conflicts = $derived.by((): ShortcutConflict[] => {
    return detectConflicts(
      shortcutList.map((s) => ({ id: s.id, key: s.key, modifiers: s.modifiers })),
    );
  });

  /** Whether any shortcut conflicts exist. */
  let hasConflicts = $derived(conflicts.length > 0);

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
    const inputFocused = isInputFocused();

    const combo = buildComboKey(event.key, [
      ...(event.ctrlKey ? (['ctrl'] as const) : []),
      ...(event.altKey ? (['alt'] as const) : []),
      ...(event.shiftKey ? (['shift'] as const) : []),
      ...(event.metaKey ? (['meta'] as const) : []),
    ]);

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

      // When input is focused, only allow shortcuts that:
      //  - have allowInInput set, OR
      //  - have a modifier key (Ctrl/Meta/Alt), OR
      //  - are Escape
      if (inputFocused && !shortcut.allowInInput) {
        const hasModifier =
          shortcut.modifiers.includes('ctrl') ||
          shortcut.modifiers.includes('meta') ||
          shortcut.modifiers.includes('alt');
        if (!hasModifier && event.key !== 'Escape') continue;
      }

      if (shortcut.preventDefault) event.preventDefault();
      if (shortcut.stopPropagation) event.stopPropagation();

      lastTriggered = shortcut.id;
      lastTriggeredAt = Date.now();
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
      allowInInput: registration.allowInInput ?? false,
    };

    shortcuts.set(shortcut.id, shortcut);
    shortcuts = new Map(shortcuts);

    return () => unregisterShortcut(shortcut.id);
  }

  /** Register multiple shortcuts at once. Returns a single cleanup function. */
  function registerShortcuts(registrations: ShortcutRegistration[]): () => void {
    // Batch all insertions before triggering reactivity
    for (const reg of registrations) {
      const shortcut: KeyboardShortcut = {
        id: reg.id,
        key: reg.key,
        modifiers: reg.modifiers ?? [],
        description: reg.description,
        scopes: reg.scopes ?? [],
        handler: reg.handler,
        enabled: reg.enabled ?? true,
        category: reg.category ?? 'General',
        preventDefault: reg.preventDefault ?? true,
        stopPropagation: reg.stopPropagation ?? false,
        allowInInput: reg.allowInInput ?? false,
      };
      shortcuts.set(shortcut.id, shortcut);
    }
    // Single reactivity trigger
    shortcuts = new Map(shortcuts);

    return () => {
      for (const reg of registrations) {
        shortcuts.delete(reg.id);
      }
      shortcuts = new Map(shortcuts);
    };
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
      (s) => s.enabled && (s.scopes.length === 0 || s.scopes.includes(scope)),
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
    return shortcut ? formatShortcutDisplay(shortcut.key, shortcut.modifiers) : '';
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
    get lastTriggeredAt() {
      return lastTriggeredAt;
    },
    get paletteOpen() {
      return paletteOpen;
    },
    set paletteOpen(value: boolean) {
      paletteOpen = value;
    },
    get conflicts() {
      return conflicts;
    },
    get hasConflicts() {
      return hasConflicts;
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
    formatShortcutDisplay,
  };
}

export const keyboardStore = createKeyboardStore();
