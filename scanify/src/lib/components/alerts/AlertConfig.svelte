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

<div class="config-root {className}">
	<!-- Header with enable toggle -->
	<div class="header">
		<h3 class="header-title">Alert Configuration</h3>
		<div class="header-toggle-group">
			<span class="active-label">
				{config.isActive ? 'Active' : 'Inactive'}
			</span>
			<button
				type="button"
				role="switch"
				aria-checked={config.isActive}
				class="toggle-switch-lg"
				class:toggle-on={config.isActive}
				class:toggle-off={!config.isActive}
				onclick={() => (config.isActive = !config.isActive)}
			>
				<span
					class="toggle-thumb-lg"
					class:toggle-thumb-lg-on={config.isActive}
					class:toggle-thumb-lg-off={!config.isActive}
				></span>
			</button>
		</div>
	</div>

	<!-- Name input -->
	<div class="field-group">
		<label for="alert-name" class="field-label">Alert Name</label>
		<input
			id="alert-name"
			type="text"
			bind:value={config.name}
			placeholder="e.g., Bullish Momentum Scanner"
			class="text-input"
		/>
	</div>

	<!-- Scan Selection -->
	<div class="field-group-md">
		<label class="field-label">Scans to Monitor</label>
		<div class="scan-grid">
			{#each availableScans as scan (scan.id)}
				<label
					class="scan-option"
					class:scan-option-selected={config.scanIds.includes(scan.id)}
					class:scan-option-unselected={!config.scanIds.includes(scan.id)}
				>
					<input
						type="checkbox"
						checked={config.scanIds.includes(scan.id)}
						onchange={() => toggleScanId(scan.id)}
						class="sr-only"
					/>
					<span
						class="checkbox-indicator"
						class:checkbox-checked={config.scanIds.includes(scan.id)}
						class:checkbox-unchecked={!config.scanIds.includes(scan.id)}
					>
						{#if config.scanIds.includes(scan.id)}
							<svg
								xmlns="http://www.w3.org/2000/svg"
								class="check-icon"
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
					<span class="scan-label">{scan.label}</span>
				</label>
			{/each}
		</div>
		{#if config.scanIds.length > 0}
			<p class="scan-count">
				{config.scanIds.length} scan{config.scanIds.length !== 1 ? 's' : ''} selected
			</p>
		{/if}
	</div>

	<!-- Minimum Strength -->
	<div class="field-group-md">
		<div class="strength-header">
			<label class="field-label">Minimum Signal Strength</label>
			<span class="strength-value">
				{config.minStrength} - {strengthLabels[config.minStrength] ?? ''}
			</span>
		</div>
		<input
			type="range"
			bind:value={config.minStrength}
			min="1"
			max="5"
			step="1"
			class="slider-track"
			style="background: linear-gradient(to right, oklch(0.45 0.12 145) 0%, oklch(0.45 0.12 145) {((config.minStrength - 1) / 4) * 100}%, oklch(0.20 0 0) {((config.minStrength - 1) / 4) * 100}%, oklch(0.20 0 0) 100%);"
		/>
		<div class="strength-ticks">
			{#each [1, 2, 3, 4, 5] as n}
				<span
					class="tick-label"
					class:tick-active={config.minStrength >= n}
					class:tick-inactive={config.minStrength < n}
				>
					{n}
				</span>
			{/each}
		</div>
	</div>

	<!-- Direction Toggles -->
	<div class="field-group-md">
		<label class="field-label">Signal Direction</label>
		<div class="direction-group">
			<button
				type="button"
				class="direction-btn"
				class:direction-bullish-active={config.directions.includes('bullish') && !isBothDirections}
				class:direction-inactive={!(config.directions.includes('bullish') && !isBothDirections)}
				onclick={() => setDirection('bullish')}
			>
				Bullish Only
			</button>
			<button
				type="button"
				class="direction-btn"
				class:direction-both-active={isBothDirections}
				class:direction-inactive={!isBothDirections}
				onclick={() => setDirection('both')}
			>
				Both
			</button>
			<button
				type="button"
				class="direction-btn"
				class:direction-bearish-active={config.directions.includes('bearish') && !isBothDirections}
				class:direction-inactive={!(config.directions.includes('bearish') && !isBothDirections)}
				onclick={() => setDirection('bearish')}
			>
				Bearish Only
			</button>
		</div>
	</div>

	<!-- Notification Settings -->
	<div class="notifications-section">
		<label class="field-label">Notifications</label>

		<!-- Sound Toggle -->
		<div class="notification-row">
			<div class="notification-info">
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="notification-icon"
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
				<div class="notification-text">
					<span class="notification-title">Sound Alert</span>
					<span class="notification-desc">Play a sound when triggered</span>
				</div>
			</div>
			<div class="notification-controls">
				{#if config.soundEnabled}
					<select
						bind:value={selectedSoundType}
						class="sound-select"
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
					class="toggle-switch-sm"
					class:toggle-on={config.soundEnabled}
					class:toggle-off={!config.soundEnabled}
					onclick={() => (config.soundEnabled = !config.soundEnabled)}
				>
					<span
						class="toggle-thumb-sm"
						class:toggle-thumb-sm-on={config.soundEnabled}
						class:toggle-thumb-sm-off={!config.soundEnabled}
					></span>
				</button>
			</div>
		</div>

		<!-- Push Toggle -->
		<div class="notification-row">
			<div class="notification-info">
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="notification-icon"
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
				<div class="notification-text">
					<span class="notification-title">Push Notifications</span>
					<span class="notification-desc">Receive browser push alerts</span>
				</div>
			</div>
			<button
				type="button"
				role="switch"
				aria-checked={config.pushEnabled}
				class="toggle-switch-sm"
				class:toggle-on={config.pushEnabled}
				class:toggle-off={!config.pushEnabled}
				onclick={() => (config.pushEnabled = !config.pushEnabled)}
			>
				<span
					class="toggle-thumb-sm"
					class:toggle-thumb-sm-on={config.pushEnabled}
					class:toggle-thumb-sm-off={!config.pushEnabled}
				></span>
			</button>
		</div>
	</div>

	<!-- Action Buttons -->
	<div class="actions-bar">
		<div>
			{#if showDeleteConfirm}
				<div class="delete-confirm-group">
					<span class="delete-confirm-text">Confirm delete?</span>
					<button
						type="button"
						class="delete-confirm-btn"
						onclick={handleDelete}
					>
						Delete
					</button>
					<button
						type="button"
						class="delete-cancel-btn"
						onclick={cancelDelete}
					>
						Cancel
					</button>
				</div>
			{:else}
				<button
					type="button"
					class="delete-btn"
					onclick={handleDelete}
				>
					Delete Alert
				</button>
			{/if}
		</div>

		<button
			type="button"
			class="save-btn"
			onclick={handleSave}
		>
			Save Configuration
		</button>
	</div>
</div>

<style>
	/* ── Root container ── */
	.config-root {
		display: flex;
		flex-direction: column;
		gap: 24px;
		border-radius: var(--radius-xl, 12px);
		border: 1px solid oklch(0.20 0 0);
		background: oklch(0.14 0 0);
		padding: 20px;
	}

	/* ── Header ── */
	.header {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.header-title {
		font-size: 0.875rem;
		font-weight: 600;
		color: oklch(0.88 0 0);
	}

	.header-toggle-group {
		display: flex;
		align-items: center;
		gap: 10px;
	}

	.active-label {
		font-size: 0.75rem;
		color: oklch(0.55 0 0);
	}

	/* ── Toggle switch (large - header) ── */
	.toggle-switch-lg {
		position: relative;
		display: inline-flex;
		height: 24px;
		width: 44px;
		flex-shrink: 0;
		align-items: center;
		border-radius: 9999px;
		border: none;
		cursor: pointer;
		transition: background-color 200ms;
		padding: 0;
	}

	.toggle-thumb-lg {
		display: inline-block;
		height: 20px;
		width: 20px;
		border-radius: 9999px;
		background: white;
		box-shadow: 0 1px 2px 0 rgb(0 0 0 / 0.05);
		transition: transform 200ms;
	}

	.toggle-thumb-lg-on {
		transform: translateX(20px);
	}

	.toggle-thumb-lg-off {
		transform: translateX(2px);
	}

	/* ── Toggle switch (small - notifications) ── */
	.toggle-switch-sm {
		position: relative;
		display: inline-flex;
		height: 20px;
		width: 36px;
		flex-shrink: 0;
		align-items: center;
		border-radius: 9999px;
		border: none;
		cursor: pointer;
		transition: background-color 200ms;
		padding: 0;
	}

	.toggle-thumb-sm {
		display: inline-block;
		height: 14px;
		width: 14px;
		border-radius: 9999px;
		background: white;
		box-shadow: 0 1px 2px 0 rgb(0 0 0 / 0.05);
		transition: transform 200ms;
	}

	.toggle-thumb-sm-on {
		transform: translateX(18px);
	}

	.toggle-thumb-sm-off {
		transform: translateX(2px);
	}

	/* ── Toggle on/off shared colours ── */
	.toggle-on {
		background: oklch(0.55 0.15 145);
	}

	.toggle-off {
		background: oklch(0.24 0 0);
	}

	/* ── Field groups ── */
	.field-group {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.field-group-md {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.field-label {
		font-size: 0.75rem;
		font-weight: 500;
		color: oklch(0.65 0 0);
	}

	/* ── Text input ── */
	.text-input {
		width: 100%;
		border-radius: var(--radius-lg, 8px);
		border: 1px solid oklch(0.24 0 0);
		background: oklch(0.13 0 0);
		padding: 8px 12px;
		font-size: 0.875rem;
		color: oklch(0.88 0 0);
		outline: none;
		transition: all 150ms;
	}

	.text-input::placeholder {
		color: oklch(0.40 0 0);
	}

	.text-input:focus {
		border-color: oklch(0.45 0.12 250);
		box-shadow: 0 0 0 2px oklch(0.45 0.12 250 / 0.3);
	}

	/* ── Scan grid ── */
	.scan-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 6px;
	}

	.scan-option {
		display: flex;
		cursor: pointer;
		align-items: center;
		gap: 8px;
		border-radius: var(--radius-lg, 8px);
		border: 1px solid;
		padding: 8px 12px;
		transition: all 150ms;
	}

	.scan-option-selected {
		border-color: oklch(0.40 0.10 250);
		background: oklch(0.17 0.02 250);
	}

	.scan-option-unselected {
		border-color: oklch(0.20 0 0);
		background: oklch(0.11 0 0);
	}

	.scan-option-unselected:hover {
		border-color: oklch(0.28 0 0);
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		border: 0;
	}

	.checkbox-indicator {
		display: flex;
		height: 16px;
		width: 16px;
		flex-shrink: 0;
		align-items: center;
		justify-content: center;
		border-radius: var(--radius-sm, 4px);
		border: 1px solid;
		transition: all 150ms;
	}

	.checkbox-checked {
		border-color: oklch(0.50 0.12 250);
		background: oklch(0.45 0.12 250);
	}

	.checkbox-unchecked {
		border-color: oklch(0.30 0 0);
		background: oklch(0.13 0 0);
	}

	.check-icon {
		height: 12px;
		width: 12px;
		color: white;
	}

	.scan-label {
		font-size: 0.75rem;
		color: oklch(0.75 0 0);
	}

	.scan-count {
		font-size: 11px;
		color: oklch(0.50 0 0);
	}

	/* ── Strength slider ── */
	.strength-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.strength-value {
		font-size: 0.75rem;
		font-weight: 500;
		color: oklch(0.75 0.10 250);
	}

	.slider-track {
		height: 6px;
		width: 100%;
		cursor: pointer;
		appearance: none;
		border-radius: 9999px;
		background: oklch(0.20 0 0);
		outline: none;
	}

	.slider-track::-webkit-slider-thumb {
		height: 16px;
		width: 16px;
		appearance: none;
		border-radius: 9999px;
		background: oklch(0.55 0.15 145);
		box-shadow: 0 0 0 3px oklch(0.14 0 0);
		transition: all 150ms;
	}

	.slider-track::-webkit-slider-thumb:hover {
		background: oklch(0.60 0.16 145);
		transform: scale(1.1);
	}

	.slider-track::-moz-range-thumb {
		height: 16px;
		width: 16px;
		border-radius: 9999px;
		border: 0;
		background: oklch(0.55 0.15 145);
		box-shadow: 0 0 0 3px oklch(0.14 0 0);
	}

	.strength-ticks {
		display: flex;
		justify-content: space-between;
		padding-inline: 2px;
	}

	.tick-label {
		font-size: 10px;
	}

	.tick-active {
		color: oklch(0.60 0.10 145);
	}

	.tick-inactive {
		color: oklch(0.35 0 0);
	}

	/* ── Direction buttons ── */
	.direction-group {
		display: flex;
		gap: 6px;
	}

	.direction-btn {
		flex: 1;
		border-radius: var(--radius-lg, 8px);
		border: 1px solid;
		padding: 8px 12px;
		font-size: 0.75rem;
		font-weight: 500;
		cursor: pointer;
		transition: all 150ms;
	}

	.direction-bullish-active {
		border-color: oklch(0.40 0.10 145);
		background: oklch(0.18 0.04 145);
		color: oklch(0.75 0.15 145);
	}

	.direction-both-active {
		border-color: oklch(0.40 0.10 250);
		background: oklch(0.17 0.02 250);
		color: oklch(0.72 0.12 250);
	}

	.direction-bearish-active {
		border-color: oklch(0.40 0.10 25);
		background: oklch(0.18 0.04 25);
		color: oklch(0.70 0.16 25);
	}

	.direction-inactive {
		border-color: oklch(0.20 0 0);
		background: oklch(0.11 0 0);
		color: oklch(0.55 0 0);
	}

	.direction-inactive:hover {
		border-color: oklch(0.28 0 0);
	}

	/* ── Notifications section ── */
	.notifications-section {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.notification-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		border-radius: var(--radius-lg, 8px);
		border: 1px solid oklch(0.20 0 0);
		background: oklch(0.11 0 0);
		padding: 12px 16px;
	}

	.notification-info {
		display: flex;
		align-items: center;
		gap: 12px;
	}

	.notification-icon {
		height: 16px;
		width: 16px;
		color: oklch(0.55 0 0);
	}

	.notification-text {
		display: flex;
		flex-direction: column;
	}

	.notification-title {
		font-size: 0.75rem;
		font-weight: 500;
		color: oklch(0.80 0 0);
	}

	.notification-desc {
		font-size: 11px;
		color: oklch(0.50 0 0);
	}

	.notification-controls {
		display: flex;
		align-items: center;
		gap: 12px;
	}

	/* ── Sound select ── */
	.sound-select {
		border-radius: var(--radius-md, 6px);
		border: 1px solid oklch(0.24 0 0);
		background: oklch(0.13 0 0);
		padding: 4px 8px;
		font-size: 11px;
		color: oklch(0.75 0 0);
		outline: none;
	}

	.sound-select:focus {
		border-color: oklch(0.45 0.12 250);
	}

	/* ── Actions bar ── */
	.actions-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		border-top: 1px solid oklch(0.20 0 0);
		padding-top: 16px;
	}

	.delete-confirm-group {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.delete-confirm-text {
		font-size: 0.75rem;
		color: oklch(0.65 0.16 25);
	}

	.delete-confirm-btn {
		border-radius: var(--radius-md, 6px);
		border: none;
		background: oklch(0.50 0.18 25);
		padding: 6px 12px;
		font-size: 0.75rem;
		font-weight: 500;
		color: white;
		cursor: pointer;
		transition: background-color 200ms;
	}

	.delete-confirm-btn:hover {
		background: oklch(0.55 0.19 25);
	}

	.delete-cancel-btn {
		border-radius: var(--radius-md, 6px);
		border: none;
		background: transparent;
		padding: 6px 12px;
		font-size: 0.75rem;
		font-weight: 500;
		color: oklch(0.65 0 0);
		cursor: pointer;
		transition: color 200ms;
	}

	.delete-cancel-btn:hover {
		color: oklch(0.80 0 0);
	}

	.delete-btn {
		border-radius: var(--radius-md, 6px);
		border: none;
		background: transparent;
		padding: 6px 12px;
		font-size: 0.75rem;
		font-weight: 500;
		color: oklch(0.55 0.10 25);
		cursor: pointer;
		transition: all 200ms;
	}

	.delete-btn:hover {
		background: oklch(0.18 0.02 25);
		color: oklch(0.65 0.14 25);
	}

	.save-btn {
		border-radius: var(--radius-lg, 8px);
		border: none;
		background: oklch(0.55 0.15 145);
		padding: 8px 20px;
		font-size: 0.875rem;
		font-weight: 500;
		color: white;
		cursor: pointer;
		box-shadow: 0 1px 2px 0 oklch(0.55 0.15 145 / 0.25);
		transition: all 150ms;
	}

	.save-btn:hover {
		background: oklch(0.60 0.16 145);
	}

	.save-btn:active {
		background: oklch(0.50 0.14 145);
	}
</style>
