<script lang="ts">
	interface Props {
		direction: 'bullish' | 'bearish' | 'neutral';
		strength: number;
		label?: string;
		class?: string;
	}

	let {
		direction,
		strength,
		label,
		class: className = ''
	}: Props = $props();

	const clampedStrength = $derived(Math.max(1, Math.min(5, Math.round(strength))));

	const directionStyles: Record<string, { bg: string; text: string; glow: string; border: string }> = {
		bullish: {
			bg: 'bg-[oklch(0.35_0.10_145)]',
			text: 'text-[oklch(0.80_0.14_145)]',
			glow: 'shadow-[0_0_8px_oklch(0.50_0.15_145/0.3)]',
			border: 'border-[oklch(0.45_0.12_145/0.5)]'
		},
		bearish: {
			bg: 'bg-[oklch(0.32_0.10_25)]',
			text: 'text-[oklch(0.78_0.14_25)]',
			glow: 'shadow-[0_0_8px_oklch(0.50_0.18_25/0.3)]',
			border: 'border-[oklch(0.42_0.12_25/0.5)]'
		},
		neutral: {
			bg: 'bg-[oklch(0.28_0.04_250)]',
			text: 'text-[oklch(0.72_0.06_250)]',
			glow: 'shadow-[0_0_8px_oklch(0.45_0.06_250/0.3)]',
			border: 'border-[oklch(0.38_0.04_250/0.5)]'
		}
	};

	let style = $derived(directionStyles[direction] ?? directionStyles.neutral);

	let dots = $derived(() => {
		let result = '';
		for (let i = 0; i < 5; i++) {
			result += i < clampedStrength ? '\u25CF' : '\u25CB';
		}
		return result;
	});
</script>

<span
	class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium {style.bg} {style.text} {style.glow} {style.border} {className}"
>
	{#if label}
		<span class="whitespace-nowrap">{label}</span>
	{/if}
	<span class="font-mono text-[10px] tracking-tight opacity-80" aria-label="Strength {clampedStrength} of 5">
		{dots()}
	</span>
</span>
