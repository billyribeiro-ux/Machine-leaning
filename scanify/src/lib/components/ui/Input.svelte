<script lang="ts">
	interface Props {
		type?: string;
		placeholder?: string;
		value?: string;
		disabled?: boolean;
		error?: string;
		label?: string;
		class?: string;
		id?: string;
		name?: string;
		oninput?: (e: Event) => void;
		onchange?: (e: Event) => void;
		[key: string]: unknown;
	}

	let {
		type = 'text',
		placeholder = '',
		value = $bindable(''),
		disabled = false,
		error = '',
		label = '',
		class: className = '',
		id,
		name,
		oninput,
		onchange,
		...rest
	}: Props = $props();

	const inputId = $derived(id || (label ? `input-${label.toLowerCase().replace(/\s+/g, '-')}` : undefined));

	const baseInputClasses =
		'w-full rounded-lg bg-[oklch(0.13_0_0)] text-[oklch(0.88_0_0)] placeholder-[oklch(0.45_0_0)] px-3 py-2 text-sm transition-all duration-150 outline-none';

	const borderClasses = $derived(
		error
			? 'border border-[oklch(0.55_0.18_25)] focus:border-[oklch(0.60_0.19_25)] focus:ring-2 focus:ring-[oklch(0.55_0.18_25/0.3)]'
			: 'border border-[oklch(0.24_0_0)] focus:border-[oklch(0.45_0.12_250)] focus:ring-2 focus:ring-[oklch(0.45_0.12_250/0.3)]'
	);

	const disabledClasses = $derived(
		disabled ? 'opacity-50 cursor-not-allowed' : ''
	);

	let computedInputClass = $derived(
		`${baseInputClasses} ${borderClasses} ${disabledClasses} ${className}`.trim()
	);
</script>

<div class="flex flex-col gap-1.5">
	{#if label}
		<label
			for={inputId}
			class="text-xs font-medium text-[oklch(0.65_0_0)] select-none"
		>
			{label}
		</label>
	{/if}

	<input
		{type}
		id={inputId}
		{name}
		{placeholder}
		{disabled}
		bind:value
		class={computedInputClass}
		{oninput}
		{onchange}
		aria-invalid={error ? 'true' : undefined}
		aria-describedby={error ? `${inputId}-error` : undefined}
		{...rest}
	/>

	{#if error}
		<p
			id={inputId ? `${inputId}-error` : undefined}
			class="text-[11px] text-[oklch(0.65_0.16_25)]"
		>
			{error}
		</p>
	{/if}
</div>
