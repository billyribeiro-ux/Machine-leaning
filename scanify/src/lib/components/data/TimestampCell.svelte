<script lang="ts">
	interface Props {
		timestamp: number | Date;
		format?: 'relative' | 'absolute' | 'both';
		size?: 'sm' | 'md';
		class?: string;
	}

	let {
		timestamp,
		format = 'relative',
		size = 'sm',
		class: className = ''
	}: Props = $props();

	let now = $state(Date.now());
	let intervalId: ReturnType<typeof setInterval> | undefined;

	const sizeClasses: Record<string, string> = {
		sm: 'text-xs',
		md: 'text-sm'
	};

	let tsMs = $derived.by(() => {
		if (timestamp instanceof Date) return timestamp.getTime();
		if (typeof timestamp === 'number') {
			return timestamp < 1e12 ? timestamp * 1000 : timestamp;
		}
		return Date.now();
	});

	let relativeText = $derived.by(() => {
		const diff = Math.max(0, now - tsMs);
		const seconds = Math.floor(diff / 1000);

		if (seconds < 60) return seconds + 's ago';

		const minutes = Math.floor(seconds / 60);
		if (minutes < 60) return minutes + 'm ago';

		const hours = Math.floor(minutes / 60);
		if (hours < 24) return hours + 'h ago';

		const days = Math.floor(hours / 24);
		return days + 'd ago';
	});

	let absoluteText = $derived.by(() => {
		const date = new Date(tsMs);
		const h = String(date.getHours()).padStart(2, '0');
		const m = String(date.getMinutes()).padStart(2, '0');
		const s = String(date.getSeconds()).padStart(2, '0');
		return h + ':' + m + ':' + s;
	});

	let displayText = $derived.by(() => {
		if (format === 'absolute') return absoluteText;
		if (format === 'both') return absoluteText + ' (' + relativeText + ')';
		return relativeText;
	});

	$effect(() => {
		const diff = now - tsMs;
		let interval: number;

		if (diff < 60_000) {
			interval = 1000;
		} else if (diff < 3_600_000) {
			interval = 10_000;
		} else {
			interval = 60_000;
		}

		if (format === 'absolute') {
			return;
		}

		intervalId = setInterval(() => {
			now = Date.now();
		}, interval);

		return () => {
			if (intervalId) clearInterval(intervalId);
		};
	});
</script>

<span
	class="inline-block whitespace-nowrap font-mono tabular-nums text-[oklch(0.48_0_0)] {sizeClasses[size]} {className}"
	style="font-variant-numeric: tabular-nums;"
	title={new Date(tsMs).toISOString()}
>
	{displayText}
</span>
