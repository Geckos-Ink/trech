// Per-vertex-coloured shader for trajectory polylines and particle-frame point clouds.
// Positions are already world-space (millimetres), so only the camera uniform is needed —
// no per-object model matrix. Shares the camera layout with surface.wgsl (group(0)/binding(0)).

struct Camera {
    view_proj : mat4x4<f32>,
    light_dir : vec4<f32>,
};

@group(0) @binding(0) var<uniform> camera : Camera;

struct VsOut {
    @builtin(position) clip_pos : vec4<f32>,
    @location(0) color          : vec4<f32>,
};

@vertex
fn vs_main(@location(0) position : vec3<f32>, @location(1) color : vec3<f32>) -> VsOut {
    var out : VsOut;
    out.clip_pos = camera.view_proj * vec4<f32>(position, 1.0);
    out.color = vec4<f32>(color, 1.0);
    return out;
}

@fragment
fn fs_main(in : VsOut) -> @location(0) vec4<f32> {
    return in.color;
}
