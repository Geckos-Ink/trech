// The engine, not the caller, picks the field-evolution method: the same declared system is
// graded against two different references and the selected method must follow the evidence.
#include "trech/ml/FieldEvolution.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

using trech::ml::FieldEvolution;

namespace {
int failures = 0;
void check(bool ok, const std::string& message) {
  if (!ok) { std::fprintf(stderr, "FAIL: %s\n", message.c_str()); ++failures; }
}

// Independent reference: explicit 1-D slab conduction with the same exchanges.
struct Column {
  std::vector<double> t;
  double dz, kappa;
  void advance(double seconds, double rate, double target) {
    const double dt = 0.2 * dz * dz / kappa;
    for (double done = 0; done < seconds - 1e-12;) {
      const double h = std::min(dt, seconds - done);
      std::vector<double> next = t;
      for (std::size_t c = 0; c < t.size(); ++c) {
        const double below = c ? t[c - 1] : t[c], above = c + 1 < t.size() ? t[c + 1] : t[c];
        next[c] += kappa * h / (dz * dz) * (below - 2 * t[c] + above);
      }
      next[0] += rate * (target - next[0]) * h;
      t = next; done += h;
    }
  }
};

nlohmann::json run(bool frozenReference) {
  const int cells = 8;
  const double heightMm = 120, slab = heightMm / cells, kappa = 1e-5, rate = 0.2, target = 10;
  std::vector<std::array<double, 3>> lo, hi;
  for (int c = 0; c < cells; ++c) { lo.push_back({0, 0, c * slab}); hi.push_back({30, 30, (c + 1) * slab}); }
  trech::ml::FieldRegion region;
  region.shape = "box"; region.sizeMm = {30, 30, heightMm};
  trech::ml::FieldProperties props;
  props.kinematicViscosityM2S = 1e-5; props.diffusivityM2S = kappa;  // no gravity: no buoyancy
  trech::ml::FieldEvolutionOptions opt;
  opt.cellMm = 5; opt.minElements = 16; opt.seed = 7;
  FieldEvolution evolution(region, lo, hi, props, std::vector<double>(cells, 0.0), opt);
  Column column{std::vector<double>(cells, 0.0), slab * 1e-3, kappa};
  nlohmann::json last;
  for (int frame = 1; frame <= 60; ++frame) {
    if (!frozenReference) column.advance(2.0, rate, target);
    trech::ml::FieldEvolutionInput in;
    in.timeS = 2.0 * frame;
    in.rate.assign(cells, 0.0); in.rate[0] = rate;
    in.target.assign(cells, 0.0); in.target[0] = target;
    in.reference = column.t;
    last = evolution.step(in);
  }
  return evolution.summary();
}
}  // namespace

int main() {
  try {
    const auto diffusing = run(false), frozen = run(true);
    const auto share = [](const nlohmann::json& s, const char* m) { return s.at("methods").at(m).at("selected_share").get<double>(); };
    const auto rmse = [](const nlohmann::json& s, const char* m) { return s.at("methods").at(m).at("rmse").get<double>(); };
    const double latticeShare = share(diffusing, "lattice_conductive") + share(diffusing, "lattice_convective");
    std::printf("conducting reference: lattice share %.3f persistence share %.3f arbitrated rmse %.4f persistence rmse %.4f\n",
                latticeShare, share(diffusing, "persistence"), diffusing.at("arbitrated_rmse").get<double>(),
                rmse(diffusing, "persistence"));
    check(latticeShare > 0.5, "a conducting reference did not make a lattice method emerge");
    check(diffusing.at("arbitrated_rmse").get<double>() < rmse(diffusing, "persistence"),
          "arbitration did not beat persistence on a conducting reference");
    // Away from the exchange every method predicts "no change", so ties there are arbitrary;
    // where they differ, the evidence must remove most of the lattice error.
    const double latticeBest = std::min(rmse(frozen, "lattice_conductive"), rmse(frozen, "lattice_convective"));
    std::printf("frozen reference: persistence share %.3f arbitrated rmse %.4f best lattice rmse %.4f\n",
                share(frozen, "persistence"), frozen.at("arbitrated_rmse").get<double>(), latticeBest);
    check(frozen.at("arbitrated_rmse").get<double>() < 0.25 * latticeBest,
          "a frozen reference did not make persistence emerge where methods differ");
    check(diffusing.at("learned_selection_share").get<double>() > 0.5, "selections were not learned");
  } catch (const std::exception& error) {
    std::fprintf(stderr, "%s\n", error.what());
    return 1;
  }
  return failures ? 1 : 0;
}
