<!--
  ThemeSettings.svelte
  Theme selection with preview cards, animations toggle,
  and density selector (Compact / Normal / Comfortable).
-->
<script lang="ts">
  type ThemeId = 'dark' | 'light' | 'high-contrast' | 'oled';
  type Density = 'compact' | 'normal' | 'comfortable';

  interface ThemeOption {
    id: ThemeId;
    label: string;
    description: string;
    colors: string[];
  }

  interface ThemeSettingsProps {
    /** Currently active theme (bindable). */
    activeTheme: ThemeId;
    /** Whether animations are enabled (bindable). */
    animationsEnabled: boolean;
    /** Additional CSS classes. */
    class?: string;
  }

  let {
    activeTheme = $bindable('dark'),
    animationsEnabled = $bindable(true),
    class: className = '',
  }: ThemeSettingsProps = $props();

  let density = $state<Density>('normal');

  const themes: ThemeOption[] = [
    {
      id: 'dark',
      label: 'Dark',
      description: 'Default dark theme optimized for trading',
      colors: ['oklch(0.13 0 0)', 'oklch(0.20 0 0)', 'oklch(0.55 0.15 250)', 'oklch(0.55 0.15 145)'],
    },
    {
      id: 'light',
      label: 'Light',
      description: 'Bright theme for well-lit environments',
      colors: ['oklch(0.97 0 0)', 'oklch(0.90 0 0)', 'oklch(0.50 0.15 250)', 'oklch(0.45 0.18 145)'],
    },
    {
      id: 'high-contrast',
      label: 'High Contrast',
      description: 'Enhanced contrast for accessibility',
      colors: ['oklch(0.08 0 0)', 'oklch(0.15 0 0)', 'oklch(0.70 0.20 250)', 'oklch(0.70 0.22 145)'],
    },
    {
      id: 'oled',
      label: 'OLED Black',
      description: 'True blacks for OLED displays',
      colors: ['oklch(0 0 0)', 'oklch(0.10 0 0)', 'oklch(0.55 0.15 250)', 'oklch(0.55 0.15 145)'],
    },
  ];

  const densityOptions: { id: Density; label: string }[] = [
    { id: 'compact',     label: 'Compact' },
    { id: 'normal',      label: 'Normal' },
    { id: 'comfortable', label: 'Comfortable' },
  ];

  function selectTheme(id: ThemeId): void {
    activeTheme = id;
  }
</script>

<div class="flex flex-col gap-8 {className}">
  <!-- Section header -->
  <div class="flex flex-col gap-1">
    <h2 class="text-lg font-semibold text-[oklch(0.90_0_0)]">Appearance</h2>
    <p class="text-sm text-[oklch(0.55_0_0)]">Customize the look and feel of your workspace</p>
  </div>

  <!-- Theme selection: 2x2 grid -->
  <div class="flex flex-col gap-3">
    <h3 class="text-xs font-semibold uppercase tracking-wider text-[oklch(0.60_0_0)]">Theme</h3>
    <div class="grid grid-cols-2 gap-3">
      {#each themes as theme (theme.id)}
        {@const isActive = activeTheme === theme.id}
        <button
          class="
            relative flex flex-col gap-3 p-4 rounded-xl border text-left
            transition-all duration-200 cursor-pointer
            {isActive
              ? 'border-[oklch(0.50_0.15_250)] bg-[oklch(0.15_0.01_250)] shadow-[0_0_16px_oklch(0.50_0.15_250/0.1)]'
              : 'border-[oklch(0.22_0_0)] bg-[oklch(0.12_0_0)] hover:border-[oklch(0.30_0_0)] hover:bg-[oklch(0.14_0_0)]'}
          "
          onclick={() => selectTheme(theme.id)}
        >
          <!-- Active indicator -->
          {#if isActive}
            <div class="absolute top-3 right-3">
              <div class="flex items-center justify-center w-5 h-5 rounded-full bg-[oklch(0.50_0.15_250)]">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
            </div>
          {/if}

          <!-- Color swatch preview -->
          <div class="flex items-center gap-2">
            {#each theme.colors as color}
              <span
                class="w-5 h-5 rounded-full border border-[oklch(0.30_0_0)]"
                style:background-color={color}
              ></span>
            {/each}
          </div>

          <!-- Label and description -->
          <div class="flex flex-col gap-0.5">
            <span class="text-sm font-semibold {isActive ? 'text-[oklch(0.90_0_0)]' : 'text-[oklch(0.75_0_0)]'}">
              {theme.label}
            </span>
            <span class="text-[11px] text-[oklch(0.48_0_0)]">
              {theme.description}
            </span>
          </div>
        </button>
      {/each}
    </div>
  </div>

  <!-- Animations toggle -->
  <div class="flex flex-col gap-3">
    <h3 class="text-xs font-semibold uppercase tracking-wider text-[oklch(0.60_0_0)]">Motion</h3>
    <div
      class="
        flex items-center justify-between
        rounded-xl border border-[oklch(0.20_0_0)] bg-[oklch(0.12_0_0)]
        px-4 py-3
      "
    >
      <div class="flex flex-col gap-0.5">
        <span class="text-sm font-medium text-[oklch(0.80_0_0)]">Animations</span>
        <span class="text-[11px] text-[oklch(0.48_0_0)]">
          Enable transitions and motion effects
        </span>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={animationsEnabled}
        class="
          relative inline-flex h-6 w-11 shrink-0 items-center rounded-full
          transition-colors duration-200 cursor-pointer border-none
          {animationsEnabled ? 'bg-[oklch(0.55_0.15_145)]' : 'bg-[oklch(0.24_0_0)]'}
        "
        onclick={() => { animationsEnabled = !animationsEnabled; }}
      >
        <span
          class="
            inline-block h-5 w-5 rounded-full bg-white shadow-sm
            transition-transform duration-200
            {animationsEnabled ? 'translate-x-5' : 'translate-x-0.5'}
          "
        ></span>
      </button>
    </div>
  </div>

  <!-- Density selector -->
  <div class="flex flex-col gap-3">
    <h3 class="text-xs font-semibold uppercase tracking-wider text-[oklch(0.60_0_0)]">Density</h3>
    <div class="flex gap-2">
      {#each densityOptions as option (option.id)}
        {@const isActive = density === option.id}
        <button
          class="
            flex-1 py-2.5 rounded-lg text-xs font-medium text-center
            border transition-all duration-150 cursor-pointer
            {isActive
              ? 'border-[oklch(0.45_0.12_250)] bg-[oklch(0.17_0.02_250)] text-[oklch(0.80_0.10_250)]'
              : 'border-[oklch(0.22_0_0)] bg-[oklch(0.12_0_0)] text-[oklch(0.55_0_0)] hover:border-[oklch(0.30_0_0)] hover:text-[oklch(0.70_0_0)]'}
          "
          onclick={() => { density = option.id; }}
        >
          {option.label}
        </button>
      {/each}
    </div>
    <p class="text-[11px] text-[oklch(0.42_0_0)]">
      {density === 'compact'
        ? 'Tighter spacing for maximum data density'
        : density === 'normal'
          ? 'Balanced spacing for everyday use'
          : 'Relaxed spacing for improved readability'}
    </p>
  </div>
</div>
