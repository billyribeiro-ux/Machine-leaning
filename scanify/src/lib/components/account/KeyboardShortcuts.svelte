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
        { keys: ['\u2190'],    description: 'Pan Left' },
        { keys: ['\u2192'],    description: 'Pan Right' },
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

<div class="flex flex-col gap-6">
  <!-- Section header -->
  <div class="flex flex-col gap-1">
    <h2 class="text-lg font-semibold text-[oklch(0.90_0_0)]">Keyboard Shortcuts</h2>
    <p class="text-sm text-[oklch(0.55_0_0)]">Quick reference for all available keybindings</p>
  </div>

  <!-- Search filter -->
  <div class="relative">
    <svg
      xmlns="http://www.w3.org/2000/svg"
      class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[oklch(0.45_0_0)] pointer-events-none"
      viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
    >
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
    <input
      type="text"
      bind:value={searchQuery}
      placeholder="Search shortcuts..."
      class="
        w-full rounded-lg border border-[oklch(0.24_0_0)]
        bg-[oklch(0.12_0_0)] pl-10 pr-4 py-2.5
        text-sm text-[oklch(0.88_0_0)]
        placeholder-[oklch(0.40_0_0)]
        outline-none transition-all duration-150
        focus:border-[oklch(0.45_0.12_250)]
        focus:ring-2 focus:ring-[oklch(0.45_0.12_250/0.3)]
      "
    />
    {#if searchQuery.trim().length > 0}
      <span class="absolute right-3 top-1/2 -translate-y-1/2 text-[11px] text-[oklch(0.45_0_0)]">
        {totalShortcuts} result{totalShortcuts !== 1 ? 's' : ''}
      </span>
    {/if}
  </div>

  <!-- Shortcut groups in two-column layout -->
  {#if filteredGroups.length === 0}
    <div class="flex items-center justify-center py-12 text-sm text-[oklch(0.45_0_0)]">
      No shortcuts match "{searchQuery}"
    </div>
  {:else}
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {#each filteredGroups as group (group.category)}
        <div class="flex flex-col gap-2">
          <!-- Category header -->
          <h3 class="text-xs font-semibold uppercase tracking-wider text-[oklch(0.55_0_0)] pb-1 border-b border-[oklch(0.20_0_0)]">
            {group.category}
          </h3>

          <!-- Shortcut rows -->
          <div class="flex flex-col">
            {#each group.shortcuts as shortcut (shortcut.description)}
              <div class="flex items-center justify-between py-2 px-2 rounded-md hover:bg-[oklch(0.15_0_0)] transition-colors duration-100">
                <!-- Description -->
                <span class="text-xs text-[oklch(0.75_0_0)]">
                  {shortcut.description}
                </span>

                <!-- Kbd keys -->
                <div class="flex items-center gap-1 shrink-0 ml-4">
                  {#each shortcut.keys as key, ki}
                    {#if ki > 0 && key !== '-'}
                      <span class="text-[10px] text-[oklch(0.35_0_0)]">+</span>
                    {/if}
                    {#if key === '-' && shortcut.keys.length === 3}
                      <span class="text-[10px] text-[oklch(0.35_0_0)]">{key}</span>
                    {:else}
                      <kbd
                        class="
                          inline-flex items-center justify-center
                          min-w-[22px] h-[22px] px-1.5
                          rounded border border-[oklch(0.28_0_0)]
                          bg-[oklch(0.16_0_0)]
                          text-[11px] font-mono font-medium text-[oklch(0.70_0_0)]
                          shadow-[0_1px_0_oklch(0.10_0_0)]
                        "
                      >
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
