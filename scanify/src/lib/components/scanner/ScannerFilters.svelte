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

		if (!isActive) {
			return 'dir-btn dir-btn-inactive';
		}

		if (opt === 'bullish') {
			return 'dir-btn dir-btn-bullish badge-bullish';
		}
		if (opt === 'bearish') {
			return 'dir-btn dir-btn-bearish badge-bearish';
		}
		return 'dir-btn dir-btn-all-active';
	}

	function strengthLabel(val: number): string {
		return val + '+ / 5';
	}
</script>

<div class="filter-bar {className}">
	<!-- Search input -->
	<div class="search-wrapper">
		<svg
			class="search-icon"
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
			class="search-input"
		/>
	</div>

	<!-- Separator -->
	<div class="separator"></div>

	<!-- Category dropdown -->
	<div class="select-wrapper">
		<select
			bind:value={filters.category}
			class="category-select"
		>
			{#each categoryOptions as opt (opt.value)}
				<option value={opt.value}>{opt.label}</option>
			{/each}
		</select>
		<div class="select-chevron">
			<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
				<path d="m6 9 6 6 6-6" />
			</svg>
		</div>
	</div>

	<!-- Separator -->
	<div class="separator"></div>

	<!-- Direction toggle buttons -->
	<div class="direction-group">
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
	<div class="separator"></div>

	<!-- Strength slider -->
	<div class="strength-group">
		<span class="strength-label">Min Str</span>
		<input
			type="range"
			min="1"
			max="5"
			step="1"
			bind:value={filters.minStrength}
			class="strength-slider"
		/>
		<span class="strength-value mono-nums">{strengthLabel(filters.minStrength)}</span>
	</div>

	<!-- Spacer -->
	<div class="spacer"></div>

	<!-- Clear all -->
	{#if activeFilterCount > 0}
		<button
			type="button"
			class="clear-btn"
			onclick={clearAll}
		>
			<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
				<path d="M18 6 6 18" />
				<path d="m6 6 12 12" />
			</svg>
			Clear
			<span class="clear-badge">
				{activeFilterCount}
			</span>
		</button>
	{/if}
</div>

<style>
	.filter-bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 12px;
		border-radius: var(--radius-lg);
		border: 1px solid var(--border-subtle);
		background-color: var(--bg-surface);
		padding: 10px 16px;
	}

	/* Search */
	.search-wrapper {
		position: relative;
		min-width: 180px;
		flex-shrink: 0;
	}

	.search-icon {
		pointer-events: none;
		position: absolute;
		left: 10px;
		top: 50%;
		transform: translateY(-50%);
		color: var(--text-disabled);
	}

	.search-input {
		width: 100%;
		border-radius: var(--radius-md);
		border: 1px solid var(--border-subtle);
		background-color: var(--bg-base);
		padding: 6px 12px 6px 32px;
		font-size: var(--text-sm);
		color: var(--text-primary);
		outline: none;
		transition: all 150ms;
	}

	.search-input::placeholder {
		color: var(--text-disabled);
	}

	.search-input:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-bg);
	}

	/* Separator */
	.separator {
		height: 24px;
		width: 1px;
		background-color: var(--border-subtle);
	}

	/* Category select */
	.select-wrapper {
		position: relative;
		flex-shrink: 0;
	}

	.category-select {
		appearance: none;
		border-radius: var(--radius-md);
		border: 1px solid var(--border-subtle);
		background-color: var(--bg-base);
		padding: 6px 32px 6px 12px;
		font-size: var(--text-sm);
		color: var(--text-primary);
		outline: none;
		transition: all 150ms;
		cursor: pointer;
	}

	.category-select:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-bg);
	}

	.select-chevron {
		pointer-events: none;
		position: absolute;
		right: 10px;
		top: 50%;
		transform: translateY(-50%);
		color: var(--text-disabled);
	}

	/* Direction toggle group */
	.direction-group {
		display: flex;
		align-items: center;
		gap: 4px;
		border-radius: var(--radius-lg);
		border: 1px solid var(--border-subtle);
		background-color: var(--bg-base);
		padding: 2px;
	}

	.dir-btn {
		padding: 6px 12px;
		font-size: var(--text-xs);
		font-weight: 500;
		border-radius: var(--radius-md);
		transition: all 150ms;
		user-select: none;
		border: none;
		cursor: pointer;
	}

	.dir-btn-inactive {
		background-color: transparent;
		color: var(--text-tertiary);
	}

	.dir-btn-inactive:hover {
		color: var(--text-secondary);
		background-color: var(--bg-overlay);
	}

	.dir-btn-all-active {
		background-color: var(--bg-overlay);
		color: var(--text-primary);
		border: 1px solid var(--border-strong);
	}

	/* Strength slider */
	.strength-group {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-shrink: 0;
	}

	.strength-label {
		font-size: var(--text-2xs);
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-tertiary);
	}

	.strength-slider {
		height: 4px;
		width: 80px;
		cursor: pointer;
		appearance: none;
		border-radius: var(--radius-full);
		background-color: var(--bg-overlay);
		outline: none;
	}

	.strength-slider::-webkit-slider-thumb {
		appearance: none;
		height: 14px;
		width: 14px;
		border-radius: var(--radius-full);
		background-color: var(--accent);
		box-shadow: 0 0 0 2px var(--bg-surface);
	}

	.strength-slider::-moz-range-thumb {
		border: 0;
		height: 14px;
		width: 14px;
		border-radius: var(--radius-full);
		background-color: var(--accent);
	}

	.strength-value {
		font-size: var(--text-xs);
		color: var(--text-secondary);
	}

	/* Spacer */
	.spacer {
		flex: 1;
	}

	/* Clear button */
	.clear-btn {
		display: flex;
		align-items: center;
		gap: 6px;
		border-radius: var(--radius-md);
		border: 1px solid var(--border-subtle);
		background-color: var(--bg-base);
		padding: 6px 10px;
		font-size: var(--text-xs);
		font-weight: 500;
		color: var(--text-secondary);
		transition: all 150ms;
		cursor: pointer;
	}

	.clear-btn:hover {
		border-color: var(--border-strong);
		color: var(--text-primary);
	}

	.clear-badge {
		display: inline-flex;
		height: 16px;
		width: 16px;
		align-items: center;
		justify-content: center;
		border-radius: var(--radius-full);
		background-color: var(--accent-bg);
		font-size: 10px;
		font-weight: 600;
		color: var(--accent);
	}
</style>
