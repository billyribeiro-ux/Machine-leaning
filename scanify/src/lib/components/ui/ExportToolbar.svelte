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

<div class="export-toolbar">
	<button
		type="button"
		onclick={() => handleExport('csv')}
		disabled={exporting !== null}
		class="export-btn"
		title="Download CSV"
	>
		{#if exporting === 'csv'}
			<span class="export-spinner"></span>
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
		class="export-btn"
		title="Download PDF"
	>
		{#if exporting === 'pdf'}
			<span class="export-spinner"></span>
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
		<span class="export-error">{error}</span>
	{/if}
</div>

<style>
	.export-toolbar {
		display: flex;
		align-items: center;
		gap: 6px;
	}

	.export-btn {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		border-radius: var(--radius-md);
		padding-inline: 10px;
		padding-block: 6px;
		font-size: 11px;
		font-weight: 500;
		transition: all 150ms;
		background-color: var(--bg-elevated);
		color: var(--text-secondary);
		border: 1px solid var(--border-subtle);
	}

	.export-btn:hover:not(:disabled) {
		background-color: var(--bg-overlay);
		color: var(--text-primary);
	}

	.export-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.export-spinner {
		display: inline-block;
		width: 12px;
		height: 12px;
		border: 2px solid var(--text-tertiary);
		border-top-color: transparent;
		border-radius: var(--radius-full);
		animation: spin 1s linear infinite;
	}

	.export-error {
		font-size: 10px;
		font-weight: 500;
		color: var(--bearish);
	}

	@keyframes spin {
		from { transform: rotate(0deg); }
		to { transform: rotate(360deg); }
	}
</style>
