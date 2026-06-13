<svelte:head>
  <title>Analysis - Scanify</title>
</svelte:head>

<div class="page-container">
  <div class="placeholder-content">
    <div class="icon-badge">
      <span class="icon-letter">A</span>
    </div>
    <h1 class="page-title">
      Analysis
    </h1>
    <p class="page-description">
      Advanced charting, technical indicators, and historical analysis tools are coming soon.
    </p>
    <div class="status-badge">
      Coming Soon
    </div>
  </div>
</div>

<style>
  .page-container {
    display: flex;
    height: 100%;
    align-items: center;
    justify-content: center;
    padding: 32px;
  }

  .placeholder-content {
    text-align: center;
    max-width: 28rem;
  }

  .placeholder-content > :global(* + *) {
    margin-top: 16px;
  }

  .icon-badge {
    margin-inline: auto;
    display: flex;
    height: 64px;
    width: 64px;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-xl);
    background: var(--bg-elevated);
    border: 1px solid var(--border-subtle);
  }

  .icon-letter {
    font-size: var(--text-2xl);
    font-weight: 700;
    color: var(--text-secondary);
    font-family: var(--font-mono);
  }

  .page-title {
    font-size: var(--text-2xl);
    font-weight: 700;
    color: var(--text-primary);
    font-family: var(--font-display);
  }

  .page-description {
    font-size: var(--text-sm);
    line-height: 1.625;
    color: var(--text-tertiary);
  }

  .status-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border-radius: var(--radius-lg);
    padding: 8px 16px;
    font-size: var(--text-xs);
    font-weight: 500;
    background: var(--bg-elevated);
    color: var(--text-secondary);
    border: 1px solid var(--border-subtle);
  }
</style>
