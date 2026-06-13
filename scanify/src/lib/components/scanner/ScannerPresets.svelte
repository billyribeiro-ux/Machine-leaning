<script lang="ts">
	interface PresetItem {
		id: string;
		name: string;
		icon: string;
	}

	interface Props {
		activePreset: string;
		presets?: PresetItem[];
		class?: string;
	}

	const defaultPresets: PresetItem[] = [
		{ id: 'top-movers', name: 'Top Movers', icon: 'M2 20h.01M7 20v-4M12 20v-8M17 20V8M22 4v16' },
		{ id: 'unusual-volume', name: 'Unusual Volume', icon: 'M3 3v18h18M7 16l4-4 4 4 5-5' },
		{ id: 'breakouts', name: 'Breakouts', icon: 'M13 7l5 5m0 0l-5 5m5-5H6' },
		{ id: 'options-flow', name: 'Options Flow', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6M9 19h6M15 19v-6a2 2 0 012-2h2a2 2 0 012 2v6M12 3v6' },
		{ id: 'institutional', name: 'Institutional', icon: 'M3 21h18M3 10h18M4 6l8-4 8 4M6 10v11M10 10v11M14 10v11M18 10v11' },
		{ id: 'momentum', name: 'Momentum', icon: 'M13 2L3 14h9l-1 8 10-12h-9l1-8' },
	];

	let { activePreset = $bindable(''), presets, class: className = '' }: Props = $props();

	let resolvedPresets = $derived(presets ?? defaultPresets);
	let scrollContainer: HTMLDivElement;

	function selectPreset(id: string) {
		activePreset = id;
	}

	function presetButtonClass(id: string): string {
		const isActive = activePreset === id;
		const base = 'preset-button';

		if (isActive) {
			return base + ' preset-button--active';
		}

		return base + ' preset-button--inactive';
	}
</script>

<div class="presets-wrapper {className}">
	<!-- Scroll shadow indicators -->
	<div class="scroll-shadow scroll-shadow--left"></div>
	<div class="scroll-shadow scroll-shadow--right"></div>

	<!-- Scrollable preset row -->
	<div
		class="presets-row"
		bind:this={scrollContainer}
		role="tablist"
		aria-label="Scanner presets"
	>
		{#each resolvedPresets as preset (preset.id)}
			<button
				type="button"
				class={presetButtonClass(preset.id)}
				onclick={() => selectPreset(preset.id)}
				role="tab"
				aria-selected={activePreset === preset.id}
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
					class="preset-icon"
				>
					<path d={preset.icon} />
				</svg>
				{preset.name}
			</button>
		{/each}
	</div>
</div>

<style>
	.presets-wrapper {
		position: relative;
	}

	.scroll-shadow {
		pointer-events: none;
		position: absolute;
		top: 0;
		bottom: 0;
		z-index: 10;
		width: 24px;
	}

	.scroll-shadow--left {
		left: 0;
		background: linear-gradient(to right, var(--bg-surface), transparent);
	}

	.scroll-shadow--right {
		right: 0;
		background: linear-gradient(to left, var(--bg-surface), transparent);
	}

	.presets-row {
		display: flex;
		align-items: center;
		gap: 6px;
		overflow-x: auto;
		padding: 6px 8px;
		scrollbar-width: none;
	}

	.presets-row::-webkit-scrollbar {
		display: none;
	}

	.preset-button {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		gap: 8px;
		border-radius: var(--radius-lg);
		padding: 8px 14px;
		font-size: var(--text-sm);
		font-weight: 500;
		transition: all 150ms;
		user-select: none;
		white-space: nowrap;
		border: 1px solid;
	}

	.preset-button--active {
		background-color: var(--accent-bg);
		color: var(--accent-bright);
		border-color: var(--accent-dim);
		box-shadow: 0 0 12px 0 var(--accent-bg);
	}

	.preset-button--inactive {
		background-color: transparent;
		color: var(--text-tertiary);
		border-color: transparent;
	}

	.preset-button--inactive:hover {
		background-color: var(--bg-overlay);
		color: var(--text-secondary);
		border-color: var(--border-subtle);
	}

	.preset-icon {
		flex-shrink: 0;
		opacity: 0.7;
	}
</style>
