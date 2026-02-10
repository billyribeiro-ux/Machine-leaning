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

	const variantConfig: Record<string, { bg: string; border: string; icon: string; iconColor: string }> = {
		info: {
			bg: 'bg-[oklch(0.15_0.02_250)]',
			border: 'border-[oklch(0.30_0.08_250)]',
			icon: 'M12 16v-4m0-4h.01M22 12c0 5.523-4.477 10-10 10S2 17.523 2 12 6.477 2 12 2s10 4.477 10 10z',
			iconColor: 'text-[oklch(0.65_0.14_250)]'
		},
		success: {
			bg: 'bg-[oklch(0.15_0.02_145)]',
			border: 'border-[oklch(0.30_0.08_145)]',
			icon: 'M9 12l2 2 4-4m6 2a10 10 0 11-20 0 10 10 0 0120 0z',
			iconColor: 'text-[oklch(0.65_0.14_145)]'
		},
		warning: {
			bg: 'bg-[oklch(0.16_0.02_80)]',
			border: 'border-[oklch(0.32_0.08_80)]',
			icon: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z',
			iconColor: 'text-[oklch(0.72_0.14_80)]'
		},
		error: {
			bg: 'bg-[oklch(0.15_0.02_25)]',
			border: 'border-[oklch(0.30_0.08_25)]',
			icon: 'M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a10 10 0 11-20 0 10 10 0 0120 0z',
			iconColor: 'text-[oklch(0.65_0.16_25)]'
		}
	};

	const progressBarColors: Record<string, string> = {
		info: 'bg-[oklch(0.55_0.14_250)]',
		success: 'bg-[oklch(0.55_0.15_145)]',
		warning: 'bg-[oklch(0.65_0.14_80)]',
		error: 'bg-[oklch(0.55_0.18_25)]'
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
	class="pointer-events-auto w-80 overflow-hidden rounded-lg border shadow-xl shadow-black/30 transition-all duration-200 ease-out
		{config.bg} {config.border}
		{visible ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0'}"
	role="alert"
	aria-live="assertive"
>
	<div class="flex items-start gap-3 p-3.5">
		<!-- Icon -->
		<svg
			xmlns="http://www.w3.org/2000/svg"
			class="h-5 w-5 shrink-0 {config.iconColor}"
			fill="none"
			viewBox="0 0 24 24"
			stroke="currentColor"
			stroke-width="1.5"
		>
			<path stroke-linecap="round" stroke-linejoin="round" d={config.icon} />
		</svg>

		<!-- Message -->
		<p class="flex-1 text-sm text-[oklch(0.85_0_0)] leading-snug">
			{message}
		</p>

		<!-- Close button -->
		<button
			type="button"
			onclick={close}
			class="shrink-0 rounded p-0.5 text-[oklch(0.50_0_0)] transition-colors hover:text-[oklch(0.75_0_0)] hover:bg-[oklch(0.20_0_0)] focus:outline-none"
			aria-label="Dismiss"
		>
			<svg
				xmlns="http://www.w3.org/2000/svg"
				class="h-4 w-4"
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
	<div class="h-0.5 w-full bg-[oklch(0.12_0_0)]">
		<div
			class="h-full transition-none {progressBarColors[variant]}"
			style="width: {progress}%"
		></div>
	</div>
</div>
