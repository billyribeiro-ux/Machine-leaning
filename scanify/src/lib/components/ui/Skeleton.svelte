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
</script>

<div
	class="skeleton rounded-{rounded} {className}"
	style="width: {width}; height: {height};"
	aria-hidden="true"
	role="presentation"
></div>

<style>
	.skeleton {
		animation: pulse-loading 1.8s ease-in-out infinite;
		background-color: oklch(0.20 0.005 270);
	}

	.rounded-sm { border-radius: var(--radius-sm); }
	.rounded-md { border-radius: var(--radius-md); }
	.rounded-lg { border-radius: var(--radius-lg); }
	.rounded-full { border-radius: var(--radius-full); }

	@keyframes pulse-loading {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.5; }
	}
</style>
