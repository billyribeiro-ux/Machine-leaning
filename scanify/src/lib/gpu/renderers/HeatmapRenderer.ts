// ---------------------------------------------------------------------------
// WebGPU Heatmap Renderer — Scanify trading scanner
//
// Full WebGPU render pipeline for colour-mapped heatmap display.
// Uses the WGSL shaders defined in ../shaders/heatmap.wgsl.
// ---------------------------------------------------------------------------

import type { GPUCapabilities } from '$types/gpu';

// Inline the heatmap WGSL source so the renderer is self-contained at runtime.
// This mirrors the shader already in ../shaders/heatmap.wgsl.
const HEATMAP_WGSL = /* wgsl */ `
struct HeatmapUniforms {
  grid_size   : vec2<f32>,
  value_range : vec2<f32>,
  viewport    : vec2<f32>,
  color_mode  : f32,
  _pad        : f32,
};

@group(0) @binding(0) var<uniform> uniforms : HeatmapUniforms;
@group(0) @binding(1) var<storage, read> values : array<f32>;

struct VertexOutput {
  @builtin(position) position : vec4<f32>,
  @location(0) uv : vec2<f32>,
};

@vertex
fn vs_main(@builtin(vertex_index) vertex_index : u32) -> VertexOutput {
  var out : VertexOutput;
  let x = f32(i32(vertex_index & 1u) * 4 - 1);
  let y = f32(i32(vertex_index >> 1u) * 4 - 1);
  out.position = vec4<f32>(x, y, 0.0, 1.0);
  out.uv = vec2<f32>((x + 1.0) * 0.5, (1.0 - y) * 0.5);
  return out;
}

fn colour_blue_red(t : f32) -> vec3<f32> {
  let blue = vec3<f32>(0.230, 0.299, 0.754);
  let mid  = vec3<f32>(0.085, 0.085, 0.105);
  let red  = vec3<f32>(0.706, 0.016, 0.150);
  if (t < 0.5) { return mix(blue, mid, t * 2.0); }
  return mix(mid, red, (t - 0.5) * 2.0);
}

fn colour_red_green(t : f32) -> vec3<f32> {
  let red   = vec3<f32>(0.800, 0.100, 0.100);
  let mid   = vec3<f32>(0.120, 0.120, 0.140);
  let green = vec3<f32>(0.100, 0.700, 0.250);
  if (t < 0.5) { return mix(red, mid, t * 2.0); }
  return mix(mid, green, (t - 0.5) * 2.0);
}

@fragment
fn fs_main(in : VertexOutput) -> @location(0) vec4<f32> {
  let cols = u32(uniforms.grid_size.x);
  let rows = u32(uniforms.grid_size.y);
  let col  = min(u32(floor(in.uv.x * f32(cols))), cols - 1u);
  let row  = min(u32(floor(in.uv.y * f32(rows))), rows - 1u);
  let idx  = row * cols + col;
  let raw  = values[idx];

  let lo    = uniforms.value_range.x;
  let hi    = uniforms.value_range.y;
  let range = hi - lo;
  var t : f32 = 0.5;
  if (range > 0.0) { t = clamp((raw - lo) / range, 0.0, 1.0); }

  var colour : vec3<f32>;
  if (uniforms.color_mode < 0.5) { colour = colour_blue_red(t); }
  else { colour = colour_red_green(t); }

  let cell_uv = fract(in.uv * uniforms.grid_size);
  let edge = smoothstep(0.0, 0.04, min(cell_uv.x, cell_uv.y))
           * smoothstep(0.0, 0.04, min(1.0 - cell_uv.x, 1.0 - cell_uv.y));
  colour *= mix(0.6, 1.0, edge);

  return vec4<f32>(colour, 1.0);
}
`;

// ---------------------------------------------------------------------------
// Uniform layout  (8 x f32 = 32 bytes, 16-byte aligned)
// ---------------------------------------------------------------------------
//   [0..1]  grid_size   (cols, rows)
//   [2..3]  value_range (min, max)
//   [4..5]  viewport    (width, height)
//   [6]     color_mode  (0 = blue-red, 1 = red-green)
//   [7]     _pad
const UNIFORM_BUFFER_SIZE = 32; // bytes

/**
 * Colour mapping mode.
 *
 * - `'blue-red'`  — diverging blue (low) to red (high).
 * - `'red-green'` — diverging red (bearish) to green (bullish).
 */
export type HeatmapColorMode = 'blue-red' | 'red-green';

/**
 * WebGPU-backed renderer that displays a 2-D grid of scalar values as a
 * colour-mapped heatmap.  Designed for market sector heat maps, correlation
 * matrices, and similar dense data displays.
 */
export class HeatmapRenderer {
  // -- GPU handles ----------------------------------------------------------
  private device: GPUDevice | null = null;
  private pipeline: GPURenderPipeline | null = null;
  private canvas: HTMLCanvasElement;
  private context: GPUCanvasContext | null = null;
  private canvasFormat: GPUTextureFormat = 'bgra8unorm';

  // -- Buffers --------------------------------------------------------------
  private dataBuffer: GPUBuffer | null = null;
  private uniformBuffer: GPUBuffer | null = null;
  private bindGroup: GPUBindGroup | null = null;

  // -- State ----------------------------------------------------------------
  private gridWidth = 0;
  private gridHeight = 0;
  private colorMode: HeatmapColorMode = 'red-green';
  private minValue = 0;
  private maxValue = 1;
  private initialized = false;

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
  }

  // -----------------------------------------------------------------------
  // Lifecycle
  // -----------------------------------------------------------------------

  /**
   * Initialise the WebGPU pipeline, buffers, and canvas context.
   *
   * @param device  A live GPUDevice obtained from {@link GPUContext}.
   * @returns `true` when initialisation succeeds.
   */
  async init(device: GPUDevice): Promise<boolean> {
    try {
      this.device = device;

      // Canvas context -------------------------------------------------------
      const ctx = this.canvas.getContext('webgpu') as GPUCanvasContext | null;
      if (!ctx) {
        console.error('[HeatmapRenderer] Failed to obtain WebGPU canvas context.');
        return false;
      }
      this.context = ctx;
      this.canvasFormat = navigator.gpu.getPreferredCanvasFormat();
      this.context.configure({
        device: this.device,
        format: this.canvasFormat,
        alphaMode: 'premultiplied',
      });

      // Shader module --------------------------------------------------------
      const shaderModule: GPUShaderModule = device.createShaderModule({
        label: 'heatmap-shader',
        code: HEATMAP_WGSL,
      });

      // Bind group layout ----------------------------------------------------
      const bindGroupLayout: GPUBindGroupLayout = device.createBindGroupLayout({
        label: 'heatmap-bind-group-layout',
        entries: [
          {
            binding: 0,
            visibility: GPUShaderStage.VERTEX | GPUShaderStage.FRAGMENT,
            buffer: { type: 'uniform' },
          },
          {
            binding: 1,
            visibility: GPUShaderStage.FRAGMENT,
            buffer: { type: 'read-only-storage' },
          },
        ],
      });

      // Pipeline layout ------------------------------------------------------
      const pipelineLayout: GPUPipelineLayout = device.createPipelineLayout({
        label: 'heatmap-pipeline-layout',
        bindGroupLayouts: [bindGroupLayout],
      });

      // Render pipeline ------------------------------------------------------
      this.pipeline = device.createRenderPipeline({
        label: 'heatmap-render-pipeline',
        layout: pipelineLayout,
        vertex: {
          module: shaderModule,
          entryPoint: 'vs_main',
        },
        fragment: {
          module: shaderModule,
          entryPoint: 'fs_main',
          targets: [{ format: this.canvasFormat }],
        },
        primitive: {
          topology: 'triangle-list',
        },
      });

      // Uniform buffer -------------------------------------------------------
      this.uniformBuffer = device.createBuffer({
        label: 'heatmap-uniform-buffer',
        size: UNIFORM_BUFFER_SIZE,
        usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
      });

      // Initial (empty) data buffer — 4 bytes minimum -----------------------
      this.dataBuffer = device.createBuffer({
        label: 'heatmap-data-buffer',
        size: 4,
        usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
      });

      // Bind group -----------------------------------------------------------
      this.bindGroup = device.createBindGroup({
        label: 'heatmap-bind-group',
        layout: bindGroupLayout,
        entries: [
          { binding: 0, resource: { buffer: this.uniformBuffer } },
          { binding: 1, resource: { buffer: this.dataBuffer } },
        ],
      });

      this.initialized = true;
      return true;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error(`[HeatmapRenderer] init failed: ${msg}`);
      return false;
    }
  }

  // -----------------------------------------------------------------------
  // Data
  // -----------------------------------------------------------------------

  /**
   * Upload a new grid of scalar values to the GPU.
   *
   * @param values  Row-major flat array of `width * height` floats.
   * @param width   Number of columns.
   * @param height  Number of rows.
   */
  setData(values: Float32Array, width: number, height: number): void {
    if (!this.device || !this.initialized) return;

    this.gridWidth = width;
    this.gridHeight = height;

    // Compute value range for normalisation.
    let min = Infinity;
    let max = -Infinity;
    for (let i = 0; i < values.length; i++) {
      const v = values[i]!;
      if (v < min) min = v;
      if (v > max) max = v;
    }
    this.minValue = Number.isFinite(min) ? min : 0;
    this.maxValue = Number.isFinite(max) ? max : 1;

    // Recreate the storage buffer if the size changed.
    const requiredSize = values.byteLength || 4;
    if (!this.dataBuffer || this.dataBuffer.size < requiredSize) {
      this.dataBuffer?.destroy();
      this.dataBuffer = this.device.createBuffer({
        label: 'heatmap-data-buffer',
        size: requiredSize,
        usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
      });
      this.rebuildBindGroup();
    }

    this.device.queue.writeBuffer(this.dataBuffer!, 0, values);
  }

  /**
   * Set the colour mapping mode.
   */
  setColorMode(mode: HeatmapColorMode): void {
    this.colorMode = mode;
  }

  // -----------------------------------------------------------------------
  // Rendering
  // -----------------------------------------------------------------------

  /**
   * Encode and submit a render pass that draws the heatmap.
   */
  render(): void {
    if (!this.device || !this.pipeline || !this.context || !this.bindGroup || !this.uniformBuffer) {
      return;
    }

    // Write current uniforms ------------------------------------------------
    const uniforms = new Float32Array(8);
    uniforms[0] = this.gridWidth;
    uniforms[1] = this.gridHeight;
    uniforms[2] = this.minValue;
    uniforms[3] = this.maxValue;
    uniforms[4] = this.canvas.width;
    uniforms[5] = this.canvas.height;
    uniforms[6] = this.colorMode === 'red-green' ? 1.0 : 0.0;
    uniforms[7] = 0.0; // pad
    this.device.queue.writeBuffer(this.uniformBuffer, 0, uniforms);

    // Render pass -----------------------------------------------------------
    const textureView: GPUTextureView = this.context.getCurrentTexture().createView();

    const encoder: GPUCommandEncoder = this.device.createCommandEncoder({
      label: 'heatmap-command-encoder',
    });

    const passDescriptor: GPURenderPassDescriptor = {
      colorAttachments: [
        {
          view: textureView,
          clearValue: { r: 0.05, g: 0.05, b: 0.07, a: 1.0 },
          loadOp: 'clear',
          storeOp: 'store',
        },
      ],
    };

    const pass: GPURenderPassEncoder = encoder.beginRenderPass(passDescriptor);
    pass.setPipeline(this.pipeline);
    pass.setBindGroup(0, this.bindGroup);
    pass.draw(3, 1, 0, 0); // full-screen triangle
    pass.end();

    this.device.queue.submit([encoder.finish()]);
  }

  // -----------------------------------------------------------------------
  // Resize
  // -----------------------------------------------------------------------

  /**
   * Handle canvas resize.  Reconfigures the canvas context so the next
   * render pass uses the correct dimensions.
   */
  resize(width: number, height: number): void {
    this.canvas.width = width;
    this.canvas.height = height;

    if (this.context && this.device) {
      this.context.configure({
        device: this.device,
        format: this.canvasFormat,
        alphaMode: 'premultiplied',
      });
    }
  }

  // -----------------------------------------------------------------------
  // Cleanup
  // -----------------------------------------------------------------------

  /**
   * Destroy all GPU resources held by this renderer.
   */
  destroy(): void {
    this.dataBuffer?.destroy();
    this.uniformBuffer?.destroy();
    this.dataBuffer = null;
    this.uniformBuffer = null;
    this.bindGroup = null;
    this.pipeline = null;
    this.context = null;
    this.device = null;
    this.initialized = false;
  }

  // -----------------------------------------------------------------------
  // Internal
  // -----------------------------------------------------------------------

  /** Rebuild the bind group after a buffer is recreated. */
  private rebuildBindGroup(): void {
    if (!this.device || !this.pipeline || !this.uniformBuffer || !this.dataBuffer) return;

    this.bindGroup = this.device.createBindGroup({
      label: 'heatmap-bind-group',
      layout: this.pipeline.getBindGroupLayout(0),
      entries: [
        { binding: 0, resource: { buffer: this.uniformBuffer } },
        { binding: 1, resource: { buffer: this.dataBuffer } },
      ],
    });
  }
}
