// Exact-solution verification fixture; never particle training data or obstacle validation.
TRECH_INCLUDE("../../../js/trech_euler3d_reference.js");
const scope = 'Independent exact periodic Euler verification; no Geant4-trained aerodynamic response';
globalThis.TRECH_CONFIG = {
  run:{nEvents:1,seed:424242,threads:1},determinism:{mode:'strict'},
  detector:{worldSizeMm:100,worldMaterial:'G4_AIR'},
  beam:{particle:'gamma',energyMeV:.1,positionMm:[0,0,-40],direction:[0,0,1]},
  hooks:{enable:true,maxEmitsPerCallback:1,maxEmitPayloadBytes:1048576,
    inputs:{reference_kind:'independent_exact_solution',scope,
      domain_m:[1,1,1],time_s:.04,grids:[6,12,24],cfl:[.3,.15,.075],
      temporal_reference_cfl:.009375,temporal_grid:12,
      anchors:['oblique_entropy','triaxial_entropy','oblique_shear'],
      gamma:1.4,gas_constant_j_kg_k:1,density_kg_m3:1,pressure_pa:1,
      velocity_m_s:[.7,-.4,.3],wave_vector_cycles_m:[1,1,1],
      density_amplitude_kg_m3:.2,shear_amplitude_m_s:[.15,-.1,-.05],
      method:'Exact conservative cell averages; periodic boundaries; fixed physical time',
      spatial_order_min:.5,temporal_order_min:.8,order_max:1.5}}
};

function verifyEuler3D() {
  function check(ok,message) {if(!ok) throw new Error(message);}
  const gamma=1.4, velocity=[.7,-.4,.3], shear=[.15,-.1,-.05];
  const end=.04, sinc=x=>x===0?1:Math.sin(x)/x;
  // These closed-form anchors are separate from the numerical solver. Constant
  // pressure/velocity advects arbitrary density. A shear perpendicular to k also
  // advects exactly, since k dot shear=0 and divergence(v)=0. Integrate each
  // conservative variable over the voxel, including the sin² kinetic term.
  function exact(kind,n,x,y,z,t) {
    const q=[x,y,z].map((v,a)=>2*Math.PI*(v-velocity[a]*t));
    const filter=sinc(Math.PI/n), phase=q.reduce((a,b)=>a+b,0);
    let density=1, v=velocity.slice(), kinetic;
    if(kind==='oblique_entropy') density+=.2*filter**3*Math.sin(phase);
    if(kind==='triaxial_entropy') density+=.2*filter**3*q.reduce((a,b)=>a*Math.sin(b),1);
    if(kind==='oblique_shear') {
      const sine=filter**3*Math.sin(phase);
      const sineSquare=.5*(1-sinc(2*Math.PI/n)**3*Math.cos(2*phase));
      v=v.map((value,a)=>value+shear[a]*sine);
      kinetic=.5*velocity.reduce((s,value,a)=>s+value*value+
        2*value*shear[a]*sine+shear[a]**2*sineSquare,0);
    } else kinetic=.5*density*velocity.reduce((s,value)=>s+value*value,0);
    return [density,...v.map(value=>density*value),1/(gamma-1)+kinetic];
  }
  const conservative=c=>[c.rho,c.rho*c.vx,c.rho*c.vy,c.rho*c.vz,
    c.p/(gamma-1)+.5*c.rho*(c.vx*c.vx+c.vy*c.vy+c.vz*c.vz)];
  function solve(kind,n,cfl) {
    const solver=TRECH_EULER3D_REFERENCE.create({nx:n,ny:n,nz:n,dx:1/n,
      gamma,gasConstant:1,rho:1,pressure:1,mach:0,body:false,velocity,cfl,boundary:'periodic',
      initialState:(x,y,z)=>exact(kind,n,x,y,z,0)});
    solver.advanceTo(end);
    const s=solver.snapshot();
    check(s.time_s===end,'Study compared different physical times');
    check(s.boundary_exchange.every(v=>v===0),'Periodic seam counted as external exchange');
    check(s.balance_residual.every((v,k)=>Math.abs(v)<2e-11*Math.max(1,Math.abs(s.integral[k]))),
      'Periodic conservation lost');
    check(s.cells.every(c=>c.rho>0&&c.p>0),'Anchor lost positive state');
    const actual=s.cells.map(conservative), expected=s.cells.map(c=>exact(kind,n,c.x,c.y,c.z,end));
    const names=['density','momentum_x','momentum_y','momentum_z','energy'];
    const norms=Object.fromEntries(names.map((name,k)=>[name,
      TRECH_FIELD_ERROR(actual.map(v=>v[k]),expected.map(v=>v[k]),1/n)]));
    return {n,cfl,time_s:s.time_s,steps:s.steps,norms,
      balance_residual:s.balance_residual,actual};
  }
  const anchors=[];
  for(const kind of ['oblique_entropy','triaxial_entropy','oblique_shear']) {
    const spatial=[6,12,24].map(n=>solve(kind,n,.3));
    const quantity=kind==='oblique_shear'?'momentum_x':'density';
    const spatialOrders=spatial.slice(1).map((s,i)=>
      Math.log(spatial[i].norms[quantity].l1/s.norms[quantity].l1)/Math.log(2));
    check(spatialOrders.every(p=>p>.5&&p<1.5),'Spatial convergence outside first-order range: '+kind+' '+spatialOrders);
    const baseline=solve(kind,12,.009375), temporal=[spatial[1],solve(kind,12,.15),solve(kind,12,.075)];
    const component=kind==='oblique_shear'?1:0;
    const temporalErrors=temporal.map(s=>TRECH_FIELD_ERROR(s.actual.map(v=>v[component]),
      baseline.actual.map(v=>v[component]),1/12));
    const temporalOrders=temporalErrors.slice(1).map((s,i)=>Math.log(temporalErrors[i].l1/s.l1)/Math.log(2));
    check(temporalOrders.every(p=>p>.8&&p<1.5),'Temporal convergence outside first-order range: '+kind);
    function summary(s) {const {actual,...report}=s;return report;}
    anchors.push({kind,quantity,spatial:spatial.map(summary),spatial_orders:spatialOrders,
      temporal:temporal.map(summary),temporal_errors:temporalErrors,temporal_orders:temporalOrders,
      temporal_reference:summary(baseline)});
  }
  return {schema:'trech_euler3d_verification_v1',scope,time_s:end,anchors,
    physical_accuracy_verified:false,particle_training_data:false,
    limitations:'Smooth periodic entropy/shear modes only; no acoustic/shock/wall/obstacle accuracy, experimental uncertainty or particle-derived response'};
}
globalThis.TRECH_HOOKS={onEventEnd(ctx){ctx.emit('euler3d_accuracy',verifyEuler3D());}};
