<script lang="ts">
	import type { ScanCategory } from '$lib/types/scan';

	interface Condition {
		id: string;
		field: string;
		operator: string;
		value: string;
	}

	interface ScanBuilderConfig {
		name: string;
		category: ScanCategory | '';
		conditions: Condition[];
	}

	interface Props {
		config: ScanBuilderConfig;
		onsave?: (config: ScanBuilderConfig) => void;
		class?: string;
	}

	let { config = $bindable(), onsave, class: className = '' }: Props = $props();

	const categoryOptions: { value: ScanCategory | ''; label: string }[] = [
		{ value: '', label: 'Select category...' },
		{ value: 'momentum', label: 'Momentum' },
		{ value: 'volatility', label: 'Volatility' },
		{ value: 'flow', label: 'Flow' },
		{ value: 'technical', label: 'Technical' },
		{ value: 'institutional', label: 'Institutional' },
		{ value: 'options', label: 'Options' },
		{ value: 'breadth', label: 'Breadth' },
		{ value: 'custom', label: 'Custom' },
	];

	const fieldOptions = [
		{ value: 'price', label: 'Price' },
		{ value: 'changePercent', label: 'Change %' },
		{ value: 'volume', label: 'Volume' },
		{ value: 'relativeVolume', label: 'Relative Volume' },
		{ value: 'marketCap', label: 'Market Cap' },
		{ value: 'strength', label: 'Signal Strength' },
		{ value: 'sector', label: 'Sector' },
		{ value: 'rsi', label: 'RSI' },
		{ value: 'atr', label: 'ATR' },
		{ value: 'vwap', label: 'VWAP Deviation' },
	];

	const operatorOptions = [
		{ value: 'gt', label: '>' },
		{ value: 'gte', label: '>=' },
		{ value: 'lt', label: '<' },
		{ value: 'lte', label: '<=' },
		{ value: 'eq', label: '=' },
		{ value: 'between', label: 'between' },
		{ value: 'contains', label: 'contains' },
	];

	let nextId = $state(1);

	function addCondition() {
		const newCondition: Condition = {
			id: 'cond-' + nextId++,
			field: 'price',
			operator: 'gt',
			value: '',
		};
		config.conditions = [...config.conditions, newCondition];
	}

	function removeCondition(id: string) {
		config.conditions = config.conditions.filter((c) => c.id !== id);
	}

	function handleSave() {
		onsave?.(config);
	}

	let isValid = $derived(() => {
		return (
			config.name.trim().length > 0 &&
			config.category !== '' &&
			config.conditions.length > 0 &&
			config.conditions.every((c) => c.value.trim().length > 0)
		);
	});

	let conditionCount = $derived(config.conditions.length);

	const selectClasses =
		'appearance-none rounded-md border border-[var(--border-subtle)] bg-[var(--bg-base)] px-2.5 py-1.5 text-sm text-[var(--text-primary)] outline-none transition-all duration-150 focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-bg)] cursor-pointer';

	const inputClasses =
		'rounded-md border border-[var(--border-subtle)] bg-[var(--bg-base)] px-2.5 py-1.5 text-sm text-[var(--text-primary)] placeholder-[var(--text-disabled)] outline-none transition-all duration-150 focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-bg)]';
</script>

<div class="rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] {className}">
	<!-- Header -->
	<div class="flex items-center justify-between border-b border-[var(--border-subtle)] px-5 py-3">
		<div class="flex items-center gap-2">
			<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-[var(--accent)]">
				<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
			</svg>
			<h3 class="text-sm font-semibold text-[var(--text-primary)]">Custom Scan Builder</h3>
		</div>
		{#if conditionCount > 0}
			<span class="text-2xs text-[var(--text-tertiary)]">
				{conditionCount} condition{conditionCount !== 1 ? 's' : ''}
			</span>
		{/if}
	</div>

	<div class="space-y-4 p-5">
		<!-- Name + Category row -->
		<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
			<!-- Scan name -->
			<div class="flex flex-col gap-1.5">
				<label for="scan-name" class="text-xs font-medium text-[var(--text-tertiary)] select-none">Scan Name</label>
				<input
					id="scan-name"
					type="text"
					placeholder="e.g. High Volume Breakouts"
					bind:value={config.name}
					class="{inputClasses} w-full"
				/>
			</div>

			<!-- Category select -->
			<div class="flex flex-col gap-1.5">
				<label for="scan-category" class="text-xs font-medium text-[var(--text-tertiary)] select-none">Category</label>
				<div class="relative">
					<select
						id="scan-category"
						bind:value={config.category}
						class="{selectClasses} w-full pr-8"
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
			</div>
		</div>

		<!-- Conditions section -->
		<div>
			<div class="mb-2 flex items-center justify-between">
				<label class="text-xs font-medium text-[var(--text-tertiary)] select-none">Conditions</label>
				<button
					type="button"
					class="flex items-center gap-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-base)] px-2 py-1 text-xs font-medium text-[var(--accent)] transition-all duration-150 hover:border-[var(--accent-dim)] hover:bg-[var(--accent-bg)]"
					onclick={addCondition}
				>
					<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<path d="M12 5v14" />
						<path d="M5 12h14" />
					</svg>
					Add condition
				</button>
			</div>

			{#if config.conditions.length === 0}
				<div class="rounded-md border border-dashed border-[var(--border-subtle)] bg-[var(--bg-base)] px-4 py-6 text-center">
					<p class="text-sm text-[var(--text-disabled)]">No conditions yet. Click "Add condition" to start building your scan.</p>
				</div>
			{:else}
				<div class="space-y-2">
					{#each config.conditions as condition, i (condition.id)}
						<div class="flex items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-base)] p-2.5">
							<!-- Condition number -->
							<span class="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-[var(--bg-overlay)] text-[10px] font-semibold text-[var(--text-tertiary)]">
								{i + 1}
							</span>

							<!-- Field select -->
							<div class="relative flex-shrink-0">
								<select
									bind:value={condition.field}
									class="{selectClasses} min-w-[130px] pr-7"
								>
									{#each fieldOptions as opt (opt.value)}
										<option value={opt.value}>{opt.label}</option>
									{/each}
								</select>
								<div class="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-disabled)]">
									<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
										<path d="m6 9 6 6 6-6" />
									</svg>
								</div>
							</div>

							<!-- Operator select -->
							<div class="relative flex-shrink-0">
								<select
									bind:value={condition.operator}
									class="{selectClasses} min-w-[80px] pr-7 font-mono"
								>
									{#each operatorOptions as opt (opt.value)}
										<option value={opt.value}>{opt.label}</option>
									{/each}
								</select>
								<div class="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-disabled)]">
									<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
										<path d="m6 9 6 6 6-6" />
									</svg>
								</div>
							</div>

							<!-- Value input -->
							<input
								type="text"
								placeholder="Value..."
								bind:value={condition.value}
								class="{inputClasses} min-w-0 flex-1 font-mono"
							/>

							<!-- Remove button -->
							<button
								type="button"
								class="flex-shrink-0 rounded-md p-1.5 text-[var(--text-disabled)] transition-colors hover:bg-[var(--bearish-bg)] hover:text-[var(--bearish)]"
								onclick={() => removeCondition(condition.id)}
								title="Remove condition"
							>
								<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
									<path d="M18 6 6 18" />
									<path d="m6 6 12 12" />
								</svg>
							</button>
						</div>

						<!-- AND connector between conditions -->
						{#if i < config.conditions.length - 1}
							<div class="flex items-center justify-center">
								<span class="rounded-full bg-[var(--bg-overlay)] px-3 py-0.5 text-[10px] font-semibold uppercase tracking-widest text-[var(--text-disabled)]">
									AND
								</span>
							</div>
						{/if}
					{/each}
				</div>
			{/if}
		</div>
	</div>

	<!-- Footer with save -->
	<div class="flex items-center justify-end gap-3 border-t border-[var(--border-subtle)] px-5 py-3">
		<button
			type="button"
			class="rounded-lg bg-transparent px-4 py-2 text-sm font-medium text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-primary)]"
			onclick={() => {
				config = { name: '', category: '', conditions: [] };
			}}
		>
			Reset
		</button>
		<button
			type="button"
			class="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all duration-150
				{isValid()
					? 'bg-[var(--accent)] text-white hover:bg-[var(--accent-bright)] shadow-sm cursor-pointer'
					: 'bg-[var(--bg-overlay)] text-[var(--text-disabled)] cursor-not-allowed'}"
			disabled={!isValid()}
			onclick={handleSave}
		>
			<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
				<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
				<polyline points="17 21 17 13 7 13 7 21" />
				<polyline points="7 3 7 8 15 8" />
			</svg>
			Save Scan
		</button>
	</div>
</div>
