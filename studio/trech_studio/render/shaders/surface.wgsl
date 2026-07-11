// Lit surface shader for scene volumes.
//
// naga (inside wgpu) cross-compiles this to SPIR-V for Vulkan (Linux/Windows) and MSL for
// Metal (macOS), so this one source runs natively everywhere. group(0) carries the camera +
// light (updated once per frame); group(1) carries per-volume model matrix + colour.

struct Camera {
    view_proj : mat4x4<f32>,
    light_dir : vec4<f32>,   // world-space direction TO the light (xyz), w unused
};

struct Model {
    model       : mat4x4<f32>,
    normal_mat  : mat4x4<f32>,  // inverse-transpose of model (upper 3x3 used)
    color       : vec4<f32>,    // rgba; a < 1.0 = translucent (from derived optics)
};

@group(0) @binding(0) var<uniform> camera : Camera;
@group(1) @binding(0) var<uniform> object : Model;

struct VsOut {
    @builtin(position) clip_pos : vec4<f32>,
    @location(0) normal_ws      : vec3<f32>,
    @location(1) color          : vec4<f32>,
};

@vertex
fn vs_main(
    @location(0) position : vec3<f32>,
    @location(1) normal   : vec3<f32>,
) -> VsOut {
    var out : VsOut;
    let world_pos = object.model * vec4<f32>(position, 1.0);
    out.clip_pos = camera.view_proj * world_pos;
    out.normal_ws = (object.normal_mat * vec4<f32>(normal, 0.0)).xyz;
    out.color = object.color;
    return out;
}

@fragment
fn fs_main(in : VsOut) -> @location(0) vec4<f32> {
    let n = normalize(in.normal_ws);
    let l = normalize(camera.light_dir.xyz);
    // Two-sided lighting so thin translucent shells stay visible from inside.
    let ndl = max(abs(dot(n, l)), 0.0);
    let ambient = 0.28;
    let shade = ambient + (1.0 - ambient) * ndl;
    return vec4<f32>(in.color.rgb * shade, in.color.a);
}
