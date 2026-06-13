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
		cmd: '⌘',
		command: '⌘',
		meta: '⌘',
		ctrl: '⌃',
		control: '⌃',
		alt: '⌥',
		option: '⌥',
		opt: '⌥',
		shift: '⇧',
		enter: '⏎',
		return: '⏎',
		backspace: '⌫',
		delete: '⌦',
		escape: 'Esc',
		esc: 'Esc',
		tab: '⇥',
		space: '␣',
		up: '↑',
		down: '↓',
		left: '←',
		right: '→'
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

<span class="kbd-group {className}" aria-label="Keyboard shortcut: {keys}">
	{#each parsedKeys as key, i (i)}
		{#if i > 0}
			<span class="kbd-separator">+</span>
		{/if}
		<kbd class="kbd-key">
			{key}
		</kbd>
	{/each}
</span>

<style>
	.kbd-group {
		display: inline-flex;
		align-items: center;
		gap: 2px;
	}

	.kbd-separator {
		color: oklch(0.40 0 0);
		font-size: 10px;
		margin-inline: 1px;
		user-select: none;
	}

	.kbd-key {
		display: inline-flex;
		height: 20px;
		min-width: 20px;
		align-items: center;
		justify-content: center;
		border-radius: var(--radius-DEFAULT);
		border: 1px solid oklch(0.28 0.005 270);
		background-color: oklch(0.17 0.005 270);
		padding-inline: 6px;
		font-family: var(--font-mono);
		font-size: 10px;
		font-weight: 500;
		color: oklch(0.65 0 0);
		box-shadow: 0 1px 0 1px oklch(0.10 0 0);
		line-height: 1;
	}
</style>
