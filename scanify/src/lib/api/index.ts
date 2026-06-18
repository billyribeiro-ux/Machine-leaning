// ---------------------------------------------------------------------------
// Configured API client singleton and typed fetch helpers
// ---------------------------------------------------------------------------

import { createApiClient } from '$lib/utils/api';
import type { ApiClient } from '$lib/utils/api';

// ---------------------------------------------------------------------------
// Singleton client
// ---------------------------------------------------------------------------

export const api: ApiClient = createApiClient({
  baseUrl: 'http://localhost:8000',
  timeout: 15_000,
});

// ---------------------------------------------------------------------------
// Response types (raw JSON shapes from the backend)
// ---------------------------------------------------------------------------

export interface DashboardData {
  priceSnapshot: unknown;
  macroSnapshot: unknown;
  sectors: unknown;
  movers: unknown;
}

export interface ScannerData {
  movers: unknown;
  screener: unknown;
}

export interface OptionsData {
  chainSummary: unknown;
  gexLevels: unknown;
  expectedMove: unknown;
}

export interface MarketData {
  breadth: unknown;
  direction: unknown;
  macroSnapshot: unknown;
  sectors: unknown;
}

export interface InstitutionalData {
  holders: unknown;
  sentiment: unknown;
}

// ---------------------------------------------------------------------------
// Fetch helpers — return raw data or null on error
// ---------------------------------------------------------------------------

export async function fetchDashboardData(): Promise<DashboardData | null> {
  try {
    const [priceSnapshot, macroSnapshot, sectors, movers] = await Promise.all([
      api.get<unknown>('/api/equity/price/snapshot'),
      api.get<unknown>('/api/equity/macro/snapshot'),
      api.get<unknown>('/api/equity/market/sectors'),
      api.get<unknown>('/api/equity/market/movers'),
    ]);

    return {
      priceSnapshot: priceSnapshot.data,
      macroSnapshot: macroSnapshot.data,
      sectors: sectors.data,
      movers: movers.data,
    };
  } catch {
    return null;
  }
}

export async function fetchScannerData(): Promise<ScannerData | null> {
  try {
    const [movers, screener] = await Promise.all([
      api.get<unknown>('/api/equity/market/movers'),
      api.get<unknown>('/api/equity/market/screener'),
    ]);

    return {
      movers: movers.data,
      screener: screener.data,
    };
  } catch {
    return null;
  }
}

export async function fetchOptionsData(): Promise<OptionsData | null> {
  try {
    const [chainSummary, gexLevels, expectedMove] = await Promise.all([
      api.get<unknown>('/api/options/chain/summary'),
      api.get<unknown>('/api/options/gex/levels'),
      api.get<unknown>('/api/options/expected-move'),
    ]);

    return {
      chainSummary: chainSummary.data,
      gexLevels: gexLevels.data,
      expectedMove: expectedMove.data,
    };
  } catch {
    return null;
  }
}

export async function fetchMarketData(): Promise<MarketData | null> {
  try {
    const [breadth, direction, macroSnapshot, sectors] = await Promise.all([
      api.get<unknown>('/api/equity/internals/breadth'),
      api.get<unknown>('/api/equity/internals/direction'),
      api.get<unknown>('/api/equity/macro/snapshot'),
      api.get<unknown>('/api/equity/market/sectors'),
    ]);

    return {
      breadth: breadth.data,
      direction: direction.data,
      macroSnapshot: macroSnapshot.data,
      sectors: sectors.data,
    };
  } catch {
    return null;
  }
}

export async function fetchInstitutionalData(): Promise<InstitutionalData | null> {
  try {
    const [holders, sentiment] = await Promise.all([
      api.get<unknown>('/api/equity/institutional/holders'),
      api.get<unknown>('/api/equity/institutional/sentiment'),
    ]);

    return {
      holders: holders.data,
      sentiment: sentiment.data,
    };
  } catch {
    return null;
  }
}
