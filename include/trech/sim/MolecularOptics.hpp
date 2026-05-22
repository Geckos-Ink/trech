#pragma once

#include "trech/core/Config.hpp"

#include <array>
#include <string>
#include <unordered_map>
#include <vector>

class G4Material;

namespace trech::sim {

// One spectral sample of the derived complex refractive index and the
// underlying linear attenuation coefficients (per material).
struct DerivedOpticsSample {
  double energyEv = 0.0;
  double wavelengthNm = 0.0;
  double refractiveIndex = 1.0;     // real part, derived via Kramers-Kronig
  double extinctionK = 0.0;         // imag part (n + i k)
  double absorptionLengthMm = 0.0;  // 1 / mu_abs (photoelectric + Compton)
  double scatterLengthMm = 0.0;     // 1 / mu_scat (Rayleigh)
  double muAbsPerMm = 0.0;
  double muScatPerMm = 0.0;
};

struct DerivedOpticsReferenceDelta {
  double energyEv = 0.0;
  double refractiveIndex = 0.0;
  double refractiveIndexReference = 0.0;
  double refractiveIndexDelta = 0.0;
  double absorptionLengthMm = 0.0;
  double absorptionLengthReferenceMm = 0.0;
  double scatterLengthMm = 0.0;
  double scatterLengthReferenceMm = 0.0;
  std::string source;
};

// Per-material derivation result. Lives long enough to feed the macroscale
// G4MaterialPropertiesTable and the viz scene manifest.
struct DerivedOpticsResult {
  std::string materialName;          // Geant4 material name (post-resolve)
  std::string configMaterialKey;     // key used in config materials section
  double densityGcm3 = 0.0;
  double meanMolarMassGperMol = 0.0;
  double numberDensityPerCm3 = 0.0;
  std::vector<DerivedOpticsSample> samples;     // visible-band reporting samples
  std::vector<DerivedOpticsSample> kkSamples;   // wide-range integration support
  std::array<double, 3> displayRgb{{1.0, 1.0, 1.0}};
  double meanRefractiveIndex = 1.0;
  double meanAbsorptionLengthMm = 0.0;
  double meanScatterLengthMm = 0.0;
  std::vector<DerivedOpticsReferenceDelta> referenceDeltas;
  bool available = false;            // false means derivation skipped/failed
  std::string note;                  // human-readable provenance note
};

class MolecularOpticsExtractor {
 public:
  MolecularOpticsExtractor(const OpticsDeriveConfig& cfg,
                           const std::vector<MaterialConfig>& materialConfigs,
                           const std::vector<OpticsValidationReferenceConfig>& refs);

  // Runs the derivation for every G4Material name passed in. Geant4 must be
  // fully initialized (physics list materialized) before this is called so the
  // EM cross-section tables are populated.
  std::vector<DerivedOpticsResult> deriveAll(
      const std::vector<std::string>& materialNames) const;

  DerivedOpticsResult deriveForMaterial(G4Material* material) const;

  // Attach a G4MaterialPropertiesTable built from the derived samples to the
  // given G4Material.  Existing properties are overwritten.
  static void attachToMaterial(G4Material* material, const DerivedOpticsResult& result);

 private:
  OpticsDeriveConfig cfg_;
  std::vector<MaterialConfig> materialConfigs_;
  std::vector<OpticsValidationReferenceConfig> validationRefs_;
};

}  // namespace trech::sim
