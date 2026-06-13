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

<div class="toggle-wrapper">
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
		class="toggle-track size-{size}"
		class:is-checked={checked}
		class:is-disabled={disabled}
		onclick={handleClick}
		onkeydown={handleKeydown}
	>
		<span
			class="toggle-thumb size-{size}"
			class:is-checked={checked}
		></span>
	</button>

	{#if label}
		<label
			id="{toggleId}-label"
			for={toggleId}
			class="toggle-label"
			class:is-disabled={disabled}
		>
			{label}
		</label>
	{/if}
</div>

<style>
	.toggle-wrapper {
		display: inline-flex;
		align-items: center;
		gap: 10px;
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		white-space: nowrap;
		border-width: 0;
	}

	.toggle-track {
		position: relative;
		display: inline-flex;
		flex-shrink: 0;
		align-items: center;
		border-radius: var(--radius-full);
		transition: background-color 200ms ease-in-out;
		cursor: pointer;
		background-color: oklch(0.24 0 0);
	}

	.toggle-track.size-sm {
		width: 32px;
		height: 18px;
	}

	.toggle-track.size-md {
		width: 44px;
		height: 24px;
	}

	.toggle-track.is-checked {
		background-color: oklch(0.55 0.15 145);
	}

	.toggle-track.is-disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.toggle-track:not(.is-disabled):hover {
		filter: brightness(1.1);
	}

	.toggle-thumb {
		display: inline-block;
		border-radius: var(--radius-full);
		background-color: white;
		box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
		transform: translateX(2px);
		transition: transform 200ms ease-in-out;
	}

	.toggle-thumb.size-sm {
		height: 14px;
		width: 14px;
	}

	.toggle-thumb.size-md {
		height: 20px;
		width: 20px;
	}

	.toggle-thumb.size-sm.is-checked {
		transform: translateX(14px);
	}

	.toggle-thumb.size-md.is-checked {
		transform: translateX(20px);
	}

	.toggle-label {
		font-size: var(--text-sm);
		color: oklch(0.75 0 0);
		user-select: none;
		cursor: pointer;
	}

	.toggle-label.is-disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
</style>
