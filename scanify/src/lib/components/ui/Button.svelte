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

	const baseClasses =
		'inline-flex items-center justify-center font-medium rounded-lg transition-all duration-150 ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-[oklch(0.13_0_0)] select-none';

	const variantClasses: Record<string, string> = {
		primary:
			'bg-[oklch(0.55_0.15_145)] text-white hover:bg-[oklch(0.60_0.16_145)] active:bg-[oklch(0.50_0.14_145)] focus-visible:ring-[oklch(0.55_0.15_145)] shadow-sm shadow-[oklch(0.55_0.15_145/0.25)]',
		secondary:
			'bg-[oklch(0.20_0.005_270)] text-[oklch(0.80_0_0)] border border-[oklch(0.28_0.005_270)] hover:bg-[oklch(0.24_0.005_270)] hover:text-white active:bg-[oklch(0.18_0.005_270)] focus-visible:ring-[oklch(0.40_0.01_270)]',
		ghost:
			'bg-transparent text-[oklch(0.70_0_0)] hover:bg-[oklch(0.20_0_0)] hover:text-[oklch(0.85_0_0)] active:bg-[oklch(0.18_0_0)] focus-visible:ring-[oklch(0.40_0_0)]',
		danger:
			'bg-[oklch(0.50_0.18_25)] text-white hover:bg-[oklch(0.55_0.19_25)] active:bg-[oklch(0.45_0.17_25)] focus-visible:ring-[oklch(0.50_0.18_25)] shadow-sm shadow-[oklch(0.50_0.18_25/0.25)]'
	};

	const sizeClasses: Record<string, string> = {
		sm: 'text-xs px-2.5 py-1.5 gap-1.5',
		md: 'text-sm px-4 py-2 gap-2',
		lg: 'text-base px-6 py-2.5 gap-2.5'
	};

	let computedClass = $derived(
		`${baseClasses} ${variantClasses[variant]} ${sizeClasses[size]} ${disabled || loading ? 'opacity-50 cursor-not-allowed pointer-events-none' : 'cursor-pointer'} ${loading ? 'animate-pulse' : ''} ${className}`.trim()
	);
</script>

<button
	{type}
	class={computedClass}
	disabled={disabled || loading}
	onclick={onclick}
	aria-busy={loading}
	{...rest}
>
	{#if loading}
		<svg
			class="h-4 w-4 animate-spin"
			xmlns="http://www.w3.org/2000/svg"
			fill="none"
			viewBox="0 0 24 24"
		>
			<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"
			></circle>
			<path
				class="opacity-75"
				fill="currentColor"
				d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
			></path>
		</svg>
	{/if}
	{@render children?.()}
</button>
