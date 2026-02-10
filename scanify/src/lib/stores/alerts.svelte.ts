// ---------------------------------------------------------------------------
// Alerts store – Svelte 5 rune-based reactive state
// ---------------------------------------------------------------------------

import type {
  AlertConfig,
  AlertHistory,
  Signal,
  NotificationType,
  SoundType,
  SignalStrength,
  SignalDirection,
  DisplayPriority,
} from '$lib/types/signal';
import type { ScanCategory } from '$lib/types/scan';

/** Runtime state for a single alert rule (extends persisted config). */
export interface AlertRule extends AlertConfig {
  /** Number of times this alert has fired since creation. */
  fireCount: number;
  /** ISO-8601 timestamp of last fire, or null if never. */
  lastFiredAt: string | null;
  /** Cooldown period in ms (suppress re-fires within this window). */
  cooldownMs: number;
}

/** Filter for viewing alert history. */
export interface AlertHistoryFilter {
  acknowledged: 'all' | 'read' | 'unread';
  categories: ScanCategory[];
  directions: SignalDirection[];
  minStrength: SignalStrength;
  dateRange: { from: string | null; to: string | null };
}

// ---------------------------------------------------------------------------
// Store factory
// ---------------------------------------------------------------------------

function createAlertsStore() {
  // ---- reactive state ----
  let rules = $state<AlertRule[]>([]);
  let history = $state<AlertHistory[]>([]);
  let maxHistory = $state(500);
  let isMuted = $state(false);
  let historyFilter = $state<AlertHistoryFilter>({
    acknowledged: 'all',
    categories: [],
    directions: [],
    minStrength: 1,
    dateRange: { from: null, to: null },
  });

  // ---- derived ----

  /** Number of unread (unacknowledged) alerts. */
  let unreadCount = $derived(
    history.filter((h) => h.acknowledgedAt === null).length
  );

  /** Only active alert rules. */
  let activeRules = $derived(rules.filter((r) => r.isActive));

  /** Number of active rules. */
  let activeRuleCount = $derived(activeRules.length);

  /** Alert history filtered by current criteria. */
  let filteredHistory = $derived.by(() => {
    return history.filter((entry) => {
      // Acknowledged filter
      if (
        historyFilter.acknowledged === 'read' &&
        entry.acknowledgedAt === null
      )
        return false;
      if (
        historyFilter.acknowledged === 'unread' &&
        entry.acknowledgedAt !== null
      )
        return false;

      // Category filter
      if (
        historyFilter.categories.length > 0 &&
        !historyFilter.categories.includes(entry.signal.category)
      )
        return false;

      // Direction filter
      if (
        historyFilter.directions.length > 0 &&
        !historyFilter.directions.includes(entry.signal.direction)
      )
        return false;

      // Strength filter
      if (entry.signal.strength < historyFilter.minStrength) return false;

      // Date range
      if (historyFilter.dateRange.from) {
        if (entry.signal.timestamp < historyFilter.dateRange.from) return false;
      }
      if (historyFilter.dateRange.to) {
        if (entry.signal.timestamp > historyFilter.dateRange.to) return false;
      }

      return true;
    });
  });

  /** Total number of history entries. */
  let historyCount = $derived(history.length);

  /** Most recent unread alerts (top 10). */
  let recentUnread = $derived(
    history
      .filter((h) => h.acknowledgedAt === null)
      .slice(0, 10)
  );

  // ---- helpers ----

  function isOnCooldown(rule: AlertRule): boolean {
    if (!rule.lastFiredAt || rule.cooldownMs <= 0) return false;
    return Date.now() - new Date(rule.lastFiredAt).getTime() < rule.cooldownMs;
  }

  function generateId(): string {
    return `alert_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  }

  // ---- actions ----

  /**
   * Process an incoming signal against all active alert rules.
   * Returns the history entries created (if any).
   */
  function processSignal(signal: Signal): AlertHistory[] {
    const fired: AlertHistory[] = [];

    for (const rule of rules) {
      if (!rule.isActive) continue;
      if (isOnCooldown(rule)) continue;

      // Check scan ID membership
      if (rule.scanIds.length > 0 && !rule.scanIds.includes(signal.scanId)) continue;

      // Check minimum strength
      if (signal.strength < rule.minStrength) continue;

      // Check direction filter
      if (rule.directions.length > 0 && !rule.directions.includes(signal.direction)) continue;

      // Check category filter
      if (rule.categories.length > 0 && !rule.categories.includes(signal.category)) continue;

      // Alert matches – fire it
      const notificationType: NotificationType = rule.pushEnabled
        ? 'push'
        : rule.emailEnabled
          ? 'email'
          : 'sound';

      const entry: AlertHistory = {
        id: generateId(),
        signal,
        acknowledgedAt: null,
        notificationType,
      };

      history.unshift(entry);
      fired.push(entry);

      // Update rule stats
      rule.fireCount++;
      rule.lastFiredAt = new Date().toISOString();
    }

    // Trim history
    if (history.length > maxHistory) {
      history = history.slice(0, maxHistory);
    }

    return fired;
  }

  /** Add a new alert from a signal (manual / one-off). */
  function addAlert(signal: Signal, notificationType: NotificationType = 'sound'): string {
    const id = generateId();
    const entry: AlertHistory = {
      id,
      signal,
      acknowledgedAt: null,
      notificationType,
    };
    history.unshift(entry);
    if (history.length > maxHistory) {
      history = history.slice(0, maxHistory);
    }
    return id;
  }

  /** Mark a single alert as acknowledged. */
  function acknowledgeAlert(alertId: string): void {
    const entry = history.find((h) => h.id === alertId);
    if (entry && entry.acknowledgedAt === null) {
      // Replace the entry to trigger reactivity
      const idx = history.indexOf(entry);
      history[idx] = {
        ...entry,
        acknowledgedAt: new Date().toISOString(),
      };
    }
  }

  /** Mark all unread alerts as acknowledged. */
  function acknowledgeAll(): void {
    const now = new Date().toISOString();
    history = history.map((h) =>
      h.acknowledgedAt === null ? { ...h, acknowledgedAt: now } : h
    );
  }

  /** Configure a new alert rule. */
  function configureAlert(config: Omit<AlertConfig, 'id'>): string {
    const id = generateId();
    const rule: AlertRule = {
      ...config,
      id,
      fireCount: 0,
      lastFiredAt: null,
      cooldownMs: 5000, // 5 second default cooldown
    };
    rules.push(rule);
    return id;
  }

  /** Update an existing alert rule. */
  function updateRule(ruleId: string, updates: Partial<Omit<AlertRule, 'id'>>): boolean {
    const idx = rules.findIndex((r) => r.id === ruleId);
    if (idx < 0) return false;
    rules[idx] = { ...rules[idx], ...updates };
    return true;
  }

  /** Remove an alert rule. */
  function removeAlert(ruleId: string): void {
    rules = rules.filter((r) => r.id !== ruleId);
  }

  /** Remove a history entry. */
  function removeHistoryEntry(entryId: string): void {
    history = history.filter((h) => h.id !== entryId);
  }

  /** Clear all history entries. */
  function clearHistory(): void {
    history = [];
  }

  /** Toggle an alert rule's active state. */
  function toggleRule(ruleId: string): void {
    const rule = rules.find((r) => r.id === ruleId);
    if (rule) {
      const idx = rules.indexOf(rule);
      rules[idx] = { ...rule, isActive: !rule.isActive };
    }
  }

  /** Set the history filter criteria. */
  function setHistoryFilter(updates: Partial<AlertHistoryFilter>): void {
    historyFilter = { ...historyFilter, ...updates };
  }

  /** Toggle global mute. */
  function toggleMute(): void {
    isMuted = !isMuted;
  }

  /** Set the cooldown for a specific rule. */
  function setCooldown(ruleId: string, cooldownMs: number): void {
    const idx = rules.findIndex((r) => r.id === ruleId);
    if (idx >= 0) {
      rules[idx] = { ...rules[idx], cooldownMs };
    }
  }

  // ---- public API ----
  return {
    // reactive getters
    get rules() {
      return rules;
    },
    get activeRules() {
      return activeRules;
    },
    get activeRuleCount() {
      return activeRuleCount;
    },
    get history() {
      return history;
    },
    get filteredHistory() {
      return filteredHistory;
    },
    get historyCount() {
      return historyCount;
    },
    get unreadCount() {
      return unreadCount;
    },
    get recentUnread() {
      return recentUnread;
    },
    get isMuted() {
      return isMuted;
    },
    get historyFilter() {
      return historyFilter;
    },

    // actions
    processSignal,
    addAlert,
    acknowledgeAlert,
    acknowledgeAll,
    configureAlert,
    updateRule,
    removeAlert,
    removeHistoryEntry,
    clearHistory,
    toggleRule,
    setHistoryFilter,
    toggleMute,
    setCooldown,
  };
}

export const alertsStore = createAlertsStore();
