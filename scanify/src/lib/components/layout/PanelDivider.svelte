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

  let cursorClass = $derived(
    orientation === 'vertical' ? 'cursor-col-resize' : 'cursor-row-resize'
  );

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
  class="
    relative flex items-center justify-center select-none
    {orientation === 'vertical' ? 'w-[4px] h-full flex-col' : 'h-[4px] w-full flex-row'}
    {cursorClass}
    {className}
  "
  onmousedown={handleMouseDown}
  onmouseenter={() => { isHovered = true; }}
  onmouseleave={() => { isHovered = false; }}
  role="separator"
  aria-orientation={orientation}
  tabindex={0}
>
  <!-- Visible 1px line -->
  <div
    class="
      transition-colors duration-150
      {orientation === 'vertical'
        ? 'w-px h-full'
        : 'h-px w-full'}
      {lineActive
        ? 'bg-[oklch(0.50_0_0)]'
        : 'bg-[oklch(0.25_0_0)]'}
    "
  ></div>

  <!-- Drag indicator dots (shown on hover/drag) -->
  {#if lineActive}
    <div
      class="
        absolute flex gap-[2px]
        {orientation === 'vertical'
          ? 'flex-col top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2'
          : 'flex-row top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2'}
      "
    >
      <span class="block w-[3px] h-[3px] rounded-full bg-[oklch(0.50_0_0)]"></span>
      <span class="block w-[3px] h-[3px] rounded-full bg-[oklch(0.50_0_0)]"></span>
      <span class="block w-[3px] h-[3px] rounded-full bg-[oklch(0.50_0_0)]"></span>
    </div>
  {/if}
</div>

<style>
  div[role="separator"]:focus-visible {
    outline: 2px solid var(--focus-ring, oklch(0.55 0.15 250));
    outline-offset: -1px;
  }
</style>
