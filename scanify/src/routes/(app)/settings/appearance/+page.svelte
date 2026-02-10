<script lang="ts">
  // ---- Theme state ----
  interface ThemeOption {
    id: string;
    name: string;
    description: string;
    preview: {
      bg: string;
      surface: string;
      text: string;
      accent: string;
      border: string;
    };
  }

  let selectedTheme = $state('dark');
  let density = $state<'compact' | 'normal' | 'comfortable'>('normal');
  let animationsEnabled = $state(true);

  const themes: ThemeOption[] = [
    {
      id: 'dark',
      name: 'Dark',
      description: 'Default dark theme with subtle blue undertones',
      preview: { bg: 'oklch(0.08 0.02 260)', surface: 'oklch(0.14 0.02 260)', text: 'oklch(0.95 0.01 260)', accent: 'oklch(0.62 0.20 290)', border: 'oklch(0.20 0.01 260)' },
    },
    {
      id: 'light',
      name: 'Light',
      description: 'Clean light theme for bright environments',
      preview: { bg: 'oklch(0.97 0.005 260)', surface: 'oklch(1.0 0 0)', text: 'oklch(0.15 0.02 260)', accent: 'oklch(0.55 0.22 290)', border: 'oklch(0.88 0.005 260)' },
    },
    {
      id: 'high-contrast',
      name: 'High Contrast',
      description: 'Maximum readability with stronger contrast',
      preview: { bg: 'oklch(0.05 0.01 260)', surface: 'oklch(0.10 0.01 260)', text: 'oklch(0.98 0.005 260)', accent: 'oklch(0.70 0.22 290)', border: 'oklch(0.30 0.02 260)' },
    },
    {
      id: 'oled',
      name: 'OLED Black',
      description: 'Pure black for OLED displays, saves battery',
      preview: { bg: 'oklch(0.0 0 0)', surface: 'oklch(0.07 0.005 260)', text: 'oklch(0.90 0.005 260)', accent: 'oklch(0.62 0.18 290)', border: 'oklch(0.15 0.005 260)' },
    },
  ];

  const densityOptions = [
    { id: 'compact' as const, label: 'Compact', description: 'Smaller spacing, more data visible' },
    { id: 'normal' as const, label: 'Normal', description: 'Balanced spacing and readability' },
    { id: 'comfortable' as const, label: 'Comfortable', description: 'More breathing room between elements' },
  ];
</script>

<svelte:head>
  <title>Appearance - Scanify</title>
</svelte:head>

<div class="flex flex-col h-full overflow-auto">
  <!-- Header -->
  <div class="flex items-center justify-between px-5 py-3 shrink-0" style="border-bottom: 1px solid var(--border-subtle);">
    <div class="flex items-center gap-3">
      <a href="/settings" class="text-xs" style="color: var(--text-tertiary);">Settings</a>
      <span style="color: var(--text-disabled);">/</span>
      <h1 class="text-lg font-bold" style="color: var(--text-primary);">Appearance</h1>
    </div>
  </div>

  <div class="p-5 space-y-8 max-w-3xl">
    <!-- Theme Selector -->
    <section class="space-y-3">
      <div>
        <h2 class="text-sm font-semibold" style="color: var(--text-primary);">Theme</h2>
        <p class="text-xs mt-0.5" style="color: var(--text-tertiary);">Choose the visual theme for the application.</p>
      </div>

      <div class="grid grid-cols-2 gap-3">
        {#each themes as theme (theme.id)}
          {@const isActive = selectedTheme === theme.id}
          <button
            type="button"
            onclick={() => selectedTheme = theme.id}
            class="text-left rounded-xl p-4 transition-all"
            style="background: var(--bg-surface);
                   border: 2px solid {isActive ? 'var(--accent)' : 'var(--border-subtle)'};
                   box-shadow: {isActive ? 'var(--glow-accent)' : 'none'};"
          >
            <!-- Theme preview -->
            <div
              class="rounded-lg h-20 mb-3 overflow-hidden flex flex-col"
              style="background: {theme.preview.bg}; border: 1px solid {theme.preview.border};"
            >
              <!-- Mini nav bar -->
              <div class="flex items-center gap-1.5 px-2 py-1.5" style="border-bottom: 1px solid {theme.preview.border};">
                <div class="w-1.5 h-1.5 rounded-full" style="background: {theme.preview.accent};"></div>
                <div class="w-8 h-1 rounded-full" style="background: {theme.preview.text}; opacity: 0.3;"></div>
              </div>
              <!-- Mini content area -->
              <div class="flex-1 p-2 flex gap-1.5">
                <div class="flex-1 rounded" style="background: {theme.preview.surface}; border: 1px solid {theme.preview.border};"></div>
                <div class="w-1/3 rounded" style="background: {theme.preview.surface}; border: 1px solid {theme.preview.border};"></div>
              </div>
            </div>

            <!-- Label -->
            <div class="flex items-center justify-between">
              <div>
                <h3 class="text-sm font-semibold" style="color: var(--text-primary);">{theme.name}</h3>
                <p class="text-[10px] mt-0.5" style="color: var(--text-tertiary);">{theme.description}</p>
              </div>
              {#if isActive}
                <div
                  class="flex h-5 w-5 items-center justify-center rounded-full shrink-0"
                  style="background: var(--accent);"
                >
                  <svg class="h-3 w-3 text-white" viewBox="0 0 20 20" fill="currentColor">
                    <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
                  </svg>
                </div>
              {/if}
            </div>
          </button>
        {/each}
      </div>
    </section>

    <!-- Density Selector -->
    <section class="space-y-3">
      <div>
        <h2 class="text-sm font-semibold" style="color: var(--text-primary);">Density</h2>
        <p class="text-xs mt-0.5" style="color: var(--text-tertiary);">Control the spacing and sizing of UI elements.</p>
      </div>

      <div class="flex gap-3">
        {#each densityOptions as option (option.id)}
          {@const isActive = density === option.id}
          <button
            type="button"
            onclick={() => density = option.id}
            class="flex-1 text-left rounded-lg p-4 transition-all"
            style="background: var(--bg-surface);
                   border: 2px solid {isActive ? 'var(--accent)' : 'var(--border-subtle)'};"
          >
            <!-- Visual indicator -->
            <div class="flex flex-col mb-3" style="gap: {option.id === 'compact' ? '2px' : option.id === 'normal' ? '4px' : '6px'};">
              {#each Array(3) as _}
                <div
                  class="rounded-sm"
                  style="background: var(--bg-elevated); border: 1px solid var(--border-subtle);
                         height: {option.id === 'compact' ? '6px' : option.id === 'normal' ? '8px' : '10px'};"
                ></div>
              {/each}
            </div>

            <div class="flex items-center justify-between">
              <div>
                <h3 class="text-xs font-semibold" style="color: var(--text-primary);">{option.label}</h3>
                <p class="text-[10px]" style="color: var(--text-tertiary);">{option.description}</p>
              </div>
              <!-- Radio dot -->
              <div
                class="h-4 w-4 rounded-full shrink-0 flex items-center justify-center"
                style="border: 2px solid {isActive ? 'var(--accent)' : 'var(--border-default)'};"
              >
                {#if isActive}
                  <div class="h-2 w-2 rounded-full" style="background: var(--accent);"></div>
                {/if}
              </div>
            </div>
          </button>
        {/each}
      </div>
    </section>

    <!-- Animations Toggle -->
    <section class="space-y-3">
      <div>
        <h2 class="text-sm font-semibold" style="color: var(--text-primary);">Animations</h2>
        <p class="text-xs mt-0.5" style="color: var(--text-tertiary);">Enable or disable UI transition animations.</p>
      </div>

      <div
        class="flex items-center justify-between rounded-lg p-4"
        style="background: var(--bg-surface); border: 1px solid var(--border-subtle);"
      >
        <div class="space-y-0.5">
          <h3 class="text-sm font-medium" style="color: var(--text-primary);">
            Enable animations
          </h3>
          <p class="text-xs" style="color: var(--text-tertiary);">
            {animationsEnabled ? 'Smooth transitions and motion effects are active.' : 'All animations are disabled for a snappier experience.'}
          </p>
        </div>

        <button
          type="button"
          role="switch"
          aria-checked={animationsEnabled}
          class="relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors"
          style="background: {animationsEnabled ? 'var(--bullish)' : 'oklch(0.24 0 0)'};"
          onclick={() => animationsEnabled = !animationsEnabled}
        >
          <span
            class="inline-block h-5 w-5 rounded-full bg-white shadow-sm transition-transform"
            style="transform: translateX({animationsEnabled ? '20px' : '2px'});"
          ></span>
        </button>
      </div>
    </section>

    <!-- Preview area -->
    <section class="space-y-3">
      <div>
        <h2 class="text-sm font-semibold" style="color: var(--text-primary);">Preview</h2>
        <p class="text-xs mt-0.5" style="color: var(--text-tertiary);">See how your settings look with sample data.</p>
      </div>

      <div class="panel p-4 space-y-3">
        <!-- Sample signal row -->
        <div class="flex items-center gap-3 rounded-lg px-3 py-2.5" style="background: var(--bg-base); border: 1px solid var(--border-subtle);">
          <div class="w-2.5 h-2.5 rounded-full" style="background: var(--bullish);"></div>
          <span class="text-sm font-bold font-mono" style="color: var(--text-primary);">NVDA</span>
          <span class="text-[11px]" style="color: var(--text-tertiary);">Momentum Breakout</span>
          <div class="flex-1"></div>
          <div class="flex gap-0.5">
            {#each Array(5) as _, i}
              <div class="h-1.5 w-2.5 rounded-full" style="background: {i < 5 ? 'var(--strength-5)' : 'var(--bg-overlay)'};"></div>
            {/each}
          </div>
          <span class="text-sm font-mono font-bold" style="color: var(--bullish);">+3.39%</span>
        </div>

        <!-- Sample badges -->
        <div class="flex items-center gap-2 flex-wrap">
          <span class="badge-bullish rounded-full px-2.5 py-1 text-[10px] font-semibold">BULLISH</span>
          <span class="badge-bearish rounded-full px-2.5 py-1 text-[10px] font-semibold">BEARISH</span>
          <span class="badge-neutral rounded-full px-2.5 py-1 text-[10px] font-semibold">NEUTRAL</span>
          <span class="badge-warning rounded-full px-2.5 py-1 text-[10px] font-semibold">UNUSUAL</span>
          <span class="badge-accent rounded-full px-2.5 py-1 text-[10px] font-semibold">SWEEP</span>
        </div>

        <!-- Sample metrics -->
        <div class="grid grid-cols-4 gap-2">
          {#each [['TICK', '+456', 'var(--bullish)'], ['TRIN', '0.87', 'var(--bullish)'], ['VIX', '15.2', 'var(--bullish)'], ['A/D', '1.40', 'var(--bullish)']] as [label, value, color]}
            <div class="text-center rounded-md p-2" style="background: var(--bg-base); border: 1px solid var(--border-subtle);">
              <div class="text-[9px] uppercase tracking-wider" style="color: var(--text-tertiary);">{label}</div>
              <div class="text-sm font-bold font-mono" style="color: {color};">{value}</div>
            </div>
          {/each}
        </div>
      </div>
    </section>
  </div>
</div>
