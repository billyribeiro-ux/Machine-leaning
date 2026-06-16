<!--
  ContextPanel.svelte
  Right-side slide-in panel with surface background and left border.
  Closes on Escape key, uses translateX transition.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';

  interface ContextPanelProps {
    /** Whether the panel is open (bindable). */
    isOpen: boolean;
    /** Optional title displayed in the header. */
    title?: string;
    /** Panel width in pixels. */
    width?: number;
    /** Content snippet. */
    children: Snippet;
    /** Additional CSS classes. */
    class?: string;
  }

  let {
    isOpen = $bindable(false),
    title = '',
    width = 380,
    children,
    class: className = '',
  }: ContextPanelProps = $props();

  let panelEl = $state<HTMLElement | null>(null);

  // Close on Escape key
  $effect(() => {
    if (!isOpen) return;

    function handleKeydown(e: KeyboardEvent): void {
      if (e.key === 'Escape') {
        e.preventDefault();
        isOpen = false;
      }
    }

    window.addEventListener('keydown', handleKeydown);
    return () => window.removeEventListener('keydown', handleKeydown);
  });

  // Focus panel when opened for keyboard accessibility
  $effect(() => {
    if (isOpen && panelEl) {
      requestAnimationFrame(() => {
        panelEl?.focus();
      });
    }
  });

  function handleClose(): void {
    isOpen = false;
  }
</script>

{#if isOpen}
  <aside
    bind:this={panelEl}
    class="context-panel {className}"
    style:width="{width}px"
    role="complementary"
    aria-label={title || 'Context panel'}
    tabindex={-1}
  >
    <!-- Header -->
    <header class="panel-header">
      <h2 class="panel-title">
        {title}
      </h2>
      <button
        class="close-button"
        onclick={handleClose}
        aria-label="Close panel"
        title="Close (Esc)"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="close-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </header>

    <!-- Content -->
    <div class="panel-content">
      {@render children()}
    </div>
  </aside>
{/if}

<style>
  .context-panel {
    position: fixed;
    top: 0;
    right: 0;
    height: 100%;
    z-index: 40;
    display: flex;
    flex-direction: column;
    background-color: oklch(0.13 0 0);
    border-left: 1px solid oklch(0.22 0 0);
    box-shadow: -4px 0 24px oklch(0 0 0 / 0.4);
    animation: context-panel-slide-in 200ms ease-out forwards;
  }

  @keyframes context-panel-slide-in {
    from {
      transform: translateX(100%);
    }
    to {
      transform: translateX(0);
    }
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 3rem;
    padding-left: 1rem;
    padding-right: 1rem;
    flex-shrink: 0;
    border-bottom: 1px solid oklch(0.20 0 0);
  }

  .panel-title {
    font-size: 0.875rem;
    line-height: 1.25rem;
    font-weight: 600;
    color: oklch(0.85 0 0);
    letter-spacing: 0.025em;
  }

  .close-button {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 1.75rem;
    height: 1.75rem;
    border-radius: 0.375rem;
    border: none;
    background: none;
    color: oklch(0.55 0 0);
    transition: color 150ms, background-color 150ms;
    cursor: pointer;
  }

  .close-button:hover {
    color: oklch(0.80 0 0);
    background-color: oklch(0.20 0 0);
  }

  .close-icon {
    width: 16px;
    height: 16px;
  }

  .panel-content {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
  }
</style>
