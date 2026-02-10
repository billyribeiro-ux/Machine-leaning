// ---------------------------------------------------------------------------
// Options store – Svelte 5 rune-based reactive state
// ---------------------------------------------------------------------------

/** A single options contract in a chain. */
export interface OptionsContract {
  /** Unique contract identifier (e.g. "AAPL240119C00200000"). */
  contractId: string;
  /** Underlying symbol. */
  symbol: string;
  /** Strike price. */
  strike: number;
  /** Expiration date ISO-8601. */
  expiration: string;
  /** "call" or "put". */
  type: 'call' | 'put';
  /** Last traded price. */
  last: number;
  /** Bid price. */
  bid: number;
  /** Ask price. */
  ask: number;
  /** Bid/ask midpoint. */
  mid: number;
  /** Today's volume. */
  volume: number;
  /** Open interest. */
  openInterest: number;
  /** Implied volatility (0-1 scale, e.g. 0.35 = 35%). */
  impliedVolatility: number;
  /** Greeks. */
  greeks: Greeks;
  /** ISO-8601 timestamp of last update. */
  updatedAt: string;
}

/** Black-Scholes greeks for a single contract. */
export interface Greeks {
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  rho: number;
}

/** Full option chain for a symbol + expiration. */
export interface OptionsChain {
  /** Underlying symbol. */
  symbol: string;
  /** Underlying price at chain fetch time. */
  underlyingPrice: number;
  /** Selected expiration date ISO-8601. */
  expiration: string;
  /** All available expiration dates. */
  expirations: string[];
  /** Call contracts sorted by strike. */
  calls: OptionsContract[];
  /** Put contracts sorted by strike. */
  puts: OptionsContract[];
  /** ISO-8601 fetch timestamp. */
  fetchedAt: string;
}

/** A single options flow / unusual activity item. */
export interface OptionsFlowItem {
  /** Unique flow item id. */
  id: string;
  /** Underlying symbol. */
  symbol: string;
  /** Contract type. */
  type: 'call' | 'put';
  /** Strike price. */
  strike: number;
  /** Expiration date. */
  expiration: string;
  /** Execution price. */
  price: number;
  /** Number of contracts. */
  size: number;
  /** Total premium (price * size * 100). */
  premium: number;
  /** Trade side classification. */
  side: 'bid' | 'ask' | 'mid' | 'unknown';
  /** Sentiment inference. */
  sentiment: 'bullish' | 'bearish' | 'neutral';
  /** Whether this was flagged as unusual activity. */
  isUnusual: boolean;
  /** Whether this is a block trade. */
  isBlock: boolean;
  /** Whether this is a sweep (hitting multiple exchanges). */
  isSweep: boolean;
  /** Open interest at time of trade. */
  openInterest: number;
  /** Volume/OI ratio at time of trade. */
  volumeOIRatio: number;
  /** Implied volatility at execution. */
  impliedVolatility: number;
  /** ISO-8601 timestamp. */
  timestamp: string;
}

/** Aggregated unusual activity summary for a symbol. */
export interface UnusualActivity {
  symbol: string;
  /** Number of unusual flow items. */
  flowCount: number;
  /** Total call premium. */
  totalCallPremium: number;
  /** Total put premium. */
  totalPutPremium: number;
  /** Net sentiment score (-100 to +100). */
  sentimentScore: number;
  /** Most recent flow items contributing. */
  recentItems: OptionsFlowItem[];
  /** Last updated. */
  updatedAt: string;
}

// ---------------------------------------------------------------------------
// Store factory
// ---------------------------------------------------------------------------

function createOptionsStore() {
  // ---- reactive state ----
  let activeChain = $state<OptionsChain | null>(null);
  let flowFeed = $state<OptionsFlowItem[]>([]);
  let unusualActivity = $state<Map<string, UnusualActivity>>(new Map());
  let isLoadingChain = $state(false);
  let maxFlowItems = $state(1000);
  let flowFilter = $state<{
    minPremium: number;
    types: ('call' | 'put')[];
    sentiments: ('bullish' | 'bearish' | 'neutral')[];
    onlyUnusual: boolean;
    onlySweeps: boolean;
    symbols: string[];
  }>({
    minPremium: 0,
    types: ['call', 'put'],
    sentiments: ['bullish', 'bearish', 'neutral'],
    onlyUnusual: false,
    onlySweeps: false,
    symbols: [],
  });

  // ---- derived ----

  /** All strikes available in the current chain. */
  let chainStrikes = $derived.by(() => {
    if (!activeChain) return [];
    const strikes = new Set([
      ...activeChain.calls.map((c) => c.strike),
      ...activeChain.puts.map((p) => p.strike),
    ]);
    return [...strikes].sort((a, b) => a - b);
  });

  /** At-the-money strike (closest to underlying price). */
  let atmStrike = $derived.by(() => {
    if (!activeChain || chainStrikes.length === 0) return null;
    const price = activeChain.underlyingPrice;
    return chainStrikes.reduce((closest, strike) =>
      Math.abs(strike - price) < Math.abs(closest - price) ? strike : closest
    );
  });

  /** Total call open interest in active chain. */
  let totalCallOI = $derived(
    activeChain ? activeChain.calls.reduce((sum, c) => sum + c.openInterest, 0) : 0
  );

  /** Total put open interest in active chain. */
  let totalPutOI = $derived(
    activeChain ? activeChain.puts.reduce((sum, p) => sum + p.openInterest, 0) : 0
  );

  /** Put/Call OI ratio. */
  let putCallRatio = $derived(
    totalCallOI > 0 ? Math.round((totalPutOI / totalCallOI) * 100) / 100 : 0
  );

  /** Max pain strike (strike with maximum combined OI). */
  let maxPainStrike = $derived.by(() => {
    if (!activeChain) return null;
    const oiByStrike = new Map<number, number>();
    for (const c of activeChain.calls) {
      oiByStrike.set(c.strike, (oiByStrike.get(c.strike) ?? 0) + c.openInterest);
    }
    for (const p of activeChain.puts) {
      oiByStrike.set(p.strike, (oiByStrike.get(p.strike) ?? 0) + p.openInterest);
    }
    let maxStrike: number | null = null;
    let maxOI = 0;
    for (const [strike, oi] of oiByStrike) {
      if (oi > maxOI) {
        maxOI = oi;
        maxStrike = strike;
      }
    }
    return maxStrike;
  });

  /** Filtered flow feed based on current filter criteria. */
  let filteredFlow = $derived.by(() => {
    return flowFeed.filter((item) => {
      if (item.premium < flowFilter.minPremium) return false;
      if (!flowFilter.types.includes(item.type)) return false;
      if (!flowFilter.sentiments.includes(item.sentiment)) return false;
      if (flowFilter.onlyUnusual && !item.isUnusual) return false;
      if (flowFilter.onlySweeps && !item.isSweep) return false;
      if (flowFilter.symbols.length > 0 && !flowFilter.symbols.includes(item.symbol)) {
        return false;
      }
      return true;
    });
  });

  /** Total premium flowing through the feed (after filter). */
  let totalFlowPremium = $derived(
    filteredFlow.reduce((sum, item) => sum + item.premium, 0)
  );

  /** Net flow sentiment (-100 to +100). */
  let netFlowSentiment = $derived.by(() => {
    if (filteredFlow.length === 0) return 0;
    const bullish = filteredFlow.filter((i) => i.sentiment === 'bullish').length;
    const bearish = filteredFlow.filter((i) => i.sentiment === 'bearish').length;
    const total = bullish + bearish;
    if (total === 0) return 0;
    return Math.round(((bullish - bearish) / total) * 100);
  });

  /** Count of unusual activity symbols. */
  let unusualCount = $derived(unusualActivity.size);

  // ---- actions ----

  /** Set the active options chain. */
  function setChain(chain: OptionsChain): void {
    activeChain = chain;
    isLoadingChain = false;
  }

  /** Change the selected expiration on the active chain (triggers a refetch externally). */
  function selectExpiration(expiration: string): void {
    if (activeChain) {
      activeChain = { ...activeChain, expiration };
    }
    isLoadingChain = true;
  }

  /** Clear the active chain. */
  function clearChain(): void {
    activeChain = null;
    isLoadingChain = false;
  }

  /** Add a single flow item to the feed. */
  function addFlowItem(item: OptionsFlowItem): void {
    flowFeed.unshift(item); // newest first
    if (flowFeed.length > maxFlowItems) {
      flowFeed = flowFeed.slice(0, maxFlowItems);
    }

    // Update unusual activity aggregation
    if (item.isUnusual) {
      const existing = unusualActivity.get(item.symbol);
      if (existing) {
        const updated: UnusualActivity = {
          ...existing,
          flowCount: existing.flowCount + 1,
          totalCallPremium:
            existing.totalCallPremium + (item.type === 'call' ? item.premium : 0),
          totalPutPremium:
            existing.totalPutPremium + (item.type === 'put' ? item.premium : 0),
          recentItems: [item, ...existing.recentItems].slice(0, 20),
          updatedAt: new Date().toISOString(),
        };
        // Recalculate sentiment score
        const totalCall = updated.totalCallPremium;
        const totalPut = updated.totalPutPremium;
        const total = totalCall + totalPut;
        updated.sentimentScore =
          total > 0 ? Math.round(((totalCall - totalPut) / total) * 100) : 0;
        unusualActivity.set(item.symbol, updated);
      } else {
        unusualActivity.set(item.symbol, {
          symbol: item.symbol,
          flowCount: 1,
          totalCallPremium: item.type === 'call' ? item.premium : 0,
          totalPutPremium: item.type === 'put' ? item.premium : 0,
          sentimentScore: item.sentiment === 'bullish' ? 50 : item.sentiment === 'bearish' ? -50 : 0,
          recentItems: [item],
          updatedAt: new Date().toISOString(),
        });
      }
      unusualActivity = new Map(unusualActivity);
    }
  }

  /** Add a batch of flow items. */
  function addFlowItems(items: OptionsFlowItem[]): void {
    for (const item of items) {
      addFlowItem(item);
    }
  }

  /** Update greeks for a specific contract in the active chain. */
  function updateGreeks(contractId: string, greeks: Greeks): void {
    if (!activeChain) return;

    const callIdx = activeChain.calls.findIndex((c) => c.contractId === contractId);
    if (callIdx >= 0) {
      activeChain.calls[callIdx] = { ...activeChain.calls[callIdx], greeks };
      return;
    }

    const putIdx = activeChain.puts.findIndex((p) => p.contractId === contractId);
    if (putIdx >= 0) {
      activeChain.puts[putIdx] = { ...activeChain.puts[putIdx], greeks };
    }
  }

  /** Update the flow filter criteria. */
  function setFlowFilter(updates: Partial<typeof flowFilter>): void {
    flowFilter = { ...flowFilter, ...updates };
  }

  /** Clear the flow feed. */
  function clearFlow(): void {
    flowFeed = [];
  }

  /** Clear unusual activity data. */
  function clearUnusualActivity(): void {
    unusualActivity = new Map();
  }

  /** Set loading state for chain fetches. */
  function setLoadingChain(loading: boolean): void {
    isLoadingChain = loading;
  }

  // ---- public API ----
  return {
    // reactive getters
    get activeChain() {
      return activeChain;
    },
    get flowFeed() {
      return flowFeed;
    },
    get filteredFlow() {
      return filteredFlow;
    },
    get unusualActivity() {
      return unusualActivity;
    },
    get isLoadingChain() {
      return isLoadingChain;
    },
    get chainStrikes() {
      return chainStrikes;
    },
    get atmStrike() {
      return atmStrike;
    },
    get totalCallOI() {
      return totalCallOI;
    },
    get totalPutOI() {
      return totalPutOI;
    },
    get putCallRatio() {
      return putCallRatio;
    },
    get maxPainStrike() {
      return maxPainStrike;
    },
    get totalFlowPremium() {
      return totalFlowPremium;
    },
    get netFlowSentiment() {
      return netFlowSentiment;
    },
    get unusualCount() {
      return unusualCount;
    },
    get flowFilter() {
      return flowFilter;
    },

    // actions
    setChain,
    selectExpiration,
    clearChain,
    addFlowItem,
    addFlowItems,
    updateGreeks,
    setFlowFilter,
    clearFlow,
    clearUnusualActivity,
    setLoadingChain,
  };
}

export const optionsStore = createOptionsStore();
