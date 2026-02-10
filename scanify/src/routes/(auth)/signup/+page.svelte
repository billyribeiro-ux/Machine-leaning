<script lang="ts">
  let name = $state('');
  let email = $state('');
  let password = $state('');
  let confirmPassword = $state('');
  let isLoading = $state(false);
  let showPassword = $state(false);
  let errorMessage = $state('');

  let passwordsMatch = $derived(password === confirmPassword || confirmPassword === '');
  let passwordStrength = $derived(() => {
    if (password.length === 0) return 0;
    let score = 0;
    if (password.length >= 8) score++;
    if (/[A-Z]/.test(password)) score++;
    if (/[0-9]/.test(password)) score++;
    if (/[^A-Za-z0-9]/.test(password)) score++;
    return score;
  });

  let strengthLabel = $derived(() => {
    const s = passwordStrength();
    if (s === 0) return '';
    if (s === 1) return 'Weak';
    if (s === 2) return 'Fair';
    if (s === 3) return 'Good';
    return 'Strong';
  });

  let strengthColor = $derived(() => {
    const s = passwordStrength();
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

<div class="flex min-h-screen items-center justify-center px-4" style="background: var(--bg-void);">
  <div class="w-full max-w-md space-y-8">
    <!-- Brand -->
    <div class="text-center">
      <h1 class="text-3xl font-bold tracking-tight" style="color: var(--accent-bright); font-family: var(--font-display);">
        SCANIFY
      </h1>
      <p class="mt-2 text-sm" style="color: var(--text-tertiary);">
        Create your trading account
      </p>
    </div>

    <!-- Card -->
    <div class="rounded-xl p-8 space-y-6" style="background: var(--bg-surface); border: 1px solid var(--border-subtle);">
      <!-- Error -->
      {#if errorMessage}
        <div class="rounded-lg px-4 py-3 text-sm" style="background: var(--bearish-bg); color: var(--bearish-bright); border: 1px solid var(--bearish-dim);">
          {errorMessage}
        </div>
      {/if}

      <!-- Form -->
      <form onsubmit={handleSubmit} class="space-y-4">
        <!-- Name -->
        <div class="space-y-1.5">
          <label for="name" class="block text-xs font-medium" style="color: var(--text-secondary);">
            Full name
          </label>
          <input
            id="name"
            type="text"
            bind:value={name}
            placeholder="John Doe"
            autocomplete="name"
            class="w-full rounded-lg px-4 py-2.5 text-sm outline-none transition-all"
            style="background: var(--bg-base); color: var(--text-primary); border: 1px solid var(--border-default);"
          />
        </div>

        <!-- Email -->
        <div class="space-y-1.5">
          <label for="signup-email" class="block text-xs font-medium" style="color: var(--text-secondary);">
            Email address
          </label>
          <input
            id="signup-email"
            type="email"
            bind:value={email}
            placeholder="trader@example.com"
            autocomplete="email"
            class="w-full rounded-lg px-4 py-2.5 text-sm outline-none transition-all"
            style="background: var(--bg-base); color: var(--text-primary); border: 1px solid var(--border-default);"
          />
        </div>

        <!-- Password -->
        <div class="space-y-1.5">
          <label for="signup-password" class="block text-xs font-medium" style="color: var(--text-secondary);">
            Password
          </label>
          <div class="relative">
            <input
              id="signup-password"
              type={showPassword ? 'text' : 'password'}
              bind:value={password}
              placeholder="Min. 8 characters"
              autocomplete="new-password"
              class="w-full rounded-lg px-4 py-2.5 pr-10 text-sm outline-none transition-all"
              style="background: var(--bg-base); color: var(--text-primary); border: 1px solid var(--border-default);"
            />
            <button
              type="button"
              onclick={() => showPassword = !showPassword}
              class="absolute right-3 top-1/2 -translate-y-1/2 text-xs"
              style="color: var(--text-tertiary);"
            >
              {showPassword ? 'Hide' : 'Show'}
            </button>
          </div>
          <!-- Password strength indicator -->
          {#if password.length > 0}
            <div class="space-y-1">
              <div class="flex gap-1">
                {#each Array(4) as _, i}
                  <div
                    class="h-1 flex-1 rounded-full transition-all"
                    style="background: {i < passwordStrength() ? strengthColor() : 'var(--bg-overlay)'};"
                  ></div>
                {/each}
              </div>
              <p class="text-xs" style="color: {strengthColor()};">{strengthLabel()}</p>
            </div>
          {/if}
        </div>

        <!-- Confirm Password -->
        <div class="space-y-1.5">
          <label for="confirm-password" class="block text-xs font-medium" style="color: var(--text-secondary);">
            Confirm password
          </label>
          <input
            id="confirm-password"
            type={showPassword ? 'text' : 'password'}
            bind:value={confirmPassword}
            placeholder="Re-enter your password"
            autocomplete="new-password"
            class="w-full rounded-lg px-4 py-2.5 text-sm outline-none transition-all"
            style="background: var(--bg-base); color: var(--text-primary); border: 1px solid {passwordsMatch ? 'var(--border-default)' : 'var(--bearish)'};"
          />
          {#if !passwordsMatch}
            <p class="text-xs" style="color: var(--bearish);">Passwords do not match</p>
          {/if}
        </div>

        <!-- Submit -->
        <button
          type="submit"
          disabled={isLoading}
          class="w-full rounded-lg px-4 py-2.5 text-sm font-semibold transition-all disabled:opacity-50"
          style="background: var(--accent); color: white;"
        >
          {#if isLoading}
            <span class="inline-flex items-center gap-2">
              <span class="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"></span>
              Creating account...
            </span>
          {:else}
            Create Account
          {/if}
        </button>
      </form>

      <!-- Terms -->
      <p class="text-center text-xs" style="color: var(--text-disabled);">
        By signing up, you agree to our Terms of Service and Privacy Policy.
      </p>
    </div>

    <!-- Footer link -->
    <p class="text-center text-sm" style="color: var(--text-tertiary);">
      Already have an account?
      <a href="/login" class="font-medium transition-colors" style="color: var(--accent-bright);">
        Log in
      </a>
    </p>
  </div>
</div>
