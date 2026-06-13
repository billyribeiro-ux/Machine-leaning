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
  class="toast-stack {className}"
  aria-live="polite"
  aria-label="Notifications"
>
  {#each visibleToasts as toast (toast.id)}
    <div
      class="toast toast--{toast.variant}"
      role="alert"
    >
      <!-- Variant icon -->
      <span class="toast__icon toast__icon--{toast.variant}">
        {#if toast.variant === 'info'}
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon--md" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
        {:else if toast.variant === 'success'}
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon--md" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
        {:else if toast.variant === 'warning'}
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon--md" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        {:else}
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon--md" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
        {/if}
      </span>

      <!-- Message content -->
      <div class="toast__content">
        <span class="toast__label toast__label--{toast.variant}">
          {variantLabel(toast.variant)}
        </span>
        <p class="toast__message">
          {toast.message}
        </p>
      </div>

      <!-- Close button -->
      <button
        class="toast__close"
        onclick={() => handleDismiss(toast.id)}
        aria-label="Dismiss notification"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="icon icon--sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  {/each}
</div>

<style>
  /* ── Stack container ── */
  .toast-stack {
    position: fixed;
    bottom: 16px;
    right: 16px;
    z-index: 50;
    display: flex;
    flex-direction: column-reverse;
    gap: 8px;
    pointer-events: none;
  }

  /* ── Individual toast ── */
  .toast {
    animation: toast-slide-in 250ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
    pointer-events: auto;
    display: flex;
    align-items: flex-start;
    gap: 12px;
    width: 360px;
    max-width: calc(100vw - 2rem);
    padding: 12px 16px;
    border-radius: var(--radius-lg);
    border: 1px solid oklch(0.22 0 0);
    border-left: 3px solid;
    background: oklch(0.14 0 0);
    box-shadow: 0 4px 24px oklch(0 0 0 / 0.5);
  }

  /* ── Variant border colors ── */
  .toast--info {
    border-left-color: oklch(0.55 0.15 250);
  }

  .toast--success {
    border-left-color: oklch(0.55 0.15 145);
  }

  .toast--warning {
    border-left-color: oklch(0.65 0.15 85);
  }

  .toast--error {
    border-left-color: oklch(0.55 0.18 25);
  }

  /* ── Icon ── */
  .toast__icon {
    flex-shrink: 0;
    margin-top: 2px;
  }

  .toast__icon--info {
    color: oklch(0.60 0.15 250);
  }

  .toast__icon--success {
    color: oklch(0.60 0.15 145);
  }

  .toast__icon--warning {
    color: oklch(0.70 0.15 85);
  }

  .toast__icon--error {
    color: oklch(0.60 0.18 25);
  }

  /* ── SVG icon sizes ── */
  .icon--md {
    width: 16px;
    height: 16px;
  }

  .icon--sm {
    width: 12px;
    height: 12px;
  }

  /* ── Message content ── */
  .toast__content {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 1;
    min-width: 0;
  }

  /* ── Variant label ── */
  .toast__label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .toast__label--info {
    color: oklch(0.60 0.15 250);
  }

  .toast__label--success {
    color: oklch(0.60 0.15 145);
  }

  .toast__label--warning {
    color: oklch(0.70 0.15 85);
  }

  .toast__label--error {
    color: oklch(0.60 0.18 25);
  }

  /* ── Message text ── */
  .toast__message {
    font-size: 12px;
    color: oklch(0.78 0 0);
    line-height: 1.625;
    margin: 0;
    overflow-wrap: break-word;
  }

  /* ── Close button ── */
  .toast__close {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    margin-top: 2px;
    border-radius: var(--radius-DEFAULT);
    color: oklch(0.45 0 0);
    background: transparent;
    border: none;
    cursor: pointer;
    transition: color 100ms, background-color 100ms;
  }

  .toast__close:hover {
    color: oklch(0.70 0 0);
    background-color: oklch(0.20 0 0);
  }

  /* ── Slide-in animation ── */
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
