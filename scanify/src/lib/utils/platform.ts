/**
 * Platform detection and Tauri bridge utilities.
 *
 * When the app runs inside Tauri (desktop) the `@tauri-apps/api` module is
 * available at runtime.  In the browser it is not.  Every call site should
 * use these helpers instead of importing Tauri APIs directly — they return
 * no-ops / graceful fallbacks when running in a normal browser.
 */

/** True when running inside a Tauri desktop shell. */
export const isTauri: boolean =
	typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;

/** Send a native desktop notification (no-op in browser). */
export async function sendNotification(title: string, body: string): Promise<void> {
	if (!isTauri) return;
	try {
		const { invoke } = await import('@tauri-apps/api/core');
		await invoke('send_notification', { title, body });
	} catch {
		// Tauri API unavailable — swallow silently.
	}
}

/** Retrieve OS / arch / app-version from the Rust backend. */
export async function getSystemInfo(): Promise<{
	os: string;
	arch: string;
	version: string;
} | null> {
	if (!isTauri) return null;
	try {
		const { invoke } = await import('@tauri-apps/api/core');
		return await invoke('get_system_info');
	} catch {
		return null;
	}
}

/**
 * Listen for scanner-control events emitted by the system-tray menu.
 * Returns a cleanup function to unlisten.
 */
export async function onScannerControl(
	callback: (action: 'start' | 'stop') => void
): Promise<() => void> {
	if (!isTauri) return () => {};
	try {
		const { listen } = await import('@tauri-apps/api/event');
		const unlisten = await listen<string>('scanner-control', (event) => {
			callback(event.payload as 'start' | 'stop');
		});
		return unlisten;
	} catch {
		return () => {};
	}
}
