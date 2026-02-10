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
    class="
      context-panel
      fixed top-0 right-0 h-full z-40
      flex flex-col
      bg-[oklch(0.13_0_0)] border-l border-[oklch(0.22_0_0)]
      shadow-[-4px_0_24px_oklch(0_0_0/0.4)]
      {className}
    "
    style:width="{width}px"
    role="complementary"
    aria-label={title || 'Context panel'}
    tabindex={-1}
  >
    <!-- Header -->
    <header class="flex items-center justify-between h-12 px-4 shrink-0 border-b border-[oklch(0.20_0_0)]">
      <h2 class="text-sm font-semibold text-[oklch(0.85_0_0)] tracking-wide">
        {title}
      </h2>
      <button
        class="
          flex items-center justify-center w-7 h-7
          rounded-md border-none
          text-[oklch(0.55_0_0)] hover:text-[oklch(0.80_0_0)]
          hover:bg-[oklch(0.20_0_0)]
          transition-colors duration-150
          cursor-pointer
        "
        onclick={handleClose}
        aria-label="Close panel"
        title="Close (Esc)"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </header>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto overflow-x-hidden">
      {@render children()}
    </div>
  </aside>
{/if}

<style>
  .context-panel {
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
</style>
