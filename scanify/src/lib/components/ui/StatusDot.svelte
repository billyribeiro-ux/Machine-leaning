<script lang="ts">
	interface Props {
		status?: 'online' | 'offline' | 'connecting' | 'error';
		size?: 'sm' | 'md' | 'lg';
		pulse?: boolean;
		class?: string;
	}

	let {
		status = 'offline',
		size = 'md',
		pulse = false,
		class: className = ''
	}: Props = $props();

	const statusColors: Record<string, string> = {
		online: 'bg-[oklch(0.60_0.17_145)]',
		offline: 'bg-[oklch(0.45_0_0)]',
		connecting: 'bg-[oklch(0.70_0.15_80)]',
		error: 'bg-[oklch(0.55_0.18_25)]'
	};

	const statusGlowColors: Record<string, string> = {
		online: 'shadow-[0_0_6px_oklch(0.55_0.17_145/0.6)]',
		offline: '',
		connecting: 'shadow-[0_0_6px_oklch(0.65_0.15_80/0.5)]',
		error: 'shadow-[0_0_6px_oklch(0.50_0.18_25/0.6)]'
	};

	const pulseRingColors: Record<string, string> = {
		online: 'bg-[oklch(0.60_0.17_145/0.4)]',
		offline: 'bg-[oklch(0.45_0_0/0.3)]',
		connecting: 'bg-[oklch(0.70_0.15_80/0.4)]',
		error: 'bg-[oklch(0.55_0.18_25/0.4)]'
	};

	const sizeClasses: Record<string, string> = {
		sm: 'h-1.5 w-1.5',
		md: 'h-2.5 w-2.5',
		lg: 'h-3.5 w-3.5'
	};

	const pulseSizeClasses: Record<string, string> = {
		sm: 'h-1.5 w-1.5',
		md: 'h-2.5 w-2.5',
		lg: 'h-3.5 w-3.5'
	};

	let shouldPulse = $derived(pulse || status === 'connecting');

	const statusLabel: Record<string, string> = {
		online: 'Online',
		offline: 'Offline',
		connecting: 'Connecting',
		error: 'Error'
	};
</script>

<span
	class="relative inline-flex {className}"
	role="status"
	aria-label={statusLabel[status]}
>
	{#if shouldPulse}
		<span
			class="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 {pulseRingColors[status]}"
		></span>
	{/if}
	<span
		class="relative inline-flex rounded-full {sizeClasses[size]} {statusColors[status]} {statusGlowColors[status]}"
	></span>
</span>
