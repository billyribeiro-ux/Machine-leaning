<!--
  ToastStack.svelte
  Fixed bottom-right toast notification stack.
  Auto-dismiss with $effect timers, max 5 visible, slide-in animation.
  Colored left borders: info=blue, success=green, warning=amber, error=red.
-->
<script lang="ts">
  type ToastVariant = 'info' | 'success' | 'warning' | 'error';

  interface Toast {
    id: string;
    message: string;
    variant: ToastVariant;
    duration?: number;
  }

  interface ToastStackProps {
    /** Array of active toasts. */
    toasts: Toast[];
    /** Callback when a toast should be removed. */
    onremove: (id: string) => void;
    /** Additional CSS classes. */
    class?: string;
  }

  let {
    toasts,
    onremove,
    class: className = '',
  }: ToastStackProps = $props();

  /** Only show the last 5 toasts. */
  let visibleToasts = $derived(toasts.slice(-5));

  /** Map variant to left-border color. */
  function borderColor(variant: ToastVariant): string {
    switch (variant) {
      case 'info':    return 'border-l-[oklch(0.55_0.15_250)]';
      case 'success': return 'border-l-[oklch(0.55_0.15_145)]';
      case 'warning': return 'border-l-[oklch(0.65_0.15_85)]';
      case 'error':   return 'border-l-[oklch(0.55_0.18_25)]';
    }
  }

  /** Map variant to icon color. */
  function iconColor(variant: ToastVariant): string {
    switch (variant) {
      case 'info':    return 'text-[oklch(0.60_0.15_250)]';
      case 'success': return 'text-[oklch(0.60_0.15_145)]';
      case 'warning': return 'text-[oklch(0.70_0.15_85)]';
      case 'error':   return 'text-[oklch(0.60_0.18_25)]';
    }
  }

  /** Map variant to display label. */
  function variantLabel(variant: ToastVariant): string {
    switch (variant) {
      case 'info':    return 'Info';
      case 'success': return 'Success';
      case 'warning': return 'Warning';
      case 'error':   return 'Error';
    }
  }

  // Auto-dismiss timers via $effect
  $effect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];

    for (const toast of toasts) {
      const duration = toast.duration ?? 5000;
      if (duration > 0) {
        const timer = setTimeout(() => {
          onremove(toast.id);
        }, duration);
        timers.push(timer);
      }
    }

    return () => {
      for (const timer of timers) {
        clearTimeout(timer);
      }
    };
  });

  function handleDismiss(id: string): void {
    onremove(id);
  }
</script>

<div
  class="fixed bottom-4 right-4 z-50 flex flex-col-reverse gap-2 pointer-events-none {className}"
  aria-live="polite"
  aria-label="Notifications"
>
  {#each visibleToasts as toast (toast.id)}
    <div
      class="
        toast-enter pointer-events-auto
        flex items-start gap-3
        w-[360px] max-w-[calc(100vw-2rem)]
        px-4 py-3
        rounded-lg border border-[oklch(0.22_0_0)] border-l-[3px]
        bg-[oklch(0.14_0_0)]
        shadow-[0_4px_24px_oklch(0_0_0/0.5)]
        {borderColor(toast.variant)}
      "
      role="alert"
    >
      <!-- Variant icon -->
      <span class="shrink-0 mt-0.5 {iconColor(toast.variant)}">
        {#if toast.variant === 'info'}
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
        {:else if toast.variant === 'success'}
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
        {:else if toast.variant === 'warning'}
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        {:else}
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
        {/if}
      </span>

      <!-- Message content -->
      <div class="flex flex-col gap-0.5 flex-1 min-w-0">
        <span class="text-[11px] font-semibold uppercase tracking-wider {iconColor(toast.variant)}">
          {variantLabel(toast.variant)}
        </span>
        <p class="text-xs text-[oklch(0.78_0_0)] leading-relaxed m-0 break-words">
          {toast.message}
        </p>
      </div>

      <!-- Close button -->
      <button
        class="
          shrink-0 flex items-center justify-center
          w-5 h-5 mt-0.5 rounded
          text-[oklch(0.45_0_0)] hover:text-[oklch(0.70_0_0)]
          hover:bg-[oklch(0.20_0_0)]
          transition-colors duration-100
          cursor-pointer border-none bg-transparent
        "
        onclick={() => handleDismiss(toast.id)}
        aria-label="Dismiss notification"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  {/each}
</div>

<style>
  .toast-enter {
    animation: toast-slide-in 250ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
  }

  @keyframes toast-slide-in {
    from {
      opacity: 0;
      transform: translateX(100%);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }
</style>
