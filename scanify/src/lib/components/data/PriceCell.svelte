<script lang="ts">
	interface Props {
		value: number;
		prevValue?: number;
		decimals?: number;
		size?: 'sm' | 'md' | 'lg';
		class?: string;
	}

	let {
		value,
		prevValue,
		decimals = 2,
		size = 'md',
		class: className = ''
	}: Props = $props();

	let flashClass = $state('');
	let flashTimeout: ReturnType<typeof setTimeout> | undefined;

	let formatted = $derived.by(() => {
		if (value == null || isNaN(value)) return '$--';
		return '$' + value.toFixed(decimals);
	});

	$effect(() => {
		const current = value;
		const prev = prevValue;

		if (prev != null && current !== prev) {
			if (flashTimeout) clearTimeout(flashTimeout);

			if (current > prev) {
				flashClass = 'flash-up';
			} else if (current < prev) {
				flashClass = 'flash-down';
			}

			flashTimeout = setTimeout(() => {
				flashClass = '';
			}, 400);
		}

		return () => {
			if (flashTimeout) clearTimeout(flashTimeout);
		};
	});
</script>

<span
	class="price-cell size-{size} {flashClass} {className}"
	style="font-variant-numeric: tabular-nums;"
>
	{formatted}
</span>

<style>
	.price-cell {
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

	.flash-up {
		animation: flash-green 400ms ease-out;
	}
	.flash-down {
		animation: flash-red 400ms ease-out;
	}
	@keyframes flash-green {
		0% {
			background-color: oklch(0.55 0.15 145 / 0.4);
			color: oklch(0.85 0.12 145);
		}
		100% {
			background-color: transparent;
		}
	}
	@keyframes flash-red {
		0% {
			background-color: oklch(0.50 0.18 25 / 0.4);
			color: oklch(0.80 0.14 25);
		}
		100% {
			background-color: transparent;
		}
	}
</style>
