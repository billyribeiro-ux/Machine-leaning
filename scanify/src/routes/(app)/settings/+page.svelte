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
      title: 'Vendor API Keys',
      description: 'Configure FMP, Polygon, Tradier and other data vendor credentials',
      href: '/settings/vendors',
      icon: 'M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z',
    },
  ];
</script>

<svelte:head>
  <title>Settings - Scanify</title>
</svelte:head>

<div class="settings-page">
  <!-- Header -->
  <div class="settings-header" style="border-bottom: 1px solid var(--border-subtle);">
    <h1 class="settings-title" style="color: var(--text-primary);">Settings</h1>
  </div>

  <div class="settings-body">
    <!-- 2-column grid -->
    <div class="settings-grid">
      {#each settingsCards as card (card.title)}
        <a
          href={card.href}
          class="panel settings-card"
          style="color: inherit;"
        >
          <!-- Icon -->
          <div
            class="card-icon-wrapper"
            style="background: var(--bg-base); border: 1px solid var(--border-subtle);"
          >
            <svg class="card-icon" style="color: var(--accent);" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
              <path stroke-linecap="round" stroke-linejoin="round" d={card.icon} />
            </svg>
          </div>

          <!-- Text -->
          <div class="card-content">
            <div class="card-title" style="color: var(--text-primary);">{card.title}</div>
            <div class="card-description" style="color: var(--text-tertiary);">{card.description}</div>
          </div>

          <!-- Arrow -->
          <svg class="card-arrow" style="color: var(--text-disabled);" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </a>
      {/each}
    </div>
  </div>
</div>

<style>
  .settings-page {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: auto;
  }

  .settings-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    flex-shrink: 0;
  }

  .settings-title {
    font-size: var(--text-lg);
    font-weight: 700;
  }

  .settings-body {
    padding: 20px;
  }

  .settings-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 16px;
  }

  @media (min-width: 768px) {
    .settings-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  .settings-card {
    padding: 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    transition: color 150ms, background-color 150ms;
    transition-duration: 150ms;
    text-decoration: none;
  }

  .settings-card:hover .card-arrow {
    transform: translateX(2px);
  }

  .card-icon-wrapper {
    display: flex;
    height: 40px;
    width: 40px;
    flex-shrink: 0;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-lg);
  }

  .card-icon {
    height: 20px;
    width: 20px;
  }

  .card-content {
    flex: 1;
    min-width: 0;
  }

  .card-title {
    font-size: var(--text-sm);
    font-weight: 600;
  }

  .card-description {
    font-size: var(--text-xs);
    margin-top: 2px;
  }

  .card-arrow {
    height: 16px;
    width: 16px;
    flex-shrink: 0;
    transition: transform 150ms;
  }
</style>
