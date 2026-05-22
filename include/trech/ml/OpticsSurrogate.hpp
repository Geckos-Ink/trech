#pragma once

#include <array>
#include <memory>
#include <string>
#include <vector>

namespace torch::jit {
class Module;
}

namespace trech::ml {

// Optics surrogate model: predicts (n, absorption_length_mm, scatter_length_mm)
// in the visible band given a fixed-length composition vector.
//
// The vector schema (kCompositionElements) is the same one used by the Python
// trainer at tools/torch/train_optics_surrogate.py.  Each entry is the mass
// fraction of the corresponding element; the final entry is the bulk density
// in g/cm^3.  Keep the two schemas in lock-step.
class OpticsSurrogate {
 public:
  // Element list and slot meanings.  Anything outside this list contributes
  // through a single 'other' bucket so unknown elements degrade gracefully
  // rather than failing the prediction.
  static constexpr std::array<const char*, 13> kCompositionElements = {
      "H", "C", "N", "O", "F", "Na", "Mg", "Al", "Si", "P", "S", "Cl", "other"};
  static constexpr int kInputFeatureCount =
      static_cast<int>(kCompositionElements.size()) + 1;  // + density

  OpticsSurrogate();
  ~OpticsSurrogate();

  OpticsSurrogate(const OpticsSurrogate&) = delete;
  OpticsSurrogate& operator=(const OpticsSurrogate&) = delete;

  bool load(const std::string& modelPath);
  bool loaded() const;
  const std::string& modelPath() const { return modelPath_; }
  const std::string& note() const { return note_; }

  // Predict (n, absorption_length_mm, scatter_length_mm).  Returns true on
  // success and writes the three outputs in order.  When Torch is not built
  // or the model is not loaded this returns false and out is untouched.
  bool predict(const std::vector<float>& compositionVector,
               std::array<float, 3>* out) const;

  // Helper: encode (element mass fractions map + density) into the canonical
  // input vector, dispatching unknown elements into the 'other' bucket.
  static std::vector<float> encodeComposition(
      const std::vector<std::pair<std::string, double>>& massFractions,
      double densityGcm3);

 private:
  std::string modelPath_;
  std::string note_;
#if defined(TRECH_ENABLE_TORCH)
  std::unique_ptr<torch::jit::Module> module_;
#endif
};

}  // namespace trech::ml
