#include "trech/sim/GeantRunner.hpp"
#include "trech/chem/DnaChemistry.hpp"
#include "trech/ml/OpticsSurrogate.hpp"
#include "trech/sim/MultiscaleBridge.hpp"
#include "trech/sim/ActionInitialization.hpp"
#include "trech/sim/DetectorConstruction.hpp"
#include "trech/sim/MolecularOptics.hpp"

#include "G4Element.hh"
#include "G4Material.hh"
#include "G4NistManager.hh"

#include "G4PhysListFactory.hh"
#if defined(TRECH_ENABLE_DNA_CHEM)
#include "G4EmDNAChemistry.hh"
#include "G4EmDNAChemistry_option1.hh"
#include "G4EmDNAChemistry_option2.hh"
#include "G4EmDNAChemistry_option3.hh"
#include "G4EmDNAPhysics.hh"
#include "G4EmDNAPhysics_option1.hh"
#include "G4EmDNAPhysics_option2.hh"
#include "G4EmDNAPhysics_option3.hh"
#include "G4EmDNAPhysics_option4.hh"
#include "G4EmDNAPhysics_option5.hh"
#include "G4EmDNAPhysics_option6.hh"
#include "G4EmDNAPhysics_option7.hh"
#include "G4EmDNAPhysics_option8.hh"
#include "G4VPhysicsConstructor.hh"
#endif
#include "G4OpticalPhysics.hh"
#include "G4RunManagerFactory.hh"
#include "G4UIExecutive.hh"
#include "G4UImanager.hh"
#include "G4VisExecutive.hh"
#include "G4VisManager.hh"
#include "G4VModularPhysicsList.hh"
#include "Randomize.hh"

#include <filesystem>
#include <string>

namespace trech {
namespace {
#if defined(TRECH_ENABLE_DNA_CHEM)

G4VPhysicsConstructor* buildDnaPhysics(int option) {
  switch (option) {
    case 1:
      return new G4EmDNAPhysics_option1();
    case 2:
      return new G4EmDNAPhysics_option2();
    case 3:
      return new G4EmDNAPhysics_option3();
    case 4:
      return new G4EmDNAPhysics_option4();
    case 5:
      return new G4EmDNAPhysics_option5();
    case 6:
      return new G4EmDNAPhysics_option6();
    case 7:
      return new G4EmDNAPhysics_option7();
    case 8:
      return new G4EmDNAPhysics_option8();
    default:
      return new G4EmDNAPhysics();
  }
}

G4VPhysicsConstructor* buildDnaChemistry(int option) {
  switch (option) {
    case 1:
      return new G4EmDNAChemistry_option1();
    case 2:
      return new G4EmDNAChemistry_option2();
    case 3:
      return new G4EmDNAChemistry_option3();
    default:
      return new G4EmDNAChemistry();
  }
}

std::string dnaPhysicsTag(int option) {
  if (option > 0) {
    return "DNA_Opt" + std::to_string(option);
  }
  return "DNA";
}

std::string dnaChemistryTag(int option) {
  if (option > 0) {
    return "Chem_Opt" + std::to_string(option);
  }
  return "Chem";
}

#endif
} // namespace

int runGeant4(const TrechConfig& cfg, RunOptions options, int argc, char** argv) {
  if (!options.outputDir.empty()) {
    std::filesystem::create_directories(options.outputDir);
  }

  CLHEP::HepRandom::setTheSeed(cfg.run.seed);
  if (CLHEP::HepRandom::getTheEngine()) {
    options.rngEngine = CLHEP::HepRandom::getTheEngine()->name();
  }

  auto* runManager = G4RunManagerFactory::CreateRunManager();

  // Optional explicit worker-thread count (run.threads). 0 keeps Geant4's
  // default; a positive value (typically 1) forces deterministic serial event
  // processing for hook-driven scenarios whose state accumulates across events.
  if (cfg.run.threads > 0) {
    runManager->SetNumberOfThreads(cfg.run.threads);
  }

  runManager->SetUserInitialization(
      new TrechDetectorConstruction(cfg.detector, cfg.optics, cfg.geometry, cfg.materials));

  G4PhysListFactory factory;
  const std::string physicsListName = "QBBC";
  G4VModularPhysicsList* phys = factory.GetReferencePhysList(physicsListName);
#if defined(TRECH_ENABLE_DNA_CHEM)
  bool dnaPhysicsEnabled = false;
  bool dnaChemistryEnabled = false;
  int dnaPhysicsOption = 0;
  int dnaChemistryOption = 0;
#endif

  if (cfg.chemistry.enable) {
    trech::chem::DnaChemistryBridge chemistry(cfg.chemistry);
    const auto status = chemistry.Configure();
#if defined(TRECH_ENABLE_DNA_CHEM)
    if (status.dnaPhysics) {
      dnaPhysicsEnabled = true;
      dnaPhysicsOption = status.dnaPhysicsOption;
      phys->ReplacePhysics(buildDnaPhysics(status.dnaPhysicsOption));
      if (status.chemistryStage) {
        dnaChemistryEnabled = true;
        dnaChemistryOption = status.chemistryOption;
        phys->RegisterPhysics(buildDnaChemistry(status.chemistryOption));
      }
    }
#else
    (void)status;
#endif
  }
  if (cfg.multiscale.enable) {
    trech::sim::MultiscaleBridge multiscale(cfg.multiscale);
    const auto status = multiscale.Configure();
    (void)status;
  }
  if (cfg.optics.enable) {
    phys->RegisterPhysics(new G4OpticalPhysics());
  }
  options.physicsList = physicsListName;
#if defined(TRECH_ENABLE_DNA_CHEM)
  options.dnaPhysicsEnabled = dnaPhysicsEnabled;
  options.dnaPhysicsOption = dnaPhysicsOption;
  options.dnaChemistryEnabled = dnaChemistryEnabled;
  options.dnaChemistryOption = dnaChemistryOption;
  if (dnaPhysicsEnabled) {
    options.physicsList += "+" + dnaPhysicsTag(dnaPhysicsOption);
  }
  if (dnaChemistryEnabled) {
    options.physicsList += "+" + dnaChemistryTag(dnaChemistryOption);
  }
#endif
  if (cfg.optics.enable) {
    options.physicsList += "+Optical";
  }
  runManager->SetUserInitialization(phys);

  if (cfg.opticsDerive.enable && !options.derivedOptics) {
    options.derivedOptics = std::make_shared<std::vector<trech::sim::DerivedOpticsResult>>();
  }
  runManager->SetUserInitialization(new TrechActionInitialization(cfg, options));

  G4UIExecutive* ui = options.enableUi ? new G4UIExecutive(argc, argv) : nullptr;
  G4VisManager* vis = nullptr;

  if (ui) {
    vis = new G4VisExecutive();
    vis->Initialize();
  }

  runManager->Initialize();

  if (cfg.opticsDerive.enable) {
    trech::sim::MolecularOpticsExtractor extractor(
        cfg.opticsDerive, cfg.materials, cfg.opticsDerive.validationReferences);
    std::vector<std::string> materialNames;
    materialNames.reserve(cfg.materials.size() + 4);
    const auto pushIfMissing = [&](const std::string& name) {
      if (name.empty()) {
        return;
      }
      for (const auto& existing : materialNames) {
        if (existing == name) {
          return;
        }
      }
      materialNames.push_back(name);
    };
    pushIfMissing(cfg.detector.worldMaterial);
    pushIfMissing(cfg.detector.mediumMaterial);
    for (const auto& mat : cfg.materials) {
      pushIfMissing(mat.name);
    }
    for (const auto& volume : cfg.geometry.volumes) {
      pushIfMissing(volume.material);
    }
    auto derived = extractor.deriveAll(materialNames);
    auto* nist = G4NistManager::Instance();
    // Surrogate path: when configured, override scalar fields (mean n, abs,
    // scat) with surrogate predictions for materials whose composition the
    // surrogate accepts.  Spectrum samples remain from the extractor so the
    // viewer / validation report can compare both signals.
    const bool useSurrogate = !cfg.opticsDerive.surrogateModelPath.empty();
    trech::ml::OpticsSurrogate surrogate;
    if (useSurrogate) {
      surrogate.load(cfg.opticsDerive.surrogateModelPath);
    }
    for (auto& result : derived) {
      if (!useSurrogate || !surrogate.loaded() || !result.available) {
        continue;
      }
      G4Material* material = nist->FindOrBuildMaterial(result.materialName);
      if (!material) {
        for (auto* m : *G4Material::GetMaterialTable()) {
          if (m && m->GetName() == result.materialName) {
            material = m;
            break;
          }
        }
      }
      if (!material) {
        continue;
      }
      std::vector<std::pair<std::string, double>> massFractions;
      const auto* elements = material->GetElementVector();
      const auto* fractions = material->GetFractionVector();
      for (std::size_t i = 0; i < material->GetNumberOfElements(); ++i) {
        if (!(*elements)[i]) {
          continue;
        }
        massFractions.emplace_back((*elements)[i]->GetSymbol(), fractions[i]);
      }
      auto composition = trech::ml::OpticsSurrogate::encodeComposition(
          massFractions, result.densityGcm3);
      std::array<float, 3> prediction{};
      if (surrogate.predict(composition, &prediction)) {
        // Shift the whole derived dispersion curve to the surrogate's predicted
        // level so transport actually uses the learned n (RINDEX is built from
        // result.samples), while keeping the f-sum dispersion *shape*. The
        // scalar mean tracks the shift.
        const double nPred = static_cast<double>(prediction[0]);
        const double shift = nPred - result.meanRefractiveIndex;
        for (auto& sample : result.samples) {
          sample.refractiveIndex += shift;
        }
        result.meanRefractiveIndex = nPred;
        // The ridge backend predicts n only and signals abs/scat "not
        // predicted" with a negative sentinel; the TorchScript backend predicts
        // all three. Only override when a real (positive) value is given.
        bool overrodeAbsScat = false;
        if (prediction[1] > 0.0f) {
          result.meanAbsorptionLengthMm = prediction[1];
          overrodeAbsScat = true;
        }
        if (prediction[2] > 0.0f) {
          result.meanScatterLengthMm = prediction[2];
          overrodeAbsScat = true;
        }
        result.note += overrodeAbsScat
                           ? " | surrogate override applied (n curve-shifted, abs, scat)"
                           : " | surrogate override applied (n curve-shifted to learned level)";
      }
    }
    for (const auto& result : derived) {
      if (!result.available || !nist) {
        continue;
      }
      G4Material* material = nist->FindOrBuildMaterial(result.materialName);
      if (!material) {
        const auto& table = *G4Material::GetMaterialTable();
        for (auto* m : table) {
          if (m && m->GetName() == result.materialName) {
            material = m;
            break;
          }
        }
      }
      if (material) {
        trech::sim::MolecularOpticsExtractor::attachToMaterial(material, result);
      }
    }
    if (options.derivedOptics) {
      *options.derivedOptics = std::move(derived);
    } else {
      options.derivedOptics =
          std::make_shared<std::vector<trech::sim::DerivedOpticsResult>>(std::move(derived));
    }
  }

  auto* uiManager = G4UImanager::GetUIpointer();
  if (ui) {
    if (!options.macroPath.empty()) {
      uiManager->ApplyCommand("/control/execute " + options.macroPath);
    } else if (std::filesystem::exists("init_vis.mac")) {
      uiManager->ApplyCommand("/control/execute init_vis.mac");
    }
    ui->SessionStart();
    delete ui;
    delete vis;
  } else if (!options.macroPath.empty()) {
    uiManager->ApplyCommand("/control/execute " + options.macroPath);
  } else {
    uiManager->ApplyCommand("/run/beamOn " + std::to_string(cfg.run.nEvents));
  }

  delete runManager;
  return 0;
}

} // namespace trech
