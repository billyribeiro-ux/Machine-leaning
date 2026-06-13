<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
		size?: 'sm' | 'md' | 'lg';
		disabled?: boolean;
		loading?: boolean;
		class?: string;
		children?: Snippet;
		onclick?: (e: MouseEvent) => void;
		type?: 'button' | 'submit' | 'reset';
		[key: string]: unknown;
	}

	let {
		variant = 'primary',
		size = 'md',
		disabled = false,
		loading = false,
		class: className = '',
		children,
		onclick,
		type = 'button',
		...rest
	}: Props = $props();
</script>

<button
	{type}
	class="btn variant-{variant} size-{size} {className}"
	class:is-disabled={disabled || loading}
	class:is-loading={loading}
	disabled={disabled || loading}
	onclick={onclick}
	aria-busy={loading}
	{...rest}
>
	{#if loading}
		<svg
			class="spinner-icon"
			xmlns="http://www.w3.org/2000/svg"
			fill="none"
			viewBox="0 0 24 24"
		>
			<circle class="spinner-track" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"
			></circle>
			<path
				class="spinner-head"
				fill="currentColor"
				d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
			></path>
		</svg>
	{/if}
	{@render children?.()}
</button>

<style>
	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		font-weight: 500;
		border-radius: var(--radius-lg);
		transition: all 150ms ease-out;
		outline: none;
		user-select: none;
		cursor: pointer;
	}

	.btn:focus-visible {
		outline: 2px solid var(--focus-ring, oklch(0.55 0.15 145));
		outline-offset: 2px;
	}

	/* Sizes */
	.size-sm {
		font-size: var(--text-xs);
		padding-inline: 10px;
		padding-block: 6px;
		gap: 6px;
	}

	.size-md {
		font-size: var(--text-sm);
		padding-inline: 16px;
		padding-block: 8px;
		gap: 8px;
	}

	.size-lg {
		font-size: var(--text-base);
		padding-inline: 24px;
		padding-block: 10px;
		gap: 10px;
	}

	/* Variants */
	.variant-primary {
		background-color: oklch(0.55 0.15 145);
		color: white;
		box-shadow: 0 1px 2px oklch(0.55 0.15 145 / 0.25);
	}

	.variant-primary:hover {
		background-color: oklch(0.60 0.16 145);
	}

	.variant-primary:active {
		background-color: oklch(0.50 0.14 145);
	}

	.variant-primary:focus-visible {
		outline-color: oklch(0.55 0.15 145);
	}

	.variant-secondary {
		background-color: oklch(0.20 0.005 270);
		color: oklch(0.80 0 0);
		border: 1px solid oklch(0.28 0.005 270);
	}

	.variant-secondary:hover {
		background-color: oklch(0.24 0.005 270);
		color: white;
	}

	.variant-secondary:active {
		background-color: oklch(0.18 0.005 270);
	}

	.variant-secondary:focus-visible {
		outline-color: oklch(0.40 0.01 270);
	}

	.variant-ghost {
		background-color: transparent;
		color: oklch(0.70 0 0);
	}

	.variant-ghost:hover {
		background-color: oklch(0.20 0 0);
		color: oklch(0.85 0 0);
	}

	.variant-ghost:active {
		background-color: oklch(0.18 0 0);
	}

	.variant-ghost:focus-visible {
		outline-color: oklch(0.40 0 0);
	}

	.variant-danger {
		background-color: oklch(0.50 0.18 25);
		color: white;
		box-shadow: 0 1px 2px oklch(0.50 0.18 25 / 0.25);
	}

	.variant-danger:hover {
		background-color: oklch(0.55 0.19 25);
	}

	.variant-danger:active {
		background-color: oklch(0.45 0.17 25);
	}

	.variant-danger:focus-visible {
		outline-color: oklch(0.50 0.18 25);
	}

	/* States */
	.is-disabled {
		opacity: 0.5;
		cursor: not-allowed;
		pointer-events: none;
	}

	.is-loading {
		animation: pulse-loading 1.8s ease-in-out infinite;
	}

	/* Spinner */
	.spinner-icon {
		height: 16px;
		width: 16px;
		animation: spin 1s linear infinite;
	}

	.spinner-track {
		opacity: 0.25;
	}

	.spinner-head {
		opacity: 0.75;
	}

	@keyframes spin {
		from { transform: rotate(0deg); }
		to { transform: rotate(360deg); }
	}

	@keyframes pulse-loading {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.5; }
	}
</style>
