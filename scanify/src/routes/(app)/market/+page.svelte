<script lang="ts">
  import BreadthDashboard from '$components/market/BreadthDashboard.svelte';
  import InternalsBar from '$components/market/InternalsBar.svelte';
  import SentimentGauge from '$components/market/SentimentGauge.svelte';
  import SectorRotation from '$components/market/SectorRotation.svelte';
  import ExportToolbar from '$lib/components/ui/ExportToolbar.svelte';

  const breadthData = {
    advancers: 1850,
    decliners: 1320,
    newHighs: 45,
    newLows: 12,
    percentAbove200ma: 62,
    percentAbove50ma: 54,
  };

  const sectorData = [
    { name: 'Technology',       change: 1.82,  relativeStrength: 78, momentum: 65 },
    { name: 'Healthcare',       change: -0.45, relativeStrength: 42, momentum: -15 },
    { name: 'Financials',       change: 0.92,  relativeStrength: 62, momentum: 35 },
    { name: 'Energy',           change: 1.35,  relativeStrength: 71, momentum: 55 },
    { name: 'Consumer Disc.',   change: -1.12, relativeStrength: 35, momentum: -40 },
    { name: 'Industrials',      change: 0.68,  relativeStrength: 58, momentum: 25 },
    { name: 'Communication',    change: 0.24,  relativeStrength: 50, momentum: 10 },
    { name: 'Utilities',        change: -0.15, relativeStrength: 38, momentum: -8 },
    { name: 'Consumer Staples', change: 0.32,  relativeStrength: 45, momentum: 5 },
    { name: 'Materials',        change: 0.78,  relativeStrength: 55, momentum: 30 },
    { name: 'Real Estate',      change: -0.62, relativeStrength: 32, momentum: -25 },
  ];
</script>

<svelte:head>
  <title>Market - Scanify</title>
</svelte:head>

<div class="page-root">
  <!-- Header -->
  <div class="page-header">
    <h1 class="page-title">Market Overview</h1>
    <div class="header-actions">
      <ExportToolbar source="market" />
      <div class="header-divider"></div>
      <span class="header-timestamp">
        {new Date().toLocaleTimeString('en-US', { hour12: false })}
      </span>
    </div>
  </div>

  <div class="page-content">
    <!-- 2x2 Grid -->
    <div class="overview-grid">

      <!-- Breadth Dashboard -->
      <div class="panel section-panel">
        <h2 class="section-label">Market Breadth</h2>
        <BreadthDashboard internals={breadthData} />
      </div>

      <!-- Internals Bar -->
      <div class="panel section-panel">
        <h2 class="section-label">Market Internals</h2>
        <InternalsBar tick={456} trin={0.87} vix={15.2} advDecRatio={1.40} />
        <!-- Supplementary metric cards -->
        <div class="metric-grid">
          <div class="metric-card">
            <div class="metric-label">Advancers</div>
            <div class="metric-value metric-value--bullish">1,850</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Decliners</div>
            <div class="metric-value metric-value--bearish">1,320</div>
          </div>
        </div>
      </div>

      <!-- Sentiment Gauge -->
      <div class="panel sentiment-panel">
        <SentimentGauge value={35} label="Market Sentiment" />
      </div>

      <!-- Sector Rotation -->
      <div class="panel sector-panel">
        <SectorRotation sectors={sectorData} />
      </div>

    </div>
  </div>
</div>

<style>
  .page-root {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: auto;
  }

  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    flex-shrink: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .page-title {
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--text-primary);
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .header-divider {
    width: 1px;
    height: 20px;
    background: var(--border-subtle);
  }

  .header-timestamp {
    font-size: var(--text-xs);
    font-family: var(--font-mono);
    color: var(--text-tertiary);
  }

  .page-content {
    padding: 20px;
  }

  .page-content > * + * {
    margin-top: 20px;
  }

  .overview-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 20px;
  }

  @media (min-width: 1024px) {
    .overview-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  .section-panel {
    padding: 20px;
  }

  .section-panel > * + * {
    margin-top: 12px;
  }

  .section-label {
    font-size: var(--text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
  }

  .metric-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    margin-top: 12px;
  }

  .metric-card {
    border-radius: var(--radius-lg);
    padding: 12px;
    text-align: center;
    background: var(--bg-base);
    border: 1px solid var(--border-subtle);
  }

  .metric-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
  }

  .metric-value {
    font-size: var(--text-lg);
    font-weight: 700;
    font-family: var(--font-mono);
  }

  .metric-value--bullish {
    color: var(--bullish);
  }

  .metric-value--bearish {
    color: var(--bearish);
  }

  .sentiment-panel {
    padding: 20px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
  }

  .sector-panel {
    padding: 20px;
  }
</style>
