// ---------------------------------------------------------------------------
// GPU capability types for the Scanify trading scanner
// ---------------------------------------------------------------------------

/**
 * Tiered classification of the client's GPU / rendering support.
 *
 *   - `'webgpu'`  - Full WebGPU support (best performance).
 *   - `'webgl2'`  - WebGL 2 fallback.
 *   - `'canvas'`  - 2-D canvas only.
 *   - `'none'`    - No usable GPU rendering path detected.
 */
export type GPUTier = 'webgpu' | 'webgl2' | 'canvas' | 'none';

/**
 * Rendering backend actually in use at runtime.
 *
 * This is a strict subset of {@link GPUTier} that excludes `'none'` because
 * if we have no backend we cannot render at all.
 */
export type RenderBackend = 'webgpu' | 'webgl2' | 'canvas';

// ---------------------------------------------------------------------------
// Capabilities
// ---------------------------------------------------------------------------

/** Detected GPU capabilities used to choose rendering strategies. */
export interface GPUCapabilities {
  /** Highest supported rendering tier. */
  readonly tier: GPUTier;
  /** Maximum texture dimension the GPU supports (px). */
  readonly maxTextureSize: number;
  /** Maximum buffer size the GPU supports (bytes). */
  readonly maxBufferSize: number;
  /** Whether compute shaders are available (WebGPU only). */
  readonly supportsCompute: boolean;
  /** Whether 32-bit float textures / buffers are supported. */
  readonly supportsFloat32: boolean;
  /** Human-readable GPU device name (e.g. "NVIDIA GeForce RTX 4090"). */
  readonly deviceName: string;
  /** GPU vendor name (e.g. "NVIDIA", "AMD", "Apple"). */
  readonly vendorName: string;
}
