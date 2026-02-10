<!--
  LayoutPresets.svelte
  Dropdown button to switch between predefined layout presets.
  Closes on outside click.
-->
<script lang="ts">
  interface PresetOption {
    id: string;
    label: string;
    description: string;
  }

  interface LayoutPresetsProps {
    /** Currently active preset identifier (bindable). */
    activePreset: string;
    /** Additional CSS classes. */
    class?: string;
  }

  let {
    activePreset = $bindable('scanner'),
    class: className = '',
  }: LayoutPresetsProps = $props();

  let isOpen = $state(false);
  let containerEl = $state<HTMLDivElement | null>(null);

  const presets: PresetOption[] = [
    { id: 'scanner',   label: 'Scanner View',  description: 'Full scanner with filters and results' },
    { id: 'analysis',  label: 'Analysis View',  description: 'Charts and technical analysis tools' },
    { id: 'flow',      label: 'Flow View',      description: 'Options flow and dark pool data' },
    { id: 'chart',     label: 'Full Chart',     description: 'Maximized charting workspace' },
    { id: 'dashboard', label: 'Dashboard',      description: 'Overview with market internals' },
  ];

  let activeLabel = $derived(
    presets.find(p => p.id === activePreset)?.label ?? 'Select Layout'
  );

  function toggleDropdown(): void {
    isOpen = !isOpen;
  }

  function selectPreset(id: string): void {
    activePreset = id;
    isOpen = false;
  }

  // Close on outside click
  $effect(() => {
    if (!isOpen) return;

    function handleClickOutside(e: MouseEvent): void {
      if (containerEl && !containerEl.contains(e.target as Node)) {
        isOpen = false;
      }
    }

    // Delay so the opening click doesn't immediately close
    requestAnimationFrame(() => {
      document.addEventListener('click', handleClickOutside);
    });

    return () => document.removeEventListener('click', handleClickOutside);
  });
</script>

<div bind:this={containerEl} class="relative inline-block {className}">
  <!-- Trigger button -->
  <button
    class="
      flex items-center gap-2 px-3 py-1.5
      rounded-lg border border-[oklch(0.24_0_0)]
      bg-[oklch(0.14_0_0)] hover:bg-[oklch(0.17_0_0)]
      text-xs font-medium text-[oklch(0.80_0_0)]
      transition-colors duration-150 cursor-pointer
    "
    onclick={toggleDropdown}
    aria-haspopup="listbox"
    aria-expanded={isOpen}
  >
    <!-- Grid icon -->
    <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-[oklch(0.55_0_0)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
    </svg>
    <span>{activeLabel}</span>
    <!-- Chevron -->
    <svg
      xmlns="http://www.w3.org/2000/svg"
      class="w-3 h-3 text-[oklch(0.45_0_0)] transition-transform duration-150 {isOpen ? 'rotate-180' : ''}"
      viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  </button>

  <!-- Dropdown menu -->
  {#if isOpen}
    <div
      class="
        absolute top-full left-0 mt-1 z-50
        w-64 py-1
        rounded-lg border border-[oklch(0.24_0_0)]
        bg-[oklch(0.13_0_0)]
        shadow-[0_8px_32px_oklch(0_0_0/0.5)]
      "
      role="listbox"
      aria-label="Layout presets"
    >
      {#each presets as preset (preset.id)}
        {@const isActive = activePreset === preset.id}
        <button
          class="
            flex items-center gap-3 w-full px-3 py-2.5 text-left
            transition-colors duration-100 cursor-pointer
            {isActive
              ? 'bg-[oklch(0.17_0.02_250)]'
              : 'hover:bg-[oklch(0.16_0_0)]'}
          "
          role="option"
          aria-selected={isActive}
          onclick={() => selectPreset(preset.id)}
        >
          <!-- Checkmark column -->
          <span class="w-4 shrink-0 flex items-center justify-center">
            {#if isActive}
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-[oklch(0.65_0.15_250)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            {/if}
          </span>

          <!-- Label and description -->
          <div class="flex flex-col gap-0.5 min-w-0">
            <span class="text-xs font-medium {isActive ? 'text-[oklch(0.88_0_0)]' : 'text-[oklch(0.75_0_0)]'}">
              {preset.label}
            </span>
            <span class="text-[11px] text-[oklch(0.45_0_0)] truncate">
              {preset.description}
            </span>
          </div>
        </button>
      {/each}
    </div>
  {/if}
</div>
