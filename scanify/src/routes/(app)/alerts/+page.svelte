<script lang="ts">
	let activeTab = $state<'active' | 'history'>('active');

	const activeAlerts = [
		{ id: '1', name: 'High Strength Signals', description: 'Alerts for strength 4-5 signals across all scans', minStrength: 4, directions: ['bullish', 'bearish'], soundEnabled: true, isActive: true },
		{ id: '2', name: 'Unusual Volume Breakouts', description: 'Volume > 3x average with price breakout', minStrength: 3, directions: ['bullish'], soundEnabled: true, isActive: true },
		{ id: '3', name: 'Options Sweep Alerts', description: 'Large sweep orders > $500K premium', minStrength: 2, directions: ['bullish', 'bearish'], soundEnabled: false, isActive: false },
	];

	const alertHistory = [
		{ id: 'h1', symbol: 'NVDA', signalName: 'Momentum Breakout', direction: 'bullish', strength: 5, price: 875.30, timestamp: Date.now() - 120000, isRead: false },
		{ id: 'h2', symbol: 'TSLA', signalName: 'Volume Surge', direction: 'bearish', strength: 4, price: 245.10, timestamp: Date.now() - 300000, isRead: false },
		{ id: 'h3', symbol: 'AMD', signalName: 'Unusual Options', direction: 'bullish', strength: 4, price: 165.40, timestamp: Date.now() - 600000, isRead: true },
		{ id: 'h4', symbol: 'META', signalName: 'Institutional Flow', direction: 'bullish', strength: 3, price: 505.80, timestamp: Date.now() - 1200000, isRead: true },
		{ id: 'h5', symbol: 'SPY', signalName: 'Breadth Divergence', direction: 'bearish', strength: 3, price: 502.34, timestamp: Date.now() - 1800000, isRead: true },
	];

	function formatTime(ts: number): string {
		const diff = Math.floor((Date.now() - ts) / 1000);
		if (diff < 60) return `${diff}s ago`;
		if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
		return `${Math.floor(diff / 3600)}h ago`;
	}

	let toggles = $state(activeAlerts.map(a => a.isActive));
</script>

<div class="flex h-full flex-col gap-4 p-4" style="color: oklch(0.95 0.005 260);">
	<h1 class="text-lg font-semibold">Alerts</h1>

	<div class="flex gap-1 rounded-md p-1" style="background: oklch(0.11 0.008 260); border: 1px solid oklch(0.20 0.008 260); width: fit-content;">
		<button onclick={() => activeTab = 'active'} class="rounded px-4 py-1.5 text-xs font-medium transition-colors" style="background: {activeTab === 'active' ? 'oklch(0.17 0.012 260)' : 'transparent'}; color: {activeTab === 'active' ? 'oklch(0.95 0.005 260)' : 'oklch(0.52 0.006 260)'};">Active Alerts</button>
		<button onclick={() => activeTab = 'history'} class="rounded px-4 py-1.5 text-xs font-medium transition-colors" style="background: {activeTab === 'history' ? 'oklch(0.17 0.012 260)' : 'transparent'}; color: {activeTab === 'history' ? 'oklch(0.95 0.005 260)' : 'oklch(0.52 0.006 260)'};">History</button>
	</div>

	{#if activeTab === 'active'}
		<div class="flex flex-col gap-3">
			{#each activeAlerts as alert, i}
				<div class="flex items-center justify-between rounded-lg p-4" style="background: oklch(0.14 0.010 260); border: 1px solid oklch(0.20 0.008 260);">
					<div class="flex-1">
						<div class="flex items-center gap-2">
							<h3 class="text-sm font-semibold">{alert.name}</h3>
							<span class="rounded-full px-2 py-0.5 text-[10px] font-mono" style="background: oklch(0.20 0.014 260); color: oklch(0.72 0.008 260);">Strength ≥ {alert.minStrength}</span>
						</div>
						<p class="mt-1 text-xs" style="color: oklch(0.52 0.006 260);">{alert.description}</p>
					</div>
					<button onclick={() => toggles[i] = !toggles[i]} class="relative h-5 w-9 rounded-full transition-colors" style="background: {toggles[i] ? 'oklch(0.72 0.19 155)' : 'oklch(0.28 0.010 260)'};">
						<span class="absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform" style="left: {toggles[i] ? '18px' : '2px'};"></span>
					</button>
				</div>
			{/each}
		</div>
	{:else}
		<div class="flex flex-col gap-2">
			{#each alertHistory as alert}
				<div class="flex items-center gap-3 rounded-lg px-4 py-3" style="background: oklch(0.14 0.010 260); border-left: 3px solid {alert.direction === 'bullish' ? 'oklch(0.72 0.19 155)' : 'oklch(0.65 0.22 25)'}; opacity: {alert.isRead ? 0.7 : 1};">
					<div class="flex-1">
						<div class="flex items-center gap-2">
							<span class="font-mono text-sm font-semibold tracking-wider">{alert.symbol}</span>
							<span class="text-xs" style="color: oklch(0.52 0.006 260);">{alert.signalName}</span>
						</div>
						<div class="mt-1 flex items-center gap-2 font-mono text-xs">
							<span style="color: {alert.direction === 'bullish' ? 'oklch(0.72 0.19 155)' : 'oklch(0.65 0.22 25)'};">${alert.price.toFixed(2)}</span>
							<span style="color: oklch(0.52 0.006 260);">{formatTime(alert.timestamp)}</span>
						</div>
					</div>
					<div class="flex items-center gap-1">
						{#each Array(5) as _, j}
							<span class="text-[8px]" style="color: {j < alert.strength ? (alert.direction === 'bullish' ? 'oklch(0.72 0.19 155)' : 'oklch(0.65 0.22 25)') : 'oklch(0.28 0.010 260)'};">●</span>
						{/each}
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>
