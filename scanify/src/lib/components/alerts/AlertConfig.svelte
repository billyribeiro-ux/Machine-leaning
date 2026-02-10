<!--
  AlertConfig.svelte
  Configuration form for setting up trading alert rules.
  Supports scan selection, strength threshold, direction filtering, and notification preferences.
-->
<script lang="ts">
	interface AlertConfigType {
		id: string;
		name: string;
		scanIds: string[];
		minStrength: number;
		directions: string[];
		soundEnabled: boolean;
		pushEnabled: boolean;
		isActive: boolean;
	}

	interface ScanOption {
		id: string;
		label: string;
	}

	interface Props {
		config: AlertConfigType;
		onsave?: (config: AlertConfigType) => void;
		ondelete?: (id: string) => void;
		availableScans?: ScanOption[];
		class?: string;
	}

	let {
		config = $bindable(),
		onsave,
		ondelete,
		availableScans = [
			{ id: 'macd-cross', label: 'MACD Crossover' },
			{ id: 'rsi-oversold', label: 'RSI Oversold' },
			{ id: 'rsi-overbought', label: 'RSI Overbought' },
			{ id: 'vol-spike', label: 'Volume Spike' },
			{ id: 'bb-squeeze', label: 'Bollinger Squeeze' },
			{ id: 'golden-cross', label: 'Golden Cross' },
			{ id: 'death-cross', label: 'Death Cross' },
			{ id: 'gap-up', label: 'Gap Up' },
			{ id: 'gap-down', label: 'Gap Down' },
			{ id: 'breakout', label: 'Breakout' }
		],
		class: className = ''
	}: Props = $props();

	let showDeleteConfirm = $state(false);

	const soundTypes = [
		{ value: 'chime', label: 'Chime' },
		{ value: 'bell', label: 'Bell' },
		{ value: 'alert', label: 'Alert Tone' },
		{ value: 'ping', label: 'Ping' },
		{ value: 'none', label: 'Silent' }
	];

	let selectedSoundType = $state('chime');

	const directionOptions: { key: string; label: string }[] = [
		{ key: 'bullish', label: 'Bullish' },
		{ key: 'bearish', label: 'Bearish' }
	];

	let isBothDirections = $derived(
		config.directions.includes('bullish') && config.directions.includes('bearish')
	);

	function toggleScanId(scanId: string) {
		if (config.scanIds.includes(scanId)) {
			config.scanIds = config.scanIds.filter((id) => id !== scanId);
		} else {
			config.scanIds = [...config.scanIds, scanId];
		}
	}

	function setDirection(mode: 'bullish' | 'bearish' | 'both') {
		if (mode === 'both') {
			config.directions = ['bullish', 'bearish'];
		} else {
			config.directions = [mode];
		}
	}

	function handleSave() {
		onsave?.(config);
	}

	function handleDelete() {
		if (showDeleteConfirm) {
			ondelete?.(config.id);
			showDeleteConfirm = false;
		} else {
			showDeleteConfirm = true;
		}
	}

	function cancelDelete() {
		showDeleteConfirm = false;
	}

	let strengthLabels: Record<number, string> = {
		1: 'Very Weak',
		2: 'Weak',
		3: 'Moderate',
		4: 'Strong',
		5: 'Very Strong'
	};
</script>

<div class="flex flex-col gap-6 rounded-xl border border-[oklch(0.20_0_0)] bg-[oklch(0.14_0_0)] p-5 {className}">
	<!-- Header with enable toggle -->
	<div class="flex items-center justify-between">
		<h3 class="text-sm font-semibold text-[oklch(0.88_0_0)]">Alert Configuration</h3>
		<div class="flex items-center gap-2.5">
			<span class="text-xs text-[oklch(0.55_0_0)]">
				{config.isActive ? 'Active' : 'Inactive'}
			</span>
			<button
				type="button"
				role="switch"
				aria-checked={config.isActive}
				class="relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-200
					{config.isActive ? 'bg-[oklch(0.55_0.15_145)]' : 'bg-[oklch(0.24_0_0)]'}"
				onclick={() => (config.isActive = !config.isActive)}
			>
				<span
					class="inline-block h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200
						{config.isActive ? 'translate-x-5' : 'translate-x-0.5'}"
				></span>
			</button>
		</div>
	</div>

	<!-- Name input -->
	<div class="flex flex-col gap-1.5">
		<label for="alert-name" class="text-xs font-medium text-[oklch(0.65_0_0)]">Alert Name</label>
		<input
			id="alert-name"
			type="text"
			bind:value={config.name}
			placeholder="e.g., Bullish Momentum Scanner"
			class="w-full rounded-lg border border-[oklch(0.24_0_0)] bg-[oklch(0.13_0_0)] px-3 py-2 text-sm text-[oklch(0.88_0_0)] placeholder-[oklch(0.40_0_0)] outline-none transition-all duration-150 focus:border-[oklch(0.45_0.12_250)] focus:ring-2 focus:ring-[oklch(0.45_0.12_250/0.3)]"
		/>
	</div>

	<!-- Scan Selection -->
	<div class="flex flex-col gap-2">
		<label class="text-xs font-medium text-[oklch(0.65_0_0)]">Scans to Monitor</label>
		<div class="grid grid-cols-2 gap-1.5">
			{#each availableScans as scan (scan.id)}
				<label
					class="flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 transition-all duration-150
						{config.scanIds.includes(scan.id)
						? 'border-[oklch(0.40_0.10_250)] bg-[oklch(0.17_0.02_250)]'
						: 'border-[oklch(0.20_0_0)] bg-[oklch(0.11_0_0)] hover:border-[oklch(0.28_0_0)]'}"
				>
					<input
						type="checkbox"
						checked={config.scanIds.includes(scan.id)}
						onchange={() => toggleScanId(scan.id)}
						class="sr-only"
					/>
					<span
						class="flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-all duration-150
							{config.scanIds.includes(scan.id)
							? 'border-[oklch(0.50_0.12_250)] bg-[oklch(0.45_0.12_250)]'
							: 'border-[oklch(0.30_0_0)] bg-[oklch(0.13_0_0)]'}"
					>
						{#if config.scanIds.includes(scan.id)}
							<svg
								xmlns="http://www.w3.org/2000/svg"
								class="h-3 w-3 text-white"
								viewBox="0 0 20 20"
								fill="currentColor"
							>
								<path
									fill-rule="evenodd"
									d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
									clip-rule="evenodd"
								/>
							</svg>
						{/if}
					</span>
					<span class="text-xs text-[oklch(0.75_0_0)]">{scan.label}</span>
				</label>
			{/each}
		</div>
		{#if config.scanIds.length > 0}
			<p class="text-[11px] text-[oklch(0.50_0_0)]">
				{config.scanIds.length} scan{config.scanIds.length !== 1 ? 's' : ''} selected
			</p>
		{/if}
	</div>

	<!-- Minimum Strength -->
	<div class="flex flex-col gap-2">
		<div class="flex items-center justify-between">
			<label class="text-xs font-medium text-[oklch(0.65_0_0)]">Minimum Signal Strength</label>
			<span class="text-xs font-medium text-[oklch(0.75_0.10_250)]">
				{config.minStrength} - {strengthLabels[config.minStrength] ?? ''}
			</span>
		</div>
		<input
			type="range"
			bind:value={config.minStrength}
			min="1"
			max="5"
			step="1"
			class="slider-track h-1.5 w-full cursor-pointer appearance-none rounded-full bg-[oklch(0.20_0_0)] outline-none
				[&::-webkit-slider-thumb]:h-4
				[&::-webkit-slider-thumb]:w-4
				[&::-webkit-slider-thumb]:appearance-none
				[&::-webkit-slider-thumb]:rounded-full
				[&::-webkit-slider-thumb]:bg-[oklch(0.55_0.15_145)]
				[&::-webkit-slider-thumb]:shadow-[0_0_0_3px_oklch(0.14_0_0)]
				[&::-webkit-slider-thumb]:transition-all
				[&::-webkit-slider-thumb]:duration-150
				[&::-webkit-slider-thumb]:hover:bg-[oklch(0.60_0.16_145)]
				[&::-webkit-slider-thumb]:hover:scale-110
				[&::-moz-range-thumb]:h-4
				[&::-moz-range-thumb]:w-4
				[&::-moz-range-thumb]:rounded-full
				[&::-moz-range-thumb]:border-0
				[&::-moz-range-thumb]:bg-[oklch(0.55_0.15_145)]
				[&::-moz-range-thumb]:shadow-[0_0_0_3px_oklch(0.14_0_0)]"
			style="background: linear-gradient(to right, oklch(0.45 0.12 145) 0%, oklch(0.45 0.12 145) {((config.minStrength - 1) / 4) * 100}%, oklch(0.20 0 0) {((config.minStrength - 1) / 4) * 100}%, oklch(0.20 0 0) 100%);"
		/>
		<div class="flex justify-between px-0.5">
			{#each [1, 2, 3, 4, 5] as n}
				<span
					class="text-[10px] {config.minStrength >= n
						? 'text-[oklch(0.60_0.10_145)]'
						: 'text-[oklch(0.35_0_0)]'}"
				>
					{n}
				</span>
			{/each}
		</div>
	</div>

	<!-- Direction Toggles -->
	<div class="flex flex-col gap-2">
		<label class="text-xs font-medium text-[oklch(0.65_0_0)]">Signal Direction</label>
		<div class="flex gap-1.5">
			<button
				type="button"
				class="flex-1 rounded-lg border px-3 py-2 text-xs font-medium transition-all duration-150
					{config.directions.includes('bullish') && !isBothDirections
					? 'border-[oklch(0.40_0.10_145)] bg-[oklch(0.18_0.04_145)] text-[oklch(0.75_0.15_145)]'
					: 'border-[oklch(0.20_0_0)] bg-[oklch(0.11_0_0)] text-[oklch(0.55_0_0)] hover:border-[oklch(0.28_0_0)]'}"
				onclick={() => setDirection('bullish')}
			>
				Bullish Only
			</button>
			<button
				type="button"
				class="flex-1 rounded-lg border px-3 py-2 text-xs font-medium transition-all duration-150
					{isBothDirections
					? 'border-[oklch(0.40_0.10_250)] bg-[oklch(0.17_0.02_250)] text-[oklch(0.72_0.12_250)]'
					: 'border-[oklch(0.20_0_0)] bg-[oklch(0.11_0_0)] text-[oklch(0.55_0_0)] hover:border-[oklch(0.28_0_0)]'}"
				onclick={() => setDirection('both')}
			>
				Both
			</button>
			<button
				type="button"
				class="flex-1 rounded-lg border px-3 py-2 text-xs font-medium transition-all duration-150
					{config.directions.includes('bearish') && !isBothDirections
					? 'border-[oklch(0.40_0.10_25)] bg-[oklch(0.18_0.04_25)] text-[oklch(0.70_0.16_25)]'
					: 'border-[oklch(0.20_0_0)] bg-[oklch(0.11_0_0)] text-[oklch(0.55_0_0)] hover:border-[oklch(0.28_0_0)]'}"
				onclick={() => setDirection('bearish')}
			>
				Bearish Only
			</button>
		</div>
	</div>

	<!-- Notification Settings -->
	<div class="flex flex-col gap-3">
		<label class="text-xs font-medium text-[oklch(0.65_0_0)]">Notifications</label>

		<!-- Sound Toggle -->
		<div class="flex items-center justify-between rounded-lg border border-[oklch(0.20_0_0)] bg-[oklch(0.11_0_0)] px-4 py-3">
			<div class="flex items-center gap-3">
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-4 w-4 text-[oklch(0.55_0_0)]"
					fill="none"
					viewBox="0 0 24 24"
					stroke="currentColor"
					stroke-width="1.5"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z"
					/>
				</svg>
				<div class="flex flex-col">
					<span class="text-xs font-medium text-[oklch(0.80_0_0)]">Sound Alert</span>
					<span class="text-[11px] text-[oklch(0.50_0_0)]">Play a sound when triggered</span>
				</div>
			</div>
			<div class="flex items-center gap-3">
				{#if config.soundEnabled}
					<select
						bind:value={selectedSoundType}
						class="rounded-md border border-[oklch(0.24_0_0)] bg-[oklch(0.13_0_0)] px-2 py-1 text-[11px] text-[oklch(0.75_0_0)] outline-none focus:border-[oklch(0.45_0.12_250)]"
					>
						{#each soundTypes as st (st.value)}
							<option value={st.value}>{st.label}</option>
						{/each}
					</select>
				{/if}
				<button
					type="button"
					role="switch"
					aria-checked={config.soundEnabled}
					class="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-200
						{config.soundEnabled ? 'bg-[oklch(0.55_0.15_145)]' : 'bg-[oklch(0.24_0_0)]'}"
					onclick={() => (config.soundEnabled = !config.soundEnabled)}
				>
					<span
						class="inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-200
							{config.soundEnabled ? 'translate-x-[18px]' : 'translate-x-0.5'}"
					></span>
				</button>
			</div>
		</div>

		<!-- Push Toggle -->
		<div class="flex items-center justify-between rounded-lg border border-[oklch(0.20_0_0)] bg-[oklch(0.11_0_0)] px-4 py-3">
			<div class="flex items-center gap-3">
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-4 w-4 text-[oklch(0.55_0_0)]"
					fill="none"
					viewBox="0 0 24 24"
					stroke="currentColor"
					stroke-width="1.5"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
					/>
				</svg>
				<div class="flex flex-col">
					<span class="text-xs font-medium text-[oklch(0.80_0_0)]">Push Notifications</span>
					<span class="text-[11px] text-[oklch(0.50_0_0)]">Receive browser push alerts</span>
				</div>
			</div>
			<button
				type="button"
				role="switch"
				aria-checked={config.pushEnabled}
				class="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-200
					{config.pushEnabled ? 'bg-[oklch(0.55_0.15_145)]' : 'bg-[oklch(0.24_0_0)]'}"
				onclick={() => (config.pushEnabled = !config.pushEnabled)}
			>
				<span
					class="inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-200
						{config.pushEnabled ? 'translate-x-[18px]' : 'translate-x-0.5'}"
				></span>
			</button>
		</div>
	</div>

	<!-- Action Buttons -->
	<div class="flex items-center justify-between border-t border-[oklch(0.20_0_0)] pt-4">
		<div>
			{#if showDeleteConfirm}
				<div class="flex items-center gap-2">
					<span class="text-xs text-[oklch(0.65_0.16_25)]">Confirm delete?</span>
					<button
						type="button"
						class="rounded-md bg-[oklch(0.50_0.18_25)] px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-[oklch(0.55_0.19_25)]"
						onclick={handleDelete}
					>
						Delete
					</button>
					<button
						type="button"
						class="rounded-md px-3 py-1.5 text-xs font-medium text-[oklch(0.65_0_0)] transition-colors hover:text-[oklch(0.80_0_0)]"
						onclick={cancelDelete}
					>
						Cancel
					</button>
				</div>
			{:else}
				<button
					type="button"
					class="rounded-md px-3 py-1.5 text-xs font-medium text-[oklch(0.55_0.10_25)] transition-colors hover:bg-[oklch(0.18_0.02_25)] hover:text-[oklch(0.65_0.14_25)]"
					onclick={handleDelete}
				>
					Delete Alert
				</button>
			{/if}
		</div>

		<button
			type="button"
			class="rounded-lg bg-[oklch(0.55_0.15_145)] px-5 py-2 text-sm font-medium text-white shadow-sm shadow-[oklch(0.55_0.15_145/0.25)] transition-all duration-150 hover:bg-[oklch(0.60_0.16_145)] active:bg-[oklch(0.50_0.14_145)]"
			onclick={handleSave}
		>
			Save Configuration
		</button>
	</div>
</div>
