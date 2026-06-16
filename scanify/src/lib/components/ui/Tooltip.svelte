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
</script>

<div
	class="tooltip-trigger {className}"
	onmouseenter={showTooltip}
	onmouseleave={hideTooltip}
	onfocusin={showTooltip}
	onfocusout={hideTooltip}
>
	{@render children?.()}

	{#if visible && content}
		<div
			role="tooltip"
			class="tooltip-positioner position-{position}"
		>
			<div class="tooltip-content">
				{content}
				<!-- Arrow -->
				<span class="tooltip-arrow position-{position}"></span>
			</div>
		</div>
	{/if}
</div>

<style>
	.tooltip-trigger {
		position: relative;
		display: inline-flex;
	}

	.tooltip-positioner {
		position: absolute;
		z-index: var(--z-tooltip, 700);
		pointer-events: none;
	}

	.tooltip-positioner.position-top {
		bottom: 100%;
		left: 50%;
		transform: translateX(-50%);
		margin-bottom: 8px;
	}

	.tooltip-positioner.position-bottom {
		top: 100%;
		left: 50%;
		transform: translateX(-50%);
		margin-top: 8px;
	}

	.tooltip-positioner.position-left {
		right: 100%;
		top: 50%;
		transform: translateY(-50%);
		margin-right: 8px;
	}

	.tooltip-positioner.position-right {
		left: 100%;
		top: 50%;
		transform: translateY(-50%);
		margin-left: 8px;
	}

	.tooltip-content {
		position: relative;
		border-radius: var(--radius-md);
		background-color: oklch(0.22 0.005 270);
		padding-inline: 10px;
		padding-block: 6px;
		font-size: var(--text-xs);
		font-weight: 500;
		color: oklch(0.88 0 0);
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
		white-space: nowrap;
		animation: tooltip-fade-in 150ms ease-out;
	}

	.tooltip-arrow {
		position: absolute;
		width: 0;
		height: 0;
		border: 5px solid transparent;
	}

	.tooltip-arrow.position-top {
		top: 100%;
		left: 50%;
		transform: translateX(-50%);
		border-top-color: oklch(0.22 0.005 270);
	}

	.tooltip-arrow.position-bottom {
		bottom: 100%;
		left: 50%;
		transform: translateX(-50%);
		border-bottom-color: oklch(0.22 0.005 270);
	}

	.tooltip-arrow.position-left {
		left: 100%;
		top: 50%;
		transform: translateY(-50%);
		border-left-color: oklch(0.22 0.005 270);
	}

	.tooltip-arrow.position-right {
		right: 100%;
		top: 50%;
		transform: translateY(-50%);
		border-right-color: oklch(0.22 0.005 270);
	}

	@keyframes tooltip-fade-in {
		from { opacity: 0; }
		to { opacity: 1; }
	}
</style>
