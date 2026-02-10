<script lang="ts">
	import PriceCell from './PriceCell.svelte';
	import PercentCell from './PercentCell.svelte';
	import VolumeBar from './VolumeBar.svelte';
	import SignalBadge from './SignalBadge.svelte';
	import SparkLine from './SparkLine.svelte';
	import TimestampCell from './TimestampCell.svelte';
	import TickerSymbol from './TickerSymbol.svelte';

	interface Props {
		type: 'price' | 'percent' | 'volume' | 'text' | 'signal' | 'sparkline' | 'timestamp' | 'ticker';
		value: unknown;
		metadata?: Record<string, unknown>;
		class?: string;
	}

	let {
		type,
		value,
		metadata = {},
		class: className = ''
	}: Props = $props();
</script>

<div class="inline-flex items-center {className}">
	{#if type === 'price'}
		<PriceCell
			value={Number(value) || 0}
			prevValue={metadata.prevValue != null ? Number(metadata.prevValue) : undefined}
			decimals={metadata.decimals != null ? Number(metadata.decimals) : 2}
			size={(metadata.size as 'sm' | 'md' | 'lg') ?? 'md'}
		/>
	{:else if type === 'percent'}
		<PercentCell
			value={Number(value) || 0}
			signed={metadata.signed != null ? Boolean(metadata.signed) : true}
			size={(metadata.size as 'sm' | 'md' | 'lg') ?? 'md'}
		/>
	{:else if type === 'volume'}
		<VolumeBar
			value={Number(value) || 0}
			average={metadata.average != null ? Number(metadata.average) : 1}
			maxWidth={metadata.maxWidth != null ? Number(metadata.maxWidth) : 80}
		/>
	{:else if type === 'signal'}
		<SignalBadge
			direction={(metadata.direction as 'bullish' | 'bearish' | 'neutral') ?? 'neutral'}
			strength={Number(metadata.strength) || 1}
			label={metadata.label != null ? String(metadata.label) : undefined}
		/>
	{:else if type === 'sparkline'}
		<SparkLine
			data={Array.isArray(value) ? (value as number[]) : []}
			width={metadata.width != null ? Number(metadata.width) : 100}
			height={metadata.height != null ? Number(metadata.height) : 24}
			color={metadata.color != null ? String(metadata.color) : undefined}
			showLastPoint={metadata.showLastPoint != null ? Boolean(metadata.showLastPoint) : false}
		/>
	{:else if type === 'timestamp'}
		<TimestampCell
			timestamp={value instanceof Date ? value : Number(value) || Date.now()}
			format={(metadata.format as 'relative' | 'absolute' | 'both') ?? 'relative'}
			size={(metadata.size as 'sm' | 'md') ?? 'sm'}
		/>
	{:else if type === 'ticker'}
		<TickerSymbol
			symbol={String(value ?? '')}
			name={metadata.name != null ? String(metadata.name) : undefined}
			showName={metadata.showName != null ? Boolean(metadata.showName) : false}
			size={(metadata.size as 'sm' | 'md' | 'lg') ?? 'md'}
		/>
	{:else}
		<!-- text fallback -->
		<span class="truncate text-sm text-[oklch(0.78_0_0)]">
			{String(value ?? '--')}
		</span>
	{/if}
</div>
