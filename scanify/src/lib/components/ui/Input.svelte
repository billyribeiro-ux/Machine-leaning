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
</script>

<div class="input-wrapper">
	{#if label}
		<label
			for={inputId}
			class="input-label"
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
		class="input-field {className}"
		class:has-error={!!error}
		class:is-disabled={disabled}
		{oninput}
		{onchange}
		aria-invalid={error ? 'true' : undefined}
		aria-describedby={error ? `${inputId}-error` : undefined}
		{...rest}
	/>

	{#if error}
		<p
			id={inputId ? `${inputId}-error` : undefined}
			class="input-error"
		>
			{error}
		</p>
	{/if}
</div>

<style>
	.input-wrapper {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.input-label {
		font-size: var(--text-xs);
		font-weight: 500;
		color: oklch(0.65 0 0);
		user-select: none;
	}

	.input-field {
		width: 100%;
		border-radius: var(--radius-lg);
		background-color: oklch(0.13 0 0);
		color: oklch(0.88 0 0);
		padding-inline: 12px;
		padding-block: 8px;
		font-size: var(--text-sm);
		transition: all 150ms;
		outline: none;
		border: 1px solid oklch(0.24 0 0);
	}

	.input-field::placeholder {
		color: oklch(0.45 0 0);
	}

	.input-field:focus {
		border-color: oklch(0.45 0.12 250);
		box-shadow: 0 0 0 2px oklch(0.45 0.12 250 / 0.3);
	}

	.input-field.has-error {
		border-color: oklch(0.55 0.18 25);
	}

	.input-field.has-error:focus {
		border-color: oklch(0.60 0.19 25);
		box-shadow: 0 0 0 2px oklch(0.55 0.18 25 / 0.3);
	}

	.input-field.is-disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.input-error {
		font-size: 11px;
		color: oklch(0.65 0.16 25);
	}
</style>
