// ---------------------------------------------------------------------------
// Heatmap rendering shaders — Scanify trading scanner
//
// Renders a 2-D grid of scalar values as a colour-mapped heatmap.
//   low  (blue)  ->  mid (neutral / dark)  ->  high (red/green)
// ---------------------------------------------------------------------------

// ---- Uniforms ----

struct HeatmapUniforms {
  // Grid dimensions (cols, rows) packed into xy.
  grid_size : vec2<f32>,
  // Value range: (min_value, max_value).
  value_range : vec2<f32>,
  // Canvas viewport in pixels (width, height).
  viewport : vec2<f32>,
  // 0 = red-blue diverging, 1 = green-red diverging.
  color_mode : f32,
  // Padding for 16-byte alignment.
  _pad : f32,
};

@group(0) @binding(0) var<uniform> uniforms : HeatmapUniforms;
@group(0) @binding(1) var<storage, read> values : array<f32>;

// ---- Vertex stage ----

struct VertexOutput {
  @builtin(position) position : vec4<f32>,
  @location(0) uv : vec2<f32>,
};

// Full-screen triangle trick: 3 hard-coded vertices cover the entire clip
// space without any vertex buffer.
@vertex
fn vs_main(@builtin(vertex_index) vertex_index : u32) -> VertexOutput {
  var out : VertexOutput;
  // Generate a large triangle that covers [-1, 1] in clip space.
  let x = f32(i32(vertex_index & 1u) * 4 - 1);
  let y = f32(i32(vertex_index >> 1u) * 4 - 1);
  out.position = vec4<f32>(x, y, 0.0, 1.0);
  // Map to [0, 1] UV space.
  out.uv = vec2<f32>((x + 1.0) * 0.5, (1.0 - y) * 0.5);
  return out;
}

// ---- Colour helpers ----

// Diverging colour ramp: blue -> dark -> red.
fn colour_blue_red(t : f32) -> vec3<f32> {
  // t in [0, 1].  0 = min (blue), 0.5 = mid (near black), 1 = max (red).
  let blue  = vec3<f32>(0.230, 0.299, 0.754);
  let mid   = vec3<f32>(0.085, 0.085, 0.105);
  let red   = vec3<f32>(0.706, 0.016, 0.150);

  if (t < 0.5) {
    return mix(blue, mid, t * 2.0);
  }
  return mix(mid, red, (t - 0.5) * 2.0);
}

// Diverging colour ramp: red (bearish) -> dark -> green (bullish).
fn colour_red_green(t : f32) -> vec3<f32> {
  let red   = vec3<f32>(0.800, 0.100, 0.100);
  let mid   = vec3<f32>(0.120, 0.120, 0.140);
  let green = vec3<f32>(0.100, 0.700, 0.250);

  if (t < 0.5) {
    return mix(red, mid, t * 2.0);
  }
  return mix(mid, green, (t - 0.5) * 2.0);
}

// ---- Fragment stage ----

@fragment
fn fs_main(in : VertexOutput) -> @location(0) vec4<f32> {
  let cols = u32(uniforms.grid_size.x);
  let rows = u32(uniforms.grid_size.y);

  // Determine which cell the fragment falls into.
  let col = u32(floor(in.uv.x * f32(cols)));
  let row = u32(floor(in.uv.y * f32(rows)));

  // Clamp to grid bounds.
  let c = min(col, cols - 1u);
  let r = min(row, rows - 1u);

  let idx = r * cols + c;
  let raw = values[idx];

  // Normalise to [0, 1].
  let lo  = uniforms.value_range.x;
  let hi  = uniforms.value_range.y;
  let range = hi - lo;
  var t : f32 = 0.5;
  if (range > 0.0) {
    t = clamp((raw - lo) / range, 0.0, 1.0);
  }

  // Choose colour ramp.
  var colour : vec3<f32>;
  if (uniforms.color_mode < 0.5) {
    colour = colour_blue_red(t);
  } else {
    colour = colour_red_green(t);
  }

  // Subtle grid lines: darken the edges of each cell.
  let cell_uv = fract(in.uv * uniforms.grid_size);
  let edge = smoothstep(0.0, 0.04, min(cell_uv.x, cell_uv.y))
           * smoothstep(0.0, 0.04, min(1.0 - cell_uv.x, 1.0 - cell_uv.y));
  colour *= mix(0.6, 1.0, edge);

  return vec4<f32>(colour, 1.0);
}
