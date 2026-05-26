<script lang="ts">
	import type { ScanCategory, SignalDirection, SignalStrength } from '$lib/types/scan';

	interface FilterState {
		category: ScanCategory | '';
		direction: SignalDirection | 'all';
		minStrength: SignalStrength;
		searchQuery: string;
	}

	interface Props {
		filters: FilterState;
		class?: string;
	}

	let { filters = $bindable(), class: className = '' }: Props = $props();

	const categoryOptions: { value: ScanCategory | ''; label: string }[] = [
		{ value: '', label: 'All Categories' },
		{ value: 'momentum', label: 'Momentum' },
		{ value: 'volatility', label: 'Volatility' },
		{ value: 'flow', label: 'Flow' },
		{ value: 'technical', label: 'Technical' },
		{ value: 'institutional', label: 'Institutional' },
		{ value: 'options', label: 'Options' },
		{ value: 'breadth', label: 'Breadth' },
		{ value: 'custom', label: 'Custom' },
	];

	const directionOptions: { value: SignalDirection | 'all'; label: string }[] = [
		{ value: 'all', label: 'All' },
		{ value: 'bullish', label: 'Bullish' },
		{ value: 'bearish', label: 'Bearish' },
	];

	let activeFilterCount = $derived.by(() => {
		let count = 0;
		if (filters.category !== '') count++;
		if (filters.direction !== 'all') count++;
		if (filters.minStrength > 1) count++;
		if (filters.searchQuery.trim() !== '') count++;
		return count;
	});

	function clearAll() {
		filters = {
			category: '',
			direction: 'all',
			minStrength: 1 as SignalStrength,
			searchQuery: '',
		};
	}

	function dirButtonClass(opt: SignalDirection | 'all'): string {
		const isActive = filters.direction === opt;
		const base = 'px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-150 select-none';

		if (!isActive) {
			return base + ' bg-transparent text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-overlay)]';
		}

		if (opt === 'bullish') {
			return base + ' badge-bullish';
		}
		if (opt === 'bearish') {
			return base + ' badge-bearish';
		}
		return base + ' bg-[var(--bg-overlay)] text-[var(--text-primary)] border border-[var(--border-strong)]';
	}

	function strengthLabel(val: number): string {
		return val + '+ / 5';
	}
</script>

<div class="flex flex-wrap items-center gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-2.5 {className}">
	<!-- Search input -->
	<div class="relative min-w-[180px] flex-shrink-0">
		<svg
			class="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-disabled)]"
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
			<circle cx="11" cy="11" r="8" />
			<path d="m21 21-4.3-4.3" />
		</svg>
		<input
			type="text"
			placeholder="Search symbols..."
			bind:value={filters.searchQuery}
			class="w-full rounded-md border border-[var(--border-subtle)] bg-[var(--bg-base)] py-1.5 pl-8 pr-3 text-sm text-[var(--text-primary)] placeholder-[var(--text-disabled)] outline-none transition-all duration-150 focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-bg)]"
		/>
	</div>

	<!-- Separator -->
	<div class="h-6 w-px bg-[var(--border-subtle)]"></div>

	<!-- Category dropdown -->
	<div class="relative flex-shrink-0">
		<select
			bind:value={filters.category}
			class="appearance-none rounded-md border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-1.5 pr-8 text-sm text-[var(--text-primary)] outline-none transition-all duration-150 focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-bg)] cursor-pointer"
		>
			{#each categoryOptions as opt (opt.value)}
				<option value={opt.value}>{opt.label}</option>
			{/each}
		</select>
		<div class="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[var(--text-disabled)]">
			<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
				<path d="m6 9 6 6 6-6" />
			</svg>
		</div>
	</div>

	<!-- Separator -->
	<div class="h-6 w-px bg-[var(--border-subtle)]"></div>

	<!-- Direction toggle buttons -->
	<div class="flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] p-0.5">
		{#each directionOptions as opt (opt.value)}
			<button
				type="button"
				class={dirButtonClass(opt.value)}
				onclick={() => { filters.direction = opt.value; }}
			>
				{opt.label}
			</button>
		{/each}
	</div>

	<!-- Separator -->
	<div class="h-6 w-px bg-[var(--border-subtle)]"></div>

	<!-- Strength slider -->
	<div class="flex items-center gap-2 flex-shrink-0">
		<span class="text-2xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">Min Str</span>
		<input
			type="range"
			min="1"
			max="5"
			step="1"
			bind:value={filters.minStrength}
			class="h-1 w-20 cursor-pointer appearance-none rounded-full bg-[var(--bg-overlay)] outline-none
				[&::-webkit-slider-thumb]:appearance-none
				[&::-webkit-slider-thumb]:h-3.5
				[&::-webkit-slider-thumb]:w-3.5
				[&::-webkit-slider-thumb]:rounded-full
				[&::-webkit-slider-thumb]:bg-[var(--accent)]
				[&::-webkit-slider-thumb]:shadow-[0_0_0_2px_var(--bg-surface)]
				[&::-moz-range-thumb]:border-0
				[&::-moz-range-thumb]:h-3.5
				[&::-moz-range-thumb]:w-3.5
				[&::-moz-range-thumb]:rounded-full
				[&::-moz-range-thumb]:bg-[var(--accent)]"
		/>
		<span class="mono-nums text-xs text-[var(--text-secondary)]">{strengthLabel(filters.minStrength)}</span>
	</div>

	<!-- Spacer -->
	<div class="flex-1"></div>

	<!-- Clear all -->
	{#if activeFilterCount > 0}
		<button
			type="button"
			class="flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-base)] px-2.5 py-1.5 text-xs font-medium text-[var(--text-secondary)] transition-all duration-150 hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
			onclick={clearAll}
		>
			<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
				<path d="M18 6 6 18" />
				<path d="m6 6 12 12" />
			</svg>
			Clear
			<span class="inline-flex h-4 w-4 items-center justify-center rounded-full bg-[var(--accent-bg)] text-[10px] font-semibold text-[var(--accent)]">
				{activeFilterCount}
			</span>
		</button>
	{/if}
</div>
