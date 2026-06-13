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
		if (direction === 'bullish') return 'dot-bullish';
		if (direction === 'bearish') return 'dot-bearish';
		return 'dot-neutral';
	}

	function lineColor(direction: string): string {
		if (direction === 'bullish') return 'line-bullish';
		if (direction === 'bearish') return 'line-bearish';
		return 'line-neutral';
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

<div class="timeline-container {className}" role="list" aria-label="Signal timeline">
	{#each sorted as signal, i (signal.time + signal.name)}
		<div class="timeline-item" role="listitem">
			<!-- Timeline line + dot -->
			<div class="timeline-track">
				<!-- Dot -->
				<div class="timeline-dot {dotColor(signal.direction)}">
					{#if i === 0}
						<div class="timeline-ping {dotColor(signal.direction)} signal-ping"></div>
					{/if}
				</div>
				<!-- Connecting line -->
				{#if i < sorted.length - 1}
					<div class="timeline-line {lineColor(signal.direction)}"></div>
				{/if}
			</div>

			<!-- Content -->
			<div class="timeline-content">
				<div class="signal-header">
					<span class="signal-name">{signal.name}</span>
					<span class="signal-badge {badgeClass(signal.direction)}">
						{signal.direction}
					</span>
				</div>

				<div class="signal-meta">
					<!-- Strength indicator -->
					<div class="strength-bar" title="Strength: {signal.strength}/5">
						{#each strengthDots(signal.strength) as _, idx}
							<div
								class="strength-dot {idx < signal.strength ? `strength-${Math.min(signal.strength, 5) as SignalStrength}` : 'strength-empty'}"
							></div>
						{/each}
					</div>

					<!-- Timestamp -->
					<span class="signal-timestamp mono-nums">
						{formatTimestamp(signal.time)}
					</span>
				</div>
			</div>
		</div>
	{:else}
		<div class="timeline-empty">
			No signals recorded
		</div>
	{/each}
</div>

<style>
	.timeline-container {
		display: flex;
		flex-direction: column;
	}

	.timeline-item {
		position: relative;
		display: flex;
		gap: 12px;
	}

	.timeline-track {
		display: flex;
		flex-direction: column;
		align-items: center;
	}

	.timeline-dot {
		position: relative;
		z-index: 10;
		margin-top: 4px;
		height: 10px;
		width: 10px;
		flex-shrink: 0;
		border-radius: var(--radius-full);
	}

	.timeline-ping {
		position: absolute;
		top: 0;
		right: 0;
		bottom: 0;
		left: 0;
		border-radius: var(--radius-full);
		opacity: 0.4;
	}

	.timeline-line {
		width: 1px;
		flex: 1;
		min-height: 24px;
	}

	.timeline-content {
		flex: 1;
		padding-bottom: 16px;
		min-width: 0;
	}

	.signal-header {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-wrap: wrap;
	}

	.signal-name {
		font-size: var(--text-sm);
		font-weight: 500;
		color: var(--text-primary);
	}

	.signal-badge {
		display: inline-flex;
		align-items: center;
		border-radius: var(--radius-full);
		padding: 2px 8px;
		font-size: 10px;
		font-weight: 500;
		line-height: 1;
	}

	.signal-meta {
		margin-top: 4px;
		display: flex;
		align-items: center;
		gap: 12px;
	}

	.strength-bar {
		display: flex;
		align-items: center;
		gap: 2px;
	}

	.strength-dot {
		height: 4px;
		width: 12px;
		border-radius: var(--radius-full);
		transition: color 150ms, background-color 150ms;
	}

	.strength-empty {
		background-color: var(--bg-overlay);
	}

	.signal-timestamp {
		font-size: var(--text-2xs);
		color: var(--text-tertiary);
	}

	.timeline-empty {
		padding: 16px 0;
		text-align: center;
		font-size: var(--text-sm);
		color: var(--text-tertiary);
	}

	/* Direction-specific dot colors */
	.dot-bullish {
		background-color: var(--bullish);
	}

	.dot-bearish {
		background-color: var(--bearish);
	}

	.dot-neutral {
		background-color: var(--neutral);
	}

	/* Direction-specific line colors */
	.line-bullish {
		background-color: var(--bullish-dim);
	}

	.line-bearish {
		background-color: var(--bearish-dim);
	}

	.line-neutral {
		background-color: var(--neutral-dim);
	}
</style>
