// ---------------------------------------------------------------------------
// User preferences store – Svelte 5 rune-based reactive state
// Persisted to localStorage, loaded on init
// ---------------------------------------------------------------------------

import { browser } from '$app/environment';

export type Theme = 'dark' | 'light' | 'high-contrast' | 'oled';

export type Locale =
  | 'en-US'
  | 'en-GB'
  | 'de-DE'
  | 'fr-FR'
  | 'ja-JP'
  | 'zh-CN'
  | 'es-ES'
  | 'pt-BR'
  | 'ko-KR';

export type NumberFormat = 'standard' | 'compact' | 'scientific';

export type DateFormatStyle = 'absolute' | 'relative' | 'mixed';

export interface ChartPreferences {
  /** Default chart type. */
  defaultChartType: 'candle' | 'line' | 'bar' | 'heikin-ashi';
  /** Show volume sub-chart. */
  showVolume: boolean;
  /** Show grid lines. */
  showGrid: boolean;
  /** Enable crosshair. */
  crosshairEnabled: boolean;
  /** Default time frame. */
  defaultTimeframe: '1m' | '5m' | '15m' | '1h' | '4h' | '1D' | '1W';
}

export interface NotificationPreferences {
  /** Enable browser push notifications. */
  pushEnabled: boolean;
  /** Enable email notifications. */
  emailEnabled: boolean;
  /** Enable in-app toast notifications. */
  toastEnabled: boolean;
  /** Duration toasts stay visible (ms). */
  toastDuration: number;
  /** Maximum simultaneous toasts. */
  maxToasts: number;
}

export interface AccessibilityPreferences {
  /** Reduce motion for animations. */
  reduceMotion: boolean;
  /** High contrast mode (separate from theme). */
  highContrast: boolean;
  /** Font size scale factor (1.0 = default). */
  fontScale: number;
  /** Enable screen reader hints. */
  screenReaderHints: boolean;
}

export interface AllPreferences {
  theme: Theme;
  soundEnabled: boolean;
  soundVolume: number;
  locale: Locale;
  numberFormat: NumberFormat;
  dateFormat: DateFormatStyle;
  chart: ChartPreferences;
  notifications: NotificationPreferences;
  accessibility: AccessibilityPreferences;
  /** Scan results per page. */
  resultsPerPage: number;
  /** Auto-refresh interval in ms (0 = disabled). */
  autoRefreshInterval: number;
  /** Confirm before closing the app with active scans. */
  confirmOnExit: boolean;
  /** Show tooltips on hover. */
  showTooltips: boolean;
}

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'scanify:preferences';

function defaultPreferences(): AllPreferences {
  return {
    theme: 'dark',
    soundEnabled: true,
    soundVolume: 0.7,
    locale: 'en-US',
    numberFormat: 'standard',
    dateFormat: 'mixed',
    chart: {
      defaultChartType: 'candle',
      showVolume: true,
      showGrid: true,
      crosshairEnabled: true,
      defaultTimeframe: '5m',
    },
    notifications: {
      pushEnabled: false,
      emailEnabled: false,
      toastEnabled: true,
      toastDuration: 5000,
      maxToasts: 5,
    },
    accessibility: {
      reduceMotion: false,
      highContrast: false,
      fontScale: 1.0,
      screenReaderHints: false,
    },
    resultsPerPage: 50,
    autoRefreshInterval: 0,
    confirmOnExit: true,
    showTooltips: true,
  };
}

// ---------------------------------------------------------------------------
// Store factory
// ---------------------------------------------------------------------------

function createPreferencesStore() {
  const defaults = defaultPreferences();

  // ---- reactive state ----
  let theme = $state<Theme>(defaults.theme);
  let soundEnabled = $state(defaults.soundEnabled);
  let soundVolume = $state(defaults.soundVolume);
  let locale = $state<Locale>(defaults.locale);
  let numberFormat = $state<NumberFormat>(defaults.numberFormat);
  let dateFormat = $state<DateFormatStyle>(defaults.dateFormat);
  let chart = $state<ChartPreferences>({ ...defaults.chart });
  let notifications = $state<NotificationPreferences>({ ...defaults.notifications });
  let accessibility = $state<AccessibilityPreferences>({ ...defaults.accessibility });
  let resultsPerPage = $state(defaults.resultsPerPage);
  let autoRefreshInterval = $state(defaults.autoRefreshInterval);
  let confirmOnExit = $state(defaults.confirmOnExit);
  let showTooltips = $state(defaults.showTooltips);

  // ---- derived ----

  let isDarkMode = $derived(theme === 'dark' || theme === 'oled');
  let isHighContrast = $derived(theme === 'high-contrast' || accessibility.highContrast);
  let effectiveFontSize = $derived(Math.round(16 * accessibility.fontScale));

  /** Serialize all preferences into a single object (for export / backup). */
  let allPreferences = $derived<AllPreferences>({
    theme,
    soundEnabled,
    soundVolume,
    locale,
    numberFormat,
    dateFormat,
    chart,
    notifications,
    accessibility,
    resultsPerPage,
    autoRefreshInterval,
    confirmOnExit,
    showTooltips,
  });

  // ---- persistence ----

  function persist(): void {
    if (!browser) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(allPreferences));
    } catch {
      // Silently ignore storage errors
    }
  }

  function loadFromStorage(): void {
    if (!browser) return;
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw) as Partial<AllPreferences>;

      if (saved.theme) theme = saved.theme;
      if (saved.soundEnabled !== undefined) soundEnabled = saved.soundEnabled;
      if (saved.soundVolume !== undefined) soundVolume = saved.soundVolume;
      if (saved.locale) locale = saved.locale;
      if (saved.numberFormat) numberFormat = saved.numberFormat;
      if (saved.dateFormat) dateFormat = saved.dateFormat;
      if (saved.chart) chart = { ...defaults.chart, ...saved.chart };
      if (saved.notifications)
        notifications = { ...defaults.notifications, ...saved.notifications };
      if (saved.accessibility)
        accessibility = { ...defaults.accessibility, ...saved.accessibility };
      if (saved.resultsPerPage !== undefined) resultsPerPage = saved.resultsPerPage;
      if (saved.autoRefreshInterval !== undefined)
        autoRefreshInterval = saved.autoRefreshInterval;
      if (saved.confirmOnExit !== undefined) confirmOnExit = saved.confirmOnExit;
      if (saved.showTooltips !== undefined) showTooltips = saved.showTooltips;
    } catch {
      // Corrupt data – keep defaults
    }
  }

  // ---- actions ----

  /** Set the UI theme and apply it to the document. */
  function setTheme(newTheme: Theme): void {
    theme = newTheme;
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', newTheme);
      document.documentElement.classList.toggle(
        'dark',
        newTheme === 'dark' || newTheme === 'oled'
      );
    }
    persist();
  }

  /** Toggle sound on/off. */
  function toggleSound(): void {
    soundEnabled = !soundEnabled;
    persist();
  }

  /** Set the master sound volume (0.0 – 1.0). */
  function setVolume(volume: number): void {
    soundVolume = Math.max(0, Math.min(1, volume));
    persist();
  }

  /** Set the display locale. */
  function setLocale(newLocale: Locale): void {
    locale = newLocale;
    persist();
  }

  /** Update the number display format. */
  function setNumberFormat(format: NumberFormat): void {
    numberFormat = format;
    persist();
  }

  /** Update the date display format. */
  function setDateFormat(format: DateFormatStyle): void {
    dateFormat = format;
    persist();
  }

  /** Update chart preferences. */
  function updateChartPreferences(updates: Partial<ChartPreferences>): void {
    chart = { ...chart, ...updates };
    persist();
  }

  /** Update notification preferences. */
  function updateNotificationPreferences(updates: Partial<NotificationPreferences>): void {
    notifications = { ...notifications, ...updates };
    persist();
  }

  /** Update accessibility preferences. */
  function updateAccessibility(updates: Partial<AccessibilityPreferences>): void {
    accessibility = { ...accessibility, ...updates };
    if (typeof document !== 'undefined') {
      document.documentElement.style.fontSize = `${Math.round(16 * accessibility.fontScale)}px`;
      if (accessibility.reduceMotion) {
        document.documentElement.classList.add('reduce-motion');
      } else {
        document.documentElement.classList.remove('reduce-motion');
      }
    }
    persist();
  }

  /** Set the number of scan results shown per page. */
  function setResultsPerPage(count: number): void {
    resultsPerPage = Math.max(10, Math.min(200, count));
    persist();
  }

  /** Set the auto-refresh interval (0 disables). */
  function setAutoRefreshInterval(intervalMs: number): void {
    autoRefreshInterval = Math.max(0, intervalMs);
    persist();
  }

  /** Toggle exit confirmation. */
  function toggleConfirmOnExit(): void {
    confirmOnExit = !confirmOnExit;
    persist();
  }

  /** Toggle tooltip visibility. */
  function toggleTooltips(): void {
    showTooltips = !showTooltips;
    persist();
  }

  /** Import a full preferences object (e.g. from backup). */
  function importPreferences(prefs: Partial<AllPreferences>): void {
    if (prefs.theme) setTheme(prefs.theme);
    if (prefs.soundEnabled !== undefined) soundEnabled = prefs.soundEnabled;
    if (prefs.soundVolume !== undefined) soundVolume = prefs.soundVolume;
    if (prefs.locale) locale = prefs.locale;
    if (prefs.numberFormat) numberFormat = prefs.numberFormat;
    if (prefs.dateFormat) dateFormat = prefs.dateFormat;
    if (prefs.chart) chart = { ...chart, ...prefs.chart };
    if (prefs.notifications) notifications = { ...notifications, ...prefs.notifications };
    if (prefs.accessibility) updateAccessibility(prefs.accessibility);
    if (prefs.resultsPerPage !== undefined) resultsPerPage = prefs.resultsPerPage;
    if (prefs.autoRefreshInterval !== undefined)
      autoRefreshInterval = prefs.autoRefreshInterval;
    if (prefs.confirmOnExit !== undefined) confirmOnExit = prefs.confirmOnExit;
    if (prefs.showTooltips !== undefined) showTooltips = prefs.showTooltips;
    persist();
  }

  /** Reset all preferences to factory defaults. */
  function resetToDefaults(): void {
    const d = defaultPreferences();
    theme = d.theme;
    soundEnabled = d.soundEnabled;
    soundVolume = d.soundVolume;
    locale = d.locale;
    numberFormat = d.numberFormat;
    dateFormat = d.dateFormat;
    chart = { ...d.chart };
    notifications = { ...d.notifications };
    accessibility = { ...d.accessibility };
    resultsPerPage = d.resultsPerPage;
    autoRefreshInterval = d.autoRefreshInterval;
    confirmOnExit = d.confirmOnExit;
    showTooltips = d.showTooltips;
    persist();
  }

  /** Initialize by loading persisted preferences and applying theme to DOM. */
  function initialize(): void {
    loadFromStorage();
    // Apply theme to document
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', theme);
      document.documentElement.classList.toggle(
        'dark',
        theme === 'dark' || theme === 'oled'
      );
      document.documentElement.style.fontSize = `${Math.round(16 * accessibility.fontScale)}px`;
      if (accessibility.reduceMotion) {
        document.documentElement.classList.add('reduce-motion');
      }
    }
  }

  // ---- public API ----
  return {
    // reactive getters
    get theme() {
      return theme;
    },
    get soundEnabled() {
      return soundEnabled;
    },
    get soundVolume() {
      return soundVolume;
    },
    get locale() {
      return locale;
    },
    get numberFormat() {
      return numberFormat;
    },
    get dateFormat() {
      return dateFormat;
    },
    get chart() {
      return chart;
    },
    get notifications() {
      return notifications;
    },
    get accessibility() {
      return accessibility;
    },
    get resultsPerPage() {
      return resultsPerPage;
    },
    get autoRefreshInterval() {
      return autoRefreshInterval;
    },
    get confirmOnExit() {
      return confirmOnExit;
    },
    get showTooltips() {
      return showTooltips;
    },
    get isDarkMode() {
      return isDarkMode;
    },
    get isHighContrast() {
      return isHighContrast;
    },
    get effectiveFontSize() {
      return effectiveFontSize;
    },
    get allPreferences() {
      return allPreferences;
    },

    // actions
    setTheme,
    toggleSound,
    setVolume,
    setLocale,
    setNumberFormat,
    setDateFormat,
    updateChartPreferences,
    updateNotificationPreferences,
    updateAccessibility,
    setResultsPerPage,
    setAutoRefreshInterval,
    toggleConfirmOnExit,
    toggleTooltips,
    importPreferences,
    resetToDefaults,
    initialize,
  };
}

export const preferencesStore = createPreferencesStore();
