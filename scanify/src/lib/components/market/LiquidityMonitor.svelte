<!--
  LiquidityMonitor.svelte
  Dashboard cards for key liquidity metrics: Fed Balance Sheet,
  Repo Rate, Treasury General Account (TGA), and Reverse Repo.
  Each card shows large formatted number with trend indicator.
-->
<script lang="ts">
  import { formatMarketCap } from '$lib/utils/format';

  interface LiquidityData {
    fedBalance: number;
    repoRate: number;
    tga: number;
    reverse_repo: number;
  }

  interface Props {
    data: LiquidityData;
    class?: string;
  }

  let {
    data,
    class: className = ''
  }: Props = $props();

  interface MetricCard {
    label: string;
    key: keyof LiquidityData;
    format: (v: number) => string;
    description: string;
    trendPositiveIs: 'bullish' | 'bearish';
  }

  const metrics: MetricCard[] = [
    {
      label: 'Fed Balance',
      key: 'fedBalance',
      format: formatMarketCap,
      description: 'Federal Reserve balance sheet total assets',
      trendPositiveIs: 'bullish'
    },
    {
      label: 'Repo Rate',
      key: 'repoRate',
      format: (v) => v.toFixed(2) + '%',
      description: 'Overnight repo rate benchmark',
      trendPositiveIs: 'bearish'
    },
    {
      label: 'TGA Balance',
      key: 'tga',
      format: formatMarketCap,
      description: 'Treasury General Account balance',
      trendPositiveIs: 'bearish'
    },
    {
      label: 'Reverse Repo',
      key: 'reverse_repo',
      format: formatMarketCap,
      description: 'ON RRP facility usage',
      trendPositiveIs: 'bearish'
    }
  ];

  // Simple trend indicator based on value magnitude
  function trendDirection(val: number): 'up' | 'down' | 'flat' {
    // In a real app this would compare to previous values;
    // here we derive a visual cue from the value itself for display purposes.
    if (val > 0) return 'up';
    if (val < 0) return 'down';
    return 'flat';
  }
</script>

<div class="flex flex-col gap-3 {className}">
  <div class="flex items-center justify-between px-1">
    <span class="text-sm font-semibold text-[var(--text-primary)]">Liquidity Monitor</span>
    <span class="text-2xs text-[var(--text-tertiary)]">Key liquidity indicators</span>
  </div>

  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
    {#each metrics as metric (metric.key)}
      {@const val = data[metric.key]}
      {@const trend = trendDirection(val)}
      {@const trendIsBullish = (trend === 'up' && metric.trendPositiveIs === 'bullish') || (trend === 'down' && metric.trendPositiveIs === 'bearish')}

      <div class="panel p-4 flex flex-col gap-2">
        <!-- Label -->
        <div class="flex items-center justify-between">
          <span class="text-2xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">{metric.label}</span>

          <!-- Trend arrow -->
          {#if trend === 'up'}
            <span class="flex items-center gap-0.5 text-2xs font-medium {trendIsBullish ? 'text-[var(--bullish)]' : 'text-[var(--bearish)]'}">
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                <path d="M5 2L8 6H2L5 2Z" fill="currentColor" />
              </svg>
            </span>
          {:else if trend === 'down'}
            <span class="flex items-center gap-0.5 text-2xs font-medium {trendIsBullish ? 'text-[var(--bullish)]' : 'text-[var(--bearish)]'}">
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                <path d="M5 8L2 4H8L5 8Z" fill="currentColor" />
              </svg>
            </span>
          {:else}
            <span class="text-2xs text-[var(--text-disabled)]">--</span>
          {/if}
        </div>

        <!-- Value -->
        <div class="mono-nums text-xl font-bold text-[var(--text-primary)]">
          {metric.format(val)}
        </div>

        <!-- Description -->
        <span class="text-2xs text-[var(--text-tertiary)] leading-snug">{metric.description}</span>
      </div>
    {/each}
  </div>
</div>
