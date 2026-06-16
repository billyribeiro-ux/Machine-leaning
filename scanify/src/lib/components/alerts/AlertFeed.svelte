<!--
  AlertFeed.svelte
  Real-time vertical feed of triggered trading alerts.
  Supports filtering by read-state and direction, slide-in animations.
-->
<script lang="ts">
	interface AlertSignal {
		symbol: string;
		direction: 'bullish' | 'bearish';
		strength: number;
		name: string;
		price: number;
	}

	interface Alert {
		id: string;
		signal: AlertSignal;
		timestamp: number;
		isRead: boolean;
	}

	type FilterMode = 'all' | 'unread' | 'bullish' | 'bearish';

	interface Props {
		alerts?: Alert[];
		onmarkread?: (id: string) => void;
		class?: string;
	}

	let {
		alerts = [],
		onmarkread,
		class: className = ''
	}: Props = $props();

	let filter = $state<FilterMode>('all');

	let filteredAlerts = $derived.by(() => {
		let result = alerts;
		switch (filter) {
			case 'unread':
				result = result.filter((a) => !a.isRead);
				break;
			case 'bullish':
				result = result.filter((a) => a.signal.direction === 'bullish');
				break;
			case 'bearish':
				result = result.filter((a) => a.signal.direction === 'bearish');
				break;
		}
		return result.sort((a, b) => b.timestamp - a.timestamp);
	});

	let unreadCount = $derived(alerts.filter((a) => !a.isRead).length);

	function formatTime(ts: number): string {
		const d = new Date(ts);
		return d.toLocaleTimeString('en-US', {
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit',
			hour12: false
		});
	}

	function formatPrice(price: number): string {
		return '$' + price.toFixed(2);
	}

	function handleAlertClick(id: string) {
		onmarkread?.(id);
	}

	const filterButtons: { key: FilterMode; label: string }[] = [
		{ key: 'all', label: 'All' },
		{ key: 'unread', label: 'Unread' },
		{ key: 'bullish', label: 'Bullish' },
		{ key: 'bearish', label: 'Bearish' }
	];

	const directionConfig: Record<string, { icon: string }> = {
		bullish: {
			icon: 'M5 15l7-7 7 7'
		},
		bearish: {
			icon: 'M19 9l-7 7-7-7'
		}
	};
</script>

<div class="feed-root {className}">
	<!-- Header -->
	<div class="feed-header">
		<div class="header-left">
			<h3 class="header-title">Alert Feed</h3>
			{#if unreadCount > 0}
				<span class="unread-badge">
					{unreadCount}
				</span>
			{/if}
		</div>

		<!-- Filters -->
		<div class="filter-bar">
			{#each filterButtons as btn (btn.key)}
				<button
					type="button"
					class="filter-btn"
					class:filter-btn-active={filter === btn.key}
					onclick={() => (filter = btn.key)}
				>
					{btn.label}
				</button>
			{/each}
		</div>
	</div>

	<!-- Alert List -->
	<div class="alert-list scrollbar-thin">
		{#if filteredAlerts.length === 0}
			<div class="empty-state">
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="empty-icon"
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
				<p class="empty-text">No alerts to display</p>
			</div>
		{:else}
			<div class="alert-col">
				{#each filteredAlerts as alert, idx (alert.id)}
					{@const config = directionConfig[alert.signal.direction]}
					<button
						type="button"
						class="alert-card"
						class:bullish-border={alert.signal.direction === 'bullish' && alert.isRead}
						class:bullish-border-unread={alert.signal.direction === 'bullish' && !alert.isRead}
						class:bearish-border={alert.signal.direction === 'bearish' && alert.isRead}
						class:bearish-border-unread={alert.signal.direction === 'bearish' && !alert.isRead}
						class:alert-read={alert.isRead}
						style="animation-delay: {idx * 40}ms"
						onclick={() => handleAlertClick(alert.id)}
						aria-label="Alert: {alert.signal.symbol} {alert.signal.name} - {alert.signal.direction}"
					>
						<!-- Direction Icon -->
						<div
							class="direction-icon-wrapper"
							class:direction-icon-bullish={alert.signal.direction === 'bullish'}
							class:direction-icon-bearish={alert.signal.direction === 'bearish'}
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								class="direction-icon-svg"
								class:direction-svg-bullish={alert.signal.direction === 'bullish'}
								class:direction-svg-bearish={alert.signal.direction === 'bearish'}
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
								stroke-width="2.5"
							>
								<path stroke-linecap="round" stroke-linejoin="round" d={config.icon} />
							</svg>
						</div>

						<!-- Content -->
						<div class="alert-content">
							<div class="alert-top-row">
								<div class="alert-symbol-group">
									<span class="alert-symbol">
										{alert.signal.symbol}
									</span>
									<span
										class="direction-badge"
										class:badge-bullish={alert.signal.direction === 'bullish'}
										class:badge-bearish={alert.signal.direction === 'bearish'}
									>
										{alert.signal.direction === 'bullish' ? 'BULL' : 'BEAR'}
									</span>
								</div>
								<span class="alert-time">
									{formatTime(alert.timestamp)}
								</span>
							</div>

							<div class="alert-mid-row">
								<span class="alert-name">
									{alert.signal.name}
								</span>
								<span class="alert-price">
									{formatPrice(alert.signal.price)}
								</span>
							</div>

							<!-- Strength dots -->
							<div class="strength-dots">
								{#each Array(5) as _, i}
									<span
										class="strength-dot"
										class:dot-bullish-active={i < alert.signal.strength && alert.signal.direction === 'bullish'}
										class:dot-bearish-active={i < alert.signal.strength && alert.signal.direction === 'bearish'}
										class:dot-inactive={i >= alert.signal.strength}
									></span>
								{/each}
								<span class="strength-label">
									{alert.signal.strength}/5
								</span>
							</div>
						</div>

						<!-- Unread indicator -->
						{#if !alert.isRead}
							<span class="unread-dot"></span>
						{/if}
					</button>
				{/each}
			</div>
		{/if}
	</div>
</div>

<style>
	/* ---- Layout root ---- */
	.feed-root {
		display: flex;
		flex-direction: column;
		height: 100%;
	}

	/* ---- Header ---- */
	.feed-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		border-bottom: 1px solid oklch(0.20 0 0);
		padding: 12px 16px;
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.header-title {
		font-size: 0.875rem;
		font-weight: 600;
		color: oklch(0.88 0 0);
	}

	.unread-badge {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		height: 20px;
		min-width: 20px;
		padding: 0 6px;
		border-radius: 9999px;
		background-color: oklch(0.55 0.15 145);
		font-size: 10px;
		font-weight: 700;
		color: white;
	}

	/* ---- Filter bar ---- */
	.filter-bar {
		display: flex;
		gap: 2px;
		border-radius: var(--radius-lg, 8px);
		background-color: oklch(0.13 0 0);
		padding: 2px;
	}

	.filter-btn {
		border-radius: var(--radius-md, 6px);
		padding: 4px 10px;
		font-size: 11px;
		font-weight: 500;
		transition: all 150ms;
		color: oklch(0.55 0 0);
		cursor: pointer;
		border: none;
		background: none;
	}

	.filter-btn:hover {
		color: oklch(0.75 0 0);
	}

	.filter-btn-active {
		background-color: oklch(0.22 0.005 270);
		color: oklch(0.88 0 0);
		box-shadow: 0 1px 2px 0 rgb(0 0 0 / 0.05);
	}

	.filter-btn-active:hover {
		color: oklch(0.88 0 0);
	}

	/* ---- Alert list ---- */
	.alert-list {
		flex: 1;
		overflow-y: auto;
	}

	/* ---- Empty state ---- */
	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 8px;
		padding: 64px 0;
		color: oklch(0.45 0 0);
	}

	.empty-icon {
		width: 32px;
		height: 32px;
	}

	.empty-text {
		font-size: 0.75rem;
	}

	/* ---- Alert column ---- */
	.alert-col {
		display: flex;
		flex-direction: column;
	}

	/* ---- Alert card ---- */
	.alert-card {
		display: flex;
		width: 100%;
		align-items: flex-start;
		gap: 12px;
		border-bottom: 1px solid oklch(0.16 0 0);
		border-left: 3px solid transparent;
		padding: 12px 16px;
		text-align: left;
		transition: all 150ms;
		cursor: pointer;
		background: none;
		opacity: 1;
		animation: slideInLeft 250ms ease-out both;
	}

	.alert-card:hover {
		background-color: oklch(0.16 0 0);
	}

	/* Direction-based left border */
	.bullish-border {
		border-left-color: oklch(0.30 0.08 145);
	}

	.bullish-border-unread {
		border-left-color: oklch(0.55 0.15 145);
	}

	.bearish-border {
		border-left-color: oklch(0.30 0.08 25);
	}

	.bearish-border-unread {
		border-left-color: oklch(0.55 0.18 25);
	}

	/* Read state */
	.alert-read {
		opacity: 0.7;
	}

	/* ---- Direction icon ---- */
	.direction-icon-wrapper {
		margin-top: 2px;
		display: flex;
		height: 28px;
		width: 28px;
		flex-shrink: 0;
		align-items: center;
		justify-content: center;
		border-radius: var(--radius-md, 6px);
	}

	.direction-icon-bullish {
		background-color: oklch(0.18 0.04 145);
	}

	.direction-icon-bearish {
		background-color: oklch(0.18 0.04 25);
	}

	.direction-icon-svg {
		width: 16px;
		height: 16px;
	}

	.direction-svg-bullish {
		color: oklch(0.65 0.15 145);
	}

	.direction-svg-bearish {
		color: oklch(0.65 0.16 25);
	}

	/* ---- Alert content ---- */
	.alert-content {
		display: flex;
		min-width: 0;
		flex: 1;
		flex-direction: column;
		gap: 4px;
	}

	.alert-top-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
	}

	.alert-symbol-group {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.alert-symbol {
		font-size: 0.875rem;
		font-weight: 700;
		color: oklch(0.90 0 0);
	}

	/* ---- Direction badge ---- */
	.direction-badge {
		display: inline-flex;
		align-items: center;
		border-radius: 9999px;
		border: 1px solid transparent;
		padding: 2px 6px;
		font-size: 10px;
		font-weight: 500;
	}

	.badge-bullish {
		background-color: oklch(0.20 0.04 145);
		color: oklch(0.75 0.15 145);
		border-color: oklch(0.30 0.06 145);
	}

	.badge-bearish {
		background-color: oklch(0.20 0.04 25);
		color: oklch(0.70 0.16 25);
		border-color: oklch(0.30 0.06 25);
	}

	/* ---- Time ---- */
	.alert-time {
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono',
			'Courier New', monospace;
		font-size: 11px;
		color: oklch(0.50 0 0);
	}

	/* ---- Mid row ---- */
	.alert-mid-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
	}

	.alert-name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.75rem;
		color: oklch(0.65 0 0);
	}

	.alert-price {
		flex-shrink: 0;
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono',
			'Courier New', monospace;
		font-size: 0.75rem;
		font-weight: 500;
		color: oklch(0.80 0 0);
	}

	/* ---- Strength dots ---- */
	.strength-dots {
		display: flex;
		align-items: center;
		gap: 2px;
	}

	.strength-dot {
		display: inline-block;
		width: 6px;
		height: 6px;
		border-radius: 9999px;
	}

	.dot-bullish-active {
		background-color: oklch(0.55 0.15 145);
	}

	.dot-bearish-active {
		background-color: oklch(0.55 0.18 25);
	}

	.dot-inactive {
		background-color: oklch(0.22 0 0);
	}

	.strength-label {
		margin-left: 4px;
		font-size: 10px;
		color: oklch(0.45 0 0);
	}

	/* ---- Unread dot ---- */
	.unread-dot {
		margin-top: 4px;
		width: 8px;
		height: 8px;
		flex-shrink: 0;
		border-radius: 9999px;
		background-color: oklch(0.55 0.15 145);
		box-shadow: 0 0 6px oklch(0.55 0.15 145 / 0.5);
	}

	/* ---- Animation ---- */
	@keyframes slideInLeft {
		from {
			opacity: 0;
			transform: translateX(-12px);
		}
		to {
			opacity: 1;
			transform: translateX(0);
		}
	}

	/* ---- Scrollbar ---- */
	.scrollbar-thin {
		scrollbar-width: thin;
		scrollbar-color: oklch(0.25 0 0) transparent;
	}
	.scrollbar-thin::-webkit-scrollbar {
		width: 4px;
	}
	.scrollbar-thin::-webkit-scrollbar-track {
		background: transparent;
	}
	.scrollbar-thin::-webkit-scrollbar-thumb {
		background-color: oklch(0.25 0 0);
		border-radius: 2px;
	}
</style>
