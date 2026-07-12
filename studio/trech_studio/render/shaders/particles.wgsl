// Particle-cloud sprite shader (fluid_frame clouds, e.g. the shaken glass of water).
//
// Each engine-emitted particle position is drawn as a *camera-facing, world-sized* round
// sprite (a billboard) instead of a 1-px point, so a dense cloud reads as a cohesive body of
// water rather than sparse noise. The sprite size (params.radius) is a rendering choice derived
// from the cloud's own spacing — it moves no particle, it only makes each one visible; the true
// metaball isosurface is ROADMAP M3. group(0) = camera (shared 96-byte layout: view_proj +
// light + eye); group(1) = the sprite radius. Instance data is one (center, colour) per particle.

struct Camera {
    view_proj : mat4x4<f32>,
    light_dir : vec4<f32>,
    eye_pos   : vec4<f32>,
};

struct Params {
    radius : vec4<f32>,   // x = world-space sprite radius (mm), yzw unused
};

@group(0) @binding(0) var<uniform> camera : Camera;
@group(1) @binding(0) var<uniform> params : Params;

struct VsOut {
    @builtin(position) clip_pos : vec4<f32>,
    @location(0) color : vec3<f32>,
    @location(1) uv    : vec2<f32>,
};

@vertex
fn vs_main(
    @builtin(vertex_index) vid : u32,
    @location(0) center : vec3<f32>,
    @location(1) color  : vec3<f32>,
) -> VsOut {
    // Two triangles → a unit quad in the billboard plane.
    var corners = array<vec2<f32>, 6>(
        vec2<f32>(-1.0, -1.0), vec2<f32>(1.0, -1.0), vec2<f32>(1.0, 1.0),
        vec2<f32>(-1.0, -1.0), vec2<f32>(1.0, 1.0), vec2<f32>(-1.0, 1.0),
    );
    let c = corners[vid];

    // Camera-facing basis from the eye position (no view matrix needed).
    let facing = normalize(camera.eye_pos.xyz - center);
    let world_up = vec3<f32>(0.0, 1.0, 0.0);
    var right = cross(world_up, facing);
    let rlen = length(right);
    if (rlen < 1e-4) {
        right = vec3<f32>(1.0, 0.0, 0.0);
    } else {
        right = right / rlen;
    }
    let up = cross(facing, right);

    let world = center + (c.x * right + c.y * up) * params.radius.x;

    var out : VsOut;
    out.clip_pos = camera.view_proj * vec4<f32>(world, 1.0);
    out.color = color;
    out.uv = c;
    return out;
}

@fragment
fn fs_main(in : VsOut) -> @location(0) vec4<f32> {
    let r2 = dot(in.uv, in.uv);
    if (r2 > 1.0) {
        discard;
    }
    // Soft round droplet: alpha fades to the rim, a brighter core gives the cloud volume.
    let a = smoothstep(1.0, 0.15, r2) * 0.85;
    let core = 0.65 + 0.35 * (1.0 - r2);
    return vec4<f32>(in.color * core, a);
}
