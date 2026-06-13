<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		variant?: 'default' | 'bullish' | 'bearish' | 'neutral' | 'warning' | 'accent';
		size?: 'sm' | 'md';
		class?: string;
		children?: Snippet;
	}

	let {
		variant = 'default',
		size = 'sm',
		class: className = '',
		children
	}: Props = $props();
</script>

<span
	class="badge size-{size} variant-{variant} {className}"
>
	{@render children?.()}
</span>

<style>
	.badge {
		display: inline-flex;
		align-items: center;
		border-radius: var(--radius-full);
		border: 1px solid;
		font-weight: 500;
		line-height: 1;
		white-space: nowrap;
	}

	/* Sizes */
	.size-sm {
		font-size: 10px;
		padding-inline: 8px;
		padding-block: 2px;
	}

	.size-md {
		font-size: var(--text-xs);
		padding-inline: 10px;
		padding-block: 4px;
	}

	/* Variants */
	.variant-default {
		background-color: oklch(0.20 0 0);
		color: oklch(0.70 0 0);
		border-color: oklch(0.28 0 0);
	}

	.variant-bullish {
		background-color: oklch(0.20 0.04 145);
		color: oklch(0.75 0.15 145);
		border-color: oklch(0.30 0.06 145);
	}

	.variant-bearish {
		background-color: oklch(0.20 0.04 25);
		color: oklch(0.70 0.16 25);
		border-color: oklch(0.30 0.06 25);
	}

	.variant-neutral {
		background-color: oklch(0.20 0.03 250);
		color: oklch(0.72 0.12 250);
		border-color: oklch(0.30 0.05 250);
	}

	.variant-warning {
		background-color: oklch(0.22 0.04 80);
		color: oklch(0.78 0.14 80);
		border-color: oklch(0.32 0.06 80);
	}

	.variant-accent {
		background-color: oklch(0.20 0.04 300);
		color: oklch(0.72 0.14 300);
		border-color: oklch(0.30 0.06 300);
	}
</style>
