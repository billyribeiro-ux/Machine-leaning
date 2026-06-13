<script lang="ts">
	interface Props {
		value?: number;
		min?: number;
		max?: number;
		step?: number;
		disabled?: boolean;
		label?: string;
		showValue?: boolean;
		class?: string;
		id?: string;
		oninput?: (e: Event) => void;
		[key: string]: unknown;
	}

	let {
		value = $bindable(0),
		min = 0,
		max = 100,
		step = 1,
		disabled = false,
		label = '',
		showValue = true,
		class: className = '',
		id,
		oninput,
		...rest
	}: Props = $props();

	const sliderId = $derived(
		id || (label ? `slider-${label.toLowerCase().replace(/\s+/g, '-')}` : undefined)
	);

	let percentage = $derived(((value - min) / (max - min)) * 100);
</script>

<div class="slider-wrapper {className}">
	{#if label || showValue}
		<div class="slider-header">
			{#if label}
				<label
					for={sliderId}
					class="slider-label"
				>
					{label}
				</label>
			{/if}
			{#if showValue}
				<span class="slider-value">
					{value}
				</span>
			{/if}
		</div>
	{/if}

	<input
		type="range"
		id={sliderId}
		bind:value
		{min}
		{max}
		{step}
		{disabled}
		{oninput}
		class="slider-track"
		class:is-disabled={disabled}
		style="background: linear-gradient(to right, oklch(0.45 0.12 145) 0%, oklch(0.45 0.12 145) {percentage}%, oklch(0.20 0 0) {percentage}%, oklch(0.20 0 0) 100%);"
		{...rest}
	/>
</div>

<style>
	.slider-wrapper {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.slider-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.slider-label {
		font-size: var(--text-xs);
		font-weight: 500;
		color: oklch(0.65 0 0);
		user-select: none;
	}

	.slider-value {
		font-size: var(--text-xs);
		font-family: var(--font-mono);
		color: oklch(0.75 0 0);
	}

	.slider-track {
		width: 100%;
		height: 6px;
		border-radius: var(--radius-full);
		appearance: none;
		-webkit-appearance: none;
		cursor: pointer;
		background-color: oklch(0.20 0 0);
		outline: none;
		transition: opacity 150ms;
	}

	.slider-track.is-disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.slider-track::-webkit-slider-thumb {
		appearance: none;
		-webkit-appearance: none;
		height: 16px;
		width: 16px;
		border-radius: var(--radius-full);
		background-color: oklch(0.55 0.15 145);
		box-shadow: 0 0 0 3px oklch(0.13 0 0);
		transition: all 150ms;
	}

	.slider-track::-webkit-slider-thumb:hover {
		background-color: oklch(0.60 0.16 145);
		transform: scale(1.1);
	}

	.slider-track::-moz-range-thumb {
		border: 0;
		height: 16px;
		width: 16px;
		border-radius: var(--radius-full);
		background-color: oklch(0.55 0.15 145);
		box-shadow: 0 0 0 3px oklch(0.13 0 0);
		transition: all 150ms;
	}

	.slider-track::-moz-range-thumb:hover {
		background-color: oklch(0.60 0.16 145);
	}
</style>
