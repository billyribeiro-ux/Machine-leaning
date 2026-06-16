<script lang="ts">
  let name = $state('');
  let email = $state('');
  let password = $state('');
  let confirmPassword = $state('');
  let isLoading = $state(false);
  let showPassword = $state(false);
  let errorMessage = $state('');

  let passwordsMatch = $derived(password === confirmPassword || confirmPassword === '');
  let passwordStrength = $derived.by(() => {
    if (password.length === 0) return 0;
    let score = 0;
    if (password.length >= 8) score++;
    if (/[A-Z]/.test(password)) score++;
    if (/[0-9]/.test(password)) score++;
    if (/[^A-Za-z0-9]/.test(password)) score++;
    return score;
  });

  let strengthLabel = $derived.by(() => {
    const s = passwordStrength;
    if (s === 0) return '';
    if (s === 1) return 'Weak';
    if (s === 2) return 'Fair';
    if (s === 3) return 'Good';
    return 'Strong';
  });

  let strengthColor = $derived.by(() => {
    const s = passwordStrength;
    if (s <= 1) return 'var(--bearish)';
    if (s === 2) return 'var(--warning)';
    if (s === 3) return 'var(--bullish-dim)';
    return 'var(--bullish)';
  });

  function handleSubmit(e: SubmitEvent) {
    e.preventDefault();
    errorMessage = '';
    if (!name || !email || !password || !confirmPassword) {
      errorMessage = 'Please fill in all fields.';
      return;
    }
    if (password !== confirmPassword) {
      errorMessage = 'Passwords do not match.';
      return;
    }
    if (password.length < 8) {
      errorMessage = 'Password must be at least 8 characters.';
      return;
    }
    isLoading = true;
    setTimeout(() => {
      isLoading = false;
    }, 1500);
  }
</script>

<svelte:head>
  <title>Create Account - Scanify</title>
</svelte:head>

<div class="auth-page" style="background: var(--bg-void);">
  <div class="auth-container">
    <!-- Brand -->
    <div class="brand">
      <h1 class="brand-title" style="color: var(--accent-bright); font-family: var(--font-display);">
        SCANIFY
      </h1>
      <p class="brand-subtitle" style="color: var(--text-tertiary);">
        Create your trading account
      </p>
    </div>

    <!-- Card -->
    <div class="auth-card" style="background: var(--bg-surface); border: 1px solid var(--border-subtle);">
      <!-- Error -->
      {#if errorMessage}
        <div class="error-banner" style="background: var(--bearish-bg); color: var(--bearish-bright); border: 1px solid var(--bearish-dim);">
          {errorMessage}
        </div>
      {/if}

      <!-- Form -->
      <form onsubmit={handleSubmit} class="auth-form">
        <!-- Name -->
        <div class="field-group">
          <label for="name" class="field-label" style="color: var(--text-secondary);">
            Full name
          </label>
          <input
            id="name"
            type="text"
            bind:value={name}
            placeholder="John Doe"
            autocomplete="name"
            class="field-input"
            style="background: var(--bg-base); color: var(--text-primary); border: 1px solid var(--border-default);"
          />
        </div>

        <!-- Email -->
        <div class="field-group">
          <label for="signup-email" class="field-label" style="color: var(--text-secondary);">
            Email address
          </label>
          <input
            id="signup-email"
            type="email"
            bind:value={email}
            placeholder="trader@example.com"
            autocomplete="email"
            class="field-input"
            style="background: var(--bg-base); color: var(--text-primary); border: 1px solid var(--border-default);"
          />
        </div>

        <!-- Password -->
        <div class="field-group">
          <label for="signup-password" class="field-label" style="color: var(--text-secondary);">
            Password
          </label>
          <div class="password-wrapper">
            <input
              id="signup-password"
              type={showPassword ? 'text' : 'password'}
              bind:value={password}
              placeholder="Min. 8 characters"
              autocomplete="new-password"
              class="field-input password-input"
              style="background: var(--bg-base); color: var(--text-primary); border: 1px solid var(--border-default);"
            />
            <button
              type="button"
              onclick={() => showPassword = !showPassword}
              class="password-toggle"
              style="color: var(--text-tertiary);"
            >
              {showPassword ? 'Hide' : 'Show'}
            </button>
          </div>
          <!-- Password strength indicator -->
          {#if password.length > 0}
            <div class="strength-container">
              <div class="strength-bars">
                {#each Array(4) as _, i}
                  <div
                    class="strength-bar"
                    style="background: {i < passwordStrength ? strengthColor : 'var(--bg-overlay)'};"
                  ></div>
                {/each}
              </div>
              <p class="strength-label" style="color: {strengthColor};">{strengthLabel}</p>
            </div>
          {/if}
        </div>

        <!-- Confirm Password -->
        <div class="field-group">
          <label for="confirm-password" class="field-label" style="color: var(--text-secondary);">
            Confirm password
          </label>
          <input
            id="confirm-password"
            type={showPassword ? 'text' : 'password'}
            bind:value={confirmPassword}
            placeholder="Re-enter your password"
            autocomplete="new-password"
            class="field-input"
            style="background: var(--bg-base); color: var(--text-primary); border: 1px solid {passwordsMatch ? 'var(--border-default)' : 'var(--bearish)'};"
          />
          {#if !passwordsMatch}
            <p class="mismatch-text" style="color: var(--bearish);">Passwords do not match</p>
          {/if}
        </div>

        <!-- Submit -->
        <button
          type="submit"
          disabled={isLoading}
          class="submit-btn"
          style="background: var(--accent); color: white;"
        >
          {#if isLoading}
            <span class="loading-content">
              <span class="spinner"></span>
              Creating account...
            </span>
          {:else}
            Create Account
          {/if}
        </button>
      </form>

      <!-- Terms -->
      <p class="terms-text" style="color: var(--text-disabled);">
        By signing up, you agree to our Terms of Service and Privacy Policy.
      </p>
    </div>

    <!-- Footer link -->
    <p class="auth-footer" style="color: var(--text-tertiary);">
      Already have an account?
      <a href="/login" class="auth-footer-link" style="color: var(--accent-bright);">
        Log in
      </a>
    </p>
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

  .error-banner {
    border-radius: var(--radius-lg);
    padding: 12px 16px;
    font-size: var(--text-sm);
  }

  .auth-form {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .field-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .field-label {
    display: block;
    font-size: var(--text-xs);
    font-weight: 500;
  }

  .field-input {
    width: 100%;
    border-radius: var(--radius-lg);
    padding: 10px 16px;
    font-size: var(--text-sm);
    outline: none;
    transition: all 150ms;
  }

  .password-wrapper {
    position: relative;
  }

  .password-input {
    padding-right: 40px;
  }

  .password-toggle {
    position: absolute;
    right: 12px;
    top: 50%;
    transform: translateY(-50%);
    font-size: var(--text-xs);
  }

  .strength-container {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .strength-bars {
    display: flex;
    gap: 4px;
  }

  .strength-bar {
    height: 4px;
    flex: 1;
    border-radius: var(--radius-full);
    transition: all 150ms;
  }

  .strength-label {
    font-size: var(--text-xs);
  }

  .mismatch-text {
    font-size: var(--text-xs);
  }

  .submit-btn {
    width: 100%;
    border-radius: var(--radius-lg);
    padding: 10px 16px;
    font-size: var(--text-sm);
    font-weight: 600;
    transition: all 150ms;
  }

  .submit-btn:disabled {
    opacity: 0.5;
  }

  .loading-content {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }

  .spinner {
    height: 16px;
    width: 16px;
    border-radius: var(--radius-full);
    border: 2px solid currentColor;
    border-top-color: transparent;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .terms-text {
    text-align: center;
    font-size: var(--text-xs);
  }

  .auth-footer {
    text-align: center;
    font-size: var(--text-sm);
  }

  .auth-footer-link {
    font-weight: 500;
    transition: color 150ms, background-color 150ms;
  }
</style>
