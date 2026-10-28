"""Interactive inspection of recorded fields. Transform controls are representation only."""
from dataclasses import replace
import numpy as np
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QImage, QPen
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QComboBox, QSlider, QScrollArea, QCheckBox
from ..render.density import DensityDisplay, transfer_range, density_colors, slice_data, mass_level
from ..render.energy_palette import energy_rgb, LEVEL_COLORS


class FieldSlice(QWidget):
    def __init__(self):
        super().__init__()
        self.density = None
        self.display = DensityDisplay()
        self.setMinimumHeight(330)
        self.setMaximumHeight(420)
        self.setMouseTracking(True)
        self._rect = None
        self._slice = None

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#0c1322'))
        if self.density is None:
            p.setPen(QColor('#c8d6e7'))
            p.drawText(15,30,'Select an emitted scalar field.')
            return
        d, display = self.density, self.display
        phase = display.mode == 'phase' and d.amplitude is not None
        shown = replace(d, values=d.amplitude) if phase else d
        values, axes, index, coordinate = slice_data(shown, display)
        low, high = transfer_range(shown, display)
        signed = phase or d.quantity == 'density_difference'
        rgb, intensity = density_colors(values,low,high,signed)
        energy_mode=display.mode == 'levels' and d.energy_components
        if energy_mode:
            mixed,_=energy_rgb(d.energy_components)
            full=mixed.reshape((*d.values.shape,3))
            rgb=np.take(full,index,axis=display.axis)*intensity[...,None]**.35
        pixels = np.ascontiguousarray(np.clip(rgb.transpose(1,0,2)[::-1]*255,0,255).astype(np.uint8))
        image = QImage(pixels.data,pixels.shape[1],pixels.shape[0],pixels.strides[0],QImage.Format_RGB888).copy()
        available = QRectF(46,36,max(10,self.width()-64),max(10,self.height()-120))
        ratio = values.shape[0]/values.shape[1]
        width = min(available.width(),available.height()*ratio)
        height = width/ratio
        rect = QRectF(available.x()+(available.width()-width)/2,available.y()+(available.height()-height)/2,width,height)
        self._rect, self._slice = rect, (values,axes,index)
        p.setRenderHint(QPainter.SmoothPixmapTransform,True)
        p.drawImage(rect,image)
        p.setPen(QColor('#92a8bf'))
        p.drawRect(rect)
        # Projected nuclear positions provide molecular context, not field ownership.
        owners=list(dict.fromkeys(a[2] for a in (d.atom_labels or [])))
        for atom_index,(label, position, owner) in enumerate(d.atom_labels or []):
            x = rect.x()+((position[axes[0]]-d.origin[axes[0]])/d.spacing+.5)/values.shape[0]*rect.width()
            y = rect.bottom()-((position[axes[1]]-d.origin[axes[1]])/d.spacing+.5)/values.shape[1]*rect.height()
            if not rect.contains(x,y): continue
            p.setPen(QPen(QColor('#ffffff'),1.5))
            p.drawLine(int(x-4),int(y),int(x+4),int(y))
            p.drawLine(int(x),int(y-4),int(x),int(y+4))
            p.drawText(int(x+6),int(y-6 if atom_index%2==0 else y+15),f'{chr(65+owners.index(owner))}:{label}')
        p.setPen(QColor('#dbe6f4'))
        p.drawText(12,22,f'{"XYZ"[display.axis]} = {coordinate:.3f} Å · recorded slice {index+1}/{d.values.shape[display.axis]}')
        p.drawText(int(rect.x()),int(rect.bottom()+18),f'{"XYZ"[axes[0]]}: {d.origin[axes[0]]:.2f} → {d.origin[axes[0]]+(values.shape[0]-1)*d.spacing:.2f} Å')
        p.drawText(8,int(rect.y()+15),f'{"XYZ"[axes[1]]} ↑')
        p.drawText(12,self.height()-56," · ".join(f'{chr(65+i)} = {owner}' for i,owner in enumerate(owners)))
        y = self.height()-40
        if energy_mode:
            p.setPen(QColor('#dbe6f4'))
            p.drawText(20,y-5,'Occupied-energy contributions (colors blend where states overlap)')
            for i,component in enumerate(d.energy_components):
                x=20+i*(self.width()-40)/len(d.energy_components)
                color=QColor.fromRgbF(*[float(v) for v in LEVEL_COLORS[i%len(LEVEL_COLORS)]])
                p.fillRect(int(x),y,15,10,color)
                p.setPen(color)
                p.drawText(int(x),y+28,f'L{i+1}: {component["occupation"]:g} e')
            p.end()
            return
        # Quantitative logarithmic legend, same palette as the GPU volume.
        count=max(2,self.width()-40)
        if signed:
            half=count//2
            legend_values=np.concatenate((-np.power(10.,np.linspace(high,low,half)),np.power(10.,np.linspace(low,high,count-half))))
        else:
            legend_values=np.power(10.,np.linspace(low,high,count))
        colors,_ = density_colors(legend_values,low,high,signed)
        for i,color in enumerate(colors):
            p.setPen(QColor.fromRgbF(*[float(x) for x in color]))
            p.drawLine(20+i,y,20+i,y+10)
        p.setPen(QColor('#dbe6f4'))
        unit = 'Å^-3/2' if phase else d.density_unit
        legend = f'−{10**high:.3g} ← 0 → +{10**high:.3g} {unit} · log |value|' if signed else f'{10**low:.3g} → {10**high:.3g} {unit} · log scale'
        p.drawText(20,y+28,legend)
        p.end()

    def mouseMoveEvent(self,event):
        if self._rect is None or not self._rect.contains(event.position()): return
        values, axes, index = self._slice
        x=min(values.shape[0]-1,max(0,int((event.position().x()-self._rect.x())/self._rect.width()*values.shape[0])))
        y=min(values.shape[1]-1,max(0,int((self._rect.bottom()-event.position().y())/self._rect.height()*values.shape[1])))
        coords=np.array(self.density.origin,dtype=float)
        coords[axes[0]]+=x*self.density.spacing
        coords[axes[1]]+=y*self.density.spacing
        coords[self.display.axis]+=index*self.density.spacing
        self.setToolTip(f'Recorded cell: ({coords[0]:.4f}, {coords[1]:.4f}, {coords[2]:.4f}) Å\nValue: {values[x,y]:.8g}')


class DensityExplorer(QWidget):
    display_changed = Signal(object)

    def __init__(self):
        super().__init__()
        self._playback = None
        self._density = None
        self._defaulted = False
        self.display = DensityDisplay()
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.title = QLabel('Explore an emitted probability or number-density field.')
        self.title.setWordWrap(True)
        layout.addWidget(self.title)
        self.mode = QComboBox()
        for text,key in [('Occupied energy contributions','levels'),('Volume · density gradients','volume'),('Orbital phase · +ψ / −ψ lobes','phase'),
                         ('Enclosed-grid contours · 10 / 50 / 90%','contours'),('Movable 3D section','slice')]:
            self.mode.addItem(text,key)
        self.mode.setCurrentIndex(1)
        layout.addWidget(self.mode)
        self.overlay = QComboBox()
        self.overlay.addItem('Orbital overlay: none','')
        layout.addWidget(self.overlay)
        self.cutaway = QCheckBox("Cutaway volume through the selected section")
        layout.addWidget(self.cutaway)
        self.cutaway.toggled.connect(self._changed)
        self.mass = self._slider(layout,'Enclosed finite-grid mass (%)',1,99,90)
        self.mass_note = QLabel()
        self.mass_note.setWordWrap(True)
        layout.addWidget(self.mass_note)
        self.decades = self._slider(layout,'Log density window (decades)',2,7,4)
        self.opacity = self._slider(layout,'Display opacity',1,100,60)
        row = QHBoxLayout()
        row.addWidget(QLabel('Section normal'))
        self.axis = QComboBox()
        self.axis.addItems(['X','Y','Z'])
        self.axis.setCurrentIndex(2)
        row.addWidget(self.axis)
        layout.addLayout(row)
        self.section = self._slider(layout,'Section position',0,1000,500)
        self.slice = FieldSlice()
        layout.addWidget(self.slice,1)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        for control in (self.mode,self.overlay,self.mass,self.decades,self.opacity,self.axis,self.section):
            signal=control.currentIndexChanged if isinstance(control,QComboBox) else control.valueChanged
            signal.connect(self._changed)

    def _slider(self, layout, title, low, high, value):
        row=QHBoxLayout()
        row.addWidget(QLabel(title))
        slider=QSlider(Qt.Horizontal)
        slider.setRange(low,high)
        slider.setValue(value)
        row.addWidget(slider,1)
        layout.addLayout(row)
        return slider

    def _changed(self):
        if self.mode.currentData() == "levels" and self.display.mode != "levels":
            self.cutaway.blockSignals(True)
            self.cutaway.setChecked(True)
            self.cutaway.blockSignals(False)
        if self.mode.currentData() == "phase" and self.display.mode != "phase":
            self.axis.blockSignals(True)
            self.axis.setCurrentIndex(1)
            self.axis.blockSignals(False)
        self.display=DensityDisplay(self.mode.currentData(),self.mass.value(),float(self.decades.value()),
                                    self.opacity.value()/100,self.axis.currentIndex(),self.section.value()/1000,self.overlay.currentData() or "",self.cutaway.isChecked())
        self._refresh()
        self.display_changed.emit(self.display)

    def set_playback(self, playback):
        self._playback=playback
        if playback and playback.frames:
            self.set_cursor(playback.t_max)
            if not self._defaulted and self._density and self._density.energy_components:
                self._defaulted=True
                self.mode.setCurrentIndex(0)
        else:
            self._density=None
            self._refresh()

    def set_cursor(self,cursor):
        if self._playback and self._playback.frames:
            frame=self._playback.frames[self._playback.frame_index_at(cursor)]
            self._density=frame.density
            self._selected=(frame.details or {}).get('selected_field') or {}
            self._refresh()

    def _refresh(self):
        d=self._density
        self.slice.density=d
        self.slice.display=self.display
        self.slice.update()
        self.mass.setEnabled(bool(d and (d.statistics or {}).get('mass_levels')))
        if d is None:
            self.title.setText('This view has no scalar grid. Select a density or orbital field.')
            self.overlay.blockSignals(True)
            self.overlay.clear()
            self.overlay.addItem('Orbital overlay: none','')
            self.overlay.setEnabled(False)
            self.overlay.blockSignals(False)
            self.mass_note.clear()
            self.note.clear()
            return
        self.overlay.blockSignals(True)
        self.overlay.clear()
        self.overlay.addItem('Orbital overlay: none','')
        for key, item in (d.overlays or {}).items():
            orbital=item['orbital']
            self.overlay.addItem(f'Overlay MO {orbital["index"]} · {orbital["occupation"]:g} e · {orbital["energy_hartree"]:.5f} Eh',key)
        self.overlay.setCurrentIndex(max(0,self.overlay.findData(self.display.overlay_id)))
        self.overlay.setEnabled(bool(d.overlays))
        self.overlay.blockSignals(False)
        selected=self._selected
        orbital=selected.get('orbital')
        name=f'MO {orbital["index"]} · {orbital["occupation"]:g} electrons · {orbital["energy_hartree"]:.6f} Eh' if orbital else 'Joint-system density'
        if d.energy_components: name='Computed occupied-energy electron density'
        if d.quantity=='density_difference': name='Density redistribution: joint − isolated fragments'
        self.title.setText(name+'\n'+d.source_note)
        level=mass_level(d,self.display.mass_percent)
        if level:
            self.mass_note.setText(f'Target {self.display.mass_percent}% · actual {level["enclosed_fraction"]:.2%} of finite-grid '+
                ('absolute signal' if d.quantity=='density_difference' else 'mass')+f'\nThreshold {level["threshold"]:.5g} {d.density_unit}')
        else: self.mass_note.setText('Enclosed-mass thresholds were not recorded; rerun TRECH for this diagnostic.')
        if self.display.mode=='levels' and d.energy_components:
            self.note.setText('The cutaway exposes inner contributions; it removes no source data. Colors show the calculated occupied-state contributions, weighted by their occupations; they mix where levels overlap in space. Density and state contributions are nonuniform. Open Electron levels for diameter and spherical radial curves with the actual energies. These are solved RHF states, not linearly spaced shells.')
        elif self.display.mode=='levels':
            self.note.setText('Energy decomposition was not recorded for this field; the volume uses the ordinary density gradient. Select the occupied-energy density field or calculate a reference with complete recorded occupied grids.')
        elif d.quantity=='density_difference':
            stats=d.statistics or {}
            self.note.setText('Orange: density increase. Blue: decrease. '+(d.comparison or {}).get('definition','')+
                f'\nIntegrated increase/decrease: {stats.get("positive_integral",float("nan")):.5g} / {stats.get("negative_integral",float("nan")):.5g} e. '+
                'A common field does not establish a shared bond. Fragment-basis differences contribute to this comparison.')
        elif self.display.mode=='phase':
            self.note.setText('Orange +ψ / blue −ψ; the zero between lobes is a node. The global sign is arbitrary and is not electric charge. '+
                ('Signed amplitude was not recorded for this field; the 3D view falls back to a probability contour.' if d.amplitude is None else
                 'Slice shows signed point-sampled amplitude; mass thresholds use the recorded cell-average |ψ|² grid.'))
        else:
            self.note.setText('Move the section to explore the gradient; hover for recorded values. Crosses label projected nuclei. '+
                'Contour percentages describe enclosed finite-grid probability/number density, not extra quantum energy levels. '+
                'Color, interpolation and opacity are display choices. Use the redistribution field to compare the joint system with isolated molecules.')
