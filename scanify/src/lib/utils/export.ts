export type ExportFormat = 'csv' | 'json' | 'pdf';

export type ExportSource =
	| 'scanner'
	| 'options-flow'
	| 'institutional'
	| 'market'
	| 'dashboard'
	| 'alerts';

export async function exportData(
	format: ExportFormat,
	source: ExportSource
): Promise<void> {
	const token =
		typeof localStorage !== 'undefined'
			? localStorage.getItem('scanify_token')
			: null;
	const params = new URLSearchParams({ format, source });
	const url = `/api/signals/export?${params.toString()}`;

	const res = await fetch(url, {
		method: 'POST',
		headers: token ? { Authorization: `Bearer ${token}` } : {},
	});

	if (!res.ok) throw new Error(`Export failed: ${res.status}`);

	const disposition = res.headers.get('Content-Disposition') ?? '';
	const match = disposition.match(/filename="?([^"]+)"?/);
	const filename = match?.[1] ?? `scanify_${source}.${format}`;

	const blob = await res.blob();
	const a = document.createElement('a');
	a.href = URL.createObjectURL(blob);
	a.download = filename;
	a.click();
	URL.revokeObjectURL(a.href);
}
