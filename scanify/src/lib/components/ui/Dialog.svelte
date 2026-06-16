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
		class="dialog-root"
		onclick={handleBackdropClick}
		onkeydown={handleKeydown}
		oncancel={handleCancel}
		aria-modal="true"
		aria-labelledby={title ? 'dialog-title' : undefined}
	>
		<!-- Backdrop -->
		<div class="dialog-backdrop" aria-hidden="true"></div>

		<!-- Panel -->
		<div
			class="dialog-panel {className}"
			onclick={(e) => e.stopPropagation()}
		>
			<!-- Header -->
			{#if title}
				<div class="dialog-header">
					<h2
						id="dialog-title"
						class="dialog-title"
					>
						{title}
					</h2>
					<button
						type="button"
						onclick={close}
						class="dialog-close-btn"
						aria-label="Close dialog"
					>
						<svg
							xmlns="http://www.w3.org/2000/svg"
							class="close-icon"
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
					class="dialog-close-btn dialog-close-absolute"
					aria-label="Close dialog"
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						class="close-icon"
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
			<div class="dialog-content">
				{@render content?.()}
			</div>

			<!-- Footer -->
			{#if footer}
				<div class="dialog-footer">
					{@render footer?.()}
				</div>
			{/if}
		</div>
	</dialog>
{/if}

<style>
	.dialog-root {
		position: fixed;
		inset: 0;
		z-index: var(--z-modal, 400);
		margin: 0;
		height: 100%;
		width: 100%;
		max-height: 100%;
		max-width: 100%;
		background: transparent;
		padding: 0;
		border: none;
	}

	.dialog-root[open] {
		display: flex;
		align-items: center;
		justify-content: center;
	}

	/* Override native dialog backdrop */
	.dialog-root::backdrop {
		background: transparent;
	}

	.dialog-backdrop {
		position: fixed;
		inset: 0;
		background-color: rgba(0, 0, 0, 0.60);
		backdrop-filter: blur(4px);
	}

	.dialog-panel {
		position: relative;
		z-index: 10;
		width: 100%;
		max-width: 512px;
		margin-inline: 16px;
		border-radius: var(--radius-xl);
		border: 1px solid oklch(0.24 0.005 270);
		background-color: oklch(0.14 0.005 270);
		box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5);
	}

	.dialog-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		border-bottom: 1px solid oklch(0.22 0 0);
		padding-inline: 20px;
		padding-block: 16px;
	}

	.dialog-title {
		font-size: var(--text-base);
		font-weight: 600;
		color: oklch(0.90 0 0);
	}

	.dialog-close-btn {
		border-radius: var(--radius-lg);
		padding: 4px;
		color: oklch(0.45 0 0);
		transition: color 150ms, background-color 150ms;
		outline: none;
	}

	.dialog-close-btn:hover {
		color: oklch(0.75 0 0);
		background-color: oklch(0.20 0 0);
	}

	.dialog-close-btn:focus-visible {
		outline: 2px solid oklch(0.40 0 0);
		outline-offset: 2px;
	}

	.dialog-close-absolute {
		position: absolute;
		top: 12px;
		right: 12px;
		z-index: 10;
	}

	.close-icon {
		height: 20px;
		width: 20px;
	}

	.dialog-content {
		padding-inline: 20px;
		padding-block: 16px;
		font-size: var(--text-sm);
		color: oklch(0.75 0 0);
	}

	.dialog-footer {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 12px;
		border-top: 1px solid oklch(0.22 0 0);
		padding-inline: 20px;
		padding-block: 14px;
	}
</style>
