"""Portable ray-marched display of emitted scalar grids. No inference or new physics."""
from collections import OrderedDict
from pathlib import Path
import numpy as np
import wgpu
from . import mesh as meshgen
from .density import mass_level
from .energy_palette import energy_rgb


class DensityVolume:
    def __init__(self, renderer):
        self.renderer = renderer
        self.device = renderer.device
        self.uniform = self.device.create_buffer(size=64, usage=wgpu.BufferUsage.UNIFORM|wgpu.BufferUsage.COPY_DST)
        self.sampler = self.device.create_sampler(mag_filter='linear', min_filter='linear')
        self.layout = self.device.create_bind_group_layout(entries=[
            {'binding':0,'visibility':wgpu.ShaderStage.VERTEX|wgpu.ShaderStage.FRAGMENT,'buffer':{'type':'uniform'}},
            {'binding':1,'visibility':wgpu.ShaderStage.FRAGMENT,'texture':{'sample_type':'float','view_dimension':'3d'}},
            {'binding':2,'visibility':wgpu.ShaderStage.FRAGMENT,'sampler':{'type':'filtering'}},
            {'binding':3,'visibility':wgpu.ShaderStage.FRAGMENT,'texture':{'sample_type':'float','view_dimension':'3d'}}])
        shader = self.device.create_shader_module(code=(Path(__file__).parent/'shaders/density.wgsl').read_text())
        self.pipeline = self.device.create_render_pipeline(
            layout=self.device.create_pipeline_layout(bind_group_layouts=[renderer._bgl_camera,self.layout]),
            vertex={'module':shader,'entry_point':'vs_main','buffers':[{'array_stride':24,'step_mode':'vertex',
                'attributes':[{'format':'float32x3','offset':0,'shader_location':0}]}]},
            primitive={'topology':'triangle-list','cull_mode':'back'},
            depth_stencil={'format':'depth24plus','depth_write_enabled':False,'depth_compare':'always'},
            fragment={'module':shader,'entry_point':'fs_main','targets':[{'format':renderer._render_format,'blend':renderer._alpha_blend()}]})
        cube = meshgen.box((1.,1.,1.))
        self.vbo = renderer._upload(cube.vertices,wgpu.BufferUsage.VERTEX)
        self.ibo = renderer._upload(cube.indices,wgpu.BufferUsage.INDEX)
        self.count = cube.index_count
        self.cache = OrderedDict()
        self.bind_group = None

    def prepare(self, density, display):
        key = id(density)
        resources = self.cache.pop(key,None)
        if resources is None:
            shape = density.values.shape
            maximum=max(float(np.max(np.abs(density.values))),1e-30)
            normalized=np.ascontiguousarray((density.values/maximum).transpose(2,1,0),dtype=np.float16)
            # queue.write_texture supports arbitrary row widths, but padding keeps all backends happy.
            padded_width=((shape[0]*2+255)//256)*128
            payload=np.zeros((shape[2],shape[1],padded_width),dtype=np.float16)
            payload[:,:,:shape[0]]=normalized
            texture=self.device.create_texture(size=shape,dimension='3d',format='r16float',
                usage=wgpu.TextureUsage.TEXTURE_BINDING|wgpu.TextureUsage.COPY_DST)
            self.device.queue.write_texture({'texture':texture},payload.tobytes(),
                {'offset':0,'bytes_per_row':padded_width*2,'rows_per_image':shape[1]},shape)
            rgb_texture=self.device.create_texture(size=shape,dimension='3d',format='rgba16float',
                usage=wgpu.TextureUsage.TEXTURE_BINDING|wgpu.TextureUsage.COPY_DST)
            rgb=np.zeros((shape[2],shape[1],shape[0],4),np.float16)
            if density.energy_components:
                mixed,_=energy_rgb(density.energy_components)
                rgb[:,:,:,:3]=mixed.reshape((*shape,3)).transpose(2,1,0,3)
            rgb[:,:,:,3]=1
            if density.quantity == 'scalar':
                rgb[:,:,:,3] = density.active_mask.transpose(2,1,0)
            rgb_width=((shape[0]*8+255)//256)*32
            rgb_payload=np.zeros((shape[2],shape[1],rgb_width,4),np.float16)
            rgb_payload[:,:,:shape[0]]=rgb
            self.device.queue.write_texture({'texture':rgb_texture},rgb_payload.tobytes(),
                {'offset':0,'bytes_per_row':rgb_width*8,'rows_per_image':shape[1]},shape)
            group=self.device.create_bind_group(layout=self.layout,entries=[
                {'binding':0,'resource':{'buffer':self.uniform,'offset':0,'size':64}},
                {'binding':1,'resource':texture.create_view(dimension='3d')},
                {'binding':2,'resource':self.sampler},
                {'binding':3,'resource':rgb_texture.create_view(dimension='3d')}])
            resources=(density,texture,group,rgb_texture)
        self.cache[key]=resources
        while len(self.cache)>4: self.cache.popitem(last=False)
        self.bind_group=resources[2]
        lo=density.origin-density.spacing*.5
        hi=lo+np.array(density.values.shape)*density.spacing
        index=round(display.slice_fraction*(density.values.shape[display.axis]-1))
        fraction=(index+.5)/density.values.shape[display.axis]
        level=mass_level(density,display.mass_percent)
        cutoff=level["threshold"]/max(float(np.max(np.abs(density.values))),1e-30) if level else 0.0
        low, high, kind = -display.decades, 0, 2.0 if display.mode=='levels' and density.energy_components else float(density.quantity=='density_difference')
        if density.quantity == 'scalar':
            maximum=max(float(np.max(np.abs(density.values))),1e-30)
            low,high = np.asarray(density.scalar_range)/maximum
            kind,cutoff = 3.0,0.0
        payload=np.array([*lo,0,*hi,cutoff,low,high,display.opacity,kind,
                          display.axis,fraction,(1.0 if display.mode=='slice' else 2.0 if display.cutaway else 0.0),density.spacing],dtype=np.float32)
        self.device.queue.write_buffer(self.uniform,0,payload)

    def draw(self, render_pass):
        if self.bind_group is None: return
        render_pass.set_pipeline(self.pipeline)
        render_pass.set_bind_group(0,self.renderer._camera_bind_group)
        render_pass.set_bind_group(1,self.bind_group)
        render_pass.set_vertex_buffer(0,self.vbo)
        render_pass.set_index_buffer(self.ibo,'uint32')
        render_pass.draw_indexed(self.count,1,0,0,0)
