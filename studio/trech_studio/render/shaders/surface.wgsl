// Lit surface shader for scene volumes.
//
// naga (inside wgpu) cross-compiles this to SPIR-V for Vulkan (Linux/Windows) and MSL for
// Metal (macOS), so this one source runs natively everywhere. group(0) carries the camera +
// light + eye (updated once per frame); group(1) carries per-volume model matrix + colour +
// surface params derived from the run's optics (Fresnel reflectance, gloss, emissive flag).

struct Camera {
    view_proj : mat4x4<f32>,
    light_dir : vec4<f32>,   // world-space direction TO the light (xyz), w unused
    eye_pos   : vec4<f32>,   // world-space camera position (xyz), for the specular view vector
};

struct Model {
    model       : mat4x4<f32>,
    normal_mat  : mat4x4<f32>,  // inverse-transpose of model (upper 3x3 used)
    color       : vec4<f32>,    // rgba; a < 1.0 = translucent (Beer–Lambert from derived optics)
    params      : vec4<f32>,    // x = Fresnel R0, y = gloss(0..1), z = emissive, w unused
};

@group(0) @binding(0) var<uniform> camera : Camera;
@group(1) @binding(0) var<uniform> object : Model;

struct VsOut {
    @builtin(position) clip_pos : vec4<f32>,
    @location(0) normal_ws      : vec3<f32>,
    @location(1) color          : vec4<f32>,
    @location(2) world_pos      : vec3<f32>,
    @location(3) params         : vec4<f32>,
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
    out.world_pos = world_pos.xyz;
    out.params = object.params;
    return out;
}

@fragment
fn fs_main(in : VsOut) -> @location(0) vec4<f32> {
    let n = normalize(in.normal_ws);
    let l = normalize(camera.light_dir.xyz);
    let parallel_view = -normalize(vec3<f32>(camera.view_proj[0].z,camera.view_proj[1].z,camera.view_proj[2].z));
    let v = select(parallel_view,normalize(camera.eye_pos.xyz - in.world_pos),camera.eye_pos.w > 0.5);

    // Emissive bodies (emitters / viz_emissive) are self-lit: skip shading entirely.
    if (in.params.z > 0.5) {
        return in.color;
    }

    // Two-sided diffuse so thin translucent shells stay visible from inside.
    let nl = max(abs(dot(n, l)), 0.0);
    let ambient = 0.20;
    let diffuse = ambient + (1.0 - ambient) * nl;

    // Scalar-field contours use only display lighting and fixed alpha. Their
    // colour encodes phase/contour, never optical Fresnel/material behaviour.
    if in.params.w > 0.5 {
        return vec4<f32>(in.color.rgb*(0.4+0.6*nl),in.color.a);
    }

    // Fresnel–Schlick reflectance grows toward grazing angles: this is how glass/water "reflect
    // photons". R0 (params.x) comes from the derived refractive index; gloss (params.y) tightens
    // the highlight. Higher-index media get brighter, tighter speculars — glass reads glassy.
    let r0 = in.params.x;
    let gloss = in.params.y;
    // Two-sided shells need the angle on either face. Clamping a back face to zero
    // makes its Fresnel term one everywhere and turns a clear vessel into a milky wall.
    let ndv = abs(dot(n, v));
    let fresnel = r0 + (1.0 - r0) * pow(1.0 - ndv, 5.0);

    let h = normalize(l + v);
    let ndh = max(abs(dot(n, h)), 0.0);
    let shininess = mix(16.0, 128.0, gloss);
    let spec = pow(ndh, shininess) * (0.25 + 8.0 * r0);

    // A clear medium (low base alpha) must stay genuinely see-through so a beam behind/inside it
    // reads — otherwise its flat faces (front+back, plus any overlapping volume) stack into an
    // opaque "milk". So suppress the flat diffuse fill for clear media and let the Fresnel *rim*
    // + specular carry the glass's shape: the body is barely there, the silhouette/highlights
    // define it, exactly like real glass. Opaque bodies (clearness→0) keep their full shading.
    let base_a = in.color.a;
    let clearness = clamp(1.0 - base_a, 0.0, 1.0);
    let body = in.color.rgb * diffuse * mix(1.0, 0.30, clearness);
    let lit = body + vec3<f32>(spec + fresnel * 0.5);
    // Flat faces sit near the (low) base alpha; the grazing rim + specular add opacity only at the
    // edges/highlights, so the outline reads glassy without the whole body going milky.
    let alpha = clamp(base_a * mix(1.0, 0.55, clearness) + fresnel * clearness * 0.45 + spec,
                      0.0, 1.0);
    return vec4<f32>(lit, alpha);
}

// Explicit material class RGBA is a display palette, separate from optical material laws.
@vertex
fn vs_colored(
    @location(0) position : vec3<f32>,
    @location(1) normal : vec3<f32>,
    @location(2) color : vec4<f32>,
) -> VsOut {
    var out : VsOut;
    let world_pos = object.model * vec4<f32>(position, 1.0);
    out.clip_pos = camera.view_proj * world_pos;
    out.normal_ws = (object.normal_mat * vec4<f32>(normal, 0.0)).xyz;
    out.color = color;
    out.world_pos = world_pos.xyz;
    out.params = object.params;
    return out;
}
