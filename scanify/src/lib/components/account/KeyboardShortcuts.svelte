<!--
  KeyboardShortcuts.svelte
  Displays all keyboard shortcuts grouped by category.
  Two-column layout with a search filter at top.
  Each shortcut renders description + Kbd-styled key(s).
-->
<script lang="ts">
  interface Shortcut {
    keys: string[];
    description: string;
  }

  interface ShortcutGroup {
    category: string;
    shortcuts: Shortcut[];
  }

  let searchQuery = $state('');

  const shortcutGroups: ShortcutGroup[] = [
    {
      category: 'Global',
      shortcuts: [
        { keys: ['Cmd', 'K'],     description: 'Open Command Palette' },
        { keys: ['Cmd', '/'],     description: 'Toggle Keyboard Shortcuts' },
        { keys: ['1', '-', '9'],  description: 'Switch Layout Presets' },
        { keys: ['Esc'],          description: 'Close Panel / Dialog' },
        { keys: ['Space'],        description: 'Pause / Resume Scan' },
      ],
    },
    {
      category: 'Scanner',
      shortcuts: [
        { keys: ['j'],     description: 'Navigate Down' },
        { keys: ['k'],     description: 'Navigate Up' },
        { keys: ['Enter'], description: 'Expand Selected Row' },
        { keys: ['f'],     description: 'Open Filter Panel' },
        { keys: ['s'],     description: 'Toggle Sort Column' },
        { keys: ['r'],     description: 'Refresh Data' },
        { keys: ['a'],     description: 'Add to Watchlist' },
      ],
    },
    {
      category: 'Charts',
      shortcuts: [
        { keys: ['+'],         description: 'Zoom In' },
        { keys: ['-'],         description: 'Zoom Out' },
        { keys: ['←'],    description: 'Pan Left' },
        { keys: ['→'],    description: 'Pan Right' },
        { keys: ['d'],         description: 'Toggle Drawing Tools' },
        { keys: ['c'],         description: 'Toggle Crosshair' },
        { keys: ['t'],         description: 'Change Timeframe' },
      ],
    },
  ];

  /** Filtered groups based on search query. */
  let filteredGroups = $derived<ShortcutGroup[]>(
    searchQuery.trim().length === 0
      ? shortcutGroups
      : shortcutGroups
          .map((group) => ({
            ...group,
            shortcuts: group.shortcuts.filter((s) =>
              s.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
              s.keys.some((k) => k.toLowerCase().includes(searchQuery.toLowerCase()))
            ),
          }))
          .filter((group) => group.shortcuts.length > 0)
  );

  /** Total matched shortcuts count. */
  let totalShortcuts = $derived(
    filteredGroups.reduce((sum, g) => sum + g.shortcuts.length, 0)
  );
</script>

<div class="wrapper">
  <!-- Section header -->
  <div class="section-header">
    <h2 class="title">Keyboard Shortcuts</h2>
    <p class="subtitle">Quick reference for all available keybindings</p>
  </div>

  <!-- Search filter -->
  <div class="search-wrapper">
    <svg
      xmlns="http://www.w3.org/2000/svg"
      class="search-icon"
      viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
    >
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
    <input
      type="text"
      bind:value={searchQuery}
      placeholder="Search shortcuts..."
      class="search-input"
    />
    {#if searchQuery.trim().length > 0}
      <span class="result-count">
        {totalShortcuts} result{totalShortcuts !== 1 ? 's' : ''}
      </span>
    {/if}
  </div>

  <!-- Shortcut groups in two-column layout -->
  {#if filteredGroups.length === 0}
    <div class="empty-state">
      No shortcuts match "{searchQuery}"
    </div>
  {:else}
    <div class="groups-grid">
      {#each filteredGroups as group (group.category)}
        <div class="group">
          <!-- Category header -->
          <h3 class="category-header">
            {group.category}
          </h3>

          <!-- Shortcut rows -->
          <div class="shortcut-list">
            {#each group.shortcuts as shortcut (shortcut.description)}
              <div class="shortcut-row">
                <!-- Description -->
                <span class="shortcut-description">
                  {shortcut.description}
                </span>

                <!-- Kbd keys -->
                <div class="keys-group">
                  {#each shortcut.keys as key, ki}
                    {#if ki > 0 && key !== '-'}
                      <span class="key-separator">+</span>
                    {/if}
                    {#if key === '-' && shortcut.keys.length === 3}
                      <span class="key-separator">{key}</span>
                    {:else}
                      <kbd class="kbd">
                        {key}
                      </kbd>
                    {/if}
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

<style>
  .wrapper {
    display: flex;
    flex-direction: column;
    gap: 24px;
  }

  .section-header {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .title {
    font-size: 1.125rem;
    font-weight: 600;
    color: oklch(0.90 0 0);
  }

  .subtitle {
    font-size: 0.875rem;
    color: oklch(0.55 0 0);
  }

  .search-wrapper {
    position: relative;
  }

  .search-icon {
    position: absolute;
    left: 12px;
    top: 50%;
    transform: translateY(-50%);
    width: 16px;
    height: 16px;
    color: oklch(0.45 0 0);
    pointer-events: none;
  }

  .search-input {
    width: 100%;
    border-radius: var(--radius-lg);
    border: 1px solid oklch(0.24 0 0);
    background-color: oklch(0.12 0 0);
    padding: 10px 16px 10px 40px;
    font-size: 0.875rem;
    color: oklch(0.88 0 0);
    outline: none;
    transition: all 150ms;
  }

  .search-input::placeholder {
    color: oklch(0.40 0 0);
  }

  .search-input:focus {
    border-color: oklch(0.45 0.12 250);
    box-shadow: 0 0 0 2px oklch(0.45 0.12 250 / 0.3);
  }

  .result-count {
    position: absolute;
    right: 12px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 11px;
    color: oklch(0.45 0 0);
  }

  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 48px 0;
    font-size: 0.875rem;
    color: oklch(0.45 0 0);
  }

  .groups-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 24px;
  }

  @media (min-width: 1024px) {
    .groups-grid {
      grid-template-columns: 1fr 1fr;
    }
  }

  .group {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .category-header {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: oklch(0.55 0 0);
    padding-bottom: 4px;
    border-bottom: 1px solid oklch(0.20 0 0);
  }

  .shortcut-list {
    display: flex;
    flex-direction: column;
  }

  .shortcut-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px;
    border-radius: var(--radius-md);
    transition: background-color 100ms;
  }

  .shortcut-row:hover {
    background-color: oklch(0.15 0 0);
  }

  .shortcut-description {
    font-size: 0.75rem;
    color: oklch(0.75 0 0);
  }

  .keys-group {
    display: flex;
    align-items: center;
    gap: 4px;
    flex-shrink: 0;
    margin-left: 16px;
  }

  .key-separator {
    font-size: 10px;
    color: oklch(0.35 0 0);
  }

  .kbd {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 22px;
    height: 22px;
    padding: 0 6px;
    border-radius: var(--radius-md);
    border: 1px solid oklch(0.28 0 0);
    background-color: oklch(0.16 0 0);
    font-size: 11px;
    font-family: monospace;
    font-weight: 500;
    color: oklch(0.70 0 0);
    box-shadow: 0 1px 0 oklch(0.10 0 0);
  }
</style>
