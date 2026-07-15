// Trajectory-beam shader: each sampled trajectory segment (two engine-emitted points) is drawn
// as a camera-facing, world-sized *ribbon* with a soft glowing edge — so a run's optical-photon
// paths read as a bright beam bending through glass/water, not as thin 1-px scribbles the milky
// volumes hide. The segment positions and colour are engine output (wavelength→RGB for optical
// photons); the ribbon width + glow are the only rendering choices. group(0) = camera (shared
// 96-byte layout); group(1) = the beam half-width. Instance data is one segment: p0, colour,
// per-segment (width scale, opacity), p1. Those style values encode the sampled beam strength
// and an explicit air-vs-condensed-medium rendering choice; they never change the path.

struct Camera {
    view_proj : mat4x4<f32>,
    light_dir : vec4<f32>,
    eye_pos   : vec4<f32>,
};

struct Params {
    width : vec4<f32>,   // x = world-space beam half-width (mm), yzw unused
};

@group(0) @binding(0) var<uniform> camera : Camera;
@group(1) @binding(0) var<uniform> params : Params;

struct VsOut {
    @builtin(position) clip_pos : vec4<f32>,
    @location(0) color : vec3<f32>,
    @location(1) u     : f32,      // -1..1 across the ribbon width (for the soft edge)
    @location(2) opacity : f32,
};

@vertex
fn vs_main(
    @builtin(vertex_index) vid : u32,
    @location(0) p0    : vec3<f32>,
    @location(1) color : vec3<f32>,
    @location(2) style : vec2<f32>, // x=width scale, y=opacity
    @location(3) p1    : vec3<f32>,
) -> VsOut {
    // Per-corner: which endpoint (0=p0, 1=p1) and which side (-1/+1 across the width).
    var ends  = array<f32, 6>(0.0, 0.0, 1.0, 0.0, 1.0, 1.0);
    var sides = array<f32, 6>(-1.0, 1.0, 1.0, -1.0, 1.0, -1.0);
    let end = ends[vid];
    let side = sides[vid];

    let p = mix(p0, p1, end);
    var dir = p1 - p0;
    let dlen = length(dir);
    if (dlen < 1e-6) { dir = vec3<f32>(1.0, 0.0, 0.0); } else { dir = dir / dlen; }
    // Ribbon lies in the plane containing the segment, offset perpendicular to it toward the
    // screen (so it always faces the camera and keeps a constant apparent thickness).
    let view = normalize(camera.eye_pos.xyz - p);
    var offs = cross(dir, view);
    let olen = length(offs);
    if (olen < 1e-5) { offs = vec3<f32>(0.0, 1.0, 0.0); } else { offs = offs / olen; }

    let world = p + offs * (side * params.width.x * style.x);

    var out : VsOut;
    out.clip_pos = camera.view_proj * vec4<f32>(world, 1.0);
    out.color = color;
    out.u = side;
    out.opacity = style.y;
    return out;
}

@fragment
fn fs_main(in : VsOut) -> @location(0) vec4<f32> {
    // Soft round-profile beam: bright core, fading to the edge. Additive blend (set on the
    // pipeline) makes overlapping photon paths accumulate into a glowing beam.
    let edge = 1.0 - abs(in.u);
    let glow = edge * edge;
    return vec4<f32>(in.color * (0.35 + 0.65 * glow), glow * in.opacity);
}
