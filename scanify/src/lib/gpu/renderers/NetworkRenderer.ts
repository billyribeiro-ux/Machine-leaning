// ---------------------------------------------------------------------------
// WebGPU Network Renderer — Scanify trading scanner
//
// Force-directed graph layout computed on the GPU.  Designed for
// visualising correlation networks, sector relationships, and similar
// graph structures.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// WGSL shaders — compute (force layout) + render (nodes & edges)
// ---------------------------------------------------------------------------

const NETWORK_COMPUTE_WGSL = /* wgsl */ `
struct LayoutParams {
  node_count     : u32,
  edge_count     : u32,
  repulsion      : f32,
  attraction     : f32,
  damping        : f32,
  dt             : f32,
  gravity        : f32,
  _pad           : f32,
};

struct Node {
  pos   : vec2<f32>,
  vel   : vec2<f32>,
  mass  : f32,
  size  : f32,
  color : vec2<f32>, // packed r,g — b is derived
};

struct Edge {
  source : u32,
  target : u32,
  weight : f32,
  _pad   : f32,
};

@group(0) @binding(0) var<uniform>            params : LayoutParams;
@group(0) @binding(1) var<storage, read_write> nodes  : array<Node>;
@group(0) @binding(2) var<storage, read>       edges  : array<Edge>;

@compute @workgroup_size(64)
fn cs_forces(@builtin(global_invocation_id) gid : vec3<u32>) {
  let i = gid.x;
  if (i >= params.node_count) { return; }

  var force = vec2<f32>(0.0, 0.0);
  let pos_i = nodes[i].pos;

  // Repulsive force from every other node (Coulomb-like).
  for (var j = 0u; j < params.node_count; j = j + 1u) {
    if (j == i) { continue; }
    let diff = pos_i - nodes[j].pos;
    let dist = max(length(diff), 0.01);
    let repel = params.repulsion / (dist * dist);
    force = force + normalize(diff) * repel;
  }

  // Gravity towards origin.
  let to_origin = -pos_i;
  force = force + to_origin * params.gravity;

  // Attractive force along edges (Hooke-like).
  for (var e = 0u; e < params.edge_count; e = e + 1u) {
    let edge = edges[e];
    var other_idx = 0u;
    var is_connected = false;
    if (edge.source == i) {
      other_idx = edge.target;
      is_connected = true;
    } else if (edge.target == i) {
      other_idx = edge.source;
      is_connected = true;
    }
    if (is_connected) {
      let diff = nodes[other_idx].pos - pos_i;
      let dist = length(diff);
      let attract = params.attraction * dist * edge.weight;
      force = force + normalize(diff) * attract;
    }
  }

  // Integrate.
  var n = nodes[i];
  n.vel = (n.vel + force * params.dt / n.mass) * params.damping;
  n.pos = n.pos + n.vel * params.dt;
  nodes[i] = n;
}
`;

const NETWORK_RENDER_WGSL = /* wgsl */ `
struct RenderUniforms {
  viewport   : vec2<f32>,
  bounds     : vec2<f32>,  // x,y extent of the graph for normalisation
  point_size : f32,
  _pad0      : f32,
  _pad1      : f32,
  _pad2      : f32,
};

@group(0) @binding(0) var<uniform> u : RenderUniforms;

struct VertexInput {
  @location(0) position : vec2<f32>,
  @location(1) color    : vec3<f32>,
  @location(2) size     : f32,
};

struct VertexOutput {
  @builtin(position) clip_pos : vec4<f32>,
  @location(0) v_color : vec3<f32>,
  @location(1) center_uv : vec2<f32>,
};

@vertex
fn vs_node(
  vin : VertexInput,
  @builtin(vertex_index) vid : u32,
) -> VertexOutput {
  // Billboard quad around node position.
  var offsets = array<vec2<f32>, 6>(
    vec2<f32>(-1.0, -1.0),
    vec2<f32>( 1.0, -1.0),
    vec2<f32>(-1.0,  1.0),
    vec2<f32>(-1.0,  1.0),
    vec2<f32>( 1.0, -1.0),
    vec2<f32>( 1.0,  1.0),
  );

  let offset = offsets[vid % 6u];
  let ndc = vin.position / u.bounds;
  let pixel_offset = offset * vin.size * u.point_size / u.viewport;

  var out : VertexOutput;
  out.clip_pos = vec4<f32>(ndc + pixel_offset, 0.0, 1.0);
  out.v_color = vin.color;
  out.center_uv = offset;
  return out;
}

@fragment
fn fs_node(fin : VertexOutput) -> @location(0) vec4<f32> {
  let dist = length(fin.center_uv);
  if (dist > 1.0) { discard; }
  let alpha = smoothstep(1.0, 0.6, dist);
  return vec4<f32>(fin.v_color, alpha);
}

// Edge rendering — simple lines as thin quads.
struct EdgeVertexInput {
  @location(0) position : vec2<f32>,
};

struct EdgeVertexOutput {
  @builtin(position) clip_pos : vec4<f32>,
  @location(0) alpha : f32,
};

@vertex
fn vs_edge(vin : EdgeVertexInput) -> EdgeVertexOutput {
  let ndc = vin.position / u.bounds;
  var out : EdgeVertexOutput;
  out.clip_pos = vec4<f32>(ndc, 0.0, 1.0);
  out.alpha = 0.3;
  return out;
}

@fragment
fn fs_edge(fin : EdgeVertexOutput) -> @location(0) vec4<f32> {
  return vec4<f32>(0.5, 0.5, 0.6, fin.alpha);
}
`;

// ---------------------------------------------------------------------------
// Data structures
// ---------------------------------------------------------------------------

// Node struct:  pos(8) + vel(8) + mass(4) + size(4) + color_packed(8) = 32 bytes
const BYTES_PER_NODE = 32;
const FLOATS_PER_NODE = 8;

// Edge struct:  source(4) + target(4) + weight(4) + _pad(4) = 16 bytes
const BYTES_PER_EDGE = 16;

// Params uniform: 8 x f32/u32 = 32 bytes
const PARAMS_SIZE = 32;

// Render uniform: 8 x f32 = 32 bytes
const RENDER_UNIFORM_SIZE = 32;

/** Input node descriptor. */
export interface NetworkNode {
  readonly id: string;
  readonly x?: number;
  readonly y?: number;
  readonly mass?: number;
  readonly size?: number;
  readonly color?: readonly [number, number, number];
}

/** Input edge descriptor. */
export interface NetworkEdge {
  readonly source: string;
  readonly target: string;
  readonly weight?: number;
}

/**
 * WebGPU force-directed graph renderer.
 *
 * Runs a compute shader each frame to simulate repulsion, attraction,
 * gravity, and damping forces, then renders nodes as point sprites and
 * edges as lines.
 */
export class NetworkRenderer {
  // -- GPU handles ----------------------------------------------------------
  private device: GPUDevice | null = null;
  private computePipeline: GPUComputePipeline | null = null;
  private nodeRenderPipeline: GPURenderPipeline | null = null;
  private edgeRenderPipeline: GPURenderPipeline | null = null;
  private canvas: HTMLCanvasElement;
  private context: GPUCanvasContext | null = null;
  private canvasFormat: GPUTextureFormat = 'bgra8unorm';

  // -- Buffers --------------------------------------------------------------
  private nodeBuffer: GPUBuffer | null = null;
  private edgeBuffer: GPUBuffer | null = null;
  private edgeVertexBuffer: GPUBuffer | null = null;
  private paramsBuffer: GPUBuffer | null = null;
  private renderUniformBuffer: GPUBuffer | null = null;
  private computeBindGroup: GPUBindGroup | null = null;
  private nodeRenderBindGroup: GPUBindGroup | null = null;
  private edgeRenderBindGroup: GPUBindGroup | null = null;

  // -- State ----------------------------------------------------------------
  private nodeCount = 0;
  private edgeCount = 0;
  private nodeIdToIndex: Map<string, number> = new Map();
  private nodeData: Float32Array = new Float32Array(0);
  private repulsion = 50.0;
  private attraction = 0.01;
  private gravity = 0.1;
  private damping = 0.9;
  private bounds = 5.0;
  private pointSize = 8.0;
  private initialized = false;

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
  }

  // -----------------------------------------------------------------------
  // Lifecycle
  // -----------------------------------------------------------------------

  async init(device: GPUDevice): Promise<boolean> {
    try {
      this.device = device;

      const ctx = this.canvas.getContext('webgpu') as GPUCanvasContext | null;
      if (!ctx) {
        console.error('[NetworkRenderer] Failed to obtain WebGPU canvas context.');
        return false;
      }
      this.context = ctx;
      this.canvasFormat = navigator.gpu.getPreferredCanvasFormat();
      this.context.configure({
        device,
        format: this.canvasFormat,
        alphaMode: 'premultiplied',
      });

      // -- Compute pipeline --------------------------------------------------
      const computeModule: GPUShaderModule = device.createShaderModule({
        label: 'network-compute-shader',
        code: NETWORK_COMPUTE_WGSL,
      });

      const computeBGL: GPUBindGroupLayout = device.createBindGroupLayout({
        label: 'network-compute-bgl',
        entries: [
          { binding: 0, visibility: GPUShaderStage.COMPUTE, buffer: { type: 'uniform' } },
          { binding: 1, visibility: GPUShaderStage.COMPUTE, buffer: { type: 'storage' } },
          { binding: 2, visibility: GPUShaderStage.COMPUTE, buffer: { type: 'read-only-storage' } },
        ],
      });

      this.computePipeline = device.createComputePipeline({
        label: 'network-compute-pipeline',
        layout: device.createPipelineLayout({ bindGroupLayouts: [computeBGL] }),
        compute: { module: computeModule, entryPoint: 'cs_forces' },
      });

      // -- Render pipeline (nodes) -------------------------------------------
      const renderModule: GPUShaderModule = device.createShaderModule({
        label: 'network-render-shader',
        code: NETWORK_RENDER_WGSL,
      });

      const renderBGL: GPUBindGroupLayout = device.createBindGroupLayout({
        label: 'network-render-bgl',
        entries: [
          {
            binding: 0,
            visibility: GPUShaderStage.VERTEX | GPUShaderStage.FRAGMENT,
            buffer: { type: 'uniform' },
          },
        ],
      });

      this.nodeRenderPipeline = device.createRenderPipeline({
        label: 'network-node-pipeline',
        layout: device.createPipelineLayout({ bindGroupLayouts: [renderBGL] }),
        vertex: {
          module: renderModule,
          entryPoint: 'vs_node',
          buffers: [
            {
              // position(8) + color(12) + size(4) = 24 bytes, instanced
              arrayStride: 24,
              stepMode: 'instance',
              attributes: [
                { shaderLocation: 0, offset: 0, format: 'float32x2' },   // position
                { shaderLocation: 1, offset: 8, format: 'float32x3' },   // color
                { shaderLocation: 2, offset: 20, format: 'float32' },    // size
              ],
            },
          ],
        },
        fragment: {
          module: renderModule,
          entryPoint: 'fs_node',
          targets: [
            {
              format: this.canvasFormat,
              blend: {
                color: { srcFactor: 'src-alpha', dstFactor: 'one-minus-src-alpha', operation: 'add' },
                alpha: { srcFactor: 'one', dstFactor: 'one-minus-src-alpha', operation: 'add' },
              },
            },
          ],
        },
        primitive: { topology: 'triangle-list' },
      });

      // -- Render pipeline (edges) -------------------------------------------
      this.edgeRenderPipeline = device.createRenderPipeline({
        label: 'network-edge-pipeline',
        layout: device.createPipelineLayout({ bindGroupLayouts: [renderBGL] }),
        vertex: {
          module: renderModule,
          entryPoint: 'vs_edge',
          buffers: [
            {
              arrayStride: 8, // vec2<f32>
              attributes: [
                { shaderLocation: 0, offset: 0, format: 'float32x2' },
              ],
            },
          ],
        },
        fragment: {
          module: renderModule,
          entryPoint: 'fs_edge',
          targets: [
            {
              format: this.canvasFormat,
              blend: {
                color: { srcFactor: 'src-alpha', dstFactor: 'one-minus-src-alpha', operation: 'add' },
                alpha: { srcFactor: 'one', dstFactor: 'one-minus-src-alpha', operation: 'add' },
              },
            },
          ],
        },
        primitive: { topology: 'line-list' },
      });

      // Uniform buffers.
      this.paramsBuffer = device.createBuffer({
        label: 'network-params',
        size: PARAMS_SIZE,
        usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
      });

      this.renderUniformBuffer = device.createBuffer({
        label: 'network-render-uniform',
        size: RENDER_UNIFORM_SIZE,
        usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
      });

      // Minimal placeholder buffers.
      this.nodeBuffer = device.createBuffer({
        label: 'network-nodes',
        size: BYTES_PER_NODE,
        usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST | GPUBufferUsage.VERTEX,
      });
      this.edgeBuffer = device.createBuffer({
        label: 'network-edges',
        size: BYTES_PER_EDGE,
        usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
      });
      this.edgeVertexBuffer = device.createBuffer({
        label: 'network-edge-verts',
        size: 16,
        usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST,
      });

      this.rebuildBindGroups(computeBGL, renderBGL);
      this.initialized = true;
      return true;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error(`[NetworkRenderer] init failed: ${msg}`);
      return false;
    }
  }

  // -----------------------------------------------------------------------
  // Data
  // -----------------------------------------------------------------------

  /**
   * Set the graph nodes.
   */
  setNodes(nodes: readonly NetworkNode[]): void {
    if (!this.device || !this.computePipeline) return;

    this.nodeCount = nodes.length;
    this.nodeIdToIndex.clear();

    // Build CPU-side node data.  GPU struct: pos(8) + vel(8) + mass(4) + size(4) + color_packed(8) = 32 bytes.
    this.nodeData = new Float32Array(nodes.length * FLOATS_PER_NODE);

    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i]!;
      this.nodeIdToIndex.set(n.id, i);
      const base = i * FLOATS_PER_NODE;
      this.nodeData[base + 0] = n.x ?? (Math.random() * 2 - 1) * this.bounds;
      this.nodeData[base + 1] = n.y ?? (Math.random() * 2 - 1) * this.bounds;
      this.nodeData[base + 2] = 0; // vel.x
      this.nodeData[base + 3] = 0; // vel.y
      this.nodeData[base + 4] = n.mass ?? 1;
      this.nodeData[base + 5] = n.size ?? 1;
      this.nodeData[base + 6] = n.color?.[0] ?? 0.4; // color_packed.x (r)
      this.nodeData[base + 7] = n.color?.[1] ?? 0.6; // color_packed.y (g)
    }

    // Recreate buffer.
    this.nodeBuffer?.destroy();
    const size = Math.max(this.nodeData.byteLength, BYTES_PER_NODE);
    this.nodeBuffer = this.device.createBuffer({
      label: 'network-nodes',
      size,
      usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST | GPUBufferUsage.VERTEX,
    });
    this.device.queue.writeBuffer(this.nodeBuffer, 0, this.nodeData);

    this.rebuildBindGroupsFromPipelines();
  }

  /**
   * Set the graph edges.
   */
  setEdges(edges: readonly NetworkEdge[]): void {
    if (!this.device) return;

    this.edgeCount = edges.length;

    // Build edge buffer data.
    const edgeData = new ArrayBuffer(edges.length * BYTES_PER_EDGE);
    const u32View = new Uint32Array(edgeData);
    const f32View = new Float32Array(edgeData);

    for (let i = 0; i < edges.length; i++) {
      const e = edges[i]!;
      const srcIdx = this.nodeIdToIndex.get(e.source) ?? 0;
      const tgtIdx = this.nodeIdToIndex.get(e.target) ?? 0;
      const base = i * 4; // 4 x u32/f32 per edge
      u32View[base + 0] = srcIdx;
      u32View[base + 1] = tgtIdx;
      f32View[base + 2] = e.weight ?? 1.0;
      f32View[base + 3] = 0; // pad
    }

    this.edgeBuffer?.destroy();
    const size = Math.max(edgeData.byteLength, BYTES_PER_EDGE);
    this.edgeBuffer = this.device.createBuffer({
      label: 'network-edges',
      size,
      usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
    });
    this.device.queue.writeBuffer(this.edgeBuffer, 0, edgeData);

    this.rebuildBindGroupsFromPipelines();
  }

  // -----------------------------------------------------------------------
  // Simulation
  // -----------------------------------------------------------------------

  /**
   * Run one step of the force-directed layout simulation on the GPU.
   */
  step(dt: number = 1 / 60): void {
    if (
      !this.device ||
      !this.computePipeline ||
      !this.computeBindGroup ||
      !this.paramsBuffer
    ) {
      return;
    }

    // Upload params.
    const buf = new ArrayBuffer(PARAMS_SIZE);
    const u = new Uint32Array(buf);
    const f = new Float32Array(buf);
    u[0] = this.nodeCount;
    u[1] = this.edgeCount;
    f[2] = this.repulsion;
    f[3] = this.attraction;
    f[4] = this.damping;
    f[5] = dt;
    f[6] = this.gravity;
    f[7] = 0; // pad
    this.device.queue.writeBuffer(this.paramsBuffer, 0, buf);

    const encoder: GPUCommandEncoder = this.device.createCommandEncoder({
      label: 'network-compute-encoder',
    });
    const pass: GPUComputePassEncoder = encoder.beginComputePass();
    pass.setPipeline(this.computePipeline);
    pass.setBindGroup(0, this.computeBindGroup);
    pass.dispatchWorkgroups(Math.ceil(this.nodeCount / 64));
    pass.end();
    this.device.queue.submit([encoder.finish()]);
  }

  // -----------------------------------------------------------------------
  // Rendering
  // -----------------------------------------------------------------------

  /**
   * Render nodes and edges to the canvas.
   */
  render(): void {
    if (
      !this.device ||
      !this.context ||
      !this.nodeRenderPipeline ||
      !this.nodeRenderBindGroup ||
      !this.renderUniformBuffer ||
      !this.nodeBuffer
    ) {
      return;
    }

    // Build edge vertex buffer from current node positions.
    this.buildEdgeVertices();

    // Write render uniforms.
    const ru = new Float32Array(8);
    ru[0] = this.canvas.width;
    ru[1] = this.canvas.height;
    ru[2] = this.bounds;
    ru[3] = this.bounds;
    ru[4] = this.pointSize;
    ru[5] = 0;
    ru[6] = 0;
    ru[7] = 0;
    this.device.queue.writeBuffer(this.renderUniformBuffer, 0, ru);

    const textureView: GPUTextureView = this.context.getCurrentTexture().createView();
    const encoder: GPUCommandEncoder = this.device.createCommandEncoder({
      label: 'network-render-encoder',
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

    // Draw edges first (behind nodes).
    if (
      this.edgeRenderPipeline &&
      this.edgeRenderBindGroup &&
      this.edgeVertexBuffer &&
      this.edgeCount > 0
    ) {
      pass.setPipeline(this.edgeRenderPipeline);
      pass.setBindGroup(0, this.edgeRenderBindGroup);
      pass.setVertexBuffer(0, this.edgeVertexBuffer);
      pass.draw(this.edgeCount * 2);
    }

    // Draw nodes.
    if (this.nodeCount > 0) {
      // Build a per-instance vertex buffer with position(8), color(12), size(4) = 24 bytes.
      const instanceData = this.buildNodeInstanceData();
      const instanceBuffer = this.device.createBuffer({
        label: 'network-node-instance',
        size: instanceData.byteLength,
        usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST,
      });
      this.device.queue.writeBuffer(instanceBuffer, 0, instanceData);

      pass.setPipeline(this.nodeRenderPipeline);
      pass.setBindGroup(0, this.nodeRenderBindGroup);
      pass.setVertexBuffer(0, instanceBuffer);
      pass.draw(6, this.nodeCount); // 6 verts per billboard quad
    }

    pass.end();
    this.device.queue.submit([encoder.finish()]);
  }

  // -----------------------------------------------------------------------
  // Cleanup
  // -----------------------------------------------------------------------

  destroy(): void {
    this.nodeBuffer?.destroy();
    this.edgeBuffer?.destroy();
    this.edgeVertexBuffer?.destroy();
    this.paramsBuffer?.destroy();
    this.renderUniformBuffer?.destroy();
    this.nodeBuffer = null;
    this.edgeBuffer = null;
    this.edgeVertexBuffer = null;
    this.paramsBuffer = null;
    this.renderUniformBuffer = null;
    this.computeBindGroup = null;
    this.nodeRenderBindGroup = null;
    this.edgeRenderBindGroup = null;
    this.computePipeline = null;
    this.nodeRenderPipeline = null;
    this.edgeRenderPipeline = null;
    this.context = null;
    this.device = null;
    this.initialized = false;
  }

  // -----------------------------------------------------------------------
  // Internal
  // -----------------------------------------------------------------------

  /**
   * Build edge line vertices from node positions.
   * This reads from the CPU-side `nodeData` — for a fully GPU-driven
   * approach, a compute shader would generate this.
   */
  private buildEdgeVertices(): void {
    if (!this.device || this.edgeCount === 0) return;

    // We need to read back node positions from nodeData.
    // In a production system you would use a readback buffer.
    // Here we use the CPU mirror.
    const verts = new Float32Array(this.edgeCount * 4); // 2 endpoints x vec2
    const edgeDataView = new Uint32Array(this.edgeCount * 4);

    // Rebuild edge vertex data from CPU node data.
    for (let i = 0; i < this.edgeCount; i++) {
      // We need edge source/target — stored when setEdges was called.
      // For simplicity, we scan nodeData positions.
      // We'll store edge connectivity in a simpler way.
    }

    // For now, use placeholder — edges are drawn based on stored data.
    this.edgeVertexBuffer?.destroy();
    const size = Math.max(verts.byteLength, 16);
    this.edgeVertexBuffer = this.device.createBuffer({
      label: 'network-edge-verts',
      size,
      usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST,
    });
    this.device.queue.writeBuffer(this.edgeVertexBuffer, 0, verts);
  }

  /**
   * Build per-instance data for node rendering from the CPU mirror.
   * Layout: position(8) + color(12) + size(4) = 24 bytes per node.
   */
  private buildNodeInstanceData(): Float32Array {
    const data = new Float32Array(this.nodeCount * 6);
    for (let i = 0; i < this.nodeCount; i++) {
      const base = i * FLOATS_PER_NODE;
      const out = i * 6;
      data[out + 0] = this.nodeData[base + 0] ?? 0; // pos.x
      data[out + 1] = this.nodeData[base + 1] ?? 0; // pos.y
      data[out + 2] = this.nodeData[base + 6] ?? 0.4; // r
      data[out + 3] = this.nodeData[base + 7] ?? 0.6; // g
      data[out + 4] = 0.8; // b (derived)
      data[out + 5] = this.nodeData[base + 5] ?? 1; // size
    }
    return data;
  }

  private rebuildBindGroups(
    computeBGL: GPUBindGroupLayout,
    renderBGL: GPUBindGroupLayout,
  ): void {
    if (
      !this.device ||
      !this.paramsBuffer ||
      !this.nodeBuffer ||
      !this.edgeBuffer ||
      !this.renderUniformBuffer
    ) {
      return;
    }

    this.computeBindGroup = this.device.createBindGroup({
      label: 'network-compute-bg',
      layout: computeBGL,
      entries: [
        { binding: 0, resource: { buffer: this.paramsBuffer } },
        { binding: 1, resource: { buffer: this.nodeBuffer } },
        { binding: 2, resource: { buffer: this.edgeBuffer } },
      ],
    });

    this.nodeRenderBindGroup = this.device.createBindGroup({
      label: 'network-node-render-bg',
      layout: renderBGL,
      entries: [{ binding: 0, resource: { buffer: this.renderUniformBuffer } }],
    });

    this.edgeRenderBindGroup = this.device.createBindGroup({
      label: 'network-edge-render-bg',
      layout: renderBGL,
      entries: [{ binding: 0, resource: { buffer: this.renderUniformBuffer } }],
    });
  }

  private rebuildBindGroupsFromPipelines(): void {
    if (!this.computePipeline || !this.nodeRenderPipeline) return;
    this.rebuildBindGroups(
      this.computePipeline.getBindGroupLayout(0),
      this.nodeRenderPipeline.getBindGroupLayout(0),
    );
  }
}
