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

	let isValid = $derived.by(() => {
		return (
			config.name.trim().length > 0 &&
			config.category !== '' &&
			config.conditions.length > 0 &&
			config.conditions.every((c) => c.value.trim().length > 0)
		);
	});

	let conditionCount = $derived(config.conditions.length);
</script>

<div class="scan-builder {className}">
	<!-- Header -->
	<div class="header">
		<div class="header-left">
			<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="header-icon">
				<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
			</svg>
			<h3 class="header-title">Custom Scan Builder</h3>
		</div>
		{#if conditionCount > 0}
			<span class="condition-count">
				{conditionCount} condition{conditionCount !== 1 ? 's' : ''}
			</span>
		{/if}
	</div>

	<div class="body">
		<!-- Name + Category row -->
		<div class="form-row">
			<!-- Scan name -->
			<div class="form-group">
				<label for="scan-name" class="form-label">Scan Name</label>
				<input
					id="scan-name"
					type="text"
					placeholder="e.g. High Volume Breakouts"
					bind:value={config.name}
					class="form-input"
				/>
			</div>

			<!-- Category select -->
			<div class="form-group">
				<label for="scan-category" class="form-label">Category</label>
				<div class="select-wrapper">
					<select
						id="scan-category"
						bind:value={config.category}
						class="form-select category-select"
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
			</div>
		</div>

		<!-- Conditions section -->
		<div>
			<div class="conditions-header">
				<label class="form-label">Conditions</label>
				<button
					type="button"
					class="add-condition-btn"
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
				<div class="empty-state">
					<p class="empty-state-text">No conditions yet. Click "Add condition" to start building your scan.</p>
				</div>
			{:else}
				<div class="conditions-list">
					{#each config.conditions as condition, i (condition.id)}
						<div class="condition-row">
							<!-- Condition number -->
							<span class="condition-number">
								{i + 1}
							</span>

							<!-- Field select -->
							<div class="select-wrapper condition-field-wrapper">
								<select
									bind:value={condition.field}
									class="form-select condition-field-select"
								>
									{#each fieldOptions as opt (opt.value)}
										<option value={opt.value}>{opt.label}</option>
									{/each}
								</select>
								<div class="select-chevron select-chevron-sm">
									<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
										<path d="m6 9 6 6 6-6" />
									</svg>
								</div>
							</div>

							<!-- Operator select -->
							<div class="select-wrapper condition-operator-wrapper">
								<select
									bind:value={condition.operator}
									class="form-select condition-operator-select"
								>
									{#each operatorOptions as opt (opt.value)}
										<option value={opt.value}>{opt.label}</option>
									{/each}
								</select>
								<div class="select-chevron select-chevron-sm">
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
								class="form-input condition-value-input"
							/>

							<!-- Remove button -->
							<button
								type="button"
								class="remove-condition-btn"
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
							<div class="and-connector">
								<span class="and-badge">
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
	<div class="footer">
		<button
			type="button"
			class="reset-btn"
			onclick={() => {
				config = { name: '', category: '', conditions: [] };
			}}
		>
			Reset
		</button>
		<button
			type="button"
			class="save-btn {isValid ? 'save-btn--active' : 'save-btn--disabled'}"
			disabled={!isValid}
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

<style>
	/* Container */
	.scan-builder {
		border-radius: var(--radius-lg);
		border: 1px solid var(--border-default);
		background-color: var(--bg-surface);
	}

	/* Header */
	.header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		border-bottom: 1px solid var(--border-subtle);
		padding: 12px 20px;
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.header-icon {
		color: var(--accent);
	}

	.header-title {
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--text-primary);
	}

	.condition-count {
		font-size: var(--text-2xs);
		color: var(--text-tertiary);
	}

	/* Body */
	.body {
		padding: 20px;
	}

	.body > * + * {
		margin-top: 16px;
	}

	/* Form row (grid) */
	.form-row {
		display: grid;
		grid-template-columns: 1fr;
		gap: 16px;
	}

	@media (min-width: 640px) {
		.form-row {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	/* Form group */
	.form-group {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	/* Form label */
	.form-label {
		font-size: var(--text-xs);
		font-weight: 500;
		color: var(--text-tertiary);
		user-select: none;
	}

	/* Shared form-input */
	.form-input {
		border-radius: var(--radius-md);
		border: 1px solid var(--border-subtle);
		background-color: var(--bg-base);
		padding: 6px 10px;
		font-size: var(--text-sm);
		color: var(--text-primary);
		outline: none;
		transition: all 150ms;
		width: 100%;
	}

	.form-input::placeholder {
		color: var(--text-disabled);
	}

	.form-input:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-bg);
	}

	/* Shared form-select */
	.form-select {
		appearance: none;
		border-radius: var(--radius-md);
		border: 1px solid var(--border-subtle);
		background-color: var(--bg-base);
		padding: 6px 10px;
		font-size: var(--text-sm);
		color: var(--text-primary);
		outline: none;
		transition: all 150ms;
		cursor: pointer;
		width: 100%;
	}

	.form-select:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-bg);
	}

	/* Category select specific */
	.category-select {
		padding-right: 32px;
	}

	/* Select wrapper (relative positioning for chevron) */
	.select-wrapper {
		position: relative;
	}

	/* Select chevron icon */
	.select-chevron {
		pointer-events: none;
		position: absolute;
		right: 10px;
		top: 50%;
		transform: translateY(-50%);
		color: var(--text-disabled);
	}

	.select-chevron-sm {
		right: 8px;
	}

	/* Conditions header */
	.conditions-header {
		margin-bottom: 8px;
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	/* Add condition button */
	.add-condition-btn {
		display: flex;
		align-items: center;
		gap: 4px;
		border-radius: var(--radius-md);
		border: 1px solid var(--border-subtle);
		background-color: var(--bg-base);
		padding: 4px 8px;
		font-size: var(--text-xs);
		font-weight: 500;
		color: var(--accent);
		transition: all 150ms;
	}

	.add-condition-btn:hover {
		border-color: var(--accent-dim);
		background-color: var(--accent-bg);
	}

	/* Empty state */
	.empty-state {
		border-radius: var(--radius-md);
		border: 1px dashed var(--border-subtle);
		background-color: var(--bg-base);
		padding: 24px 16px;
		text-align: center;
	}

	.empty-state-text {
		font-size: var(--text-sm);
		color: var(--text-disabled);
	}

	/* Conditions list */
	.conditions-list > * + * {
		margin-top: 8px;
	}

	/* Condition row */
	.condition-row {
		display: flex;
		align-items: center;
		gap: 8px;
		border-radius: var(--radius-md);
		border: 1px solid var(--border-subtle);
		background-color: var(--bg-base);
		padding: 10px;
	}

	/* Condition number badge */
	.condition-number {
		display: flex;
		height: 20px;
		width: 20px;
		flex-shrink: 0;
		align-items: center;
		justify-content: center;
		border-radius: var(--radius-full);
		background-color: var(--bg-overlay);
		font-size: 10px;
		font-weight: 600;
		color: var(--text-tertiary);
	}

	/* Condition field select wrapper */
	.condition-field-wrapper {
		flex-shrink: 0;
	}

	.condition-field-select {
		min-width: 130px;
		padding-right: 28px;
	}

	/* Condition operator select wrapper */
	.condition-operator-wrapper {
		flex-shrink: 0;
	}

	.condition-operator-select {
		min-width: 80px;
		padding-right: 28px;
		font-family: var(--font-mono);
	}

	/* Condition value input */
	.condition-value-input {
		min-width: 0;
		flex: 1;
		font-family: var(--font-mono);
	}

	/* Remove condition button */
	.remove-condition-btn {
		flex-shrink: 0;
		border-radius: var(--radius-md);
		padding: 6px;
		color: var(--text-disabled);
		transition: color 150ms, background-color 150ms, border-color 150ms;
	}

	.remove-condition-btn:hover {
		background-color: var(--bearish-bg);
		color: var(--bearish);
	}

	/* AND connector */
	.and-connector {
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.and-badge {
		border-radius: var(--radius-full);
		background-color: var(--bg-overlay);
		padding: 2px 12px;
		font-size: 10px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--text-disabled);
	}

	/* Footer */
	.footer {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 12px;
		border-top: 1px solid var(--border-subtle);
		padding: 12px 20px;
	}

	/* Reset button */
	.reset-btn {
		border-radius: var(--radius-lg);
		background-color: transparent;
		padding: 8px 16px;
		font-size: var(--text-sm);
		font-weight: 500;
		color: var(--text-tertiary);
		transition: color 150ms, background-color 150ms, border-color 150ms;
	}

	.reset-btn:hover {
		color: var(--text-primary);
	}

	/* Save button */
	.save-btn {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		border-radius: var(--radius-lg);
		padding: 8px 16px;
		font-size: var(--text-sm);
		font-weight: 500;
		transition: all 150ms;
	}

	.save-btn--active {
		background-color: var(--accent);
		color: white;
		box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
		cursor: pointer;
	}

	.save-btn--active:hover {
		background-color: var(--accent-bright);
	}

	.save-btn--disabled {
		background-color: var(--bg-overlay);
		color: var(--text-disabled);
		cursor: not-allowed;
	}
</style>
