#include "trech/core/LatticeContinuum.hpp"

#include <algorithm>
#include <cmath>
#include <deque>
#include <limits>
#include <map>
#include <stdexcept>

namespace trech::lattice {
namespace {

VelocitySet makeSet(const std::string& name, int d, double cs2, const std::vector<std::array<int, 3>>& c,
                    const std::vector<double>& w) {
  VelocitySet s;
  s.name = name; s.dimensions = d; s.cs2 = cs2; s.w = w;
  for (const auto& v : c) { s.cx.push_back(v[0]); s.cy.push_back(v[1]); s.cz.push_back(v[2]); }
  for (std::size_t a = 0; a < c.size(); ++a)
    for (std::size_t b = 0; b < c.size(); ++b)
      if (c[b][0] == -c[a][0] && c[b][1] == -c[a][1] && c[b][2] == -c[a][2]) { s.opp.push_back(static_cast<int32_t>(b)); break; }
  return s;
}

const std::map<std::string, VelocitySet>& sets() {
  static const std::map<std::string, VelocitySet> all = [] {
    std::map<std::string, VelocitySet> m;
    const double a = 1.0 / 9, b = 1.0 / 36;
    m["D2Q9"] = makeSet("D2Q9", 2, 1.0 / 3, {{0,0,0},{1,0,0},{0,1,0},{-1,0,0},{0,-1,0},{1,1,0},{-1,1,0},{-1,-1,0},{1,-1,0}},
                        {4.0 / 9, a, a, a, a, b, b, b, b});
    const double e = 1.0 / 18, d = 1.0 / 36;
    m["D3Q19"] = makeSet("D3Q19", 3, 1.0 / 3,
                         {{0,0,0},{1,0,0},{-1,0,0},{0,1,0},{0,-1,0},{0,0,1},{0,0,-1},{1,1,0},{-1,-1,0},{1,-1,0},
                          {-1,1,0},{1,0,1},{-1,0,-1},{1,0,-1},{-1,0,1},{0,1,1},{0,-1,-1},{0,1,-1},{0,-1,1}},
                         {1.0 / 3, e, e, e, e, e, e, d, d, d, d, d, d, d, d, d, d, d, d});
    m["D2Q5"] = makeSet("D2Q5", 2, 1.0 / 3, {{0,0,0},{1,0,0},{0,1,0},{-1,0,0},{0,-1,0}},
                        {1.0 / 3, 1.0 / 6, 1.0 / 6, 1.0 / 6, 1.0 / 6});
    m["D3Q7"] = makeSet("D3Q7", 3, 0.25, {{0,0,0},{1,0,0},{-1,0,0},{0,1,0},{0,-1,0},{0,0,1},{0,0,-1}},
                        {0.25, 0.125, 0.125, 0.125, 0.125, 0.125, 0.125});
    return m;
  }();
  return all;
}

}  // namespace

const VelocitySet& velocitySet(const std::string& name) {
  const auto it = sets().find(name);
  if (it == sets().end()) throw std::invalid_argument("Unknown lattice " + name);
  return it->second;
}

Domain::Domain(std::array<int, 3> shape_, const std::function<bool(int, int, int)>& solid,
               std::array<bool, 3> periodic_)
    : shape(shape_), periodic(periodic_) {
  for (int n : shape)
    if (n < 1) throw std::invalid_argument("Lattice shape must be positive");
  const long cells = static_cast<long>(shape[0]) * shape[1] * shape[2];
  if (cells > 8000000) throw std::invalid_argument("Lattice exceeds 8e6 cells");
  index_.assign(static_cast<std::size_t>(cells), -1);
  for (int k = 0; k < shape[2]; ++k)
    for (int j = 0; j < shape[1]; ++j)
      for (int i = 0; i < shape[0]; ++i) {
        if (solid && solid(i, j, k)) continue;
        index_[static_cast<std::size_t>(i + shape[0] * (j + shape[1] * k))] = static_cast<int>(x.size());
        x.push_back(i); y.push_back(j); z.push_back(k);
      }
  if (x.empty()) throw std::invalid_argument("Lattice has no fluid cells");
}

int Domain::at(int i, int j, int k) const {
  int p[3] = {i, j, k};
  for (int a = 0; a < 3; ++a) {
    if (p[a] < 0 || p[a] >= shape[a]) {
      if (!periodic[a]) return -1;
      p[a] = ((p[a] % shape[a]) + shape[a]) % shape[a];
    }
  }
  return index_[static_cast<std::size_t>(p[0] + shape[0] * (p[1] + shape[1] * p[2]))];
}

const std::vector<int>& Domain::neighbours() const {
  if (!neighbours_.empty()) return neighbours_;
  const std::size_t F = count();
  static const int steps[6][3] = {{1,0,0},{-1,0,0},{0,1,0},{0,-1,0},{0,0,1},{0,0,-1}};
  neighbours_.resize(6 * F);
  for (std::size_t i = 0; i < F; ++i)
    for (int k = 0; k < 6; ++k)
      neighbours_[6 * i + k] = at(x[i] + steps[k][0], y[i] + steps[k][1], z[i] + steps[k][2]);
  return neighbours_;
}

const std::vector<double>& Domain::wallDistance() const {
  if (!wallDistance_.empty()) return wallDistance_;
  const auto& nb = neighbours();
  const std::size_t F = count();
  wallDistance_.assign(F, std::numeric_limits<double>::infinity());
  std::deque<std::size_t> queue;
  for (std::size_t i = 0; i < F; ++i)
    for (int k = 0; k < 6; ++k)
      if (nb[6 * i + k] < 0) { wallDistance_[i] = 1; queue.push_back(i); break; }
  while (!queue.empty()) {
    const std::size_t i = queue.front(); queue.pop_front();
    for (int k = 0; k < 6; ++k) {
      const int j = nb[6 * i + k];
      if (j >= 0 && wallDistance_[j] > wallDistance_[i] + 1) { wallDistance_[j] = wallDistance_[i] + 1; queue.push_back(j); }
    }
  }
  const double cap = *std::max_element(shape.begin(), shape.end());
  for (auto& d : wallDistance_) if (!std::isfinite(d)) d = cap;
  return wallDistance_;
}

Lattice::Lattice(const LatticeSpec& spec) : spec_(spec), domain_(spec.shape, spec.solid, spec.periodic) { build(); }

double Lattice::viscosity() const { return flowSet_ ? flowSet_->cs2 * (spec_.tau - 0.5) : 0.0; }
double Lattice::soundSpeed() const { return flowSet_ ? std::sqrt(flowSet_->cs2) : 0.0; }

void Lattice::build() {
  const std::size_t F = domain_.count();
  if (!spec_.flow && !spec_.scalar) throw std::invalid_argument("Lattice needs a flow or a scalar");
  if (spec_.buoyancyAxis < 0 || spec_.buoyancyAxis > 2) throw std::invalid_argument("Buoyancy axis must be 0..2");
  auto pull = [&](const VelocitySet& set, std::vector<int32_t>& src, std::vector<uint8_t>& wall) {
    const std::size_t Q = set.q();
    src.resize(Q * F); wall.assign(Q * F, 0);
    for (std::size_t q = 0; q < Q; ++q)
      for (std::size_t i = 0; i < F; ++i) {
        const int j = domain_.at(domain_.x[i] - static_cast<int>(set.cx[q]), domain_.y[i] - static_cast<int>(set.cy[q]),
                                 domain_.z[i] - static_cast<int>(set.cz[q]));
        if (j >= 0) src[q * F + i] = static_cast<int32_t>(q * F + static_cast<std::size_t>(j));
        else { src[q * F + i] = static_cast<int32_t>(static_cast<std::size_t>(set.opp[q]) * F + i); wall[q * F + i] = 1; }
      }
  };
  if (static_cast<double>(F) * 19.0 > static_cast<double>(std::numeric_limits<int32_t>::max()))
    throw std::invalid_argument("Lattice too large for 32-bit streaming tables");
  rho_.assign(F, 1.0); ux_.assign(F, 0.0); uy_.assign(F, 0.0); uz_.assign(F, 0.0);
  if (spec_.flow) {
    flowSet_ = &velocitySet(spec_.flowLattice);
    if (flowSet_->name != "D2Q9" && flowSet_->name != "D3Q19") throw std::invalid_argument("Flow lattice must be D2Q9 or D3Q19");
    if (flowSet_->dimensions == 2 && spec_.shape[2] != 1) throw std::invalid_argument("D2Q9 needs nz = 1");
    if (!(spec_.tau > 0.5) || spec_.tau > 5.0) throw std::invalid_argument("Flow tau must be in (1/2, 5]");
    if (!(spec_.flowMagic > 0)) throw std::invalid_argument("Flow TRT magic must be positive");
    const std::size_t Q = flowSet_->q();
    flowOmegaPlus_ = 1.0 / spec_.tau;
    flowOmegaMinus_ = 1.0 / (0.5 + spec_.flowMagic / (spec_.tau - 0.5));
    pull(*flowSet_, fSrc_, fWall_);
    f_.resize(Q * F); fPost_.resize(Q * F);
    const auto& s = *flowSet_;
    for (std::size_t i = 0; i < F; ++i) {
      std::array<double, 4> st{1.0, 0.0, 0.0, 0.0};
      if (spec_.initialFlow) st = spec_.initialFlow(domain_.x[i], domain_.y[i], domain_.z[i]);
      if (!(st[0] > 0) || !std::isfinite(st[1] + st[2] + st[3])) throw std::invalid_argument("Invalid initial flow");
      rho_[i] = st[0]; ux_[i] = st[1]; uy_[i] = st[2]; uz_[i] = st[3];
      const double u2 = st[1] * st[1] + st[2] * st[2] + st[3] * st[3];
      for (std::size_t q = 0; q < Q; ++q) {
        const double cu = (s.cx[q] * st[1] + s.cy[q] * st[2] + s.cz[q] * st[3]) / s.cs2;
        f_[q * F + i] = s.w[q] * st[0] * (1 + cu + 0.5 * cu * cu - 0.5 * u2 / s.cs2);
      }
    }
    if (spec_.wallVelocity) {
      wallTerm_.assign(Q * F, 0.0);
      for (std::size_t q = 0; q < Q; ++q)
        for (std::size_t i = 0; i < F; ++i) {
          if (!fWall_[q * F + i]) continue;
          std::array<double, 3> uw{0, 0, 0};
          if (spec_.wallVelocity(domain_.x[i] - static_cast<int>(s.cx[q]), domain_.y[i] - static_cast<int>(s.cy[q]),
                                 domain_.z[i] - static_cast<int>(s.cz[q]), uw))
            wallTerm_[q * F + i] = 2 * s.w[q] * (s.cx[q] * uw[0] + s.cy[q] * uw[1] + s.cz[q] * uw[2]) / s.cs2;
        }
    }
  }
  if (spec_.scalar) {
    scalarSet_ = &velocitySet(spec_.scalarLattice);
    if (scalarSet_->name != "D2Q5" && scalarSet_->name != "D3Q7") throw std::invalid_argument("Scalar lattice must be D2Q5 or D3Q7");
    if (scalarSet_->dimensions == 2 && spec_.shape[2] != 1) throw std::invalid_argument("D2Q5 needs nz = 1");
    if (!(spec_.diffusivity > 0)) throw std::invalid_argument("Scalar diffusivity must be positive");
    const auto& s = *scalarSet_;
    const std::size_t Q = s.q();
    const double tauMinus = 0.5 + spec_.diffusivity / s.cs2;
    const double magic = spec_.scalarMagic > 0 ? spec_.scalarMagic : 0.5 * (tauMinus - 0.5);
    scalarOmegaMinus_ = 1.0 / tauMinus;
    scalarOmegaPlus_ = 1.0 / (0.5 + magic / (tauMinus - 0.5));
    std::vector<uint8_t> wall;
    pull(s, gSrc_, wall);
    anti_.assign(Q * F, 0); dirichlet_.assign(Q * F, 0.0);
    if (spec_.dirichlet)
      for (std::size_t q = 0; q < Q; ++q)
        for (std::size_t i = 0; i < F; ++i) {
          if (!wall[q * F + i]) continue;
          double value = 0;
          if (spec_.dirichlet(domain_.x[i] - static_cast<int>(s.cx[q]), domain_.y[i] - static_cast<int>(s.cy[q]),
                              domain_.z[i] - static_cast<int>(s.cz[q]), domain_.x[i], domain_.y[i], domain_.z[i], value)) {
            anti_[q * F + i] = 1; dirichlet_[q * F + i] = 2 * s.w[q] * value;
          }
        }
    g_.resize(Q * F); gPost_.resize(Q * F); value_.resize(F);
    for (std::size_t i = 0; i < F; ++i) {
      const double v = spec_.initialScalar ? spec_.initialScalar(domain_.x[i], domain_.y[i], domain_.z[i]) : 0.0;
      if (!std::isfinite(v)) throw std::invalid_argument("Invalid initial scalar");
      value_[i] = v;
      for (std::size_t q = 0; q < Q; ++q) g_[q * F + i] = s.w[q] * v;
    }
  }
  rate_.assign(F, 0.0); target_.assign(F, 0.0); constant_.assign(F, 0.0);
}

namespace {
LatticeVelocitySet view(const VelocitySet& s) {
  LatticeVelocitySet v;
  v.q = s.q(); v.cx = s.cx.data(); v.cy = s.cy.data(); v.cz = s.cz.data(); v.w = s.w.data(); v.opp = s.opp.data(); v.cs2 = s.cs2;
  return v;
}
bool anyNonZero(const std::vector<double>& v) {
  for (double x : v) if (x != 0.0) return true;
  return false;
}
}  // namespace

bool Lattice::advance(std::uint64_t n) {
  const std::size_t F = domain_.count();
  LatticeScalarView sv;
  if (spec_.scalar) {
    sv.set = view(*scalarSet_); sv.cells = F;
    sv.omegaPlus = scalarOmegaPlus_; sv.omegaMinus = scalarOmegaMinus_;
    sv.g = g_.data(); sv.post = gPost_.data(); sv.src = gSrc_.data(); sv.anti = anti_.data();
    sv.dirichlet = dirichlet_.data(); sv.value = value_.data();
    if (anyNonZero(rate_)) { sv.rate = rate_.data(); sv.target = target_.data(); }
    if (anyNonZero(constant_)) sv.constant = constant_.data();
  }
  if (!spec_.flow) {
    const bool advect = advectX_.size() == F && advectY_.size() == F && advectZ_.size() == F;
    const auto r = advanceScalarLattice(sv, advect ? advectX_.data() : nullptr, advect ? advectY_.data() : nullptr,
                                        advect ? advectZ_.data() : nullptr, n);
    steps_ += r.steps;
    return true;
  }
  LatticeFlowView fv;
  fv.set = view(*flowSet_); fv.cells = F;
  fv.omegaPlus = flowOmegaPlus_; fv.omegaMinus = flowOmegaMinus_;
  fv.f = f_.data(); fv.post = fPost_.data(); fv.src = fSrc_.data();
  fv.wall = fWall_.data(); fv.wallTerm = wallTerm_.empty() ? nullptr : wallTerm_.data();
  fv.rho = rho_.data(); fv.ux = ux_.data(); fv.uy = uy_.data(); fv.uz = uz_.data();
  LatticeCoupling c;
  c.base[0] = spec_.uniformForce[0]; c.base[1] = spec_.uniformForce[1]; c.base[2] = spec_.uniformForce[2];
  c.axis = spec_.buoyancyAxis; c.coefficient = spec_.buoyancyCoefficient;
  c.reference = spec_.buoyancyReference; c.meanReference = spec_.meanReference;
  if (!spec_.scalar && forceX_.size() == F && forceY_.size() == F && forceZ_.size() == F) {
    c.forceX = forceX_.data(); c.forceY = forceY_.data(); c.forceZ = forceZ_.data();
  }
  const auto r = advanceLattice(fv, spec_.scalar ? &sv : nullptr, c, n);
  steps_ += r.steps;
  maxMach_ = std::max(maxMach_, r.maxMach);
  return !r.nonphysical;
}

const std::vector<double>& Lattice::scalarValues() {
  if (!spec_.scalar) return value_;
  const std::size_t F = domain_.count(), Q = scalarSet_->q();
  for (std::size_t i = 0; i < F; ++i) {
    double s = 0;
    for (std::size_t q = 0; q < Q; ++q) s += g_[q * F + i];
    value_[i] = s;
  }
  return value_;
}

void Lattice::flowMoments(std::vector<double>& rho, std::vector<double>& ux, std::vector<double>& uy,
                          std::vector<double>& uz) const {
  const std::size_t F = domain_.count();
  rho.assign(F, 1.0); ux.assign(F, 0.0); uy.assign(F, 0.0); uz.assign(F, 0.0);
  if (!spec_.flow) return;
  const auto& s = *flowSet_;
  for (std::size_t i = 0; i < F; ++i) {
    double r = 0, mx = 0, my = 0, mz = 0;
    for (std::size_t q = 0; q < s.q(); ++q) {
      const double v = f_[q * F + i];
      r += v; mx += s.cx[q] * v; my += s.cy[q] * v; mz += s.cz[q] * v;
    }
    rho[i] = r; ux[i] = mx / r; uy[i] = my / r; uz[i] = mz / r;
  }
}

void Lattice::addScalar(const std::vector<double>& delta) {
  if (!spec_.scalar) return;
  const std::size_t F = domain_.count(), Q = scalarSet_->q();
  if (delta.size() != F) throw std::invalid_argument("addScalar needs one value per fluid cell");
  for (std::size_t q = 0; q < Q; ++q)
    for (std::size_t i = 0; i < F; ++i) g_[q * F + i] += scalarSet_->w[q] * delta[i];
}

double Lattice::mass() const { double m = 0; for (double v : f_) m += v; return m; }
double Lattice::scalarTotal() const { double m = 0; for (double v : g_) m += v; return m; }

bool sample(const Domain& d, const std::vector<double>& field, double x, double y, double z, double& out) {
  const int x0 = static_cast<int>(std::floor(x)), y0 = static_cast<int>(std::floor(y)), z0 = static_cast<int>(std::floor(z));
  double acc = 0, wsum = 0;
  for (int k = 0; k < 8; ++k) {
    const int ix = x0 + (k & 1), iy = y0 + ((k >> 1) & 1), iz = z0 + ((k >> 2) & 1);
    const int j = d.at(ix, iy, iz);
    if (j < 0) continue;
    const double wt = (1 - std::abs(x - ix)) * (1 - std::abs(y - iy)) * (1 - std::abs(z - iz));
    if (wt <= 0) continue;
    acc += wt * field[static_cast<std::size_t>(j)]; wsum += wt;
  }
  if (!(wsum > 0)) return false;
  out = acc / wsum;
  return true;
}

LocalDescriptors localDescriptors(Lattice& lattice, double scalarScale) {
  const Domain& d = lattice.domain();
  const std::size_t F = d.count();
  const auto& nb = d.neighbours();
  const auto& T = lattice.scalarValues();
  const auto& ux = lattice.ux(); const auto& uy = lattice.uy(); const auto& uz = lattice.uz();
  const double cs = lattice.hasFlow() ? lattice.soundSpeed() : std::sqrt(1.0 / 3.0);
  const double nu = lattice.hasFlow() ? lattice.viscosity() : 1.0;
  const double D = lattice.hasScalar() ? lattice.diffusivity() : 1.0;
  LocalDescriptors out;
  out.mach.resize(F); out.cellReynolds.resize(F); out.cellPeclet.resize(F);
  out.scalarStep.resize(F); out.velocityCurvature.resize(F); out.wallDistance = d.wallDistance();
  for (std::size_t i = 0; i < F; ++i) {
    const double speed = std::sqrt(ux[i] * ux[i] + uy[i] * uy[i] + uz[i] * uz[i]);
    out.mach[i] = speed / cs; out.cellReynolds[i] = speed / nu; out.cellPeclet[i] = speed / D;
    double g2 = 0, mx = 0, my = 0, mz = 0;
    if (lattice.hasScalar())
      for (int a = 0; a < 3; ++a) {
        const int p = nb[6 * i + 2 * a], m = nb[6 * i + 2 * a + 1];
        const double g = p >= 0 && m >= 0 ? 0.5 * (T[p] - T[m]) : p >= 0 ? T[p] - T[i] : m >= 0 ? T[i] - T[m] : 0.0;
        g2 += g * g;
      }
    for (int k = 0; k < 6; ++k) {
      const int j = nb[6 * i + k];
      if (j >= 0) { mx += ux[j]; my += uy[j]; mz += uz[j]; }
    }
    out.scalarStep[i] = std::sqrt(g2) / scalarScale;
    out.velocityCurvature[i] = std::sqrt((mx / 6 - ux[i]) * (mx / 6 - ux[i]) + (my / 6 - uy[i]) * (my / 6 - uy[i]) +
                                         (mz / 6 - uz[i]) * (mz / 6 - uz[i])) / cs;
  }
  return out;
}

double staggeredFraction(const Domain& d, const std::vector<double>& ux, const std::vector<double>& uy,
                         const std::vector<double>& uz) {
  const std::size_t F = d.count();
  double total = 0;
  for (std::size_t i = 0; i < F; ++i) total += ux[i] * ux[i] + uy[i] * uy[i] + uz[i] * uz[i];
  if (!(total > 0)) return 0.0;
  const std::vector<int>* c[3] = {&d.x, &d.y, &d.z};
  const std::vector<double>* u[3] = {&ux, &uy, &uz};
  double worst = 0;
  for (int a = 0; a < 3; ++a) {
    const int b = (a + 1) % 3, e = (a + 2) % 3;
    std::map<std::pair<int, int>, std::array<double, 4>> lines;
    for (std::size_t i = 0; i < F; ++i) {
      auto& line = lines[{(*c[b])[i], (*c[e])[i]}];
      const double sign = ((*c[a])[i] & 1) ? -1.0 : 1.0;
      for (int k = 0; k < 3; ++k) line[k] += sign * (*u[k])[i];
      line[3] += 1;
    }
    double energy = 0;
    for (const auto& [key, line] : lines) energy += (line[0] * line[0] + line[1] * line[1] + line[2] * line[2]) / line[3];
    worst = std::max(worst, energy / total);
  }
  return worst;
}

}  // namespace trech::lattice
