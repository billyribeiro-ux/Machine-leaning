<svelte:head>
  <title>Forgot Password - Scanify</title>
</svelte:head>

<div class="auth-page" style="background: var(--bg-void);">
  <div class="auth-container">
    <div class="brand">
      <h1 class="brand-title" style="color: var(--accent-bright); font-family: var(--font-display);">
        SCANIFY
      </h1>
      <p class="brand-subtitle" style="color: var(--text-tertiary);">
        Reset your password
      </p>
    </div>

    <div class="auth-card" style="background: var(--bg-surface); border: 1px solid var(--border-subtle);">
      <div class="placeholder-content">
        <div class="lock-icon" style="background: var(--bg-elevated);">
          <span class="lock-emoji" style="color: var(--text-secondary);">&#128274;</span>
        </div>
        <h2 class="placeholder-title" style="color: var(--text-primary);">Coming Soon</h2>
        <p class="placeholder-description" style="color: var(--text-tertiary);">
          Password reset functionality is under development. Please contact support for assistance.
        </p>
      </div>

      <a
        href="/login"
        class="back-link"
        style="background: var(--bg-elevated); color: var(--text-primary); border: 1px solid var(--border-default);"
      >
        Back to Sign In
      </a>
    </div>
  </div>
</div>

<style>
  .auth-page {
    display: flex;
    min-height: 100vh;
    align-items: center;
    justify-content: center;
    padding-left: 16px;
    padding-right: 16px;
  }

  .auth-container {
    width: 100%;
    max-width: 28rem;
    display: flex;
    flex-direction: column;
    gap: 32px;
    text-align: center;
  }

  .brand {
    text-align: center;
  }

  .brand-title {
    font-size: var(--text-3xl);
    font-weight: 700;
    letter-spacing: -0.025em;
  }

  .brand-subtitle {
    margin-top: 8px;
    font-size: var(--text-sm);
  }

  .auth-card {
    border-radius: var(--radius-xl);
    padding: 32px;
    display: flex;
    flex-direction: column;
    gap: 24px;
  }

  .placeholder-content {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .lock-icon {
    margin-left: auto;
    margin-right: auto;
    display: flex;
    height: 48px;
    width: 48px;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-full);
  }

  .lock-emoji {
    font-size: var(--text-xl);
  }

  .placeholder-title {
    font-size: var(--text-lg);
    font-weight: 600;
  }

  .placeholder-description {
    font-size: var(--text-sm);
  }

  .back-link {
    display: inline-block;
    border-radius: var(--radius-lg);
    padding: 10px 24px;
    font-size: var(--text-sm);
    font-weight: 500;
    transition: color 150ms, background-color 150ms;
  }
</style>
