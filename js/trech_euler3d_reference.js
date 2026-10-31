// Independent 3D inviscid Euler comparison. No learned or Geant4 flow response.
(function() {
  if (globalThis.TRECH_EULER3D_REFERENCE) return;
  function create(o) {
    const {nx, ny, nz, dx, gamma, gasConstant, rho, pressure, mach} = o;
    const shape = [nx, ny, nz], stride = [1, nx, nx * ny];
    if (!shape.every(n => Number.isInteger(n) && n >= 4) || nx * ny * nz > 30000 ||
        ![dx, gamma - 1, gasConstant, rho, pressure].every(v => Number.isFinite(v) && v > 0) ||
        !Number.isFinite(mach) || mach < 0 || mach > 3) throw new Error('Invalid 3D Euler inputs');
    const speed = mach * Math.sqrt(gamma * pressure / rho);
    const velocity = o.velocity || [speed, 0, 0];
    if (velocity.length !== 3 || !velocity.every(Number.isFinite)) throw new Error('Invalid inlet velocity');
    const cfl = o.cfl === undefined ? .3 : o.cfl;
    const boundary = o.boundary === undefined ? 'reservoir' : o.boundary;
    if (!Number.isFinite(cfl) || cfl <= 0 || cfl > .3 || !['reservoir','periodic'].includes(boundary) ||
        (boundary === 'periodic' && o.body !== false) ||
        (o.initialState !== undefined && typeof o.initialState !== 'function'))
      throw new Error('Invalid 3D Euler boundary, initial state or CFL');
    const inlet = [rho, ...velocity.map(v => rho * v), pressure / (gamma - 1) +
      0.5 * rho * velocity.reduce((s,v) => s + v*v, 0)];
    const centre = [nx * .42, ny * .5, nz * .5], radius = Math.min(ny, nz) * .22;
    const coords = i => [i % nx, Math.floor(i / nx) % ny, Math.floor(i / (nx * ny))];
    let state = Array.from({length: nx * ny * nz}, (_,i) => {
      const u = o.initialState ? o.initialState(...coords(i).map(v => (v+.5)*dx)) : inlet;
      if (!Array.isArray(u) || u.length !== 5) throw new Error('Initial state needs five cell-average conservative values');
      primitive(u);
      return u.slice();
    });
    const solid = state.map((_,i) => o.body !== false &&
      Math.hypot(...coords(i).map((v,a) => v + .5 - centre[a])) < radius);
    let time = 0, steps = 0;
    const exchange = [0,0,0,0,0];
    function primitive(u) {
      const p = (gamma - 1) * (u[4] - .5 * (u[1]**2 + u[2]**2 + u[3]**2) / u[0]);
      if (!u.every(Number.isFinite) || !(u[0] > 0) || !(p > 0))
        throw new Error('Nonphysical 3D Euler state; refine grid/timestep instead of clipping');
      return {rho:u[0], vx:u[1]/u[0], vy:u[2]/u[0], vz:u[3]/u[0], p,
        temperature:p/(u[0]*gasConstant), c:Math.sqrt(gamma*p/u[0])};
    }
    function flux(u, axis, p) {
      const v = u[axis+1]/u[0];
      return [u[0]*v, u[1]*v+(axis===0?p:0), u[2]*v+(axis===1?p:0),
        u[3]*v+(axis===2?p:0), (u[4]+p)*v];
    }
    function totals() {
      const sum = [0,0,0,0,0];
      state.forEach((u,i) => {if(!solid[i]) for(let k=0;k<5;k++) sum[k]+=u[k]*dx**3;});
      return sum;
    }
    const initial = totals();
    function advance(maxDt) {
      if (maxDt !== undefined && (!Number.isFinite(maxDt) || maxDt <= 0))
        throw new Error('Maximum timestep must be finite and positive');
      let frequency = 0;
      const primitives = state.map((u,i) => {
        const p=primitive(u);
        if(!solid[i]) frequency=Math.max(frequency,(Math.abs(p.vx)+Math.abs(p.vy)+Math.abs(p.vz)+3*p.c)/dx);
        return p;
      });
      const dt=Math.min(cfl/frequency,maxDt === undefined ? Infinity : maxDt);
      if (!(dt > 0) || time + dt === time) throw new Error('Euler timestep cannot advance clock');
      const delta=state.map(()=>[0,0,0,0,0]), stepExchange=[0,0,0,0,0];
      function face(a,b,axis) {
        const fluidA=a>=0&&!solid[a], fluidB=b>=0&&!solid[b];
        if(!fluidA&&!fluidB) return;
        let left=fluidA?state[a]:inlet, right=fluidB?state[b]:(axis===0&&b<0?left:inlet);
        if(a>=0&&solid[a]) {left=right.slice();left[axis+1]*=-1;}
        if(b>=0&&solid[b]) {right=left.slice();right[axis+1]*=-1;}
        const pa=fluidA?primitives[a]:primitive(left), pb=fluidB?primitives[b]:primitive(right);
        const fa=flux(left,axis,pa.p), fb=flux(right,axis,pb.p);
        const wave=Math.max(Math.abs(left[axis+1]/left[0])+pa.c,Math.abs(right[axis+1]/right[0])+pb.c);
        for(let k=0;k<5;k++) {
          const f=.5*(fa[k]+fb[k]-wave*(right[k]-left[k]));
          if(fluidA) delta[a][k]-=dt/dx*f;
          if(fluidB) delta[b][k]+=dt/dx*f;
          if(fluidA!==fluidB) stepExchange[k]+=(fluidB?1:-1)*dt*dx*dx*f;
        }
      }
      // Each Cartesian face is evaluated once; all three momentum components evolve.
      for(let axis=0;axis<3;axis++) {
        for(let i=0;i<state.length;i++) {
          const c=coords(i)[axis];
          if(c===0 && boundary === 'reservoir') face(-1,i,axis);
          face(i,c+1<shape[axis]?i+stride[axis]:
            boundary === 'periodic'?i-(shape[axis]-1)*stride[axis]:-1,axis);
        }
      }
      const next=state.map((u,i)=>u.map((v,k)=>v+delta[i][k]));
      next.forEach((u,i)=>{if(!solid[i])primitive(u);});
      state=next;time+=dt;steps++;
      for(let k=0;k<5;k++) exchange[k]+=stepExchange[k];
      return dt;
    }
    function advanceTo(target) {
      if (!Number.isFinite(target) || target < time) throw new Error('Target time must be finite and nondecreasing');
      while(time < target) advance(target-time);
      return time;
    }
    function snapshot() {
      const cells=[], solid_positions=[], fields={density:[],pressure:[],temperature:[]};
      state.forEach((u,i)=>{
        const xyz=coords(i).map(v=>(v+.5)*dx), p=primitive(u);
        if(solid[i]) solid_positions.push(xyz);
        else cells.push({x:xyz[0],y:xyz[1],z:xyz[2],...p});
        // Zero-filled excluded voxels are explicitly masked, never gas measurements.
        fields.density.push(solid[i]?0:p.rho);fields.pressure.push(solid[i]?0:p.p);
        fields.temperature.push(solid[i]?0:p.temperature);
      });
      const integral=totals();
      return {time_s:time,steps,cells,solid_positions,shape:shape.slice(),fields,
        active_mask:solid.map(s=>!s),integral,boundary_exchange:exchange.slice(),
        balance_residual:integral.map((v,k)=>v-initial[k]-exchange[k])};
    }
    return {advance,advanceTo,snapshot};
  }
  globalThis.TRECH_EULER3D_REFERENCE={create};
})();
