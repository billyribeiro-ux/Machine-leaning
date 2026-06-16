<script lang="ts">
	import { onMount } from 'svelte';

	interface Props {
		message?: string;
		variant?: 'info' | 'success' | 'warning' | 'error';
		duration?: number;
		onclose?: () => void;
	}

	let {
		message = '',
		variant = 'info',
		duration = 4000,
		onclose
	}: Props = $props();

	let visible = $state(false);
	let progress = $state(100);
	let animationFrame: number | null = null;
	let startTime: number;

	const variantConfig: Record<string, { icon: string }> = {
		info: {
			icon: 'M12 16v-4m0-4h.01M22 12c0 5.523-4.477 10-10 10S2 17.523 2 12 6.477 2 12 2s10 4.477 10 10z'
		},
		success: {
			icon: 'M9 12l2 2 4-4m6 2a10 10 0 11-20 0 10 10 0 0120 0z'
		},
		warning: {
			icon: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z'
		},
		error: {
			icon: 'M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a10 10 0 11-20 0 10 10 0 0120 0z'
		}
	};

	function startProgressAnimation() {
		startTime = performance.now();

		function tick(now: number) {
			const elapsed = now - startTime;
			progress = Math.max(0, 100 - (elapsed / duration) * 100);

			if (progress > 0) {
				animationFrame = requestAnimationFrame(tick);
			} else {
				close();
			}
		}

		animationFrame = requestAnimationFrame(tick);
	}

	function close() {
		visible = false;
		if (animationFrame !== null) {
			cancelAnimationFrame(animationFrame);
			animationFrame = null;
		}
		setTimeout(() => {
			onclose?.();
		}, 200);
	}

	onMount(() => {
		requestAnimationFrame(() => {
			visible = true;
		});
		startProgressAnimation();

		return () => {
			if (animationFrame !== null) {
				cancelAnimationFrame(animationFrame);
			}
		};
	});

	let config = $derived(variantConfig[variant]);
</script>

<div
	class="toast variant-{variant}"
	class:is-visible={visible}
	class:is-hidden={!visible}
	role="alert"
	aria-live="assertive"
>
	<div class="toast-body">
		<!-- Icon -->
		<svg
			xmlns="http://www.w3.org/2000/svg"
			class="toast-icon variant-{variant}"
			fill="none"
			viewBox="0 0 24 24"
			stroke="currentColor"
			stroke-width="1.5"
		>
			<path stroke-linecap="round" stroke-linejoin="round" d={config.icon} />
		</svg>

		<!-- Message -->
		<p class="toast-message">
			{message}
		</p>

		<!-- Close button -->
		<button
			type="button"
			onclick={close}
			class="toast-close"
			aria-label="Dismiss"
		>
			<svg
				xmlns="http://www.w3.org/2000/svg"
				class="toast-close-icon"
				fill="none"
				viewBox="0 0 24 24"
				stroke="currentColor"
				stroke-width="2"
			>
				<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
			</svg>
		</button>
	</div>

	<!-- Progress bar -->
	<div class="toast-progress-track">
		<div
			class="toast-progress-bar variant-{variant}"
			style="width: {progress}%"
		></div>
	</div>
</div>

<style>
	.toast {
		pointer-events: auto;
		width: 320px;
		overflow: hidden;
		border-radius: var(--radius-lg);
		border: 1px solid;
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
		transition: all 200ms ease-out;
	}

	.toast.is-visible {
		transform: translateX(0);
		opacity: 1;
	}

	.toast.is-hidden {
		transform: translateX(100%);
		opacity: 0;
	}

	/* Variant backgrounds and borders */
	.toast.variant-info {
		background-color: oklch(0.15 0.02 250);
		border-color: oklch(0.30 0.08 250);
	}

	.toast.variant-success {
		background-color: oklch(0.15 0.02 145);
		border-color: oklch(0.30 0.08 145);
	}

	.toast.variant-warning {
		background-color: oklch(0.16 0.02 80);
		border-color: oklch(0.32 0.08 80);
	}

	.toast.variant-error {
		background-color: oklch(0.15 0.02 25);
		border-color: oklch(0.30 0.08 25);
	}

	.toast-body {
		display: flex;
		align-items: flex-start;
		gap: 12px;
		padding: 14px;
	}

	.toast-icon {
		height: 20px;
		width: 20px;
		flex-shrink: 0;
	}

	.toast-icon.variant-info { color: oklch(0.65 0.14 250); }
	.toast-icon.variant-success { color: oklch(0.65 0.14 145); }
	.toast-icon.variant-warning { color: oklch(0.72 0.14 80); }
	.toast-icon.variant-error { color: oklch(0.65 0.16 25); }

	.toast-message {
		flex: 1;
		font-size: var(--text-sm);
		color: oklch(0.85 0 0);
		line-height: 1.4;
	}

	.toast-close {
		flex-shrink: 0;
		border-radius: var(--radius-DEFAULT);
		padding: 2px;
		color: oklch(0.50 0 0);
		transition: color 150ms, background-color 150ms;
		outline: none;
	}

	.toast-close:hover {
		color: oklch(0.75 0 0);
		background-color: oklch(0.20 0 0);
	}

	.toast-close-icon {
		height: 16px;
		width: 16px;
	}

	.toast-progress-track {
		height: 2px;
		width: 100%;
		background-color: oklch(0.12 0 0);
	}

	.toast-progress-bar {
		height: 100%;
		transition: none;
	}

	.toast-progress-bar.variant-info { background-color: oklch(0.55 0.14 250); }
	.toast-progress-bar.variant-success { background-color: oklch(0.55 0.15 145); }
	.toast-progress-bar.variant-warning { background-color: oklch(0.65 0.14 80); }
	.toast-progress-bar.variant-error { background-color: oklch(0.55 0.18 25); }
</style>
