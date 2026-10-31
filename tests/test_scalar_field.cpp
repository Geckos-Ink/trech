#include "trech/core/ScalarField.hpp"
#include <nlohmann/json.hpp>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <iostream>
void require(bool ok, const char* message) { if (!ok) throw std::runtime_error(message); }
int main() {
 try {
  auto stats = trech::scalarFieldStatistics({4, 2, 2, 0}, .5);
  require(stats["integral"] == 1 && stats["absolute_integral"] == 1, "voxel quadrature failed");
  const auto level = stats["mass_levels"][49];
  require(level["threshold"] == 4 && level["enclosed_fraction"] == .5, "half-mass contour wrong");
  require(stats["mass_levels"][89]["enclosed_fraction"] == 1 && stats["mass_levels"][89]["voxel_count"] == 3,
    "threshold ties must include the whole level");
  stats = trech::scalarFieldStatistics({-2, 2, 0}, 1);
  require(stats["integral"] == 0 && stats["absolute_integral"] == 4 && stats["negative_integral"] == 2,
    "signed redistribution cancellation/mass lost");
  require(trech::scalarFieldStatistics({0,0}, 1)["mass_levels"].empty(), "zero field has no mass contour");
  require(trech::scalarFieldStatistics({std::numeric_limits<double>::denorm_min()}, 1)["mass_levels"].size() == 99,
    "subnormal mass target must not underflow into an invalid threshold index");
  require(trech::scalarFieldStatistics({1e308,1e307}, 1)["mass_levels"][49]["voxel_count"] == 1,
    "finite large mass must not overflow while forming percentile targets");
  for (auto values : {std::vector<double>{}, std::vector<double>{std::numeric_limits<double>::infinity()}}) {
    bool rejected=false; try { trech::scalarFieldStatistics(values, 1); } catch (...) { rejected=true; }
    require(rejected, "invalid grid accepted");
  }
  const auto error = trech::scalarFieldError({1, 3}, {2, 1}, .5);
  require(error["l1"] == 1.5 && error["linf"] == 2 && error["bias"] == .5 &&
    error["support_volume"] == .25 && std::abs(error["l2"].get<double>()-std::sqrt(2.5)) < 1e-14,
    "co-located field norms wrong");
  require(trech::scalarFieldError({1e300,-1e300}, {0,0}, 1)["l2"] == 1e300,
    "finite field norm overflowed while squaring");
  require(trech::scalarFieldError({1e-300,-1e-300}, {0,0}, 1)["l2"] == 1e-300,
    "small field norm underflowed while squaring");
  require(trech::scalarFieldError({0,0}, {0,0}, 1)["l2"] == 0, "zero field error is nonzero");
  for (int invalid=0; invalid<7; ++invalid) {
    bool rejected=false;
    try {
      auto a=std::vector<double>{1}, b=a;
      double spacing=1;
      if(invalid==0) b.push_back(2);
      if(invalid==1) a.clear();
      if(invalid==2) a[0]=std::numeric_limits<double>::quiet_NaN();
      if(invalid==3) spacing=0;
      if(invalid==4) spacing=1e200;
      if(invalid==5) {a[0]=1e308;b[0]=-1e308;}
      if(invalid==6) spacing=1e-200;
      trech::scalarFieldError(a,b,spacing);
    } catch (...) {rejected=true;}
    require(rejected,"invalid field comparison accepted");
  }
  std::cout << "finite-grid signed integrals and tied enclosed-mass thresholds pass\n";
 } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
