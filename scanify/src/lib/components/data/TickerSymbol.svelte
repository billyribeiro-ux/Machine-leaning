<script lang="ts">
	interface Props {
		symbol: string;
		name?: string;
		showName?: boolean;
		size?: 'sm' | 'md' | 'lg';
		class?: string;
	}

	let {
		symbol,
		name,
		showName = false,
		size = 'md',
		class: className = ''
	}: Props = $props();

	const sizeClasses: Record<string, { symbol: string; name: string }> = {
		sm: {
			symbol: 'text-xs',
			name: 'text-[10px]'
		},
		md: {
			symbol: 'text-sm',
			name: 'text-xs'
		},
		lg: {
			symbol: 'text-base',
			name: 'text-sm'
		}
	};

	let sizeStyle = $derived(sizeClasses[size] ?? sizeClasses.md);
</script>

<div
	class="inline-flex flex-col justify-center {className}"
	title={name ?? symbol}
>
	<span
		class="font-mono font-semibold uppercase leading-tight text-[oklch(0.90_0_0)] {sizeStyle.symbol}"
		style="letter-spacing: 0.02em;"
	>
		{symbol.toUpperCase()}
	</span>
	{#if showName && name}
		<span
			class="truncate leading-tight text-[oklch(0.50_0_0)] {sizeStyle.name}"
			style="max-width: 120px;"
		>
			{name}
		</span>
	{/if}
</div>
