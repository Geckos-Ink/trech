// These controls change representation only; the state is independently evolved in 3D.
TRECH_VIEWS.aerodynamics_reference = {
  viz0() {return {enable:true};},
  frame1(dx, field, ny, nz, positions, reference, s, scope, values, controls) {
    const mode=controls.display_mode, opacity=controls.opacity;
    const unit=field==='temperature'?'K':field==='pressure'?'Pa':'kg/m^3';
    return {stream:'aerodynamics_reference',time_s:s.time_s,up_axis:'y',show_geant4_scene:false,
      positions_mm:positions.map(p=>[1000*(p[0]-.2),1000*(p[1]-ny*dx/2),1000*(p[2]-nz*dx/2)]),
      colors_rgba:positions.map(()=>[.65,.68,.72,1]),radii:positions.map(()=>dx*450),
      scalar_field:{schema:'trech_scalar_grid_v1',shape:s.shape,order:'x_fastest',
        origin:[1000*(dx/2-.2),1000*(dx/2-ny*dx/2),1000*(dx/2-nz*dx/2)],spacing:1000*dx,
        values:s.fields[field],active_mask:s.active_mask,unit,source:scope,
        display:{mode,low:controls.gradient_low_ratio*reference,high:controls.gradient_high_ratio*reference,opacity,
          isovalue:controls.isovalue_ratio*reference,
          axis:controls.slice_axis,fraction:controls.slice_fraction}},
      render_camera:{yaw_deg:controls.camera_yaw,pitch_deg:controls.camera_pitch},
      phase:'3D COMPARISON · air '+field,
      clock_text:'t = '+(s.time_s*1000).toFixed(3)+' ms; CFL step '+s.steps,
      hud_lines:[Math.min(...values).toFixed(2)+'–'+Math.max(...values).toFixed(2)+' '+unit,
        s.shape.join(' × ')+' cells · '+mode+' · opacity is representation'],
      legend:[{label:'Gradient: '+controls.gradient_low_ratio+'–'+controls.gradient_high_ratio+'× inlet; grey: fixed sphere',color_rgba:[.5,.3,.5,1]}],
      motion_scope:scope+'; scalar interpolation, transparency, surfaces and camera are display choices'};
  }
};
