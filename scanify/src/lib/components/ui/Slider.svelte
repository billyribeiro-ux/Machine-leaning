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

<div class="flex flex-col gap-2 {className}">
	{#if label || showValue}
		<div class="flex items-center justify-between">
			{#if label}
				<label
					for={sliderId}
					class="text-xs font-medium text-[oklch(0.65_0_0)] select-none"
				>
					{label}
				</label>
			{/if}
			{#if showValue}
				<span class="text-xs font-mono text-[oklch(0.75_0_0)]">
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
		class="slider-track w-full h-1.5 rounded-full appearance-none cursor-pointer
			bg-[oklch(0.20_0_0)] outline-none transition-opacity
			{disabled ? 'opacity-50 cursor-not-allowed' : ''}
			[&::-webkit-slider-thumb]:appearance-none
			[&::-webkit-slider-thumb]:h-4
			[&::-webkit-slider-thumb]:w-4
			[&::-webkit-slider-thumb]:rounded-full
			[&::-webkit-slider-thumb]:bg-[oklch(0.55_0.15_145)]
			[&::-webkit-slider-thumb]:shadow-[0_0_0_3px_oklch(0.13_0_0)]
			[&::-webkit-slider-thumb]:transition-all
			[&::-webkit-slider-thumb]:duration-150
			[&::-webkit-slider-thumb]:hover:bg-[oklch(0.60_0.16_145)]
			[&::-webkit-slider-thumb]:hover:scale-110
			[&::-moz-range-thumb]:border-0
			[&::-moz-range-thumb]:h-4
			[&::-moz-range-thumb]:w-4
			[&::-moz-range-thumb]:rounded-full
			[&::-moz-range-thumb]:bg-[oklch(0.55_0.15_145)]
			[&::-moz-range-thumb]:shadow-[0_0_0_3px_oklch(0.13_0_0)]
			[&::-moz-range-thumb]:transition-all
			[&::-moz-range-thumb]:duration-150
			[&::-moz-range-thumb]:hover:bg-[oklch(0.60_0.16_145)]"
		style="background: linear-gradient(to right, oklch(0.45 0.12 145) 0%, oklch(0.45 0.12 145) {percentage}%, oklch(0.20 0 0) {percentage}%, oklch(0.20 0 0) 100%);"
		{...rest}
	/>
</div>
