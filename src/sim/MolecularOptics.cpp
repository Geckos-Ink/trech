#include "trech/sim/MolecularOptics.hpp"

#include "G4Element.hh"
#include "G4ElementVector.hh"
#include "G4EmCalculator.hh"
#include "G4Gamma.hh"
#include "G4IonisParamMat.hh"
#include "G4Material.hh"
#include "G4MaterialPropertiesTable.hh"
#include "G4NistManager.hh"
#include "G4ParticleDefinition.hh"
#include "G4PhysicalConstants.hh"
#include "G4SystemOfUnits.hh"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

namespace trech::sim {
namespace {

// Geant4 carries internal CLHEP units; we keep all the optics math in SI-ish
// scalars (mm, eV) and convert at the boundary.

constexpr double kHcEvNm = 1239.841984;  // h * c expressed in eV * nm

// f-sum rule: the squared plasma energy (hbar*omega_p)^2 in eV^2 per unit
// electron number density (electrons / cm^3).  Derived from
//   (hbar*omega_p)[eV] = 28.816 * sqrt(rho[g/cm^3] * Z/A)
// with rho*(Z/A) = N_e / N_A, i.e. 28.816^2 / N_A.  Cross-check: water at
// N_e = 3.34e23/cm^3 gives hbar*omega_p = 21.47 eV.
constexpr double kPlasmaEnergySqPerElectronDensityCm3 = 1.3789e-21;

// Valence electrons = Z minus the largest filled noble-gas core <= Z.  The
// valence shell carries essentially all of the visible-band oscillator
// strength; the tightly bound core electrons resonate in the keV range and
// contribute negligibly to the refractive index at optical energies.  Closed
// noble-gas shells: He 2, Ne 10, Ar 18, Kr 36, Xe 54, Rn 86.
int valenceElectronCount(int z) {
  if (z <= 0) {
    return 0;
  }
  static constexpr int kNobleCores[] = {2, 10, 18, 36, 54, 86};
  int core = 0;
  for (const int shell : kNobleCores) {
    if (shell < z) {
      core = shell;
    } else {
      break;
    }
  }
  return z - core;
}

double energyEvToWavelengthNm(double energyEv) {
  if (energyEv <= 0.0) {
    return 0.0;
  }
  return kHcEvNm / energyEv;
}

double clampNonNeg(double value) {
  return value < 0.0 ? 0.0 : value;
}

std::string toLowerCopy(const std::string& input) {
  std::string out = input;
  std::transform(out.begin(), out.end(), out.begin(), [](unsigned char ch) {
    return static_cast<char>(std::tolower(ch));
  });
  return out;
}

// Crude (E, RGB) mapping just for the viewer's tint hint.  Not used in physics.
std::array<double, 3> visibleEnergyToRgb(double energyEv) {
  const double wl = energyEvToWavelengthNm(energyEv);
  double r = 0.0;
  double g = 0.0;
  double b = 0.0;
  if (wl >= 380.0 && wl < 440.0) {
    r = -(wl - 440.0) / (440.0 - 380.0);
    b = 1.0;
  } else if (wl < 490.0) {
    g = (wl - 440.0) / (490.0 - 440.0);
    b = 1.0;
  } else if (wl < 510.0) {
    g = 1.0;
    b = -(wl - 510.0) / (510.0 - 490.0);
  } else if (wl < 580.0) {
    r = (wl - 510.0) / (580.0 - 510.0);
    g = 1.0;
  } else if (wl < 645.0) {
    r = 1.0;
    g = -(wl - 645.0) / (645.0 - 580.0);
  } else if (wl <= 780.0) {
    r = 1.0;
  }
  return {clampNonNeg(r), clampNonNeg(g), clampNonNeg(b)};
}

// Average display RGB weighted by visible-band transmission length.
std::array<double, 3> aggregateDisplayRgb(const std::vector<DerivedOpticsSample>& samples) {
  std::array<double, 3> acc{{0.0, 0.0, 0.0}};
  double weight = 0.0;
  for (const auto& s : samples) {
    const auto rgb = visibleEnergyToRgb(s.energyEv);
    const double w =
        s.absorptionLengthMm > 0.0 ? std::log1p(s.absorptionLengthMm) : 1.0;
    acc[0] += rgb[0] * w;
    acc[1] += rgb[1] * w;
    acc[2] += rgb[2] * w;
    weight += w;
  }
  if (weight <= 0.0) {
    return {1.0, 1.0, 1.0};
  }
  acc[0] /= weight;
  acc[1] /= weight;
  acc[2] /= weight;
  // Avoid total black — viewer needs something visible.
  const double maxComp = std::max({acc[0], acc[1], acc[2], 1e-3});
  acc[0] = std::clamp(acc[0] / maxComp, 0.0, 1.0);
  acc[1] = std::clamp(acc[1] / maxComp, 0.0, 1.0);
  acc[2] = std::clamp(acc[2] / maxComp, 0.0, 1.0);
  return acc;
}

// Logarithmic energy grid from energyMinEv to energyMaxEv.
std::vector<double> buildLogEnergyGrid(double minEv, double maxEv, int bins) {
  std::vector<double> grid;
  if (bins < 2 || minEv <= 0.0 || maxEv <= minEv) {
    if (minEv > 0.0) {
      grid.push_back(minEv);
    }
    return grid;
  }
  grid.reserve(bins);
  const double logMin = std::log(minEv);
  const double logMax = std::log(maxEv);
  for (int i = 0; i < bins; ++i) {
    const double t = static_cast<double>(i) / static_cast<double>(bins - 1);
    grid.push_back(std::exp(logMin + t * (logMax - logMin)));
  }
  return grid;
}

// Computes the cross sections via Geant4's EM calculator at one photon energy
// for the given material.  Returns CLHEP units (CrossSectionPerVolume -> 1/mm).
struct CrossSections {
  double muPhotoElectricPerMm = 0.0;
  double muComptonPerMm = 0.0;
  double muRayleighPerMm = 0.0;
};

CrossSections queryCrossSections(G4EmCalculator& calc, G4Material* material,
                                 double energyEv, double modelValidMinEv) {
  CrossSections cs;
  if (!material || energyEv <= 0.0) {
    return cs;
  }
  if (modelValidMinEv > 0.0 && energyEv < modelValidMinEv) {
    // Below the Livermore/Penelope model validity range — extrapolated values
    // would dominate the optical-band attenuation artificially.  Treat as
    // "Geant4 atomic data does not constrain this" by returning zero.
    return cs;
  }
  const double energyMeV = energyEv * 1.0e-6;  // 1 eV = 1e-6 MeV
  const double energyG4 = energyMeV * MeV;
  const G4ParticleDefinition* gamma = G4Gamma::Definition();
  const auto safeQuery = [&](const G4String& processName) -> double {
    try {
      const double value =
          calc.ComputeCrossSectionPerVolume(energyG4, gamma, processName, material);
      // Geant4 returns CLHEP "1/length" — convert to 1/mm.
      return std::max(0.0, value * mm);
    } catch (...) {
      return 0.0;
    }
  };
  cs.muPhotoElectricPerMm = safeQuery("phot");
  cs.muComptonPerMm = safeQuery("compt");
  cs.muRayleighPerMm = safeQuery("Rayl");
  return cs;
}

// Discrete Kramers-Kronig transform for the real part of refractive index.
// n(E) - 1 = (2/pi) * P ∫₀^∞ E' * k(E') / (E'^2 - E^2) dE'
// Integration is on a logarithmic grid; near-singularity points are skipped
// (P stands for Cauchy principal value).
double kramersKronigRealMinusOne(double targetEv,
                                 const std::vector<double>& energyEv,
                                 const std::vector<double>& extinctionK) {
  if (energyEv.size() < 2) {
    return 0.0;
  }
  double accumulator = 0.0;
  for (std::size_t i = 0; i + 1 < energyEv.size(); ++i) {
    const double e0 = energyEv[i];
    const double e1 = energyEv[i + 1];
    const double k0 = extinctionK[i];
    const double k1 = extinctionK[i + 1];
    const double mid = 0.5 * (e0 + e1);
    const double width = e1 - e0;
    const double denom = (mid * mid) - (targetEv * targetEv);
    if (std::abs(denom) < 1.0e-12) {
      continue;
    }
    const double integrand = mid * (0.5 * (k0 + k1)) / denom;
    accumulator += integrand * width;
  }
  return (2.0 / M_PI) * accumulator;
}

}  // namespace

MolecularOpticsExtractor::MolecularOpticsExtractor(
    const OpticsDeriveConfig& cfg,
    const std::vector<MaterialConfig>& materialConfigs,
    const std::vector<OpticsValidationReferenceConfig>& refs)
    : cfg_(cfg), materialConfigs_(materialConfigs), validationRefs_(refs) {}

std::vector<DerivedOpticsResult> MolecularOpticsExtractor::deriveAll(
    const std::vector<std::string>& materialNames) const {
  std::vector<DerivedOpticsResult> out;
  out.reserve(materialNames.size());
  auto* nist = G4NistManager::Instance();
  if (!nist) {
    return out;
  }
  for (const auto& name : materialNames) {
    if (name.empty()) {
      continue;
    }
    G4Material* material = nist->FindOrBuildMaterial(name);
    if (!material) {
      // Try the custom registry by simple iteration (Geant4 globally caches by name).
      const auto& table = *G4Material::GetMaterialTable();
      for (auto* m : table) {
        if (m && m->GetName() == name) {
          material = m;
          break;
        }
      }
    }
    if (!material) {
      DerivedOpticsResult skipped;
      skipped.materialName = name;
      skipped.available = false;
      skipped.note = "material not resolvable in G4 registry";
      out.push_back(std::move(skipped));
      continue;
    }
    out.push_back(deriveForMaterial(material));
  }
  return out;
}

DerivedOpticsResult MolecularOpticsExtractor::deriveForMaterial(G4Material* material) const {
  DerivedOpticsResult result;
  if (!material) {
    result.note = "null material";
    return result;
  }
  result.materialName = material->GetName();
  result.densityGcm3 = material->GetDensity() / (g / cm3);
  result.numberDensityPerCm3 = material->GetTotNbOfAtomsPerVolume() / (1.0 / cm3);

  // mean molar mass — handy for the manifest.
  {
    const auto* elements = material->GetElementVector();
    const auto* fractions = material->GetFractionVector();
    double inverseMolar = 0.0;
    for (std::size_t i = 0; i < material->GetNumberOfElements(); ++i) {
      if (!(*elements)[i]) {
        continue;
      }
      // G4Element::GetA() returns mass in Geant4 internal units (g/mole).
      const double massGperMol = (*elements)[i]->GetA() / (g / mole);
      if (massGperMol > 0.0) {
        inverseMolar += fractions[i] / massGperMol;
      }
      // G4Material's fraction vector is by mass — exactly what the surrogate
      // composition encoder expects.
      result.elementMassFractions.emplace_back(
          (*elements)[i]->GetSymbol(), fractions[i]);
    }
    result.meanMolarMassGperMol = inverseMolar > 0.0 ? (1.0 / inverseMolar) : 0.0;
  }

  // f-sum-rule valence oscillator inputs.  Total electron density comes
  // straight from Geant4; the valence electron density is summed per element
  // from the closed-shell rule.  The valence plasma energy then sets the
  // oscillator strength restored in the visible band.
  result.electronDensityPerCm3 = material->GetElectronDensity() / (1.0 / cm3);
  {
    const auto* elements = material->GetElementVector();
    const G4double* atomsPerVol = material->GetVecNbOfAtomsPerVolume();
    double valenceDensity = 0.0;
    for (std::size_t i = 0; i < material->GetNumberOfElements(); ++i) {
      if (!(*elements)[i] || !atomsPerVol) {
        continue;
      }
      const int z = (*elements)[i]->GetZasInt();
      const double nAtomsPerCm3 = atomsPerVol[i] / (1.0 / cm3);
      valenceDensity += nAtomsPerCm3 * static_cast<double>(valenceElectronCount(z));
    }
    result.valenceElectronDensityPerCm3 = valenceDensity;
  }
  if (material->GetIonisation()) {
    result.meanExcitationEnergyEv = material->GetIonisation()->GetMeanExcitationEnergy() / eV;
  }
  const double plasmaValenceSqEv2 =
      result.valenceElectronDensityPerCm3 * kPlasmaEnergySqPerElectronDensityCm3;
  result.plasmaEnergyEv = std::sqrt(std::max(0.0, plasmaValenceSqEv2));
  result.valenceResonanceEv = cfg_.valenceOscillator ? cfg_.valenceResonanceEv : 0.0;

  // Match this material against the JS-level config (used for SMILES note etc.).
  const auto lname = toLowerCopy(result.materialName);
  for (const auto& cfg : materialConfigs_) {
    if (!cfg.name.empty() && toLowerCopy(cfg.name) == lname) {
      result.configMaterialKey = cfg.name;
      break;
    }
  }

  G4EmCalculator calc;

  // Wide-range cross-section sweep used as the Kramers-Kronig integrand source.
  // The visible-band samples then carry the report-facing n(E).
  const auto kkGrid =
      buildLogEnergyGrid(cfg_.kkIntegrationMinEv, cfg_.kkIntegrationMaxEv,
                         cfg_.kkIntegrationBins);
  result.kkSamples.reserve(kkGrid.size());
  for (const double energyEv : kkGrid) {
    const auto cs = queryCrossSections(calc, material, energyEv, cfg_.modelValidMinEv);
    DerivedOpticsSample sample;
    sample.energyEv = energyEv;
    sample.wavelengthNm = energyEvToWavelengthNm(energyEv);
    sample.muAbsPerMm = cs.muPhotoElectricPerMm + cs.muComptonPerMm;
    sample.muScatPerMm = cs.muRayleighPerMm;
    // k = mu_abs * (h c) / (4 pi E)
    // expressing E in eV, lambda in nm: k = mu_abs[1/nm] * lambda[nm] / (4 pi)
    const double muAbsPerNm = sample.muAbsPerMm * 1.0e-6;
    sample.extinctionK = (muAbsPerNm * sample.wavelengthNm) / (4.0 * M_PI);
    if (sample.muAbsPerMm > 0.0) {
      sample.absorptionLengthMm = 1.0 / sample.muAbsPerMm;
    }
    if (sample.muScatPerMm > 0.0) {
      sample.scatterLengthMm = 1.0 / sample.muScatPerMm;
    }
    result.kkSamples.push_back(sample);
  }

  std::vector<double> kkEnergies;
  std::vector<double> kkExtinctions;
  kkEnergies.reserve(result.kkSamples.size());
  kkExtinctions.reserve(result.kkSamples.size());
  for (const auto& sample : result.kkSamples) {
    kkEnergies.push_back(sample.energyEv);
    kkExtinctions.push_back(sample.extinctionK);
  }

  const auto visibleGrid = buildLogEnergyGrid(cfg_.energyMinEv, cfg_.energyMaxEv,
                                              cfg_.nEnergyBins);
  result.samples.reserve(visibleGrid.size());
  for (const double energyEv : visibleGrid) {
    const auto cs = queryCrossSections(calc, material, energyEv, cfg_.modelValidMinEv);
    DerivedOpticsSample sample;
    sample.energyEv = energyEv;
    sample.wavelengthNm = energyEvToWavelengthNm(energyEv);
    sample.muAbsPerMm = cs.muPhotoElectricPerMm + cs.muComptonPerMm;
    sample.muScatPerMm = cs.muRayleighPerMm;
    const double muAbsPerNm = sample.muAbsPerMm * 1.0e-6;
    sample.extinctionK = (muAbsPerNm * sample.wavelengthNm) / (4.0 * M_PI);

    const double nMinus1 = kramersKronigRealMinusOne(energyEv, kkEnergies, kkExtinctions);
    // Combine susceptibilities (chi = n^2 - 1; they add linearly).  The KK
    // result carries the core/high-energy dispersion Geant4 resolves; the
    // valence oscillator restores the UV oscillator strength below
    // modelValidMinEv that dominates the visible refractive index but that the
    // atomic photoabsorption tables miss.  chi_valence(E) = (hbar*wp)^2 /
    // (E0^2 - E^2) with the strength fixed by the valence electron density.
    const double nCore = 1.0 + nMinus1;
    double chi = (nCore * nCore) - 1.0;
    if (cfg_.valenceOscillator && cfg_.valenceResonanceEv > 0.0 &&
        plasmaValenceSqEv2 > 0.0) {
      const double e0 = cfg_.valenceResonanceEv;
      const double denom = (e0 * e0) - (energyEv * energyEv);
      if (denom > 1.0e-6) {
        chi += plasmaValenceSqEv2 / denom;
      }
    }
    // Lower-bound to 1.0 for stability — KK on a truncated spectrum can dip
    // marginally below 1, and Geant4's optical transport refuses negative n.
    sample.refractiveIndex = std::sqrt(std::max(1.0, 1.0 + chi));

    if (sample.muAbsPerMm > 0.0) {
      sample.absorptionLengthMm = 1.0 / sample.muAbsPerMm;
    } else {
      sample.absorptionLengthMm = 1.0e6;  // effectively transparent at this band
    }
    if (sample.muScatPerMm > 0.0) {
      sample.scatterLengthMm = 1.0 / sample.muScatPerMm;
    } else {
      sample.scatterLengthMm = 1.0e6;
    }
    result.samples.push_back(sample);
  }

  // Aggregate scalar reporting fields.
  if (!result.samples.empty()) {
    double sumN = 0.0;
    double sumAbs = 0.0;
    double sumScat = 0.0;
    for (const auto& s : result.samples) {
      sumN += s.refractiveIndex;
      sumAbs += s.absorptionLengthMm;
      sumScat += s.scatterLengthMm;
    }
    const double n = static_cast<double>(result.samples.size());
    result.meanRefractiveIndex = sumN / n;
    result.meanAbsorptionLengthMm = sumAbs / n;
    result.meanScatterLengthMm = sumScat / n;
  }

  // Validation deltas against user-supplied references (logged only).
  for (const auto& ref : validationRefs_) {
    if (!ref.material.empty() && toLowerCopy(ref.material) != lname) {
      continue;
    }
    // pick the closest derived sample
    const DerivedOpticsSample* closest = nullptr;
    double bestDelta = std::numeric_limits<double>::infinity();
    for (const auto& s : result.samples) {
      const double d = std::abs(std::log(s.energyEv / ref.energyEv));
      if (d < bestDelta) {
        bestDelta = d;
        closest = &s;
      }
    }
    if (!closest) {
      continue;
    }
    DerivedOpticsReferenceDelta delta;
    delta.energyEv = ref.energyEv;
    delta.refractiveIndex = closest->refractiveIndex;
    delta.refractiveIndexReference = ref.refractiveIndex;
    delta.refractiveIndexDelta = closest->refractiveIndex - ref.refractiveIndex;
    delta.absorptionLengthMm = closest->absorptionLengthMm;
    delta.absorptionLengthReferenceMm = ref.absorptionLengthMm;
    delta.scatterLengthMm = closest->scatterLengthMm;
    delta.scatterLengthReferenceMm = ref.scatterLengthMm;
    delta.source = ref.source;
    result.referenceDeltas.push_back(delta);
  }

  result.displayRgb = aggregateDisplayRgb(result.samples);
  result.available = !result.samples.empty();
  if (!result.available) {
    result.note = "no visible-band samples produced";
  } else {
    std::ostringstream note;
    note << "derived via G4EmCalculator photoelectric+Compton+Rayleigh over ["
         << cfg_.kkIntegrationMinEv << " eV, " << cfg_.kkIntegrationMaxEv
         << " eV], visible band [" << cfg_.energyMinEv << " eV, "
         << cfg_.energyMaxEv << " eV]; n via Kramers-Kronig on extinction k";
    if (cfg_.valenceOscillator && result.valenceResonanceEv > 0.0) {
      note << " + f-sum valence oscillator (hbar*wp=" << result.plasmaEnergyEv
           << " eV from " << result.valenceElectronDensityPerCm3
           << " valence e/cm^3, E0=" << result.valenceResonanceEv << " eV)";
    }
    note << ".";
    result.note = note.str();
  }

  return result;
}

void MolecularOpticsExtractor::attachToMaterial(G4Material* material,
                                                const DerivedOpticsResult& result) {
  if (!material || result.samples.empty()) {
    return;
  }
  std::vector<double> photonEnergy;
  std::vector<double> rindex;
  std::vector<double> absLength;
  std::vector<double> rayleigh;
  photonEnergy.reserve(result.samples.size());
  rindex.reserve(result.samples.size());
  absLength.reserve(result.samples.size());
  rayleigh.reserve(result.samples.size());
  for (const auto& sample : result.samples) {
    photonEnergy.push_back(sample.energyEv * eV);
    rindex.push_back(sample.refractiveIndex);
    absLength.push_back(std::max(1.0e-6, sample.absorptionLengthMm) * mm);
    rayleigh.push_back(std::max(1.0e-6, sample.scatterLengthMm) * mm);
  }
  auto* mpt = material->GetMaterialPropertiesTable();
  if (!mpt) {
    mpt = new G4MaterialPropertiesTable();
    material->SetMaterialPropertiesTable(mpt);
  }
  mpt->AddProperty("RINDEX", photonEnergy, rindex, true);
  mpt->AddProperty("ABSLENGTH", photonEnergy, absLength, true);
  mpt->AddProperty("RAYLEIGH", photonEnergy, rayleigh, true);
}

}  // namespace trech::sim
