<script lang="ts">
  let alertConfigs = $state([
    {
      id: 'ac1',
      name: 'Momentum Breakout Scanner',
      description: 'Alerts when stocks break above key resistance with high relative volume',
      enabled: true,
    },
    {
      id: 'ac2',
      name: 'Unusual Options Activity',
      description: 'Triggers on options volume exceeding 3x open interest',
      enabled: true,
    },
    {
      id: 'ac3',
      name: 'Dark Pool Block Alerts',
      description: 'Notifies on dark pool prints exceeding $1M notional value',
      enabled: false,
    },
  ]);

  const alertHistory = [
    { id: 'ah1', symbol: 'NVDA', message: 'Momentum Breakout detected at $875.30', time: '14:32:15', type: 'bullish' as const },
    { id: 'ah2', symbol: 'TSLA', message: 'Unusual put activity - 6,200 contracts at $230P', time: '14:28:43', type: 'bearish' as const },
    { id: 'ah3', symbol: 'AMD',  message: 'Relative volume spike to 2.8x average', time: '14:15:22', type: 'bullish' as const },
    { id: 'ah4', symbol: 'SPY',  message: 'Dark pool block print: 45,000 shares at $502.10', time: '13:58:07', type: 'neutral' as const },
    { id: 'ah5', symbol: 'COIN', message: 'Breakout above $225 with 3.8x relative volume', time: '13:42:51', type: 'bullish' as const },
  ];

  function typeColor(t: string): string {
    if (t === 'bullish') return 'var(--bullish)';
    if (t === 'bearish') return 'var(--bearish)';
    return 'var(--neutral)';
  }

  function typeBg(t: string): string {
    if (t === 'bullish') return 'var(--bullish-bg)';
    if (t === 'bearish') return 'var(--bearish-bg)';
    return 'var(--neutral-bg)';
  }

  function typeBorder(t: string): string {
    if (t === 'bullish') return 'oklch(0.45 0.12 155 / 0.3)';
    if (t === 'bearish') return 'oklch(0.42 0.12 25 / 0.3)';
    return 'oklch(0.45 0.08 250 / 0.3)';
  }

  function toggleAlert(id: string) {
    alertConfigs = alertConfigs.map(a =>
      a.id === id ? { ...a, enabled: !a.enabled } : a
    );
  }
</script>

<svelte:head>
  <title>Alerts - Scanify</title>
</svelte:head>

<div class="flex flex-col h-full overflow-auto">
  <!-- Header -->
  <div class="flex items-center justify-between px-5 py-3 shrink-0" style="border-bottom: 1px solid var(--border-subtle);">
    <h1 class="text-lg font-bold" style="color: var(--text-primary);">Alerts</h1>
    <span class="text-xs font-mono" style="color: var(--text-tertiary);">
      {alertConfigs.filter(a => a.enabled).length} active
    </span>
  </div>

  <div class="p-5 space-y-6">
    <!-- Active Alerts Section -->
    <div class="space-y-3">
      <h2 class="text-sm font-semibold" style="color: var(--text-primary);">Active Alerts</h2>
      <div class="space-y-2">
        {#each alertConfigs as config (config.id)}
          <div class="panel p-4 flex items-center gap-4">
            <!-- Status indicator -->
            <div
              class="w-2 h-2 rounded-full shrink-0"
              style="background: {config.enabled ? 'var(--bullish)' : 'var(--text-disabled)'};"
            ></div>

            <!-- Info -->
            <div class="flex-1 min-w-0">
              <div class="text-sm font-medium" style="color: var(--text-primary);">{config.name}</div>
              <div class="text-xs mt-0.5" style="color: var(--text-tertiary);">{config.description}</div>
            </div>

            <!-- Toggle -->
            <button
              type="button"
              role="switch"
              aria-checked={config.enabled}
              onclick={() => toggleAlert(config.id)}
              class="relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-200"
              style="background: {config.enabled ? 'oklch(0.55 0.15 145)' : 'oklch(0.24 0 0)'};"
            >
              <span
                class="inline-block h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200"
                style="transform: translateX({config.enabled ? '20px' : '2px'});"
              ></span>
            </button>
          </div>
        {/each}
      </div>
    </div>

    <!-- Alert History Section -->
    <div class="space-y-3">
      <h2 class="text-sm font-semibold" style="color: var(--text-primary);">Alert History</h2>
      <div class="space-y-2">
        {#each alertHistory as alert (alert.id)}
          <div
            class="panel px-4 py-3 flex items-start gap-3"
            style="border-left: 3px solid {typeColor(alert.type)};"
          >
            <!-- Direction dot -->
            <div class="w-2 h-2 rounded-full shrink-0 mt-1.5" style="background: {typeColor(alert.type)};"></div>

            <!-- Content -->
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-sm font-bold font-mono" style="color: var(--text-primary);">{alert.symbol}</span>
                <span
                  class="text-[10px] font-semibold uppercase rounded-full px-2 py-0.5"
                  style="background: {typeBg(alert.type)}; color: {typeColor(alert.type)};
                         border: 1px solid {typeBorder(alert.type)};"
                >
                  {alert.type}
                </span>
              </div>
              <p class="text-xs mt-1" style="color: var(--text-secondary);">{alert.message}</p>
            </div>

            <!-- Timestamp -->
            <span class="text-[11px] font-mono shrink-0" style="color: var(--text-tertiary);">{alert.time}</span>
          </div>
        {/each}
      </div>
    </div>
  </div>
</div>
