<script lang="ts">
	interface SelectOption {
		value: string;
		label: string;
	}

	interface Props {
		options?: SelectOption[];
		value?: string;
		placeholder?: string;
		disabled?: boolean;
		label?: string;
		class?: string;
		id?: string;
		name?: string;
		onchange?: (e: Event) => void;
		[key: string]: unknown;
	}

	let {
		options = [],
		value = $bindable(''),
		placeholder = 'Select...',
		disabled = false,
		label = '',
		class: className = '',
		id,
		name,
		onchange,
		...rest
	}: Props = $props();

	const selectId = $derived(
		id || (label ? `select-${label.toLowerCase().replace(/\s+/g, '-')}` : undefined)
	);

	const baseClasses =
		'w-full appearance-none rounded-lg bg-[oklch(0.13_0_0)] text-[oklch(0.88_0_0)] px-3 py-2 pr-9 text-sm border border-[oklch(0.24_0_0)] transition-all duration-150 outline-none focus:border-[oklch(0.45_0.12_250)] focus:ring-2 focus:ring-[oklch(0.45_0.12_250/0.3)] cursor-pointer';

	const disabledClasses = $derived(
		disabled ? 'opacity-50 cursor-not-allowed' : ''
	);

	let computedClass = $derived(
		`${baseClasses} ${disabledClasses} ${className}`.trim()
	);
</script>

<div class="relative flex flex-col gap-1.5">
	{#if label}
		<label
			for={selectId}
			class="text-xs font-medium text-[oklch(0.65_0_0)] select-none"
		>
			{label}
		</label>
	{/if}

	<div class="relative">
		<select
			id={selectId}
			{name}
			{disabled}
			bind:value
			class={computedClass}
			{onchange}
			{...rest}
		>
			{#if placeholder}
				<option value="" disabled selected class="text-[oklch(0.45_0_0)]">
					{placeholder}
				</option>
			{/if}
			{#each options as option (option.value)}
				<option value={option.value}>
					{option.label}
				</option>
			{/each}
		</select>

		<!-- Chevron icon -->
		<div
			class="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-[oklch(0.50_0_0)]"
		>
			<svg
				xmlns="http://www.w3.org/2000/svg"
				width="14"
				height="14"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
				stroke-linejoin="round"
			>
				<path d="m6 9 6 6 6-6" />
			</svg>
		</div>
	</div>
</div>
