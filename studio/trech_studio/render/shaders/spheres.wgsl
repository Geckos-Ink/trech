// True-size spheres from engine-emitted centres, RGBA and radii. Shading is representation.
struct Camera {
    view_proj : mat4x4<f32>,
    light_dir : vec4<f32>,
    eye_pos : vec4<f32>,
};
@group(0) @binding(0) var<uniform> camera : Camera;
struct VsOut {
    @builtin(position) clip_pos : vec4<f32>,
    @location(0) normal : vec3<f32>,
    @location(1) color : vec4<f32>,
};
@vertex
fn vs_main(@location(0) position : vec3<f32>, @location(1) normal : vec3<f32>,
           @location(2) center : vec3<f32>, @location(3) color : vec4<f32>,
           @location(4) radius : f32) -> VsOut {
    var out : VsOut;
    out.clip_pos = camera.view_proj * vec4<f32>(center + radius * position, 1.0);
    out.normal = normal;
    out.color = color;
    return out;
}
@fragment
fn fs_main(in : VsOut) -> @location(0) vec4<f32> {
    let diffuse = max(dot(normalize(in.normal), normalize(camera.light_dir.xyz)), 0.0);
    return vec4<f32>(in.color.rgb * (0.35 + 0.65 * diffuse), in.color.a);
}
