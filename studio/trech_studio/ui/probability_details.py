"""Readable engine-emitted quantum states and nuclear distributions; no physics solver."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QTableWidget, QTableWidgetItem, QAbstractItemView


class RadialPlot(QWidget):
    def __init__(self):
        super().__init__()
        self.distribution = None
        self.setMinimumHeight(130)
        self.setMaximumHeight(180)

    def paintEvent(self, _event):
        if not self.distribution:
            return
        d = self.distribution
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#151e2c'))
        p.setPen(QColor('#d9e3f1'))
        p.drawText(12, 20, 'Radial counts across recorded configurations')
        protons, neutrons = d['proton_counts'], d['neutron_counts']
        maximum = max(protons+neutrons+[1])
        width = (self.width()-32)/len(protons)
        height = self.height()-62
        for i, (a, b) in enumerate(zip(protons, neutrons)):
            for offset, count, color in ((0, a, '#ff7666'), (.44, b, '#65b1ff')):
                h = height*count/maximum
                p.fillRect(int(16+(i+offset)*width), int(30+height-h), max(1, int(width*.4)), int(h), QColor(color))
        p.setPen(QColor('#d9e3f1'))
        p.drawText(12, self.height()-10, '0')
        p.drawText(self.width()-48, self.height()-10, f'≥{(len(protons)-1)*d["bin_width_fm"]:g}')
        p.drawText(44, self.height()-10, 'Distance from nucleon centroid (fm)')
        p.end()


class ProbabilityDetails(QWidget):
    view_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self._playback = None
        layout = QVBoxLayout(self)
        self.summary = QLabel('Load a chemistry probability run to inspect its states and particle inventory.')
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.summary)
        self.plot = RadialPlot()
        layout.addWidget(self.plot)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['State', 'Energy (Eh)', 'Occupation', '3D field'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setColumnWidth(0, 90)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 95)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellClicked.connect(self._select_state)
        layout.addWidget(self.table, 1)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self._field_ids = []
        self.plot.hide()

    def _select_state(self, row, _column):
        field_id = self._field_ids[row]
        if field_id:
            self.view_requested.emit('density:'+field_id)

    def set_playback(self, playback):
        self._playback = playback
        if playback and playback.frames:
            self.set_cursor(playback.t_max)
        else:
            self.table.setRowCount(0)
            self._field_ids = []
            self.plot.distribution = None
            self.plot.hide()
            self.summary.setText('No chemistry probability diagnostics in this playback.')
            self.note.clear()

    def set_cursor(self, cursor):
        pb = self._playback
        if not pb or not pb.frames:
            return
        frame = pb.frames[pb.frame_index_at(cursor)]
        d = frame.details or {}
        self.plot.distribution = None
        self.plot.hide()
        self.table.setRowCount(0)
        self._field_ids = []
        if d.get('kind') == 'nuclear':
            z, a = d['z'], d['a']
            stats = d.get('statistics')
            text = f'ONE {d["element"]}-{a} nucleus\n{z} protons (red) + {a-z} neutrons (blue) = {a} nucleons\nConfiguration {d["configuration"]}/{d["configuration_count"]} · showing {d["component"]}'
            if stats:
                for species in ('protons', 'neutrons'):
                    rms = stats[species]['rms_radius_fm']
                    if rms is not None:
                        text += f'\n{species.capitalize()} RMS distance: {rms:.3f} fm'
            self.summary.setText(text)
            self.plot.distribution = d.get('radial_distribution')
            self.plot.setVisible(bool(self.plot.distribution))
            self.plot.update()
            self.note.setText('Geant4 nuclear initial-state model. Each configuration samples ONE nucleus independently. Red = protons; blue = neutrons. Grey circles mark this sample’s extent; glyph radii are display choices. Nuclear shell occupations and time evolution are unavailable.')
            self.table.hide()
            return
        self.table.show()
        inventory = d.get('particle_inventory') or {}
        electronic = d.get('electronic_structure') or {}
        text = ''
        if inventory:
            neutrons = inventory.get('neutrons')
            text = f'{inventory["electrons"]} electrons · {inventory["protons"]} protons · {neutrons if neutrons is not None else "unresolved natural-isotope"} neutrons'
        if electronic:
            text += f'\nIndependent {electronic["source"]["method"]}\nTotal energy: {electronic["total_energy_hartree"]:.8f} Eh'
            if electronic.get('dipole_debye'):
                text += '\nDipole (D): '+', '.join(f'{x:.4f}' for x in electronic['dipole_debye'])
            rows = electronic['orbitals']
            self.table.setRowCount(len(rows))
            occupied = sorted((o for o in rows if o['occupation'] > 0), key=lambda o: o['energy_hartree'])
            virtual = sorted((o for o in rows if o['occupation'] == 0), key=lambda o: o['energy_hartree'])
            for i, o in enumerate(rows):
                label = f'MO {o["index"]}'
                if occupied and o['index'] == occupied[-1]['index']: label += ' HOMO'
                if virtual and o['index'] == virtual[0]['index']: label += ' LUMO'
                self._field_ids.append(o.get('field_id'))
                for j, value in enumerate((label, f'{o["energy_hartree"]:.6f}',
                        f'{o["occupation"]:g} e '+('↑↓' if o['occupation'] == 2 else ''), 'View →' if o.get('field_id') else 'not recorded')):
                    cell = QTableWidgetItem(value)
                    if o.get('field_id'):
                        cell.setForeground(QColor('#b69cff') if o['occupation'] else QColor('#ffc477'))
                    self.table.setItem(i, j, cell)
        selected = d.get('selected_field') or {}
        if selected.get('orbital'):
            text += f'\nSelected MO {selected["orbital"]["index"]} · probability |ψ|²'
        elif selected:
            text += '\nTotal density combines the occupied states.'
        self.summary.setText(text or 'This older run has no state spectrum or particle inventory. Re-run with orbital output.')
        self.note.setText('Click a recorded state to view its lobes and nodes. Energies are discrete; positions have continuous probability. Molecular orbitals share several nuclei and have no circular trajectories or fixed radial shells. Virtual states are unoccupied. RHF orbital energies are not measured excitation energies.')
