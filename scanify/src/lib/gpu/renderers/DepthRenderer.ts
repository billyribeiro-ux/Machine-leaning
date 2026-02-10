// ---------------------------------------------------------------------------
// WebGPU Depth Renderer — Scanify trading scanner
//
// Renders a stacked area chart of bid/ask order book depth using WebGPU.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// WGSL shaders for order book depth visualisation
// ---------------------------------------------------------------------------

const DEPTH_WGSL = /* wgsl */ `
struct DepthUniforms {
  viewport     : vec2<f32>,
  price_range  : vec2<f32>,  // (min_price, max_price)
  max_depth    : f32,        // maximum cumulative depth for normalisation
  mid_price    : f32,        // mid price for centre line
  bid_count    : u32,
  ask_count    : u32,
};

struct DepthLevel {
  price     : f32,
  cum_size  : f32,
};

@group(0) @binding(0) var<uniform> uniforms : DepthUniforms;
@group(0) @binding(1) var<storage, read> bids : array<DepthLevel>;
@group(0) @binding(2) var<storage, read> asks : array<DepthLevel>;

struct VertexOutput {
  @builtin(position) position : vec4<f32>,
  @location(0) uv : vec2<f32>,
};

// Full-screen triangle.
@vertex
fn vs_main(@builtin(vertex_index) vid : u32) -> VertexOutput {
  var out : VertexOutput;
  let x = f32(i32(vid & 1u) * 4 - 1);
  let y = f32(i32(vid >> 1u) * 4 - 1);
  out.position = vec4<f32>(x, y, 0.0, 1.0);
  out.uv = vec2<f32>((x + 1.0) * 0.5, (1.0 - y) * 0.5);
  return out;
}

// Map a price to normalised x [0,1].
fn price_to_x(price : f32) -> f32 {
  let range = uniforms.price_range.y - uniforms.price_range.x;
  if (range <= 0.0) { return 0.5; }
  return (price - uniforms.price_range.x) / range;
}

// Sample the cumulative depth at a given UV.x by binary-searching the bid or ask array.
fn sample_bid_depth(norm_x : f32) -> f32 {
  let price = uniforms.price_range.x + norm_x * (uniforms.price_range.y - uniforms.price_range.x);
  // Bids are stored highest price first. Find the last bid >= price.
  var depth = 0.0;
  for (var i = 0u; i < uniforms.bid_count; i = i + 1u) {
    if (bids[i].price >= price) {
      depth = bids[i].cum_size;
    }
  }
  return depth / uniforms.max_depth;
}

fn sample_ask_depth(norm_x : f32) -> f32 {
  let price = uniforms.price_range.x + norm_x * (uniforms.price_range.y - uniforms.price_range.x);
  // Asks are stored lowest price first. Find the last ask <= price.
  var depth = 0.0;
  for (var i = 0u; i < uniforms.ask_count; i = i + 1u) {
    if (asks[i].price <= price) {
      depth = asks[i].cum_size;
    }
  }
  return depth / uniforms.max_depth;
}

@fragment
fn fs_main(in : VertexOutput) -> @location(0) vec4<f32> {
  let mid_x = price_to_x(uniforms.mid_price);

  // Background.
  var colour = vec3<f32>(0.06, 0.06, 0.08);

  // Centre line.
  let dist_to_mid = abs(in.uv.x - mid_x);
  if (dist_to_mid < 0.002) {
    colour = vec3<f32>(0.4, 0.4, 0.5);
  }

  // Bid side (left of mid).
  if (in.uv.x <= mid_x) {
    let depth = sample_bid_depth(in.uv.x);
    let fill_y = 1.0 - depth; // depth grows downward from the bottom
    if (in.uv.y >= fill_y) {
      let intensity = 0.3 + 0.4 * (1.0 - (in.uv.y - fill_y) / max(depth, 0.001));
      colour = vec3<f32>(0.1, intensity * 0.8, 0.2);
    }
  }

  // Ask side (right of mid).
  if (in.uv.x > mid_x) {
    let depth = sample_ask_depth(in.uv.x);
    let fill_y = 1.0 - depth;
    if (in.uv.y >= fill_y) {
      let intensity = 0.3 + 0.4 * (1.0 - (in.uv.y - fill_y) / max(depth, 0.001));
      colour = vec3<f32>(intensity * 0.8, 0.1, 0.15);
    }
  }

  return vec4<f32>(colour, 1.0);
}
`;

// ---------------------------------------------------------------------------
// Depth level data layout — must match WGSL struct DepthLevel (8 bytes).
// ---------------------------------------------------------------------------
const BYTES_PER_LEVEL = 8; // price(f32) + cum_size(f32)
const UNIFORM_SIZE = 32;   // 8 x f32/u32

/** A single price level in the order book. */
export interface DepthLevel {
  readonly price: number;
  readonly size: number;
}

/**
 * WebGPU renderer for order book depth visualisation.
 *
 * Displays a stacked area chart with bids on the left (green) and asks on
 * the right (red), centred around the current mid price.
 */
export class DepthRenderer {
  // -- GPU handles ----------------------------------------------------------
  private device: GPUDevice | null = null;
  private pipeline: GPURenderPipeline | null = null;
  private canvas: HTMLCanvasElement;
  private context: GPUCanvasContext | null = null;
  private canvasFormat: GPUTextureFormat = 'bgra8unorm';

  // -- Buffers --------------------------------------------------------------
  private uniformBuffer: GPUBuffer | null = null;
  private bidBuffer: GPUBuffer | null = null;
  private askBuffer: GPUBuffer | null = null;
  private bindGroup: GPUBindGroup | null = null;

  // -- State ----------------------------------------------------------------
  private bidCount = 0;
  private askCount = 0;
  private maxDepth = 1;
  private midPrice = 0;
  private minPrice = 0;
  private maxPrice = 1;
  private initialized = false;

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
  }

  // -----------------------------------------------------------------------
  // Lifecycle
  // -----------------------------------------------------------------------

  /**
   * Initialise the depth chart renderer.
   *
   * @param device  A live GPUDevice.
   * @returns `true` on success.
   */
  async init(device: GPUDevice): Promise<boolean> {
    try {
      this.device = device;

      const ctx = this.canvas.getContext('webgpu') as GPUCanvasContext | null;
      if (!ctx) {
        console.error('[DepthRenderer] Failed to obtain WebGPU canvas context.');
        return false;
      }
      this.context = ctx;
      this.canvasFormat = navigator.gpu.getPreferredCanvasFormat();
      this.context.configure({
        device,
        format: this.canvasFormat,
        alphaMode: 'premultiplied',
      });

      const shaderModule: GPUShaderModule = device.createShaderModule({
        label: 'depth-shader',
        code: DEPTH_WGSL,
      });

      const bgl: GPUBindGroupLayout = device.createBindGroupLayout({
        label: 'depth-bgl',
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
          {
            binding: 2,
            visibility: GPUShaderStage.FRAGMENT,
            buffer: { type: 'read-only-storage' },
          },
        ],
      });

      this.pipeline = device.createRenderPipeline({
        label: 'depth-render-pipeline',
        layout: device.createPipelineLayout({ bindGroupLayouts: [bgl] }),
        vertex: { module: shaderModule, entryPoint: 'vs_main' },
        fragment: {
          module: shaderModule,
          entryPoint: 'fs_main',
          targets: [{ format: this.canvasFormat }],
        },
        primitive: { topology: 'triangle-list' },
      });

      // Uniform buffer
      this.uniformBuffer = device.createBuffer({
        label: 'depth-uniforms',
        size: UNIFORM_SIZE,
        usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
      });

      // Initial empty buffers for bids/asks (min 8 bytes each for alignment).
      this.bidBuffer = device.createBuffer({
        label: 'depth-bids',
        size: BYTES_PER_LEVEL,
        usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
      });
      this.askBuffer = device.createBuffer({
        label: 'depth-asks',
        size: BYTES_PER_LEVEL,
        usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
      });

      this.rebuildBindGroup(bgl);
      this.initialized = true;
      return true;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error(`[DepthRenderer] init failed: ${msg}`);
      return false;
    }
  }

  // -----------------------------------------------------------------------
  // Data
  // -----------------------------------------------------------------------

  /**
   * Upload new order book depth data.
   *
   * @param bids  Bid levels sorted by price descending (highest first).
   * @param asks  Ask levels sorted by price ascending (lowest first).
   */
  setDepthData(bids: readonly DepthLevel[], asks: readonly DepthLevel[]): void {
    if (!this.device || !this.pipeline) return;

    // Compute cumulative sizes.
    const bidData = new Float32Array(bids.length * 2);
    let cumBid = 0;
    for (let i = 0; i < bids.length; i++) {
      const bid = bids[i]!;
      cumBid += bid.size;
      bidData[i * 2] = bid.price;
      bidData[i * 2 + 1] = cumBid;
    }

    const askData = new Float32Array(asks.length * 2);
    let cumAsk = 0;
    for (let i = 0; i < asks.length; i++) {
      const ask = asks[i]!;
      cumAsk += ask.size;
      askData[i * 2] = ask.price;
      askData[i * 2 + 1] = cumAsk;
    }

    this.bidCount = bids.length;
    this.askCount = asks.length;
    this.maxDepth = Math.max(cumBid, cumAsk, 1);

    // Price range.
    const bidHighest = bids.length > 0 ? bids[0]!.price : 0;
    const bidLowest = bids.length > 0 ? bids[bids.length - 1]!.price : 0;
    const askLowest = asks.length > 0 ? asks[0]!.price : 0;
    const askHighest = asks.length > 0 ? asks[asks.length - 1]!.price : 0;

    this.minPrice = Math.min(bidLowest, askLowest);
    this.maxPrice = Math.max(bidHighest, askHighest);
    this.midPrice = (bidHighest + askLowest) / 2;

    // Recreate buffers if needed.
    const bidSize = Math.max(bidData.byteLength, BYTES_PER_LEVEL);
    const askSize = Math.max(askData.byteLength, BYTES_PER_LEVEL);

    const needsRebuild =
      !this.bidBuffer ||
      !this.askBuffer ||
      this.bidBuffer.size < bidSize ||
      this.askBuffer.size < askSize;

    if (needsRebuild) {
      this.bidBuffer?.destroy();
      this.askBuffer?.destroy();
      this.bidBuffer = this.device.createBuffer({
        label: 'depth-bids',
        size: bidSize,
        usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
      });
      this.askBuffer = this.device.createBuffer({
        label: 'depth-asks',
        size: askSize,
        usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
      });
      this.rebuildBindGroup(this.pipeline.getBindGroupLayout(0));
    }

    if (bidData.byteLength > 0) {
      this.device.queue.writeBuffer(this.bidBuffer!, 0, bidData);
    }
    if (askData.byteLength > 0) {
      this.device.queue.writeBuffer(this.askBuffer!, 0, askData);
    }
  }

  // -----------------------------------------------------------------------
  // Rendering
  // -----------------------------------------------------------------------

  /**
   * Encode and submit a render pass.
   */
  render(): void {
    if (
      !this.device ||
      !this.pipeline ||
      !this.context ||
      !this.bindGroup ||
      !this.uniformBuffer
    ) {
      return;
    }

    // Write uniforms.
    const ub = new ArrayBuffer(UNIFORM_SIZE);
    const f = new Float32Array(ub);
    const u = new Uint32Array(ub);
    f[0] = this.canvas.width;
    f[1] = this.canvas.height;
    f[2] = this.minPrice;
    f[3] = this.maxPrice;
    f[4] = this.maxDepth;
    f[5] = this.midPrice;
    u[6] = this.bidCount;
    u[7] = this.askCount;
    this.device.queue.writeBuffer(this.uniformBuffer, 0, ub);

    const textureView: GPUTextureView = this.context.getCurrentTexture().createView();
    const encoder: GPUCommandEncoder = this.device.createCommandEncoder({
      label: 'depth-encoder',
    });

    const pass: GPURenderPassEncoder = encoder.beginRenderPass({
      colorAttachments: [
        {
          view: textureView,
          clearValue: { r: 0.04, g: 0.04, b: 0.06, a: 1.0 },
          loadOp: 'clear',
          storeOp: 'store',
        },
      ],
    });

    pass.setPipeline(this.pipeline);
    pass.setBindGroup(0, this.bindGroup);
    pass.draw(3, 1, 0, 0);
    pass.end();

    this.device.queue.submit([encoder.finish()]);
  }

  /**
   * Handle canvas resize.
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
   * Destroy all GPU resources.
   */
  destroy(): void {
    this.uniformBuffer?.destroy();
    this.bidBuffer?.destroy();
    this.askBuffer?.destroy();
    this.uniformBuffer = null;
    this.bidBuffer = null;
    this.askBuffer = null;
    this.bindGroup = null;
    this.pipeline = null;
    this.context = null;
    this.device = null;
    this.initialized = false;
  }

  // -----------------------------------------------------------------------
  // Internal
  // -----------------------------------------------------------------------

  private rebuildBindGroup(layout: GPUBindGroupLayout): void {
    if (!this.device || !this.uniformBuffer || !this.bidBuffer || !this.askBuffer) return;
    this.bindGroup = this.device.createBindGroup({
      label: 'depth-bg',
      layout,
      entries: [
        { binding: 0, resource: { buffer: this.uniformBuffer } },
        { binding: 1, resource: { buffer: this.bidBuffer } },
        { binding: 2, resource: { buffer: this.askBuffer } },
      ],
    });
  }
}
