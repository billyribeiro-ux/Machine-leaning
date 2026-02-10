// ---------------------------------------------------------------------------
// WebGPU Surface Renderer — Scanify trading scanner
//
// Renders a 3-D volatility surface as a triangle mesh with interactive
// rotation and zoom.  Suitable for options implied-volatility surfaces,
// term structure visualisation, etc.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// WGSL shaders
// ---------------------------------------------------------------------------

const SURFACE_WGSL = /* wgsl */ `
struct SurfaceUniforms {
  view       : mat4x4<f32>,
  projection : mat4x4<f32>,
  model      : mat4x4<f32>,
  light_dir  : vec3<f32>,
  _pad0      : f32,
  color_low  : vec3<f32>,
  _pad1      : f32,
  color_high : vec3<f32>,
  value_range: f32,   // max height for normalisation
};

struct VertexInput {
  @location(0) position : vec3<f32>,
  @location(1) normal   : vec3<f32>,
  @location(2) height   : f32,
};

struct VertexOutput {
  @builtin(position) clip_pos : vec4<f32>,
  @location(0) world_normal   : vec3<f32>,
  @location(1) height_ratio   : f32,
};

@group(0) @binding(0) var<uniform> u : SurfaceUniforms;

@vertex
fn vs_main(vin : VertexInput) -> VertexOutput {
  let world_pos = u.model * vec4<f32>(vin.position, 1.0);
  let clip = u.projection * u.view * world_pos;

  var out : VertexOutput;
  out.clip_pos = clip;
  out.world_normal = (u.model * vec4<f32>(vin.normal, 0.0)).xyz;
  out.height_ratio = clamp(vin.height / max(u.value_range, 0.001), 0.0, 1.0);
  return out;
}

@fragment
fn fs_main(fin : VertexOutput) -> @location(0) vec4<f32> {
  let n = normalize(fin.world_normal);
  let l = normalize(u.light_dir);

  // Simple diffuse + ambient lighting.
  let ndotl = max(dot(n, l), 0.0);
  let ambient = 0.2;
  let diffuse = ndotl * 0.8;

  // Height-based colour ramp.
  let colour = mix(u.color_low, u.color_high, fin.height_ratio);
  let lit = colour * (ambient + diffuse);

  return vec4<f32>(lit, 1.0);
}
`;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// SurfaceUniforms byte size:
//   view(64) + projection(64) + model(64) + light_dir(12) + _pad0(4)
//   + color_low(12) + _pad1(4) + color_high(12) + value_range(4) = 240
const UNIFORM_SIZE = 240;

/** A 2-D grid of scalar values used to generate the surface mesh. */
export interface SurfaceGrid {
  /** Number of columns (X axis, e.g. strike prices). */
  readonly cols: number;
  /** Number of rows (Z axis, e.g. expiration dates). */
  readonly rows: number;
  /** Row-major flat array of height values (cols * rows). */
  readonly values: Float32Array;
}

/**
 * WebGPU renderer for interactive 3-D surface visualisation.
 *
 * Generates a triangle mesh from a regular grid and renders it with basic
 * diffuse lighting and a height-based colour ramp.  Supports interactive
 * rotation and zoom.
 */
export class SurfaceRenderer {
  // -- GPU handles ----------------------------------------------------------
  private device: GPUDevice | null = null;
  private pipeline: GPURenderPipeline | null = null;
  private canvas: HTMLCanvasElement;
  private context: GPUCanvasContext | null = null;
  private canvasFormat: GPUTextureFormat = 'bgra8unorm';
  private depthTexture: GPUTexture | null = null;

  // -- Buffers --------------------------------------------------------------
  private uniformBuffer: GPUBuffer | null = null;
  private vertexBuffer: GPUBuffer | null = null;
  private indexBuffer: GPUBuffer | null = null;
  private bindGroup: GPUBindGroup | null = null;

  // -- Mesh state -----------------------------------------------------------
  private indexCount = 0;
  private valueRange = 1;

  // -- Camera state ---------------------------------------------------------
  private rotationX = -0.6; // radians
  private rotationY = 0.4;
  private zoomLevel = 3.0;
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
        console.error('[SurfaceRenderer] Failed to obtain WebGPU canvas context.');
        return false;
      }
      this.context = ctx;
      this.canvasFormat = navigator.gpu.getPreferredCanvasFormat();
      this.context.configure({
        device,
        format: this.canvasFormat,
        alphaMode: 'premultiplied',
      });

      // Depth texture for z-buffering.
      this.depthTexture = this.createDepthTexture();

      const shaderModule: GPUShaderModule = device.createShaderModule({
        label: 'surface-shader',
        code: SURFACE_WGSL,
      });

      const bgl: GPUBindGroupLayout = device.createBindGroupLayout({
        label: 'surface-bgl',
        entries: [
          {
            binding: 0,
            visibility: GPUShaderStage.VERTEX | GPUShaderStage.FRAGMENT,
            buffer: { type: 'uniform' },
          },
        ],
      });

      this.pipeline = device.createRenderPipeline({
        label: 'surface-pipeline',
        layout: device.createPipelineLayout({ bindGroupLayouts: [bgl] }),
        vertex: {
          module: shaderModule,
          entryPoint: 'vs_main',
          buffers: [
            {
              // position (vec3) + normal (vec3) + height (f32) = 28 bytes
              arrayStride: 28,
              attributes: [
                { shaderLocation: 0, offset: 0, format: 'float32x3' },  // position
                { shaderLocation: 1, offset: 12, format: 'float32x3' }, // normal
                { shaderLocation: 2, offset: 24, format: 'float32' },   // height
              ],
            },
          ],
        },
        fragment: {
          module: shaderModule,
          entryPoint: 'fs_main',
          targets: [{ format: this.canvasFormat }],
        },
        primitive: {
          topology: 'triangle-list',
          cullMode: 'none',
        },
        depthStencil: {
          format: 'depth24plus',
          depthWriteEnabled: true,
          depthCompare: 'less',
        },
      });

      this.uniformBuffer = device.createBuffer({
        label: 'surface-uniforms',
        size: UNIFORM_SIZE,
        usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
      });

      this.bindGroup = device.createBindGroup({
        label: 'surface-bg',
        layout: bgl,
        entries: [{ binding: 0, resource: { buffer: this.uniformBuffer } }],
      });

      this.initialized = true;
      return true;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error(`[SurfaceRenderer] init failed: ${msg}`);
      return false;
    }
  }

  // -----------------------------------------------------------------------
  // Data
  // -----------------------------------------------------------------------

  /**
   * Build a triangle mesh from the supplied grid data and upload it.
   */
  setSurfaceData(grid: SurfaceGrid): void {
    if (!this.device) return;

    const { cols, rows, values } = grid;
    if (cols < 2 || rows < 2) return;

    // Determine value range.
    let maxVal = 0;
    for (let i = 0; i < values.length; i++) {
      const v = Math.abs(values[i] ?? 0);
      if (v > maxVal) maxVal = v;
    }
    this.valueRange = maxVal || 1;

    // Build vertices: position (3) + normal (3) + height (1) = 7 floats each.
    const vertexCount = cols * rows;
    const vertFloats = new Float32Array(vertexCount * 7);

    const getHeight = (c: number, r: number): number => {
      return values[r * cols + c] ?? 0;
    };

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const idx = r * cols + c;
        const x = (c / (cols - 1)) * 2 - 1; // [-1, 1]
        const z = (r / (rows - 1)) * 2 - 1; // [-1, 1]
        const y = getHeight(c, r) / this.valueRange;

        // Simple normal estimation via finite differences.
        const hL = c > 0 ? getHeight(c - 1, r) / this.valueRange : y;
        const hR = c < cols - 1 ? getHeight(c + 1, r) / this.valueRange : y;
        const hD = r > 0 ? getHeight(c, r - 1) / this.valueRange : y;
        const hU = r < rows - 1 ? getHeight(c, r + 1) / this.valueRange : y;

        const nx = hL - hR;
        const nz = hD - hU;
        const ny = 2.0 / Math.max(cols, rows);
        const len = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;

        const base = idx * 7;
        vertFloats[base + 0] = x;
        vertFloats[base + 1] = y;
        vertFloats[base + 2] = z;
        vertFloats[base + 3] = nx / len;
        vertFloats[base + 4] = ny / len;
        vertFloats[base + 5] = nz / len;
        vertFloats[base + 6] = getHeight(c, r);
      }
    }

    // Build index buffer (two triangles per quad cell).
    const quads = (cols - 1) * (rows - 1);
    const indices = new Uint32Array(quads * 6);
    let ii = 0;
    for (let r = 0; r < rows - 1; r++) {
      for (let c = 0; c < cols - 1; c++) {
        const topLeft = r * cols + c;
        const topRight = topLeft + 1;
        const bottomLeft = topLeft + cols;
        const bottomRight = bottomLeft + 1;

        indices[ii++] = topLeft;
        indices[ii++] = bottomLeft;
        indices[ii++] = topRight;
        indices[ii++] = topRight;
        indices[ii++] = bottomLeft;
        indices[ii++] = bottomRight;
      }
    }
    this.indexCount = indices.length;

    // Upload to GPU.
    this.vertexBuffer?.destroy();
    this.indexBuffer?.destroy();

    this.vertexBuffer = this.device.createBuffer({
      label: 'surface-vertices',
      size: vertFloats.byteLength,
      usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST,
    });
    this.device.queue.writeBuffer(this.vertexBuffer, 0, vertFloats);

    this.indexBuffer = this.device.createBuffer({
      label: 'surface-indices',
      size: indices.byteLength,
      usage: GPUBufferUsage.INDEX | GPUBufferUsage.COPY_DST,
    });
    this.device.queue.writeBuffer(this.indexBuffer, 0, indices);
  }

  // -----------------------------------------------------------------------
  // Camera
  // -----------------------------------------------------------------------

  /**
   * Rotate the camera by the given delta in screen pixels.
   */
  rotate(dx: number, dy: number): void {
    this.rotationY += dx * 0.005;
    this.rotationX += dy * 0.005;
    // Clamp vertical rotation to avoid flipping.
    this.rotationX = Math.max(-Math.PI / 2 + 0.01, Math.min(Math.PI / 2 - 0.01, this.rotationX));
  }

  /**
   * Zoom the camera by a scroll delta.
   */
  zoom(delta: number): void {
    this.zoomLevel = Math.max(1.0, Math.min(10.0, this.zoomLevel + delta * 0.01));
  }

  // -----------------------------------------------------------------------
  // Rendering
  // -----------------------------------------------------------------------

  /**
   * Render the surface.
   *
   * If external view/projection matrices are supplied they override the
   * built-in orbit camera.
   */
  render(viewMatrix?: Float32Array, projMatrix?: Float32Array): void {
    if (
      !this.device ||
      !this.pipeline ||
      !this.context ||
      !this.bindGroup ||
      !this.uniformBuffer ||
      !this.vertexBuffer ||
      !this.indexBuffer ||
      !this.depthTexture
    ) {
      return;
    }

    const view = viewMatrix ?? this.buildViewMatrix();
    const proj = projMatrix ?? this.buildProjectionMatrix();
    const model = this.buildModelMatrix();

    // Pack uniforms.
    const data = new Float32Array(UNIFORM_SIZE / 4);
    data.set(view, 0);   // offset 0:  view (16 floats)
    data.set(proj, 16);  // offset 16: projection (16 floats)
    data.set(model, 32); // offset 32: model (16 floats)

    // light_dir (normalised).
    const lx = 0.5, ly = 1.0, lz = 0.3;
    const ll = Math.sqrt(lx * lx + ly * ly + lz * lz);
    data[48] = lx / ll;
    data[49] = ly / ll;
    data[50] = lz / ll;
    data[51] = 0; // pad

    // color_low (blue).
    data[52] = 0.15;
    data[53] = 0.3;
    data[54] = 0.8;
    data[55] = 0; // pad

    // color_high (red/orange).
    data[56] = 0.9;
    data[57] = 0.25;
    data[58] = 0.1;

    // value_range.
    data[59] = this.valueRange;

    this.device.queue.writeBuffer(this.uniformBuffer, 0, data);

    // Render pass.
    const colorView: GPUTextureView = this.context.getCurrentTexture().createView();
    const depthView: GPUTextureView = this.depthTexture.createView();

    const encoder: GPUCommandEncoder = this.device.createCommandEncoder({
      label: 'surface-encoder',
    });

    const pass: GPURenderPassEncoder = encoder.beginRenderPass({
      colorAttachments: [
        {
          view: colorView,
          clearValue: { r: 0.05, g: 0.05, b: 0.07, a: 1.0 },
          loadOp: 'clear',
          storeOp: 'store',
        },
      ],
      depthStencilAttachment: {
        view: depthView,
        depthClearValue: 1.0,
        depthLoadOp: 'clear',
        depthStoreOp: 'store',
      },
    });

    pass.setPipeline(this.pipeline);
    pass.setBindGroup(0, this.bindGroup);
    pass.setVertexBuffer(0, this.vertexBuffer);
    pass.setIndexBuffer(this.indexBuffer, 'uint32');
    pass.drawIndexed(this.indexCount);
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
      this.depthTexture?.destroy();
      this.depthTexture = this.createDepthTexture();
    }
  }

  // -----------------------------------------------------------------------
  // Cleanup
  // -----------------------------------------------------------------------

  destroy(): void {
    this.uniformBuffer?.destroy();
    this.vertexBuffer?.destroy();
    this.indexBuffer?.destroy();
    this.depthTexture?.destroy();
    this.uniformBuffer = null;
    this.vertexBuffer = null;
    this.indexBuffer = null;
    this.depthTexture = null;
    this.bindGroup = null;
    this.pipeline = null;
    this.context = null;
    this.device = null;
    this.initialized = false;
  }

  // -----------------------------------------------------------------------
  // Internal matrix helpers
  // -----------------------------------------------------------------------

  private createDepthTexture(): GPUTexture {
    return this.device!.createTexture({
      label: 'surface-depth',
      size: { width: this.canvas.width || 1, height: this.canvas.height || 1 },
      format: 'depth24plus',
      usage: GPUTextureUsage.RENDER_ATTACHMENT,
    });
  }

  /** Build a simple orbit-camera view matrix. */
  private buildViewMatrix(): Float32Array {
    const cosX = Math.cos(this.rotationX);
    const sinX = Math.sin(this.rotationX);
    const cosY = Math.cos(this.rotationY);
    const sinY = Math.sin(this.rotationY);

    const eyeX = this.zoomLevel * cosX * sinY;
    const eyeY = this.zoomLevel * sinX;
    const eyeZ = this.zoomLevel * cosX * cosY;

    return lookAt(eyeX, eyeY, eyeZ, 0, 0, 0, 0, 1, 0);
  }

  /** Build a perspective projection matrix. */
  private buildProjectionMatrix(): Float32Array {
    const aspect = (this.canvas.width || 1) / (this.canvas.height || 1);
    return perspective(Math.PI / 4, aspect, 0.1, 100);
  }

  /** Build a model matrix (identity — surface is already centred). */
  private buildModelMatrix(): Float32Array {
    return new Float32Array([
      1, 0, 0, 0,
      0, 1, 0, 0,
      0, 0, 1, 0,
      0, 0, 0, 1,
    ]);
  }
}

// ---------------------------------------------------------------------------
// Minimal matrix helpers (no external dependency)
// ---------------------------------------------------------------------------

function lookAt(
  eyeX: number, eyeY: number, eyeZ: number,
  targetX: number, targetY: number, targetZ: number,
  upX: number, upY: number, upZ: number,
): Float32Array {
  let fx = targetX - eyeX;
  let fy = targetY - eyeY;
  let fz = targetZ - eyeZ;
  let len = Math.sqrt(fx * fx + fy * fy + fz * fz) || 1;
  fx /= len; fy /= len; fz /= len;

  // side = forward x up
  let sx = fy * upZ - fz * upY;
  let sy = fz * upX - fx * upZ;
  let sz = fx * upY - fy * upX;
  len = Math.sqrt(sx * sx + sy * sy + sz * sz) || 1;
  sx /= len; sy /= len; sz /= len;

  // recalculate up = side x forward
  const ux = sy * fz - sz * fy;
  const uy = sz * fx - sx * fz;
  const uz = sx * fy - sy * fx;

  return new Float32Array([
    sx, ux, -fx, 0,
    sy, uy, -fy, 0,
    sz, uz, -fz, 0,
    -(sx * eyeX + sy * eyeY + sz * eyeZ),
    -(ux * eyeX + uy * eyeY + uz * eyeZ),
    -(-fx * eyeX + -fy * eyeY + -fz * eyeZ),
    1,
  ]);
}

function perspective(
  fovY: number,
  aspect: number,
  near: number,
  far: number,
): Float32Array {
  const f = 1.0 / Math.tan(fovY / 2);
  const rangeInv = 1.0 / (near - far);

  return new Float32Array([
    f / aspect, 0, 0, 0,
    0, f, 0, 0,
    0, 0, (near + far) * rangeInv, -1,
    0, 0, near * far * rangeInv * 2, 0,
  ]);
}
