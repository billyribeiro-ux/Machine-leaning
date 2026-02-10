<script lang="ts">
  let activeTheme = $state('dark');
  let animationsEnabled = $state(true);
  let density = $state<'compact' | 'normal' | 'comfortable'>('normal');

  const themes = [
    { id: 'dark',          label: 'Dark',          description: 'Default dark theme with OKLCH colors',     bg: 'oklch(0.14 0.02 260)', text: 'oklch(0.95 0.01 260)' },
    { id: 'light',         label: 'Light',         description: 'Light theme for bright environments',      bg: 'oklch(0.96 0.01 260)', text: 'oklch(0.15 0.02 260)' },
    { id: 'high-contrast', label: 'High Contrast', description: 'Enhanced contrast for accessibility',      bg: 'oklch(0.05 0.01 260)', text: 'oklch(0.98 0.00 260)' },
    { id: 'oled',          label: 'OLED',          description: 'True black for OLED displays',             bg: 'oklch(0.00 0.00 0)',   text: 'oklch(0.90 0.01 260)' },
  ];

  const densityOptions: { id: 'compact' | 'normal' | 'comfortable'; label: string; description: string }[] = [
    { id: 'compact',     label: 'Compact',     description: 'Tighter spacing, smaller text' },
    { id: 'normal',      label: 'Normal',      description: 'Balanced spacing and readability' },
    { id: 'comfortable', label: 'Comfortable', description: 'More whitespace, larger touch targets' },
  ];
</script>

<svelte:head>
  <title>Appearance - Scanify</title>
</svelte:head>

<div class="flex flex-col h-full overflow-auto">
  <!-- Header -->
  <div class="flex items-center gap-3 px-5 py-3 shrink-0" style="border-bottom: 1px solid var(--border-subtle);">
    <a href="/settings" class="text-xs" style="color: var(--text-tertiary);">Settings</a>
    <span class="text-xs" style="color: var(--text-disabled);">/</span>
    <h1 class="text-lg font-bold" style="color: var(--text-primary);">Appearance</h1>
  </div>

  <div class="p-5 space-y-8 max-w-3xl">

    <!-- Theme Selector -->
    <div class="space-y-3">
      <div>
        <h2 class="text-sm font-semibold" style="color: var(--text-primary);">Theme</h2>
        <p class="text-xs mt-0.5" style="color: var(--text-tertiary);">Choose the visual theme for the application</p>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        {#each themes as theme (theme.id)}
          <button
            type="button"
            onclick={() => activeTheme = theme.id}
            class="flex flex-col rounded-xl p-4 text-left transition-all duration-150"
            style="background: var(--bg-surface);
                   border: 2px solid {activeTheme === theme.id ? 'var(--accent)' : 'var(--border-subtle)'};
                   {activeTheme === theme.id ? 'box-shadow: var(--glow-accent);' : ''}"
          >
            <!-- Theme preview swatch -->
            <div
              class="w-full h-12 rounded-md mb-3 flex items-center justify-center"
              style="background: {theme.bg}; border: 1px solid var(--border-subtle);"
            >
              <span class="text-xs font-bold font-mono" style="color: {theme.text};">Aa</span>
            </div>

            <span class="text-xs font-semibold" style="color: {activeTheme === theme.id ? 'var(--accent-bright)' : 'var(--text-primary)'};">
              {theme.label}
            </span>
            <span class="text-[10px] mt-0.5" style="color: var(--text-tertiary);">{theme.description}</span>

            <!-- Active check -->
            {#if activeTheme === theme.id}
              <div class="flex items-center gap-1 mt-2">
                <svg class="w-3 h-3" style="color: var(--accent);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <span class="text-[10px] font-medium" style="color: var(--accent);">Active</span>
              </div>
            {/if}
          </button>
        {/each}
      </div>
    </div>

    <!-- Animations Toggle -->
    <div class="space-y-3">
      <div>
        <h2 class="text-sm font-semibold" style="color: var(--text-primary);">Animations</h2>
        <p class="text-xs mt-0.5" style="color: var(--text-tertiary);">Enable or disable UI animations and transitions</p>
      </div>

      <div class="panel p-4 flex items-center justify-between">
        <div class="flex flex-col">
          <span class="text-xs font-medium" style="color: var(--text-primary);">Enable Animations</span>
          <span class="text-[11px]" style="color: var(--text-tertiary);">Smooth transitions, price flashes, and signal pings</span>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={animationsEnabled}
          onclick={() => animationsEnabled = !animationsEnabled}
          class="relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-200"
          style="background: {animationsEnabled ? 'oklch(0.55 0.15 145)' : 'oklch(0.24 0 0)'};"
        >
          <span
            class="inline-block h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200"
            style="transform: translateX({animationsEnabled ? '20px' : '2px'});"
          ></span>
        </button>
      </div>
    </div>

    <!-- Density -->
    <div class="space-y-3">
      <div>
        <h2 class="text-sm font-semibold" style="color: var(--text-primary);">Density</h2>
        <p class="text-xs mt-0.5" style="color: var(--text-tertiary);">Control the spacing and sizing of interface elements</p>
      </div>

      <div class="space-y-2">
        {#each densityOptions as option (option.id)}
          <button
            type="button"
            onclick={() => density = option.id}
            class="w-full panel p-4 flex items-center gap-4 text-left transition-all duration-150"
            style="border: 2px solid {density === option.id ? 'var(--accent)' : 'var(--border-subtle)'};
                   {density === option.id ? 'box-shadow: var(--glow-accent);' : ''}"
          >
            <!-- Radio circle -->
            <div
              class="w-4 h-4 rounded-full shrink-0 flex items-center justify-center"
              style="border: 2px solid {density === option.id ? 'var(--accent)' : 'var(--text-disabled)'};"
            >
              {#if density === option.id}
                <div class="w-2 h-2 rounded-full" style="background: var(--accent);"></div>
              {/if}
            </div>

            <!-- Label -->
            <div class="flex-1 min-w-0">
              <div class="text-xs font-semibold" style="color: {density === option.id ? 'var(--accent-bright)' : 'var(--text-primary)'};">
                {option.label}
              </div>
              <div class="text-[10px] mt-0.5" style="color: var(--text-tertiary);">{option.description}</div>
            </div>
          </button>
        {/each}
      </div>
    </div>

  </div>
</div>
