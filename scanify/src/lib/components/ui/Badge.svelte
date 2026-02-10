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

	const variantClasses: Record<string, string> = {
		default:
			'bg-[oklch(0.20_0_0)] text-[oklch(0.70_0_0)] border-[oklch(0.28_0_0)]',
		bullish:
			'bg-[oklch(0.20_0.04_145)] text-[oklch(0.75_0.15_145)] border-[oklch(0.30_0.06_145)]',
		bearish:
			'bg-[oklch(0.20_0.04_25)] text-[oklch(0.70_0.16_25)] border-[oklch(0.30_0.06_25)]',
		neutral:
			'bg-[oklch(0.20_0.03_250)] text-[oklch(0.72_0.12_250)] border-[oklch(0.30_0.05_250)]',
		warning:
			'bg-[oklch(0.22_0.04_80)] text-[oklch(0.78_0.14_80)] border-[oklch(0.32_0.06_80)]',
		accent:
			'bg-[oklch(0.20_0.04_300)] text-[oklch(0.72_0.14_300)] border-[oklch(0.30_0.06_300)]'
	};

	const sizeClasses: Record<string, string> = {
		sm: 'text-[10px] px-2 py-0.5',
		md: 'text-xs px-2.5 py-1'
	};

	let computedClass = $derived(
		`inline-flex items-center rounded-full border font-medium leading-none whitespace-nowrap ${variantClasses[variant]} ${sizeClasses[size]} ${className}`.trim()
	);
</script>

<span class={computedClass}>
	{@render children?.()}
</span>
