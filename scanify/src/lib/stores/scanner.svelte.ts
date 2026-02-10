// ---------------------------------------------------------------------------
// Scanner store – Svelte 5 rune-based reactive state
// ---------------------------------------------------------------------------

import type {
  ScanResult,
  ScanConfig,
  ScanFilter,
  ScanFilterOperator,
  SortDirection,
  ScanFilterValue,
} from '$lib/types/scan';

export interface ActiveScan {
  config: ScanConfig;
  startedAt: number;
  lastTick: number;
  resultCount: number;
  status: 'running' | 'paused' | 'error';
  errorMessage?: string;
}

export interface SortConfig {
  field: string;
  direction: SortDirection;
}

// ---------------------------------------------------------------------------
// Filter evaluation helpers
// ---------------------------------------------------------------------------

function getFieldValue(result: ScanResult, field: string): unknown {
  return (result as unknown as Record<string, unknown>)[field];
}

function evaluateFilter(result: ScanResult, filter: ScanFilter): boolean {
  if (!filter.enabled) return true;

  const raw = getFieldValue(result, filter.field);
  const value = filter.value;

  switch (filter.operator) {
    case 'gt':
      return typeof raw === 'number' && raw > (value as number);
    case 'lt':
      return typeof raw === 'number' && raw < (value as number);
    case 'eq':
      return raw === value;
    case 'gte':
      return typeof raw === 'number' && raw >= (value as number);
    case 'lte':
      return typeof raw === 'number' && raw <= (value as number);
    case 'between': {
      const [lo, hi] = value as readonly [number, number];
      return typeof raw === 'number' && raw >= lo && raw <= hi;
    }
    case 'in':
      return (value as readonly (string | number | boolean)[]).includes(
        raw as string | number | boolean
      );
    case 'contains':
      return typeof raw === 'string' && raw.toLowerCase().includes((value as string).toLowerCase());
    default:
      return true;
  }
}

function compareValues(a: unknown, b: unknown, direction: SortDirection): number {
  const mult = direction === 'asc' ? 1 : -1;
  if (a === b) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (typeof a === 'number' && typeof b === 'number') return (a - b) * mult;
  return String(a).localeCompare(String(b)) * mult;
}

// ---------------------------------------------------------------------------
// Store factory
// ---------------------------------------------------------------------------

function createScannerStore() {
  // ---- reactive state ----
  let results = $state<ScanResult[]>([]);
  let activeScans = $state<Map<string, ActiveScan>>(new Map());
  let filters = $state<ScanFilter[]>([]);
  let sort = $state<SortConfig>({ field: 'timestamp', direction: 'desc' });
  let selectedResultId = $state<string | null>(null);
  let maxResults = $state<number>(5000);

  // ---- derived ----

  let filteredResults = $derived.by(() => {
    const enabledFilters = filters.filter((f) => f.enabled);
    if (enabledFilters.length === 0) return results;
    return results.filter((r) => enabledFilters.every((f) => evaluateFilter(r, f)));
  });

  let sortedResults = $derived.by(() => {
    const arr = [...filteredResults];
    arr.sort((a, b) =>
      compareValues(
        getFieldValue(a, sort.field),
        getFieldValue(b, sort.field),
        sort.direction
      )
    );
    return arr;
  });

  let resultCount = $derived(results.length);
  let filteredCount = $derived(filteredResults.length);
  let activeScanCount = $derived(activeScans.size);

  let selectedResult = $derived(
    selectedResultId ? results.find((r) => r.id === selectedResultId) ?? null : null
  );

  let categories = $derived(
    [...new Set(results.map((r) => r.category))].sort()
  );

  let symbolSet = $derived(new Set(results.map((r) => r.symbol)));

  // ---- actions ----

  /** Append a single scan result, evicting the oldest if at capacity. */
  function addScanResult(result: ScanResult): void {
    results.push(result);
    if (results.length > maxResults) {
      results = results.slice(results.length - maxResults);
    }
    // Update parent scan stats
    const parentScan = activeScans.get(result.category);
    if (parentScan) {
      parentScan.lastTick = Date.now();
      parentScan.resultCount++;
    }
  }

  /** Append many results at once (batch ingestion). */
  function addScanResults(batch: ScanResult[]): void {
    results.push(...batch);
    if (results.length > maxResults) {
      results = results.slice(results.length - maxResults);
    }
  }

  /** Remove a result by id. */
  function removeScanResult(id: string): void {
    results = results.filter((r) => r.id !== id);
    if (selectedResultId === id) selectedResultId = null;
  }

  /** Replace the full filter set. */
  function setFilters(newFilters: ScanFilter[]): void {
    filters = newFilters;
  }

  /** Add or update a single filter. If a filter with the same field + operator exists it is replaced. */
  function updateFilter(filter: ScanFilter): void {
    const idx = filters.findIndex(
      (f) => f.field === filter.field && f.operator === filter.operator
    );
    if (idx >= 0) {
      filters[idx] = filter;
    } else {
      filters.push(filter);
    }
  }

  /** Remove a filter by field + operator key. */
  function removeFilter(field: string, operator: ScanFilterOperator): void {
    filters = filters.filter(
      (f) => !(f.field === field && f.operator === operator)
    );
  }

  /** Clear all filters. */
  function clearFilters(): void {
    filters = [];
  }

  /** Set the sort configuration. */
  function setSort(field: string, direction: SortDirection): void {
    sort = { field, direction };
  }

  /** Toggle sort direction for a given field, or switch to a new field with desc. */
  function toggleSort(field: string): void {
    if (sort.field === field) {
      sort = { field, direction: sort.direction === 'asc' ? 'desc' : 'asc' };
    } else {
      sort = { field, direction: 'desc' };
    }
  }

  /** Remove all results and reset selection. */
  function clearResults(): void {
    results = [];
    selectedResultId = null;
  }

  /** Select a result by id. */
  function selectResult(id: string | null): void {
    selectedResultId = id;
  }

  // ---- active scan management ----

  /** Register a new active scan configuration. */
  function startScan(config: ScanConfig): void {
    activeScans.set(config.id, {
      config,
      startedAt: Date.now(),
      lastTick: Date.now(),
      resultCount: 0,
      status: 'running',
    });
    // Force reactivity on Map replacement
    activeScans = new Map(activeScans);
  }

  /** Pause an active scan. */
  function pauseScan(scanId: string): void {
    const scan = activeScans.get(scanId);
    if (scan) {
      scan.status = 'paused';
      activeScans = new Map(activeScans);
    }
  }

  /** Resume a paused scan. */
  function resumeScan(scanId: string): void {
    const scan = activeScans.get(scanId);
    if (scan && scan.status === 'paused') {
      scan.status = 'running';
      activeScans = new Map(activeScans);
    }
  }

  /** Stop and remove an active scan. */
  function stopScan(scanId: string): void {
    activeScans.delete(scanId);
    activeScans = new Map(activeScans);
  }

  /** Mark an active scan as errored. */
  function setScanError(scanId: string, message: string): void {
    const scan = activeScans.get(scanId);
    if (scan) {
      scan.status = 'error';
      scan.errorMessage = message;
      activeScans = new Map(activeScans);
    }
  }

  /** Set the maximum number of results to keep in memory. */
  function setMaxResults(max: number): void {
    maxResults = max;
    if (results.length > max) {
      results = results.slice(results.length - max);
    }
  }

  // ---- public API ----
  return {
    // reactive getters
    get results() {
      return results;
    },
    get filteredResults() {
      return filteredResults;
    },
    get sortedResults() {
      return sortedResults;
    },
    get resultCount() {
      return resultCount;
    },
    get filteredCount() {
      return filteredCount;
    },
    get activeScanCount() {
      return activeScanCount;
    },
    get activeScans() {
      return activeScans;
    },
    get filters() {
      return filters;
    },
    get sort() {
      return sort;
    },
    get selectedResult() {
      return selectedResult;
    },
    get selectedResultId() {
      return selectedResultId;
    },
    get categories() {
      return categories;
    },
    get symbolSet() {
      return symbolSet;
    },
    get maxResults() {
      return maxResults;
    },

    // actions
    addScanResult,
    addScanResults,
    removeScanResult,
    setFilters,
    updateFilter,
    removeFilter,
    clearFilters,
    setSort,
    toggleSort,
    clearResults,
    selectResult,
    startScan,
    pauseScan,
    resumeScan,
    stopScan,
    setScanError,
    setMaxResults,
  };
}

export const scannerStore = createScannerStore();
