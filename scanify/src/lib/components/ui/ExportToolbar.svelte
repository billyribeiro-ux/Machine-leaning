<script lang="ts">
	import { exportData, type ExportSource } from '$lib/utils/export';

	interface Props {
		source: ExportSource;
	}

	let { source }: Props = $props();

	let exporting = $state<'csv' | 'pdf' | null>(null);
	let error = $state('');

	async function handleExport(format: 'csv' | 'pdf') {
		exporting = format;
		error = '';
		try {
			await exportData(format, source);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Export failed';
		} finally {
			exporting = null;
		}
	}
</script>

<div class="flex items-center gap-1.5">
	<button
		type="button"
		onclick={() => handleExport('csv')}
		disabled={exporting !== null}
		class="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] font-medium transition-all"
		style="background: var(--bg-elevated); color: var(--text-secondary); border: 1px solid var(--border-subtle);"
		title="Download CSV"
	>
		{#if exporting === 'csv'}
			<span class="inline-block w-3 h-3 border-2 rounded-full animate-spin" style="border-color: var(--text-tertiary); border-top-color: transparent;"></span>
		{:else}
			<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
				<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
				<polyline points="14 2 14 8 20 8"/>
				<line x1="16" y1="13" x2="8" y2="13"/>
				<line x1="16" y1="17" x2="8" y2="17"/>
			</svg>
		{/if}
		CSV
	</button>

	<button
		type="button"
		onclick={() => handleExport('pdf')}
		disabled={exporting !== null}
		class="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] font-medium transition-all"
		style="background: var(--bg-elevated); color: var(--text-secondary); border: 1px solid var(--border-subtle);"
		title="Download PDF"
	>
		{#if exporting === 'pdf'}
			<span class="inline-block w-3 h-3 border-2 rounded-full animate-spin" style="border-color: var(--text-tertiary); border-top-color: transparent;"></span>
		{:else}
			<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
				<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
				<polyline points="14 2 14 8 20 8"/>
				<line x1="12" y1="18" x2="12" y2="12"/>
				<polyline points="9 15 12 18 15 15"/>
			</svg>
		{/if}
		PDF
	</button>

	{#if error}
		<span class="text-[10px] font-medium" style="color: var(--bearish);">{error}</span>
	{/if}
</div>
