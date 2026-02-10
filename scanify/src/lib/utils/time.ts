// ---------------------------------------------------------------------------
// Time utilities — US equity market hours helpers
// ---------------------------------------------------------------------------

/** The IANA timezone identifier for US Eastern time. */
const EASTERN_TZ = 'America/New_York';

/** Market session phases. */
export type MarketPhase = 'pre' | 'regular' | 'post' | 'closed';

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Return a Date whose `.getHours()` / `.getMinutes()` etc. reflect US Eastern
 * time. We achieve this by formatting into parts and reconstructing.
 */
function easternParts(date: Date): {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
  weekday: number;
} {
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: EASTERN_TZ,
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: 'numeric',
    minute: 'numeric',
    second: 'numeric',
    weekday: 'short',
    hour12: false,
  });

  const parts = formatter.formatToParts(date);

  const get = (type: Intl.DateTimeFormatPartTypes): string => {
    const part = parts.find((p) => p.type === type);
    return part?.value ?? '0';
  };

  // Map weekday abbreviation to JS-compatible numeric day (0 = Sun, 6 = Sat).
  const weekdayMap: Record<string, number> = {
    Sun: 0,
    Mon: 1,
    Tue: 2,
    Wed: 3,
    Thu: 4,
    Fri: 5,
    Sat: 6,
  };

  // Intl hour12:false returns "24" for midnight in some engines. Normalise.
  let hour = Number(get('hour'));
  if (hour === 24) hour = 0;

  return {
    year: Number(get('year')),
    month: Number(get('month')),
    day: Number(get('day')),
    hour,
    minute: Number(get('minute')),
    second: Number(get('second')),
    weekday: weekdayMap[get('weekday')] ?? 0,
  };
}

/** Minutes since midnight for a given hour:minute pair. */
function minutesSinceMidnight(hour: number, minute: number): number {
  return hour * 60 + minute;
}

// Market time boundaries (in minutes since midnight ET).
const PRE_MARKET_OPEN = minutesSinceMidnight(4, 0); // 04:00 ET
const MARKET_OPEN = minutesSinceMidnight(9, 30); // 09:30 ET
const MARKET_CLOSE = minutesSinceMidnight(16, 0); // 16:00 ET
const POST_MARKET_CLOSE = minutesSinceMidnight(20, 0); // 20:00 ET

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Check whether the US stock market is currently in regular trading hours
 * (09:30 -- 16:00 ET, Monday--Friday).
 *
 * This does **not** account for US federal holidays.
 */
export function isMarketOpen(now?: Date): boolean {
  return getMarketPhase(now) === 'regular';
}

/**
 * Determine the current market session phase.
 *
 * - `'pre'`     — 04:00 -- 09:29 ET, weekdays
 * - `'regular'` — 09:30 -- 15:59 ET, weekdays
 * - `'post'`    — 16:00 -- 19:59 ET, weekdays
 * - `'closed'`  — all other times (weekends & overnight)
 */
export function getMarketPhase(now?: Date): MarketPhase {
  const d = now ?? new Date();
  const { hour, minute, weekday } = easternParts(d);

  // Weekend — market is closed.
  if (weekday === 0 || weekday === 6) return 'closed';

  const mins = minutesSinceMidnight(hour, minute);

  if (mins >= MARKET_OPEN && mins < MARKET_CLOSE) return 'regular';
  if (mins >= PRE_MARKET_OPEN && mins < MARKET_OPEN) return 'pre';
  if (mins >= MARKET_CLOSE && mins < POST_MARKET_CLOSE) return 'post';

  return 'closed';
}

/**
 * Milliseconds until the next regular-session market open.
 *
 * If the market is currently in regular hours, returns `0`.
 */
export function timeUntilMarketOpen(now?: Date): number {
  const d = now ?? new Date();
  const phase = getMarketPhase(d);

  if (phase === 'regular') return 0;

  // Walk forward day-by-day until we find the next weekday,
  // then compute the difference to 09:30 ET on that day.
  const { hour, minute, second, weekday } = easternParts(d);
  const currentMins = minutesSinceMidnight(hour, minute);

  // If it's a weekday and we haven't passed market open yet, the next open
  // is today at 09:30 ET.
  if (weekday >= 1 && weekday <= 5 && currentMins < MARKET_OPEN) {
    const minsUntilOpen = MARKET_OPEN - currentMins;
    return minsUntilOpen * 60 * 1000 - second * 1000;
  }

  // Otherwise, advance to the next weekday.
  let daysToAdd: number;
  if (weekday === 5) {
    // Friday after open or post — next is Monday.
    daysToAdd = 3;
  } else if (weekday === 6) {
    // Saturday — next is Monday.
    daysToAdd = 2;
  } else if (weekday === 0) {
    // Sunday — next is Monday.
    daysToAdd = 1;
  } else {
    // Mon-Thu after close — next is tomorrow.
    daysToAdd = 1;
  }

  // Calculate ms until midnight ET, then add the remaining days + 9h30m.
  const msUntilMidnight =
    ((23 - hour) * 3600 + (59 - minute) * 60 + (60 - second)) * 1000;
  const msRemainingDays = (daysToAdd - 1) * 24 * 3600 * 1000;
  const msFromMidnightToOpen = MARKET_OPEN * 60 * 1000;

  return msUntilMidnight + msRemainingDays + msFromMidnightToOpen;
}

/**
 * Milliseconds until the regular-session market close.
 *
 * Returns `0` if the market is not in regular hours.
 */
export function timeUntilMarketClose(now?: Date): number {
  const d = now ?? new Date();
  const phase = getMarketPhase(d);

  if (phase !== 'regular') return 0;

  const { hour, minute, second } = easternParts(d);
  const currentMins = minutesSinceMidnight(hour, minute);
  const minsUntilClose = MARKET_CLOSE - currentMins;

  return minsUntilClose * 60 * 1000 - second * 1000;
}

/**
 * Convert a date to a `Date` object representing the same instant,
 * annotated with a human-readable Eastern-time string via `.toString()`.
 *
 * Note: JavaScript `Date` objects always store UTC internally. This function
 * returns the same instant; it is useful as a convenience to pair with
 * {@link formatMarketTime}.
 */
export function toMarketTime(date?: Date): Date {
  return date ?? new Date();
}

/**
 * Format a date as `HH:MM:SS ET`.
 *
 * ```ts
 * formatMarketTime() // "09:31:42 ET"
 * ```
 */
export function formatMarketTime(date?: Date): string {
  const d = date ?? new Date();

  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: EASTERN_TZ,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });

  return `${formatter.format(d)} ET`;
}
