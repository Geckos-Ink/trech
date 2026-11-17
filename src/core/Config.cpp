#include "trech/core/Config.hpp"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <limits>
#include <array>
#include <stdexcept>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>

namespace trech {
namespace {

// Key-read ledger for unknown-key reporting: every key the parser asks an
// object about (has / fieldOr / ...) is recorded against that object, and
// after parsing, any key of a visited object that was never asked about is
// reported as unknown (a misspelling or a field the engine does not read).
// Objects the parser never queries (free-form blocks such as hooks.inputs)
// are not judged. Single-threaded per parse via a thread_local pointer.
using KeyLedger = std::unordered_map<const nlohmann::json*, std::unordered_set<std::string>>;
thread_local KeyLedger* tKeyLedger = nullptr;

bool has(const nlohmann::json& j, const std::string& key) {
  if (tKeyLedger && j.is_object()) {
    (*tKeyLedger)[&j].insert(key);
  }
  return j.contains(key);
}

void collectUnknownKeys(const nlohmann::json& j, const std::string& path, const KeyLedger& ledger,
                        std::vector<std::string>& out) {
  if (j.is_array()) {
    for (std::size_t i = 0; i < j.size(); ++i) {
      collectUnknownKeys(j.at(i), path + "[" + std::to_string(i) + "]", ledger, out);
    }
    return;
  }
  if (!j.is_object()) {
    return;
  }
  const auto visited = ledger.find(&j);
  for (auto it = j.begin(); it != j.end(); ++it) {
    const std::string child = path.empty() ? it.key() : path + "." + it.key();
    if (visited != ledger.end() && visited->second.count(it.key()) == 0) {
      out.push_back(child);  // its subtree was never read either
      continue;
    }
    collectUnknownKeys(it.value(), child, ledger, out);
  }
}

[[noreturn]] void throwFieldError(const std::string& message);

// A string or an array of strings at `field`; anything else is a FieldError
// ("tags[2] must be a string"). Entries were silently dropped before 2026-11-15.
void appendStringListFromJson(const nlohmann::json& j, std::vector<std::string>& out,
                              const std::string& field) {
  if (j.is_string()) {
    out.push_back(j.get<std::string>());
    return;
  }
  if (!j.is_array()) {
    throwFieldError(field + " must be a string or an array of strings");
  }
  for (std::size_t i = 0; i < j.size(); ++i) {
    if (!j.at(i).is_string()) {
      throwFieldError(field + "[" + std::to_string(i) + "] must be a string");
    }
    out.push_back(j.at(i).get<std::string>());
  }
}

// Field readers for every typed config field: a present field of the wrong
// JSON type throws a FieldError naming the field relative to its block, and
// located() prefixes each enclosing level, so the final message reads e.g.
// "optics.spectrum[2].energyEv must be a number" instead of a bare
// nlohmann::json type_error with no location. Absent fields keep their
// defaults. Numbers are not read from booleans (nlohmann would give 0/1).
class FieldError : public std::invalid_argument {
 public:
  using std::invalid_argument::invalid_argument;
};

[[noreturn]] void throwFieldError(const std::string& message) { throw FieldError(message); }

// An integer-typed field (a count, limit, seed, Z/A, ...) takes only a JSON
// integer that fits the C++ type: 2.5 or "3" is "must be an integer", a
// negative value into an unsigned field is "must be a non-negative integer",
// and a value outside the type's range is "is out of range". nlohmann would
// otherwise truncate 2.5 to 2 and wrap -1 into an unsigned seed. A
// non-negative integer may arrive signed (built in C++) or unsigned (parsed).
template <typename T>
T integerFieldValue(const nlohmann::json& value, const std::string& field) {
  if (!value.is_number_integer()) {
    throw FieldError(field + " must be an integer");
  }
  const bool negative = !value.is_number_unsigned() && value.get<std::int64_t>() < 0;
  if constexpr (std::is_unsigned_v<T>) {
    if (negative) {
      throw FieldError(field + " must be a non-negative integer");
    }
  }
  const bool inRange =
      negative ? value.get<std::int64_t>() >= static_cast<std::int64_t>(std::numeric_limits<T>::min())
               : value.get<std::uint64_t>() <= static_cast<std::uint64_t>(std::numeric_limits<T>::max());
  if (!inRange) {
    throw FieldError(field + " is out of range");
  }
  return value.get<T>();
}

// An integer-valued count/limit: present and not an integer is a FieldError.
template <typename T>
T integerFieldOr(const nlohmann::json& j, const char* key, T fallback) {
  if (!has(j, key)) {
    return fallback;
  }
  return integerFieldValue<T>(j.at(key), key);
}

template <typename T>
T fieldValue(const nlohmann::json& value, const std::string& field) {
  if constexpr (std::is_same_v<T, bool>) {
    if (!value.is_boolean()) {
      throw FieldError(field + " must be a boolean");
    }
  } else if constexpr (std::is_integral_v<T>) {
    return integerFieldValue<T>(value, field);
  } else if constexpr (std::is_arithmetic_v<T>) {
    if (!value.is_number()) {
      throw FieldError(field + " must be a number");
    }
  } else {
    if (!value.is_string()) {
      throw FieldError(field + " must be a string");
    }
  }
  return value.get<T>();
}

template <typename T>
T fieldOr(const nlohmann::json& j, const char* key, const T& fallback) {
  if (!has(j, key)) {
    return fallback;
  }
  return fieldValue<T>(j.at(key), key);
}

double geometryNumber(const nlohmann::json& value, const std::string& field) {
  return fieldValue<double>(value, field);
}

double geometryNumberOr(const nlohmann::json& j, const char* key, double fallback,
                        const std::string& prefix) {
  if (!has(j, key)) {
    return fallback;
  }
  return geometryNumber(j.at(key), prefix + key);
}

std::string geometryStringOr(const nlohmann::json& j, const char* key,
                             const std::string& fallback, const std::string& prefix) {
  if (!has(j, key)) {
    return fallback;
  }
  return fieldValue<std::string>(j.at(key), prefix + key);
}

// Runs one parse step at `where` ("optics", "spectrum[2]", "beams[1] ('probe')").
// A FieldError gains the location as a path segment (an index segment "[k]"
// joins without a dot); any other JSON exception
// keeps the library message behind it. Fully located errors (plain
// std::invalid_argument / std::runtime_error) pass through unchanged.
template <typename Fn>
auto located(const std::string& where, Fn&& parse) -> decltype(parse()) {
  try {
    return parse();
  } catch (const FieldError& error) {
    const std::string inner = error.what();
    const bool bare = inner.rfind('[', 0) == 0 || inner.rfind(' ', 0) == 0;
    throw FieldError(where + (bare ? "" : ".") + inner);
  } catch (const nlohmann::json::exception& error) {
    throw FieldError(where + ": " + error.what());
  }
}

// "<base>[i]", plus " ('name')" when the entry has a string name.
std::string entryLocation(const std::string& base, std::size_t index, const nlohmann::json& entry) {
  std::string where = base + "[" + std::to_string(index) + "]";
  if (entry.is_object() && has(entry, "name") && entry.at("name").is_string()) {
    where += " ('" + entry.at("name").get<std::string>() + "')";
  }
  return where;
}

// Object-only blocks and collection entries. Before 2026-11-17 a scalar in an
// object position silently fell back to the defaults (`run: 5` ran with the
// default run block, also through a lab patch). JSON null still means "unset"
// (it keeps the defaults or skips the entry); any other wrong type is a
// FieldError naming `where` (empty = the enclosing location), e.g.
// "run must be an object (got number)", "materials[2] must be an object".
bool objectAt(const nlohmann::json& j, const std::string& where = {},
              const char* expected = "an object") {
  if (j.is_object()) {
    return true;
  }
  if (j.is_null()) {
    return false;
  }
  throw FieldError(where + " must be " + expected + " (got " + j.type_name() + ")");
}

// A collection field that takes an array of entries or one entry object.
// Call after the array/object branches; null keeps the collection empty.
void rejectCollection(const nlohmann::json& j, const std::string& where) {
  if (!j.is_null()) {
    throw FieldError(where + " must be an array or an object (got " + j.type_name() + ")");
  }
}

DetectorConfig detectorFromJson(const nlohmann::json& j, const DetectorConfig& defaults) {
  DetectorConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.worldSizeMm = fieldOr(j, "worldSizeMm", cfg.worldSizeMm);
  cfg.worldMaterial = fieldOr(j, "worldMaterial", cfg.worldMaterial);
  cfg.mediumBoxMm = fieldOr(j, "mediumBoxMm", cfg.mediumBoxMm);
  cfg.mediumMaterial = fieldOr(j, "mediumMaterial", cfg.mediumMaterial);
  if (has(j, "waterBoxMm")) {
    cfg.mediumBoxMm = fieldOr(j, "waterBoxMm", cfg.mediumBoxMm);
  }
  if (has(j, "waterMaterial")) {
    cfg.mediumMaterial = fieldOr(j, "waterMaterial", cfg.mediumMaterial);
  }
  cfg.temperatureK = fieldOr(j, "temperatureK", cfg.temperatureK);
  cfg.pressureAtm = fieldOr(j, "pressureAtm", cfg.pressureAtm);
  return cfg;
}

// [x, y, z] (>= 3 entries) or {x, y, z}; other forms keep the defaults, as before.
std::array<double, 3> geometryTriple(const nlohmann::json& j, std::array<double, 3> xyz,
                                     const std::string& field) {
  if (j.is_array() && j.size() >= 3) {
    for (std::size_t k = 0; k < 3; ++k) {
      xyz[k] = geometryNumber(j.at(k), field + "[" + std::to_string(k) + "]");
    }
  } else if (j.is_object()) {
    const char* keys[] = {"x", "y", "z"};
    for (std::size_t k = 0; k < 3; ++k) {
      xyz[k] = geometryNumberOr(j, keys[k], xyz[k], field + ".");
    }
  }
  return xyz;
}

BeamConfig beamFromJson(const nlohmann::json& j, const BeamConfig& defaults) {
  BeamConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.name = fieldOr(j, "name", cfg.name);
  cfg.particle = fieldOr(j, "particle", cfg.particle);
  cfg.energyMeV = fieldOr(j, "energyMeV", cfg.energyMeV);
  if (has(j, "direction")) {
    const auto d = geometryTriple(j.at("direction"),
                                  {cfg.directionX, cfg.directionY, cfg.directionZ}, "direction");
    cfg.directionX = d[0];
    cfg.directionY = d[1];
    cfg.directionZ = d[2];
  }
  if (has(j, "originMm")) {
    const auto o = geometryTriple(j.at("originMm"),
                                  {cfg.originXMm, cfg.originYMm, cfg.originZMm}, "originMm");
    cfg.originXMm = o[0];
    cfg.originYMm = o[1];
    cfg.originZMm = o[2];
  }
  // Source variety: accept flat keys or a nested `spread` object (the latter
  // reads naturally in JS scenarios). Flat keys win if both are present.
  if (has(j, "spread") && objectAt(j.at("spread"), "spread")) {
    const auto& s = j.at("spread");
    located("spread", [&] {
      cfg.spotRadiusMm = fieldOr(s, "spotRadiusMm", cfg.spotRadiusMm);
      cfg.divergenceDeg = fieldOr(s, "divergenceDeg", cfg.divergenceDeg);
      cfg.energySpreadFractional =
          fieldOr(s, "energySpreadFractional", cfg.energySpreadFractional);
    });
  }
  cfg.spotRadiusMm = fieldOr(j, "spotRadiusMm", cfg.spotRadiusMm);
  cfg.divergenceDeg = fieldOr(j, "divergenceDeg", cfg.divergenceDeg);
  cfg.energySpreadFractional =
      fieldOr(j, "energySpreadFractional", cfg.energySpreadFractional);
  // Polarization: accept a bare mode string ("linear") or an object
  // ({mode, angleDeg}); a flat polarizationAngleDeg wins if also present.
  if (has(j, "polarization")) {
    const auto& p = j.at("polarization");
    if (p.is_string()) {
      cfg.polarization = p.get<std::string>();
    } else if (p.is_object()) {
      located("polarization", [&] {
        cfg.polarization = fieldOr(p, "mode", cfg.polarization);
        cfg.polarizationAngleDeg = fieldOr(p, "angleDeg", cfg.polarizationAngleDeg);
      });
    } else if (!p.is_null()) {
      objectAt(p, "polarization", "a string or an object");
    }
  }
  cfg.polarizationAngleDeg =
      fieldOr(j, "polarizationAngleDeg", cfg.polarizationAngleDeg);
  // Optional emission spectrum. Each entry gives an energy (as `energyMeV`,
  // `energyEv`, or `wavelengthNm`) and an optional `weight`. Authoring in eV or
  // nm is natural for optical photons; everything is normalized to MeV here.
  if (has(j, "spectrum")) {
    const auto parseLine = [](const nlohmann::json& e) -> BeamSpectralLine {
      BeamSpectralLine line;
      if (has(e, "energyMeV")) {
        line.energyMeV = fieldOr(e, "energyMeV", 0.0);
      } else if (has(e, "energyEv")) {
        line.energyMeV = fieldOr(e, "energyEv", 0.0) * 1.0e-6;
      } else if (has(e, "wavelengthNm")) {
        const double nm = fieldOr(e, "wavelengthNm", 0.0);
        if (nm > 0.0) {
          line.energyMeV = (1239.841984 / nm) * 1.0e-6;  // hc in eV*nm -> MeV
        }
      }
      line.weight = fieldOr(e, "weight", 1.0);
      return line;
    };
    const auto& spec = j.at("spectrum");
    cfg.spectrum.clear();
    if (spec.is_array()) {
      for (std::size_t i = 0; i < spec.size(); ++i) {
        const auto& e = spec.at(i);
        if (objectAt(e, "spectrum[" + std::to_string(i) + "]")) {
          BeamSpectralLine line =
              located("spectrum[" + std::to_string(i) + "]", [&] { return parseLine(e); });
          if (line.energyMeV > 0.0 && line.weight > 0.0) {
            cfg.spectrum.push_back(line);
          }
        }
      }
    } else if (spec.is_object()) {
      BeamSpectralLine line = located("spectrum", [&] { return parseLine(spec); });
      if (line.energyMeV > 0.0 && line.weight > 0.0) {
        cfg.spectrum.push_back(line);
      }
    } else {
      rejectCollection(spec, "spectrum");
    }
  }
  cfg.active = fieldOr(j, "active", cfg.active);
  return cfg;
}

// Parses one beam and prefixes any wrong-typed field with its location
// ("beam", "beams[2] ('probe')"), like the geometry volume reader.
BeamConfig locatedBeamFromJson(const nlohmann::json& j, const BeamConfig& defaults,
                               const std::string& where) {
  return located(where, [&] { return beamFromJson(j, defaults); });
}

void appendBeamsFromJson(const nlohmann::json& j, std::vector<BeamConfig>& out) {
  if (j.is_array()) {
    for (std::size_t i = 0; i < j.size(); ++i) {
      const auto& entry = j.at(i);
      if (objectAt(entry, entryLocation("beams", i, entry))) {
        out.push_back(locatedBeamFromJson(entry, BeamConfig{}, entryLocation("beams", i, entry)));
      }
    }
  } else if (j.is_object()) {
    out.push_back(locatedBeamFromJson(j, BeamConfig{}, "beams"));
  } else {
    rejectCollection(j, "beams");
  }
}

BeamConfig selectPrimaryBeam(const std::vector<BeamConfig>& beams,
                             const BeamConfig& fallback) {
  for (const auto& beam : beams) {
    if (beam.active) {
      return beam;
    }
  }
  if (!beams.empty()) {
    return beams.front();
  }
  return fallback;
}

// Serialize the optional origin/variety fields only when they differ from the
// historical defaults. This keeps the canonical config (and its hash) byte
// identical for scenarios that don't use them, so existing provenance and the
// determinism-replay baselines are unaffected.
void writeBeamExtras(nlohmann::json& entry, const BeamConfig& beam) {
  if (beam.originXMm != 0.0 || beam.originYMm != 0.0 || beam.originZMm != 0.0) {
    entry["originMm"] = {beam.originXMm, beam.originYMm, beam.originZMm};
  }
  if (beam.spotRadiusMm != 0.0) {
    entry["spotRadiusMm"] = beam.spotRadiusMm;
  }
  if (beam.divergenceDeg != 0.0) {
    entry["divergenceDeg"] = beam.divergenceDeg;
  }
  if (beam.energySpreadFractional != 0.0) {
    entry["energySpreadFractional"] = beam.energySpreadFractional;
  }
  // Default "" (unpolarized sampling) is left unserialized so optical scenarios
  // that don't set polarization keep their exact config hash even though the
  // engine now samples polarization explicitly.
  if (!beam.polarization.empty()) {
    entry["polarization"] = beam.polarization;
  }
  if (beam.polarizationAngleDeg != 0.0) {
    entry["polarizationAngleDeg"] = beam.polarizationAngleDeg;
  }
  // Spectrum serializes canonically as energyMeV + weight (the normalized form),
  // so a parse->serialize->parse round-trip is stable regardless of whether the
  // author wrote eV/nm. Omitted when empty to keep single-energy hashes.
  if (!beam.spectrum.empty()) {
    auto lines = nlohmann::json::array();
    for (const auto& line : beam.spectrum) {
      lines.push_back({{"energyMeV", line.energyMeV}, {"weight", line.weight}});
    }
    entry["spectrum"] = lines;
  }
}

RunConfig runFromJson(const nlohmann::json& j, const RunConfig& defaults) {
  RunConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.nEvents = fieldOr(j, "nEvents", cfg.nEvents);
  cfg.seed = fieldOr(j, "seed", cfg.seed);
  cfg.threads = fieldOr(j, "threads", cfg.threads);
  cfg.timeBudgetSeconds = fieldOr(j, "timeBudgetSeconds", cfg.timeBudgetSeconds);
  if (!std::isfinite(cfg.timeBudgetSeconds) || cfg.timeBudgetSeconds < 0.0) {
    throw std::runtime_error("run.timeBudgetSeconds must be finite and non-negative");
  }
  return cfg;
}

PhysicsConfig physicsFromJson(const nlohmann::json& j, const PhysicsConfig& defaults) {
  PhysicsConfig cfg = defaults;
  if (j.is_string()) {
    cfg.list = j.get<std::string>();
    return cfg;
  }
  if (!objectAt(j, {}, "a string or an object")) {
    return cfg;
  }
  cfg.list = fieldOr(j, "list", cfg.list);
  cfg.radioactiveDecayThresholdYears =
      std::max(0.0, fieldOr(j, "radioactiveDecayThresholdYears", cfg.radioactiveDecayThresholdYears));
  const double limit =
      fieldOr(j, "gammaNuclearLowEnergyModelLimitMeV", cfg.gammaNuclearLowEnergyModelLimitMeV);
  cfg.gammaNuclearLowEnergyModelLimitMeV = limit >= 0.0 ? limit : -1.0;
  return cfg;
}

std::string normalizeDeterminismMode(std::string mode) {
  std::transform(mode.begin(), mode.end(), mode.begin(),
                 [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
  if (mode == "predictive") {
    return mode;
  }
  return "strict";
}

DeterminismConfig determinismFromJson(const nlohmann::json& j,
                                      const DeterminismConfig& defaults) {
  DeterminismConfig cfg = defaults;
  if (j.is_string()) {
    cfg.mode = normalizeDeterminismMode(j.get<std::string>());
    return cfg;
  }
  if (!objectAt(j, {}, "a string or an object")) {
    return cfg;
  }
  cfg.mode = normalizeDeterminismMode(fieldOr(j, "mode", cfg.mode));
  if (has(j, "predictive")) {
    cfg.mode = fieldValue<bool>(j.at("predictive"), "predictive") ? "predictive" : "strict";
  }
  return cfg;
}

SystemConfig systemFromJson(const nlohmann::json& j, const SystemConfig& defaults) {
  SystemConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.enable = fieldOr(j, "enable", cfg.enable);
  cfg.mode = fieldOr(j, "mode", cfg.mode);
  cfg.frame = fieldOr(j, "frame", cfg.frame);
  cfg.ensemble = fieldOr(j, "ensemble", cfg.ensemble);
  cfg.volumeMm3 = fieldOr(j, "volumeMm3", cfg.volumeMm3);
  return cfg;
}

OpticsConfig opticsFromJson(const nlohmann::json& j, const OpticsConfig& defaults) {
  OpticsConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.enable = fieldOr(j, "enable", cfg.enable);
  cfg.refractiveIndex = fieldOr(j, "refractiveIndex", cfg.refractiveIndex);
  cfg.absorptionLengthMm = fieldOr(j, "absorptionLengthMm", cfg.absorptionLengthMm);
  cfg.scatterLengthMm = fieldOr(j, "scatterLengthMm", cfg.scatterLengthMm);
  if (has(j, "spectrum")) {
    cfg.spectrum.clear();
    const auto appendSpectrumPoint = [&](const nlohmann::json& entry) {
      if (!entry.is_array() && !entry.is_object()) {
        rejectCollection(entry, "");
        return;
      }
      OpticsSpectrumPoint point;
      if (entry.is_array()) {
        if (!entry.empty()) {
          point.energyEv = fieldValue<double>(entry.at(0), "[0]");
        }
        if (entry.size() > 1) {
          point.refractiveIndex = fieldValue<double>(entry.at(1), "[1]");
        }
        if (entry.size() > 2) {
          point.absorptionLengthMm = fieldValue<double>(entry.at(2), "[2]");
        }
        if (entry.size() > 3) {
          point.scatterLengthMm = fieldValue<double>(entry.at(3), "[3]");
        }
      } else {
        point.energyEv = fieldOr(entry, "energyEv", point.energyEv);
        point.wavelengthNm = fieldOr(entry, "wavelengthNm", point.wavelengthNm);
        point.refractiveIndex = fieldOr(entry, "refractiveIndex", point.refractiveIndex);
        point.absorptionLengthMm =
            fieldOr(entry, "absorptionLengthMm", point.absorptionLengthMm);
        point.scatterLengthMm = fieldOr(entry, "scatterLengthMm", point.scatterLengthMm);
      }
      if (point.energyEv > 0.0 || point.wavelengthNm > 0.0) {
        cfg.spectrum.push_back(point);
      }
    };
    const auto& spectrum = j.at("spectrum");
    if (spectrum.is_array()) {
      for (std::size_t i = 0; i < spectrum.size(); ++i) {
        located("spectrum[" + std::to_string(i) + "]",
                [&] { appendSpectrumPoint(spectrum.at(i)); });
      }
    } else {
      located("spectrum", [&] { appendSpectrumPoint(spectrum); });
    }
  }
  return cfg;
}

OpticsValidationReferenceConfig opticsValidationReferenceFromJson(
    const nlohmann::json& j, const OpticsValidationReferenceConfig& defaults) {
  OpticsValidationReferenceConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.material = fieldOr(j, "material", cfg.material);
  cfg.energyEv = fieldOr(j, "energyEv", cfg.energyEv);
  cfg.refractiveIndex = fieldOr(j, "refractiveIndex", cfg.refractiveIndex);
  cfg.absorptionLengthMm = fieldOr(j, "absorptionLengthMm", cfg.absorptionLengthMm);
  cfg.scatterLengthMm = fieldOr(j, "scatterLengthMm", cfg.scatterLengthMm);
  cfg.source = fieldOr(j, "source", cfg.source);
  return cfg;
}

OpticsDeriveConfig opticsDeriveFromJson(const nlohmann::json& j,
                                        const OpticsDeriveConfig& defaults) {
  OpticsDeriveConfig cfg = defaults;
  if (j.is_boolean()) {
    cfg.enable = j.get<bool>();
    return cfg;
  }
  if (j.is_string()) {
    cfg.enable = true;
    cfg.mode = j.get<std::string>();
    return cfg;
  }
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.enable = fieldOr(j, "enable", cfg.enable);
  cfg.mode = fieldOr(j, "mode", cfg.mode);
  cfg.energyMinEv = fieldOr(j, "energyMinEv", cfg.energyMinEv);
  cfg.energyMaxEv = fieldOr(j, "energyMaxEv", cfg.energyMaxEv);
  cfg.nEnergyBins = fieldOr(j, "nEnergyBins", cfg.nEnergyBins);
  cfg.kkIntegrationMinEv = fieldOr(j, "kkIntegrationMinEv", cfg.kkIntegrationMinEv);
  cfg.kkIntegrationMaxEv = fieldOr(j, "kkIntegrationMaxEv", cfg.kkIntegrationMaxEv);
  cfg.kkIntegrationBins = fieldOr(j, "kkIntegrationBins", cfg.kkIntegrationBins);
  cfg.modelValidMinEv = fieldOr(j, "modelValidMinEv", cfg.modelValidMinEv);
  cfg.valenceOscillator = fieldOr(j, "valenceOscillator", cfg.valenceOscillator);
  cfg.valenceResonanceEv = fieldOr(j, "valenceResonanceEv", cfg.valenceResonanceEv);
  cfg.surrogateModelPath = fieldOr(j, "surrogateModelPath", cfg.surrogateModelPath);
  cfg.writeSpectrum = fieldOr(j, "writeSpectrum", cfg.writeSpectrum);
  if (has(j, "validate") && objectAt(j.at("validate"), "validate")) {
    const auto& validate = j.at("validate");
    located("validate", [&] {
      cfg.validateAgainstReferences = fieldOr(validate, "enable", cfg.validateAgainstReferences);
      if (has(validate, "references")) {
        cfg.validationReferences.clear();
        const auto& refs = validate.at("references");
        const auto appendOne = [&](const nlohmann::json& entry, const std::string& where) {
          if (objectAt(entry, where)) {
            cfg.validationReferences.push_back(located(where, [&] {
              return opticsValidationReferenceFromJson(entry, OpticsValidationReferenceConfig{});
            }));
          }
        };
        if (refs.is_array()) {
          for (std::size_t i = 0; i < refs.size(); ++i) {
            appendOne(refs.at(i), "references[" + std::to_string(i) + "]");
          }
        } else {
          appendOne(refs, "references");
        }
      }
    });
  }
  if (cfg.nEnergyBins < 2) {
    cfg.nEnergyBins = 2;
  }
  if (cfg.kkIntegrationBins < 16) {
    cfg.kkIntegrationBins = 16;
  }
  return cfg;
}

VizConfig vizFromJson(const nlohmann::json& j, const VizConfig& defaults) {
  VizConfig cfg = defaults;
  if (j.is_boolean()) {
    cfg.enable = j.get<bool>();
    return cfg;
  }
  if (!objectAt(j, {}, "a boolean or an object")) {
    return cfg;
  }
  cfg.enable = fieldOr(j, "enable", cfg.enable);
  cfg.scenePath = fieldOr(j, "scenePath", cfg.scenePath);
  cfg.trajectoriesPath = fieldOr(j, "trajectoriesPath", cfg.trajectoriesPath);
  cfg.maxTrajectories = fieldOr(j, "maxTrajectories", cfg.maxTrajectories);
  cfg.sampleEveryNth = fieldOr(j, "sampleEveryNth", cfg.sampleEveryNth);
  cfg.maxSegmentsPerTrajectory =
      fieldOr(j, "maxSegmentsPerTrajectory", cfg.maxSegmentsPerTrajectory);
  cfg.includeNonOptical = fieldOr(j, "includeNonOptical", cfg.includeNonOptical);
  cfg.recordVertices = fieldOr(j, "recordVertices", cfg.recordVertices);
  if (cfg.sampleEveryNth < 1) {
    cfg.sampleEveryNth = 1;
  }
  if (cfg.maxTrajectories < 0) {
    cfg.maxTrajectories = 0;
  }
  if (cfg.maxSegmentsPerTrajectory < 1) {
    cfg.maxSegmentsPerTrajectory = 1;
  }
  return cfg;
}

ChemistryConfig chemistryFromJson(const nlohmann::json& j, const ChemistryConfig& defaults) {
  ChemistryConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.enable = fieldOr(j, "enable", cfg.enable);
  cfg.model = fieldOr(j, "model", cfg.model);
  cfg.solver = fieldOr(j, "solver", cfg.solver);
  return cfg;
}

NuclearReactionParticipantConfig nuclearReactionParticipantFromJson(
    const nlohmann::json& j, const NuclearReactionParticipantConfig& defaults) {
  NuclearReactionParticipantConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.particle = fieldOr(j, "particle", cfg.particle);
  cfg.z = fieldOr(j, "z", cfg.z);
  cfg.a = fieldOr(j, "a", cfg.a);
  return cfg;
}

void appendNuclearReactionParticipantsFromJson(
    const nlohmann::json& j, std::vector<NuclearReactionParticipantConfig>& out) {
  if (j.is_array()) {
    for (std::size_t i = 0; i < j.size(); ++i) {
      const auto& entry = j.at(i);
      if (objectAt(entry, "[" + std::to_string(i) + "]")) {
        out.push_back(located("[" + std::to_string(i) + "]", [&] {
          return nuclearReactionParticipantFromJson(entry, NuclearReactionParticipantConfig{});
        }));
      }
    }
    return;
  }
  if (j.is_object()) {
    out.push_back(nuclearReactionParticipantFromJson(j, NuclearReactionParticipantConfig{}));
  } else {
    rejectCollection(j, "");
  }
}

NuclearSpeciesConfig nuclearSpeciesFromJson(const nlohmann::json& j,
                                            const NuclearSpeciesConfig& defaults) {
  NuclearSpeciesConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.symbol = fieldOr(j, "symbol", cfg.symbol);
  cfg.material = fieldOr(j, "material", cfg.material);
  cfg.z = fieldOr(j, "z", cfg.z);
  cfg.a = fieldOr(j, "a", cfg.a);
  cfg.phase = fieldOr(j, "phase", cfg.phase);
  cfg.densityGcm3 = fieldOr(j, "densityGcm3", cfg.densityGcm3);
  return cfg;
}

NuclearReactionConfig nuclearReactionFromJson(const nlohmann::json& j,
                                              const NuclearReactionConfig& defaults) {
  NuclearReactionConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.name = fieldOr(j, "name", cfg.name);
  cfg.halfLifeYears = fieldOr(j, "halfLifeYears", cfg.halfLifeYears);
  if (has(j, "reactants")) {
    cfg.reactants.clear();
    located("reactants",
            [&] { appendNuclearReactionParticipantsFromJson(j.at("reactants"), cfg.reactants); });
  }
  if (has(j, "products")) {
    cfg.products.clear();
    located("products",
            [&] { appendNuclearReactionParticipantsFromJson(j.at("products"), cfg.products); });
  }
  return cfg;
}

NuclearCycleConfig nuclearCycleFromJson(const nlohmann::json& j,
                                        const NuclearCycleConfig& defaults) {
  NuclearCycleConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.name = fieldOr(j, "name", cfg.name);
  cfg.enable = fieldOr(j, "enable", cfg.enable);
  if (has(j, "source")) {
    cfg.source = located("source", [&] { return nuclearSpeciesFromJson(j.at("source"), cfg.source); });
  }
  if (has(j, "target")) {
    cfg.target = located("target", [&] { return nuclearSpeciesFromJson(j.at("target"), cfg.target); });
  }
  if (has(j, "forward")) {
    cfg.forward = located("forward", [&] { return nuclearReactionFromJson(j.at("forward"), cfg.forward); });
  }
  if (has(j, "backward")) {
    cfg.backward = located("backward", [&] { return nuclearReactionFromJson(j.at("backward"), cfg.backward); });
  }
  return cfg;
}

NuclearConfig nuclearFromJson(const nlohmann::json& j, const NuclearConfig& defaults) {
  NuclearConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.enable = fieldOr(j, "enable", cfg.enable);
  if (has(j, "cycles")) {
    cfg.cycles.clear();
    const auto& cycles = j.at("cycles");
    if (cycles.is_array()) {
      for (std::size_t i = 0; i < cycles.size(); ++i) {
        const auto& entry = cycles.at(i);
        if (objectAt(entry, entryLocation("cycles", i, entry))) {
          cfg.cycles.push_back(located(entryLocation("cycles", i, entry), [&] {
            return nuclearCycleFromJson(entry, NuclearCycleConfig{});
          }));
        }
      }
    } else if (cycles.is_object()) {
      cfg.cycles.push_back(
          located("cycles", [&] { return nuclearCycleFromJson(cycles, NuclearCycleConfig{}); }));
    } else {
      rejectCollection(cycles, "cycles");
    }
  }
  return cfg;
}

MultiscaleConfig multiscaleFromJson(const nlohmann::json& j, const MultiscaleConfig& defaults) {
  MultiscaleConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.enable = fieldOr(j, "enable", cfg.enable);
  cfg.method = fieldOr(j, "method", cfg.method);
  cfg.mode = fieldOr(j, "mode", cfg.mode);
  return cfg;
}

AnalyticCheckConfig analyticCheckFromJson(const nlohmann::json& j,
                                          const AnalyticCheckConfig& defaults) {
  AnalyticCheckConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.type = fieldOr(j, "type", cfg.type);
  cfg.label = fieldOr(j, "label", cfg.label);
  cfg.particle = fieldOr(j, "particle", cfg.particle);
  cfg.energyMeV = fieldOr(j, "energyMeV", cfg.energyMeV);
  cfg.material = fieldOr(j, "material", cfg.material);
  cfg.pathLengthMm = fieldOr(j, "pathLengthMm", cfg.pathLengthMm);
  cfg.toleranceRel = fieldOr(j, "toleranceRel", cfg.toleranceRel);
  return cfg;
}

AnalyticConfig analyticFromJson(const nlohmann::json& j, const AnalyticConfig& defaults) {
  AnalyticConfig cfg = defaults;
  if (j.is_boolean()) {
    cfg.enable = j.get<bool>();
    return cfg;
  }
  if (!objectAt(j, {}, "a boolean or an object")) {
    return cfg;
  }
  cfg.enable = fieldOr(j, "enable", cfg.enable);
  if (has(j, "checks")) {
    cfg.checks.clear();
    const auto& checks = j.at("checks");
    const auto appendOne = [&](const nlohmann::json& entry, const std::string& where) {
      if (objectAt(entry, where)) {
        cfg.checks.push_back(
            located(where, [&] { return analyticCheckFromJson(entry, AnalyticCheckConfig{}); }));
      }
    };
    if (checks.is_array()) {
      for (std::size_t i = 0; i < checks.size(); ++i) {
        appendOne(checks.at(i), "checks[" + std::to_string(i) + "]");
      }
    } else {
      appendOne(checks, "checks");
    }
  }
  return cfg;
}

// The recognized precision-profile vocabulary. Anything else is recorded as
// `custom` rather than rejected: a scenario may legitimately resolve a mixture
// of axes (an explicit override on one knob), and calling that "custom" is more
// honest than silently presenting it as a named rung of the ladder.
std::string normalizePrecisionProfile(const std::string& raw) {
  std::string lowered;
  lowered.reserve(raw.size());
  for (const char c : raw) {
    lowered.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
  }
  if (lowered.empty()) {
    return {};
  }
  if (lowered == "preview" || lowered == "balanced" || lowered == "high" ||
      lowered == "convergence" || lowered == "custom") {
    return lowered;
  }
  return "custom";
}

PrecisionAxisConfig precisionAxisFromJson(const nlohmann::json& j) {
  PrecisionAxisConfig axis;
  if (!objectAt(j)) {
    return axis;
  }
  axis.name = fieldOr(j, "name", axis.name);
  axis.role = fieldOr(j, "role", axis.role);
  axis.control = fieldOr(j, "control", axis.control);
  axis.unit = fieldOr(j, "unit", axis.unit);
  axis.value = fieldOr(j, "value", axis.value);
  axis.baselineValue = fieldOr(j, "baselineValue", axis.value);
  axis.representationOnly = fieldOr(j, "representationOnly", axis.representationOnly);
  axis.overridden = fieldOr(j, "overridden", axis.overridden);
  // A representation axis is display-only by definition; keep that invariant in
  // the engine so a scenario cannot smuggle a render knob in as physics.
  if (axis.role == "representation") {
    axis.representationOnly = true;
  }
  return axis;
}

PrecisionConfig precisionFromJson(const nlohmann::json& j,
                                  const PrecisionConfig& defaults) {
  PrecisionConfig cfg = defaults;
  if (j.is_string()) {
    cfg.profile = normalizePrecisionProfile(j.get<std::string>());
    return cfg;
  }
  if (!objectAt(j, {}, "a string or an object")) {
    return cfg;
  }
  if (has(j, "profile")) {
    cfg.profile = normalizePrecisionProfile(fieldValue<std::string>(j.at("profile"), "profile"));
  }
  cfg.note = fieldOr(j, "note", cfg.note);
  if (has(j, "axes")) {
    cfg.axes.clear();
    const auto& axes = j.at("axes");
    if (axes.is_array()) {
      for (std::size_t i = 0; i < axes.size(); ++i) {
        const auto& entry = axes.at(i);
        if (objectAt(entry, entryLocation("axes", i, entry))) {
          cfg.axes.push_back(
              located(entryLocation("axes", i, entry), [&] { return precisionAxisFromJson(entry); }));
        }
      }
    } else if (axes.is_object()) {
      cfg.axes.push_back(located("axes", [&] { return precisionAxisFromJson(axes); }));
    } else {
      rejectCollection(axes, "axes");
    }
  }
  return cfg;
}

MaterialProbeConfig materialProbeFromJson(const nlohmann::json& j,
                                          const MaterialProbeConfig& defaults) {
  MaterialProbeConfig cfg = defaults;
  if (j.is_boolean()) {
    cfg.enable = j.get<bool>();
    return cfg;
  }
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.enable = fieldOr(j, "enable", cfg.enable);
  cfg.includeIsotopes = fieldOr(j, "includeIsotopes", cfg.includeIsotopes);
  if (has(j, "nuclearSamples")) {
    const auto& samples = j.at("nuclearSamples");
    if (!samples.is_object() || !has(samples, "configurations") ||
        !samples.at("configurations").is_number_integer() ||
        samples.at("configurations").get<double>() < 1 || samples.at("configurations").get<double>() > 32)
      throw std::invalid_argument("materialProbe.nuclearSamples.configurations must be an integer in [1,32]");
    cfg.nuclearConfigurations = samples.at("configurations").get<int>();
    if (has(samples, "seed") && (!samples.at("seed").is_number_unsigned() &&
        (!samples.at("seed").is_number_integer() || samples.at("seed").get<double>() < 0)))
      throw std::invalid_argument("materialProbe.nuclearSamples.seed must be an unsigned integer");
    cfg.nuclearSeed = fieldOr(samples, "seed", std::uint64_t{1});
    cfg.includeIsotopes = true;
  }
  if (has(j, "materials")) {
    cfg.materials.clear();
    appendStringListFromJson(j.at("materials"), cfg.materials, "materials");
  }
  if (has(j, "interactions")) {
    const auto& sample = j.at("interactions");
    if (!sample.is_object() || !has(sample, "particle") || !has(sample, "processes") ||
        !has(sample, "energiesMeV")) {
      throw std::invalid_argument("materialProbe.interactions requires particle, processes and energiesMeV");
    }
    located("interactions", [&] {
      cfg.interactionParticle = fieldValue<std::string>(sample.at("particle"), "particle");
      cfg.interactionProcesses.clear();
      appendStringListFromJson(sample.at("processes"), cfg.interactionProcesses, "processes");
      const auto& energies = sample.at("energiesMeV");
      if (!energies.is_array()) {
        throw FieldError("energiesMeV must be an array of numbers");
      }
      cfg.interactionEnergiesMeV.clear();
      for (std::size_t i = 0; i < energies.size(); ++i) {
        cfg.interactionEnergiesMeV.push_back(
            fieldValue<double>(energies.at(i), "energiesMeV[" + std::to_string(i) + "]"));
      }
    });
    if (cfg.interactionParticle.empty() || cfg.interactionProcesses.empty() ||
        cfg.interactionEnergiesMeV.empty()) {
      throw std::invalid_argument("materialProbe.interactions requires particle, processes and energiesMeV");
    }
    for (const auto& process : cfg.interactionProcesses) {
      if (process.empty()) throw std::invalid_argument("empty interaction process");
    }
    for (double energy : cfg.interactionEnergiesMeV) {
      if (!std::isfinite(energy) || energy <= 0)
        throw std::invalid_argument("interaction energies must be positive finite MeV");
    }
  }
  return cfg;
}


PlacementConfig placementFromJson(const nlohmann::json& j, const PlacementConfig& defaults) {
  PlacementConfig cfg = defaults;
  if (!objectAt(j, "placement")) {
    return cfg;
  }
  cfg.parent = geometryStringOr(j, "parent", cfg.parent, "placement.");
  if (has(j, "positionMm")) {
    const auto p = geometryTriple(j.at("positionMm"),
                                  {cfg.positionMm.x, cfg.positionMm.y, cfg.positionMm.z},
                                  "placement.positionMm");
    cfg.positionMm.x = p[0];
    cfg.positionMm.y = p[1];
    cfg.positionMm.z = p[2];
  }
  if (has(j, "rotationDeg")) {
    const auto r = geometryTriple(j.at("rotationDeg"),
                                  {cfg.rotationDeg.x, cfg.rotationDeg.y, cfg.rotationDeg.z},
                                  "placement.rotationDeg");
    cfg.rotationDeg.x = r[0];
    cfg.rotationDeg.y = r[1];
    cfg.rotationDeg.z = r[2];
  }
  return cfg;
}

ShapeConfig shapeFromJson(const nlohmann::json& j, const ShapeConfig& defaults) {
  ShapeConfig cfg = defaults;
  if (!objectAt(j, "shape")) {
    return cfg;
  }
  cfg.type = geometryStringOr(j, "type", cfg.type, "shape.");
  if (has(j, "sizeMm")) {
    const auto size = geometryTriple(j.at("sizeMm"), {cfg.sizeXmm, cfg.sizeYmm, cfg.sizeZmm},
                                     "shape.sizeMm");
    cfg.sizeXmm = size[0];
    cfg.sizeYmm = size[1];
    cfg.sizeZmm = size[2];
  }
  if ((cfg.sizeXmm <= 0.0 || cfg.sizeYmm <= 0.0 || cfg.sizeZmm <= 0.0) &&
      has(j, "halfSizeMm")) {
    const auto half = geometryTriple(
        j.at("halfSizeMm"), {0.5 * cfg.sizeXmm, 0.5 * cfg.sizeYmm, 0.5 * cfg.sizeZmm},
        "shape.halfSizeMm");
    // Unrecognised forms return the halved defaults, so doubling is a no-op.
    cfg.sizeXmm = 2.0 * half[0];
    cfg.sizeYmm = 2.0 * half[1];
    cfg.sizeZmm = 2.0 * half[2];
  }
  cfg.innerRadiusMm = geometryNumberOr(j, "innerRadiusMm", cfg.innerRadiusMm, "shape.");
  cfg.outerRadiusMm = geometryNumberOr(j, "outerRadiusMm", cfg.outerRadiusMm, "shape.");
  if (cfg.outerRadiusMm <= 0.0) {
    cfg.outerRadiusMm = geometryNumberOr(j, "radiusMm", cfg.outerRadiusMm, "shape.");
  }
  if (cfg.outerRadiusMm <= 0.0) {
    const auto diameter = geometryNumberOr(j, "diameterMm", 0.0, "shape.");
    if (diameter > 0.0) {
      cfg.outerRadiusMm = 0.5 * diameter;
    }
  }
  cfg.lengthMm = geometryNumberOr(j, "lengthMm", cfg.lengthMm, "shape.");
  if (cfg.lengthMm <= 0.0) {
    const auto halfLength = geometryNumberOr(j, "halfLengthMm", 0.0, "shape.");
    if (halfLength > 0.0) {
      cfg.lengthMm = 2.0 * halfLength;
    }
  }
  return cfg;
}

VolumeConfig volumeFromJson(const nlohmann::json& j, const VolumeConfig& defaults) {
  VolumeConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.name = fieldOr(j, "name", cfg.name);
  cfg.material = fieldOr(j, "material", cfg.material);
  cfg.scoreEdep = fieldOr(j, "scoreEdep", cfg.scoreEdep);
  if (has(j, "shape")) {
    cfg.shape = shapeFromJson(j.at("shape"), cfg.shape);
  }
  if (has(j, "placement")) {
    cfg.placement = placementFromJson(j.at("placement"), cfg.placement);
  }
  if (has(j, "tags")) {
    cfg.tags.clear();
    appendStringListFromJson(j.at("tags"), cfg.tags, "tags");
  }
  return cfg;
}

GeometryConfig geometryFromJson(const nlohmann::json& j, const GeometryConfig& defaults) {
  GeometryConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  if (has(j, "volumes")) {
    const auto& volumes = j.at("volumes");
    cfg.volumes.clear();
    if (volumes.is_array()) {
      for (std::size_t i = 0; i < volumes.size(); ++i) {
        const auto& entry = volumes.at(i);
        if (!objectAt(entry, entryLocation("volumes", i, entry))) {
          continue;
        }
        // Name the volume; the top level adds the "geometry." prefix.
        cfg.volumes.push_back(located(entryLocation("volumes", i, entry),
                                      [&] { return volumeFromJson(entry, VolumeConfig{}); }));
      }
    } else if (volumes.is_object()) {
      cfg.volumes.push_back(
          located("volumes", [&] { return volumeFromJson(volumes, VolumeConfig{}); }));
    } else {
      rejectCollection(volumes, "volumes");
    }
  }
  if (has(j, "overlapCheck")) {
    const auto& check = j.at("overlapCheck");
    if (check.is_boolean()) {
      cfg.overlapCheck.enable = check.get<bool>();
    } else if (check.is_object()) {
      cfg.overlapCheck.enable =
          located("overlapCheck", [&] { return fieldOr(check, "enable", cfg.overlapCheck.enable); });
      if (has(check, "samplesPerVolume")) {
        const auto& samples = check.at("samplesPerVolume");
        if (!samples.is_number_integer() || samples.get<long long>() < 1 ||
            samples.get<long long>() > 1000000) {
          throw std::invalid_argument(
              "geometry.overlapCheck.samplesPerVolume must be an integer in [1, 1000000]");
        }
        cfg.overlapCheck.samplesPerVolume = samples.get<int>();
      }
      if (has(check, "toleranceMm")) {
        const auto& tol = check.at("toleranceMm");
        if (!tol.is_number() || tol.get<double>() < 0.0) {
          throw std::invalid_argument("geometry.overlapCheck.toleranceMm must be a number >= 0");
        }
        cfg.overlapCheck.toleranceMm = tol.get<double>();
      }
    } else {
      throw std::invalid_argument("geometry.overlapCheck must be a boolean or an object");
    }
  }
  if (has(j, "refuseOn")) {
    // Same list and order as sim::geometryIssueKinds().
    static const std::vector<std::string> kKinds = {"material_fallback", "parent_fallback",
                                                    "volume_skipped", "overlap"};
    const auto& refuse = j.at("refuseOn");
    std::vector<std::string> requested;
    if (refuse.is_string()) {
      requested.push_back(refuse.get<std::string>());
    } else if (refuse.is_array()) {
      for (const auto& entry : refuse) {
        if (!entry.is_string()) {
          throw std::invalid_argument("geometry.refuseOn entries must be strings");
        }
        requested.push_back(entry.get<std::string>());
      }
    } else {
      throw std::invalid_argument("geometry.refuseOn must be a string or an array of strings");
    }
    std::vector<bool> wanted(kKinds.size(), false);
    for (const auto& name : requested) {
      if (name == "any") {
        wanted.assign(kKinds.size(), true);
        continue;
      }
      const auto it = std::find(kKinds.begin(), kKinds.end(), name);
      if (it == kKinds.end()) {
        throw std::invalid_argument("geometry.refuseOn: unknown issue kind '" + name +
                                    "' (expected any, material_fallback, parent_fallback, "
                                    "volume_skipped or overlap)");
      }
      wanted[static_cast<std::size_t>(it - kKinds.begin())] = true;
    }
    cfg.refuseOn.clear();
    for (std::size_t i = 0; i < kKinds.size(); ++i) {
      if (wanted[i]) {
        cfg.refuseOn.push_back(kKinds[i]);
      }
    }
  }
  if (!cfg.overlapCheck.enable &&
      std::find(cfg.refuseOn.begin(), cfg.refuseOn.end(), "overlap") != cfg.refuseOn.end()) {
    throw std::invalid_argument(
        "geometry.refuseOn names 'overlap' but geometry.overlapCheck is disabled; "
        "an overlap could never be found");
  }
  return cfg;
}

void appendMaterialComponentsFromJson(const nlohmann::json& j,
                                      std::vector<MaterialComponentConfig>& out) {
  const auto appendOne = [&](const nlohmann::json& entry) {
    if (!objectAt(entry)) {
      return;
    }
    MaterialComponentConfig comp;
    comp.material = fieldOr(entry, "material", comp.material);
    comp.element = fieldOr(entry, "element", comp.element);
    comp.fraction = fieldOr(entry, "fraction", comp.fraction);
    for (const auto* field : {"atoms", "massNumber"}) {
      if (has(entry, field) && (!entry.at(field).is_number_integer() ||
          entry.at(field).get<double>() <= 0 || entry.at(field).get<double>() > 1000000))
        throw std::invalid_argument(std::string("material component ") + field + " must be a positive integer <= 1000000");
    }
    comp.atoms = fieldOr(entry, "atoms", 0);
    comp.massNumber = fieldOr(entry, "massNumber", 0);
    if ((comp.atoms || comp.massNumber) && (comp.element.empty() || !comp.material.empty()))
      throw std::invalid_argument("isotope/stoichiometric components require an element only");
    if (comp.atoms && has(entry, "fraction"))
      throw std::invalid_argument("material component atoms and fraction are mutually exclusive");
    if (!comp.material.empty() || !comp.element.empty()) {
      out.push_back(comp);
    }
  };
  if (j.is_array()) {
    for (std::size_t i = 0; i < j.size(); ++i) {
      located("[" + std::to_string(i) + "]", [&] { appendOne(j.at(i)); });
    }
  } else if (j.is_object()) {
    appendOne(j);
  } else {
    rejectCollection(j, "");
  }
}

MaterialConfig materialFromJson(const nlohmann::json& j, const MaterialConfig& defaults) {
  MaterialConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.name = fieldOr(j, "name", cfg.name);
  cfg.smiles = fieldOr(j, "smiles", cfg.smiles);
  cfg.densityGcm3 = fieldOr(j, "densityGcm3", cfg.densityGcm3);
  if (has(j, "components")) {
    cfg.components.clear();
    located("components",
            [&] { appendMaterialComponentsFromJson(j.at("components"), cfg.components); });
    const bool stoichiometric = std::any_of(cfg.components.begin(), cfg.components.end(),
        [](const auto& c) { return c.atoms > 0; });
    if (stoichiometric && std::any_of(cfg.components.begin(), cfg.components.end(),
        [](const auto& c) { return c.atoms == 0; }))
      throw std::invalid_argument("all components must use atoms in a stoichiometric material");
  }
  return cfg;
}

ModelConfig modelFromJson(const nlohmann::json& j, const ModelConfig& defaults) {
  ModelConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.name = fieldOr(j, "name", cfg.name);
  cfg.path = fieldOr(j, "path", cfg.path);
  cfg.scale = fieldOr(j, "scale", cfg.scale);
  cfg.operatorRole = fieldOr(j, "operator_role", cfg.operatorRole);
  cfg.elementKind = fieldOr(j, "element_kind", cfg.elementKind);
  if (has(j, "required_context_keys")) {
    cfg.requiredContextKeys.clear();
    appendStringListFromJson(j.at("required_context_keys"), cfg.requiredContextKeys,
                             "required_context_keys");
  }
  // TRECH_ML.modelEntry() annotates a registry-resolved entry with the
  // checkpoint it chose (`registry`: id, version, structure, sha256, ...). It
  // is a known, accepted annotation, not an ignored key: the engine does not
  // act on it (provenance model_artifacts records the loaded file's own
  // sha256) and it is not serialized, so config hashes are unchanged.
  if (has(j, "registry") && !j.at("registry").is_object()) {
    throwFieldError("registry must be an object");
  }
  return cfg;
}

HooksConfig hooksFromJson(const nlohmann::json& j, const HooksConfig& defaults) {
  HooksConfig cfg = defaults;
  if (j.is_string()) {
    cfg.registered.clear();
    cfg.registered.push_back(j.get<std::string>());
    return cfg;
  }
  if (j.is_array()) {
    cfg.registered.clear();
    appendStringListFromJson(j, cfg.registered, "");
    return cfg;
  }
  if (!objectAt(j, {}, "a string, an array of strings or an object")) {
    return cfg;
  }
  if (has(j, "inputs")) {
    if (!j.at("inputs").is_object()) throw std::invalid_argument("hooks.inputs must be an object");
    cfg.inputsJson = j.at("inputs").dump();
  }
  cfg.registered.clear();
  if (has(j, "registered") && (j.at("registered").is_array() || j.at("registered").is_string())) {
    appendStringListFromJson(j.at("registered"), cfg.registered, "registered");
  } else if (has(j, "names") && (j.at("names").is_array() || j.at("names").is_string())) {
    appendStringListFromJson(j.at("names"), cfg.registered, "names");
  } else {
    for (auto it = j.begin(); it != j.end(); ++it) {
      if (it.value().is_boolean()) {
        has(j, it.key());  // a boolean key is a hook toggle, so it is read
        if (it.value().get<bool>()) {
          cfg.registered.push_back(it.key());
        }
      }
    }
  }
  cfg.maxStepCallbacks = integerFieldOr(j, "maxStepCallbacks", cfg.maxStepCallbacks);
  cfg.maxStepCallbacks = integerFieldOr(j, "maxStepRecords", cfg.maxStepCallbacks);
  cfg.maxTrackCallbacks = integerFieldOr(j, "maxTrackCallbacks", cfg.maxTrackCallbacks);
  cfg.maxEmitsPerCallback = integerFieldOr(j, "maxEmitsPerCallback", cfg.maxEmitsPerCallback);
  cfg.maxEmitsPerCallback = integerFieldOr(j, "maxEmitsPerCall", cfg.maxEmitsPerCallback);
  cfg.maxEmitsPerCallback = integerFieldOr(j, "maxEmits", cfg.maxEmitsPerCallback);
  cfg.maxEmitPayloadBytes = integerFieldOr(j, "maxEmitPayloadBytes", cfg.maxEmitPayloadBytes);
  cfg.maxEmitPayloadBytes = integerFieldOr(j, "maxPayloadBytes", cfg.maxEmitPayloadBytes);
  if (cfg.maxStepCallbacks < 0) {
    cfg.maxStepCallbacks = 0;
  }
  if (cfg.maxTrackCallbacks < 0) {
    cfg.maxTrackCallbacks = 0;
  }
  if (cfg.maxEmitsPerCallback < 0) {
    cfg.maxEmitsPerCallback = 0;
  }
  if (cfg.maxEmitPayloadBytes < 0) {
    cfg.maxEmitPayloadBytes = 0;
  }
  return cfg;
}

StratifyConfig stratifyFromJson(const nlohmann::json& j, const StratifyConfig& defaults) {
  StratifyConfig cfg = defaults;
  if (!objectAt(j)) {
    return cfg;
  }
  cfg.enable = fieldOr(j, "enable", cfg.enable);
  cfg.edepMeVThreshold = fieldOr(j, "edepMeVThreshold", cfg.edepMeVThreshold);
  cfg.opticalTrackLengthMmThreshold =
      fieldOr(j, "opticalTrackLengthMmThreshold", cfg.opticalTrackLengthMmThreshold);
  cfg.totalTrackLengthMmThreshold =
      fieldOr(j, "totalTrackLengthMmThreshold", cfg.totalTrackLengthMmThreshold);
  cfg.totalTrackCountThreshold =
      fieldOr(j, "totalTrackCountThreshold", cfg.totalTrackCountThreshold);
  cfg.totalStepCountThreshold =
      fieldOr(j, "totalStepCountThreshold", cfg.totalStepCountThreshold);
  cfg.opticalPhotonTrackThreshold =
      fieldOr(j, "opticalPhotonTrackThreshold", cfg.opticalPhotonTrackThreshold);
  cfg.opticalPhotonStepThreshold =
      fieldOr(j, "opticalPhotonStepThreshold", cfg.opticalPhotonStepThreshold);
  cfg.labelPredictable = fieldOr(j, "labelPredictable", cfg.labelPredictable);
  cfg.labelExceptional = fieldOr(j, "labelExceptional", cfg.labelExceptional);
  cfg.labelUnclassified = fieldOr(j, "labelUnclassified", cfg.labelUnclassified);
  cfg.modelPath = fieldOr(j, "modelPath", cfg.modelPath);
  cfg.dumpFeatures = fieldOr(j, "dumpFeatures", cfg.dumpFeatures);
  cfg.dumpResimQueue = fieldOr(j, "dumpResimQueue", cfg.dumpResimQueue);
  cfg.resimOnLowConfidence =
      fieldOr(j, "resimOnLowConfidence", cfg.resimOnLowConfidence);
  cfg.resimOnStarvation =
      fieldOr(j, "resimOnStarvation", cfg.resimOnStarvation);
  cfg.resimOnScaleMismatch =
      fieldOr(j, "resimOnScaleMismatch", cfg.resimOnScaleMismatch);
  return cfg;
}

LabConfig labFromJson(const nlohmann::json& j, const LabConfig& defaults) {
  LabConfig cfg = defaults;
  if (j.is_boolean()) {
    cfg.enable = j.get<bool>();
    return cfg;
  }
  if (j.is_string()) {
    cfg.mode = j.get<std::string>();
    cfg.enable = cfg.mode != "scenario";
    return cfg;
  }
  if (!objectAt(j, {}, "a boolean, a string or an object")) {
    return cfg;
  }
  cfg.enable = fieldOr(j, "enable", cfg.enable);
  cfg.mode = fieldOr(j, "mode", cfg.mode);
  cfg.commandSchema = fieldOr(j, "commandSchema", cfg.commandSchema);
  cfg.commandChannel = fieldOr(j, "commandChannel", cfg.commandChannel);
  cfg.targetHz = integerFieldOr(j, "targetHz", cfg.targetHz);
  cfg.targetHz = integerFieldOr(j, "tickHz", cfg.targetHz);
  if (cfg.targetHz <= 0) {
    cfg.targetHz = defaults.targetHz;
  }
  cfg.roundsPerTick = integerFieldOr(j, "roundsPerTick", cfg.roundsPerTick);
  // eventsPerTick is a clearer alias for authors who do not use the word
  // "round"; canonical output stays roundsPerTick.
  cfg.roundsPerTick = integerFieldOr(j, "eventsPerTick", cfg.roundsPerTick);
  cfg.minRoundsPerTick = fieldOr(j, "minRoundsPerTick", cfg.minRoundsPerTick);
  cfg.maxRoundsPerTick = fieldOr(j, "maxRoundsPerTick", cfg.maxRoundsPerTick);
  cfg.roundLearningRate = fieldOr(j, "roundLearningRate", cfg.roundLearningRate);
  cfg.roundsPerTick = std::max(0, cfg.roundsPerTick);
  cfg.minRoundsPerTick = std::max(1, cfg.minRoundsPerTick);
  cfg.maxRoundsPerTick = std::max(cfg.minRoundsPerTick, cfg.maxRoundsPerTick);
  cfg.roundLearningRate = std::clamp(cfg.roundLearningRate, 0.01, 1.0);
  return cfg;
}

} // namespace

TrechConfig configFromJsonString(const std::string& json) {
  TrechConfig cfg;
  if (json.empty()) {
    return cfg;
  }

  const auto root = nlohmann::json::parse(json);
  KeyLedger ledger;
  struct LedgerScope {
    KeyLedger* previous;
    explicit LedgerScope(KeyLedger* next) : previous(tKeyLedger) { tKeyLedger = next; }
    ~LedgerScope() { tKeyLedger = previous; }
  } ledgerScope(&ledger);
  const auto applyDetectorAlias = [&](const char* key) {
    if (has(root, key)) {
      cfg.detector = located(key, [&] { return detectorFromJson(root.at(key), cfg.detector); });
    }
  };
  applyDetectorAlias("environment");
  applyDetectorAlias("medium");
  applyDetectorAlias("detector");
  const bool hasBeam = has(root, "beam");
  if (hasBeam) {
    cfg.beam = locatedBeamFromJson(root.at("beam"), cfg.beam, "beam");
  }
  if (has(root, "beams")) {
    cfg.beams.clear();
    appendBeamsFromJson(root.at("beams"), cfg.beams);
  }
  if (!cfg.beams.empty() && !hasBeam) {
    cfg.beam = selectPrimaryBeam(cfg.beams, cfg.beam);
  } else if (cfg.beams.empty() && hasBeam) {
    cfg.beams.push_back(cfg.beam);
  }
  if (has(root, "physics")) {
    cfg.physics = located("physics", [&] { return physicsFromJson(root.at("physics"), cfg.physics); });
  }
  if (has(root, "run")) {
    cfg.run = located("run", [&] { return runFromJson(root.at("run"), cfg.run); });
  }
  if (has(root, "determinism")) {
    cfg.determinism = located("determinism", [&] { return determinismFromJson(root.at("determinism"), cfg.determinism); });
  }
  if (has(root, "system")) {
    cfg.system = located("system", [&] { return systemFromJson(root.at("system"), cfg.system); });
  }
  if (has(root, "optics")) {
    cfg.optics = located("optics", [&] { return opticsFromJson(root.at("optics"), cfg.optics); });
    if (root.at("optics").is_object() && has(root.at("optics"), "derive")) {
      cfg.opticsDerive = located("optics.derive", [&] {
        return opticsDeriveFromJson(root.at("optics").at("derive"), cfg.opticsDerive);
      });
    }
  }
  if (has(root, "opticsDerive")) {
    cfg.opticsDerive = located("opticsDerive", [&] { return opticsDeriveFromJson(root.at("opticsDerive"), cfg.opticsDerive); });
  }
  if (has(root, "viz")) {
    cfg.viz = located("viz", [&] { return vizFromJson(root.at("viz"), cfg.viz); });
  }
  if (has(root, "chemistry")) {
    cfg.chemistry = located("chemistry", [&] { return chemistryFromJson(root.at("chemistry"), cfg.chemistry); });
  }
  if (has(root, "nuclear")) {
    cfg.nuclear = located("nuclear", [&] { return nuclearFromJson(root.at("nuclear"), cfg.nuclear); });
  }
  if (has(root, "multiscale")) {
    cfg.multiscale = located("multiscale", [&] { return multiscaleFromJson(root.at("multiscale"), cfg.multiscale); });
  }
  if (has(root, "analytic")) {
    cfg.analytic = located("analytic", [&] { return analyticFromJson(root.at("analytic"), cfg.analytic); });
  }
  if (has(root, "materialProbe")) {
    cfg.materialProbe = located("materialProbe", [&] { return materialProbeFromJson(root.at("materialProbe"), cfg.materialProbe); });
  }
  if (has(root, "precision")) {
    cfg.precision = located("precision", [&] { return precisionFromJson(root.at("precision"), cfg.precision); });
  }
  if (has(root, "geometry")) {
    cfg.geometry = located("geometry", [&] { return geometryFromJson(root.at("geometry"), cfg.geometry); });
  }
  if (has(root, "materials")) {
    const auto& materials = root.at("materials");
    cfg.materials.clear();
    if (materials.is_array()) {
      for (std::size_t i = 0; i < materials.size(); ++i) {
        const auto& entry = materials.at(i);
        if (objectAt(entry, entryLocation("materials", i, entry))) {
          cfg.materials.push_back(located(entryLocation("materials", i, entry),
                                          [&] { return materialFromJson(entry, MaterialConfig{}); }));
        }
      }
    } else if (materials.is_object()) {
      cfg.materials.push_back(
          located("materials", [&] { return materialFromJson(materials, MaterialConfig{}); }));
    } else {
      rejectCollection(materials, "materials");
    }
  }
  if (has(root, "models")) {
    const auto& models = root.at("models");
    cfg.models.clear();
    if (models.is_array()) {
      for (std::size_t i = 0; i < models.size(); ++i) {
        const auto& entry = models.at(i);
        if (objectAt(entry, entryLocation("models", i, entry))) {
          cfg.models.push_back(located(entryLocation("models", i, entry),
                                       [&] { return modelFromJson(entry, ModelConfig{}); }));
        }
      }
    } else if (models.is_object()) {
      cfg.models.push_back(
          located("models", [&] { return modelFromJson(models, ModelConfig{}); }));
    } else {
      rejectCollection(models, "models");
    }
  }
  if (has(root, "hooks")) {
    cfg.hooks = located("hooks", [&] { return hooksFromJson(root.at("hooks"), cfg.hooks); });
  }
  if (has(root, "stratify")) {
    cfg.stratify = located("stratify", [&] { return stratifyFromJson(root.at("stratify"), cfg.stratify); });
  }
  if (has(root, "lab")) {
    cfg.lab = located("lab", [&] { return labFromJson(root.at("lab"), cfg.lab); });
  }
  collectUnknownKeys(root, "", ledger, cfg.unknownKeys);
  return cfg;
}

void requireNoUnknownConfigKeys(const TrechConfig& cfg) {
  if (cfg.unknownKeys.empty()) {
    return;
  }
  std::string message = "--strict-config: config has " + std::to_string(cfg.unknownKeys.size()) +
                        " key(s) the engine never reads:";
  for (std::size_t i = 0; i < cfg.unknownKeys.size(); ++i) {
    message += (i == 0 ? " " : ", ") + cfg.unknownKeys[i];
  }
  throw std::invalid_argument(message);
}

std::string configToJsonString(const TrechConfig& cfg) {
  nlohmann::json root;
  root["detector"] = {
    {"worldSizeMm", cfg.detector.worldSizeMm},
    {"worldMaterial", cfg.detector.worldMaterial},
    {"mediumBoxMm", cfg.detector.mediumBoxMm},
    {"mediumMaterial", cfg.detector.mediumMaterial},
    {"temperatureK", cfg.detector.temperatureK},
    {"pressureAtm", cfg.detector.pressureAtm},
  };
  root["beam"] = {
    {"particle", cfg.beam.particle},
    {"energyMeV", cfg.beam.energyMeV},
    {"direction", {cfg.beam.directionX, cfg.beam.directionY, cfg.beam.directionZ}},
  };
  if (!cfg.beam.name.empty()) {
    root["beam"]["name"] = cfg.beam.name;
  }
  writeBeamExtras(root["beam"], cfg.beam);
  if (cfg.beam.active) {
    root["beam"]["active"] = cfg.beam.active;
  }
  bool includeBeams = cfg.beams.size() > 1;
  if (!includeBeams) {
    for (const auto& beam : cfg.beams) {
      if (!beam.name.empty() || beam.active) {
        includeBeams = true;
        break;
      }
    }
  }
  if (includeBeams) {
    auto beams = nlohmann::json::array();
    for (const auto& beam : cfg.beams) {
      nlohmann::json entry;
      if (!beam.name.empty()) {
        entry["name"] = beam.name;
      }
      entry["particle"] = beam.particle;
      entry["energyMeV"] = beam.energyMeV;
      entry["direction"] = {beam.directionX, beam.directionY, beam.directionZ};
      writeBeamExtras(entry, beam);
      if (beam.active) {
        entry["active"] = beam.active;
      }
      beams.push_back(entry);
    }
    root["beams"] = beams;
  }
  root["run"] = {
    {"nEvents", cfg.run.nEvents},
    {"seed", cfg.run.seed},
  };
  // Only emit a non-default thread count, so existing scenarios keep their
  // exact serialized config hash.
  if (cfg.run.threads != 0) {
    root["run"]["threads"] = cfg.run.threads;
  }
  if (cfg.run.timeBudgetSeconds > 0.0) {
    root["run"]["timeBudgetSeconds"] = cfg.run.timeBudgetSeconds;
  }
  // Only a scenario that selects non-default physics carries a `physics` block.
  if (!cfg.physics.list.empty() || cfg.physics.radioactiveDecayThresholdYears > 0.0 ||
      cfg.physics.gammaNuclearLowEnergyModelLimitMeV >= 0.0) {
    auto physics = nlohmann::json::object();
    if (!cfg.physics.list.empty()) {
      physics["list"] = cfg.physics.list;
    }
    if (cfg.physics.radioactiveDecayThresholdYears > 0.0) {
      physics["radioactiveDecayThresholdYears"] = cfg.physics.radioactiveDecayThresholdYears;
    }
    if (cfg.physics.gammaNuclearLowEnergyModelLimitMeV >= 0.0) {
      physics["gammaNuclearLowEnergyModelLimitMeV"] = cfg.physics.gammaNuclearLowEnergyModelLimitMeV;
    }
    root["physics"] = physics;
  }
  root["determinism"] = {
    {"mode", normalizeDeterminismMode(cfg.determinism.mode)},
  };
  root["system"] = {
    {"enable", cfg.system.enable},
    {"mode", cfg.system.mode},
    {"frame", cfg.system.frame},
    {"ensemble", cfg.system.ensemble},
    {"volumeMm3", cfg.system.volumeMm3},
  };
  root["optics"] = {
    {"enable", cfg.optics.enable},
    {"refractiveIndex", cfg.optics.refractiveIndex},
    {"absorptionLengthMm", cfg.optics.absorptionLengthMm},
    {"scatterLengthMm", cfg.optics.scatterLengthMm},
  };
  if (!cfg.optics.spectrum.empty()) {
    auto spectrum = nlohmann::json::array();
    for (const auto& point : cfg.optics.spectrum) {
      nlohmann::json entry;
      if (point.energyEv > 0.0) {
        entry["energyEv"] = point.energyEv;
      }
      if (point.wavelengthNm > 0.0) {
        entry["wavelengthNm"] = point.wavelengthNm;
      }
      if (point.refractiveIndex > 0.0) {
        entry["refractiveIndex"] = point.refractiveIndex;
      }
      if (point.absorptionLengthMm > 0.0) {
        entry["absorptionLengthMm"] = point.absorptionLengthMm;
      }
      if (point.scatterLengthMm > 0.0) {
        entry["scatterLengthMm"] = point.scatterLengthMm;
      }
      if (!entry.empty()) {
        spectrum.push_back(entry);
      }
    }
    if (!spectrum.empty()) {
      root["optics"]["spectrum"] = spectrum;
    }
  }
  if (cfg.opticsDerive.enable || !cfg.opticsDerive.validationReferences.empty()) {
    nlohmann::json derive;
    derive["enable"] = cfg.opticsDerive.enable;
    derive["mode"] = cfg.opticsDerive.mode;
    derive["energyMinEv"] = cfg.opticsDerive.energyMinEv;
    derive["energyMaxEv"] = cfg.opticsDerive.energyMaxEv;
    derive["nEnergyBins"] = cfg.opticsDerive.nEnergyBins;
    derive["kkIntegrationMinEv"] = cfg.opticsDerive.kkIntegrationMinEv;
    derive["kkIntegrationMaxEv"] = cfg.opticsDerive.kkIntegrationMaxEv;
    derive["kkIntegrationBins"] = cfg.opticsDerive.kkIntegrationBins;
    derive["modelValidMinEv"] = cfg.opticsDerive.modelValidMinEv;
    derive["valenceOscillator"] = cfg.opticsDerive.valenceOscillator;
    derive["valenceResonanceEv"] = cfg.opticsDerive.valenceResonanceEv;
    if (!cfg.opticsDerive.surrogateModelPath.empty()) {
      derive["surrogateModelPath"] = cfg.opticsDerive.surrogateModelPath;
    }
    derive["writeSpectrum"] = cfg.opticsDerive.writeSpectrum;
    if (cfg.opticsDerive.validateAgainstReferences ||
        !cfg.opticsDerive.validationReferences.empty()) {
      nlohmann::json validate;
      validate["enable"] = cfg.opticsDerive.validateAgainstReferences;
      if (!cfg.opticsDerive.validationReferences.empty()) {
        auto refs = nlohmann::json::array();
        for (const auto& ref : cfg.opticsDerive.validationReferences) {
          nlohmann::json entry;
          entry["material"] = ref.material;
          entry["energyEv"] = ref.energyEv;
          if (ref.refractiveIndex > 0.0) {
            entry["refractiveIndex"] = ref.refractiveIndex;
          }
          if (ref.absorptionLengthMm > 0.0) {
            entry["absorptionLengthMm"] = ref.absorptionLengthMm;
          }
          if (ref.scatterLengthMm > 0.0) {
            entry["scatterLengthMm"] = ref.scatterLengthMm;
          }
          if (!ref.source.empty()) {
            entry["source"] = ref.source;
          }
          refs.push_back(entry);
        }
        validate["references"] = refs;
      }
      derive["validate"] = validate;
    }
    root["optics"]["derive"] = derive;
  }
  if (cfg.viz.enable) {
    nlohmann::json viz;
    viz["enable"] = cfg.viz.enable;
    viz["scenePath"] = cfg.viz.scenePath;
    viz["trajectoriesPath"] = cfg.viz.trajectoriesPath;
    viz["maxTrajectories"] = cfg.viz.maxTrajectories;
    viz["sampleEveryNth"] = cfg.viz.sampleEveryNth;
    viz["maxSegmentsPerTrajectory"] = cfg.viz.maxSegmentsPerTrajectory;
    viz["includeNonOptical"] = cfg.viz.includeNonOptical;
    viz["recordVertices"] = cfg.viz.recordVertices;
    root["viz"] = viz;
  }
  root["chemistry"] = {
    {"enable", cfg.chemistry.enable},
    {"model", cfg.chemistry.model},
    {"solver", cfg.chemistry.solver},
  };
  if (cfg.nuclear.enable || !cfg.nuclear.cycles.empty()) {
    nlohmann::json nuclear;
    nuclear["enable"] = cfg.nuclear.enable;
    if (!cfg.nuclear.cycles.empty()) {
      auto cycles = nlohmann::json::array();
      for (const auto& cycle : cfg.nuclear.cycles) {
        nlohmann::json entry;
        if (!cycle.name.empty()) {
          entry["name"] = cycle.name;
        }
        entry["enable"] = cycle.enable;
        const auto writeSpecies = [](const NuclearSpeciesConfig& species) {
          nlohmann::json value;
          if (!species.symbol.empty()) {
            value["symbol"] = species.symbol;
          }
          if (!species.material.empty()) {
            value["material"] = species.material;
          }
          if (species.z > 0) {
            value["z"] = species.z;
          }
          if (species.a > 0) {
            value["a"] = species.a;
          }
          if (!species.phase.empty()) {
            value["phase"] = species.phase;
          }
          if (species.densityGcm3 > 0.0) {
            value["densityGcm3"] = species.densityGcm3;
          }
          return value;
        };
        const auto writeReaction = [](const NuclearReactionConfig& reaction) {
          nlohmann::json value;
          if (!reaction.name.empty()) {
            value["name"] = reaction.name;
          }
          if (reaction.halfLifeYears > 0.0) {
            value["halfLifeYears"] = reaction.halfLifeYears;
          }
          const auto writeParticipants =
              [](const std::vector<NuclearReactionParticipantConfig>& participants) {
                auto out = nlohmann::json::array();
                for (const auto& participant : participants) {
                  nlohmann::json p;
                  if (!participant.particle.empty()) {
                    p["particle"] = participant.particle;
                  }
                  if (participant.z > 0) {
                    p["z"] = participant.z;
                  }
                  if (participant.a > 0) {
                    p["a"] = participant.a;
                  }
                  if (!p.empty()) {
                    out.push_back(p);
                  }
                }
                return out;
              };
          if (!reaction.reactants.empty()) {
            value["reactants"] = writeParticipants(reaction.reactants);
          }
          if (!reaction.products.empty()) {
            value["products"] = writeParticipants(reaction.products);
          }
          return value;
        };
        const auto source = writeSpecies(cycle.source);
        if (!source.empty()) {
          entry["source"] = source;
        }
        const auto target = writeSpecies(cycle.target);
        if (!target.empty()) {
          entry["target"] = target;
        }
        const auto forward = writeReaction(cycle.forward);
        if (!forward.empty()) {
          entry["forward"] = forward;
        }
        const auto backward = writeReaction(cycle.backward);
        if (!backward.empty()) {
          entry["backward"] = backward;
        }
        cycles.push_back(entry);
      }
      nuclear["cycles"] = cycles;
    }
    root["nuclear"] = nuclear;
  }
  root["multiscale"] = {
    {"enable", cfg.multiscale.enable},
    {"method", cfg.multiscale.method},
    {"mode", cfg.multiscale.mode},
  };
  // Analytic cross-checks are conditionally serialized so scenarios that do not
  // request them keep their exact config hash.
  if (cfg.analytic.enable || !cfg.analytic.checks.empty()) {
    nlohmann::json analytic;
    analytic["enable"] = cfg.analytic.enable;
    if (!cfg.analytic.checks.empty()) {
      auto checks = nlohmann::json::array();
      for (const auto& check : cfg.analytic.checks) {
        nlohmann::json entry;
        entry["type"] = check.type;
        if (!check.label.empty()) {
          entry["label"] = check.label;
        }
        entry["particle"] = check.particle;
        entry["energyMeV"] = check.energyMeV;
        if (!check.material.empty()) {
          entry["material"] = check.material;
        }
        entry["pathLengthMm"] = check.pathLengthMm;
        entry["toleranceRel"] = check.toleranceRel;
        checks.push_back(entry);
      }
      analytic["checks"] = checks;
    }
    root["analytic"] = analytic;
  }
  // The precision profile is conditionally serialized (only when a scenario
  // declares one) so every existing scenario keeps its exact config hash.
  if (!cfg.precision.profile.empty() || !cfg.precision.axes.empty()) {
    nlohmann::json precision;
    if (!cfg.precision.profile.empty()) {
      precision["profile"] = cfg.precision.profile;
    }
    if (!cfg.precision.note.empty()) {
      precision["note"] = cfg.precision.note;
    }
    if (!cfg.precision.axes.empty()) {
      auto axes = nlohmann::json::array();
      for (const auto& axis : cfg.precision.axes) {
        nlohmann::json entry;
        entry["name"] = axis.name;
        entry["role"] = axis.role;
        if (!axis.control.empty()) {
          entry["control"] = axis.control;
        }
        if (!axis.unit.empty()) {
          entry["unit"] = axis.unit;
        }
        entry["value"] = axis.value;
        entry["baselineValue"] = axis.baselineValue;
        if (axis.representationOnly) {
          entry["representationOnly"] = true;
        }
        if (axis.overridden) {
          entry["overridden"] = true;
        }
        axes.push_back(entry);
      }
      precision["axes"] = axes;
    }
    root["precision"] = precision;
  }
  // The material-composition probe is conditionally serialized (only when opted
  // in) so scenarios that do not request it keep their exact config hash.
  if (cfg.materialProbe.enable || cfg.materialProbe.includeIsotopes || cfg.materialProbe.nuclearConfigurations > 0 || !cfg.materialProbe.materials.empty() ||
      !cfg.materialProbe.interactionEnergiesMeV.empty()) {
    nlohmann::json probe;
    probe["enable"] = cfg.materialProbe.enable;
    if (cfg.materialProbe.includeIsotopes || cfg.materialProbe.nuclearConfigurations > 0) probe["includeIsotopes"] = true;
    if (cfg.materialProbe.nuclearConfigurations > 0)
      probe["nuclearSamples"] = {{"configurations", cfg.materialProbe.nuclearConfigurations}, {"seed", cfg.materialProbe.nuclearSeed}};
    if (!cfg.materialProbe.materials.empty()) {
      probe["materials"] = cfg.materialProbe.materials;
    }
    if (!cfg.materialProbe.interactionEnergiesMeV.empty()) {
      probe["interactions"] = {{"particle", cfg.materialProbe.interactionParticle},
        {"processes", cfg.materialProbe.interactionProcesses},
        {"energiesMeV", cfg.materialProbe.interactionEnergiesMeV}};
    }
    root["materialProbe"] = probe;
  }
  if (!cfg.geometry.volumes.empty()) {
    auto volumes = nlohmann::json::array();
    for (const auto& volume : cfg.geometry.volumes) {
      nlohmann::json entry;
      entry["name"] = volume.name;
      if (!volume.material.empty()) {
        entry["material"] = volume.material;
      }
      entry["scoreEdep"] = volume.scoreEdep;
      if (!volume.tags.empty()) {
        entry["tags"] = volume.tags;
      }
      nlohmann::json shape;
      shape["type"] = volume.shape.type;
      if (volume.shape.sizeXmm > 0.0 || volume.shape.sizeYmm > 0.0 ||
          volume.shape.sizeZmm > 0.0) {
        shape["sizeMm"] = {volume.shape.sizeXmm, volume.shape.sizeYmm,
                           volume.shape.sizeZmm};
      }
      if (volume.shape.outerRadiusMm > 0.0 || volume.shape.innerRadiusMm > 0.0) {
        shape["outerRadiusMm"] = volume.shape.outerRadiusMm;
        shape["innerRadiusMm"] = volume.shape.innerRadiusMm;
      }
      if (volume.shape.lengthMm > 0.0) {
        shape["lengthMm"] = volume.shape.lengthMm;
      }
      if (!shape.empty()) {
        entry["shape"] = shape;
      }
      nlohmann::json placement;
      if (!volume.placement.parent.empty()) {
        placement["parent"] = volume.placement.parent;
      }
      placement["positionMm"] = {volume.placement.positionMm.x,
                                 volume.placement.positionMm.y,
                                 volume.placement.positionMm.z};
      placement["rotationDeg"] = {volume.placement.rotationDeg.x,
                                  volume.placement.rotationDeg.y,
                                  volume.placement.rotationDeg.z};
      entry["placement"] = placement;
      volumes.push_back(entry);
    }
    root["geometry"]["volumes"] = volumes;
  }
  if (!cfg.geometry.overlapCheck.isDefault()) {
    root["geometry"]["overlapCheck"] = {{"enable", cfg.geometry.overlapCheck.enable},
                                        {"samplesPerVolume", cfg.geometry.overlapCheck.samplesPerVolume},
                                        {"toleranceMm", cfg.geometry.overlapCheck.toleranceMm}};
  }
  if (!cfg.geometry.refuseOn.empty()) {
    root["geometry"]["refuseOn"] = cfg.geometry.refuseOn;
  }
  if (!cfg.materials.empty()) {
    auto materials = nlohmann::json::array();
    for (const auto& material : cfg.materials) {
      nlohmann::json entry;
      entry["name"] = material.name;
      if (!material.smiles.empty()) {
        entry["smiles"] = material.smiles;
      }
      if (material.densityGcm3 > 0.0) {
        entry["densityGcm3"] = material.densityGcm3;
      }
      if (!material.components.empty()) {
        auto components = nlohmann::json::array();
        for (const auto& component : material.components) {
          nlohmann::json comp;
          // Mirror the input form: an element component serializes as
          // `element`, otherwise as `material`, so round-trips stay stable.
          if (!component.element.empty()) {
            comp["element"] = component.element;
          } else {
            comp["material"] = component.material;
          }
          if (component.atoms > 0) comp["atoms"] = component.atoms;
          else comp["fraction"] = component.fraction;
          if (component.massNumber > 0) comp["massNumber"] = component.massNumber;
          components.push_back(comp);
        }
        entry["components"] = components;
      }
      materials.push_back(entry);
    }
    root["materials"] = materials;
  }
  if (!cfg.models.empty()) {
    auto models = nlohmann::json::array();
    for (const auto& model : cfg.models) {
      nlohmann::json entry;
      entry["name"] = model.name;
      entry["path"] = model.path;
      // Conditionally serialized: point/cascade models with no operator
      // metadata keep their historical config bytes (and therefore hash).
      if (!model.scale.empty()) {
        entry["scale"] = model.scale;
      }
      if (!model.operatorRole.empty()) {
        entry["operator_role"] = model.operatorRole;
      }
      if (!model.requiredContextKeys.empty()) {
        entry["required_context_keys"] = model.requiredContextKeys;
      }
      if (!model.elementKind.empty()) {
        entry["element_kind"] = model.elementKind;
      }
      models.push_back(entry);
    }
    root["models"] = models;
  }
  const HooksConfig defaultHooks;
  if (!cfg.hooks.registered.empty() || !cfg.hooks.inputsJson.empty() ||
      cfg.hooks.maxStepCallbacks != defaultHooks.maxStepCallbacks ||
      cfg.hooks.maxTrackCallbacks != defaultHooks.maxTrackCallbacks ||
      cfg.hooks.maxEmitsPerCallback != defaultHooks.maxEmitsPerCallback ||
      cfg.hooks.maxEmitPayloadBytes != defaultHooks.maxEmitPayloadBytes) {
    if (!cfg.hooks.registered.empty()) {
      root["hooks"]["registered"] = cfg.hooks.registered;
    }
    if (!cfg.hooks.inputsJson.empty()) root["hooks"]["inputs"] = nlohmann::json::parse(cfg.hooks.inputsJson);
    root["hooks"]["maxStepCallbacks"] =
        std::max(0, cfg.hooks.maxStepCallbacks);
    // Conditional: configs that never set it keep their canonical bytes.
    if (cfg.hooks.maxTrackCallbacks != defaultHooks.maxTrackCallbacks) {
      root["hooks"]["maxTrackCallbacks"] = std::max(0, cfg.hooks.maxTrackCallbacks);
    }
    root["hooks"]["maxEmitsPerCallback"] =
        std::max(0, cfg.hooks.maxEmitsPerCallback);
    root["hooks"]["maxEmitPayloadBytes"] =
        std::max(0, cfg.hooks.maxEmitPayloadBytes);
  }
  root["stratify"] = {
    {"enable", cfg.stratify.enable},
    {"edepMeVThreshold", cfg.stratify.edepMeVThreshold},
    {"opticalTrackLengthMmThreshold", cfg.stratify.opticalTrackLengthMmThreshold},
    {"totalTrackLengthMmThreshold", cfg.stratify.totalTrackLengthMmThreshold},
    {"totalTrackCountThreshold", cfg.stratify.totalTrackCountThreshold},
    {"totalStepCountThreshold", cfg.stratify.totalStepCountThreshold},
    {"opticalPhotonTrackThreshold", cfg.stratify.opticalPhotonTrackThreshold},
    {"opticalPhotonStepThreshold", cfg.stratify.opticalPhotonStepThreshold},
    {"labelPredictable", cfg.stratify.labelPredictable},
    {"labelExceptional", cfg.stratify.labelExceptional},
    {"labelUnclassified", cfg.stratify.labelUnclassified},
    {"modelPath", cfg.stratify.modelPath},
    {"dumpFeatures", cfg.stratify.dumpFeatures},
    {"dumpResimQueue", cfg.stratify.dumpResimQueue},
  };
  // Conditionally serialized so config hashes stay byte-identical for the many
  // scenarios that don't use it (the stratify block above is always emitted).
  if (cfg.stratify.resimOnLowConfidence) {
    root["stratify"]["resimOnLowConfidence"] = true;
  }
  if (cfg.stratify.resimOnStarvation) {
    root["stratify"]["resimOnStarvation"] = true;
  }
  if (cfg.stratify.resimOnScaleMismatch) {
    root["stratify"]["resimOnScaleMismatch"] = true;
  }
  root["lab"] = {
    {"enable", cfg.lab.enable},
    {"mode", cfg.lab.mode},
    {"commandSchema", cfg.lab.commandSchema},
    {"commandChannel", cfg.lab.commandChannel},
    {"targetHz", cfg.lab.targetHz},
    {"roundsPerTick", cfg.lab.roundsPerTick},
    {"minRoundsPerTick", cfg.lab.minRoundsPerTick},
    {"maxRoundsPerTick", cfg.lab.maxRoundsPerTick},
    {"roundLearningRate", cfg.lab.roundLearningRate},
  };
  return root.dump();
}

} // namespace trech
