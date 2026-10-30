// Only supplied, calibrated interface meshes are displayed. Inventories never make geometry.
TRECH_VIEWS.nacl_dehydration_reference = {
  viz0() {return {enable:false};},
  interfaceFrame(frame, sequence) {
    return {stream:"nacl_measured_interface",time_s:frame.time_s,time_unit:"s",length_unit:"um",
      up_axis:"y",show_geant4_scene:false,positions:frame.vertices,colors_rgba:frame.vertices.map(()=>[.85,.9,1,0]),
      interface_mesh:{vertices:frame.vertices,triangles:frame.triangles,source:sequence.source,
        calibration:sequence.calibration,validation:sequence.validation,inspection:sequence.inspection},
      phase:"RECORDED NaCl interface · independent measurement",
      clock_text:"t = "+frame.time_s+" s; held measured frame",
      hud_lines:[sequence.source.method,"Format checked; physical accuracy requires source review"],
      motion_scope:"Recorded geometry; lighting is representation. No interpolation, invented liquid motion or particle-trained growth"};
  }
};
