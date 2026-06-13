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

<div bind:this={containerEl} class="preset-container {className}">
  <!-- Trigger button -->
  <button
    class="trigger-btn"
    onclick={toggleDropdown}
    aria-haspopup="listbox"
    aria-expanded={isOpen}
  >
    <!-- Grid icon -->
    <svg xmlns="http://www.w3.org/2000/svg" class="grid-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
    </svg>
    <span>{activeLabel}</span>
    <!-- Chevron -->
    <svg
      xmlns="http://www.w3.org/2000/svg"
      class="chevron-icon"
      class:chevron-open={isOpen}
      viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  </button>

  <!-- Dropdown menu -->
  {#if isOpen}
    <div
      class="dropdown-menu"
      role="listbox"
      aria-label="Layout presets"
    >
      {#each presets as preset (preset.id)}
        {@const isActive = activePreset === preset.id}
        <button
          class="preset-option"
          class:active={isActive}
          role="option"
          aria-selected={isActive}
          onclick={() => selectPreset(preset.id)}
        >
          <!-- Checkmark column -->
          <span class="check-column">
            {#if isActive}
              <svg xmlns="http://www.w3.org/2000/svg" class="check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            {/if}
          </span>

          <!-- Label and description -->
          <div class="preset-info">
            <span class="preset-label">
              {preset.label}
            </span>
            <span class="preset-description">
              {preset.description}
            </span>
          </div>
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .preset-container {
    position: relative;
    display: inline-block;
  }

  .trigger-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    border-radius: 8px;
    border: 1px solid oklch(0.24 0 0);
    background-color: oklch(0.14 0 0);
    font-size: 12px;
    font-weight: 500;
    color: oklch(0.80 0 0);
    transition: background-color 150ms;
    cursor: pointer;
  }

  .trigger-btn:hover {
    background-color: oklch(0.17 0 0);
  }

  .grid-icon {
    width: 14px;
    height: 14px;
    color: oklch(0.55 0 0);
  }

  .chevron-icon {
    width: 12px;
    height: 12px;
    color: oklch(0.45 0 0);
    transition: transform 150ms;
  }

  .chevron-icon.chevron-open {
    transform: rotate(180deg);
  }

  .dropdown-menu {
    position: absolute;
    top: 100%;
    left: 0;
    margin-top: 4px;
    z-index: 50;
    width: 256px;
    padding: 4px 0;
    border-radius: 8px;
    border: 1px solid oklch(0.24 0 0);
    background-color: oklch(0.13 0 0);
    box-shadow: 0 8px 32px oklch(0 0 0 / 0.5);
  }

  .preset-option {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    padding: 10px 12px;
    text-align: left;
    background: none;
    border: none;
    transition: background-color 100ms;
    cursor: pointer;
    color: inherit;
  }

  .preset-option:hover {
    background-color: oklch(0.16 0 0);
  }

  .preset-option.active {
    background-color: oklch(0.17 0.02 250);
  }

  .preset-option.active:hover {
    background-color: oklch(0.17 0.02 250);
  }

  .check-column {
    width: 16px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .check-icon {
    width: 14px;
    height: 14px;
    color: oklch(0.65 0.15 250);
  }

  .preset-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .preset-label {
    font-size: 12px;
    font-weight: 500;
    color: oklch(0.75 0 0);
  }

  .preset-option.active .preset-label {
    color: oklch(0.88 0 0);
  }

  .preset-description {
    font-size: 11px;
    color: oklch(0.45 0 0);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
