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

<div class="liquidity-monitor {className}">
  <div class="monitor-header">
    <span class="monitor-title">Liquidity Monitor</span>
    <span class="monitor-subtitle">Key liquidity indicators</span>
  </div>

  <div class="metrics-grid">
    {#each metrics as metric (metric.key)}
      {@const val = data[metric.key]}
      {@const trend = trendDirection(val)}
      {@const trendIsBullish = (trend === 'up' && metric.trendPositiveIs === 'bullish') || (trend === 'down' && metric.trendPositiveIs === 'bearish')}

      <div class="panel metric-card">
        <!-- Label -->
        <div class="card-header">
          <span class="card-label">{metric.label}</span>

          <!-- Trend arrow -->
          {#if trend === 'up'}
            <span class="trend-icon" style="color: var({trendIsBullish ? '--bullish' : '--bearish'});">
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                <path d="M5 2L8 6H2L5 2Z" fill="currentColor" />
              </svg>
            </span>
          {:else if trend === 'down'}
            <span class="trend-icon" style="color: var({trendIsBullish ? '--bullish' : '--bearish'});">
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                <path d="M5 8L2 4H8L5 8Z" fill="currentColor" />
              </svg>
            </span>
          {:else}
            <span class="trend-flat">--</span>
          {/if}
        </div>

        <!-- Value -->
        <div class="mono-nums card-value">
          {metric.format(val)}
        </div>

        <!-- Description -->
        <span class="card-description">{metric.description}</span>
      </div>
    {/each}
  </div>
</div>

<style>
  .liquidity-monitor {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .monitor-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-inline: 4px;
  }

  .monitor-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .monitor-subtitle {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
  }

  .metrics-grid {
    display: grid;
    grid-template-columns: repeat(1, minmax(0, 1fr));
    gap: 12px;
  }

  @media (min-width: 640px) {
    .metrics-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (min-width: 1024px) {
    .metrics-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
  }

  .metric-card {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .card-label {
    font-size: var(--text-2xs);
    font-weight: 500;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .trend-icon {
    display: flex;
    align-items: center;
    gap: 2px;
    font-size: var(--text-2xs);
    font-weight: 500;
  }

  .trend-flat {
    font-size: var(--text-2xs);
    color: var(--text-disabled);
  }

  .card-value {
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--text-primary);
  }

  .card-description {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    line-height: 1.4;
  }
</style>
