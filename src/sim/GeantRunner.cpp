#include "trech/sim/GeantRunner.hpp"
#include "trech/sim/ActionInitialization.hpp"
#include "trech/sim/DetectorConstruction.hpp"

#include "G4PhysListFactory.hh"
#include "G4RunManagerFactory.hh"
#include "G4UIExecutive.hh"
#include "G4UImanager.hh"
#include "G4VisExecutive.hh"
#include "G4VisManager.hh"
#include "G4VModularPhysicsList.hh"
#include "Randomize.hh"

#include <string>

namespace trech {

int runGeant4(const TrechConfig& cfg, int argc, char** argv) {
  CLHEP::HepRandom::setTheSeed(cfg.run.seed);

  auto* runManager = G4RunManagerFactory::CreateRunManager();

  runManager->SetUserInitialization(new TrechDetectorConstruction(cfg.detector));

  G4PhysListFactory factory;
  G4VModularPhysicsList* phys = factory.GetReferencePhysList("QBBC");
  runManager->SetUserInitialization(phys);

  runManager->SetUserInitialization(new TrechActionInitialization(cfg));

  G4UIExecutive* ui = (argc == 1) ? new G4UIExecutive(argc, argv) : nullptr;
  G4VisManager* vis = nullptr;

  if (ui) {
    vis = new G4VisExecutive();
    vis->Initialize();
  }

  runManager->Initialize();

  auto* uiManager = G4UImanager::GetUIpointer();
  if (ui) {
    uiManager->ApplyCommand("/control/execute init_vis.mac");
    ui->SessionStart();
    delete ui;
    delete vis;
  } else {
    uiManager->ApplyCommand("/run/beamOn " + std::to_string(cfg.run.nEvents));
  }

  delete runManager;
  return 0;
}

} // namespace trech
