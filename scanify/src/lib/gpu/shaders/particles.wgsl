// ---------------------------------------------------------------------------
// Particle system shaders — Scanify trading scanner
//
// Compute shader : updates particle positions with velocity, gravity, and
//                  attraction towards an attractor point.
// Vertex shader  : billboard point sprites facing the camera.
// Fragment shader: circular falloff with colour derived from remaining life.
// ---------------------------------------------------------------------------

// ---- Shared structures ----

struct Particle {
  pos      : vec2<f32>,
  vel      : vec2<f32>,
  color    : vec4<f32>,
  life     : f32,
  max_life : f32,
  _pad0    : f32,
  _pad1    : f32,
};

// ---- Compute shader ----

struct SimParams {
  delta_time      : f32,
  attractor_x     : f32,
  attractor_y     : f32,
  attractor_str   : f32,
  damping         : f32,
  gravity_y       : f32,
  particle_count  : u32,
  _pad            : u32,
};

@group(0) @binding(0) var<uniform>            sim : SimParams;
@group(0) @binding(1) var<storage, read_write> particles : array<Particle>;

@compute @workgroup_size(64)
fn cs_update(@builtin(global_invocation_id) gid : vec3<u32>) {
  let idx = gid.x;
  if (idx >= sim.particle_count) { return; }

  var p = particles[idx];

  // Skip dead particles.
  if (p.life <= 0.0) {
    return;
  }

  // Gravity (constant downward pull).
  p.vel.y = p.vel.y - sim.gravity_y * sim.delta_time;

  // Attraction towards the attractor point.
  let attractor = vec2<f32>(sim.attractor_x, sim.attractor_y);
  let diff = attractor - p.pos;
  let dist = max(length(diff), 0.01);
  let attract_force = normalize(diff) * sim.attractor_str / (dist + 1.0);
  p.vel = p.vel + attract_force * sim.delta_time;

  // Damping.
  p.vel = p.vel * sim.damping;

  // Integrate position.
  p.pos = p.pos + p.vel * sim.delta_time;

  // Age the particle.
  p.life = p.life - sim.delta_time;

  // Fade colour alpha based on remaining life fraction.
  let life_frac = clamp(p.life / p.max_life, 0.0, 1.0);
  p.color.a = life_frac;

  // Warm-up glow: shift hue towards white near birth.
  let birth_frac = 1.0 - life_frac;
  if (birth_frac < 0.1) {
    let warm = (0.1 - birth_frac) / 0.1;
    p.color = vec4<f32>(
      mix(p.color.r, 1.0, warm * 0.4),
      mix(p.color.g, 1.0, warm * 0.4),
      mix(p.color.b, 1.0, warm * 0.4),
      p.color.a,
    );
  }

  particles[idx] = p;
}

// ---- Vertex shader (billboard point sprites) ----

struct RenderUniforms {
  viewport   : vec2<f32>,
  point_size : f32,
  _pad       : f32,
};

@group(0) @binding(0) var<uniform>        render : RenderUniforms;
@group(0) @binding(1) var<storage, read>  render_particles : array<Particle>;

struct VertexOutput {
  @builtin(position) position : vec4<f32>,
  @location(0)       v_color  : vec4<f32>,
  @location(1)       uv       : vec2<f32>,
};

@vertex
fn vs_main(
  @builtin(vertex_index)   vid : u32,
  @builtin(instance_index) iid : u32,
) -> VertexOutput {
  let p = render_particles[iid];

  // Six vertices forming a screen-aligned quad.
  var quad = array<vec2<f32>, 6>(
    vec2<f32>(-1.0, -1.0),
    vec2<f32>( 1.0, -1.0),
    vec2<f32>(-1.0,  1.0),
    vec2<f32>(-1.0,  1.0),
    vec2<f32>( 1.0, -1.0),
    vec2<f32>( 1.0,  1.0),
  );

  let q = quad[vid];

  // Scale the quad by point size in pixel space, then convert to NDC.
  let size_ndc = render.point_size / render.viewport;
  let clip_pos = p.pos + q * size_ndc;

  var out : VertexOutput;
  out.position = vec4<f32>(clip_pos, 0.0, 1.0);
  out.v_color = p.color;
  out.uv = q;
  return out;
}

// ---- Fragment shader (circular falloff) ----

@fragment
fn fs_main(fin : VertexOutput) -> @location(0) vec4<f32> {
  // Distance from centre of the quad [0, sqrt(2)].
  let dist = length(fin.uv);

  // Discard fragments outside the unit circle.
  if (dist > 1.0) {
    discard;
  }

  // Smooth circular falloff.
  let falloff = 1.0 - smoothstep(0.0, 1.0, dist);

  // Core glow: brighter near the centre.
  let glow = exp(-dist * dist * 3.0);
  let brightness = mix(falloff, glow, 0.5);

  let alpha = brightness * fin.v_color.a;

  return vec4<f32>(fin.v_color.rgb * brightness, alpha);
}
