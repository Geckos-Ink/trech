"""Custom material definitions authored in the Inspector.

A custom material is engine config (``materials[]``): a name, a density and components that
are either another material (a Geant4 NIST ``G4_*`` name or a custom material declared
earlier) or a chemical element, by mass ``fraction`` or integer ``atoms``, optionally a pure
isotope (``massNumber``). This module holds the text form the Inspector edits and the checks
Studio can make before export. It never builds a material: Geant4 does that when the exported
scenario runs, and reports any name it cannot resolve in ``geometry_resolution``.

Text form, one component per line::

    element H atoms 2 A 2      # deuterium, stoichiometric
    element O atoms 1
    material G4_WATER fraction 0.9
    element Na fraction 0.04

Mass fractions are renormalised by the engine over the components it resolves, so they need
not sum to one. A material that uses ``atoms`` must use it on every component, and every
component must then be an element (the engine refuses a mixed material).
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence

# Symbols Z = 1..118 in order (Geant4's NIST element builder accepts exactly these).
_ORDER = ("H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge "
          "As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm "
          "Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U "
          "Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og").split()
ELEMENT_Z = {symbol: z for z, symbol in enumerate(_ORDER, start=1)}
ELEMENT_SYMBOLS = frozenset(ELEMENT_Z)

_AMOUNT_KEYS = {"fraction": "fraction", "atoms": "atoms", "a": "massNumber", "mass": "massNumber"}


def project_components(components: Iterable[Dict]) -> List[Dict]:
    """The ``{material, fraction}`` view older viz scenes record for each component."""
    return [{"material": str(c.get("material") or ""), "fraction": float(c.get("fraction") or 0.0)}
            for c in components]


def format_components(components: Sequence[Dict]) -> str:
    """Render config components in the Inspector's one-per-line text form."""
    lines = []
    for c in components:
        if c.get("element"):
            line = f"element {c['element']}"
        else:
            line = f"material {c.get('material', '')}"
        if int(c.get("atoms") or 0) > 0:
            line += f" atoms {int(c['atoms'])}"
        else:
            line += f" fraction {float(c.get('fraction') or 0.0)!r}"
        if int(c.get("massNumber") or 0) > 0:
            line += f" A {int(c['massNumber'])}"
        lines.append(line)
    return "\n".join(lines)


def _positive_int(token: str, label: str) -> int:
    try:
        value = int(token)
    except ValueError:
        raise ValueError(f"{label} must be a positive integer (got {token!r})") from None
    if value <= 0 or str(value) != token.lstrip("+"):
        raise ValueError(f"{label} must be a positive integer (got {token!r})")
    return value


def parse_components(text: str) -> List[Dict]:
    """Parse the text form into config components (``material``/``element`` + amount)."""
    components: List[Dict] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        tokens = line.split()
        where = f"component line {number}"
        if len(tokens) < 4 or len(tokens) % 2:
            raise ValueError(f"{where}: write 'element <symbol>' or 'material <name>', then "
                             "'fraction <x>' or 'atoms <n>', optionally 'A <mass number>'")
        kind, name = tokens[0].lower(), tokens[1]
        if kind not in ("element", "material"):
            raise ValueError(f"{where}: starts with 'element' or 'material', not {tokens[0]!r}")
        component: Dict = {kind: name}
        for key, value in zip(tokens[2::2], tokens[3::2]):
            field = _AMOUNT_KEYS.get(key.lower())
            if field is None:
                raise ValueError(f"{where}: unknown key {key!r} (use fraction, atoms or A)")
            if field in component:
                raise ValueError(f"{where}: {key} given twice")
            if field == "fraction":
                try:
                    component[field] = float(value)
                except ValueError:
                    raise ValueError(f"{where}: fraction must be a number (got {value!r})") from None
            else:
                component[field] = _positive_int(value, f"{where}: {key}")
        components.append(component)
    return components


def validate_material(name: str, density_gcm3: float, components: Sequence[Dict], *,
                      earlier: Iterable[str] = (), new: bool = False) -> None:
    """Refuse a custom material the engine would skip, half-build or reject.

    ``earlier`` names the custom materials declared before this one: the engine resolves a
    material component against those first, then against Geant4's NIST table. A name that is
    neither ``G4_*`` nor an earlier custom material is refused here; a ``G4_*`` name Geant4
    does not ship is reported by the engine run (it drops the component with a warning).
    """
    if not name or name != name.strip() or any(ch.isspace() for ch in name):
        raise ValueError("Material names must be nonempty and contain no spaces")
    if new and name.lower().startswith("g4_"):
        raise ValueError(f"{name}: the G4_ prefix is Geant4's NIST namespace; pick another name")
    if isinstance(density_gcm3, bool) or not isinstance(density_gcm3, (int, float)) \
            or not math.isfinite(density_gcm3) or density_gcm3 <= 0:
        raise ValueError(f"{name}: density must be a positive finite number (g/cm³); "
                         "the engine skips a material without one")
    if not components:
        raise ValueError(f"{name}: a custom material needs at least one component")
    known = {n.lower() for n in earlier}
    stoichiometric = any(int(c.get("atoms") or 0) > 0 for c in components)
    for i, c in enumerate(components, start=1):
        where = f"{name} component {i}"
        element, material = c.get("element"), c.get("material")
        if bool(element) == bool(material):
            raise ValueError(f"{where}: name exactly one element or material")
        fraction, atoms = c.get("fraction"), int(c.get("atoms") or 0)
        if (fraction is not None and float(fraction) != 0.0) and atoms:
            raise ValueError(f"{where}: give fraction or atoms, not both")
        if stoichiometric:
            if atoms <= 0:
                raise ValueError(f"{where}: a material that uses atoms must use them on every component")
            if not element:
                raise ValueError(f"{where}: stoichiometric components must be elements")
        else:
            if fraction is None or isinstance(fraction, bool) or not math.isfinite(float(fraction)) \
                    or float(fraction) <= 0:
                raise ValueError(f"{where}: fraction must be a positive finite number")
        if c.get("massNumber") is not None and not element:
            raise ValueError(f"{where}: a mass number (A) selects an isotope of an element")
        if element:
            if element not in ELEMENT_SYMBOLS:
                raise ValueError(f"{where}: {element!r} is not an element symbol")
            mass_number = int(c.get("massNumber") or 0)
            if mass_number and mass_number < ELEMENT_Z[element]:
                raise ValueError(f"{where}: A={mass_number} is below Z={ELEMENT_Z[element]} for {element}")
        else:
            key = str(material).lower()
            if key == name.lower():
                raise ValueError(f"{where}: a material cannot contain itself")
            if key not in known and not key.startswith("g4_"):
                raise ValueError(f"{where}: {material!r} is neither a Geant4 G4_* material nor a "
                                 "custom material declared before this one")


def material_references(name: str, *, world: str, medium: Optional[str], volumes: Iterable,
                        materials: Iterable) -> List[str]:
    """Where ``name`` is used: the world, the medium box, volumes or another material's components."""
    key = name.lower()
    uses = []
    if world.lower() == key:
        uses.append("the world")
    if medium and medium.lower() == key:
        uses.append("the medium box")
    uses.extend(f"volume {v.name}" for v in volumes if v.material.lower() == key)
    for m in materials:
        if m.name.lower() != key and any(str(c.get("material") or "").lower() == key
                                         for c in m.components):
            uses.append(f"material {m.name}")
    return uses

