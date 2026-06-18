<!--
  NavRail.svelte
  56px-wide left navigation rail with Phosphor icons and tooltips.
  Bloomberg Terminal-style dark trading interface navigation.
-->
<script lang="ts">
  import {
    MagnifyingGlass,
    SquaresFour,
    GitDiff,
    ChartLineUp,
    Bank,
    ChartBar,
    Bell,
    GearSix,
  } from 'phosphor-svelte';
  import type { Component } from 'svelte';

  interface NavItem {
    /** Unique route identifier. */
    id: string;
    /** Display label (shown in tooltip). */
    label: string;
    /** Phosphor icon component. */
    icon: Component<any>;
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
    { id: 'scanner',       label: 'Scanner',       icon: MagnifyingGlass, shortcut: '1' },
    { id: 'dashboard',     label: 'Dashboard',     icon: SquaresFour,     shortcut: '2' },
    { id: 'options',       label: 'Options',       icon: GitDiff,         shortcut: '3' },
    { id: 'market',        label: 'Market',        icon: ChartLineUp,     shortcut: '4' },
    { id: 'institutional', label: 'Institutional', icon: Bank,            shortcut: '5' },
    { id: 'analysis',      label: 'Analysis',      icon: ChartBar,        shortcut: '6' },
    { id: 'alerts',        label: 'Alerts',        icon: Bell,            shortcut: '7' },
  ];

  const bottomItems: NavItem[] = [
    { id: 'settings', label: 'Settings', icon: GearSix },
  ];

  /** Simulated alert count for the notification badge. */
  let alertCount = $state(3);

  /**
   * Market status derived from current ET time.
   * green = regular hours, orange = pre/post, gray = closed
   */
  let marketStatus = $state<'open' | 'extended' | 'closed'>('closed');

  $effect(() => {
    function computeMarketStatus(): 'open' | 'extended' | 'closed' {
      const now = new Date();
      const et = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
      const day = et.getDay();
      const hours = et.getHours();
      const minutes = et.getMinutes();
      const totalMinutes = hours * 60 + minutes;

      // Weekend
      if (day === 0 || day === 6) return 'closed';

      // Pre-market 4:00-9:30 ET
      if (totalMinutes >= 240 && totalMinutes < 570) return 'extended';
      // Regular 9:30-16:00 ET
      if (totalMinutes >= 570 && totalMinutes < 960) return 'open';
      // After-hours 16:00-20:00 ET
      if (totalMinutes >= 960 && totalMinutes < 1200) return 'extended';

      return 'closed';
    }

    marketStatus = computeMarketStatus();
    const interval = setInterval(() => {
      marketStatus = computeMarketStatus();
    }, 30_000);

    return () => clearInterval(interval);
  });

  let marketStatusLabel = $derived(
    marketStatus === 'open' ? 'Market Open' :
    marketStatus === 'extended' ? 'Extended Hours' :
    'Market Closed'
  );

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
    <div class="nav-rail__logo-container">
      <span class="nav-rail__logo" aria-label="Scanify">S</span>
      <span class="nav-rail__logo-glow" aria-hidden="true"></span>
    </div>
  </div>

  <!-- Market status indicator -->
  <div class="nav-rail__market-status" title={marketStatusLabel}>
    <span
      class="nav-rail__market-dot"
      class:nav-rail__market-dot--open={marketStatus === 'open'}
      class:nav-rail__market-dot--extended={marketStatus === 'extended'}
      class:nav-rail__market-dot--closed={marketStatus === 'closed'}
      aria-hidden="true"
    ></span>
    <span class="nav-rail__market-label">{marketStatus === 'open' ? 'LIVE' : marketStatus === 'extended' ? 'EXT' : 'OFF'}</span>
  </div>

  <!-- Main navigation items -->
  <div class="nav-rail__items">
    {#each navItems as item (item.id)}
      {@const isActive = activeRoute === item.id}
      {@const isAlerts = item.id === 'alerts'}
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
          <span class="nav-rail__active-glow" aria-hidden="true"></span>
        {/if}
        <span class="nav-rail__icon-wrapper" class:nav-rail__icon-wrapper--active={isActive}>
          <item.icon size={20} weight={isActive ? 'fill' : 'regular'} />
          {#if isAlerts && alertCount > 0}
            <span class="nav-rail__notification-dot" aria-label="{alertCount} notifications">
              <span class="nav-rail__notification-ping" aria-hidden="true"></span>
            </span>
          {/if}
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
          <span class="nav-rail__active-glow" aria-hidden="true"></span>
        {/if}
        <span class="nav-rail__icon-wrapper" class:nav-rail__icon-wrapper--active={isActive}>
          <item.icon size={20} weight={isActive ? 'fill' : 'regular'} />
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
      <span class="nav-rail__avatar-ring">
        <span class="nav-rail__avatar-circle">W</span>
      </span>
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
    position: relative;
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

  .nav-rail__logo-container {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .nav-rail__logo {
    font-family: var(--font-display);
    font-size: var(--text-xl);
    font-weight: 800;
    color: var(--accent-bright);
    line-height: 1;
    letter-spacing: -0.04em;
    position: relative;
    z-index: 1;
    text-shadow:
      0 0 12px oklch(0.76 0.18 290 / 0.6),
      0 0 24px oklch(0.76 0.18 290 / 0.3);
  }

  .nav-rail__logo-glow {
    position: absolute;
    inset: -6px;
    border-radius: var(--radius-full);
    background: radial-gradient(
      circle,
      oklch(0.76 0.18 290 / 0.15) 0%,
      transparent 70%
    );
    animation: logo-breathe 3s ease-in-out infinite;
  }

  @keyframes logo-breathe {
    0%, 100% { opacity: 0.6; transform: scale(1); }
    50%      { opacity: 1;   transform: scale(1.15); }
  }

  /* ---- Market Status Indicator ---- */
  .nav-rail__market-status {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 8px 0 4px;
    flex-shrink: 0;
  }

  .nav-rail__market-dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
    transition: background-color 300ms ease, box-shadow 300ms ease;
  }

  .nav-rail__market-dot--open {
    background-color: var(--bullish);
    box-shadow: 0 0 8px var(--bullish-dim), 0 0 2px var(--bullish);
    animation: market-pulse 2s ease-in-out infinite;
  }

  .nav-rail__market-dot--extended {
    background-color: var(--warning);
    box-shadow: 0 0 6px var(--warning-dim);
  }

  .nav-rail__market-dot--closed {
    background-color: var(--text-disabled);
  }

  @keyframes market-pulse {
    0%, 100% { box-shadow: 0 0 4px var(--bullish-dim), 0 0 1px var(--bullish); }
    50%      { box-shadow: 0 0 12px var(--bullish-dim), 0 0 4px var(--bullish); }
  }

  .nav-rail__market-label {
    font-family: var(--font-mono);
    font-size: 8px;
    font-weight: 600;
    letter-spacing: 0.08em;
    color: var(--text-disabled);
    line-height: 1;
  }

  /* ---- Items container ---- */
  .nav-rail__items {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 6px 0;
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
      background-color 180ms ease,
      transform 180ms var(--ease-out-expo);
  }

  .nav-rail__item:hover {
    background-color: var(--hover-overlay);
    transform: scale(1.08);
  }

  .nav-rail__item:active {
    background-color: var(--active-overlay);
    transform: scale(0.96);
  }

  .nav-rail__item:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }

  /* Hover glow effect */
  .nav-rail__item::after {
    content: '';
    position: absolute;
    inset: -2px;
    border-radius: var(--radius-DEFAULT);
    opacity: 0;
    transition: opacity 200ms ease;
    pointer-events: none;
    background: radial-gradient(
      circle at center,
      oklch(0.76 0.18 290 / 0.08) 0%,
      transparent 70%
    );
  }

  .nav-rail__item:hover::after {
    opacity: 1;
  }

  /* ---- Active indicator (left accent bar) ---- */
  .nav-rail__active-indicator {
    position: absolute;
    left: -8px;
    top: 8px;
    bottom: 8px;
    width: 3px;
    border-radius: 0 var(--radius-full) var(--radius-full) 0;
    background: linear-gradient(
      180deg,
      var(--accent-bright) 0%,
      var(--accent) 100%
    );
    box-shadow: 0 0 8px oklch(0.76 0.18 290 / 0.5);
  }

  .nav-rail__active-glow {
    position: absolute;
    inset: -4px;
    border-radius: var(--radius-lg);
    background: radial-gradient(
      circle at center,
      oklch(0.62 0.20 290 / 0.1) 0%,
      transparent 70%
    );
    pointer-events: none;
  }

  .nav-rail__item--active {
    background-color: oklch(0.62 0.20 290 / 0.08);
  }

  .nav-rail__item--active:hover {
    transform: scale(1.04);
  }

  /* ---- Icon wrapper ---- */
  .nav-rail__icon-wrapper {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-tertiary);
    transition: color 180ms ease;
    z-index: 1;
  }

  .nav-rail__item:hover .nav-rail__icon-wrapper {
    color: var(--text-secondary);
  }

  .nav-rail__icon-wrapper--active {
    color: var(--accent-bright);
  }

  .nav-rail__item:hover .nav-rail__icon-wrapper--active {
    color: var(--accent-bright);
  }

  /* ---- Notification dot (alerts) ---- */
  .nav-rail__notification-dot {
    position: absolute;
    top: -3px;
    right: -4px;
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    background-color: var(--bearish);
    border: 1.5px solid var(--bg-base);
    z-index: 2;
  }

  .nav-rail__notification-ping {
    position: absolute;
    inset: -2px;
    border-radius: var(--radius-full);
    background-color: var(--bearish);
    animation: notification-pulse 2s ease-in-out infinite;
  }

  @keyframes notification-pulse {
    0%, 100% { opacity: 0;   transform: scale(1); }
    50%      { opacity: 0.4; transform: scale(1.8); }
  }

  /* ---- Tooltip (shown on hover) ---- */
  .nav-rail__tooltip {
    position: absolute;
    left: calc(100% + 12px);
    top: 50%;
    transform: translateY(-50%) translateX(-4px);
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
    transition:
      opacity 150ms ease,
      transform 150ms var(--ease-out-expo);
    box-shadow: var(--glow-sm);
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .nav-rail__item:hover .nav-rail__tooltip,
  .nav-rail__avatar:hover .nav-rail__tooltip {
    opacity: 1;
    transform: translateY(-50%) translateX(0);
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
    transition: transform 180ms var(--ease-out-expo);
  }

  .nav-rail__avatar:hover {
    transform: scale(1.08);
  }

  .nav-rail__avatar:active {
    transform: scale(0.96);
  }

  .nav-rail__avatar:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
    border-radius: var(--radius-full);
  }

  .nav-rail__avatar-ring {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    border-radius: var(--radius-full);
    background: conic-gradient(
      from 0deg,
      var(--accent-bright),
      var(--bullish),
      var(--neutral-bright),
      var(--accent-bright)
    );
    padding: 2px;
    transition: box-shadow 200ms ease;
  }

  .nav-rail__avatar:hover .nav-rail__avatar-ring {
    box-shadow: 0 0 12px oklch(0.76 0.18 290 / 0.35);
  }

  .nav-rail__avatar-circle {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    border-radius: var(--radius-full);
    background-color: var(--bg-base);
    color: var(--text-primary);
    font-family: var(--font-display);
    font-size: var(--text-xs);
    font-weight: 700;
    letter-spacing: 0.02em;
  }
</style>
