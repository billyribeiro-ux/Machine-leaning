<script lang="ts">
  import type { Snippet } from 'svelte';
  import { page } from '$app/state';
  import { goto } from '$app/navigation';
  import AppShell from '$lib/components/layout/AppShell.svelte';
  import NavRail from '$lib/components/layout/NavRail.svelte';
  import StatusBar from '$lib/components/layout/StatusBar.svelte';
  import CommandBar from '$lib/components/layout/CommandBar.svelte';

  let { children }: { children: Snippet } = $props();

  let commandBarOpen = $state(false);

  /** Derive the active route segment from the current URL path. */
  let activeRoute = $derived(() => {
    const path = page.url.pathname;
    // Extract the first segment after /(app)/
    const segments = path.split('/').filter(Boolean);
    return segments[0] ?? 'scanner';
  });

  function handleNavigate(route: string) {
    goto(`/${route}`);
  }

  function handleCommandExecute(command: { id: string; label: string }) {
    // Navigate based on command id prefix
    if (command.id.startsWith('nav-')) {
      const route = command.id.replace('nav-', '');
      goto(`/${route}`);
    }
  }
</script>

<AppShell>
  {#snippet nav()}
    <NavRail activeRoute={activeRoute()} onnavigate={handleNavigate} />
  {/snippet}

  {#snippet main()}
    {@render children()}
  {/snippet}

  {#snippet statusbar()}
    <StatusBar
      connectionStatus="connected"
      marketPhase="regular"
      activeScanCount={3}
      lastUpdate={new Date().toISOString()}
      wsLatency={24}
    />
  {/snippet}
</AppShell>

<CommandBar bind:open={commandBarOpen} onexecute={handleCommandExecute} />
