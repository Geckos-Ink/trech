#include "trech/sim/GeantRunner.hpp"
#include "trech/chem/DnaChemistry.hpp"
#include "trech/sim/ActionInitialization.hpp"
#include "trech/sim/DetectorConstruction.hpp"

#include "G4PhysListFactory.hh"
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
  if (cfg.optics.enable) {
    phys->RegisterPhysics(new G4OpticalPhysics());
    options.physicsList = physicsListName + "+Optical";
  } else {
    options.physicsList = physicsListName;
  }

  if (cfg.chemistry.enable) {
    trech::chem::DnaChemistryBridge chemistry(cfg.chemistry);
    const auto status = chemistry.Configure();
    (void)status;
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
