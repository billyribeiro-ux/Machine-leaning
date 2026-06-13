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

<div class="wrapper {className}">
  <!-- Section header -->
  <div class="section-header">
    <h2 class="title">Appearance</h2>
    <p class="subtitle">Customize the look and feel of your workspace</p>
  </div>

  <!-- Theme selection: 2x2 grid -->
  <div class="section">
    <h3 class="section-label">Theme</h3>
    <div class="theme-grid">
      {#each themes as theme (theme.id)}
        {@const isActive = activeTheme === theme.id}
        <button
          class="theme-card"
          class:active={isActive}
          onclick={() => selectTheme(theme.id)}
        >
          <!-- Active indicator -->
          {#if isActive}
            <div class="active-indicator">
              <div class="check-circle">
                <svg xmlns="http://www.w3.org/2000/svg" class="check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
            </div>
          {/if}

          <!-- Color swatch preview -->
          <div class="swatch-row">
            {#each theme.colors as color}
              <span
                class="swatch"
                style:background-color={color}
              ></span>
            {/each}
          </div>

          <!-- Label and description -->
          <div class="theme-info">
            <span class="theme-label" class:active={isActive}>
              {theme.label}
            </span>
            <span class="theme-description">
              {theme.description}
            </span>
          </div>
        </button>
      {/each}
    </div>
  </div>

  <!-- Animations toggle -->
  <div class="section">
    <h3 class="section-label">Motion</h3>
    <div class="toggle-row">
      <div class="toggle-text">
        <span class="toggle-label">Animations</span>
        <span class="toggle-description">
          Enable transitions and motion effects
        </span>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={animationsEnabled}
        class="toggle-track"
        class:enabled={animationsEnabled}
        onclick={() => { animationsEnabled = !animationsEnabled; }}
      >
        <span
          class="toggle-thumb"
          class:enabled={animationsEnabled}
        ></span>
      </button>
    </div>
  </div>

  <!-- Density selector -->
  <div class="section">
    <h3 class="section-label">Density</h3>
    <div class="density-row">
      {#each densityOptions as option (option.id)}
        {@const isActive = density === option.id}
        <button
          class="density-btn"
          class:active={isActive}
          onclick={() => { density = option.id; }}
        >
          {option.label}
        </button>
      {/each}
    </div>
    <p class="density-hint">
      {density === 'compact'
        ? 'Tighter spacing for maximum data density'
        : density === 'normal'
          ? 'Balanced spacing for everyday use'
          : 'Relaxed spacing for improved readability'}
    </p>
  </div>
</div>

<style>
  /* ---- Layout wrapper ---- */
  .wrapper {
    display: flex;
    flex-direction: column;
    gap: 32px;
  }

  /* ---- Section header ---- */
  .section-header {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .title {
    font-size: var(--text-lg);
    font-weight: 600;
    color: oklch(0.90 0 0);
  }

  .subtitle {
    font-size: var(--text-sm);
    color: oklch(0.55 0 0);
  }

  /* ---- Reusable section ---- */
  .section {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .section-label {
    font-size: var(--text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: oklch(0.60 0 0);
  }

  /* ---- Theme grid ---- */
  .theme-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }

  .theme-card {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 16px;
    border-radius: var(--radius-xl);
    border: 1px solid oklch(0.22 0 0);
    background-color: oklch(0.12 0 0);
    text-align: left;
    transition: all 200ms;
    cursor: pointer;
  }

  .theme-card:hover {
    border-color: oklch(0.30 0 0);
    background-color: oklch(0.14 0 0);
  }

  .theme-card.active {
    border-color: oklch(0.50 0.15 250);
    background-color: oklch(0.15 0.01 250);
    box-shadow: 0 0 16px oklch(0.50 0.15 250 / 0.1);
  }

  .theme-card.active:hover {
    border-color: oklch(0.50 0.15 250);
    background-color: oklch(0.15 0.01 250);
  }

  /* ---- Active indicator (checkmark) ---- */
  .active-indicator {
    position: absolute;
    top: 12px;
    right: 12px;
  }

  .check-circle {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border-radius: var(--radius-full);
    background-color: oklch(0.50 0.15 250);
  }

  .check-icon {
    width: 12px;
    height: 12px;
    color: white;
  }

  /* ---- Swatch row ---- */
  .swatch-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .swatch {
    width: 20px;
    height: 20px;
    border-radius: var(--radius-full);
    border: 1px solid oklch(0.30 0 0);
  }

  /* ---- Theme info ---- */
  .theme-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .theme-label {
    font-size: var(--text-sm);
    font-weight: 600;
    color: oklch(0.75 0 0);
  }

  .theme-label.active {
    color: oklch(0.90 0 0);
  }

  .theme-description {
    font-size: 11px;
    color: oklch(0.48 0 0);
  }

  /* ---- Toggle row (animations) ---- */
  .toggle-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-radius: var(--radius-xl);
    border: 1px solid oklch(0.20 0 0);
    background-color: oklch(0.12 0 0);
    padding-inline: 16px;
    padding-block: 12px;
  }

  .toggle-text {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .toggle-label {
    font-size: var(--text-sm);
    font-weight: 500;
    color: oklch(0.80 0 0);
  }

  .toggle-description {
    font-size: 11px;
    color: oklch(0.48 0 0);
  }

  /* ---- Toggle switch ---- */
  .toggle-track {
    position: relative;
    display: inline-flex;
    height: 24px;
    width: 44px;
    flex-shrink: 0;
    align-items: center;
    border-radius: var(--radius-full);
    transition: background-color 200ms;
    cursor: pointer;
    border: none;
    background-color: oklch(0.24 0 0);
  }

  .toggle-track.enabled {
    background-color: oklch(0.55 0.15 145);
  }

  .toggle-thumb {
    display: inline-block;
    height: 20px;
    width: 20px;
    border-radius: var(--radius-full);
    background-color: white;
    box-shadow: 0 1px 2px 0 rgb(0 0 0 / 0.05);
    transition: transform 200ms;
    transform: translateX(2px);
  }

  .toggle-thumb.enabled {
    transform: translateX(20px);
  }

  /* ---- Density selector ---- */
  .density-row {
    display: flex;
    gap: 8px;
  }

  .density-btn {
    flex: 1;
    padding-block: 10px;
    border-radius: var(--radius-lg);
    font-size: var(--text-xs);
    font-weight: 500;
    text-align: center;
    border: 1px solid oklch(0.22 0 0);
    background-color: oklch(0.12 0 0);
    color: oklch(0.55 0 0);
    transition: all 150ms;
    cursor: pointer;
  }

  .density-btn:hover {
    border-color: oklch(0.30 0 0);
    color: oklch(0.70 0 0);
  }

  .density-btn.active {
    border-color: oklch(0.45 0.12 250);
    background-color: oklch(0.17 0.02 250);
    color: oklch(0.80 0.10 250);
  }

  .density-btn.active:hover {
    border-color: oklch(0.45 0.12 250);
    color: oklch(0.80 0.10 250);
  }

  .density-hint {
    font-size: 11px;
    color: oklch(0.42 0 0);
  }
</style>
