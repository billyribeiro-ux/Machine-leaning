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
			bg: 'oklch(0.35 0.10 145)',
			text: 'oklch(0.80 0.14 145)',
			glow: '0 0 8px oklch(0.50 0.15 145 / 0.3)',
			border: 'oklch(0.45 0.12 145 / 0.5)'
		},
		bearish: {
			bg: 'oklch(0.32 0.10 25)',
			text: 'oklch(0.78 0.14 25)',
			glow: '0 0 8px oklch(0.50 0.18 25 / 0.3)',
			border: 'oklch(0.42 0.12 25 / 0.5)'
		},
		neutral: {
			bg: 'oklch(0.28 0.04 250)',
			text: 'oklch(0.72 0.06 250)',
			glow: '0 0 8px oklch(0.45 0.06 250 / 0.3)',
			border: 'oklch(0.38 0.04 250 / 0.5)'
		}
	};

	let style = $derived(directionStyles[direction] ?? directionStyles.neutral);

	let dots = $derived.by(() => {
		let result = '';
		for (let i = 0; i < 5; i++) {
			result += i < clampedStrength ? '●' : '○';
		}
		return result;
	});
</script>

<span
	class="signal-badge {className}"
	style="background-color: {style.bg}; color: {style.text}; box-shadow: {style.glow}; border-color: {style.border};"
>
	{#if label}
		<span class="badge-label">{label}</span>
	{/if}
	<span class="badge-dots" aria-label="Strength {clampedStrength} of 5">
		{dots}
	</span>
</span>

<style>
	.signal-badge {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		border-radius: var(--radius-full);
		border: 1px solid;
		padding-inline: 10px;
		padding-block: 2px;
		font-size: var(--text-xs);
		font-weight: 500;
	}

	.badge-label {
		white-space: nowrap;
	}

	.badge-dots {
		font-family: var(--font-mono);
		font-size: 10px;
		letter-spacing: -0.02em;
		opacity: 0.8;
	}
</style>
