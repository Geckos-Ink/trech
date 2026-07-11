// Line shader for the ground grid and (planned, ROADMAP M1) sampled particle trajectories.
// Shares the camera uniform layout with surface.wgsl (group(0), binding(0)).

struct Camera {
    view_proj : mat4x4<f32>,
    light_dir : vec4<f32>,
};

struct LineParams {
    color : vec4<f32>,
};

@group(0) @binding(0) var<uniform> camera : Camera;
@group(1) @binding(0) var<uniform> params : LineParams;

struct VsOut {
    @builtin(position) clip_pos : vec4<f32>,
    @location(0) color          : vec4<f32>,
};

@vertex
fn vs_main(@location(0) position : vec3<f32>) -> VsOut {
    var out : VsOut;
    out.clip_pos = camera.view_proj * vec4<f32>(position, 1.0);
    out.color = params.color;
    return out;
}

@fragment
fn fs_main(in : VsOut) -> @location(0) vec4<f32> {
    return in.color;
}
