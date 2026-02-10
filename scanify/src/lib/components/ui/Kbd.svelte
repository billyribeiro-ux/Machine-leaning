<script lang="ts">
	interface Props {
		keys?: string;
		class?: string;
	}

	let {
		keys = '',
		class: className = ''
	}: Props = $props();

	const modifierMap: Record<string, string> = {
		cmd: '\u2318',
		command: '\u2318',
		meta: '\u2318',
		ctrl: '\u2303',
		control: '\u2303',
		alt: '\u2325',
		option: '\u2325',
		opt: '\u2325',
		shift: '\u21E7',
		enter: '\u23CE',
		return: '\u23CE',
		backspace: '\u232B',
		delete: '\u2326',
		escape: 'Esc',
		esc: 'Esc',
		tab: '\u21E5',
		space: '\u2423',
		up: '\u2191',
		down: '\u2193',
		left: '\u2190',
		right: '\u2192'
	};

	let parsedKeys = $derived(
		keys
			.split('+')
			.map((k) => k.trim())
			.filter(Boolean)
			.map((k) => {
				const lower = k.toLowerCase();
				return modifierMap[lower] || k.toUpperCase();
			})
	);
</script>

<span class="inline-flex items-center gap-0.5 {className}" aria-label="Keyboard shortcut: {keys}">
	{#each parsedKeys as key, i (i)}
		{#if i > 0}
			<span class="text-[oklch(0.40_0_0)] text-[10px] mx-px select-none">+</span>
		{/if}
		<kbd
			class="inline-flex h-5 min-w-5 items-center justify-center rounded border border-[oklch(0.28_0.005_270)] bg-[oklch(0.17_0.005_270)] px-1.5 font-mono text-[10px] font-medium text-[oklch(0.65_0_0)] shadow-[0_1px_0_1px_oklch(0.10_0_0)] leading-none"
		>
			{key}
		</kbd>
	{/each}
</span>
