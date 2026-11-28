#!/usr/bin/env python3
"""The brain MRI driver's spin-warp acquisition encodes space through its gradients.

scripts/run_magnetic_resonance_brain.py acquires k-space as explicit voxel sums under a readout
gradient and stepped phase-encode gradients, then reconstructs with an inverse FFT on the grid
the protocol implies. These checks need only numpy (no Geant4 run):

- the protocol's gradients and dwell give the requested FOV (gamma_bar Gx dwell FOV = 1);
- a point source reconstructs on its own pixel, in 2D and 3D, at any position;
- with no decay or noise, an object on the scanner grid acquires exactly its 2D FFT;
- gradients 3% weak shrink the reconstructed geometry by 3%;
- block_mean and scanner_axis put each scanner pixel at the centre of its oversampled cells.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_magnetic_resonance_brain as mr  # noqa: E402

QUIET = dict(mr.PROTOCOL, noise_fraction=0.0, readout_decay_ms=1e12)


class AcquisitionTests(unittest.TestCase):
    def test_fov_from_gradients(self):
        enc = mr.encoding(240, 180.0)
        fov = 1.0 / (mr.GAMMA_BAR_HZ_PER_T * enc["gx_t_per_m"] * enc["dwell_s"])
        self.assertAlmostEqual(fov * 1e3, 180.0, places=9)
        fov_pe = 1.0 / (mr.GAMMA_BAR_HZ_PER_T * enc["phase_step_t_per_m"] * enc["tau_s"])
        self.assertAlmostEqual(fov_pe * 1e3, 180.0, places=9)
        # A realistic clinical readout gradient (mT/m) for 62.5 kHz over 180 mm.
        self.assertTrue(5.0 < enc["gx_t_per_m"] * 1e3 < 15.0)

    def test_point_source_lands_on_its_pixel(self):
        n, fov = 32, 64.0
        for (iy, ix) in ((16, 16), (3, 27), (30, 1)):
            rho = np.zeros((n, n))
            rho[iy, ix] = 1.0
            recon = mr.reconstruct(mr.acquire(rho, fov, n, QUIET))
            self.assertEqual(np.unravel_index(recon.argmax(), recon.shape), (iy, ix))
        rho3 = np.zeros((16, 16, 16))
        rho3[4, 11, 7] = 1.0
        recon3 = mr.reconstruct(mr.acquire(rho3, 32.0, 16, QUIET))
        self.assertEqual(np.unravel_index(recon3.argmax(), recon3.shape), (4, 11, 7))

    def test_on_grid_object_acquires_its_fft(self):
        n = 24
        rng = np.random.default_rng(3)
        rho = rng.random((n, n))
        k = mr.acquire(rho, 48.0, n, QUIET)
        # Scanner pixel j sits at (j - n/2) * fov/n and k index p at (p - n/2) / fov.
        reference = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(rho)))
        self.assertLess(np.abs(k - reference).max(), 1e-9 * np.abs(reference).max())

    def test_miscalibrated_gradients_rescale_geometry(self):
        n, fov, over = 120, 180.0, 2
        axis = mr.scanner_axis(n, fov)
        fine = mr.build_phantom(n, fov, axis=mr.scanner_axis(n, fov, over))
        rho = (fine != mr.LAB["air"]).astype(float)
        level = 0.5
        nominal = mr.head_semi_axes(mr.reconstruct(mr.acquire(rho, fov, n, QUIET)), axis, level)
        weak = mr.head_semi_axes(
            mr.reconstruct(mr.acquire(rho, fov, n, QUIET, gradient_scale=0.97)), axis, level)
        for a, truth in (("x", 72.0), ("y", 88.0)):
            self.assertLess(abs(nominal[a] - truth), 0.5 * fov / n)
            # Weak gradients reach less k-space per sample: the object reconstructs smaller.
            self.assertAlmostEqual(weak[a] / nominal[a], 0.97, delta=0.004)

    def test_grids_are_centred(self):
        axis = mr.scanner_axis(8, 16.0)
        self.assertEqual(list(axis), [-8.0, -6.0, -4.0, -2.0, 0.0, 2.0, 4.0, 6.0])
        fine = mr.scanner_axis(8, 16.0, 4)
        np.testing.assert_allclose(fine.reshape(8, 4).mean(axis=1), axis)
        block = mr.block_mean(np.arange(16.0).reshape(4, 4), 2)
        np.testing.assert_allclose(block, [[2.5, 4.5], [10.5, 12.5]])


if __name__ == "__main__":
    unittest.main()
