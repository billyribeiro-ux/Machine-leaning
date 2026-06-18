<!--
  CommandBar.svelte
  Command palette overlay (Cmd+K / Ctrl+K).
  Fuzzy search with keyboard navigation, categories, and mock data.
-->
<script lang="ts">
  import { exportData } from '$lib/utils/export';

  type CommandCategory = 'navigation' | 'scans' | 'symbols' | 'actions' | 'settings';

  interface CommandItem {
    /** Unique identifier. */
    id: string;
    /** Display label. */
    label: string;
    /** Short description. */
    description: string;
    /** Category for grouping. */
    category: CommandCategory;
    /** Icon placeholder text. */
    icon: string;
    /** Keyboard shortcut display string. */
    shortcut?: string;
    /** Action to run on selection. */
    action?: () => void;
  }

  interface CommandBarProps {
    /** Whether the command bar is open (bindable). */
    open: boolean;
    /** Callback when a command is executed. */
    onexecute?: (command: CommandItem) => void;
    /** Additional CSS classes. */
    class?: string;
  }

  let {
    open = $bindable(false),
    onexecute,
    class: className = '',
  }: CommandBarProps = $props();

  // ---- Internal state ----
  let query = $state('');
  let selectedIndex = $state(0);
  let inputRef = $state<HTMLInputElement | null>(null);

  // ---- Mock command data ----
  const commands: CommandItem[] = [
    // Navigation
    { id: 'nav-scanner',       label: 'Scanner',              description: 'Open the stock scanner',          category: 'navigation', icon: 'S',  shortcut: '1' },
    { id: 'nav-dashboard',     label: 'Dashboard',            description: 'Open the dashboard view',         category: 'navigation', icon: 'D',  shortcut: '2' },
    { id: 'nav-options',       label: 'Options Flow',         description: 'View options flow and chains',    category: 'navigation', icon: 'O',  shortcut: '3' },
    { id: 'nav-market',        label: 'Market Overview',      description: 'Market internals and breadth',    category: 'navigation', icon: 'M',  shortcut: '4' },
    { id: 'nav-institutional', label: 'Institutional Flow',   description: 'Dark pool and block trades',      category: 'navigation', icon: 'I',  shortcut: '5' },
    { id: 'nav-analysis',      label: 'Analysis',             description: 'Technical analysis workspace',    category: 'navigation', icon: 'A',  shortcut: '6' },
    // Scans
    { id: 'scan-momentum',     label: 'Momentum Scan',        description: 'Stocks with strong momentum',     category: 'scans',      icon: '>>' },
    { id: 'scan-volume',       label: 'Volume Surge Scan',    description: 'Unusual volume activity',         category: 'scans',      icon: 'V+' },
    { id: 'scan-breakout',     label: 'Breakout Scan',        description: 'Stocks breaking key levels',      category: 'scans',      icon: '/\\' },
    { id: 'scan-gapper',       label: 'Gap Scanner',          description: 'Pre-market gap ups and downs',    category: 'scans',      icon: '||' },
    { id: 'scan-squeeze',      label: 'Squeeze Scan',         description: 'Bollinger Band squeeze setups',   category: 'scans',      icon: '<>' },
    // Symbols
    { id: 'sym-spy',           label: 'SPY',                  description: 'SPDR S&P 500 ETF Trust',          category: 'symbols',    icon: '$' },
    { id: 'sym-qqq',           label: 'QQQ',                  description: 'Invesco QQQ Trust',               category: 'symbols',    icon: '$' },
    { id: 'sym-aapl',          label: 'AAPL',                 description: 'Apple Inc.',                      category: 'symbols',    icon: '$' },
    { id: 'sym-tsla',          label: 'TSLA',                 description: 'Tesla Inc.',                      category: 'symbols',    icon: '$' },
    { id: 'sym-nvda',          label: 'NVDA',                 description: 'NVIDIA Corporation',              category: 'symbols',    icon: '$' },
    // Actions
    { id: 'act-new-scan',      label: 'New Scan',             description: 'Create a custom scan',            category: 'actions',    icon: '+',  shortcut: 'N' },
    { id: 'act-export',        label: 'Export Data',          description: 'Export scan results to CSV',      category: 'actions',    icon: 'Ex', action: () => exportSignals('csv') },
    { id: 'act-clear-alerts',  label: 'Clear All Alerts',     description: 'Dismiss all active alerts',       category: 'actions',    icon: 'X' },
    { id: 'act-refresh',       label: 'Force Refresh',        description: 'Refresh all data connections',    category: 'actions',    icon: 'R',  shortcut: 'Shift+R' },
    // Settings
    { id: 'set-theme',         label: 'Theme Settings',       description: 'Adjust colors and appearance',    category: 'settings',   icon: '#' },
    { id: 'set-layout',        label: 'Layout Settings',      description: 'Configure panel layout',          category: 'settings',   icon: '[]' },
    { id: 'set-alerts',        label: 'Alert Settings',       description: 'Configure alert preferences',     category: 'settings',   icon: '!' },
    { id: 'set-data',          label: 'Data Sources',         description: 'Manage data feed connections',    category: 'settings',   icon: 'db' },
    { id: 'set-keybinds',      label: 'Keyboard Shortcuts',   description: 'View and customize keybindings',  category: 'settings',   icon: 'kb', shortcut: '?' },
  ];

  function exportSignals(format: 'csv' | 'json' | 'pdf'): void {
    exportData(format, 'scanner').catch((err) => {
      console.error('Export error:', err);
    });
  }

  const recentIds = ['nav-scanner', 'scan-momentum', 'sym-spy', 'act-new-scan'];

  const categoryLabels: Record<CommandCategory, string> = {
    navigation: 'Navigation',
    scans: 'Scans',
    symbols: 'Symbols',
    actions: 'Actions',
    settings: 'Settings',
  };

  const categoryOrder: CommandCategory[] = ['navigation', 'scans', 'symbols', 'actions', 'settings'];

  // ---- Fuzzy search ----
  function fuzzyMatch(text: string, pattern: string): boolean {
    const lowerText = text.toLowerCase();
    const lowerPattern = pattern.toLowerCase();
    let pi = 0;
    for (let ti = 0; ti < lowerText.length && pi < lowerPattern.length; ti++) {
      if (lowerText[ti] === lowerPattern[pi]) {
        pi++;
      }
    }
    return pi === lowerPattern.length;
  }

  // ---- Derived: filtered results ----
  let filteredResults = $derived.by(() => {
    if (!query.trim()) {
      // Show recent items when query is empty
      return commands.filter((cmd) => recentIds.includes(cmd.id));
    }
    return commands.filter(
      (cmd) =>
        fuzzyMatch(cmd.label, query) ||
        fuzzyMatch(cmd.description, query) ||
        fuzzyMatch(cmd.category, query)
    );
  });

  // ---- Derived: grouped results (for display) ----
  let groupedResults = $derived.by(() => {
    const results = filteredResults;
    const groups: { category: CommandCategory; label: string; items: CommandItem[] }[] = [];

    for (const cat of categoryOrder) {
      const items = results.filter((cmd) => cmd.category === cat);
      if (items.length > 0) {
        groups.push({
          category: cat,
          label: categoryLabels[cat],
          items,
        });
      }
    }
    return groups;
  });

  // ---- Derived: flat list for keyboard navigation index ----
  let flatResults = $derived.by(() => {
    return groupedResults.flatMap((g) => g.items);
  });

  // ---- Reset state when opened/closed ----
  $effect(() => {
    if (open) {
      query = '';
      selectedIndex = 0;
      // Focus input on next tick
      requestAnimationFrame(() => {
        inputRef?.focus();
      });
    }
  });

  // Clamp selectedIndex when results change
  $effect(() => {
    const results = flatResults;
    if (selectedIndex >= results.length) {
      selectedIndex = Math.max(0, results.length - 1);
    }
  });

  // NOTE: The global Cmd+K shortcut is now registered in the app layout via
  // the keyboard store. This component only handles its own internal navigation.

  // ---- Command bar keyboard navigation ----
  function handleKeydown(e: KeyboardEvent): void {
    const results = flatResults;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        selectedIndex = (selectedIndex + 1) % Math.max(results.length, 1);
        scrollSelectedIntoView();
        break;
      case 'ArrowUp':
        e.preventDefault();
        selectedIndex = (selectedIndex - 1 + results.length) % Math.max(results.length, 1);
        scrollSelectedIntoView();
        break;
      case 'Enter':
        e.preventDefault();
        if (results[selectedIndex]) {
          executeCommand(results[selectedIndex]);
        }
        break;
      case 'Escape':
        e.preventDefault();
        open = false;
        break;
    }
  }

  function executeCommand(cmd: CommandItem): void {
    cmd.action?.();
    onexecute?.(cmd);
    open = false;
  }

  function scrollSelectedIntoView(): void {
    requestAnimationFrame(() => {
      const el = document.querySelector(`[data-command-index="${selectedIndex}"]`);
      el?.scrollIntoView({ block: 'nearest' });
    });
  }

  function handleBackdropClick(): void {
    open = false;
  }

  // Track flat index for each item across groups
  function getFlatIndex(category: CommandCategory, itemIndex: number): number {
    const groups = groupedResults;
    let offset = 0;
    for (const g of groups) {
      if (g.category === category) {
        return offset + itemIndex;
      }
      offset += g.items.length;
    }
    return 0;
  }
</script>

{#if open}
  <!-- Backdrop -->
  <div
    class="command-bar__backdrop"
    onclick={handleBackdropClick}
    onkeydown={(e) => { if (e.key === 'Escape') open = false; }}
    role="presentation"
  ></div>

  <!-- Command palette modal -->
  <div
    class="command-bar {className}"
    role="dialog"
    aria-label="Command palette"
    aria-modal="true"
  >
    <!-- Search input -->
    <div class="command-bar__input-wrapper">
      <!-- Magnifying glass placeholder -->
      <span class="command-bar__search-icon" aria-hidden="true">
        {'\u2315'}
      </span>
      <input
        bind:this={inputRef}
        bind:value={query}
        onkeydown={handleKeydown}
        class="command-bar__input"
        type="text"
        placeholder="Type a command or search..."
        autocomplete="off"
        spellcheck="false"
      />
      <kbd class="command-bar__escape-hint">Esc</kbd>
    </div>

    <!-- Results -->
    <div class="command-bar__results">
      {#if flatResults.length === 0}
        <div class="command-bar__empty">
          No results found for "{query}"
        </div>
      {:else}
        {#if !query.trim()}
          <div class="command-bar__section-label">Recent</div>
        {/if}
        {#each groupedResults as group (group.category)}
          {#if query.trim()}
            <div class="command-bar__section-label">{group.label}</div>
          {/if}
          {#each group.items as item, i (item.id)}
            {@const flatIdx = getFlatIndex(group.category, i)}
            {@const isSelected = flatIdx === selectedIndex}
            <button
              class="command-bar__item"
              class:command-bar__item--selected={isSelected}
              data-command-index={flatIdx}
              onclick={() => executeCommand(item)}
              onmouseenter={() => { selectedIndex = flatIdx; }}
              role="option"
              aria-selected={isSelected}
            >
              <span class="command-bar__item-icon">{item.icon}</span>
              <div class="command-bar__item-text">
                <span class="command-bar__item-label">{item.label}</span>
                <span class="command-bar__item-desc">{item.description}</span>
              </div>
              {#if item.shortcut}
                <kbd class="command-bar__item-shortcut">{item.shortcut}</kbd>
              {/if}
            </button>
          {/each}
        {/each}
      {/if}
    </div>

    <!-- Footer hint -->
    <div class="command-bar__footer">
      <span class="command-bar__hint">
        <kbd>Up</kbd><kbd>Down</kbd> navigate
      </span>
      <span class="command-bar__hint">
        <kbd>Enter</kbd> select
      </span>
      <span class="command-bar__hint">
        <kbd>Esc</kbd> close
      </span>
    </div>
  </div>
{/if}

<style>
  /* ---- Backdrop ---- */
  .command-bar__backdrop {
    position: fixed;
    inset: 0;
    background-color: oklch(0 0 0 / 0.60);
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
    z-index: var(--z-modal);
  }

  /* ---- Modal container ---- */
  .command-bar {
    position: fixed;
    top: 20%;
    left: 50%;
    transform: translateX(-50%);
    width: 100%;
    max-width: 640px;
    max-height: 480px;
    display: flex;
    flex-direction: column;
    background-color: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-xl);
    box-shadow: var(--glow-lg);
    z-index: calc(var(--z-modal) + 1);
    overflow: hidden;
    animation: command-bar-enter 150ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
  }

  @keyframes command-bar-enter {
    from {
      opacity: 0;
      transform: translateX(-50%) scale(0.96) translateY(-8px);
    }
    to {
      opacity: 1;
      transform: translateX(-50%) scale(1) translateY(0);
    }
  }

  /* ---- Input area ---- */
  .command-bar__input-wrapper {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-subtle);
  }

  .command-bar__search-icon {
    font-size: var(--text-lg);
    color: var(--text-tertiary);
    flex-shrink: 0;
    line-height: 1;
  }

  .command-bar__input {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    font-family: var(--font-body);
    font-size: var(--text-base);
    color: var(--text-primary);
    caret-color: var(--accent-bright);
  }

  .command-bar__input::placeholder {
    color: var(--text-disabled);
  }

  .command-bar__escape-hint {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    color: var(--text-disabled);
    padding: 2px 6px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-xs);
    background: var(--bg-base);
    flex-shrink: 0;
  }

  /* ---- Results list ---- */
  .command-bar__results {
    flex: 1;
    overflow-y: auto;
    padding: 4px 0;
  }

  .command-bar__section-label {
    padding: 8px 16px 4px;
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: 600;
    color: var(--text-disabled);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .command-bar__empty {
    padding: 24px 16px;
    text-align: center;
    color: var(--text-disabled);
    font-size: var(--text-sm);
  }

  /* ---- Result item ---- */
  .command-bar__item {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    padding: 8px 16px;
    border: none;
    background: transparent;
    cursor: pointer;
    text-align: left;
    transition: background-color 80ms ease;
  }

  .command-bar__item:hover,
  .command-bar__item--selected {
    background-color: var(--hover-overlay);
  }

  .command-bar__item--selected {
    background-color: var(--accent-bg);
  }

  .command-bar__item-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: var(--radius-sm);
    background-color: var(--bg-elevated);
    color: var(--text-secondary);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    font-weight: 600;
    flex-shrink: 0;
  }

  .command-bar__item--selected .command-bar__item-icon {
    background-color: var(--accent-dim);
    color: var(--accent-bright);
  }

  .command-bar__item-text {
    display: flex;
    flex-direction: column;
    gap: 1px;
    flex: 1;
    min-width: 0;
  }

  .command-bar__item-label {
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .command-bar__item-desc {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .command-bar__item-shortcut {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    color: var(--text-disabled);
    padding: 2px 6px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-xs);
    background: var(--bg-base);
    flex-shrink: 0;
  }

  .command-bar__item--selected .command-bar__item-shortcut {
    border-color: var(--accent-dim);
  }

  /* ---- Footer ---- */
  .command-bar__footer {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 8px 16px;
    border-top: 1px solid var(--border-subtle);
    background-color: var(--bg-base);
  }

  .command-bar__hint {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: var(--text-2xs);
    color: var(--text-disabled);
  }

  .command-bar__hint kbd {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    padding: 1px 4px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-xs);
    background: var(--bg-surface);
    color: var(--text-tertiary);
  }
</style>
