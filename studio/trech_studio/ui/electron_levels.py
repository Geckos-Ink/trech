"""Recorded occupied-energy contributions through a nucleus and spherical radial measure."""
import numpy as np
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QSlider,QCheckBox,QScrollArea
from ..render.energy_palette import LEVEL_COLORS


class LevelProfilePlot(QWidget):
    def __init__(self):
        super().__init__()
        self.profile=None
        self.radial=False
        self.axis=0
        self.span=1.2
        self.logarithmic=True
        self.setMinimumHeight(260)
        self.setMouseTracking(True)
        self._plot=None

    def paintEvent(self,_event):
        p=QPainter(self)
        p.fillRect(self.rect(),QColor('#0c1322'))
        if not self.profile:
            p.setPen(QColor('#dbe6f4'))
            p.drawText(12,25,'No orbital-resolved profile recorded. Calculate or open the atomic reference.')
            return
        source=self.profile
        x=np.asarray(source['radii_angstrom'] if self.radial else source['diameter_angstrom'])
        curves=[np.asarray(g['radial_probability_per_angstrom'] if self.radial else g['diameter_density_per_angstrom3'][self.axis]) for g in source['levels']]
        total=np.asarray(source['total_radial_probability_per_angstrom'] if self.radial else source['total_diameter_density_per_angstrom3'][self.axis])
        low=0 if self.radial else -self.span
        high=self.span
        visible=(x>=low)&(x<=high)
        maximum=max(float(total[visible].max()),1e-30)
        floor=maximum*1e-7
        y_min,y_max=(np.log10(floor),np.log10(maximum)*1.+.05) if self.logarithmic else (0,maximum*1.06)
        rect=QRectF(62,30,max(1,self.width()-82),max(1,self.height()-80))
        self._plot=(rect,x,curves,total,low,high)
        p.setRenderHint(QPainter.Antialiasing,True)
        p.setPen(QColor('#4b607a'))
        for j in range(5):
            y=rect.bottom()-rect.height()*j/4
            p.drawLine(int(rect.left()),int(y),int(rect.right()),int(y))
            value=y_min+(y_max-y_min)*j/4
            label=f'{10**value:.2g}' if self.logarithmic else f'{value:.2g}'
            p.setPen(QColor('#c9d8e9'))
            p.drawText(3,int(y+4),label)
            p.setPen(QColor('#4b607a'))
        for index,values in enumerate(curves+[total]):
            color=QColor('#ffffff') if index==len(curves) else QColor.fromRgbF(*[float(c) for c in LEVEL_COLORS[index%len(LEVEL_COLORS)]])
            p.setPen(QPen(color,2 if index<len(curves) else 1,Qt.SolidLine if index<len(curves) else Qt.DashLine))
            ys=np.log10(np.maximum(values,floor)) if self.logarithmic else values
            path=QPainterPath()
            active=False
            for vx,vy in zip(x,ys):
                if not low<=vx<=high: continue
                px=rect.left()+(vx-low)/(high-low)*rect.width()
                py=rect.bottom()-(vy-y_min)/(y_max-y_min)*rect.height()
                if not active: path.moveTo(px,py);active=True
                else: path.lineTo(px,py)
            p.drawPath(path)
        p.setPen(QColor('#e2ecf8'))
        p.drawText(12,19,'Radial electrons per Å' if self.radial else 'Density through nucleus (electrons / Å³)')
        p.drawText(int(rect.left()),self.height()-26,f'{low:g} Å')
        p.drawText(int(rect.right()-45),self.height()-26,f'{high:g} Å')
        if not self.radial:
            centre=rect.left()+rect.width()/2
            p.setPen(QPen(QColor('#9baec5'),1,Qt.DotLine))
            p.drawLine(int(centre),int(rect.top()),int(centre),int(rect.bottom()))
        p.setPen(QColor('#dbe6f4'))
        p.drawText(int(rect.left()),self.height()-7,'Radius from nucleus' if self.radial else f'{"XYZ"[self.axis]} coordinate relative to nucleus · white dashed = total')
        p.end()

    def mouseMoveEvent(self,event):
        if self._plot is None:return
        rect,x,curves,total,low,high=self._plot
        if not rect.contains(event.position()):return
        value=low+(event.position().x()-rect.left())/rect.width()*(high-low)
        i=int(np.abs(x-value).argmin())
        self.setToolTip(f'Recorded coordinate {x[i]:.6g} Å\nTotal {total[i]:.6g}\n'+'\n'.join(f'Level {j+1}: {y[i]:.6g}' for j,y in enumerate(curves)))


class ElectronLevels(QWidget):
    def __init__(self):
        super().__init__()
        self._playback=None
        self._profiles=[]
        self._key=None
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.title=QLabel('Computed occupied states resolve core and valence density; no fixed shell radii.')
        self.title.setWordWrap(True)
        layout.addWidget(self.title)
        self.centre=QComboBox()
        layout.addWidget(self.centre)
        self.kind=QComboBox()
        self.kind.addItem('Diameter: density contributions through the nucleus',False)
        self.kind.addItem('Radius: spherical probability / electron distribution',True)
        layout.addWidget(self.kind)
        row=QHBoxLayout()
        self.axis=QComboBox();self.axis.addItems(['X','Y','Z'])
        row.addWidget(self.axis)
        row.addWidget(QLabel('Span (0.1–4 Å)'))
        self.span=QSlider(Qt.Horizontal);self.span.setRange(1,40);self.span.setValue(12)
        row.addWidget(self.span,1)
        self.log=QCheckBox('Log density');self.log.setChecked(True)
        row.addWidget(self.log)
        layout.addLayout(row)
        self.plot=LevelProfilePlot()
        layout.addWidget(self.plot,1)
        self.legend=QLabel();self.legend.setWordWrap(True)
        layout.addWidget(self.legend)
        self.note=QLabel('Diameter density and radial probability are different observables. The radial plot includes the spherical volume measure. Molecular profiles include the joint wavefunction, not atom-owned electrons.')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.centre.currentIndexChanged.connect(self._refresh)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.axis.currentIndexChanged.connect(self._refresh)
        self.span.valueChanged.connect(self._refresh)
        self.log.toggled.connect(self._refresh)

    def _kind_changed(self):
        self.log.setChecked(not bool(self.kind.currentData()))
        self._refresh()

    def set_playback(self,playback):
        self._playback=playback
        if playback and playback.frames:self.set_cursor(playback.t_max)
        else:self._profiles=[];self._refresh()

    def set_cursor(self,cursor):
        if not self._playback or not self._playback.frames:return
        frame=self._playback.frames[self._playback.frame_index_at(cursor)]
        electronic=(frame.details or {}).get('electronic_structure') or {}
        profiles=electronic.get('radial_profiles',[])
        self._profiles=profiles
        old=self.centre.currentData()
        self.centre.blockSignals(True);self.centre.clear()
        for i,p in enumerate(profiles):self.centre.addItem(f'{p["owner_id"]} · atom {p["atom_index"]}: {p["element"]}',i)
        if old is not None:self.centre.setCurrentIndex(min(old,len(profiles)-1))
        self.centre.blockSignals(False)
        self._refresh()

    def _refresh(self):
        index=self.centre.currentData()
        profile=self._profiles[index] if index is not None and index<len(self._profiles) else None
        self.plot.profile=profile
        self.plot.radial=bool(self.kind.currentData())
        self.plot.axis=self.axis.currentIndex()
        self.plot.span=self.span.value()/10
        self.plot.logarithmic=self.log.isChecked()
        self.plot.update()
        if not profile:
            self.legend.setText('Profiles were not recorded for this playback. Recalculate the quantum reference to obtain occupied-energy contributions.')
            return
        lines=[]
        for i,g in enumerate(profile['levels']):
            color=QColor.fromRgbF(*[float(c) for c in LEVEL_COLORS[i%len(LEVEL_COLORS)]])
            label=f'Level {i+1}: {g["energy_hartree"]:.5f} Eh · {g["occupation"]:g} e · MO '+','.join(str(x) for x in g['orbital_indices'])
            lines.append(f'<span style="color:{color.name()}">● {label}</span>')
        self.legend.setText('<br>'.join(lines))
        self.title.setText(f'{profile["element"]}: {sum(g["occupation"] for g in profile["levels"]):g} electrons in {len(profile["levels"])} computed occupied-energy groups\nIndependent RHF reference · centre {profile["owner_id"]}:{profile["atom_index"]}')
