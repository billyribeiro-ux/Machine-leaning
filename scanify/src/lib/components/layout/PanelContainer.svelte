<!--
  PanelContainer.svelte
  Resizable panel wrapper with collapse/expand animation.
  Surface background, subtle border, optional header with title.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { PanelId } from '$lib/types';

  interface PanelContainerProps {
    /** Unique panel identifier. */
    id: PanelId;
    /** Minimum width in pixels. */
    minWidth?: number;
    /** Minimum height in pixels. */
    minHeight?: number;
    /** Whether the panel is collapsed (bindable). */
    isCollapsed?: boolean;
    /** Optional panel title shown in the header bar. */
    title?: string;
    /** Panel content snippet. */
    children: Snippet;
    /** Additional CSS classes. */
    class?: string;
  }

  let {
    id,
    minWidth = 200,
    minHeight = 120,
    isCollapsed = $bindable(false),
    title = '',
    children,
    class: className = '',
  }: PanelContainerProps = $props();

  let isHovered = $state(false);

  function toggleCollapse(): void {
    isCollapsed = !isCollapsed;
  }

  function handleKeydown(e: KeyboardEvent): void {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggleCollapse();
    }
  }
</script>

<section
  class="panel-container {className}"
  class:panel-container--collapsed={isCollapsed}
  style:min-width={isCollapsed ? 'auto' : `${minWidth}px`}
  style:min-height={isCollapsed ? 'auto' : `${minHeight}px`}
  data-panel-id={id}
  onmouseenter={() => { isHovered = true; }}
  onmouseleave={() => { isHovered = false; }}
  aria-label={title || `Panel ${id}`}
>
  <!-- Header (shown if title provided or always for collapse control) -->
  {#if title}
    <header class="panel-container__header">
      <h3 class="panel-container__title">{title}</h3>

      <div class="panel-container__actions">
        <button
          class="panel-container__collapse-btn"
          onclick={toggleCollapse}
          onkeydown={handleKeydown}
          aria-label={isCollapsed ? 'Expand panel' : 'Collapse panel'}
          aria-expanded={!isCollapsed}
          title={isCollapsed ? 'Expand' : 'Collapse'}
        >
          <span
            class="panel-container__collapse-icon"
            class:panel-container__collapse-icon--collapsed={isCollapsed}
            aria-hidden="true"
          >
            {'\u2303'}
          </span>
        </button>
      </div>
    </header>
  {/if}

  <!-- Content area (hidden when collapsed) -->
  <div
    class="panel-container__content"
    class:panel-container__content--collapsed={isCollapsed}
  >
    {@render children()}
  </div>
</section>

<style>
  .panel-container {
    display: flex;
    flex-direction: column;
    background-color: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    overflow: hidden;
    transition:
      min-width 250ms cubic-bezier(0.16, 1, 0.3, 1),
      min-height 250ms cubic-bezier(0.16, 1, 0.3, 1);
  }

  .panel-container:hover {
    border-color: var(--border-default);
  }

  .panel-container--collapsed {
    min-width: auto !important;
    min-height: auto !important;
  }

  /* ---- Header ---- */
  .panel-container__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 12px;
    height: 36px;
    flex-shrink: 0;
    background-color: var(--bg-elevated);
    border-bottom: 1px solid var(--border-subtle);
    user-select: none;
  }

  .panel-container__title {
    font-family: var(--font-display);
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-secondary);
    letter-spacing: 0.02em;
    text-transform: uppercase;
    line-height: 1;
    margin: 0;
  }

  .panel-container__actions {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  /* ---- Collapse button ---- */
  .panel-container__collapse-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-tertiary);
    cursor: pointer;
    transition: background-color 100ms ease, color 100ms ease;
  }

  .panel-container__collapse-btn:hover {
    background-color: var(--hover-overlay);
    color: var(--text-secondary);
  }

  .panel-container__collapse-btn:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 1px;
  }

  .panel-container__collapse-icon {
    font-size: var(--text-sm);
    line-height: 1;
    transition: transform 250ms cubic-bezier(0.16, 1, 0.3, 1);
    display: block;
  }

  .panel-container__collapse-icon--collapsed {
    transform: rotate(180deg);
  }

  /* ---- Content ---- */
  .panel-container__content {
    flex: 1;
    overflow: auto;
    transition:
      opacity 200ms ease,
      max-height 250ms cubic-bezier(0.16, 1, 0.3, 1);
  }

  .panel-container__content--collapsed {
    max-height: 0;
    opacity: 0;
    overflow: hidden;
    pointer-events: none;
  }
</style>
