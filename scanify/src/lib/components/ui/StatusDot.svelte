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

	let shouldPulse = $derived(pulse || status === 'connecting');

	const statusLabel: Record<string, string> = {
		online: 'Online',
		offline: 'Offline',
		connecting: 'Connecting',
		error: 'Error'
	};
</script>

<span
	class="status-dot-wrapper {className}"
	role="status"
	aria-label={statusLabel[status]}
>
	{#if shouldPulse}
		<span
			class="pulse-ring status-{status}"
		></span>
	{/if}
	<span
		class="dot size-{size} status-{status}"
	></span>
</span>

<style>
	.status-dot-wrapper {
		position: relative;
		display: inline-flex;
	}

	.pulse-ring {
		position: absolute;
		display: inline-flex;
		height: 100%;
		width: 100%;
		border-radius: var(--radius-full);
		opacity: 0.75;
		animation: ping 1s cubic-bezier(0, 0, 0.2, 1) infinite;
	}

	.dot {
		position: relative;
		display: inline-flex;
		border-radius: var(--radius-full);
	}

	/* Sizes */
	.size-sm { height: 6px; width: 6px; }
	.size-md { height: 10px; width: 10px; }
	.size-lg { height: 14px; width: 14px; }

	/* Status colors — applied to both dot and pulse-ring */
	.dot.status-online {
		background-color: oklch(0.60 0.17 145);
		box-shadow: 0 0 6px oklch(0.55 0.17 145 / 0.6);
	}

	.dot.status-offline {
		background-color: oklch(0.45 0 0);
	}

	.dot.status-connecting {
		background-color: oklch(0.70 0.15 80);
		box-shadow: 0 0 6px oklch(0.65 0.15 80 / 0.5);
	}

	.dot.status-error {
		background-color: oklch(0.55 0.18 25);
		box-shadow: 0 0 6px oklch(0.50 0.18 25 / 0.6);
	}

	.pulse-ring.status-online { background-color: oklch(0.60 0.17 145 / 0.4); }
	.pulse-ring.status-offline { background-color: oklch(0.45 0 0 / 0.3); }
	.pulse-ring.status-connecting { background-color: oklch(0.70 0.15 80 / 0.4); }
	.pulse-ring.status-error { background-color: oklch(0.55 0.18 25 / 0.4); }

	@keyframes ping {
		75%, 100% {
			transform: scale(2);
			opacity: 0;
		}
	}
</style>
