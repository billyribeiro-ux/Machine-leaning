<!--
  NavRail.svelte
  56px-wide left navigation rail with icon items and tooltips.
  Bloomberg Terminal-style dark trading interface navigation.
-->
<script lang="ts">
  interface NavItem {
    /** Unique route identifier. */
    id: string;
    /** Display label (shown in tooltip). */
    label: string;
    /** Text placeholder for icon (Phosphor icon name in comment). */
    icon: string;
    /** Keyboard shortcut hint. */
    shortcut?: string;
  }

  interface NavRailProps {
    /** Currently active route identifier. */
    activeRoute: string;
    /** Callback when a nav item is clicked. */
    onnavigate?: (route: string) => void;
    /** Additional CSS classes. */
    class?: string;
  }

  let {
    activeRoute,
    onnavigate,
    class: className = '',
  }: NavRailProps = $props();

  const navItems: NavItem[] = [
    { id: 'scanner',       label: 'Scanner',       icon: 'S',  shortcut: '1' },  /* Phosphor: MagnifyingGlass */
    { id: 'dashboard',     label: 'Dashboard',     icon: 'D',  shortcut: '2' },  /* Phosphor: SquaresFour */
    { id: 'options',       label: 'Options',       icon: 'O',  shortcut: '3' },  /* Phosphor: GitDiff */
    { id: 'market',        label: 'Market',        icon: 'M',  shortcut: '4' },  /* Phosphor: ChartLineUp */
    { id: 'institutional', label: 'Institutional', icon: 'I',  shortcut: '5' },  /* Phosphor: Bank */
    { id: 'analysis',      label: 'Analysis',      icon: 'A',  shortcut: '6' },  /* Phosphor: ChartBar */
    { id: 'alerts',        label: 'Alerts',        icon: '!',  shortcut: '7' },  /* Phosphor: Bell */
  ];

  const bottomItems: NavItem[] = [
    { id: 'settings', label: 'Settings', icon: 'G' },  /* Phosphor: GearSix */
  ];

  function handleItemClick(route: string): void {
    onnavigate?.(route);
  }

  function handleKeydown(event: KeyboardEvent, route: string): void {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      handleItemClick(route);
    }
  }
</script>

<nav
  class="nav-rail {className}"
  aria-label="Primary navigation"
>
  <!-- Top: Logo / brand mark -->
  <div class="nav-rail__brand">
    <span class="nav-rail__logo" aria-label="Scanify">
      S
    </span>
  </div>

  <!-- Main navigation items -->
  <div class="nav-rail__items">
    {#each navItems as item (item.id)}
      {@const isActive = activeRoute === item.id}
      <button
        class="nav-rail__item"
        class:nav-rail__item--active={isActive}
        onclick={() => handleItemClick(item.id)}
        onkeydown={(e) => handleKeydown(e, item.id)}
        aria-current={isActive ? 'page' : undefined}
        aria-label={item.label}
        title={item.shortcut ? `${item.label} (${item.shortcut})` : item.label}
      >
        {#if isActive}
          <span class="nav-rail__active-indicator" aria-hidden="true"></span>
        {/if}
        <span class="nav-rail__icon" class:nav-rail__icon--active={isActive}>
          {item.icon}
        </span>
        <span class="nav-rail__tooltip">
          {item.label}
          {#if item.shortcut}
            <kbd class="nav-rail__shortcut">{item.shortcut}</kbd>
          {/if}
        </span>
      </button>
    {/each}
  </div>

  <!-- Bottom: settings + user avatar -->
  <div class="nav-rail__bottom">
    {#each bottomItems as item (item.id)}
      {@const isActive = activeRoute === item.id}
      <button
        class="nav-rail__item"
        class:nav-rail__item--active={isActive}
        onclick={() => handleItemClick(item.id)}
        onkeydown={(e) => handleKeydown(e, item.id)}
        aria-current={isActive ? 'page' : undefined}
        aria-label={item.label}
        title={item.label}
      >
        {#if isActive}
          <span class="nav-rail__active-indicator" aria-hidden="true"></span>
        {/if}
        <span class="nav-rail__icon" class:nav-rail__icon--active={isActive}>
          {item.icon}
        </span>
        <span class="nav-rail__tooltip">{item.label}</span>
      </button>
    {/each}

    <!-- User avatar -->
    <button
      class="nav-rail__avatar"
      onclick={() => handleItemClick('profile')}
      aria-label="User profile"
      title="Profile"
    >
      <span class="nav-rail__avatar-circle">U</span>
      <span class="nav-rail__tooltip">Profile</span>
    </button>
  </div>
</nav>

<style>
  .nav-rail {
    display: flex;
    flex-direction: column;
    width: 56px;
    height: 100%;
    background-color: var(--bg-base);
    border-right: 1px solid var(--border-subtle);
    user-select: none;
  }

  /* ---- Brand ---- */
  .nav-rail__brand {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 48px;
    flex-shrink: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .nav-rail__logo {
    font-family: var(--font-display);
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--accent-bright);
    line-height: 1;
  }

  /* ---- Items container ---- */
  .nav-rail__items {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 8px 0;
    flex: 1;
    overflow-y: auto;
    scrollbar-width: none;
  }
  .nav-rail__items::-webkit-scrollbar {
    display: none;
  }

  /* ---- Bottom container ---- */
  .nav-rail__bottom {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 8px 0;
    flex-shrink: 0;
    border-top: 1px solid var(--border-subtle);
  }

  /* ---- Nav item ---- */
  .nav-rail__item {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border: none;
    border-radius: var(--radius-md);
    background: transparent;
    cursor: pointer;
    transition:
      background-color 150ms ease,
      color 150ms ease;
  }

  .nav-rail__item:hover {
    background-color: var(--hover-overlay);
  }

  .nav-rail__item:active {
    background-color: var(--active-overlay);
  }

  .nav-rail__item:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }

  /* ---- Active indicator (left accent border) ---- */
  .nav-rail__active-indicator {
    position: absolute;
    left: -8px;
    top: 8px;
    bottom: 8px;
    width: 3px;
    border-radius: 0 var(--radius-full) var(--radius-full) 0;
    background-color: var(--accent-bright);
  }

  .nav-rail__item--active {
    background-color: var(--accent-bg);
  }

  /* ---- Icon ---- */
  .nav-rail__icon {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-tertiary);
    line-height: 1;
    transition: color 150ms ease;
  }

  .nav-rail__item:hover .nav-rail__icon {
    color: var(--text-secondary);
  }

  .nav-rail__icon--active {
    color: var(--accent-bright);
  }

  .nav-rail__item:hover .nav-rail__icon--active {
    color: var(--accent-bright);
  }

  /* ---- Tooltip (shown on hover) ---- */
  .nav-rail__tooltip {
    position: absolute;
    left: calc(100% + 12px);
    top: 50%;
    transform: translateY(-50%);
    padding: 6px 10px;
    background-color: var(--bg-elevated);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    font-family: var(--font-body);
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--text-primary);
    white-space: nowrap;
    pointer-events: none;
    opacity: 0;
    z-index: var(--z-tooltip);
    transition: opacity 150ms ease;
    box-shadow: var(--glow-sm);
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .nav-rail__item:hover .nav-rail__tooltip,
  .nav-rail__avatar:hover .nav-rail__tooltip {
    opacity: 1;
  }

  .nav-rail__shortcut {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    padding: 1px 5px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-xs);
    background-color: var(--bg-surface);
  }

  /* ---- Avatar ---- */
  .nav-rail__avatar {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border: none;
    background: transparent;
    cursor: pointer;
    padding: 0;
    margin-top: 4px;
  }

  .nav-rail__avatar:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
    border-radius: var(--radius-full);
  }

  .nav-rail__avatar-circle {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: var(--radius-full);
    background-color: var(--accent-dim);
    color: var(--text-primary);
    font-family: var(--font-display);
    font-size: var(--text-xs);
    font-weight: 600;
    transition: background-color 150ms ease;
  }

  .nav-rail__avatar:hover .nav-rail__avatar-circle {
    background-color: var(--accent);
  }
</style>
