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
		const base = 'flex-shrink-0 flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-all duration-150 select-none whitespace-nowrap border';

		if (isActive) {
			return base + ' bg-[var(--accent-bg)] text-[var(--accent-bright)] border-[var(--accent-dim)] shadow-[0_0_12px_0_var(--accent-bg)]';
		}

		return base + ' bg-transparent text-[var(--text-tertiary)] border-transparent hover:bg-[var(--bg-overlay)] hover:text-[var(--text-secondary)] hover:border-[var(--border-subtle)]';
	}
</script>

<div class="relative {className}">
	<!-- Scroll shadow indicators -->
	<div class="pointer-events-none absolute left-0 top-0 bottom-0 z-10 w-6 bg-gradient-to-r from-[var(--bg-surface)] to-transparent"></div>
	<div class="pointer-events-none absolute right-0 top-0 bottom-0 z-10 w-6 bg-gradient-to-l from-[var(--bg-surface)] to-transparent"></div>

	<!-- Scrollable preset row -->
	<div
		class="flex items-center gap-1.5 overflow-x-auto px-2 py-1.5 scrollbar-hidden"
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
					class="flex-shrink-0 opacity-70"
				>
					<path d={preset.icon} />
				</svg>
				{preset.name}
			</button>
		{/each}
	</div>
</div>
