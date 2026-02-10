// ---------------------------------------------------------------------------
// Storage abstraction — safe localStorage wrapper
// ---------------------------------------------------------------------------

/**
 * Retrieve a JSON-serialised value from localStorage.
 *
 * Returns `null` when:
 *  - the key does not exist
 *  - parsing fails
 *  - localStorage is unavailable (SSR, disabled, etc.)
 *
 * ```ts
 * const theme = getItem<'dark' | 'light'>('theme');
 * ```
 */
export function getItem<T>(key: string): T | null {
  try {
    if (typeof window === 'undefined') return null;
    const raw = localStorage.getItem(key);
    if (raw === null) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

/**
 * Store a value in localStorage, JSON-serialised.
 *
 * Silently swallows errors caused by SSR, quota limits, or disabled storage.
 *
 * ```ts
 * setItem('theme', 'dark');
 * setItem('filters', { minVolume: 1_000_000 });
 * ```
 */
export function setItem<T>(key: string, value: T): void {
  try {
    if (typeof window === 'undefined') return;
    localStorage.setItem(key, JSON.stringify(value));
  } catch (err) {
    // Quota exceeded or storage disabled — log and move on.
    console.warn(`[storage] Failed to set "${key}":`, err);
  }
}

/**
 * Remove a key from localStorage.
 *
 * Silently swallows errors.
 */
export function removeItem(key: string): void {
  try {
    if (typeof window === 'undefined') return;
    localStorage.removeItem(key);
  } catch {
    // Ignore — nothing to do if removal fails.
  }
}
