<script lang="ts">
  import type { Snippet } from 'svelte';
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { goto } from '$app/navigation';
  import AppShell from '$lib/components/layout/AppShell.svelte';
  import NavRail from '$lib/components/layout/NavRail.svelte';
  import StatusBar from '$lib/components/layout/StatusBar.svelte';
  import CommandBar from '$lib/components/layout/CommandBar.svelte';
  import KeyboardShortcutOverlay from '$lib/components/layout/KeyboardShortcutOverlay.svelte';
  import { wsStore } from '$lib/stores/websocket.svelte';
  import { scannerStore } from '$lib/stores/scanner.svelte';
  import { keyboardStore } from '$lib/stores/keyboard.svelte';
  import { isMac } from '$lib/utils/keyboard';

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

  // ---------------------------------------------------------------------------
  // Navigation route map (keys 1-7)
  // ---------------------------------------------------------------------------

  const NAV_ROUTES = [
    'scanner',
    'dashboard',
    'options',
    'market',
    'institutional',
    'analysis',
    'alerts',
  ] as const;

  // ---------------------------------------------------------------------------
  // Register all global keyboard shortcuts
  // ---------------------------------------------------------------------------

  // We use the meta modifier on Mac and ctrl on Windows for "Cmd/Ctrl" combos.
  const cmdMod = isMac ? 'meta' as const : 'ctrl' as const;

  // Register global shortcuts once on mount. Using onMount (not $effect)
  // is deliberate: registerShortcuts() both reads and writes the store's
  // `shortcuts` state, which inside an $effect would create a self-
  // retriggering loop (effect_update_depth_exceeded).
  onMount(() => {
    keyboardStore.startListening();

    const cleanup = keyboardStore.registerShortcuts([
      // =======================================================================
      // Navigation (1-7)
      // =======================================================================
      {
        id: 'nav-1',
        key: '1',
        description: 'Go to Scanner',
        category: 'Navigation',
        handler: () => goto('/scanner'),
      },
      {
        id: 'nav-2',
        key: '2',
        description: 'Go to Dashboard',
        category: 'Navigation',
        handler: () => goto('/dashboard'),
      },
      {
        id: 'nav-3',
        key: '3',
        description: 'Go to Options Flow',
        category: 'Navigation',
        handler: () => goto('/options'),
      },
      {
        id: 'nav-4',
        key: '4',
        description: 'Go to Market Overview',
        category: 'Navigation',
        handler: () => goto('/market'),
      },
      {
        id: 'nav-5',
        key: '5',
        description: 'Go to Institutional Flow',
        category: 'Navigation',
        handler: () => goto('/institutional'),
      },
      {
        id: 'nav-6',
        key: '6',
        description: 'Go to Analysis',
        category: 'Navigation',
        handler: () => goto('/analysis'),
      },
      {
        id: 'nav-7',
        key: '7',
        description: 'Go to Alerts',
        category: 'Navigation',
        handler: () => goto('/alerts'),
      },

      // =======================================================================
      // Navigation (modifier combos)
      // =======================================================================
      {
        id: 'command-bar',
        key: 'k',
        modifiers: [cmdMod],
        description: 'Open command palette',
        category: 'Navigation',
        handler: () => {
          commandBarOpen = !commandBarOpen;
        },
        allowInInput: true,
      },
      {
        id: 'shortcuts-overlay',
        key: '/',
        modifiers: [cmdMod],
        description: 'Show keyboard shortcuts',
        category: 'Navigation',
        handler: () => {
          keyboardStore.togglePalette();
        },
        allowInInput: true,
      },
      {
        id: 'shortcuts-overlay-qmark',
        key: '?',
        modifiers: ['shift'],
        description: 'Show keyboard shortcuts',
        category: 'Navigation',
        handler: () => {
          keyboardStore.togglePalette();
        },
        // "?" is Shift+/ — do not show as a separate entry in overlay
        preventDefault: true,
      },
      {
        id: 'close-overlay',
        key: 'Escape',
        description: 'Close overlay / modal',
        category: 'Navigation',
        handler: () => {
          if (keyboardStore.paletteOpen) {
            keyboardStore.closePalette();
          } else if (commandBarOpen) {
            commandBarOpen = false;
          }
        },
        allowInInput: true,
        preventDefault: false,
      },

      // =======================================================================
      // Scanner
      // =======================================================================
      {
        id: 'scanner-pause',
        key: ' ',
        description: 'Pause / resume auto-scan',
        category: 'Scanner',
        handler: () => {
          if (typeof scannerStore.togglePause === 'function') {
            scannerStore.togglePause();
          }
        },
      },
      {
        id: 'scanner-refresh',
        key: 'r',
        description: 'Refresh scan data',
        category: 'Scanner',
        handler: () => {
          if (typeof scannerStore.refresh === 'function') {
            scannerStore.refresh();
          }
        },
      },
      {
        id: 'scanner-search',
        key: 'f',
        modifiers: [cmdMod],
        description: 'Focus search input',
        category: 'Scanner',
        handler: () => {
          const searchInput = document.querySelector<HTMLInputElement>(
            '[data-scanner-search]',
          );
          searchInput?.focus();
        },
        allowInInput: true,
      },
      {
        id: 'scanner-export',
        key: 'e',
        modifiers: [cmdMod],
        description: 'Export current view',
        category: 'Scanner',
        handler: () => {
          if (typeof scannerStore.exportData === 'function') {
            scannerStore.exportData();
          }
        },
        allowInInput: true,
      },
      {
        id: 'scanner-prev-preset',
        key: '[',
        description: 'Previous scanner preset',
        category: 'Scanner',
        handler: () => {
          if (typeof scannerStore.prevPreset === 'function') {
            scannerStore.prevPreset();
          }
        },
      },
      {
        id: 'scanner-next-preset',
        key: ']',
        description: 'Next scanner preset',
        category: 'Scanner',
        handler: () => {
          if (typeof scannerStore.nextPreset === 'function') {
            scannerStore.nextPreset();
          }
        },
      },
      {
        id: 'scanner-toggle-filters',
        key: 'f',
        description: 'Toggle filter bar',
        category: 'Scanner',
        handler: () => {
          if (typeof scannerStore.toggleFilters === 'function') {
            scannerStore.toggleFilters();
          }
        },
      },
      // Shift+1 through Shift+5: Minimum strength filter
      {
        id: 'scanner-strength-1',
        key: '!',
        modifiers: ['shift'],
        description: 'Set minimum strength 1',
        category: 'Scanner',
        handler: () => {
          if (typeof scannerStore.setMinStrength === 'function') {
            scannerStore.setMinStrength(1);
          }
        },
      },
      {
        id: 'scanner-strength-2',
        key: '@',
        modifiers: ['shift'],
        description: 'Set minimum strength 2',
        category: 'Scanner',
        handler: () => {
          if (typeof scannerStore.setMinStrength === 'function') {
            scannerStore.setMinStrength(2);
          }
        },
      },
      {
        id: 'scanner-strength-3',
        key: '#',
        modifiers: ['shift'],
        description: 'Set minimum strength 3',
        category: 'Scanner',
        handler: () => {
          if (typeof scannerStore.setMinStrength === 'function') {
            scannerStore.setMinStrength(3);
          }
        },
      },
      {
        id: 'scanner-strength-4',
        key: '$',
        modifiers: ['shift'],
        description: 'Set minimum strength 4',
        category: 'Scanner',
        handler: () => {
          if (typeof scannerStore.setMinStrength === 'function') {
            scannerStore.setMinStrength(4);
          }
        },
      },
      {
        id: 'scanner-strength-5',
        key: '%',
        modifiers: ['shift'],
        description: 'Set minimum strength 5',
        category: 'Scanner',
        handler: () => {
          if (typeof scannerStore.setMinStrength === 'function') {
            scannerStore.setMinStrength(5);
          }
        },
      },

      // =======================================================================
      // Data
      // =======================================================================
      {
        id: 'data-copy-row',
        key: 'c',
        modifiers: [cmdMod, 'shift'],
        description: 'Copy selected row data',
        category: 'Data',
        handler: () => {
          if (typeof scannerStore.copySelectedRow === 'function') {
            scannerStore.copySelectedRow();
          }
        },
        allowInInput: true,
      },
      {
        id: 'data-open-detail',
        key: 'Enter',
        description: 'Open detail for selected row',
        category: 'Data',
        handler: () => {
          if (typeof scannerStore.openSelectedDetail === 'function') {
            scannerStore.openSelectedDetail();
          }
        },
      },
      {
        id: 'data-row-up',
        key: 'ArrowUp',
        description: 'Select previous row',
        category: 'Data',
        handler: () => {
          if (typeof scannerStore.selectPreviousRow === 'function') {
            scannerStore.selectPreviousRow();
          }
        },
      },
      {
        id: 'data-row-down',
        key: 'ArrowDown',
        description: 'Select next row',
        category: 'Data',
        handler: () => {
          if (typeof scannerStore.selectNextRow === 'function') {
            scannerStore.selectNextRow();
          }
        },
      },
      {
        id: 'data-row-up-vim',
        key: 'k',
        description: 'Select previous row (vim)',
        category: 'Data',
        handler: () => {
          if (typeof scannerStore.selectPreviousRow === 'function') {
            scannerStore.selectPreviousRow();
          }
        },
      },
      {
        id: 'data-row-down-vim',
        key: 'j',
        description: 'Select next row (vim)',
        category: 'Data',
        handler: () => {
          if (typeof scannerStore.selectNextRow === 'function') {
            scannerStore.selectNextRow();
          }
        },
      },

      // =======================================================================
      // System
      // =======================================================================
      {
        id: 'system-settings',
        key: ',',
        modifiers: [cmdMod],
        description: 'Open settings',
        category: 'System',
        handler: () => {
          goto('/settings');
        },
        allowInInput: true,
      },
      {
        id: 'system-context-panel',
        key: '.',
        modifiers: [cmdMod],
        description: 'Toggle context panel',
        category: 'System',
        handler: () => {
          // Dispatch a custom event that the ContextPanel listens for
          document.dispatchEvent(new CustomEvent('toggle-context-panel'));
        },
        allowInInput: true,
      },
      {
        id: 'system-toggle-theme',
        key: 't',
        description: 'Toggle theme',
        category: 'System',
        handler: () => {
          // Theme toggling will be wired up when the theme system is built
          document.dispatchEvent(new CustomEvent('toggle-theme'));
        },
      },
    ]);

    return () => {
      cleanup();
      keyboardStore.stopListening();
    };
  });
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
<KeyboardShortcutOverlay />
