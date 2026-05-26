<svelte:head>
  <title>Forgot Password - Scanify</title>
</svelte:head>

<div class="flex min-h-screen items-center justify-center px-4" style="background: var(--bg-void);">
  <div class="w-full max-w-md space-y-8 text-center">
    <div>
      <h1 class="text-3xl font-bold tracking-tight" style="color: var(--accent-bright); font-family: var(--font-display);">
        SCANIFY
      </h1>
      <p class="mt-2 text-sm" style="color: var(--text-tertiary);">
        Reset your password
      </p>
    </div>

    <div class="rounded-xl p-8 space-y-6" style="background: var(--bg-surface); border: 1px solid var(--border-subtle);">
      <div class="space-y-3">
        <div class="mx-auto flex h-12 w-12 items-center justify-center rounded-full" style="background: var(--bg-elevated);">
          <span class="text-xl" style="color: var(--text-secondary);">&#128274;</span>
        </div>
        <h2 class="text-lg font-semibold" style="color: var(--text-primary);">Coming Soon</h2>
        <p class="text-sm" style="color: var(--text-tertiary);">
          Password reset functionality is under development. Please contact support for assistance.
        </p>
      </div>

      <a
        href="/login"
        class="inline-block rounded-lg px-6 py-2.5 text-sm font-medium transition-colors"
        style="background: var(--bg-elevated); color: var(--text-primary); border: 1px solid var(--border-default);"
      >
        Back to Sign In
      </a>
    </div>
  </div>
</div>
