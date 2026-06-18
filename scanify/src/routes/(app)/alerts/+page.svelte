<script lang="ts">
  // ── Alert History Data ──
  const alertHistory = $state([
    {
      id: 'a1',
      symbol: 'NVDA',
      direction: 'BULL' as const,
      type: 'Momentum Break',
      strength: 5,
      scanner: 'Momentum Scanner',
      description: '$142.50 -- broke above 20-day high with 3.2x volume',
      price: '$142.50',
      time: '2m ago',
    },
    {
      id: 'a2',
      symbol: 'TSLA',
      direction: 'BEAR' as const,
      type: 'Volume Surge',
      strength: 4,
      scanner: 'Volume Scanner',
      description: '4.8x relative volume on declining price action',
      price: '$268.90',
      time: '8m ago',
    },
    {
      id: 'a3',
      symbol: 'AMD',
      direction: 'BULL' as const,
      type: 'Squeeze Fire',
      strength: 5,
      scanner: 'Squeeze Scanner',
      description: 'Bollinger squeeze fired bullish after 12-day compression',
      price: '$178.30',
      time: '15m ago',
    },
    {
      id: 'a4',
      symbol: 'SPY',
      direction: 'BEAR' as const,
      type: 'GEX Flip',
      strength: 3,
      scanner: 'Options Flow',
      description: 'Gamma exposure flipped negative at $585 strike',
      price: '$584.20',
      time: '22m ago',
    },
    {
      id: 'a5',
      symbol: 'AAPL',
      direction: 'BULL' as const,
      type: 'Breakout',
      strength: 4,
      scanner: 'Breakout Scanner',
      description: 'Cleared $198 resistance with institutional volume',
      price: '$198.75',
      time: '35m ago',
    },
    {
      id: 'a6',
      symbol: 'META',
      direction: 'BULL' as const,
      type: 'Unusual Options',
      strength: 4,
      scanner: 'Options Flow',
      description: '10,000 $550C sweeps expiring this Friday, $4.2M premium',
      price: '$542.60',
      time: '45m ago',
    },
    {
      id: 'a7',
      symbol: 'MSFT',
      direction: 'BEAR' as const,
      type: 'Reversal',
      strength: 3,
      scanner: 'Reversal Scanner',
      description: 'Bearish engulfing at 52-week high with divergent RSI',
      price: '$448.20',
      time: '1h ago',
    },
    {
      id: 'a8',
      symbol: 'AMZN',
      direction: 'BULL' as const,
      type: 'Gap Scanner',
      strength: 4,
      scanner: 'Gap Scanner',
      description: '+2.3% gap up on AWS revenue beat, holding above VWAP',
      price: '$198.45',
      time: '1.5h ago',
    },
  ]);

  // ── Alert Configuration Categories ──
  let scannerAlerts = $state([
    { id: 's1', name: 'Momentum', enabled: true, sensitivity: 70 },
    { id: 's2', name: 'Volume', enabled: true, sensitivity: 60 },
    { id: 's3', name: 'Breakout', enabled: true, sensitivity: 80 },
    { id: 's4', name: 'Squeeze', enabled: true, sensitivity: 75 },
    { id: 's5', name: 'Gap', enabled: false, sensitivity: 50 },
    { id: 's6', name: 'Reversal', enabled: false, sensitivity: 55 },
  ]);

  let marketAlerts = $state([
    { id: 'm1', name: 'VIX Spike', enabled: true },
    { id: 'm2', name: 'TRIN Extreme', enabled: false },
    { id: 'm3', name: 'Breadth Divergence', enabled: true },
    { id: 'm4', name: 'Sector Rotation', enabled: false },
  ]);

  let optionsAlerts = $state([
    { id: 'o1', name: 'Unusual Activity', enabled: true },
    { id: 'o2', name: 'Large Block', enabled: true },
    { id: 'o3', name: 'GEX Flip', enabled: true },
    { id: 'o4', name: 'IV Surge', enabled: false },
  ]);

  let customAlerts = $state([
    { id: 'c1', name: 'Price Target', enabled: false },
    { id: 'c2', name: 'Volume Threshold', enabled: false },
  ]);

  // ── Delivery Settings ──
  let soundAlerts = $state(true);
  let pushNotifications = $state(false);
  let desktopNotifications = $state(true);
  let alertCooldown = $state('15m');

  const cooldownOptions = ['5m', '15m', '30m', '1h'];

  // ── Collapsible state ──
  let expandedSections = $state<Record<string, boolean>>({
    scanner: true,
    market: true,
    options: false,
    custom: false,
    delivery: true,
  });

  function toggleSection(key: string) {
    expandedSections = { ...expandedSections, [key]: !expandedSections[key] };
  }

  // ── Counts ──
  let activeCount = $derived(
    scannerAlerts.filter(a => a.enabled).length +
    marketAlerts.filter(a => a.enabled).length +
    optionsAlerts.filter(a => a.enabled).length +
    customAlerts.filter(a => a.enabled).length
  );

  // ── Helpers ──
  function strengthDots(n: number): string[] {
    return Array.from({ length: 5 }, (_, i) => i < n ? 'filled' : 'empty');
  }

  function toggleItem(arr: any[], id: string): any[] {
    return arr.map(a => a.id === id ? { ...a, enabled: !a.enabled } : a);
  }
</script>

<svelte:head>
  <title>Alerts - Scanify</title>
</svelte:head>

<div class="page-root">
  <!-- Header -->
  <header class="page-header">
    <div class="header-left">
      <h1 class="page-title">Alerts</h1>
      <span class="page-subtitle">Real-time scanner notifications & alert configuration</span>
    </div>
    <div class="header-right">
      <div class="active-count-badge">
        <span class="count-value mono-nums">{activeCount}</span>
        <span class="count-label">active</span>
      </div>
    </div>
  </header>

  <!-- Main Content: Split Layout -->
  <div class="split-layout">
    <!-- LEFT: Alert History Feed (65%) -->
    <div class="feed-column">
      <div class="column-header">
        <h2 class="column-title">Alert Feed</h2>
        <span class="column-count mono-nums">{alertHistory.length} alerts</span>
      </div>

      <div class="alert-timeline">
        {#each alertHistory as alert, i (alert.id)}
          <div
            class="alert-card glass-panel"
            class:alert-bull={alert.direction === 'BULL'}
            class:alert-bear={alert.direction === 'BEAR'}
            style="animation-delay: {i * 60}ms"
          >
            <div class="alert-card-body">
              <!-- Top Row: Symbol + Direction + Type + Time -->
              <div class="alert-top-row">
                <div class="alert-identity">
                  <span class="alert-symbol mono-nums">{alert.symbol}</span>
                  <span class="direction-badge" class:dir-bull={alert.direction === 'BULL'} class:dir-bear={alert.direction === 'BEAR'}>
                    {alert.direction}
                  </span>
                  <span class="type-badge">{alert.type}</span>
                </div>
                <span class="alert-time mono-nums">{alert.time}</span>
              </div>

              <!-- Description -->
              <p class="alert-description">{alert.description}</p>

              <!-- Bottom Row: Strength + Scanner + Price -->
              <div class="alert-bottom-row">
                <div class="alert-meta">
                  <div class="strength-dots" title="Signal strength: {alert.strength}/5">
                    {#each strengthDots(alert.strength) as dot}
                      <span class="dot" class:dot-filled={dot === 'filled'} class:dot-empty={dot === 'empty'}></span>
                    {/each}
                  </div>
                  <span class="scanner-name">{alert.scanner}</span>
                </div>
                <span class="alert-price mono-nums">{alert.price}</span>
              </div>
            </div>
          </div>
        {/each}
      </div>
    </div>

    <!-- RIGHT: Alert Configuration (35%) -->
    <div class="config-column">
      <div class="column-header">
        <h2 class="column-title">Configuration</h2>
      </div>

      <div class="config-scroll">
        <!-- Scanner Alerts Section -->
        <div class="config-section">
          <button class="section-toggle" onclick={() => toggleSection('scanner')}>
            <div class="section-toggle-left">
              <svg class="chevron" class:chevron-open={expandedSections.scanner} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
              <span class="section-label">Scanner Alerts</span>
            </div>
            <span class="section-count mono-nums">{scannerAlerts.filter(a => a.enabled).length}/{scannerAlerts.length}</span>
          </button>

          {#if expandedSections.scanner}
            <div class="section-items" style="animation: expandSection 250ms var(--ease-out-expo) both">
              {#each scannerAlerts as item (item.id)}
                <div class="config-item">
                  <div class="config-item-info">
                    <span class="config-item-name">{item.name}</span>
                    {#if 'sensitivity' in item}
                      <div class="sensitivity-row">
                        <div class="sensitivity-track">
                          <div class="sensitivity-fill" style="width: {item.sensitivity}%"></div>
                        </div>
                        <span class="sensitivity-value mono-nums">{item.sensitivity}%</span>
                      </div>
                    {/if}
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={item.enabled}
                    class="toggle-track"
                    class:toggle-on={item.enabled}
                    onclick={() => scannerAlerts = toggleItem(scannerAlerts, item.id)}
                  >
                    <span class="toggle-thumb" class:thumb-on={item.enabled}></span>
                  </button>
                </div>
              {/each}
            </div>
          {/if}
        </div>

        <!-- Market Alerts Section -->
        <div class="config-section">
          <button class="section-toggle" onclick={() => toggleSection('market')}>
            <div class="section-toggle-left">
              <svg class="chevron" class:chevron-open={expandedSections.market} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
              <span class="section-label">Market Alerts</span>
            </div>
            <span class="section-count mono-nums">{marketAlerts.filter(a => a.enabled).length}/{marketAlerts.length}</span>
          </button>

          {#if expandedSections.market}
            <div class="section-items" style="animation: expandSection 250ms var(--ease-out-expo) both">
              {#each marketAlerts as item (item.id)}
                <div class="config-item">
                  <span class="config-item-name">{item.name}</span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={item.enabled}
                    class="toggle-track"
                    class:toggle-on={item.enabled}
                    onclick={() => marketAlerts = toggleItem(marketAlerts, item.id)}
                  >
                    <span class="toggle-thumb" class:thumb-on={item.enabled}></span>
                  </button>
                </div>
              {/each}
            </div>
          {/if}
        </div>

        <!-- Options Alerts Section -->
        <div class="config-section">
          <button class="section-toggle" onclick={() => toggleSection('options')}>
            <div class="section-toggle-left">
              <svg class="chevron" class:chevron-open={expandedSections.options} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
              <span class="section-label">Options Alerts</span>
            </div>
            <span class="section-count mono-nums">{optionsAlerts.filter(a => a.enabled).length}/{optionsAlerts.length}</span>
          </button>

          {#if expandedSections.options}
            <div class="section-items" style="animation: expandSection 250ms var(--ease-out-expo) both">
              {#each optionsAlerts as item (item.id)}
                <div class="config-item">
                  <span class="config-item-name">{item.name}</span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={item.enabled}
                    class="toggle-track"
                    class:toggle-on={item.enabled}
                    onclick={() => optionsAlerts = toggleItem(optionsAlerts, item.id)}
                  >
                    <span class="toggle-thumb" class:thumb-on={item.enabled}></span>
                  </button>
                </div>
              {/each}
            </div>
          {/if}
        </div>

        <!-- Custom Alerts Section -->
        <div class="config-section">
          <button class="section-toggle" onclick={() => toggleSection('custom')}>
            <div class="section-toggle-left">
              <svg class="chevron" class:chevron-open={expandedSections.custom} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
              <span class="section-label">Custom</span>
            </div>
            <span class="section-count mono-nums">{customAlerts.filter(a => a.enabled).length}/{customAlerts.length}</span>
          </button>

          {#if expandedSections.custom}
            <div class="section-items" style="animation: expandSection 250ms var(--ease-out-expo) both">
              {#each customAlerts as item (item.id)}
                <div class="config-item">
                  <span class="config-item-name">{item.name}</span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={item.enabled}
                    class="toggle-track"
                    class:toggle-on={item.enabled}
                    onclick={() => customAlerts = toggleItem(customAlerts, item.id)}
                  >
                    <span class="toggle-thumb" class:thumb-on={item.enabled}></span>
                  </button>
                </div>
              {/each}
            </div>
          {/if}
        </div>

        <!-- Delivery Settings -->
        <div class="config-section delivery-section">
          <button class="section-toggle" onclick={() => toggleSection('delivery')}>
            <div class="section-toggle-left">
              <svg class="chevron" class:chevron-open={expandedSections.delivery} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
              <span class="section-label">Delivery Settings</span>
            </div>
          </button>

          {#if expandedSections.delivery}
            <div class="section-items" style="animation: expandSection 250ms var(--ease-out-expo) both">
              <div class="config-item">
                <div class="delivery-item-info">
                  <span class="config-item-name">Sound Alerts</span>
                  <span class="delivery-desc">Play audio on new alerts</span>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={soundAlerts}
                  class="toggle-track"
                  class:toggle-on={soundAlerts}
                  onclick={() => soundAlerts = !soundAlerts}
                >
                  <span class="toggle-thumb" class:thumb-on={soundAlerts}></span>
                </button>
              </div>

              <div class="config-item">
                <div class="delivery-item-info">
                  <span class="config-item-name">Push Notifications</span>
                  <span class="delivery-desc">Receive mobile push alerts</span>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={pushNotifications}
                  class="toggle-track"
                  class:toggle-on={pushNotifications}
                  onclick={() => pushNotifications = !pushNotifications}
                >
                  <span class="toggle-thumb" class:thumb-on={pushNotifications}></span>
                </button>
              </div>

              <div class="config-item">
                <div class="delivery-item-info">
                  <span class="config-item-name">Desktop Notifications</span>
                  <span class="delivery-desc">Browser notification popups</span>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={desktopNotifications}
                  class="toggle-track"
                  class:toggle-on={desktopNotifications}
                  onclick={() => desktopNotifications = !desktopNotifications}
                >
                  <span class="toggle-thumb" class:thumb-on={desktopNotifications}></span>
                </button>
              </div>

              <div class="config-item cooldown-item">
                <div class="delivery-item-info">
                  <span class="config-item-name">Alert Cooldown</span>
                  <span class="delivery-desc">Minimum time between repeat alerts</span>
                </div>
                <div class="cooldown-options">
                  {#each cooldownOptions as opt}
                    <button
                      type="button"
                      class="cooldown-btn mono-nums"
                      class:cooldown-active={alertCooldown === opt}
                      onclick={() => alertCooldown = opt}
                    >
                      {opt}
                    </button>
                  {/each}
                </div>
              </div>
            </div>
          {/if}
        </div>
      </div>
    </div>
  </div>
</div>

<style>
  /* ── Page Layout ── */
  .page-root {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }

  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 24px;
    flex-shrink: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .header-left {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .page-title {
    font-size: var(--text-xl);
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.02em;
  }

  .page-subtitle {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
  }

  .header-right {
    display: flex;
    align-items: center;
  }

  .active-count-badge {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px;
    border-radius: var(--radius-full);
    background: var(--accent-bg);
    border: 1px solid oklch(0.44 0.14 290 / 0.3);
  }

  .count-value {
    font-size: var(--text-sm);
    font-weight: 700;
    color: var(--accent-bright);
  }

  .count-label {
    font-size: var(--text-2xs);
    color: var(--accent);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  /* ── Split Layout ── */
  .split-layout {
    display: flex;
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }

  .feed-column {
    flex: 0 0 65%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    border-right: 1px solid var(--border-subtle);
  }

  .config-column {
    flex: 0 0 35%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .column-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
    background: var(--bg-base);
  }

  .column-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .column-count {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
  }

  /* ── Alert Timeline / Feed ── */
  .alert-timeline {
    flex: 1;
    overflow-y: auto;
    padding: 16px 20px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .glass-panel {
    background: oklch(0.14 0.02 260 / 0.7);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-xl);
    backdrop-filter: blur(var(--blur-panel));
    -webkit-backdrop-filter: blur(var(--blur-panel));
    box-shadow: var(--glow-xs);
  }

  .alert-card {
    position: relative;
    border-left: 3px solid transparent;
    transition: box-shadow var(--duration-normal) ease, border-color var(--duration-normal) ease;
    animation: cardFadeIn 400ms var(--ease-out-expo) both;
  }

  .alert-card:hover {
    box-shadow: var(--glow-sm);
  }

  .alert-bull {
    border-left-color: var(--bullish);
  }

  .alert-bull:hover {
    box-shadow: var(--glow-bullish);
  }

  .alert-bear {
    border-left-color: var(--bearish);
  }

  .alert-bear:hover {
    box-shadow: var(--glow-bearish);
  }

  @keyframes cardFadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .alert-card-body {
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  /* ── Alert Card Top Row ── */
  .alert-top-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .alert-identity {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .alert-symbol {
    font-size: var(--text-base);
    font-weight: 800;
    color: var(--text-primary);
    letter-spacing: 0.02em;
  }

  .direction-badge {
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 0.08em;
    padding: 2px 8px;
    border-radius: var(--radius-full);
  }

  .dir-bull {
    color: var(--bullish-bright);
    background: var(--bullish-bg);
    border: 1px solid oklch(0.45 0.12 155 / 0.3);
  }

  .dir-bear {
    color: var(--bearish-bright);
    background: var(--bearish-bg);
    border: 1px solid oklch(0.42 0.12 25 / 0.3);
  }

  .type-badge {
    font-size: var(--text-2xs);
    font-weight: 600;
    color: var(--accent-bright);
    background: var(--accent-bg);
    border: 1px solid oklch(0.44 0.14 290 / 0.25);
    padding: 2px 8px;
    border-radius: var(--radius-full);
  }

  .alert-time {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    flex-shrink: 0;
  }

  /* ── Alert Description ── */
  .alert-description {
    font-size: var(--text-xs);
    color: var(--text-secondary);
    line-height: 1.5;
  }

  /* ── Alert Bottom Row ── */
  .alert-bottom-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .alert-meta {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .strength-dots {
    display: flex;
    gap: 3px;
    align-items: center;
  }

  .dot {
    width: 6px;
    height: 6px;
    border-radius: var(--radius-full);
    transition: background-color var(--duration-fast) ease;
  }

  .dot-filled {
    background: var(--accent-bright);
    box-shadow: 0 0 4px oklch(0.76 0.18 290 / 0.4);
  }

  .dot-empty {
    background: oklch(0.25 0.01 260);
  }

  .scanner-name {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    font-weight: 500;
  }

  .alert-price {
    font-size: var(--text-xs);
    font-weight: 700;
    color: var(--text-primary);
  }

  /* ── Config Panel ── */
  .config-scroll {
    flex: 1;
    overflow-y: auto;
    padding: 8px 0;
  }

  .config-section {
    border-bottom: 1px solid var(--border-subtle);
  }

  .delivery-section {
    border-bottom: none;
  }

  .section-toggle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 12px 20px;
    cursor: pointer;
    transition: background-color var(--duration-fast) ease;
  }

  .section-toggle:hover {
    background: var(--hover-overlay);
  }

  .section-toggle-left {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .section-label {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .section-count {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    font-weight: 500;
  }

  .chevron {
    color: var(--text-tertiary);
    transition: transform var(--duration-normal) var(--ease-out-expo);
    flex-shrink: 0;
  }

  .chevron-open {
    transform: rotate(90deg);
  }

  @keyframes expandSection {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .section-items {
    padding: 0 20px 12px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .config-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 8px 12px;
    border-radius: var(--radius-DEFAULT);
    transition: background-color var(--duration-fast) ease;
  }

  .config-item:hover {
    background: oklch(0.95 0.01 260 / 0.03);
  }

  .config-item-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex: 1;
    min-width: 0;
  }

  .config-item-name {
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--text-secondary);
  }

  /* ── Sensitivity ── */
  .sensitivity-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .sensitivity-track {
    flex: 1;
    height: 3px;
    background: oklch(0.20 0.01 260);
    border-radius: var(--radius-full);
    overflow: hidden;
    max-width: 80px;
  }

  .sensitivity-fill {
    height: 100%;
    background: var(--accent);
    border-radius: var(--radius-full);
    transition: width var(--duration-normal) var(--ease-out-expo);
  }

  .sensitivity-value {
    font-size: 10px;
    color: var(--text-tertiary);
    min-width: 28px;
  }

  /* ── Toggle Switch ── */
  .toggle-track {
    position: relative;
    display: inline-flex;
    height: 22px;
    width: 40px;
    flex-shrink: 0;
    align-items: center;
    border-radius: var(--radius-full);
    background: oklch(0.22 0.01 260);
    transition: background-color var(--duration-normal) ease;
    cursor: pointer;
    border: 1px solid oklch(0.28 0.01 260);
  }

  .toggle-on {
    background: oklch(0.55 0.15 155);
    border-color: oklch(0.45 0.12 155 / 0.5);
  }

  .toggle-thumb {
    display: inline-block;
    height: 16px;
    width: 16px;
    border-radius: var(--radius-full);
    background: oklch(0.85 0.01 260);
    box-shadow: 0 1px 3px oklch(0 0 0 / 0.2);
    transition: transform var(--duration-normal) var(--ease-out-expo);
    transform: translateX(2px);
  }

  .thumb-on {
    transform: translateX(20px);
    background: white;
  }

  /* ── Delivery Settings ── */
  .delivery-item-info {
    display: flex;
    flex-direction: column;
    gap: 1px;
    flex: 1;
    min-width: 0;
  }

  .delivery-desc {
    font-size: 10px;
    color: var(--text-disabled);
  }

  .cooldown-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .cooldown-options {
    display: flex;
    gap: 4px;
    width: 100%;
  }

  .cooldown-btn {
    flex: 1;
    padding: 6px 0;
    font-size: var(--text-2xs);
    font-weight: 600;
    text-align: center;
    border-radius: var(--radius-md);
    border: 1px solid var(--border-subtle);
    background: var(--bg-surface);
    color: var(--text-tertiary);
    cursor: pointer;
    transition: all var(--duration-fast) ease;
  }

  .cooldown-btn:hover {
    border-color: var(--border-default);
    color: var(--text-secondary);
  }

  .cooldown-active {
    background: var(--accent-bg);
    color: var(--accent-bright);
    border-color: oklch(0.44 0.14 290 / 0.3);
  }

  /* ── Responsive ── */
  @media (max-width: 900px) {
    .split-layout {
      flex-direction: column;
    }

    .feed-column {
      flex: none;
      border-right: none;
      border-bottom: 1px solid var(--border-subtle);
      max-height: 60vh;
    }

    .config-column {
      flex: 1;
    }
  }
</style>
