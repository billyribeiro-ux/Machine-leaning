<script lang="ts">
	interface Props {
		value: number;
		signed?: boolean;
		size?: 'sm' | 'md' | 'lg';
		class?: string;
	}

	let {
		value,
		signed = true,
		size = 'md',
		class: className = ''
	}: Props = $props();

	let colorStyle = $derived.by(() => {
		if (value > 0) return 'color: oklch(0.72 0.14 145);';
		if (value < 0) return 'color: oklch(0.72 0.16 25);';
		return 'color: oklch(0.60 0 0);';
	});

	let formatted = $derived.by(() => {
		if (value == null || isNaN(value)) return '--%';
		const abs = Math.abs(value).toFixed(2);
		if (!signed) return abs + '%';
		if (value > 0) return '+' + abs + '%';
		if (value < 0) return '-' + abs + '%';
		return abs + '%';
	});
</script>

<span
	class="percent-cell size-{size} {className}"
	style="{colorStyle} font-variant-numeric: tabular-nums;"
>
	{formatted}
</span>

<style>
	.percent-cell {
		display: inline-block;
		text-align: right;
		font-family: var(--font-mono);
		font-variant-numeric: tabular-nums;
	}

	.size-sm {
		font-size: var(--text-xs);
	}

	.size-md {
		font-size: var(--text-sm);
	}

	.size-lg {
		font-size: var(--text-base, 1rem);
	}
</style>
