// ---------------------------------------------------------------------------
// GPU capabilities store – Svelte 5 rune-based reactive state
// ---------------------------------------------------------------------------

/** Discrete GPU performance tier. */
export type GpuTier = 'low' | 'mid' | 'high' | 'ultra' | 'unsupported';

/** Rendering / compute backend. */
export type RenderBackend = 'webgpu' | 'webgl2' | 'webgl' | 'canvas2d' | 'cpu';

/** Detailed GPU capabilities detected at runtime. */
export interface GpuCapabilities {
  /** Whether WebGPU is available. */
  webgpuAvailable: boolean;
  /** Whether WebGL 2 is available. */
  webgl2Available: boolean;
  /** Whether WebGL 1 is available. */
  webglAvailable: boolean;
  /** GPU vendor string (e.g. "NVIDIA Corporation"). */
  vendor: string;
  /** GPU renderer string (e.g. "NVIDIA GeForce RTX 4090"). */
  renderer: string;
  /** Maximum texture size (pixels). */
  maxTextureSize: number;
  /** Maximum viewport dimensions. */
  maxViewportDims: [number, number];
  /** Maximum number of vertex attributes. */
  maxVertexAttribs: number;
  /** Maximum number of texture image units in fragment shader. */
  maxTextureUnits: number;
  /** Maximum render buffer size. */
  maxRenderBufferSize: number;
  /** Whether float textures are supported. */
  floatTexturesSupported: boolean;
  /** Whether instanced rendering is supported. */
  instancedRenderingSupported: boolean;
  /** Whether compute shaders are available (WebGPU). */
  computeShadersAvailable: boolean;
  /** Estimated VRAM in MB (heuristic). */
  estimatedVRAM: number;
  /** Device pixel ratio. */
  devicePixelRatio: number;
  /** Number of logical CPU cores. */
  hardwareConcurrency: number;
  /** Whether OffscreenCanvas is supported. */
  offscreenCanvasSupported: boolean;
  /** Whether SharedArrayBuffer is supported. */
  sharedArrayBufferSupported: boolean;
}

/** Recommended rendering settings based on detected capabilities. */
export interface RenderingRecommendations {
  /** Best rendering backend to use. */
  backend: RenderBackend;
  /** Recommended maximum number of data points to render. */
  maxDataPoints: number;
  /** Recommended anti-aliasing setting. */
  antiAliasing: boolean;
  /** Recommended shadow quality. */
  shadows: boolean;
  /** Recommended particle / effect count. */
  maxParticles: number;
  /** Whether to enable GPU-accelerated computations. */
  gpuCompute: boolean;
  /** Suggested resolution scale factor (0.5 - 2.0). */
  resolutionScale: number;
  /** Whether to enable smooth animations. */
  smoothAnimations: boolean;
  /** Target frame rate. */
  targetFPS: number;
}

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

function defaultCapabilities(): GpuCapabilities {
  return {
    webgpuAvailable: false,
    webgl2Available: false,
    webglAvailable: false,
    vendor: 'unknown',
    renderer: 'unknown',
    maxTextureSize: 0,
    maxViewportDims: [0, 0],
    maxVertexAttribs: 0,
    maxTextureUnits: 0,
    maxRenderBufferSize: 0,
    floatTexturesSupported: false,
    instancedRenderingSupported: false,
    computeShadersAvailable: false,
    estimatedVRAM: 0,
    devicePixelRatio: 1,
    hardwareConcurrency: 1,
    offscreenCanvasSupported: false,
    sharedArrayBufferSupported: false,
  };
}

// ---------------------------------------------------------------------------
// Detection logic
// ---------------------------------------------------------------------------

async function probeWebGPU(): Promise<boolean> {
  try {
    if (!navigator.gpu) return false;
    const adapter = await navigator.gpu.requestAdapter();
    return adapter !== null;
  } catch {
    return false;
  }
}

function probeWebGL2(): {
  available: boolean;
  vendor: string;
  renderer: string;
  maxTextureSize: number;
  maxViewportDims: [number, number];
  maxVertexAttribs: number;
  maxTextureUnits: number;
  maxRenderBufferSize: number;
  floatTextures: boolean;
  instanced: boolean;
} {
  const result = {
    available: false,
    vendor: 'unknown',
    renderer: 'unknown',
    maxTextureSize: 0,
    maxViewportDims: [0, 0] as [number, number],
    maxVertexAttribs: 0,
    maxTextureUnits: 0,
    maxRenderBufferSize: 0,
    floatTextures: false,
    instanced: true,
  };

  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl2');
    if (!gl) return result;

    result.available = true;

    const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
    if (debugInfo) {
      result.vendor = gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) || 'unknown';
      result.renderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) || 'unknown';
    }

    result.maxTextureSize = gl.getParameter(gl.MAX_TEXTURE_SIZE) || 0;
    const vp = gl.getParameter(gl.MAX_VIEWPORT_DIMS);
    result.maxViewportDims = vp ? [vp[0], vp[1]] : [0, 0];
    result.maxVertexAttribs = gl.getParameter(gl.MAX_VERTEX_ATTRIBS) || 0;
    result.maxTextureUnits = gl.getParameter(gl.MAX_TEXTURE_IMAGE_UNITS) || 0;
    result.maxRenderBufferSize = gl.getParameter(gl.MAX_RENDERBUFFER_SIZE) || 0;
    result.floatTextures = gl.getExtension('EXT_color_buffer_float') !== null;

    // Clean up
    const ext = gl.getExtension('WEBGL_lose_context');
    if (ext) ext.loseContext();
  } catch {
    // WebGL2 not available
  }

  return result;
}

function probeWebGL1(): boolean {
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl');
    if (!gl) return false;
    const ext = gl.getExtension('WEBGL_lose_context');
    if (ext) ext.loseContext();
    return true;
  } catch {
    return false;
  }
}

function classifyTier(caps: GpuCapabilities): GpuTier {
  if (!caps.webglAvailable && !caps.webgl2Available && !caps.webgpuAvailable) {
    return 'unsupported';
  }

  let score = 0;

  // WebGPU is the strongest indicator
  if (caps.webgpuAvailable) score += 40;
  if (caps.webgl2Available) score += 20;
  if (caps.floatTexturesSupported) score += 10;
  if (caps.computeShadersAvailable) score += 15;

  // Texture size scoring
  if (caps.maxTextureSize >= 16384) score += 15;
  else if (caps.maxTextureSize >= 8192) score += 10;
  else if (caps.maxTextureSize >= 4096) score += 5;

  // VRAM scoring
  if (caps.estimatedVRAM >= 8192) score += 15;
  else if (caps.estimatedVRAM >= 4096) score += 10;
  else if (caps.estimatedVRAM >= 2048) score += 5;

  // CPU cores
  if (caps.hardwareConcurrency >= 16) score += 10;
  else if (caps.hardwareConcurrency >= 8) score += 7;
  else if (caps.hardwareConcurrency >= 4) score += 4;

  // Pixel ratio (high DPI implies capable device)
  if (caps.devicePixelRatio >= 2) score += 5;

  if (score >= 80) return 'ultra';
  if (score >= 55) return 'high';
  if (score >= 30) return 'mid';
  return 'low';
}

function estimateVRAM(renderer: string): number {
  const lower = renderer.toLowerCase();
  // Rough heuristic based on known GPU names
  if (/rtx\s*40[89]0|a6000|a100/i.test(lower)) return 16384;
  if (/rtx\s*40[67]0|rtx\s*3090/i.test(lower)) return 12288;
  if (/rtx\s*30[78]0|rtx\s*40[56]0/i.test(lower)) return 8192;
  if (/rtx\s*30[56]0|rtx\s*20[78]0|rx\s*7[89]00/i.test(lower)) return 8192;
  if (/rtx\s*20[56]0|gtx\s*1[07]80|rx\s*6[78]00/i.test(lower)) return 6144;
  if (/gtx\s*1[06]60|rx\s*5[67]00/i.test(lower)) return 4096;
  if (/gtx\s*1[05]50|rx\s*5[45]0/i.test(lower)) return 2048;
  if (/apple\s*m[23]/i.test(lower)) return 8192;
  if (/apple\s*m1/i.test(lower)) return 4096;
  if (/intel\s*(iris|uhd|hd)/i.test(lower)) return 1536;
  if (/adreno|mali|powervr/i.test(lower)) return 1024;
  return 2048; // default estimate
}

function buildRecommendations(tier: GpuTier, caps: GpuCapabilities): RenderingRecommendations {
  switch (tier) {
    case 'ultra':
      return {
        backend: caps.webgpuAvailable ? 'webgpu' : 'webgl2',
        maxDataPoints: 100000,
        antiAliasing: true,
        shadows: true,
        maxParticles: 10000,
        gpuCompute: caps.computeShadersAvailable,
        resolutionScale: caps.devicePixelRatio,
        smoothAnimations: true,
        targetFPS: 120,
      };
    case 'high':
      return {
        backend: caps.webgpuAvailable ? 'webgpu' : 'webgl2',
        maxDataPoints: 50000,
        antiAliasing: true,
        shadows: true,
        maxParticles: 5000,
        gpuCompute: caps.computeShadersAvailable,
        resolutionScale: Math.min(caps.devicePixelRatio, 2),
        smoothAnimations: true,
        targetFPS: 60,
      };
    case 'mid':
      return {
        backend: caps.webgl2Available ? 'webgl2' : 'webgl',
        maxDataPoints: 20000,
        antiAliasing: true,
        shadows: false,
        maxParticles: 1000,
        gpuCompute: false,
        resolutionScale: 1,
        smoothAnimations: true,
        targetFPS: 60,
      };
    case 'low':
      return {
        backend: caps.webglAvailable ? 'webgl' : 'canvas2d',
        maxDataPoints: 5000,
        antiAliasing: false,
        shadows: false,
        maxParticles: 200,
        gpuCompute: false,
        resolutionScale: 1,
        smoothAnimations: false,
        targetFPS: 30,
      };
    case 'unsupported':
    default:
      return {
        backend: 'canvas2d',
        maxDataPoints: 2000,
        antiAliasing: false,
        shadows: false,
        maxParticles: 0,
        gpuCompute: false,
        resolutionScale: 1,
        smoothAnimations: false,
        targetFPS: 30,
      };
  }
}

// ---------------------------------------------------------------------------
// Store factory
// ---------------------------------------------------------------------------

function createGpuStore() {
  // ---- reactive state ----
  let tier = $state<GpuTier>('unsupported');
  let capabilities = $state<GpuCapabilities>(defaultCapabilities());
  let isInitialized = $state(false);
  let isDetecting = $state(false);
  let error = $state<string | null>(null);
  let recommendations = $state<RenderingRecommendations>(
    buildRecommendations('unsupported', defaultCapabilities())
  );

  // ---- derived ----

  let hasWebGPU = $derived(capabilities.webgpuAvailable);
  let hasWebGL2 = $derived(capabilities.webgl2Available);
  let hasWebGL = $derived(capabilities.webglAvailable);
  let bestBackend = $derived<RenderBackend>(recommendations.backend);
  let canUseGpuCompute = $derived(
    capabilities.webgpuAvailable && capabilities.computeShadersAvailable
  );
  let gpuDescription = $derived(
    `${capabilities.vendor} ${capabilities.renderer}`.trim() || 'Unknown GPU'
  );
  let isCapable = $derived(tier !== 'unsupported');

  // ---- actions ----

  /** Detect GPU capabilities. Should be called once during app initialization. */
  async function detectCapabilities(): Promise<void> {
    if (typeof window === 'undefined') {
      // SSR – skip detection
      isInitialized = true;
      return;
    }

    if (isDetecting) return;
    isDetecting = true;
    error = null;

    try {
      const newCaps: GpuCapabilities = { ...defaultCapabilities() };

      // Platform info
      newCaps.devicePixelRatio = window.devicePixelRatio || 1;
      newCaps.hardwareConcurrency = navigator.hardwareConcurrency || 1;
      newCaps.offscreenCanvasSupported = typeof OffscreenCanvas !== 'undefined';
      newCaps.sharedArrayBufferSupported = typeof SharedArrayBuffer !== 'undefined';

      // WebGPU
      newCaps.webgpuAvailable = await probeWebGPU();
      if (newCaps.webgpuAvailable) {
        newCaps.computeShadersAvailable = true;
      }

      // WebGL 2
      const gl2 = probeWebGL2();
      newCaps.webgl2Available = gl2.available;
      if (gl2.available) {
        newCaps.vendor = gl2.vendor;
        newCaps.renderer = gl2.renderer;
        newCaps.maxTextureSize = gl2.maxTextureSize;
        newCaps.maxViewportDims = gl2.maxViewportDims;
        newCaps.maxVertexAttribs = gl2.maxVertexAttribs;
        newCaps.maxTextureUnits = gl2.maxTextureUnits;
        newCaps.maxRenderBufferSize = gl2.maxRenderBufferSize;
        newCaps.floatTexturesSupported = gl2.floatTextures;
        newCaps.instancedRenderingSupported = gl2.instanced;
      }

      // WebGL 1 fallback
      newCaps.webglAvailable = gl2.available || probeWebGL1();

      // Estimate VRAM from renderer string
      newCaps.estimatedVRAM = estimateVRAM(newCaps.renderer);

      // Apply
      capabilities = newCaps;
      tier = classifyTier(newCaps);
      recommendations = buildRecommendations(tier, newCaps);
      isInitialized = true;
    } catch (err) {
      error = err instanceof Error ? err.message : 'GPU detection failed';
      tier = 'unsupported';
      recommendations = buildRecommendations('unsupported', capabilities);
      isInitialized = true;
    } finally {
      isDetecting = false;
    }
  }

  /** Return the best rendering backend based on detected capabilities. */
  function getBestBackend(): RenderBackend {
    if (capabilities.webgpuAvailable) return 'webgpu';
    if (capabilities.webgl2Available) return 'webgl2';
    if (capabilities.webglAvailable) return 'webgl';
    return 'canvas2d';
  }

  /** Override the tier manually (e.g. user wants to force lower quality). */
  function overrideTier(newTier: GpuTier): void {
    tier = newTier;
    recommendations = buildRecommendations(newTier, capabilities);
  }

  /** Override a specific recommendation. */
  function overrideRecommendation(
    overrides: Partial<RenderingRecommendations>
  ): void {
    recommendations = { ...recommendations, ...overrides };
  }

  /** Check if a specific backend is available. */
  function isBackendAvailable(backend: RenderBackend): boolean {
    switch (backend) {
      case 'webgpu':
        return capabilities.webgpuAvailable;
      case 'webgl2':
        return capabilities.webgl2Available;
      case 'webgl':
        return capabilities.webglAvailable;
      case 'canvas2d':
        return true; // always available in browsers
      case 'cpu':
        return true;
    }
  }

  /** Re-run detection (e.g. after a GPU driver update). */
  async function redetect(): Promise<void> {
    isInitialized = false;
    await detectCapabilities();
  }

  // ---- public API ----
  return {
    // reactive getters
    get tier() {
      return tier;
    },
    get capabilities() {
      return capabilities;
    },
    get isInitialized() {
      return isInitialized;
    },
    get isDetecting() {
      return isDetecting;
    },
    get error() {
      return error;
    },
    get recommendations() {
      return recommendations;
    },
    get hasWebGPU() {
      return hasWebGPU;
    },
    get hasWebGL2() {
      return hasWebGL2;
    },
    get hasWebGL() {
      return hasWebGL;
    },
    get bestBackend() {
      return bestBackend;
    },
    get canUseGpuCompute() {
      return canUseGpuCompute;
    },
    get gpuDescription() {
      return gpuDescription;
    },
    get isCapable() {
      return isCapable;
    },

    // actions
    detectCapabilities,
    getBestBackend,
    overrideTier,
    overrideRecommendation,
    isBackendAvailable,
    redetect,
  };
}

export const gpuStore = createGpuStore();
