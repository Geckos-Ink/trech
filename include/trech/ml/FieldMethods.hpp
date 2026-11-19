#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace trech::ml {

// Declared system of ctx.evolveField (see FieldEvolution.hpp). Shared by every field method.
struct FieldRegion {
  std::string shape = "box";          // "box": [0,size]^3; "cylinder": axis z, x,y in [-R,R], z in [0,L]
  std::array<double, 3> sizeMm{0, 0, 0};
  double radiusMm = 0.0, lengthMm = 0.0;
};

struct FieldProperties {
  double kinematicViscosityM2S = 0.0;
  double diffusivityM2S = 0.0;
  double expansionPerUnit = 0.0;      // relative density change per field unit (Boussinesq)
  std::array<double, 3> bodyAccelerationM2S{0, 0, 0};
};

struct FieldEvolutionOptions {
  double cellMm = 6.0;                // lattice cell of the lattice methods
  double machTarget = 0.15;           // lattice Mach number of the free-fall velocity bound
  double twinRatio = 1.5;             // twin cell / main cell for self-consistency evidence
  double conductiveTau = 1.0;         // relaxation time of the conduction-only lattice
  std::size_t minElements = 32;       // learner rows per split side (arbitration, learned methods)
  std::uint64_t seed = 0;
};

struct FieldEvolutionInput {
  double timeS = 0.0;
  std::vector<double> rate, target, loadPerS;  // per field cell, may be empty
  std::vector<double> reference;               // per field cell, may be empty
};

// Everything a method may read about the declared system. Built once, on the first call.
struct FieldSystem {
  FieldRegion region;
  std::vector<std::array<double, 3>> cellMin, cellMax;
  FieldProperties properties;
  std::vector<double> initial;
  FieldEvolutionOptions options;
  double offset = 0.0;  // mean initial value (methods may evolve value - offset)
  double span = 1.0;    // range of the initial values and declared exchange targets
  // Face adjacency between declared cells: conductance = shared face area / centre distance (mm).
  struct Link { std::size_t other; double conductanceMm; };
  std::vector<std::vector<Link>> links;
  std::vector<double> volumeMm3;
  std::vector<double> exposedFraction;  // share of a cell's faces not shared with another cell
  // Method-independent context of each call (names fixed; values per cell, see FieldCall).
  std::vector<std::string> contextNames;
  std::size_t cells() const { return cellMin.size(); }
};

// One call as every method sees it. `state` is the field each method predicts FROM: the last
// reference when the previous call was graded, else the engine's own arbitrated field.
struct FieldCall {
  const FieldEvolutionInput& input;
  double previousTimeS = 0.0;
  const std::vector<double>& state;
  const std::vector<double>& context;  // cells x system.contextNames
};

// A prediction method for a declared field. Lattice methods, learned operators, baselines and
// any method added later implement this and register a factory; FieldEvolution advances every
// applicable registered method and the MethodArbiter chooses among them per context domain.
// A method never sees which method wins and never names a material, scenario or domain.
class FieldMethod {
 public:
  explicit FieldMethod(std::string name) : name_(std::move(name)) {}
  virtual ~FieldMethod() = default;
  const std::string& name() const { return name_; }

  // Build for the declared system on the first call. Return an empty string when applicable,
  // else the reason the method cannot represent this system (it is then not a candidate).
  virtual std::string build(const FieldSystem& system, const FieldEvolutionInput& first) = 0;
  // Advance to call.input.timeS with the call's exchanges.
  virtual void advance(const FieldCall& call) = 0;
  // Per declared cell; NaN where the method has no prediction.
  virtual std::vector<double> prediction() const = 0;
  // The call's reference after grading (one-step-ahead synchronisation, online learning).
  virtual void observe(const FieldCall&, const std::vector<double>& /*reference*/) {}
  // Optional extra context the method contributes to arbitration (cells x names); fixed names.
  virtual std::vector<std::string> descriptorNames() const { return {}; }
  virtual std::vector<double> descriptors() const { return {}; }
  // Per-call and run reports (diagnostics; never fed back).
  virtual nlohmann::json report() const { return nlohmann::json::object(); }
  virtual nlohmann::json summary() const { return nlohmann::json::object(); }

  bool failed() const { return failed_; }
  const std::string& failure() const { return failure_; }

 protected:
  // A failing method keeps predicting its last valid state; the arbitration routes away from it.
  void fail(std::string reason) { failed_ = true; failure_ = std::move(reason); }

 private:
  std::string name_;
  bool failed_ = false;
  std::string failure_;
};

struct FieldMethodEntry {
  std::string name;
  std::string family;       // "lattice" | "learned" | "baseline" | any later family
  std::string description;
  std::function<std::unique_ptr<FieldMethod>()> make;
};

// The engine's field-method registry (built-in methods first, in registration order). Adding a
// method is one registerFieldMethod call: arbitration, accounting and reports pick it up.
const std::vector<FieldMethodEntry>& fieldMethodRegistry();
void registerFieldMethod(FieldMethodEntry entry);  // throws on an empty or duplicate name

}  // namespace trech::ml
