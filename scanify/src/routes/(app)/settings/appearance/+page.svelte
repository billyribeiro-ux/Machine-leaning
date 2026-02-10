<script lang="ts">
	let activeTheme = $state('dark');
	let density = $state('normal');
	let animationsEnabled = $state(true);

	const themes = [
		{ id: 'dark', name: 'Dark', description: 'Default dark theme', colors: ['oklch(0.11 0.008 260)', 'oklch(0.14 0.010 260)', 'oklch(0.72 0.19 155)', 'oklch(0.65 0.22 25)'] },
		{ id: 'light', name: 'Light', description: 'Light theme for bright environments', colors: ['oklch(0.97 0.005 260)', 'oklch(0.93 0.008 260)', 'oklch(0.45 0.19 155)', 'oklch(0.50 0.22 25)'] },
		{ id: 'high-contrast', name: 'High Contrast', description: 'Enhanced contrast for accessibility', colors: ['oklch(0.05 0.005 260)', 'oklch(0.10 0.008 260)', 'oklch(0.85 0.22 155)', 'oklch(0.80 0.26 25)'] },
		{ id: 'oled', name: 'OLED Black', description: 'True blacks for AMOLED displays', colors: ['oklch(0.00 0 0)', 'oklch(0.08 0.005 260)', 'oklch(0.72 0.19 155)', 'oklch(0.65 0.22 25)'] },
	];

	const densities = [
		{ id: 'compact', name: 'Compact', description: 'Maximum information density' },
		{ id: 'normal', name: 'Normal', description: 'Balanced density' },
		{ id: 'comfortable', name: 'Comfortable', description: 'More whitespace' },
	];
</script>

<div class="flex h-full flex-col gap-6 p-4" style="color: oklch(0.95 0.005 260);">
	<h1 class="text-lg font-semibold">Appearance</h1>

	<section>
		<h2 class="mb-3 text-sm font-medium" style="color: oklch(0.72 0.008 260);">Theme</h2>
		<div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
			{#each themes as theme}
				<button
					onclick={() => activeTheme = theme.id}
					class="flex flex-col gap-2 rounded-lg p-3 text-left transition-all"
					style="background: oklch(0.14 0.010 260); border: 2px solid {activeTheme === theme.id ? 'oklch(0.65 0.18 250)' : 'oklch(0.20 0.008 260)'};"
				>
					<div class="flex gap-1.5">
						{#each theme.colors as color}
							<div class="h-4 w-4 rounded-full" style="background: {color};"></div>
						{/each}
					</div>
					<div>
						<div class="text-xs font-semibold">{theme.name}</div>
						<div class="text-[10px]" style="color: oklch(0.52 0.006 260);">{theme.description}</div>
					</div>
					{#if activeTheme === theme.id}
						<span class="text-[10px] font-medium" style="color: oklch(0.65 0.18 250);">Active</span>
					{/if}
				</button>
			{/each}
		</div>
	</section>

	<section>
		<h2 class="mb-3 text-sm font-medium" style="color: oklch(0.72 0.008 260);">Density</h2>
		<div class="flex gap-3">
			{#each densities as d}
				<button
					onclick={() => density = d.id}
					class="flex-1 rounded-lg p-3 text-left transition-all"
					style="background: oklch(0.14 0.010 260); border: 2px solid {density === d.id ? 'oklch(0.65 0.18 250)' : 'oklch(0.20 0.008 260)'};"
				>
					<div class="text-xs font-semibold">{d.name}</div>
					<div class="text-[10px]" style="color: oklch(0.52 0.006 260);">{d.description}</div>
				</button>
			{/each}
		</div>
	</section>

	<section>
		<h2 class="mb-3 text-sm font-medium" style="color: oklch(0.72 0.008 260);">Animations</h2>
		<div class="flex items-center gap-3">
			<button
				onclick={() => animationsEnabled = !animationsEnabled}
				class="relative h-5 w-9 rounded-full transition-colors"
				style="background: {animationsEnabled ? 'oklch(0.72 0.19 155)' : 'oklch(0.28 0.010 260)'};"
			>
				<span class="absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform" style="left: {animationsEnabled ? '18px' : '2px'};"></span>
			</button>
			<span class="text-xs">{animationsEnabled ? 'Animations enabled' : 'Animations disabled (reduced motion)'}</span>
		</div>
	</section>
</div>
