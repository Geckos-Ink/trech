#include "trech/sim/GeantRunner.hpp"
#include "trech/chem/DnaChemistry.hpp"
#include "trech/sim/MultiscaleBridge.hpp"
#include "trech/sim/ActionInitialization.hpp"
#include "trech/sim/DetectorConstruction.hpp"

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

  runManager->SetUserInitialization(new TrechDetectorConstruction(cfg.detector, cfg.optics));

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

  runManager->SetUserInitialization(new TrechActionInitialization(cfg, options));

  G4UIExecutive* ui = options.enableUi ? new G4UIExecutive(argc, argv) : nullptr;
  G4VisManager* vis = nullptr;

  if (ui) {
    vis = new G4VisExecutive();
    vis->Initialize();
  }

  runManager->Initialize();

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
