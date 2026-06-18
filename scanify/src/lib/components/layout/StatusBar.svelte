<!--
  StatusBar.svelte
  Bottom status bar (28px) — Bloomberg Terminal-grade information density.
  Shows connection, market phase, countdown, clock, CPU/mem, signal bars,
  scan count, latency, keyboard hint, and version.
-->
<script lang="ts">
  import {
    Lightning,
    Clock,
    Cpu,
    Pulse,
    Command,
    WifiHigh,
    WifiMedium,
    WifiLow,
    WifiNone,
  } from 'phosphor-svelte';

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

  // ---- Real-time clock (ticks every second) ----
  let currentTime = $state('--:--:-- ET');

  $effect(() => {
    function updateClock() {
      const now = new Date();
      currentTime = now.toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        timeZone: 'America/New_York',
      }) + ' ET';
    }
    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  });

  // ---- Market session countdown ----
  let sessionCountdown = $state('');

  $effect(() => {
    function computeCountdown(): string {
      const now = new Date();
      const et = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
      const day = et.getDay();
      const hours = et.getHours();
      const minutes = et.getMinutes();
      const totalMinutes = hours * 60 + minutes;

      // Weekend
      if (day === 0 || day === 6) return '';

      // Pre-market 4:00-9:30 — count down to open
      if (totalMinutes >= 240 && totalMinutes < 570) {
        const remaining = 570 - totalMinutes;
        const h = Math.floor(remaining / 60);
        const m = remaining % 60;
        return h > 0 ? `Opens in ${h}h ${m}m` : `Opens in ${m}m`;
      }

      // Regular 9:30-16:00 — count down to close
      if (totalMinutes >= 570 && totalMinutes < 960) {
        const remaining = 960 - totalMinutes;
        const h = Math.floor(remaining / 60);
        const m = remaining % 60;
        return h > 0 ? `Closes in ${h}h ${m}m` : `Closes in ${m}m`;
      }

      // After-hours 16:00-20:00
      if (totalMinutes >= 960 && totalMinutes < 1200) {
        const remaining = 1200 - totalMinutes;
        const h = Math.floor(remaining / 60);
        const m = remaining % 60;
        return h > 0 ? `AH ends ${h}h ${m}m` : `AH ends ${m}m`;
      }

      return '';
    }

    sessionCountdown = computeCountdown();
    const interval = setInterval(() => {
      sessionCountdown = computeCountdown();
    }, 15_000);
    return () => clearInterval(interval);
  });

  // ---- Simulated CPU / Memory ----
  let cpuUsage = $state(23);
  let memUsage = $state(67);

  $effect(() => {
    const interval = setInterval(() => {
      cpuUsage = Math.min(99, Math.max(5, cpuUsage + Math.round((Math.random() - 0.48) * 8)));
      memUsage = Math.min(95, Math.max(40, memUsage + Math.round((Math.random() - 0.5) * 3)));
    }, 3000);
    return () => clearInterval(interval);
  });

  // ---- Simulated connection quality (1-5 bars) ----
  let connectionQuality = $state(4);

  $effect(() => {
    const interval = setInterval(() => {
      if (connectionStatus === 'connected') {
        // Fluctuate between 3-5
        connectionQuality = Math.min(5, Math.max(3, connectionQuality + Math.round((Math.random() - 0.4) * 2)));
      } else if (connectionStatus === 'connecting') {
        connectionQuality = 2;
      } else {
        connectionQuality = 0;
      }
    }, 5000);
    return () => clearInterval(interval);
  });

  // Derived: human-readable connection label
  let connectionLabel = $derived(
    connectionStatus === 'connected'    ? 'Connected' :
    connectionStatus === 'connecting'   ? 'Connecting...' :
    connectionStatus === 'disconnected' ? 'Disconnected' :
    'Error'
  );

  // Derived: connection dot color class
  let connectionDotClass = $derived(
    connectionStatus === 'connected'    ? 'status-bar__dot--connected' :
    connectionStatus === 'connecting'   ? 'status-bar__dot--connecting' :
    connectionStatus === 'disconnected' ? 'status-bar__dot--disconnected' :
    'status-bar__dot--error'
  );

  // Derived: market phase label
  let marketPhaseLabel = $derived(
    marketPhase === 'pre'     ? 'Pre-Mkt' :
    marketPhase === 'regular' ? 'Regular' :
    marketPhase === 'post'    ? 'After-Hrs' :
    'Closed'
  );

  // Derived: market phase color class
  let marketPhaseClass = $derived(
    marketPhase === 'regular' ? 'status-bar__phase--regular' :
    marketPhase === 'pre' || marketPhase === 'post' ? 'status-bar__phase--extended' :
    'status-bar__phase--closed'
  );

  // Derived: formatted last-update timestamp
  let formattedTime = $derived.by(() => {
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

  // Derived: CPU color class
  let cpuClass = $derived(
    cpuUsage <= 40 ? 'status-bar__metric--good' :
    cpuUsage <= 70 ? 'status-bar__metric--moderate' :
    'status-bar__metric--poor'
  );

  // Derived: Memory color class
  let memClass = $derived(
    memUsage <= 60 ? 'status-bar__metric--good' :
    memUsage <= 80 ? 'status-bar__metric--moderate' :
    'status-bar__metric--poor'
  );
</script>

<div class="status-bar {className}" role="status" aria-label="Application status">
  <!-- Left section: connection + market + countdown -->
  <div class="status-bar__left">
    <!-- Connection status -->
    <div class="status-bar__segment">
      <span class="status-bar__dot {connectionDotClass}" aria-hidden="true"></span>
      <span class="status-bar__label">{connectionLabel}</span>
    </div>

    <span class="status-bar__separator" aria-hidden="true"></span>

    <!-- Signal quality bars -->
    <div class="status-bar__segment status-bar__signal" title="Connection quality: {connectionQuality}/5">
      {#each [1, 2, 3, 4, 5] as bar}
        <span
          class="status-bar__signal-bar"
          class:status-bar__signal-bar--active={bar <= connectionQuality}
          style="height: {4 + bar * 2}px"
          aria-hidden="true"
        ></span>
      {/each}
    </div>

    <span class="status-bar__separator" aria-hidden="true"></span>

    <!-- Market phase -->
    <div class="status-bar__segment">
      <span class="status-bar__phase-dot {marketPhaseClass}" aria-hidden="true"></span>
      <span class="status-bar__label {marketPhaseClass}">{marketPhaseLabel}</span>
    </div>

    <!-- Session countdown -->
    {#if sessionCountdown}
      <span class="status-bar__separator" aria-hidden="true"></span>
      <div class="status-bar__segment">
        <span class="status-bar__countdown">{sessionCountdown}</span>
      </div>
    {/if}
  </div>

  <!-- Center section: clock -->
  <div class="status-bar__center">
    <div class="status-bar__segment status-bar__clock-segment">
      <span class="status-bar__icon" aria-hidden="true">
        <Clock size={12} weight="bold" />
      </span>
      <span class="status-bar__clock">{currentTime}</span>
    </div>
  </div>

  <!-- Right section: CPU/mem + scans + latency + shortcut + version -->
  <div class="status-bar__right">
    <!-- CPU / Memory -->
    <div class="status-bar__segment" title="CPU: {cpuUsage}% | Memory: {memUsage}%">
      <span class="status-bar__icon" aria-hidden="true">
        <Cpu size={11} weight="regular" />
      </span>
      <span class="status-bar__value {cpuClass}">{cpuUsage}%</span>
      <span class="status-bar__micro-sep" aria-hidden="true">/</span>
      <span class="status-bar__value {memClass}">{memUsage}%</span>
    </div>

    <span class="status-bar__separator" aria-hidden="true"></span>

    <!-- Active scan count -->
    <div class="status-bar__segment">
      <span class="status-bar__icon" aria-hidden="true">
        <Pulse size={11} weight="bold" />
      </span>
      <span class="status-bar__label">Scans</span>
      <span class="status-bar__value status-bar__scan-count">{activeScanCount}</span>
    </div>

    <span class="status-bar__separator" aria-hidden="true"></span>

    <!-- WebSocket latency -->
    <div class="status-bar__segment">
      <span class="status-bar__icon" aria-hidden="true">
        <Lightning size={11} weight="fill" />
      </span>
      <span class="status-bar__value {latencyClass}">{wsLatency}ms</span>
    </div>

    <span class="status-bar__separator" aria-hidden="true"></span>

    <!-- Last update -->
    <div class="status-bar__segment">
      <span class="status-bar__label">Upd</span>
      <span class="status-bar__value">{formattedTime}</span>
    </div>

    <span class="status-bar__separator" aria-hidden="true"></span>

    <!-- Keyboard shortcut hint -->
    <div class="status-bar__segment status-bar__kbd-hint">
      <kbd class="status-bar__kbd">
        <span class="status-bar__kbd-icon" aria-hidden="true">
          <Command size={9} weight="bold" />
        </span>
        K
      </kbd>
      <span class="status-bar__label">Search</span>
    </div>

    <span class="status-bar__separator" aria-hidden="true"></span>

    <!-- Version -->
    <div class="status-bar__segment">
      <span class="status-bar__version">v2.0.0</span>
    </div>
  </div>
</div>

<style>
  .status-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 28px;
    padding: 0 10px;
    background-color: var(--bg-base);
    border-top: 1px solid var(--border-subtle);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-variant-numeric: tabular-nums lining-nums;
    color: var(--text-tertiary);
    user-select: none;
    gap: 4px;
  }

  .status-bar__left,
  .status-bar__center,
  .status-bar__right {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .status-bar__left {
    flex: 1;
    justify-content: flex-start;
  }

  .status-bar__center {
    flex-shrink: 0;
  }

  .status-bar__right {
    flex: 1;
    justify-content: flex-end;
  }

  .status-bar__segment {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .status-bar__separator {
    width: 1px;
    height: 12px;
    background-color: var(--border-subtle);
    flex-shrink: 0;
  }

  .status-bar__micro-sep {
    color: var(--text-disabled);
    font-size: 9px;
    line-height: 1;
  }

  .status-bar__label {
    color: var(--text-tertiary);
    letter-spacing: 0.02em;
  }

  .status-bar__value {
    color: var(--text-secondary);
  }

  .status-bar__icon {
    display: flex;
    align-items: center;
    color: var(--text-disabled);
    line-height: 0;
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
    animation: sb-pulse-loading 1.8s ease-in-out infinite;
  }

  .status-bar__dot--disconnected {
    background-color: var(--text-disabled);
  }

  .status-bar__dot--error {
    background-color: var(--bearish);
    box-shadow: 0 0 6px var(--bearish-dim);
  }

  @keyframes sb-pulse-loading {
    0%, 100% { opacity: 0.4; }
    50%      { opacity: 1; }
  }

  /* ---- Signal quality bars ---- */
  .status-bar__signal {
    gap: 1px;
    align-items: flex-end;
    height: 14px;
    padding: 0 2px;
  }

  .status-bar__signal-bar {
    width: 3px;
    border-radius: 1px;
    background-color: var(--text-disabled);
    transition: background-color 300ms ease;
  }

  .status-bar__signal-bar--active {
    background-color: var(--bullish);
    box-shadow: 0 0 3px oklch(0.64 0.16 155 / 0.3);
  }

  /* ---- Market phase dot & colors ---- */
  .status-bar__phase-dot {
    width: 5px;
    height: 5px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
  }

  .status-bar__phase--regular {
    color: var(--bullish);
    background-color: var(--bullish);
  }

  .status-bar__phase--extended {
    color: var(--warning);
    background-color: var(--warning);
  }

  .status-bar__phase--closed {
    color: var(--text-disabled);
    background-color: var(--text-disabled);
  }

  /* ---- Countdown ---- */
  .status-bar__countdown {
    color: var(--warning);
    font-weight: 600;
    letter-spacing: 0.01em;
  }

  /* ---- Clock ---- */
  .status-bar__clock-segment {
    gap: 5px;
  }

  .status-bar__clock {
    color: var(--text-secondary);
    font-weight: 600;
    letter-spacing: 0.04em;
    font-size: var(--text-xs);
  }

  /* ---- CPU / Memory metric colors ---- */
  .status-bar__metric--good {
    color: var(--bullish);
  }

  .status-bar__metric--moderate {
    color: var(--warning);
  }

  .status-bar__metric--poor {
    color: var(--bearish);
  }

  /* ---- Scan count badge ---- */
  .status-bar__scan-count {
    min-width: 14px;
    text-align: center;
    padding: 0 3px;
    border-radius: var(--radius-xs);
    background-color: oklch(0.62 0.20 290 / 0.12);
    color: var(--accent-bright);
    font-weight: 600;
    font-size: 9px;
    line-height: 14px;
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

  /* ---- Keyboard shortcut hint ---- */
  .status-bar__kbd-hint {
    gap: 4px;
    opacity: 0.7;
    transition: opacity 150ms ease;
  }

  .status-bar__kbd-hint:hover {
    opacity: 1;
  }

  .status-bar__kbd {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    padding: 0px 4px;
    height: 16px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-xs);
    background-color: var(--bg-surface);
    color: var(--text-tertiary);
    font-family: var(--font-mono);
    font-size: 9px;
    font-weight: 600;
    line-height: 1;
  }

  .status-bar__kbd-icon {
    display: flex;
    align-items: center;
    line-height: 0;
  }

  /* ---- Version ---- */
  .status-bar__version {
    color: var(--text-disabled);
    font-size: 9px;
    letter-spacing: 0.03em;
  }
</style>
