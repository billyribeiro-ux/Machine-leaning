<!--
  AppShell.svelte
  Top-level layout wrapper for the Scanify trading scanner.
  CSS Grid: NavRail (56px) | Main Content (1fr) | optional Context Panel
  StatusBar pinned to the bottom.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';

  interface AppShellProps {
    /** Snippet rendered in the left nav-rail column. */
    nav: Snippet;
    /** Snippet rendered in the main content area. */
    main: Snippet;
    /** Optional snippet rendered in the right context panel column. */
    context?: Snippet;
    /** Snippet rendered in the bottom status bar. */
    statusbar: Snippet;
    /** Whether the right context panel column is visible. */
    contextOpen?: boolean;
    /** Width of the context panel in pixels. */
    contextWidth?: number;
    /** Additional CSS classes. */
    class?: string;
  }

  let {
    nav,
    main,
    context,
    statusbar,
    contextOpen = false,
    contextWidth = 380,
    class: className = '',
  }: AppShellProps = $props();

  let gridTemplate = $derived(
    contextOpen && context
      ? `56px 1fr ${contextWidth}px`
      : '56px 1fr'
  );
</script>

<div
  class="app-shell {className}"
  style:grid-template-columns={gridTemplate}
>
  <!-- Nav Rail Column -->
  <aside class="app-shell__nav">
    {@render nav()}
  </aside>

  <!-- Main Content Column -->
  <main class="app-shell__main">
    {@render main()}
  </main>

  <!-- Context Panel Column (conditional) -->
  {#if contextOpen && context}
    <aside class="app-shell__context">
      {@render context()}
    </aside>
  {/if}

  <!-- Status Bar (spans full width at bottom) -->
  <footer class="app-shell__statusbar" style:grid-column="1 / -1">
    {@render statusbar()}
  </footer>
</div>

<style>
  .app-shell {
    display: grid;
    grid-template-rows: 1fr 28px;
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    background-color: var(--bg-void);
    color: var(--text-primary);
  }

  .app-shell__nav {
    grid-row: 1;
    overflow: hidden;
  }

  .app-shell__main {
    grid-row: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .app-shell__context {
    grid-row: 1;
    overflow: hidden;
    border-left: 1px solid var(--border-subtle);
  }

  .app-shell__statusbar {
    grid-row: 2;
    overflow: hidden;
  }
</style>
