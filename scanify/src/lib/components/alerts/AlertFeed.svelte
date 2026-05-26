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

	const directionConfig: Record<
		string,
		{ badge: string; border: string; borderUnread: string; icon: string }
	> = {
		bullish: {
			badge:
				'bg-[oklch(0.20_0.04_145)] text-[oklch(0.75_0.15_145)] border-[oklch(0.30_0.06_145)]',
			border: 'border-l-[oklch(0.30_0.08_145)]',
			borderUnread: 'border-l-[oklch(0.55_0.15_145)]',
			icon: 'M5 15l7-7 7 7'
		},
		bearish: {
			badge:
				'bg-[oklch(0.20_0.04_25)] text-[oklch(0.70_0.16_25)] border-[oklch(0.30_0.06_25)]',
			border: 'border-l-[oklch(0.30_0.08_25)]',
			borderUnread: 'border-l-[oklch(0.55_0.18_25)]',
			icon: 'M19 9l-7 7-7-7'
		}
	};
</script>

<div class="flex h-full flex-col {className}">
	<!-- Header -->
	<div class="flex items-center justify-between border-b border-[oklch(0.20_0_0)] px-4 py-3">
		<div class="flex items-center gap-2">
			<h3 class="text-sm font-semibold text-[oklch(0.88_0_0)]">Alert Feed</h3>
			{#if unreadCount > 0}
				<span
					class="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[oklch(0.55_0.15_145)] px-1.5 text-[10px] font-bold text-white"
				>
					{unreadCount}
				</span>
			{/if}
		</div>

		<!-- Filters -->
		<div class="flex gap-0.5 rounded-lg bg-[oklch(0.13_0_0)] p-0.5">
			{#each filterButtons as btn (btn.key)}
				<button
					type="button"
					class="rounded-md px-2.5 py-1 text-[11px] font-medium transition-all duration-150
						{filter === btn.key
						? 'bg-[oklch(0.22_0.005_270)] text-[oklch(0.88_0_0)] shadow-sm'
						: 'text-[oklch(0.55_0_0)] hover:text-[oklch(0.75_0_0)]'}"
					onclick={() => (filter = btn.key)}
				>
					{btn.label}
				</button>
			{/each}
		</div>
	</div>

	<!-- Alert List -->
	<div class="flex-1 overflow-y-auto scrollbar-thin">
		{#if filteredAlerts.length === 0}
			<div class="flex flex-col items-center justify-center gap-2 py-16 text-[oklch(0.45_0_0)]">
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-8 w-8"
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
				<p class="text-xs">No alerts to display</p>
			</div>
		{:else}
			<div class="flex flex-col">
				{#each filteredAlerts as alert, idx (alert.id)}
					{@const config = directionConfig[alert.signal.direction]}
					<button
						type="button"
						class="alert-card group flex w-full items-start gap-3 border-b border-l-[3px] border-b-[oklch(0.16_0_0)] px-4 py-3 text-left transition-all duration-150 hover:bg-[oklch(0.16_0_0)]
							{alert.isRead ? config.border : config.borderUnread}
							{alert.isRead ? 'opacity-70' : 'opacity-100'}"
						style="animation-delay: {idx * 40}ms"
						onclick={() => handleAlertClick(alert.id)}
						aria-label="Alert: {alert.signal.symbol} {alert.signal.name} - {alert.signal.direction}"
					>
						<!-- Direction Icon -->
						<div
							class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md
								{alert.signal.direction === 'bullish'
								? 'bg-[oklch(0.18_0.04_145)]'
								: 'bg-[oklch(0.18_0.04_25)]'}"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								class="h-4 w-4 {alert.signal.direction === 'bullish'
									? 'text-[oklch(0.65_0.15_145)]'
									: 'text-[oklch(0.65_0.16_25)]'}"
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
								stroke-width="2.5"
							>
								<path stroke-linecap="round" stroke-linejoin="round" d={config.icon} />
							</svg>
						</div>

						<!-- Content -->
						<div class="flex min-w-0 flex-1 flex-col gap-1">
							<div class="flex items-center justify-between gap-2">
								<div class="flex items-center gap-2">
									<span class="text-sm font-bold text-[oklch(0.90_0_0)]">
										{alert.signal.symbol}
									</span>
									<span
										class="inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-medium {config.badge}"
									>
										{alert.signal.direction === 'bullish' ? 'BULL' : 'BEAR'}
									</span>
								</div>
								<span class="font-mono text-[11px] text-[oklch(0.50_0_0)]">
									{formatTime(alert.timestamp)}
								</span>
							</div>

							<div class="flex items-center justify-between gap-2">
								<span class="truncate text-xs text-[oklch(0.65_0_0)]">
									{alert.signal.name}
								</span>
								<span class="shrink-0 font-mono text-xs font-medium text-[oklch(0.80_0_0)]">
									{formatPrice(alert.signal.price)}
								</span>
							</div>

							<!-- Strength dots -->
							<div class="flex items-center gap-0.5">
								{#each Array(5) as _, i}
									<span
										class="inline-block h-1.5 w-1.5 rounded-full
											{i < alert.signal.strength
											? alert.signal.direction === 'bullish'
												? 'bg-[oklch(0.55_0.15_145)]'
												: 'bg-[oklch(0.55_0.18_25)]'
											: 'bg-[oklch(0.22_0_0)]'}"
									></span>
								{/each}
								<span class="ml-1 text-[10px] text-[oklch(0.45_0_0)]">
									{alert.signal.strength}/5
								</span>
							</div>
						</div>

						<!-- Unread indicator -->
						{#if !alert.isRead}
							<span
								class="mt-1 h-2 w-2 shrink-0 rounded-full bg-[oklch(0.55_0.15_145)] shadow-[0_0_6px_oklch(0.55_0.15_145/0.5)]"
							></span>
						{/if}
					</button>
				{/each}
			</div>
		{/if}
	</div>
</div>

<style>
	.alert-card {
		animation: slideInLeft 250ms ease-out both;
	}

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
