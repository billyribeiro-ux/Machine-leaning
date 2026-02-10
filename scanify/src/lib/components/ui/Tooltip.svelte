<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		content?: string;
		position?: 'top' | 'bottom' | 'left' | 'right';
		delay?: number;
		children?: Snippet;
		class?: string;
	}

	let {
		content = '',
		position = 'top',
		delay = 300,
		children,
		class: className = ''
	}: Props = $props();

	let visible = $state(false);
	let timeoutId: ReturnType<typeof setTimeout> | null = $state(null);

	function showTooltip() {
		timeoutId = setTimeout(() => {
			visible = true;
		}, delay);
	}

	function hideTooltip() {
		if (timeoutId) {
			clearTimeout(timeoutId);
			timeoutId = null;
		}
		visible = false;
	}

	const positionClasses: Record<string, string> = {
		top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
		bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
		left: 'right-full top-1/2 -translate-y-1/2 mr-2',
		right: 'left-full top-1/2 -translate-y-1/2 ml-2'
	};

	const arrowClasses: Record<string, string> = {
		top: 'top-full left-1/2 -translate-x-1/2 border-t-[oklch(0.22_0.005_270)] border-x-transparent border-b-transparent',
		bottom: 'bottom-full left-1/2 -translate-x-1/2 border-b-[oklch(0.22_0.005_270)] border-x-transparent border-t-transparent',
		left: 'left-full top-1/2 -translate-y-1/2 border-l-[oklch(0.22_0.005_270)] border-y-transparent border-r-transparent',
		right: 'right-full top-1/2 -translate-y-1/2 border-r-[oklch(0.22_0.005_270)] border-y-transparent border-l-transparent'
	};

	const arrowBorderSize: Record<string, string> = {
		top: 'border-[5px]',
		bottom: 'border-[5px]',
		left: 'border-[5px]',
		right: 'border-[5px]'
	};
</script>

<div
	class="relative inline-flex {className}"
	onmouseenter={showTooltip}
	onmouseleave={hideTooltip}
	onfocusin={showTooltip}
	onfocusout={hideTooltip}
>
	{@render children?.()}

	{#if visible && content}
		<div
			role="tooltip"
			class="absolute z-50 {positionClasses[position]} pointer-events-none"
		>
			<div
				class="relative rounded-md bg-[oklch(0.22_0.005_270)] px-2.5 py-1.5 text-xs font-medium text-[oklch(0.88_0_0)] shadow-lg shadow-black/30 whitespace-nowrap animate-in fade-in duration-150"
			>
				{content}
				<!-- Arrow -->
				<span
					class="absolute w-0 h-0 {arrowBorderSize[position]} {arrowClasses[position]}"
				></span>
			</div>
		</div>
	{/if}
</div>
