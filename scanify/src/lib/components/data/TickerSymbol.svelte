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
</script>

<div
	class="ticker-symbol {className}"
	title={name ?? symbol}
>
	<span class="ticker-text size-{size}">
		{symbol.toUpperCase()}
	</span>
	{#if showName && name}
		<span class="ticker-name size-{size}-name">
			{name}
		</span>
	{/if}
</div>

<style>
	.ticker-symbol {
		display: inline-flex;
		flex-direction: column;
		justify-content: center;
	}

	.ticker-text {
		font-family: var(--font-mono);
		font-weight: 600;
		text-transform: uppercase;
		line-height: 1.2;
		letter-spacing: 0.02em;
		color: oklch(0.90 0 0);
	}

	.ticker-text.size-sm {
		font-size: var(--text-xs);
	}

	.ticker-text.size-md {
		font-size: var(--text-sm);
	}

	.ticker-text.size-lg {
		font-size: var(--text-base, 1rem);
	}

	.ticker-name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		line-height: 1.2;
		max-width: 120px;
		color: oklch(0.50 0 0);
	}

	.ticker-name.size-sm-name {
		font-size: 10px;
	}

	.ticker-name.size-md-name {
		font-size: var(--text-xs);
	}

	.ticker-name.size-lg-name {
		font-size: var(--text-sm);
	}
</style>
