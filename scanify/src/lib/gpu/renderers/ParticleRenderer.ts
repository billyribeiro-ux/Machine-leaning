// ---------------------------------------------------------------------------
// WebGPU Particle Renderer — Scanify trading scanner
//
// GPU-computed particle system with compute pass for physics simulation
// and render pass for billboard point-sprite display.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Inline WGSL — compute + render shaders
// ---------------------------------------------------------------------------

const PARTICLE_COMPUTE_WGSL = /* wgsl */ `
struct Params {
  delta_time    : f32,
  attractor_x   : f32,
  attractor_y   : f32,
  attractor_str : f32,
  damping       : f32,
  particle_count: u32,
  _pad0         : u32,
  _pad1         : u32,
};

struct Particle {
  pos  : vec2<f32>,
  vel  : vec2<f32>,
  color: vec4<f32>,
  life : f32,
  max_life : f32,
  _pad0: f32,
  _pad1: f32,
};

@group(0) @binding(0) var<uniform> params : Params;
@group(0) @binding(1) var<storage, read_write> particles : array<Particle>;

@compute @workgroup_size(64)
fn cs_main(@builtin(global_invocation_id) gid : vec3<u32>) {
  let idx = gid.x;
  if (idx >= params.particle_count) { return; }

  var p = particles[idx];

  // Skip dead particles.
  if (p.life <= 0.0) { return; }

  // Attraction force towards the attractor point.
  let attractor = vec2<f32>(params.attractor_x, params.attractor_y);
  let diff = attractor - p.pos;
  let dist = max(length(diff), 0.001);
  let force = normalize(diff) * params.attractor_str / (dist * dist + 1.0);

  // Integrate velocity and position.
  p.vel = (p.vel + force * params.delta_time) * params.damping;
  p.pos = p.pos + p.vel * params.delta_time;

  // Age the particle.
  p.life = p.life - params.delta_time;

  // Fade alpha based on remaining life.
  let life_ratio = clamp(p.life / p.max_life, 0.0, 1.0);
  p.color.a = life_ratio;

  particles[idx] = p;
}
`;

const PARTICLE_RENDER_WGSL = /* wgsl */ `
struct RenderUniforms {
  viewport : vec2<f32>,
  point_size : f32,
  _pad : f32,
};

struct Particle {
  pos  : vec2<f32>,
  vel  : vec2<f32>,
  color: vec4<f32>,
  life : f32,
  max_life : f32,
  _pad0: f32,
  _pad1: f32,
};

@group(0) @binding(0) var<uniform> uniforms : RenderUniforms;
@group(0) @binding(1) var<storage, read> particles : array<Particle>;

struct VertexOutput {
  @builtin(position) position : vec4<f32>,
  @location(0) color : vec4<f32>,
  @location(1) center_uv : vec2<f32>,
};

@vertex
fn vs_main(
  @builtin(vertex_index) vid : u32,
  @builtin(instance_index) iid : u32,
) -> VertexOutput {
  let p = particles[iid];

  // Quad offsets for a billboard sprite (two triangles, 6 vertices).
  var offsets = array<vec2<f32>, 6>(
    vec2<f32>(-1.0, -1.0),
    vec2<f32>( 1.0, -1.0),
    vec2<f32>(-1.0,  1.0),
    vec2<f32>(-1.0,  1.0),
    vec2<f32>( 1.0, -1.0),
    vec2<f32>( 1.0,  1.0),
  );

  let offset = offsets[vid];
  let pixel_size = uniforms.point_size;

  // Convert particle position from [-1,1] NDC to clip space, then offset.
  let clip_pos = vec2<f32>(p.pos.x, p.pos.y);
  let pixel_offset = offset * pixel_size / uniforms.viewport;

  var out : VertexOutput;
  out.position = vec4<f32>(clip_pos + pixel_offset, 0.0, 1.0);
  out.color = p.color;
  out.center_uv = offset; // [-1,1] within the quad
  return out;
}

@fragment
fn fs_main(in : VertexOutput) -> @location(0) vec4<f32> {
  // Circular falloff.
  let dist = length(in.center_uv);
  if (dist > 1.0) { discard; }
  let alpha = smoothstep(1.0, 0.3, dist) * in.color.a;
  return vec4<f32>(in.color.rgb, alpha);
}
`;

// ---------------------------------------------------------------------------
// Particle data layout — must match the WGSL struct exactly.
//
//  pos      : vec2<f32>  (8 bytes)  offset 0
//  vel      : vec2<f32>  (8 bytes)  offset 8
//  color    : vec4<f32>  (16 bytes) offset 16
//  life     : f32        (4 bytes)  offset 32
//  max_life : f32        (4 bytes)  offset 36
//  _pad0    : f32        (4 bytes)  offset 40
//  _pad1    : f32        (4 bytes)  offset 44
//  TOTAL    : 48 bytes per particle
// ---------------------------------------------------------------------------
const FLOATS_PER_PARTICLE = 12; // 48 / 4
const BYTES_PER_PARTICLE = 48;

// Params uniform: 8 x u32/f32 = 32 bytes
const PARAMS_SIZE = 32;
// Render uniform: 4 x f32 = 16 bytes
const RENDER_UNIFORM_SIZE = 16;

/** Options used when spawning a batch of new particles. */
export interface ParticleSpawnOptions {
  /** Origin X in NDC [-1, 1]. */
  readonly x: number;
  /** Origin Y in NDC [-1, 1]. */
  readonly y: number;
  /** Number of particles to emit. */
  readonly count: number;
  /** Base colour [r, g, b] each in [0, 1]. */
  readonly color: readonly [number, number, number];
  /** Lifetime in seconds. */
  readonly life: number;
  /** Spread radius for initial velocity randomisation. */
  readonly spread: number;
}

/**
 * GPU-accelerated particle system renderer.
 *
 * Uses a compute pass to simulate physics (attraction, damping, aging) and a
 * render pass to draw billboard point sprites with circular falloff.
 */
export class ParticleRenderer {
  // -- GPU handles ----------------------------------------------------------
  private device: GPUDevice | null = null;
  private computePipeline: GPUComputePipeline | null = null;
  private renderPipeline: GPURenderPipeline | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private context: GPUCanvasContext | null = null;
  private canvasFormat: GPUTextureFormat = 'bgra8unorm';

  // -- Buffers --------------------------------------------------------------
  private particleBuffer: GPUBuffer | null = null;
  private paramsBuffer: GPUBuffer | null = null;
  private renderUniformBuffer: GPUBuffer | null = null;
  private computeBindGroup: GPUBindGroup | null = null;
  private renderBindGroup: GPUBindGroup | null = null;

  // -- State ----------------------------------------------------------------
  private maxParticles = 0;
  private particleData: Float32Array = new Float32Array(0);
  private nextSlot = 0;
  private attractorX = 0;
  private attractorY = 0;
  private attractorStrength = 0.5;
  private pointSize = 6.0;
  private initialized = false;

  // -----------------------------------------------------------------------
  // Lifecycle
  // -----------------------------------------------------------------------

  /**
   * Initialise the particle system.
   *
   * @param device        A live GPUDevice.
   * @param canvas        The target canvas element.
   * @param maxParticles  Maximum number of simultaneous particles (default 10 000).
   * @returns `true` on success.
   */
  async init(
    device: GPUDevice,
    canvas: HTMLCanvasElement,
    maxParticles: number = 10_000,
  ): Promise<boolean> {
    try {
      this.device = device;
      this.canvas = canvas;
      this.maxParticles = maxParticles;

      // Canvas context -------------------------------------------------------
      const ctx = canvas.getContext('webgpu') as GPUCanvasContext | null;
      if (!ctx) {
        console.error('[ParticleRenderer] Failed to obtain WebGPU canvas context.');
        return false;
      }
      this.context = ctx;
      this.canvasFormat = navigator.gpu.getPreferredCanvasFormat();
      this.context.configure({
        device,
        format: this.canvasFormat,
        alphaMode: 'premultiplied',
      });

      // CPU-side particle array ----------------------------------------------
      this.particleData = new Float32Array(maxParticles * FLOATS_PER_PARTICLE);

      // Particle storage buffer ----------------------------------------------
      this.particleBuffer = device.createBuffer({
        label: 'particle-buffer',
        size: maxParticles * BYTES_PER_PARTICLE,
        usage:
          GPUBufferUsage.STORAGE |
          GPUBufferUsage.COPY_DST |
          GPUBufferUsage.VERTEX,
      });

      // Params uniform (compute) ---------------------------------------------
      this.paramsBuffer = device.createBuffer({
        label: 'particle-params',
        size: PARAMS_SIZE,
        usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
      });

      // Render uniform -------------------------------------------------------
      this.renderUniformBuffer = device.createBuffer({
        label: 'particle-render-uniform',
        size: RENDER_UNIFORM_SIZE,
        usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
      });

      // -- Compute pipeline --------------------------------------------------
      const computeModule: GPUShaderModule = device.createShaderModule({
        label: 'particle-compute-shader',
        code: PARTICLE_COMPUTE_WGSL,
      });

      const computeBGL: GPUBindGroupLayout = device.createBindGroupLayout({
        label: 'particle-compute-bgl',
        entries: [
          { binding: 0, visibility: GPUShaderStage.COMPUTE, buffer: { type: 'uniform' } },
          { binding: 1, visibility: GPUShaderStage.COMPUTE, buffer: { type: 'storage' } },
        ],
      });

      this.computePipeline = device.createComputePipeline({
        label: 'particle-compute-pipeline',
        layout: device.createPipelineLayout({ bindGroupLayouts: [computeBGL] }),
        compute: { module: computeModule, entryPoint: 'cs_main' },
      });

      this.computeBindGroup = device.createBindGroup({
        label: 'particle-compute-bg',
        layout: computeBGL,
        entries: [
          { binding: 0, resource: { buffer: this.paramsBuffer } },
          { binding: 1, resource: { buffer: this.particleBuffer } },
        ],
      });

      // -- Render pipeline ---------------------------------------------------
      const renderModule: GPUShaderModule = device.createShaderModule({
        label: 'particle-render-shader',
        code: PARTICLE_RENDER_WGSL,
      });

      const renderBGL: GPUBindGroupLayout = device.createBindGroupLayout({
        label: 'particle-render-bgl',
        entries: [
          {
            binding: 0,
            visibility: GPUShaderStage.VERTEX | GPUShaderStage.FRAGMENT,
            buffer: { type: 'uniform' },
          },
          {
            binding: 1,
            visibility: GPUShaderStage.VERTEX,
            buffer: { type: 'read-only-storage' },
          },
        ],
      });

      this.renderPipeline = device.createRenderPipeline({
        label: 'particle-render-pipeline',
        layout: device.createPipelineLayout({ bindGroupLayouts: [renderBGL] }),
        vertex: {
          module: renderModule,
          entryPoint: 'vs_main',
        },
        fragment: {
          module: renderModule,
          entryPoint: 'fs_main',
          targets: [
            {
              format: this.canvasFormat,
              blend: {
                color: {
                  srcFactor: 'src-alpha',
                  dstFactor: 'one-minus-src-alpha',
                  operation: 'add',
                },
                alpha: {
                  srcFactor: 'one',
                  dstFactor: 'one-minus-src-alpha',
                  operation: 'add',
                },
              },
            },
          ],
        },
        primitive: { topology: 'triangle-list' },
      });

      this.renderBindGroup = device.createBindGroup({
        label: 'particle-render-bg',
        layout: renderBGL,
        entries: [
          { binding: 0, resource: { buffer: this.renderUniformBuffer } },
          { binding: 1, resource: { buffer: this.particleBuffer } },
        ],
      });

      this.initialized = true;
      return true;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error(`[ParticleRenderer] init failed: ${msg}`);
      return false;
    }
  }

  // -----------------------------------------------------------------------
  // Simulation
  // -----------------------------------------------------------------------

  /**
   * Run the compute pass to update particle physics.
   *
   * @param dt  Time step in seconds since last update.
   */
  update(dt: number): void {
    if (!this.device || !this.computePipeline || !this.computeBindGroup || !this.paramsBuffer) {
      return;
    }

    // Upload params ----------------------------------------------------------
    const buf = new ArrayBuffer(PARAMS_SIZE);
    const f32 = new Float32Array(buf);
    const u32 = new Uint32Array(buf);
    f32[0] = dt;
    f32[1] = this.attractorX;
    f32[2] = this.attractorY;
    f32[3] = this.attractorStrength;
    f32[4] = 0.98; // damping
    u32[5] = this.maxParticles;
    u32[6] = 0;
    u32[7] = 0;
    this.device.queue.writeBuffer(this.paramsBuffer, 0, buf);

    // Dispatch compute -------------------------------------------------------
    const encoder: GPUCommandEncoder = this.device.createCommandEncoder({
      label: 'particle-compute-encoder',
    });
    const pass: GPUComputePassEncoder = encoder.beginComputePass({
      label: 'particle-compute-pass',
    });
    pass.setPipeline(this.computePipeline);
    pass.setBindGroup(0, this.computeBindGroup);
    pass.dispatchWorkgroups(Math.ceil(this.maxParticles / 64));
    pass.end();

    this.device.queue.submit([encoder.finish()]);
  }

  // -----------------------------------------------------------------------
  // Rendering
  // -----------------------------------------------------------------------

  /**
   * Render all live particles to the canvas.
   */
  render(): void {
    if (
      !this.device ||
      !this.renderPipeline ||
      !this.context ||
      !this.renderBindGroup ||
      !this.renderUniformBuffer ||
      !this.canvas
    ) {
      return;
    }

    // Upload render uniforms -------------------------------------------------
    const ru = new Float32Array(4);
    ru[0] = this.canvas.width;
    ru[1] = this.canvas.height;
    ru[2] = this.pointSize;
    ru[3] = 0; // pad
    this.device.queue.writeBuffer(this.renderUniformBuffer, 0, ru);

    // Render pass ------------------------------------------------------------
    const textureView: GPUTextureView = this.context.getCurrentTexture().createView();
    const encoder: GPUCommandEncoder = this.device.createCommandEncoder({
      label: 'particle-render-encoder',
    });

    const pass: GPURenderPassEncoder = encoder.beginRenderPass({
      colorAttachments: [
        {
          view: textureView,
          clearValue: { r: 0.03, g: 0.03, b: 0.05, a: 1.0 },
          loadOp: 'clear',
          storeOp: 'store',
        },
      ],
    });

    pass.setPipeline(this.renderPipeline);
    pass.setBindGroup(0, this.renderBindGroup);
    // 6 vertices per quad (billboard), instanced over all particles.
    pass.draw(6, this.maxParticles, 0, 0);
    pass.end();

    this.device.queue.submit([encoder.finish()]);
  }

  // -----------------------------------------------------------------------
  // Particle emission
  // -----------------------------------------------------------------------

  /**
   * Emit a batch of new particles.  Dead particles (life <= 0) are recycled
   * in a ring-buffer fashion.
   */
  addParticles(opts: ParticleSpawnOptions): void {
    if (!this.device || !this.particleBuffer) return;

    const { x, y, count, color, life, spread } = opts;

    for (let i = 0; i < count; i++) {
      const base = this.nextSlot * FLOATS_PER_PARTICLE;
      const angle = Math.random() * Math.PI * 2;
      const speed = Math.random() * spread;

      this.particleData[base + 0] = x;                     // pos.x
      this.particleData[base + 1] = y;                     // pos.y
      this.particleData[base + 2] = Math.cos(angle) * speed; // vel.x
      this.particleData[base + 3] = Math.sin(angle) * speed; // vel.y
      this.particleData[base + 4] = color[0];              // color.r
      this.particleData[base + 5] = color[1];              // color.g
      this.particleData[base + 6] = color[2];              // color.b
      this.particleData[base + 7] = 1.0;                   // color.a
      this.particleData[base + 8] = life;                  // life
      this.particleData[base + 9] = life;                  // max_life
      this.particleData[base + 10] = 0;                    // _pad0
      this.particleData[base + 11] = 0;                    // _pad1

      this.nextSlot = (this.nextSlot + 1) % this.maxParticles;
    }

    // Upload changed region (simplified: upload entire buffer).
    this.device.queue.writeBuffer(this.particleBuffer, 0, this.particleData);
  }

  /**
   * Set the attraction point for particles.
   */
  setAttractor(x: number, y: number, strength: number = 0.5): void {
    this.attractorX = x;
    this.attractorY = y;
    this.attractorStrength = strength;
  }

  /**
   * Set the render point size in pixels.
   */
  setPointSize(size: number): void {
    this.pointSize = size;
  }

  // -----------------------------------------------------------------------
  // Cleanup
  // -----------------------------------------------------------------------

  /**
   * Destroy all GPU resources.
   */
  destroy(): void {
    this.particleBuffer?.destroy();
    this.paramsBuffer?.destroy();
    this.renderUniformBuffer?.destroy();
    this.particleBuffer = null;
    this.paramsBuffer = null;
    this.renderUniformBuffer = null;
    this.computeBindGroup = null;
    this.renderBindGroup = null;
    this.computePipeline = null;
    this.renderPipeline = null;
    this.context = null;
    this.device = null;
    this.canvas = null;
    this.initialized = false;
  }
}
