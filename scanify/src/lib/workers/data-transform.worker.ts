// ---------------------------------------------------------------------------
// Data Transform Worker — off-main-thread sort, filter, group, aggregate
// Scanify trading scanner
//
// Processes large arrays of record-like objects without blocking the UI.
//
// Message types: sort, filter, group, aggregate
// Returns transformed data via postMessage.
// ---------------------------------------------------------------------------

/// <reference lib="webworker" />
declare const self: DedicatedWorkerGlobalScope;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type DataRecord = { [key: string]: unknown };

interface SortParams {
  field: string;
  direction: 'asc' | 'desc';
}

interface FilterCondition {
  field: string;
  operator:
    | 'eq'
    | 'neq'
    | 'gt'
    | 'gte'
    | 'lt'
    | 'lte'
    | 'contains'
    | 'startsWith'
    | 'endsWith'
    | 'in';
  value: unknown;
}

interface FilterParams {
  conditions: FilterCondition[];
  /** When true ALL conditions must match (AND). When false ANY can match (OR). Default: true. */
  matchAll?: boolean;
}

interface GroupParams {
  field: string;
}

interface AggregateOperation {
  field: string;
  func: 'sum' | 'avg' | 'min' | 'max' | 'count' | 'median';
  alias?: string;
}

interface AggregateParams {
  operations: AggregateOperation[];
}

type TransformMessage =
  | { type: 'sort'; data: DataRecord[]; params: SortParams; requestId?: string }
  | { type: 'filter'; data: DataRecord[]; params: FilterParams; requestId?: string }
  | { type: 'group'; data: DataRecord[]; params: GroupParams; requestId?: string }
  | { type: 'aggregate'; data: DataRecord[]; params: AggregateParams; requestId?: string };

// ---------------------------------------------------------------------------
// Sort
// ---------------------------------------------------------------------------

function sortData(data: DataRecord[], params: SortParams): DataRecord[] {
  const { field, direction } = params;
  const multiplier = direction === 'asc' ? 1 : -1;

  const sorted = [...data];
  sorted.sort((a, b) => {
    const aVal = a[field];
    const bVal = b[field];

    // Handle null / undefined -- push them to the end regardless of direction.
    if (aVal == null && bVal == null) return 0;
    if (aVal == null) return 1;
    if (bVal == null) return -1;

    // String comparison.
    if (typeof aVal === 'string' && typeof bVal === 'string') {
      return aVal.localeCompare(bVal) * multiplier;
    }

    // Numeric comparison.
    if (typeof aVal === 'number' && typeof bVal === 'number') {
      return (aVal - bVal) * multiplier;
    }

    // Boolean -- true > false.
    if (typeof aVal === 'boolean' && typeof bVal === 'boolean') {
      return (aVal === bVal ? 0 : aVal ? 1 : -1) * multiplier;
    }

    // Fallback: coerce to string.
    return String(aVal).localeCompare(String(bVal)) * multiplier;
  });

  return sorted;
}

// ---------------------------------------------------------------------------
// Filter
// ---------------------------------------------------------------------------

function matchesCondition(row: DataRecord, condition: FilterCondition): boolean {
  const { field, operator, value } = condition;
  const fieldValue = row[field];

  // Null-safe: if the field is missing, only 'neq' can match.
  if (fieldValue == null) {
    return operator === 'neq' && value != null;
  }

  switch (operator) {
    case 'eq':
      return fieldValue === value;

    case 'neq':
      return fieldValue !== value;

    case 'gt':
      return typeof fieldValue === 'number' && typeof value === 'number' && fieldValue > value;

    case 'gte':
      return typeof fieldValue === 'number' && typeof value === 'number' && fieldValue >= value;

    case 'lt':
      return typeof fieldValue === 'number' && typeof value === 'number' && fieldValue < value;

    case 'lte':
      return typeof fieldValue === 'number' && typeof value === 'number' && fieldValue <= value;

    case 'contains':
      return (
        typeof fieldValue === 'string' &&
        typeof value === 'string' &&
        fieldValue.toLowerCase().includes(value.toLowerCase())
      );

    case 'startsWith':
      return (
        typeof fieldValue === 'string' &&
        typeof value === 'string' &&
        fieldValue.toLowerCase().startsWith(value.toLowerCase())
      );

    case 'endsWith':
      return (
        typeof fieldValue === 'string' &&
        typeof value === 'string' &&
        fieldValue.toLowerCase().endsWith(value.toLowerCase())
      );

    case 'in':
      return Array.isArray(value) && (value as unknown[]).includes(fieldValue);

    default:
      return false;
  }
}

function filterData(data: DataRecord[], params: FilterParams): DataRecord[] {
  const { conditions, matchAll = true } = params;

  if (conditions.length === 0) return [...data];

  return data.filter((row) => {
    if (matchAll) {
      return conditions.every((cond) => matchesCondition(row, cond));
    }
    return conditions.some((cond) => matchesCondition(row, cond));
  });
}

// ---------------------------------------------------------------------------
// Group
// ---------------------------------------------------------------------------

function groupData(
  data: DataRecord[],
  params: GroupParams,
): { [groupKey: string]: DataRecord[] } {
  const { field } = params;
  const groups: { [groupKey: string]: DataRecord[] } = {};

  for (const row of data) {
    const key = String(row[field] ?? '__null__');
    if (!groups[key]) {
      groups[key] = [];
    }
    (groups[key] as DataRecord[]).push(row);
  }

  return groups;
}

// ---------------------------------------------------------------------------
// Aggregate
// ---------------------------------------------------------------------------

function computeMedian(values: number[]): number {
  if (values.length === 0) return NaN;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) {
    return ((sorted[mid - 1] as number) + (sorted[mid] as number)) / 2;
  }
  return sorted[mid] as number;
}

function aggregateData(
  data: DataRecord[],
  params: AggregateParams,
): { [alias: string]: number } {
  const result: { [alias: string]: number } = {};

  for (const op of params.operations) {
    const { field, func, alias } = op;
    const key = alias ?? `${func}_${field}`;

    // Extract numeric values for the target field.
    const values: number[] = [];
    for (const row of data) {
      const v = row[field];
      if (typeof v === 'number' && !isNaN(v)) {
        values.push(v);
      }
    }

    switch (func) {
      case 'sum':
        result[key] = values.reduce((acc, v) => acc + v, 0);
        break;

      case 'avg':
        result[key] =
          values.length === 0
            ? NaN
            : values.reduce((acc, v) => acc + v, 0) / values.length;
        break;

      case 'min':
        result[key] = values.length === 0 ? NaN : Math.min(...values);
        break;

      case 'max':
        result[key] = values.length === 0 ? NaN : Math.max(...values);
        break;

      case 'count':
        result[key] = values.length;
        break;

      case 'median':
        result[key] = computeMedian(values);
        break;

      default:
        result[key] = NaN;
        break;
    }
  }

  return result;
}

// ---------------------------------------------------------------------------
// Message handler
// ---------------------------------------------------------------------------

self.onmessage = (event: MessageEvent<TransformMessage>): void => {
  const msg = event.data;

  let result: unknown;
  const startTime = performance.now();

  switch (msg.type) {
    case 'sort':
      result = sortData(msg.data, msg.params);
      break;

    case 'filter':
      result = filterData(msg.data, msg.params);
      break;

    case 'group':
      result = groupData(msg.data, msg.params);
      break;

    case 'aggregate':
      result = aggregateData(msg.data, msg.params);
      break;

    default:
      console.warn(
        `[data-transform] Unknown operation: ${(msg as { type: string }).type}`,
      );
      result = null;
      break;
  }

  const elapsed = performance.now() - startTime;

  self.postMessage({
    type: 'result',
    operation: msg.type,
    result,
    requestId: (msg as { requestId?: string }).requestId ?? null,
    computeTimeMs: elapsed,
  });
};

export {};
