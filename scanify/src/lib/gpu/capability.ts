// ---------------------------------------------------------------------------
// GPU capability detection for the Scanify trading scanner
// ---------------------------------------------------------------------------

import type { GPUCapabilities, GPUTier } from '../types/gpu';

/** Default capabilities returned when no GPU support is detected. */
const NO_GPU_CAPABILITIES: GPUCapabilities = {
  tier: 'none',
  maxTextureSize: 0,
  maxBufferSize: 0,
  supportsCompute: false,
  supportsFloat32: false,
  deviceName: 'none',
  vendorName: 'unknown',
} as const;

/**
 * Attempt to detect WebGPU capabilities.
 * Returns `null` when WebGPU is not available.
 */
async function probeWebGPU(): Promise<GPUCapabilities | null> {
  if (typeof navigator === 'undefined' || !('gpu' in navigator)) {
    return null;
  }

  try {
    const gpu = navigator.gpu as GPU;
    const adapter: GPUAdapter | null = await gpu.requestAdapter({
      powerPreference: 'high-performance',
    });

    if (!adapter) {
      return null;
    }

    const adapterInfo: GPUAdapterInfo = await adapter.requestAdapterInfo();
    const device: GPUDevice = await adapter.requestDevice({
      requiredLimits: {},
    });

    const limits: GPUSupportedLimits = device.limits;

    const capabilities: GPUCapabilities = {
      tier: 'webgpu' as GPUTier,
      maxTextureSize: limits.maxTextureDimension2D ?? 8192,
      maxBufferSize: Number(limits.maxBufferSize ?? 268435456),
      supportsCompute: true,
      supportsFloat32: true,
      deviceName: adapterInfo.device || 'WebGPU Device',
      vendorName: adapterInfo.vendor || 'unknown',
    };

    device.destroy();
    return capabilities;
  } catch {
    return null;
  }
}

/**
 * Attempt to detect WebGL2 capabilities.
 * Returns `null` when WebGL2 is not available.
 */
function probeWebGL2(): GPUCapabilities | null {
  if (typeof document === 'undefined') {
    return null;
  }

  try {
    const canvas: HTMLCanvasElement = document.createElement('canvas');
    const gl: WebGL2RenderingContext | null = canvas.getContext('webgl2');

    if (!gl) {
      return null;
    }

    const maxTextureSize: number = gl.getParameter(gl.MAX_TEXTURE_SIZE) as number;
    const debugInfo: WEBGL_debug_renderer_info | null = gl.getExtension(
      'WEBGL_debug_renderer_info',
    );

    const deviceName: string = debugInfo
      ? (gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) as string)
      : 'WebGL2 Device';

    const vendorName: string = debugInfo
      ? (gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) as string)
      : 'unknown';

    const supportsFloat32: boolean =
      gl.getExtension('EXT_color_buffer_float') !== null;

    const capabilities: GPUCapabilities = {
      tier: 'webgl2' as GPUTier,
      maxTextureSize,
      maxBufferSize: maxTextureSize * maxTextureSize * 4, // rough estimate
      supportsCompute: false,
      supportsFloat32,
      deviceName,
      vendorName,
    };

    // Clean up the probing context.
    const loseCtx: WEBGL_lose_context | null =
      gl.getExtension('WEBGL_lose_context');
    loseCtx?.loseContext();

    return capabilities;
  } catch {
    return null;
  }
}

/**
 * Attempt to detect basic Canvas 2D support.
 * Returns `null` when Canvas is not available.
 */
function probeCanvas(): GPUCapabilities | null {
  if (typeof document === 'undefined') {
    return null;
  }

  try {
    const canvas: HTMLCanvasElement = document.createElement('canvas');
    const ctx: CanvasRenderingContext2D | null = canvas.getContext('2d');

    if (!ctx) {
      return null;
    }

    return {
      tier: 'canvas' as GPUTier,
      maxTextureSize: 4096,
      maxBufferSize: 0,
      supportsCompute: false,
      supportsFloat32: false,
      deviceName: 'Canvas 2D',
      vendorName: 'browser',
    };
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Detect the best available GPU capabilities on the current device.
 *
 * Probes in order of preference:
 *   1. WebGPU
 *   2. WebGL 2
 *   3. Canvas 2D
 *   4. None
 */
export async function detectGPUCapabilities(): Promise<GPUCapabilities> {
  // 1. Try WebGPU first (async — needs adapter negotiation).
  const webgpu: GPUCapabilities | null = await probeWebGPU();
  if (webgpu) {
    return webgpu;
  }

  // 2. Fall back to WebGL 2.
  const webgl2: GPUCapabilities | null = probeWebGL2();
  if (webgl2) {
    return webgl2;
  }

  // 3. Fall back to Canvas 2D.
  const canvas: GPUCapabilities | null = probeCanvas();
  if (canvas) {
    return canvas;
  }

  // 4. Nothing usable.
  return NO_GPU_CAPABILITIES;
}
