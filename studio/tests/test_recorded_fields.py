"""Recorded grids/meshes retain their axes, units and held geometry; no physical validation."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from trech_studio.render.playback import build_material_frame_playback
from trech_studio.render.scalar import scalar_grid
from trech_studio.render.interfaces import interface_mesh
from trech_studio.render.metaballs import DensityGrid, density_surface_mesh
from trech_studio.render.camera import Camera, orthographic_wgpu
from trech_studio.render.scalar import recorded_projection


def grid():
    return dict(schema='trech_scalar_grid_v1',shape=[3,4,5],order='x_fastest',origin=[1,2,3],spacing=2,
        values=list(range(60)),active_mask=[True]*60,unit='K',source='Synthetic grid fixture',
        display=dict(mode='slice',low=0,high=60,opacity=.2,isovalue=30,axis='z',fraction=.25))


def test_axis_order_mask_and_display():
    raw=grid();raw['active_mask'][1]=False
    density,display=scalar_grid(raw,'y')
    assert density.values[2,3,4]==59
    assert not density.active_mask[1,0,0] and density.values[1,0,0]==0
    assert density.scalar_range==(0,60) and display.axis==2 and display.opacity==.2
    zup,remapped=scalar_grid(grid(),'z')
    assert zup.values.shape==(3,5,4)
    assert zup.values[2,4,0]==59
    assert np.array_equal(zup.origin,[1,3,-8]) and remapped.axis==1


@pytest.mark.parametrize('change',[
    lambda d:d.update(values=[1]),lambda d:d.update(spacing=0),
    lambda d:d.update(active_mask=[1]*60),lambda d:d['values'].__setitem__(2,float('nan')),
    lambda d:d.update(source=''),lambda d:d['display'].update(opacity=2),
    lambda d:d['display'].update(high=0),lambda d:d.update(shape=[3,4,True]),
])
def test_invalid_grid_rejected(change):
    raw=grid();change(raw)
    with pytest.raises(ValueError):scalar_grid(raw,'y')


def test_camera_and_grid_on_held_frames():
    payload=dict(stream='test',positions_mm=[],colors_rgba=[],time_s=0,scalar_field=grid(),up_axis='y',
        render_camera=dict(yaw_deg=70,pitch_deg=20),show_geant4_scene=False)
    pb=build_material_frame_playback([SimpleNamespace(tag='material_frame',payload=payload)])
    assert pb.frames[0].camera==(70,20) and pb.frames[0].density.density_unit=='K'
    assert pb.frames[0].camera_projection=='perspective'
    assert np.allclose(pb.particle_bounds()[0],[0,1,2])
    assert np.allclose(pb.particle_bounds()[1],[6,9,12])


def test_orthographic_projection_depth_and_parallel_size():
    p=orthographic_wgpu(4,2,.5,100)
    assert np.allclose(p@np.array([4,2,-.5,1]),[1,1,0,1])
    assert np.allclose(p@np.array([-4,-2,-100,1]),[-1,-1,1,1])
    camera=Camera();camera.projection='orthographic'
    right,_,forward=camera._basis()
    points=[camera.target+right, camera.target+right+forward*10]
    vp=camera.view_proj(1.5)
    clip=[vp@np.append(point,1) for point in points]
    assert np.allclose(clip[0][:2]/clip[0][3],clip[1][:2]/clip[1][3])
    assert np.allclose(vp[2,:3]/np.linalg.norm(vp[2,:3]),forward)
    before=clip[0][0]
    camera.dolly(.5)
    assert np.isclose((camera.view_proj(1.5)@np.append(points[0],1))[0],2*before,rtol=1e-4)
    for projection in ('',None,'panoramic',3):
        with pytest.raises(ValueError):recorded_projection(dict(projection=projection))
    for args in ((0,1,1,2),(1,0,1,2),(1,1,2,1),(float('nan'),1,1,2)):
        with pytest.raises(ValueError):orthographic_wgpu(*args)


@pytest.mark.parametrize('mode',['volume','slice','surface'])
def test_orthographic_gpu_recorded_field(mode):
    from trech_studio.capture import _offscreen_renderer, _frame_rgb
    from trech_studio.scene.model import SceneModel
    canvas,renderer,reason=_offscreen_renderer(240,160,'dark')
    if renderer is None:pytest.skip(reason)
    raw=grid();raw['display']['mode']=mode
    payload=dict(stream='test',positions_mm=[],colors_rgba=[],time_s=0,scalar_field=raw,up_axis='y',
        render_camera=dict(yaw_deg=70,pitch_deg=20,projection='orthographic'),show_geant4_scene=False)
    pb=build_material_frame_playback([SimpleNamespace(tag='material_frame',payload=payload)])
    original=pb.frames[0].density.values.copy()
    renderer.set_scene(SceneModel(world_size_mm=20))
    renderer.set_playback(pb)
    assert renderer.camera.projection=='orthographic'
    assert renderer.precision_info()['authored_camera_projection']=='orthographic'
    parallel=_frame_rgb(canvas,240,160)
    renderer.camera.projection='perspective'
    perspective=_frame_rgb(canvas,240,160)
    assert parallel is not None and perspective is not None and not np.array_equal(parallel,perspective)
    assert np.array_equal(original,pb.frames[0].density.values)
    renderer.set_playback(pb)
    assert renderer.camera.projection=='orthographic'
    renderer.set_playback(None)
    assert renderer.camera.projection=='perspective'


def test_recorded_triangles_only():
    raw=dict(vertices=[[0,0,0],[1,0,0],[0,1,0]],triangles=[[0,1,2]],inspection=dict(format_validated=True))
    mesh=interface_mesh(raw,'y')
    assert mesh.index_count==3 and np.allclose(mesh.vertices[:,:3],raw['vertices'])
    for change in (lambda d:d.update(triangles=[[0,0,1]]),lambda d:d.update(triangles=[[0,1,4]]),
                   lambda d:d.update(inspection={})):
        bad=deepcopy(raw);change(bad)
        with pytest.raises(ValueError):interface_mesh(bad,'y')


def test_mask_does_not_create_solid_boundary_surface():
    values=np.full((4,4,4),2,dtype=np.float32);values[0]=0
    mask=np.ones_like(values,dtype=bool);mask[0]=False
    mesh=density_surface_mesh(DensityGrid(values,np.zeros(3),1),1,mask)
    assert mesh.index_count==0
