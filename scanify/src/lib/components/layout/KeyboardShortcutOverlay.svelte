<!--
  KeyboardShortcutOverlay.svelte
  Full-screen modal overlay showing all keyboard shortcuts organized by category.
  Triggered by Cmd+/ or ? key. Premium VS Code-style design.
-->
<script lang="ts">
  import { keyboardStore, SHORTCUT_CATEGORIES } from '$lib/stores/keyboard.svelte';
  import { formatShortcutDisplay } from '$lib/utils/keyboard';
  import type { KeyboardShortcut } from '$lib/stores/keyboard.svelte';

  let searchQuery = $state('');
  let searchInputRef = $state<HTMLInputElement | null>(null);

  // Deduplicate shortcuts: hide the "?" variant since Cmd+/ already covers it
  const HIDDEN_IDS = new Set(['shortcuts-overlay-qmark']);

  /** All shortcuts visible in the overlay, optionally filtered by search. */
  let visibleShortcuts = $derived.by(() => {
    const all = keyboardStore.activeShortcuts.filter(
      (s) => !HIDDEN_IDS.has(s.id),
    );
    if (!searchQuery.trim()) return all;
    const q = searchQuery.toLowerCase();
    return all.filter(
      (s) =>
        s.description.toLowerCase().includes(q) ||
        s.category.toLowerCase().includes(q) ||
        s.key.toLowerCase().includes(q) ||
        s.id.toLowerCase().includes(q),
    );
  });

  /** Shortcuts grouped by category in the predefined display order. */
  let groupedShortcuts = $derived.by(() => {
    const groups: Array<{
      id: string;
      label: string;
      icon: string;
      shortcuts: KeyboardShortcut[];
    }> = [];

    for (const cat of SHORTCUT_CATEGORIES) {
      const items = visibleShortcuts.filter((s) => s.category === cat.id);
      if (items.length > 0) {
        groups.push({ ...cat, shortcuts: items });
      }
    }

    // Catch any uncategorized shortcuts
    const knownCats = new Set(SHORTCUT_CATEGORIES.map((c) => c.id));
    const uncategorized = visibleShortcuts.filter(
      (s) => !knownCats.has(s.category),
    );
    if (uncategorized.length > 0) {
      groups.push({
        id: 'Other',
        label: 'Other',
        icon: '...',
        shortcuts: uncategorized,
      });
    }

    return groups;
  });

  /** Total visible count for the header. */
  let totalCount = $derived(visibleShortcuts.length);

  // Focus search input when overlay opens
  $effect(() => {
    if (keyboardStore.paletteOpen) {
      searchQuery = '';
      requestAnimationFrame(() => {
        searchInputRef?.focus();
      });
    }
  });

  function handleBackdropClick(): void {
    keyboardStore.closePalette();
  }

  function handleOverlayKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      keyboardStore.closePalette();
    }
  }

  /**
   * Render a key combo as an array of display tokens for individual <kbd>
   * elements. For example, ["⌘", "K"] or ["Ctrl", "Shift", "C"].
   */
  function getKeyTokens(shortcut: KeyboardShortcut): string[] {
    const display = formatShortcutDisplay(shortcut.key, shortcut.modifiers);

    // On Mac, symbols are concatenated — split each character
    // On Windows, they're joined with "+" — split on "+"
    const isMac =
      typeof navigator !== 'undefined' &&
      /Mac|iPod|iPhone|iPad/.test(navigator.platform);

    if (isMac) {
      // Split modifier symbols from the key portion
      const modSymbols = ['⌃', '⌘', '⌥', '⇧'];
      const tokens: string[] = [];
      let remaining = display;
      for (const sym of modSymbols) {
        if (remaining.startsWith(sym)) {
          tokens.push(sym);
          remaining = remaining.slice(sym.length);
        }
      }
      if (remaining) tokens.push(remaining);
      return tokens;
    }

    return display.split('+');
  }
</script>

{#if keyboardStore.paletteOpen}
  <!-- Backdrop -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="shortcut-overlay__backdrop"
    onclick={handleBackdropClick}
    onkeydown={handleOverlayKeydown}
  ></div>

  <!-- Overlay modal -->
  <div
    class="shortcut-overlay"
    role="dialog"
    aria-label="Keyboard shortcuts"
    aria-modal="true"
    onkeydown={handleOverlayKeydown}
  >
    <!-- Header -->
    <div class="shortcut-overlay__header">
      <div class="shortcut-overlay__title-row">
        <h2 class="shortcut-overlay__title">Keyboard Shortcuts</h2>
        <span class="shortcut-overlay__count">{totalCount} shortcuts</span>
      </div>
      <div class="shortcut-overlay__search-wrapper">
        <span class="shortcut-overlay__search-icon" aria-hidden="true">⌕</span>
        <input
          bind:this={searchInputRef}
          bind:value={searchQuery}
          class="shortcut-overlay__search"
          type="text"
          placeholder="Filter shortcuts..."
          autocomplete="off"
          spellcheck="false"
        />
        <button
          class="shortcut-overlay__close-btn"
          onclick={() => keyboardStore.closePalette()}
          aria-label="Close shortcuts overlay"
        >
          <kbd class="shortcut-overlay__esc-badge">Esc</kbd>
        </button>
      </div>
    </div>

    <!-- Shortcut list -->
    <div class="shortcut-overlay__body">
      {#if groupedShortcuts.length === 0}
        <div class="shortcut-overlay__empty">
          No shortcuts matching "{searchQuery}"
        </div>
      {:else}
        <div class="shortcut-overlay__grid">
          {#each groupedShortcuts as group (group.id)}
            <div class="shortcut-overlay__category">
              <div class="shortcut-overlay__category-header">
                <span class="shortcut-overlay__category-icon">{group.icon}</span>
                <span class="shortcut-overlay__category-label">{group.label}</span>
                <span class="shortcut-overlay__category-count">{group.shortcuts.length}</span>
              </div>
              <div class="shortcut-overlay__category-list">
                {#each group.shortcuts as shortcut (shortcut.id)}
                  <div class="shortcut-overlay__item">
                    <span class="shortcut-overlay__item-desc">{shortcut.description}</span>
                    <div class="shortcut-overlay__item-keys">
                      {#each getKeyTokens(shortcut) as token (token)}
                        <kbd class="shortcut-overlay__kbd">{token}</kbd>
                      {/each}
                    </div>
                  </div>
                {/each}
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </div>

    <!-- Footer -->
    <div class="shortcut-overlay__footer">
      <span class="shortcut-overlay__footer-hint">
        Press <kbd>Esc</kbd> to close
      </span>
      <span class="shortcut-overlay__footer-hint">
        <kbd>⌘</kbd><kbd>/</kbd> to toggle
      </span>
    </div>
  </div>
{/if}

<style>
  /* ================================================================
     Backdrop
     ================================================================ */
  .shortcut-overlay__backdrop {
    position: fixed;
    inset: 0;
    background-color: oklch(0.04 0.02 260 / 0.78);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    z-index: var(--z-modal);
    animation: overlay-backdrop-in 200ms var(--ease-out-expo) forwards;
  }

  @keyframes overlay-backdrop-in {
    from { opacity: 0; }
    to   { opacity: 1; }
  }

  /* ================================================================
     Modal container
     ================================================================ */
  .shortcut-overlay {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 94vw;
    max-width: 720px;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    background-color: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-xl);
    box-shadow:
      var(--glow-xl),
      0 0 0 1px oklch(0.62 0.20 290 / 0.08),
      0 24px 80px -12px oklch(0 0 0 / 0.5);
    z-index: calc(var(--z-modal) + 1);
    overflow: hidden;
    animation: overlay-enter 250ms var(--ease-out-expo) forwards;
  }

  @keyframes overlay-enter {
    from {
      opacity: 0;
      transform: translate(-50%, -50%) scale(0.95) translateY(12px);
    }
    to {
      opacity: 1;
      transform: translate(-50%, -50%) scale(1) translateY(0);
    }
  }

  /* ================================================================
     Header
     ================================================================ */
  .shortcut-overlay__header {
    padding: 20px 24px 16px;
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
  }

  .shortcut-overlay__title-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 14px;
  }

  .shortcut-overlay__title {
    font-family: var(--font-display);
    font-size: var(--text-lg);
    font-weight: 600;
    color: var(--text-primary);
    letter-spacing: -0.01em;
  }

  .shortcut-overlay__count {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    color: var(--text-disabled);
    letter-spacing: 0.02em;
  }

  .shortcut-overlay__search-wrapper {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background-color: var(--bg-base);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-DEFAULT);
    transition: border-color 150ms ease;
  }

  .shortcut-overlay__search-wrapper:focus-within {
    border-color: var(--accent-dim);
    box-shadow: 0 0 0 2px oklch(0.62 0.20 290 / 0.12);
  }

  .shortcut-overlay__search-icon {
    font-size: var(--text-sm);
    color: var(--text-disabled);
    flex-shrink: 0;
    line-height: 1;
  }

  .shortcut-overlay__search {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    font-family: var(--font-body);
    font-size: var(--text-sm);
    color: var(--text-primary);
    caret-color: var(--accent-bright);
  }

  .shortcut-overlay__search::placeholder {
    color: var(--text-disabled);
  }

  .shortcut-overlay__close-btn {
    flex-shrink: 0;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    line-height: 1;
  }

  .shortcut-overlay__esc-badge {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    color: var(--text-disabled);
    padding: 3px 7px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-xs);
    background: var(--bg-surface);
    transition: all 120ms ease;
  }

  .shortcut-overlay__close-btn:hover .shortcut-overlay__esc-badge {
    border-color: var(--border-default);
    color: var(--text-secondary);
  }

  /* ================================================================
     Body / shortcut list
     ================================================================ */
  .shortcut-overlay__body {
    flex: 1;
    overflow-y: auto;
    padding: 16px 24px 20px;
  }

  .shortcut-overlay__empty {
    padding: 40px 0;
    text-align: center;
    color: var(--text-disabled);
    font-size: var(--text-sm);
  }

  .shortcut-overlay__grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 24px;
  }

  /* ================================================================
     Category
     ================================================================ */
  .shortcut-overlay__category {
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .shortcut-overlay__category-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding-bottom: 10px;
    margin-bottom: 2px;
    border-bottom: 1px solid var(--border-subtle);
  }

  .shortcut-overlay__category-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border-radius: var(--radius-sm);
    background-color: var(--accent-bg);
    color: var(--accent-bright);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: 600;
    flex-shrink: 0;
  }

  .shortcut-overlay__category-label {
    font-family: var(--font-display);
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-secondary);
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .shortcut-overlay__category-count {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    color: var(--text-disabled);
    margin-left: auto;
  }

  .shortcut-overlay__category-list {
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  /* ================================================================
     Shortcut item
     ================================================================ */
  .shortcut-overlay__item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 7px 4px;
    border-radius: var(--radius-sm);
    transition: background-color 80ms ease;
  }

  .shortcut-overlay__item:hover {
    background-color: var(--hover-overlay);
  }

  .shortcut-overlay__item-desc {
    font-size: var(--text-sm);
    color: var(--text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
    min-width: 0;
  }

  .shortcut-overlay__item:hover .shortcut-overlay__item-desc {
    color: var(--text-primary);
  }

  .shortcut-overlay__item-keys {
    display: flex;
    align-items: center;
    gap: 3px;
    flex-shrink: 0;
  }

  /* ================================================================
     Kbd badges
     ================================================================ */
  .shortcut-overlay__kbd {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 24px;
    height: 24px;
    padding: 0 6px;
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: 500;
    color: var(--text-secondary);
    background: linear-gradient(
      180deg,
      oklch(0.20 0.02 260) 0%,
      oklch(0.15 0.02 260) 100%
    );
    border: 1px solid var(--border-default);
    border-bottom-width: 2px;
    border-radius: var(--radius-sm);
    box-shadow:
      0 1px 2px oklch(0 0 0 / 0.2),
      inset 0 1px 0 oklch(1 0 0 / 0.04);
    line-height: 1;
    white-space: nowrap;
  }

  .shortcut-overlay__item:hover .shortcut-overlay__kbd {
    color: var(--text-primary);
    border-color: var(--accent-dim);
    box-shadow:
      0 1px 3px oklch(0.62 0.20 290 / 0.12),
      inset 0 1px 0 oklch(1 0 0 / 0.05);
  }

  /* ================================================================
     Footer
     ================================================================ */
  .shortcut-overlay__footer {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 24px;
    padding: 10px 24px;
    border-top: 1px solid var(--border-subtle);
    background-color: var(--bg-base);
    flex-shrink: 0;
  }

  .shortcut-overlay__footer-hint {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: var(--text-2xs);
    color: var(--text-disabled);
  }

  .shortcut-overlay__footer-hint kbd {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    padding: 1px 5px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-xs);
    background: var(--bg-surface);
    color: var(--text-tertiary);
  }

  /* ================================================================
     Responsive
     ================================================================ */
  @media (max-width: 640px) {
    .shortcut-overlay {
      width: 100vw;
      max-width: none;
      max-height: 100vh;
      border-radius: 0;
      top: 0;
      left: 0;
      transform: none;
    }

    @keyframes overlay-enter {
      from {
        opacity: 0;
        transform: translateY(20px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    .shortcut-overlay__grid {
      grid-template-columns: 1fr;
    }
  }
</style>
