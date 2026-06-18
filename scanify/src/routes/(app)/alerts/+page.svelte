<script lang="ts">
  import ExportToolbar from '$lib/components/ui/ExportToolbar.svelte';

  let alertConfigs = $state([
    {
      id: 'ac1',
      name: 'Momentum Breakout Scanner',
      description: 'Alerts when stocks break above key resistance with high relative volume',
      enabled: false,
    },
    {
      id: 'ac2',
      name: 'Unusual Options Activity',
      description: 'Triggers on options volume exceeding 3x open interest',
      enabled: false,
    },
    {
      id: 'ac3',
      name: 'Dark Pool Block Alerts',
      description: 'Notifies on dark pool prints exceeding $1M notional value',
      enabled: false,
    },
  ]);

  let alertHistory = $state<any[]>([]);

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

<div class="page-root">
  <!-- Header -->
  <div class="page-header">
    <h1 class="page-title">Alerts</h1>
    <div class="header-actions">
      <ExportToolbar source="alerts" />
      <div class="header-divider"></div>
      <span class="header-status">
        {alertConfigs.filter(a => a.enabled).length} active
      </span>
    </div>
  </div>

  <div class="page-content">
    <!-- Active Alerts Section -->
    <div class="section">
      <h2 class="section-title">Active Alerts</h2>
      <div class="alert-config-list">
        {#each alertConfigs as config (config.id)}
          <div class="panel alert-config-row">
            <!-- Status indicator -->
            <div
              class="status-dot"
              style="background: {config.enabled ? 'var(--bullish)' : 'var(--text-disabled)'};"
            ></div>

            <!-- Info -->
            <div class="alert-config-info">
              <div class="alert-config-name">{config.name}</div>
              <div class="alert-config-desc">{config.description}</div>
            </div>

            <!-- Toggle -->
            <button
              type="button"
              role="switch"
              aria-checked={config.enabled}
              onclick={() => toggleAlert(config.id)}
              class="toggle-track"
              style="background: {config.enabled ? 'oklch(0.55 0.15 145)' : 'oklch(0.24 0 0)'};"
            >
              <span
                class="toggle-thumb"
                style="transform: translateX({config.enabled ? '20px' : '2px'});"
              ></span>
            </button>
          </div>
        {/each}
      </div>
    </div>

    <!-- Alert History Section -->
    <div class="section">
      <h2 class="section-title">Alert History</h2>
      {#if alertHistory.length === 0}
        <div class="panel empty-state">
          <div class="empty-state-icon">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
          </div>
          <p class="empty-state-title">No alerts yet</p>
          <p class="empty-state-desc">Alerts will appear here when scanner signals match your active alert rules</p>
        </div>
      {:else}
        <div class="alert-history-list">
          {#each alertHistory as alert (alert.id)}
            <div
              class="panel alert-history-row"
              style="border-left: 3px solid {typeColor(alert.type)};"
            >
              <!-- Direction dot -->
              <div class="direction-dot" style="background: {typeColor(alert.type)};"></div>

              <!-- Content -->
              <div class="alert-history-content">
                <div class="alert-history-header">
                  <span class="alert-symbol">{alert.symbol}</span>
                  <span
                    class="alert-type-badge"
                    style="background: {typeBg(alert.type)}; color: {typeColor(alert.type)};
                           border: 1px solid {typeBorder(alert.type)};"
                  >
                    {alert.type}
                  </span>
                </div>
                <p class="alert-message">{alert.message}</p>
              </div>

              <!-- Timestamp -->
              <span class="alert-timestamp">{alert.time}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  </div>
</div>

<style>
  .page-root {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: auto;
  }

  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    flex-shrink: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .page-title {
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--text-primary);
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .header-divider {
    width: 1px;
    height: 20px;
    background: var(--border-subtle);
  }

  .header-status {
    font-size: var(--text-xs);
    font-family: var(--font-mono);
    color: var(--text-tertiary);
  }

  .page-content {
    padding: 20px;
  }

  .page-content > * + * {
    margin-top: 24px;
  }

  .section > * + * {
    margin-top: 12px;
  }

  .section-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .alert-config-list > * + * {
    margin-top: 8px;
  }

  .alert-config-row {
    padding: 16px;
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
  }

  .alert-config-info {
    flex: 1;
    min-width: 0;
  }

  .alert-config-name {
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--text-primary);
  }

  .alert-config-desc {
    font-size: var(--text-xs);
    margin-top: 2px;
    color: var(--text-tertiary);
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
    border: none;
    cursor: pointer;
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

  .alert-history-list > * + * {
    margin-top: 8px;
  }

  .alert-history-row {
    padding: 12px 16px;
    display: flex;
    align-items: flex-start;
    gap: 12px;
  }

  .direction-dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
    margin-top: 6px;
  }

  .alert-history-content {
    flex: 1;
    min-width: 0;
  }

  .alert-history-header {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .alert-symbol {
    font-size: var(--text-sm);
    font-weight: 700;
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .alert-type-badge {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    border-radius: var(--radius-full);
    padding: 2px 8px;
  }

  .alert-message {
    font-size: var(--text-xs);
    margin-top: 4px;
    color: var(--text-secondary);
  }

  .alert-timestamp {
    font-size: 11px;
    font-family: var(--font-mono);
    flex-shrink: 0;
    color: var(--text-tertiary);
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 48px 24px;
    text-align: center;
  }

  .empty-state-icon {
    color: var(--text-disabled);
    margin-bottom: 12px;
  }

  .empty-state-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 4px;
  }

  .empty-state-desc {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    max-width: 320px;
  }
</style>
