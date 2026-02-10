<script lang="ts">
	import type { SignalDirection, SignalStrength } from '$types/scan';

	interface TimelineSignal {
		time: number;
		name: string;
		direction: string;
		strength: number;
	}

	interface Props {
		signals: TimelineSignal[];
		class?: string;
	}

	let { signals, class: className = '' }: Props = $props();

	let sorted = $derived(
		[...signals].sort((a, b) => b.time - a.time)
	);

	function formatTimestamp(ts: number): string {
		const d = new Date(ts);
		const now = Date.now();
		const delta = now - ts;

		if (delta < 60_000) return 'just now';
		if (delta < 3_600_000) return `${Math.floor(delta / 60_000)}m ago`;
		if (delta < 86_400_000) {
			return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
		}
		return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
	}

	function dotColor(direction: string): string {
		if (direction === 'bullish') return 'bg-[var(--bullish)]';
		if (direction === 'bearish') return 'bg-[var(--bearish)]';
		return 'bg-[var(--neutral)]';
	}

	function lineColor(direction: string): string {
		if (direction === 'bullish') return 'bg-[var(--bullish-dim)]';
		if (direction === 'bearish') return 'bg-[var(--bearish-dim)]';
		return 'bg-[var(--neutral-dim)]';
	}

	function badgeClass(direction: string): string {
		if (direction === 'bullish') return 'badge-bullish';
		if (direction === 'bearish') return 'badge-bearish';
		return 'badge-neutral';
	}

	function strengthDots(strength: number): number[] {
		return Array.from({ length: 5 }, (_, i) => i);
	}
</script>

<div class="flex flex-col {className}" role="list" aria-label="Signal timeline">
	{#each sorted as signal, i (signal.time + signal.name)}
		<div class="relative flex gap-3" role="listitem">
			<!-- Timeline line + dot -->
			<div class="flex flex-col items-center">
				<!-- Dot -->
				<div class="relative z-10 mt-1 h-2.5 w-2.5 shrink-0 rounded-full {dotColor(signal.direction)}">
					{#if i === 0}
						<div class="absolute inset-0 rounded-full {dotColor(signal.direction)} signal-ping opacity-40"></div>
					{/if}
				</div>
				<!-- Connecting line -->
				{#if i < sorted.length - 1}
					<div class="w-px flex-1 min-h-6 {lineColor(signal.direction)}"></div>
				{/if}
			</div>

			<!-- Content -->
			<div class="flex-1 pb-4 min-w-0">
				<div class="flex items-center gap-2 flex-wrap">
					<span class="text-sm font-medium text-[var(--text-primary)]">{signal.name}</span>
					<span class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium leading-none {badgeClass(signal.direction)}">
						{signal.direction}
					</span>
				</div>

				<div class="mt-1 flex items-center gap-3">
					<!-- Strength indicator -->
					<div class="flex items-center gap-0.5" title="Strength: {signal.strength}/5">
						{#each strengthDots(signal.strength) as _, idx}
							<div
								class="h-1 w-3 rounded-full transition-colors {idx < signal.strength ? `strength-${Math.min(signal.strength, 5) as SignalStrength}` : 'bg-[var(--bg-overlay)]'}"
							></div>
						{/each}
					</div>

					<!-- Timestamp -->
					<span class="text-2xs text-[var(--text-tertiary)] mono-nums">
						{formatTimestamp(signal.time)}
					</span>
				</div>
			</div>
		</div>
	{:else}
		<div class="py-4 text-center text-sm text-[var(--text-tertiary)]">
			No signals recorded
		</div>
	{/each}
</div>
