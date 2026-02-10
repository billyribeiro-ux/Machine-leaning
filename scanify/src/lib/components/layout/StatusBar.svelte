<!--
  StatusBar.svelte
  Bottom status bar (28px) showing connection, market phase, scan count,
  last update timestamp, and WebSocket latency.
-->
<script lang="ts">
  type ConnectionStatus = 'connected' | 'connecting' | 'disconnected' | 'error';
  type MarketPhase = 'pre' | 'regular' | 'post' | 'closed';

  interface StatusBarProps {
    /** WebSocket connection status. */
    connectionStatus?: ConnectionStatus;
    /** Current market trading phase. */
    marketPhase?: MarketPhase;
    /** Number of currently active scans. */
    activeScanCount?: number;
    /** ISO timestamp of last data update. */
    lastUpdate?: string;
    /** WebSocket round-trip latency in ms. */
    wsLatency?: number;
    /** Additional CSS classes. */
    class?: string;
  }

  let {
    connectionStatus = 'connected',
    marketPhase = 'regular',
    activeScanCount = 0,
    lastUpdate = '',
    wsLatency = 0,
    class: className = '',
  }: StatusBarProps = $props();

  // Derived: human-readable connection label
  let connectionLabel = $derived(
    connectionStatus === 'connected'   ? 'Connected' :
    connectionStatus === 'connecting'  ? 'Connecting...' :
    connectionStatus === 'disconnected'? 'Disconnected' :
    'Error'
  );

  // Derived: connection dot color class
  let connectionDotClass = $derived(
    connectionStatus === 'connected'   ? 'status-bar__dot--connected' :
    connectionStatus === 'connecting'  ? 'status-bar__dot--connecting' :
    connectionStatus === 'disconnected'? 'status-bar__dot--disconnected' :
    'status-bar__dot--error'
  );

  // Derived: market phase label
  let marketPhaseLabel = $derived(
    marketPhase === 'pre'     ? 'Pre-Market' :
    marketPhase === 'regular' ? 'Regular Hours' :
    marketPhase === 'post'    ? 'After Hours' :
    'Market Closed'
  );

  // Derived: market phase color class
  let marketPhaseClass = $derived(
    marketPhase === 'regular' ? 'status-bar__phase--regular' :
    marketPhase === 'pre' || marketPhase === 'post' ? 'status-bar__phase--extended' :
    'status-bar__phase--closed'
  );

  // Derived: formatted timestamp
  let formattedTime = $derived(() => {
    if (!lastUpdate) return '--:--:--';
    try {
      const d = new Date(lastUpdate);
      return d.toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return '--:--:--';
    }
  });

  // Derived: latency color class
  let latencyClass = $derived(
    wsLatency <= 50  ? 'status-bar__latency--good' :
    wsLatency <= 150 ? 'status-bar__latency--moderate' :
    'status-bar__latency--poor'
  );
</script>

<div class="status-bar {className}" role="status" aria-label="Application status">
  <!-- Left section: connection + market status -->
  <div class="status-bar__left">
    <!-- Connection status -->
    <div class="status-bar__segment">
      <span class="status-bar__dot {connectionDotClass}" aria-hidden="true"></span>
      <span class="status-bar__label">{connectionLabel}</span>
    </div>

    <span class="status-bar__separator" aria-hidden="true"></span>

    <!-- Market phase -->
    <div class="status-bar__segment">
      <span class="status-bar__label {marketPhaseClass}">{marketPhaseLabel}</span>
    </div>
  </div>

  <!-- Right section: scan count + latency + timestamp -->
  <div class="status-bar__right">
    <!-- Active scan count -->
    <div class="status-bar__segment">
      <span class="status-bar__label">Scans:</span>
      <span class="status-bar__value">{activeScanCount}</span>
    </div>

    <span class="status-bar__separator" aria-hidden="true"></span>

    <!-- WebSocket latency -->
    <div class="status-bar__segment">
      <span class="status-bar__label">Latency:</span>
      <span class="status-bar__value {latencyClass}">{wsLatency}ms</span>
    </div>

    <span class="status-bar__separator" aria-hidden="true"></span>

    <!-- Last update timestamp -->
    <div class="status-bar__segment">
      <span class="status-bar__value">{formattedTime()}</span>
    </div>
  </div>
</div>

<style>
  .status-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 28px;
    padding: 0 12px;
    background-color: var(--bg-base);
    border-top: 1px solid var(--border-subtle);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-variant-numeric: tabular-nums lining-nums;
    color: var(--text-tertiary);
    user-select: none;
  }

  .status-bar__left,
  .status-bar__right {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .status-bar__segment {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .status-bar__separator {
    width: 1px;
    height: 12px;
    background-color: var(--border-subtle);
    flex-shrink: 0;
  }

  .status-bar__label {
    color: var(--text-tertiary);
    letter-spacing: 0.02em;
  }

  .status-bar__value {
    color: var(--text-secondary);
  }

  /* ---- Connection dot ---- */
  .status-bar__dot {
    width: 6px;
    height: 6px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
  }

  .status-bar__dot--connected {
    background-color: var(--bullish);
    box-shadow: 0 0 6px var(--bullish-dim);
  }

  .status-bar__dot--connecting {
    background-color: var(--warning);
    animation: pulse-loading 1.8s ease-in-out infinite;
  }

  .status-bar__dot--disconnected {
    background-color: var(--text-disabled);
  }

  .status-bar__dot--error {
    background-color: var(--bearish);
    box-shadow: 0 0 6px var(--bearish-dim);
  }

  /* ---- Market phase colors ---- */
  .status-bar__phase--regular {
    color: var(--bullish);
  }

  .status-bar__phase--extended {
    color: var(--warning);
  }

  .status-bar__phase--closed {
    color: var(--text-disabled);
  }

  /* ---- Latency colors ---- */
  .status-bar__latency--good {
    color: var(--bullish);
  }

  .status-bar__latency--moderate {
    color: var(--warning);
  }

  .status-bar__latency--poor {
    color: var(--bearish);
  }
</style>
