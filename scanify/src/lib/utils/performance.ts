// ---------------------------------------------------------------------------
// Performance monitoring utilities
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Core Web Vitals plus supplementary metrics. */
export interface WebVitals {
  /** Largest Contentful Paint (ms). */
  readonly lcp: number | null;
  /** First Input Delay (ms). */
  readonly fid: number | null;
  /** Cumulative Layout Shift (unitless). */
  readonly cls: number | null;
  /** First Contentful Paint (ms). */
  readonly fcp: number | null;
  /** Time to First Byte (ms). */
  readonly ttfb: number | null;
}

/** Handle returned by {@link measureRenderTime}. */
export interface RenderTimeMeasure {
  /** Call when the component begins rendering. */
  start: () => void;
  /** Call when the component finishes rendering. Returns elapsed ms. */
  end: () => number;
}

// ---------------------------------------------------------------------------
// Mark / measure helpers
// ---------------------------------------------------------------------------

/** Map of open marks that have not yet been ended. */
const openMarks = new Map<string, number>();

/**
 * Record the start of a named performance span.
 *
 * Uses `performance.mark()` when available, with a fallback to `Date.now()`.
 */
export function markStart(name: string): void {
  if (typeof performance !== 'undefined' && performance.mark) {
    performance.mark(`${name}:start`);
  }
  openMarks.set(name, typeof performance !== 'undefined' ? performance.now() : Date.now());
}

/**
 * Record the end of a named performance span and return the duration in ms.
 *
 * If no matching `markStart()` call was made, returns `0`.
 */
export function markEnd(name: string): number {
  const startTime = openMarks.get(name);
  if (startTime === undefined) {
    console.warn(`[performance] markEnd called without a matching markStart for "${name}".`);
    return 0;
  }

  const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
  const duration = now - startTime;

  openMarks.delete(name);

  // Also use the browser Performance API for DevTools integration.
  if (typeof performance !== 'undefined' && performance.mark && performance.measure) {
    try {
      performance.mark(`${name}:end`);
      performance.measure(name, `${name}:start`, `${name}:end`);
    } catch {
      // Marks may have been cleared by the browser; ignore.
    }
  }

  return duration;
}

// ---------------------------------------------------------------------------
// Component render timing
// ---------------------------------------------------------------------------

/**
 * Create a scoped timer for measuring a component's render cycle.
 *
 * ```ts
 * const measure = measureRenderTime('ScanTable');
 * measure.start();
 * // ... render logic ...
 * const ms = measure.end(); // e.g. 4.32
 * ```
 */
export function measureRenderTime(component: string): RenderTimeMeasure {
  const label = `render:${component}`;

  return {
    start() {
      markStart(label);
    },
    end() {
      return markEnd(label);
    },
  };
}

// ---------------------------------------------------------------------------
// Web Vitals
// ---------------------------------------------------------------------------

/**
 * Collect a snapshot of Core Web Vitals using the browser's
 * `PerformanceObserver` API.
 *
 * Returns a promise that resolves after a short observation window (up to
 * 5 seconds). Metrics that are not available within the window are reported
 * as `null`.
 *
 * **Note:** Some metrics (FID, CLS) require user interaction; they will be
 * `null` if no interaction has occurred.
 */
export function getWebVitals(): Promise<WebVitals> {
  return new Promise<WebVitals>((resolve) => {
    const vitals: {
      lcp: number | null;
      fid: number | null;
      cls: number | null;
      fcp: number | null;
      ttfb: number | null;
    } = {
      lcp: null,
      fid: null,
      cls: null,
      fcp: null,
      ttfb: null,
    };

    // SSR guard.
    if (typeof window === 'undefined' || typeof PerformanceObserver === 'undefined') {
      resolve(vitals);
      return;
    }

    const observers: PerformanceObserver[] = [];

    // -- TTFB (from Navigation Timing) -----------------------------------

    try {
      const navEntries = performance.getEntriesByType('navigation') as PerformanceNavigationTiming[];
      if (navEntries.length > 0) {
        const nav = navEntries[0];
        if (nav) {
          vitals.ttfb = nav.responseStart - nav.requestStart;
        }
      }
    } catch {
      // Not supported.
    }

    // -- FCP (from Paint Timing) -----------------------------------------

    try {
      const paintEntries = performance.getEntriesByType('paint');
      const fcp = paintEntries.find((e) => e.name === 'first-contentful-paint');
      if (fcp) {
        vitals.fcp = fcp.startTime;
      }
    } catch {
      // Not supported.
    }

    // -- LCP --------------------------------------------------------------

    try {
      const lcpObserver = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        const last = entries[entries.length - 1];
        if (last) {
          vitals.lcp = last.startTime;
        }
      });
      lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true });
      observers.push(lcpObserver);
    } catch {
      // Not supported.
    }

    // -- FID (first-input) ------------------------------------------------

    try {
      const fidObserver = new PerformanceObserver((list) => {
        const entries = list.getEntries() as PerformanceEventTiming[];
        const first = entries[0];
        if (first) {
          vitals.fid = first.processingStart - first.startTime;
        }
      });
      fidObserver.observe({ type: 'first-input', buffered: true });
      observers.push(fidObserver);
    } catch {
      // Not supported.
    }

    // -- CLS (layout-shift) -----------------------------------------------

    try {
      let clsValue = 0;
      const clsObserver = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          const shift = entry as PerformanceEntry & {
            hadRecentInput?: boolean;
            value?: number;
          };
          if (!shift.hadRecentInput && typeof shift.value === 'number') {
            clsValue += shift.value;
          }
        }
        vitals.cls = clsValue;
      });
      clsObserver.observe({ type: 'layout-shift', buffered: true });
      observers.push(clsObserver);
    } catch {
      // Not supported.
    }

    // Resolve after a short window to let observers fire.
    setTimeout(() => {
      for (const observer of observers) {
        observer.disconnect();
      }
      resolve({ ...vitals });
    }, 5_000);
  });
}
