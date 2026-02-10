<script lang="ts">
  const settingsCards = [
    {
      title: 'Profile',
      description: 'Manage your display name, email, timezone, and password',
      href: '/settings/profile',
      icon: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z',
    },
    {
      title: 'Subscription',
      description: 'View your current plan, upgrade, or manage billing',
      href: '/settings/subscription',
      icon: 'M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z',
    },
    {
      title: 'Appearance',
      description: 'Theme, animations, density, and display preferences',
      href: '/settings/appearance',
      icon: 'M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z',
    },
    {
      title: 'Keyboard Shortcuts',
      description: 'View and customize keyboard shortcuts for quick navigation',
      href: '/settings/keyboard',
      icon: 'M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4',
    },
    {
      title: 'API Keys',
      description: 'Generate and manage API keys for programmatic access',
      href: '/settings/api',
      icon: 'M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z',
    },
  ];
</script>

<svelte:head>
  <title>Settings - Scanify</title>
</svelte:head>

<div class="flex flex-col h-full overflow-auto">
  <!-- Header -->
  <div class="flex items-center justify-between px-5 py-3 shrink-0" style="border-bottom: 1px solid var(--border-subtle);">
    <h1 class="text-lg font-bold" style="color: var(--text-primary);">Settings</h1>
  </div>

  <div class="p-5">
    <!-- 2-column grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      {#each settingsCards as card (card.title)}
        <a
          href={card.href}
          class="panel p-5 flex items-center gap-4 transition-colors duration-150 no-underline group"
          style="color: inherit;"
        >
          <!-- Icon -->
          <div
            class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg"
            style="background: var(--bg-base); border: 1px solid var(--border-subtle);"
          >
            <svg class="h-5 w-5" style="color: var(--accent);" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
              <path stroke-linecap="round" stroke-linejoin="round" d={card.icon} />
            </svg>
          </div>

          <!-- Text -->
          <div class="flex-1 min-w-0">
            <div class="text-sm font-semibold" style="color: var(--text-primary);">{card.title}</div>
            <div class="text-xs mt-0.5" style="color: var(--text-tertiary);">{card.description}</div>
          </div>

          <!-- Arrow -->
          <svg class="h-4 w-4 shrink-0 transition-transform duration-150" style="color: var(--text-disabled);" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </a>
      {/each}
    </div>
  </div>
</div>
