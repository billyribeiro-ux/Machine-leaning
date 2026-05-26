<script lang="ts">
  import type { Snippet } from 'svelte';
  import { page } from '$app/state';
  import { goto } from '$app/navigation';
  import AppShell from '$lib/components/layout/AppShell.svelte';
  import NavRail from '$lib/components/layout/NavRail.svelte';
  import StatusBar from '$lib/components/layout/StatusBar.svelte';
  import CommandBar from '$lib/components/layout/CommandBar.svelte';
  import { wsStore } from '$lib/stores/websocket.svelte';
  import { scannerStore } from '$lib/stores/scanner.svelte';

  let { children }: { children: Snippet } = $props();

  let commandBarOpen = $state(false);

  /** Map WebSocket connection state to StatusBar's expected type. */
  let connectionStatus = $derived.by(() => {
    const state = wsStore.connectionState;
    if (state === 'reconnecting') return 'connecting' as const;
    return state as 'connected' | 'connecting' | 'disconnected';
  });

  /** Derive the active route segment from the current URL path. */
  let activeRoute = $derived.by(() => {
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
    <NavRail activeRoute={activeRoute} onnavigate={handleNavigate} />
  {/snippet}

  {#snippet main()}
    {@render children()}
  {/snippet}

  {#snippet statusbar()}
    <StatusBar
      connectionStatus={connectionStatus}
      marketPhase="regular"
      activeScanCount={scannerStore.activeScanCount}
      lastUpdate={wsStore.lastMessageTimestamp ? new Date(wsStore.lastMessageTimestamp).toISOString() : ''}
      wsLatency={wsStore.latency}
    />
  {/snippet}
</AppShell>

<CommandBar bind:open={commandBarOpen} onexecute={handleCommandExecute} />
