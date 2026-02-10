// ---------------------------------------------------------------------------
// WASM core module loader — Scanify trading scanner
//
// Manages the lifecycle of the optional WebAssembly module.  When the WASM
// binary is not available (development, unsupported browser, network error),
// all callers should fall back to the pure-JS implementations in
// ./indicators.ts.
// ---------------------------------------------------------------------------

let wasmReady = false;
let wasmModule: unknown = null;
let initPromise: Promise<boolean> | null = null;

/**
 * Attempt to load and instantiate the Scanify WASM module.
 *
 * This function is idempotent: calling it multiple times returns the same
 * promise until a reset is performed.
 *
 * @returns `true` when the WASM module was loaded successfully,
 *          `false` when it is unavailable (the caller should use JS fallbacks).
 */
export async function initWasm(): Promise<boolean> {
  // Return the in-flight or cached result if already started.
  if (initPromise !== null) return initPromise;

  initPromise = (async (): Promise<boolean> => {
    try {
      // Guard: WebAssembly must be supported.
      if (typeof WebAssembly === 'undefined') {
        console.warn('[scanify-core] WebAssembly is not supported in this environment.');
        return false;
      }

      // In production the WASM binary would be fetched from a CDN or bundled
      // asset path.  During development we return false so the pure-JS
      // indicator fallbacks are used.
      //
      // To enable WASM in production, uncomment the block below and adjust the
      // path to the compiled `.wasm` binary:
      //
      // const wasmUrl = new URL('./scanify_core_bg.wasm', import.meta.url);
      // const response = await fetch(wasmUrl);
      // if (!response.ok) {
      //   console.warn(`[scanify-core] WASM fetch failed: ${response.status}`);
      //   return false;
      // }
      // const bytes = await response.arrayBuffer();
      // const { instance } = await WebAssembly.instantiate(bytes, {});
      // wasmModule = instance.exports;
      // wasmReady = true;
      // console.info('[scanify-core] WASM module loaded successfully.');
      // return true;

      return false;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.warn(`[scanify-core] Failed to initialise WASM: ${msg}`);
      wasmReady = false;
      wasmModule = null;
      return false;
    }
  })();

  return initPromise;
}

/**
 * Whether the WASM module has been loaded and is ready for use.
 */
export function isReady(): boolean {
  return wasmReady;
}

/**
 * Return the raw WASM module exports, or `null` if not loaded.
 *
 * Callers should use {@link isReady} or the typed wrappers in
 * `./indicators.ts` rather than accessing the module directly.
 */
export function getModule(): unknown {
  return wasmModule;
}

/**
 * Tear down the WASM module and allow re-initialisation.
 *
 * Primarily useful for testing and hot-reload scenarios.
 */
export function resetWasm(): void {
  wasmReady = false;
  wasmModule = null;
  initPromise = null;
}
