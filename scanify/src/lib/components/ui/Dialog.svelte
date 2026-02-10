<script lang="ts">
	import type { Snippet } from 'svelte';
	import { onMount } from 'svelte';

	interface Props {
		open?: boolean;
		title?: string;
		class?: string;
		content?: Snippet;
		footer?: Snippet;
		onclose?: () => void;
	}

	let {
		open = $bindable(false),
		title = '',
		class: className = '',
		content,
		footer,
		onclose
	}: Props = $props();

	let dialogEl: HTMLDialogElement | undefined = $state();
	let previouslyFocused: HTMLElement | null = null;

	function close() {
		open = false;
		onclose?.();
	}

	function handleBackdropClick(e: MouseEvent) {
		if (e.target === dialogEl) {
			close();
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			e.preventDefault();
			close();
		}

		// Focus trap
		if (e.key === 'Tab' && dialogEl) {
			const focusable = dialogEl.querySelectorAll<HTMLElement>(
				'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
			);
			const first = focusable[0];
			const last = focusable[focusable.length - 1];

			if (e.shiftKey) {
				if (document.activeElement === first) {
					e.preventDefault();
					last?.focus();
				}
			} else {
				if (document.activeElement === last) {
					e.preventDefault();
					first?.focus();
				}
			}
		}
	}

	$effect(() => {
		if (open && dialogEl) {
			previouslyFocused = document.activeElement as HTMLElement;
			dialogEl.showModal();

			// Focus the first focusable element inside the dialog
			requestAnimationFrame(() => {
				const focusable = dialogEl?.querySelectorAll<HTMLElement>(
					'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
				);
				if (focusable && focusable.length > 0) {
					// Skip the close button, focus the next element if possible
					const target = focusable.length > 1 ? focusable[1] : focusable[0];
					target?.focus();
				}
			});
		} else if (!open && dialogEl) {
			dialogEl.close();
			previouslyFocused?.focus();
			previouslyFocused = null;
		}
	});

	// Prevent native dialog escape handling (we handle it ourselves)
	function handleCancel(e: Event) {
		e.preventDefault();
		close();
	}
</script>

{#if open}
	<dialog
		bind:this={dialogEl}
		class="fixed inset-0 z-50 m-0 h-full w-full max-h-full max-w-full bg-transparent p-0 backdrop:bg-transparent open:flex open:items-center open:justify-center"
		onclick={handleBackdropClick}
		onkeydown={handleKeydown}
		oncancel={handleCancel}
		aria-modal="true"
		aria-labelledby={title ? 'dialog-title' : undefined}
	>
		<!-- Backdrop -->
		<div class="fixed inset-0 bg-black/60 backdrop-blur-sm" aria-hidden="true"></div>

		<!-- Panel -->
		<div
			class="relative z-10 w-full max-w-lg mx-4 rounded-xl border border-[oklch(0.24_0.005_270)] bg-[oklch(0.14_0.005_270)] shadow-2xl shadow-black/50 {className}"
			onclick={(e) => e.stopPropagation()}
		>
			<!-- Header -->
			{#if title}
				<div class="flex items-center justify-between border-b border-[oklch(0.22_0_0)] px-5 py-4">
					<h2
						id="dialog-title"
						class="text-base font-semibold text-[oklch(0.90_0_0)]"
					>
						{title}
					</h2>
					<button
						type="button"
						onclick={close}
						class="rounded-lg p-1 text-[oklch(0.45_0_0)] transition-colors hover:text-[oklch(0.75_0_0)] hover:bg-[oklch(0.20_0_0)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[oklch(0.40_0_0)]"
						aria-label="Close dialog"
					>
						<svg
							xmlns="http://www.w3.org/2000/svg"
							class="h-5 w-5"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							stroke-width="2"
						>
							<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
						</svg>
					</button>
				</div>
			{:else}
				<button
					type="button"
					onclick={close}
					class="absolute top-3 right-3 z-10 rounded-lg p-1 text-[oklch(0.45_0_0)] transition-colors hover:text-[oklch(0.75_0_0)] hover:bg-[oklch(0.20_0_0)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[oklch(0.40_0_0)]"
					aria-label="Close dialog"
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						class="h-5 w-5"
						fill="none"
						viewBox="0 0 24 24"
						stroke="currentColor"
						stroke-width="2"
					>
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			{/if}

			<!-- Content -->
			<div class="px-5 py-4 text-sm text-[oklch(0.75_0_0)]">
				{@render content?.()}
			</div>

			<!-- Footer -->
			{#if footer}
				<div class="flex items-center justify-end gap-3 border-t border-[oklch(0.22_0_0)] px-5 py-3.5">
					{@render footer?.()}
				</div>
			{/if}
		</div>
	</dialog>
{/if}
