#include "trech/ml/PairInteraction.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <set>
#include <unordered_map>

#include "trech/ml/GenericSurrogate.hpp"

namespace trech::ml {
namespace {

// Where one declared model input reads from, resolved ONCE per interact call
// (the same planning discipline as StateEvolution: the per-pair inner loop must
// be index arithmetic, not a string hash per input per pair).
struct InputSource {
  bool constant = true;
  std::size_t slot = 0;
  double value = 0.0;
};

enum class OutputKind {
  kElementRate,       // d_<element field>_dt -> rate on both members
  kElementIncrement,  // add_<element field>  -> direct increment on both
  kPairRate,          // d_<pair field>_dt    -> rate on the pair's own state
  kPairAssign,        // set_<pair field>     -> assignment on the pair's state
  kIntermediate       // anything else        -> per-pair context only
};

struct OutputTarget {
  OutputKind kind = OutputKind::kIntermediate;
  std::size_t index = 0;  // element/pair field index, or working slot
};

struct PlannedStage {
  const PairStage* stage = nullptr;
  std::vector<InputSource> inputs;
  std::vector<OutputTarget> outputs;
};

// One pair to evaluate.  `link` is the index into the caller's declared link
// list (and therefore into its per-pair state block), or kNoLink for a pair the
// neighbour search found.
constexpr std::size_t kNoLink = static_cast<std::size_t>(-1);

struct PairEntry {
  std::size_t a = 0;
  std::size_t b = 0;
  std::size_t link = kNoLink;
};

// The reserved per-call fact every operator may declare as an input: the
// bounded step it is being integrated over.
constexpr const char* kStepInputName = "dt";

// Reserved per-pair geometry inputs, in working-slot order.  `d*` is the raw
// separation b - a, `u*` its unit vector, `r` its length.  A pair whose members
// share a position reports r = 0 and a zero unit vector rather than a NaN.
constexpr const char* kGeometryInputNames[] = {"r",  "dx", "dy", "dz",
                                               "ux", "uy", "uz"};
constexpr std::size_t kGeometrySlots =
    sizeof(kGeometryInputNames) / sizeof(kGeometryInputNames[0]);

// Cell key for the uniform neighbour grid.  A hash collision merges two cells,
// which can only ADD candidates (every candidate is distance-filtered anyway);
// it can never hide a neighbour, so the pair set stays exact.
std::int64_t cellKey(long long ix, long long iy, long long iz) {
  const std::uint64_t h = static_cast<std::uint64_t>(ix) * 0x9e3779b97f4a7c15ull ^
                          static_cast<std::uint64_t>(iy) * 0xc2b2ae3d27d4eb4full ^
                          static_cast<std::uint64_t>(iz) * 0x165667b19e3779f9ull;
  return static_cast<std::int64_t>(h);
}

long long cellIndex(double coordinate, double size) {
  const double scaled = std::floor(coordinate / size);
  // Clamp absurd/non-finite coordinates into a representable cell rather than
  // invoking undefined conversion behaviour; the distance test still decides.
  if (!std::isfinite(scaled)) {
    return 0;
  }
  const double bounded = std::min(std::max(scaled, -1.0e12), 1.0e12);
  return static_cast<long long>(bounded);
}

}  // namespace

std::string PairInteraction::rateOutputName(const std::string& field) {
  return "d_" + field + "_dt";
}

std::string PairInteraction::incrementOutputName(const std::string& field) {
  return "add_" + field;
}

std::string PairInteraction::assignOutputName(const std::string& field) {
  return "set_" + field;
}

std::string PairInteraction::memberInputName(int member,
                                             const std::string& name) {
  return (member == 0 ? "a_" : "b_") + name;
}

std::string PairInteraction::pairKindName(const std::string& a,
                                          const std::string& b) {
  // Canonical (unordered): a pair of materials is the same interaction whichever
  // member the enumeration happened to call `a`.
  return a <= b ? a + "|" + b : b + "|" + a;
}

void PairInteraction::addStage(std::string name, DimensionScale scale,
                               const GenericSurrogate* model,
                               std::size_t pairKindIndex) {
  PairStage stage;
  stage.name = std::move(name);
  stage.scale = scale;
  stage.model = model;
  stage.pairKindIndex = pairKindIndex;
  stages_.push_back(std::move(stage));
}

PairInteractionResult PairInteraction::interact(
    const PairInteractionRequest& request) const {
  PairInteractionResult result;
  result.state = request.state;
  result.pairState = request.pairState;

  const std::size_t fieldCount = request.fields.size();
  const std::size_t auxCount = request.auxNames.size();
  const std::size_t pairFieldCount = request.pairFields.size();
  const std::size_t elementCount = request.elementCount;
  const std::size_t linkCount = request.links.size();
  if (fieldCount == 0 || elementCount == 0 ||
      request.state.size() < fieldCount * elementCount ||
      request.aux.size() < auxCount * elementCount ||
      request.pairState.size() < pairFieldCount * linkCount) {
    return result;  // malformed block: leave every caller array as-is
  }

  // ---- build the canonical pair list --------------------------------------
  // Declared links first: they are topology the caller owns, are always
  // evaluated (a stretched bond is the interesting case, not one to drop), and
  // are the only pairs that carry state.
  std::vector<PairEntry> links;
  links.reserve(linkCount);
  for (std::size_t l = 0; l < linkCount; ++l) {
    std::size_t a = request.links[l].a;
    std::size_t b = request.links[l].b;
    if (a == b || a >= elementCount || b >= elementCount) {
      ++result.invalidLinks;
      continue;
    }
    if (a > b) {
      std::swap(a, b);  // canonical orientation: member `a` is the lower index
    }
    links.push_back({a, b, l});
  }
  std::stable_sort(links.begin(), links.end(),
                   [](const PairEntry& x, const PairEntry& y) {
                     return x.a != y.a ? x.a < y.a : x.b < y.b;
                   });
  {
    std::vector<PairEntry> unique;
    unique.reserve(links.size());
    for (const PairEntry& entry : links) {
      if (!unique.empty() && unique.back().a == entry.a &&
          unique.back().b == entry.b) {
        ++result.duplicateLinks;  // keep the first declaration's pair state
        continue;
      }
      unique.push_back(entry);
    }
    links.swap(unique);
  }

  // Dynamic neighbours: a uniform cell list at the caller's cutoff.  Scanning
  // `a` ascending and sorting each element's candidates makes the emitted list
  // globally sorted by (a, b) BY CONSTRUCTION, so neither the cell size nor the
  // hash-map layout can reorder the floating-point accumulation -- and a cap
  // truncates a canonical prefix rather than an arbitrary subset.
  std::vector<PairEntry> neighbors;
  const bool searchNeighbors =
      request.cutoff > 0.0 && request.positions.size() >= 3 * elementCount;
  if (searchNeighbors) {
    const double cutoff = request.cutoff;
    const double cutoff2 = cutoff * cutoff;
    std::unordered_map<std::int64_t, std::vector<std::size_t>> cells;
    cells.reserve(elementCount * 2);
    for (std::size_t e = 0; e < elementCount; ++e) {
      const double* p = &request.positions[3 * e];
      cells[cellKey(cellIndex(p[0], cutoff), cellIndex(p[1], cutoff),
                    cellIndex(p[2], cutoff))]
          .push_back(e);
    }
    std::vector<std::size_t> candidates;
    for (std::size_t a = 0; a < elementCount; ++a) {
      const double* pa = &request.positions[3 * a];
      const long long ix = cellIndex(pa[0], cutoff);
      const long long iy = cellIndex(pa[1], cutoff);
      const long long iz = cellIndex(pa[2], cutoff);
      candidates.clear();
      for (long long dx = -1; dx <= 1; ++dx) {
        for (long long dy = -1; dy <= 1; ++dy) {
          for (long long dz = -1; dz <= 1; ++dz) {
            const auto cell = cells.find(cellKey(ix + dx, iy + dy, iz + dz));
            if (cell == cells.end()) {
              continue;
            }
            for (const std::size_t b : cell->second) {
              if (b <= a) {
                continue;  // canonical (a < b): each pair enumerated once
              }
              const double* pb = &request.positions[3 * b];
              const double sx = pb[0] - pa[0];
              const double sy = pb[1] - pa[1];
              const double sz = pb[2] - pa[2];
              if (sx * sx + sy * sy + sz * sz <= cutoff2) {
                candidates.push_back(b);
              }
            }
          }
        }
      }
      std::sort(candidates.begin(), candidates.end());
      candidates.erase(std::unique(candidates.begin(), candidates.end()),
                       candidates.end());
      for (const std::size_t b : candidates) {
        if (request.maxNeighborPairs > 0 &&
            neighbors.size() >= request.maxNeighborPairs) {
          ++result.neighborPairsSkipped;  // counted in full, evaluated bounded
          continue;
        }
        neighbors.push_back({a, b, kNoLink});
      }
    }
    result.neighborPairsTruncated = result.neighborPairsSkipped > 0;
  }

  // Merge the two sorted lists, dropping a neighbour pair that is already a
  // declared link (a bond inside the cutoff is one pair, evaluated once).
  std::vector<PairEntry> pairs;
  pairs.reserve(links.size() + neighbors.size());
  {
    std::size_t li = 0;
    std::size_t ni = 0;
    auto before = [](const PairEntry& x, const PairEntry& y) {
      return x.a != y.a ? x.a < y.a : x.b < y.b;
    };
    while (li < links.size() || ni < neighbors.size()) {
      if (ni >= neighbors.size()) {
        pairs.push_back(links[li++]);
      } else if (li >= links.size()) {
        pairs.push_back(neighbors[ni++]);
      } else if (before(links[li], neighbors[ni])) {
        pairs.push_back(links[li++]);
      } else if (before(neighbors[ni], links[li])) {
        pairs.push_back(neighbors[ni++]);
      } else {
        pairs.push_back(links[li++]);  // same pair: the link wins (it has state)
        ++ni;
      }
    }
  }
  result.linkPairCount = links.size();
  result.neighborPairCount = pairs.size() - links.size();
  result.pairCount = pairs.size();
  if (pairs.empty()) {
    return result;
  }

  // ---- order stages by scale band (registration order breaks ties) --------
  std::vector<const PairStage*> ordered;
  ordered.reserve(stages_.size());
  for (const PairStage& s : stages_) {
    ordered.push_back(&s);
  }
  std::stable_sort(ordered.begin(), ordered.end(),
                   [](const PairStage* x, const PairStage* y) {
                     return static_cast<int>(x->scale) < static_cast<int>(y->scale);
                   });

  // ---- working-vector layout ----------------------------------------------
  // pair state | geometry | a fields | b fields | a aux | b aux | intermediates
  // Precedence when a name appears twice is pair state > member facts >
  // geometry: the pair's own state is the most specific meaning of a name.
  const std::size_t geometryBase = pairFieldCount;
  const std::size_t memberFieldBase = geometryBase + kGeometrySlots;
  const std::size_t memberAuxBase = memberFieldBase + 2 * fieldCount;
  std::size_t workingSize = memberAuxBase + 2 * auxCount;

  std::unordered_map<std::string, std::size_t> slotOf;
  slotOf.reserve(pairFieldCount + kGeometrySlots + 2 * (fieldCount + auxCount) + 8);
  for (std::size_t p = 0; p < pairFieldCount; ++p) {
    slotOf.emplace(request.pairFields[p].name, p);
  }
  for (std::size_t f = 0; f < fieldCount; ++f) {
    slotOf.emplace(memberInputName(0, request.fields[f].name),
                   memberFieldBase + f);
    slotOf.emplace(memberInputName(1, request.fields[f].name),
                   memberFieldBase + fieldCount + f);
  }
  for (std::size_t a = 0; a < auxCount; ++a) {
    slotOf.emplace(memberInputName(0, request.auxNames[a]), memberAuxBase + a);
    slotOf.emplace(memberInputName(1, request.auxNames[a]),
                   memberAuxBase + auxCount + a);
  }
  for (std::size_t g = 0; g < kGeometrySlots; ++g) {
    slotOf.emplace(kGeometryInputNames[g], geometryBase + g);
  }

  // ---- plan every stage, registering intermediates as they appear ---------
  std::vector<PlannedStage> planned;
  planned.reserve(ordered.size());
  result.stages.reserve(ordered.size());

  for (const PairStage* stage : ordered) {
    PairStageTrace trace;
    trace.model = stage->name;
    trace.scale = stage->scale;

    if (!stage->model || !stage->model->loaded() ||
        stage->model->inputNames().empty() ||
        stage->model->outputNames().empty()) {
      result.stages.push_back(std::move(trace));
      continue;  // graceful degradation, matching ScaleCascade/StateEvolution
    }

    PlannedStage plan;
    plan.stage = stage;

    const std::vector<std::string>& inputNames = stage->model->inputNames();
    plan.inputs.reserve(inputNames.size());
    for (const std::string& in : inputNames) {
      InputSource source;
      const auto slot = slotOf.find(in);
      if (slot != slotOf.end()) {
        source.constant = false;
        source.slot = slot->second;
      } else if (in == kStepInputName) {
        source.value = request.dt;
      } else {
        const auto shared = request.shared.find(in);
        if (shared != request.shared.end()) {
          source.value = shared->second;
        } else {
          source.value = 0.0;  // same default as GenericSurrogate::predict
          trace.missingInputs.push_back(in);
        }
      }
      plan.inputs.push_back(source);
    }

    const std::vector<std::string>& outputNames = stage->model->outputNames();
    plan.outputs.reserve(outputNames.size());
    for (const std::string& out : outputNames) {
      OutputTarget target;
      bool applied = false;
      // Decode against the DECLARED field names rather than by string surgery,
      // so a field whose own name contains an affix cannot be misread.  Pair
      // state wins over element state, matching the input precedence.
      for (std::size_t p = 0; p < pairFieldCount && !applied; ++p) {
        const std::string& name = request.pairFields[p].name;
        if (out == rateOutputName(name)) {
          target.kind = OutputKind::kPairRate;
          target.index = p;
          trace.ratedPairFields.push_back(name);
          applied = true;
        } else if (out == assignOutputName(name)) {
          target.kind = OutputKind::kPairAssign;
          target.index = p;
          trace.assignedPairFields.push_back(name);
          applied = true;
        }
      }
      for (std::size_t f = 0; f < fieldCount && !applied; ++f) {
        const std::string& name = request.fields[f].name;
        if (out == rateOutputName(name)) {
          target.kind = OutputKind::kElementRate;
          target.index = f;
          trace.ratedElementFields.push_back(name);
          applied = true;
        } else if (out == incrementOutputName(name)) {
          target.kind = OutputKind::kElementIncrement;
          target.index = f;
          trace.incrementedElementFields.push_back(name);
          applied = true;
        }
      }
      if (!applied) {
        // An intermediate: it gets a working slot under its literal name so
        // higher-scale stages consume it like a cascade stage output.
        auto [it, inserted] = slotOf.emplace(out, workingSize);
        if (inserted) {
          ++workingSize;
        }
        target.kind = OutputKind::kIntermediate;
        target.index = it->second;
        trace.intermediateOutputs.push_back(out);
        // A field-directed name that updates nothing: a rate/increment for an
        // undeclared field, or `set_<element field>` -- many pairs cannot
        // assign one element a single value, so an assignment to a member field
        // is refused rather than being resolved by whichever pair came last.
        bool unapplied = out.rfind("add_", 0) == 0 && out.size() > 4;
        unapplied = unapplied || (out.rfind("d_", 0) == 0 && out.size() > 5 &&
                                  out.compare(out.size() - 3, 3, "_dt") == 0);
        unapplied = unapplied || (out.rfind("set_", 0) == 0 && out.size() > 4);
        if (unapplied) {
          trace.unappliedFieldOutputs.push_back(out);
        }
      }
      plan.outputs.push_back(target);
    }

    trace.ran = true;
    trace.domainMeasured = stage->model->domainMeasured();
    if (stage->pairKindIndex != kAnyElementKind &&
        stage->pairKindIndex < request.pairKindNames.size()) {
      trace.pairKind = request.pairKindNames[stage->pairKindIndex];
    }

    const std::vector<std::string>& bands = stage->model->trainedScaleBands();
    for (std::size_t bi = 0; bi < bands.size(); ++bi) {
      trace.trainedScale += (bi ? "," : "") + bands[bi];
    }
    if (!bands.empty() && stage->scale != DimensionScale::kUnscaled &&
        std::find(bands.begin(), bands.end(),
                  dimensionScaleName(stage->scale)) == bands.end()) {
      trace.scaleMismatch = true;
      ++result.stagesScaleMismatched;
    }
    trace.hasHoldout = stage->model->hasHoldout();
    trace.holdoutR2 = stage->model->holdoutR2Min();
    trace.holdoutSamples = stage->model->holdoutSamples();

    planned.push_back(std::move(plan));
    result.stages.push_back(std::move(trace));
    ++result.stagesRun;
  }

  if (planned.empty()) {
    return result;  // every stage skipped: state untouched, traces recorded
  }

  std::vector<std::size_t> traceIndexOf;
  traceIndexOf.reserve(planned.size());
  for (std::size_t i = 0; i < result.stages.size(); ++i) {
    if (result.stages[i].ran) {
      traceIndexOf.push_back(i);
    }
  }

  // ---- evaluate every pair ------------------------------------------------
  // Element contributions accumulate first and are applied once at the end, so
  // no member sees a partially-updated neighbour and the outcome cannot depend
  // on which pair happened to be evaluated first.
  std::vector<double> elementRates(elementCount * fieldCount, 0.0);
  std::vector<double> elementIncrements(elementCount * fieldCount, 0.0);
  std::vector<double> working(workingSize, 0.0);
  std::vector<double> pairRates(pairFieldCount, 0.0);
  std::vector<double> x;
  std::vector<double> y;
  std::vector<std::set<std::string>> outOfDomainUnion(planned.size());
  std::vector<std::set<std::string>> starvedUnion(planned.size());
  const bool havePositions = request.positions.size() >= 3 * elementCount;

  // Resolve each pair's material combination ONCE. The engine composes the
  // canonical name from the two members' kinds and looks it up in the caller's
  // declared pair-kind vocabulary, so a stage bound to `sand|melt` sees exactly
  // the grain-melt pairs however the enumeration ordered them.
  std::unordered_map<std::string, std::size_t> pairKindIndexOf;
  for (std::size_t i = 0; i < request.pairKindNames.size(); ++i) {
    pairKindIndexOf.emplace(request.pairKindNames[i], i);
  }
  const bool haveKinds = !request.elementKindIndex.empty() &&
                         !request.elementKindNames.empty() &&
                         !request.pairKindNames.empty();

  for (const PairEntry& pair : pairs) {
    std::size_t pairKind = kAnyElementKind;
    if (haveKinds) {
      const std::size_t ka = pair.a < request.elementKindIndex.size()
                                 ? request.elementKindIndex[pair.a]
                                 : kAnyElementKind;
      const std::size_t kb = pair.b < request.elementKindIndex.size()
                                 ? request.elementKindIndex[pair.b]
                                 : kAnyElementKind;
      if (ka < request.elementKindNames.size() &&
          kb < request.elementKindNames.size()) {
        const auto it = pairKindIndexOf.find(
            pairKindName(request.elementKindNames[ka],
                         request.elementKindNames[kb]));
        if (it != pairKindIndexOf.end()) {
          pairKind = it->second;
        } else {
          pairKind = request.pairKindNames.size();  // declared by nobody
        }
      }
    }
    const std::size_t aBase = pair.a * fieldCount;
    const std::size_t bBase = pair.b * fieldCount;
    for (std::size_t p = 0; p < pairFieldCount; ++p) {
      working[p] = pair.link == kNoLink
                       ? 0.0
                       : request.pairState[pair.link * pairFieldCount + p];
      pairRates[p] = 0.0;
    }
    double sx = 0.0;
    double sy = 0.0;
    double sz = 0.0;
    if (havePositions) {
      const double* pa = &request.positions[3 * pair.a];
      const double* pb = &request.positions[3 * pair.b];
      sx = pb[0] - pa[0];
      sy = pb[1] - pa[1];
      sz = pb[2] - pa[2];
    }
    const double r = std::sqrt(sx * sx + sy * sy + sz * sz);
    const double inv = r > 0.0 ? 1.0 / r : 0.0;
    working[geometryBase + 0] = r;
    working[geometryBase + 1] = sx;
    working[geometryBase + 2] = sy;
    working[geometryBase + 3] = sz;
    working[geometryBase + 4] = sx * inv;
    working[geometryBase + 5] = sy * inv;
    working[geometryBase + 6] = sz * inv;
    for (std::size_t f = 0; f < fieldCount; ++f) {
      working[memberFieldBase + f] = request.state[aBase + f];
      working[memberFieldBase + fieldCount + f] = request.state[bBase + f];
    }
    for (std::size_t a = 0; a < auxCount; ++a) {
      working[memberAuxBase + a] = request.aux[pair.a * auxCount + a];
      working[memberAuxBase + auxCount + a] = request.aux[pair.b * auxCount + a];
    }
    for (std::size_t s = memberAuxBase + 2 * auxCount; s < workingSize; ++s) {
      working[s] = 0.0;  // intermediates never carry over between pairs
    }

    for (std::size_t pi = 0; pi < planned.size(); ++pi) {
      const PlannedStage& plan = planned[pi];
      if (plan.stage->pairKindIndex != kAnyElementKind &&
          plan.stage->pairKindIndex != pairKind) {
        continue;  // another material combination's interaction
      }
      x.resize(plan.inputs.size());
      for (std::size_t i = 0; i < plan.inputs.size(); ++i) {
        const InputSource& src = plan.inputs[i];
        x[i] = src.constant ? src.value : working[src.slot];
      }
      if (!plan.stage->model->predictVector(x, &y) ||
          y.size() != plan.outputs.size()) {
        continue;  // a stage that cannot evaluate contributes nothing
      }

      PairStageTrace& trace = result.stages[traceIndexOf[pi]];
      const GenericSurrogate::Coverage cov = plan.stage->model->coverageVector(x);
      if (!cov.inDomain) {
        ++trace.pairsOutOfDomain;
        ++result.outOfDomainInferenceCount;
        for (const std::string& name : cov.outOfDomainInputs) {
          outOfDomainUnion[pi].insert(name);
        }
      }
      if (!cov.starvedInputs.empty()) {
        ++trace.pairsStarved;
        for (const std::string& name : cov.starvedInputs) {
          starvedUnion[pi].insert(name);
        }
      }
      trace.maxExtrapolation = std::max(trace.maxExtrapolation, cov.extrapolation);
      trace.maxStandardizedDeviation =
          std::max(trace.maxStandardizedDeviation, cov.maxStandardizedDeviation);

      for (std::size_t o = 0; o < plan.outputs.size(); ++o) {
        const OutputTarget& target = plan.outputs[o];
        const double value = y[o];
        switch (target.kind) {
          case OutputKind::kElementRate:
          case OutputKind::kElementIncrement: {
            // Equal and opposite (or shared) BY CONSTRUCTION: the same double
            // is applied to both members, so an antisymmetric field's pair
            // contribution cancels exactly.
            std::vector<double>& sink = target.kind == OutputKind::kElementRate
                                            ? elementRates
                                            : elementIncrements;
            const double other =
                request.fields[target.index].symmetry == PairSymmetry::kSymmetric
                    ? value
                    : -value;
            sink[aBase + target.index] += value;
            sink[bBase + target.index] += other;
            break;
          }
          case OutputKind::kPairRate:
            pairRates[target.index] += value;  // stages accumulate on one field
            break;
          case OutputKind::kPairAssign:
            working[target.index] = value;  // visible to higher-scale stages
            break;
          case OutputKind::kIntermediate:
            working[target.index] = value;
            break;
        }
      }
      ++trace.pairsMatched;
      ++result.inferenceCount;
    }

    // Integrate the pair's own state once, at the bounded step the caller
    // chose, then apply its declared bounds.  Only a declared link persists.
    if (pair.link != kNoLink && pairFieldCount > 0) {
      const std::size_t base = pair.link * pairFieldCount;
      for (std::size_t p = 0; p < pairFieldCount; ++p) {
        double value = working[p] + pairRates[p] * request.dt;
        const PairStateField& field = request.pairFields[p];
        if (value < field.minValue) value = field.minValue;
        if (value > field.maxValue) value = field.maxValue;
        result.pairState[base + p] = value;
      }
    }
  }

  // ---- apply the accumulated element contributions ------------------------
  for (std::size_t e = 0; e < elementCount; ++e) {
    const std::size_t base = e * fieldCount;
    for (std::size_t f = 0; f < fieldCount; ++f) {
      const double delta =
          elementIncrements[base + f] + elementRates[base + f] * request.dt;
      if (delta == 0.0) {
        continue;  // an element no pair touched keeps its value bit-for-bit
      }
      double value = request.state[base + f] + delta;
      const PairElementField& field = request.fields[f];
      if (value < field.minValue) value = field.minValue;
      if (value > field.maxValue) value = field.maxValue;
      result.state[base + f] = value;
    }
  }

  for (std::size_t pi = 0; pi < planned.size(); ++pi) {
    PairStageTrace& trace = result.stages[traceIndexOf[pi]];
    trace.outOfDomainInputs.assign(outOfDomainUnion[pi].begin(),
                                   outOfDomainUnion[pi].end());
    trace.starvedInputs.assign(starvedUnion[pi].begin(), starvedUnion[pi].end());
    if (trace.pairsOutOfDomain > 0) {
      ++result.stagesExtrapolating;
    }
    if (trace.pairsStarved > 0) {
      ++result.stagesStarved;
    }
    std::sort(trace.ratedElementFields.begin(), trace.ratedElementFields.end());
    std::sort(trace.incrementedElementFields.begin(),
              trace.incrementedElementFields.end());
    std::sort(trace.ratedPairFields.begin(), trace.ratedPairFields.end());
    std::sort(trace.assignedPairFields.begin(), trace.assignedPairFields.end());
    std::sort(trace.intermediateOutputs.begin(), trace.intermediateOutputs.end());
    std::sort(trace.unappliedFieldOutputs.begin(),
              trace.unappliedFieldOutputs.end());
    std::sort(trace.missingInputs.begin(), trace.missingInputs.end());
  }

  result.ran = result.inferenceCount > 0;
  return result;
}

}  // namespace trech::ml
