// Display transfer of recorded scalar data; alpha is not material absorption.
struct Camera { view_proj: mat4x4<f32>, light_dir: vec4<f32>, eye_pos: vec4<f32> };
struct Field { lo: vec4<f32>, hi: vec4<f32>, transfer: vec4<f32>, slice: vec4<f32> };
@group(0) @binding(0) var<uniform> camera: Camera;
@group(1) @binding(0) var<uniform> field: Field;
@group(1) @binding(1) var density: texture_3d<f32>;
@group(1) @binding(2) var smooth_sampler: sampler;
@group(1) @binding(3) var energy_colors: texture_3d<f32>;
struct Vertex { @builtin(position) clip: vec4<f32>, @location(0) world: vec3<f32> };
@vertex fn vs_main(@location(0) position: vec3<f32>) -> Vertex {
    var out: Vertex;
    out.world = mix(field.lo.xyz, field.hi.xyz, position + vec3<f32>(0.5));
    out.clip = camera.view_proj * vec4<f32>(out.world, 1.0);
    return out;
}
fn palette(t: f32, sign_value: f32) -> vec3<f32> {
    if field.transfer.w > 0.5 && field.transfer.w < 1.5 {
        return select(vec3<f32>(0.18,0.66,1.0), vec3<f32>(1.0,0.43,0.16), sign_value >= 0.0) * pow(t,0.55);
    }
    let x = t*4.0;
    if x < 1.0 { return mix(vec3<f32>(0.03,0.025,0.13),vec3<f32>(0.22,0.08,0.45),x); }
    if x < 2.0 { return mix(vec3<f32>(0.22,0.08,0.45),vec3<f32>(0.11,0.52,0.67),x-1.0); }
    if x < 3.0 { return mix(vec3<f32>(0.11,0.52,0.67),vec3<f32>(0.39,0.84,0.49),x-2.0); }
    return mix(vec3<f32>(0.39,0.84,0.49),vec3<f32>(1.0,0.91,0.35),x-3.0);
}
fn field_color(world: vec3<f32>, t: f32, value: f32) -> vec3<f32> {
    if field.transfer.w > 1.5 && field.transfer.w < 2.5 {
        return textureSampleLevel(energy_colors,smooth_sampler,(world-field.lo.xyz)/(field.hi.xyz-field.lo.xyz),0.0).rgb * (0.18+0.82*t);
    }
    return palette(t,value);
}
fn read_value(world: vec3<f32>) -> f32 {
    return textureSampleLevel(density, smooth_sampler, (world-field.lo.xyz)/(field.hi.xyz-field.lo.xyz),0.0).r;
}
fn intensity(value: f32) -> f32 {
    if field.transfer.w > 2.5 {
        return clamp((value-field.transfer.x)/(field.transfer.y-field.transfer.x),0.0,1.0);
    }
    if abs(field.slice.z-1.0) > 0.1 && abs(value) < field.hi.w { return 0.0; }
    // Texture is scaled to its maximum absolute value for portable float16 filtering.
    return clamp((log2(max(abs(value),1e-30))/log2(10.0)-field.transfer.x)/(field.transfer.y-field.transfer.x),0.0,1.0);
}
@fragment fn fs_main(in: Vertex) -> @location(0) vec4<f32> {
    var direction = normalize(in.world-camera.eye_pos.xyz);
    var origin = camera.eye_pos.xyz;
    if camera.eye_pos.w < 0.5 {
        // The depth row of the view-projection matrix points along camera forward.
        // Parallel rays start at each fragment's projection onto the eye plane.
        direction = normalize(vec3<f32>(camera.view_proj[0].z,camera.view_proj[1].z,camera.view_proj[2].z));
        origin = in.world-direction*dot(in.world-camera.eye_pos.xyz,direction);
    }
    // Rays parallel to a slab use a small signed epsilon only for intersection arithmetic.
    let safe_direction = select(vec3<f32>(-1e-7),vec3<f32>(1e-7), direction>=vec3<f32>(0.0));
    let inverse = 1.0 / select(safe_direction,direction,abs(direction)>vec3<f32>(1e-7));
    let a=(field.lo.xyz-origin)*inverse;
    let b=(field.hi.xyz-origin)*inverse;
    let entry=max(max(min(a.x,b.x),min(a.y,b.y)),min(a.z,b.z));
    let exit=min(min(max(a.x,b.x),max(a.y,b.y)),max(a.z,b.z));
    if exit<=max(entry,0.0) { discard; }
    if field.slice.z>0.5 && field.slice.z<1.5 {
        let axis=u32(field.slice.x);
        let plane=mix(field.lo[axis],field.hi[axis],field.slice.y);
        let t=(plane-origin[axis])*inverse[axis];
        if t<max(entry,0.0) || t>exit { discard; }
        let value=read_value(origin+t*direction);
        if field.transfer.w>2.5 && textureSampleLevel(energy_colors,smooth_sampler,(origin+t*direction-field.lo.xyz)/(field.hi.xyz-field.lo.xyz),0.0).a<0.5 { discard; }
        let c=intensity(value);
        // Faint log iso-contours make gradient magnitude legible on a slice.
        let contour=abs(fract(c*8.0)-0.5);
        let rgb=field_color(origin+t*direction,c,value)*select(0.7,1.0,contour>0.04);
        return vec4<f32>(rgb,1.0-exp(-4.688*field.transfer.z));
    }
    // Expose the sampled cut face rather than hiding the core behind outer opacity.
    // Its colors are the same recorded field values as the numeric 2D section.
    if field.slice.z>1.5 {
        let axis=u32(field.slice.x);
        let plane=mix(field.lo[axis],field.hi[axis],field.slice.y);
        let t=(plane-origin[axis])*inverse[axis];
        if origin[axis]>plane && t>=max(entry,0.0) && t<=exit {
            let point=origin+t*direction;
            let value=read_value(point);
            let c=intensity(value);
            if c>0.0 { return vec4<f32>(field_color(point,c,value),1.0-exp(-4.688*field.transfer.z)); }
        }
    }
    let start=max(entry,0.0);
    let step_size=(exit-start)/128.0;
    var color=vec3<f32>(0.0);
    var alpha=0.0;
    for(var i=0u;i<128u;i++) {
        let point=origin+(start+(f32(i)+0.5)*step_size)*direction;
        let axis=u32(field.slice.x);
        if field.slice.z>1.5 && point[axis]>mix(field.lo[axis],field.hi[axis],field.slice.y) { continue; }
        let value=read_value(point);
        if field.transfer.w>2.5 && textureSampleLevel(energy_colors,smooth_sampler,(point-field.lo.xyz)/(field.hi.xyz-field.lo.xyz),0.0).a<0.5 { continue; }
        let t=intensity(value);
        let exponent=select(1.2,2.7,field.transfer.w>1.5 && field.transfer.w<2.5);
        let opacity=1.0-exp(-field.transfer.z*pow(t,exponent)*step_size/field.slice.w);
        color+=(1.0-alpha)*opacity*field_color(point,t,value);
        alpha+=(1.0-alpha)*opacity;
        if alpha>0.985 { break; }
    }
    if alpha<0.003 { discard; }
    return vec4<f32>(color/max(alpha,1e-6),alpha);
}
