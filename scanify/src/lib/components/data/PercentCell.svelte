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

	const sizeClasses: Record<string, string> = {
		sm: 'text-xs',
		md: 'text-sm',
		lg: 'text-base'
	};

	let colorClass = $derived(() => {
		if (value > 0) return 'text-[oklch(0.72_0.14_145)]';
		if (value < 0) return 'text-[oklch(0.72_0.16_25)]';
		return 'text-[oklch(0.60_0_0)]';
	});

	let formatted = $derived(() => {
		if (value == null || isNaN(value)) return '--%';
		const abs = Math.abs(value).toFixed(2);
		if (!signed) return abs + '%';
		if (value > 0) return '+' + abs + '%';
		if (value < 0) return '-' + abs + '%';
		return abs + '%';
	});
</script>

<span
	class="inline-block text-right font-mono tabular-nums {sizeClasses[size]} {colorClass()} {className}"
	style="font-variant-numeric: tabular-nums;"
>
	{formatted()}
</span>
