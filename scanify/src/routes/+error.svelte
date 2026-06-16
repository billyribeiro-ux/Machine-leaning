<script lang="ts">
  import { page } from '$app/state';
</script>

<div class="error-page">
  <div class="error-content">
    <h1 class="error-code">{page.status}</h1>
    <p class="error-message">{page.error?.message ?? 'Something went wrong'}</p>
    <a href="/" class="home-link">Go Home</a>
  </div>
</div>

<style>
  .error-page {
    display: flex;
    min-height: 100vh;
    align-items: center;
    justify-content: center;
    background: var(--bg-void);
    color: var(--text-primary);
  }

  .error-content {
    text-align: center;
  }

  .error-content > :global(* + *) {
    margin-top: 16px;
  }

  .error-code {
    font-size: var(--text-5xl);
    font-weight: 700;
    font-family: var(--font-mono);
    color: var(--bearish);
  }

  .error-message {
    font-size: var(--text-lg);
    color: var(--text-secondary);
  }

  .home-link {
    display: inline-block;
    padding-inline: 24px;
    padding-block: 8px;
    border-radius: var(--radius-md);
    font-size: var(--text-sm);
    font-weight: 500;
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    color: var(--text-primary);
    text-decoration: none;
  }
</style>
