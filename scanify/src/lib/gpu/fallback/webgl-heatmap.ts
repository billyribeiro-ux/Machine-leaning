// ---------------------------------------------------------------------------
// WebGL 2 heatmap fallback renderer
//
// Provides a GPU-accelerated heatmap when WebGPU is not available but
// WebGL 2 is supported.  Uses a single full-screen quad with a fragment
// shader that samples a data texture and maps values through a colour ramp.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// GLSL shaders
// ---------------------------------------------------------------------------

const VERTEX_SHADER_SRC = /* glsl */ `#version 300 es
precision highp float;

// Full-screen triangle trick — no vertex buffer needed.
// gl_VertexID: 0, 1, 2 covers the entire clip space.
void main() {
  float x = float((gl_VertexID & 1) << 2) - 1.0;
  float y = float((gl_VertexID & 2) << 1) - 1.0;
  gl_Position = vec4(x, y, 0.0, 1.0);
}
`;

const FRAGMENT_SHADER_SRC = /* glsl */ `#version 300 es
precision highp float;

uniform sampler2D u_data;
uniform vec2 u_resolution;    // canvas width, canvas height
uniform vec2 u_gridSize;      // data columns, data rows
uniform float u_minValue;
uniform float u_maxValue;

out vec4 fragColor;

// Five-stop colour ramp: deep blue -> cyan -> green -> yellow -> red
vec3 heatmapColor(float t) {
  t = clamp(t, 0.0, 1.0);

  vec3 c0 = vec3(0.05, 0.05, 0.35);  // deep blue
  vec3 c1 = vec3(0.00, 0.60, 0.75);  // cyan
  vec3 c2 = vec3(0.10, 0.75, 0.25);  // green
  vec3 c3 = vec3(0.95, 0.85, 0.10);  // yellow
  vec3 c4 = vec3(0.90, 0.15, 0.10);  // red

  if (t < 0.25) return mix(c0, c1, t / 0.25);
  if (t < 0.50) return mix(c1, c2, (t - 0.25) / 0.25);
  if (t < 0.75) return mix(c2, c3, (t - 0.50) / 0.25);
  return mix(c3, c4, (t - 0.75) / 0.25);
}

void main() {
  // Map fragment coordinate to data-texture UV.
  vec2 uv = gl_FragCoord.xy / u_resolution;
  uv.y = 1.0 - uv.y;  // flip Y so row 0 is at the top

  // Determine which cell we are in for grid lines.
  vec2 cellUV = fract(uv * u_gridSize);
  float edgeFactor = smoothstep(0.0, 0.03, min(cellUV.x, cellUV.y))
                   * smoothstep(0.0, 0.03, min(1.0 - cellUV.x, 1.0 - cellUV.y));

  float rawValue = texture(u_data, uv).r;

  // Normalise into [0, 1] based on the data range.
  float range = u_maxValue - u_minValue;
  float t = range > 0.0 ? (rawValue - u_minValue) / range : 0.5;

  vec3 color = heatmapColor(t);
  // Darken edges slightly to create a grid effect.
  color *= mix(0.7, 1.0, edgeFactor);
  fragColor = vec4(color, 1.0);
}
`;

// ---------------------------------------------------------------------------
// Renderer class
// ---------------------------------------------------------------------------

export class WebGLHeatmapRenderer {
  private gl: WebGL2RenderingContext | null = null;
  private program: WebGLProgram | null = null;
  private vao: WebGLVertexArrayObject | null = null;
  private dataTexture: WebGLTexture | null = null;

  // Uniform locations
  private uResolution: WebGLUniformLocation | null = null;
  private uGridSize: WebGLUniformLocation | null = null;
  private uMinValue: WebGLUniformLocation | null = null;
  private uMaxValue: WebGLUniformLocation | null = null;
  private uData: WebGLUniformLocation | null = null;

  private dataWidth = 0;
  private dataHeight = 0;
  private currentMin = 0;
  private currentMax = 1;
  private initialized = false;

  // -----------------------------------------------------------------------
  // Lifecycle
  // -----------------------------------------------------------------------

  /**
   * Initialise shaders, program, and GPU resources.
   *
   * @param gl  A live WebGL2RenderingContext.
   * @returns `true` on success.
   */
  init(gl: WebGL2RenderingContext): boolean {
    try {
      this.gl = gl;

      // Compile shaders ---------------------------------------------------
      const vs = this.compileShader(gl, gl.VERTEX_SHADER, VERTEX_SHADER_SRC);
      const fs = this.compileShader(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER_SRC);
      if (!vs || !fs) return false;

      // Link program ------------------------------------------------------
      const program = gl.createProgram();
      if (!program) return false;
      gl.attachShader(program, vs);
      gl.attachShader(program, fs);
      gl.linkProgram(program);

      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        console.error('[WebGLHeatmap] Program link error:', gl.getProgramInfoLog(program));
        gl.deleteProgram(program);
        return false;
      }

      this.program = program;

      // Uniform locations --------------------------------------------------
      this.uResolution = gl.getUniformLocation(program, 'u_resolution');
      this.uGridSize = gl.getUniformLocation(program, 'u_gridSize');
      this.uMinValue = gl.getUniformLocation(program, 'u_minValue');
      this.uMaxValue = gl.getUniformLocation(program, 'u_maxValue');
      this.uData = gl.getUniformLocation(program, 'u_data');

      // Empty VAO (full-screen triangle uses gl_VertexID) -----------------
      this.vao = gl.createVertexArray();

      // Data texture (R32F, single-channel float) -------------------------
      this.dataTexture = gl.createTexture();
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, this.dataTexture);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.bindTexture(gl.TEXTURE_2D, null);

      // Clean up individual shaders (they are linked into the program).
      gl.deleteShader(vs);
      gl.deleteShader(fs);

      this.initialized = true;
      return true;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error(`[WebGLHeatmap] init failed: ${msg}`);
      return false;
    }
  }

  // -----------------------------------------------------------------------
  // Data upload
  // -----------------------------------------------------------------------

  /**
   * Upload a new data grid.
   *
   * @param values  A flat Float32Array or number[] of size w * h.
   * @param w       Grid width (columns).
   * @param h       Grid height (rows).
   */
  setData(values: Float32Array | number[], w: number, h: number): void {
    const gl = this.gl;
    if (!gl || !this.dataTexture) return;

    this.dataWidth = w;
    this.dataHeight = h;

    const floatData = values instanceof Float32Array ? values : new Float32Array(values);

    // Auto-detect value range.
    let min = Infinity;
    let max = -Infinity;
    for (let i = 0; i < floatData.length; i++) {
      const v = floatData[i] as number;
      if (v < min) min = v;
      if (v > max) max = v;
    }
    this.currentMin = Number.isFinite(min) ? min : 0;
    this.currentMax = Number.isFinite(max) ? max : 1;

    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.dataTexture);
    gl.texImage2D(
      gl.TEXTURE_2D,
      0,
      gl.R32F,
      w,
      h,
      0,
      gl.RED,
      gl.FLOAT,
      floatData,
    );
    gl.bindTexture(gl.TEXTURE_2D, null);
  }

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  /**
   * Draw the heatmap to the current framebuffer.
   *
   * @param minValue  Optional override for the cold end of the colour ramp.
   * @param maxValue  Optional override for the hot end of the colour ramp.
   */
  render(minValue?: number, maxValue?: number): void {
    const gl = this.gl;
    if (!gl || !this.program || !this.vao || !this.dataTexture) return;

    const lo = minValue ?? this.currentMin;
    const hi = maxValue ?? this.currentMax;

    gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight);
    gl.clearColor(0.03, 0.03, 0.05, 1.0);
    gl.clear(gl.COLOR_BUFFER_BIT);

    gl.useProgram(this.program);

    // Bind data texture on unit 0.
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.dataTexture);
    gl.uniform1i(this.uData, 0);

    // Set uniforms.
    gl.uniform2f(this.uResolution, gl.drawingBufferWidth, gl.drawingBufferHeight);
    gl.uniform2f(this.uGridSize, this.dataWidth, this.dataHeight);
    gl.uniform1f(this.uMinValue, lo);
    gl.uniform1f(this.uMaxValue, hi);

    // Draw full-screen triangle (3 vertices, no buffer needed).
    gl.bindVertexArray(this.vao);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.bindVertexArray(null);
  }

  // -----------------------------------------------------------------------
  // Cleanup
  // -----------------------------------------------------------------------

  /**
   * Destroy all GPU resources.
   */
  destroy(): void {
    const gl = this.gl;
    if (!gl) return;

    if (this.program) {
      gl.deleteProgram(this.program);
      this.program = null;
    }
    if (this.vao) {
      gl.deleteVertexArray(this.vao);
      this.vao = null;
    }
    if (this.dataTexture) {
      gl.deleteTexture(this.dataTexture);
      this.dataTexture = null;
    }

    this.uResolution = null;
    this.uGridSize = null;
    this.uMinValue = null;
    this.uMaxValue = null;
    this.uData = null;
    this.gl = null;
    this.initialized = false;
  }

  // -----------------------------------------------------------------------
  // Internal
  // -----------------------------------------------------------------------

  private compileShader(
    gl: WebGL2RenderingContext,
    type: GLenum,
    source: string,
  ): WebGLShader | null {
    const shader = gl.createShader(type);
    if (!shader) return null;

    gl.shaderSource(shader, source);
    gl.compileShader(shader);

    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const kind = type === gl.VERTEX_SHADER ? 'vertex' : 'fragment';
      console.error(`[WebGLHeatmap] ${kind} shader compile error:`, gl.getShaderInfoLog(shader));
      gl.deleteShader(shader);
      return null;
    }

    return shader;
  }
}
