<script lang="ts">
	interface Props {
		checked?: boolean;
		disabled?: boolean;
		label?: string;
		size?: 'sm' | 'md';
		id?: string;
		onchange?: (e: Event) => void;
		[key: string]: unknown;
	}

	let {
		checked = $bindable(false),
		disabled = false,
		label = '',
		size = 'md',
		id,
		onchange,
		...rest
	}: Props = $props();

	const toggleId = $derived(
		id || (label ? `toggle-${label.toLowerCase().replace(/\s+/g, '-')}` : `toggle-${Math.random().toString(36).slice(2, 8)}`)
	);

	const trackSizes: Record<string, string> = {
		sm: 'w-8 h-[18px]',
		md: 'w-11 h-6'
	};

	const thumbSizes: Record<string, string> = {
		sm: 'h-3.5 w-3.5',
		md: 'h-5 w-5'
	};

	const thumbTranslate: Record<string, string> = {
		sm: 'translate-x-3.5',
		md: 'translate-x-5'
	};

	let trackClass = $derived(
		`relative inline-flex shrink-0 ${trackSizes[size]} items-center rounded-full transition-colors duration-200 ease-in-out cursor-pointer ${
			checked
				? 'bg-[oklch(0.55_0.15_145)]'
				: 'bg-[oklch(0.24_0_0)]'
		} ${disabled ? 'opacity-50 cursor-not-allowed' : 'hover:brightness-110'}`
	);

	let thumbClass = $derived(
		`inline-block ${thumbSizes[size]} rounded-full bg-white shadow-sm transform transition-transform duration-200 ease-in-out ${
			checked ? thumbTranslate[size] : 'translate-x-0.5'
		}`
	);

	function handleClick() {
		if (!disabled) {
			checked = !checked;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === ' ' || e.key === 'Enter') {
			e.preventDefault();
			handleClick();
		}
	}
</script>

<div class="inline-flex items-center gap-2.5">
	<input
		type="checkbox"
		id={toggleId}
		bind:checked
		{disabled}
		{onchange}
		class="sr-only"
		{...rest}
	/>

	<button
		type="button"
		role="switch"
		aria-checked={checked}
		aria-labelledby={label ? `${toggleId}-label` : undefined}
		{disabled}
		class={trackClass}
		onclick={handleClick}
		onkeydown={handleKeydown}
	>
		<span class={thumbClass}></span>
	</button>

	{#if label}
		<label
			id="{toggleId}-label"
			for={toggleId}
			class="text-sm text-[oklch(0.75_0_0)] select-none {disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}"
		>
			{label}
		</label>
	{/if}
</div>
