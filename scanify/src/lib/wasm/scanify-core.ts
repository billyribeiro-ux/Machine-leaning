let wasmReady = false;
let wasmModule: unknown = null;

export async function initWasm(): Promise<boolean> {
	try {
		// In production, this would load the WASM binary:
		// const module = await import('./scanify_core_bg.wasm');
		// wasmModule = module;
		// wasmReady = true;
		// For now, we fall back to JS implementations
		return false;
	} catch {
		wasmReady = false;
		return false;
	}
}

export function isReady(): boolean {
	return wasmReady;
}

export function getModule(): unknown {
	return wasmModule;
}
