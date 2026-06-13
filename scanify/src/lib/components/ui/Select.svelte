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
</script>

<div class="select-wrapper">
	{#if label}
		<label
			for={selectId}
			class="select-label"
		>
			{label}
		</label>
	{/if}

	<div class="select-inner">
		<select
			id={selectId}
			{name}
			{disabled}
			bind:value
			class="select-field {className}"
			class:is-disabled={disabled}
			{onchange}
			{...rest}
		>
			{#if placeholder}
				<option value="" disabled selected class="select-placeholder">
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
		<div class="select-chevron">
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

<style>
	.select-wrapper {
		position: relative;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.select-label {
		font-size: var(--text-xs);
		font-weight: 500;
		color: oklch(0.65 0 0);
		user-select: none;
	}

	.select-inner {
		position: relative;
	}

	.select-field {
		width: 100%;
		appearance: none;
		-webkit-appearance: none;
		border-radius: var(--radius-lg);
		background-color: oklch(0.13 0 0);
		color: oklch(0.88 0 0);
		padding-inline: 12px;
		padding-inline-end: 36px;
		padding-block: 8px;
		font-size: var(--text-sm);
		border: 1px solid oklch(0.24 0 0);
		transition: all 150ms;
		outline: none;
		cursor: pointer;
	}

	.select-field:focus {
		border-color: oklch(0.45 0.12 250);
		box-shadow: 0 0 0 2px oklch(0.45 0.12 250 / 0.3);
	}

	.select-field.is-disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.select-placeholder {
		color: oklch(0.45 0 0);
	}

	.select-chevron {
		pointer-events: none;
		position: absolute;
		top: 50%;
		right: 12px;
		transform: translateY(-50%);
		color: oklch(0.50 0 0);
	}
</style>
