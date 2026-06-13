<!--
  PanelDivider.svelte
  Draggable divider between panels for resizing.
  4px hit area, 1px visible line, visual feedback on hover/drag.
-->
<script lang="ts">
  type Orientation = 'horizontal' | 'vertical';

  interface PanelDividerProps {
    /** Orientation: 'horizontal' splits top/bottom, 'vertical' splits left/right. */
    orientation: Orientation;
    /** Callback fired during drag with pixel delta. */
    onresize?: (delta: number) => void;
    /** Additional CSS classes. */
    class?: string;
  }

  let {
    orientation,
    onresize,
    class: className = '',
  }: PanelDividerProps = $props();

  let isDragging = $state(false);
  let isHovered = $state(false);
  let startPos = $state(0);

  let isVertical = $derived(orientation === 'vertical');

  let lineActive = $derived(isDragging || isHovered);

  function handleMouseDown(e: MouseEvent): void {
    e.preventDefault();
    isDragging = true;
    startPos = orientation === 'vertical' ? e.clientX : e.clientY;

    function handleMouseMove(moveEvent: MouseEvent): void {
      const currentPos = orientation === 'vertical' ? moveEvent.clientX : moveEvent.clientY;
      const delta = currentPos - startPos;
      if (delta !== 0) {
        onresize?.(delta);
        startPos = currentPos;
      }
    }

    function handleMouseUp(): void {
      isDragging = false;
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    }

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  class="divider {className}"
  class:vertical={isVertical}
  class:horizontal={!isVertical}
  onmousedown={handleMouseDown}
  onmouseenter={() => { isHovered = true; }}
  onmouseleave={() => { isHovered = false; }}
  role="separator"
  aria-orientation={orientation}
  tabindex={0}
>
  <!-- Visible 1px line -->
  <div
    class="line"
    class:line-vertical={isVertical}
    class:line-horizontal={!isVertical}
    class:line-active={lineActive}
    class:line-inactive={!lineActive}
  ></div>

  <!-- Drag indicator dots (shown on hover/drag) -->
  {#if lineActive}
    <div
      class="dots"
      class:dots-vertical={isVertical}
      class:dots-horizontal={!isVertical}
    >
      <span class="dot"></span>
      <span class="dot"></span>
      <span class="dot"></span>
    </div>
  {/if}
</div>

<style>
  .divider {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    user-select: none;
  }

  .divider.vertical {
    width: 4px;
    height: 100%;
    flex-direction: column;
    cursor: col-resize;
  }

  .divider.horizontal {
    height: 4px;
    width: 100%;
    flex-direction: row;
    cursor: row-resize;
  }

  .divider:focus-visible {
    outline: 2px solid var(--focus-ring, oklch(0.55 0.15 250));
    outline-offset: -1px;
  }

  .line {
    transition: background-color 150ms;
  }

  .line-vertical {
    width: 1px;
    height: 100%;
  }

  .line-horizontal {
    height: 1px;
    width: 100%;
  }

  .line-active {
    background-color: oklch(0.50 0 0);
  }

  .line-inactive {
    background-color: oklch(0.25 0 0);
  }

  .dots {
    position: absolute;
    display: flex;
    gap: 2px;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
  }

  .dots-vertical {
    flex-direction: column;
  }

  .dots-horizontal {
    flex-direction: row;
  }

  .dot {
    display: block;
    width: 3px;
    height: 3px;
    border-radius: 50%;
    background-color: oklch(0.50 0 0);
  }
</style>
