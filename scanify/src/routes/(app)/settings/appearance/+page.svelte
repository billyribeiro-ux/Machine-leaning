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

<div class="appearance-page">
  <!-- Header -->
  <div class="appearance-header" style="border-bottom: 1px solid var(--border-subtle);">
    <a href="/settings" class="breadcrumb-link" style="color: var(--text-tertiary);">Settings</a>
    <span class="breadcrumb-separator" style="color: var(--text-disabled);">/</span>
    <h1 class="appearance-title" style="color: var(--text-primary);">Appearance</h1>
  </div>

  <div class="appearance-body">

    <!-- Theme Selector -->
    <div class="section">
      <div>
        <h2 class="section-heading" style="color: var(--text-primary);">Theme</h2>
        <p class="section-description" style="color: var(--text-tertiary);">Choose the visual theme for the application</p>
      </div>

      <div class="theme-grid">
        {#each themes as theme (theme.id)}
          <button
            type="button"
            onclick={() => activeTheme = theme.id}
            class="theme-card"
            style="background: var(--bg-surface);
                   border: 2px solid {activeTheme === theme.id ? 'var(--accent)' : 'var(--border-subtle)'};
                   {activeTheme === theme.id ? 'box-shadow: var(--glow-accent);' : ''}"
          >
            <!-- Theme preview swatch -->
            <div
              class="theme-swatch"
              style="background: {theme.bg}; border: 1px solid var(--border-subtle);"
            >
              <span class="swatch-text" style="color: {theme.text};">Aa</span>
            </div>

            <span class="theme-label" style="color: {activeTheme === theme.id ? 'var(--accent-bright)' : 'var(--text-primary)'};">
              {theme.label}
            </span>
            <span class="theme-description" style="color: var(--text-tertiary);">{theme.description}</span>

            <!-- Active check -->
            {#if activeTheme === theme.id}
              <div class="theme-active-badge">
                <svg class="check-icon" style="color: var(--accent);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <span class="active-label" style="color: var(--accent);">Active</span>
              </div>
            {/if}
          </button>
        {/each}
      </div>
    </div>

    <!-- Animations Toggle -->
    <div class="section">
      <div>
        <h2 class="section-heading" style="color: var(--text-primary);">Animations</h2>
        <p class="section-description" style="color: var(--text-tertiary);">Enable or disable UI animations and transitions</p>
      </div>

      <div class="panel animations-row">
        <div class="animations-text">
          <span class="animations-label" style="color: var(--text-primary);">Enable Animations</span>
          <span class="animations-description" style="color: var(--text-tertiary);">Smooth transitions, price flashes, and signal pings</span>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={animationsEnabled}
          onclick={() => animationsEnabled = !animationsEnabled}
          class="toggle-track"
          style="background: {animationsEnabled ? 'oklch(0.55 0.15 145)' : 'oklch(0.24 0 0)'};"
        >
          <span
            class="toggle-thumb"
            style="transform: translateX({animationsEnabled ? '20px' : '2px'});"
          ></span>
        </button>
      </div>
    </div>

    <!-- Density -->
    <div class="section">
      <div>
        <h2 class="section-heading" style="color: var(--text-primary);">Density</h2>
        <p class="section-description" style="color: var(--text-tertiary);">Control the spacing and sizing of interface elements</p>
      </div>

      <div class="density-options">
        {#each densityOptions as option (option.id)}
          <button
            type="button"
            onclick={() => density = option.id}
            class="panel density-card"
            style="border: 2px solid {density === option.id ? 'var(--accent)' : 'var(--border-subtle)'};
                   {density === option.id ? 'box-shadow: var(--glow-accent);' : ''}"
          >
            <!-- Radio circle -->
            <div
              class="radio-outer"
              style="border: 2px solid {density === option.id ? 'var(--accent)' : 'var(--text-disabled)'};"
            >
              {#if density === option.id}
                <div class="radio-inner" style="background: var(--accent);"></div>
              {/if}
            </div>

            <!-- Label -->
            <div class="density-content">
              <div class="density-label" style="color: {density === option.id ? 'var(--accent-bright)' : 'var(--text-primary)'};">
                {option.label}
              </div>
              <div class="density-description" style="color: var(--text-tertiary);">{option.description}</div>
            </div>
          </button>
        {/each}
      </div>
    </div>

  </div>
</div>

<style>
  .appearance-page {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: auto;
  }

  .appearance-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 20px;
    flex-shrink: 0;
  }

  .breadcrumb-link {
    font-size: var(--text-xs);
  }

  .breadcrumb-separator {
    font-size: var(--text-xs);
  }

  .appearance-title {
    font-size: var(--text-lg);
    font-weight: 700;
  }

  .appearance-body {
    padding: 20px;
    max-width: 48rem;
  }

  .appearance-body > * + * {
    margin-top: 32px;
  }

  /* Sections */
  .section > * + * {
    margin-top: 12px;
  }

  .section-heading {
    font-size: var(--text-sm);
    font-weight: 600;
  }

  .section-description {
    font-size: var(--text-xs);
    margin-top: 2px;
  }

  /* Theme grid */
  .theme-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }

  @media (min-width: 768px) {
    .theme-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
  }

  .theme-card {
    display: flex;
    flex-direction: column;
    border-radius: var(--radius-xl);
    padding: 16px;
    text-align: left;
    transition: all 150ms;
  }

  .theme-swatch {
    width: 100%;
    height: 48px;
    border-radius: var(--radius-md);
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .swatch-text {
    font-size: var(--text-xs);
    font-weight: 700;
    font-family: var(--font-mono);
  }

  .theme-label {
    font-size: var(--text-xs);
    font-weight: 600;
  }

  .theme-description {
    font-size: 10px;
    margin-top: 2px;
  }

  .theme-active-badge {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-top: 8px;
  }

  .check-icon {
    width: 12px;
    height: 12px;
  }

  .active-label {
    font-size: 10px;
    font-weight: 500;
  }

  /* Animations toggle */
  .animations-row {
    padding: 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .animations-text {
    display: flex;
    flex-direction: column;
  }

  .animations-label {
    font-size: var(--text-xs);
    font-weight: 500;
  }

  .animations-description {
    font-size: 11px;
  }

  .toggle-track {
    position: relative;
    display: inline-flex;
    height: 24px;
    width: 44px;
    flex-shrink: 0;
    align-items: center;
    border-radius: var(--radius-full);
    transition: color 150ms, background-color 150ms;
    transition-duration: 200ms;
  }

  .toggle-thumb {
    display: inline-block;
    height: 20px;
    width: 20px;
    border-radius: var(--radius-full);
    background: white;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
    transition: transform 200ms;
  }

  /* Density options */
  .density-options > * + * {
    margin-top: 8px;
  }

  .density-card {
    width: 100%;
    padding: 16px;
    display: flex;
    align-items: center;
    gap: 16px;
    text-align: left;
    transition: all 150ms;
  }

  .radio-outer {
    width: 16px;
    height: 16px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .radio-inner {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
  }

  .density-content {
    flex: 1;
    min-width: 0;
  }

  .density-label {
    font-size: var(--text-xs);
    font-weight: 600;
  }

  .density-description {
    font-size: 10px;
    margin-top: 2px;
  }
</style>
