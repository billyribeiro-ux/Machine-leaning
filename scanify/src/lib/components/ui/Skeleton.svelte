<script lang="ts">
	interface Props {
		width?: string;
		height?: string;
		rounded?: 'sm' | 'md' | 'lg' | 'full';
		class?: string;
	}

	let {
		width = '100%',
		height = '1rem',
		rounded = 'md',
		class: className = ''
	}: Props = $props();

	const roundedClasses: Record<string, string> = {
		sm: 'rounded-sm',
		md: 'rounded-md',
		lg: 'rounded-lg',
		full: 'rounded-full'
	};

	let computedClass = $derived(
		`animate-pulse bg-[oklch(0.20_0.005_270)] ${roundedClasses[rounded]} ${className}`.trim()
	);
</script>

<div
	class={computedClass}
	style="width: {width}; height: {height};"
	aria-hidden="true"
	role="presentation"
></div>
