"""Stable display colors for computed occupied-energy groups, never physical colors."""
import numpy as np
LEVEL_COLORS = np.array([[1.,.53,.16],[.21,.75,1.],[.72,.42,1.],[.24,.86,.58],
                        [1.,.34,.55],[.9,.84,.25],[.48,.72,.8],[.85,.58,.32]],np.float32)


def energy_rgb(components):
    values=np.asarray([c['values'] for c in components],dtype=np.float32)
    colors=LEVEL_COLORS[np.arange(len(components))%len(LEVEL_COLORS)]
    total=values.sum(axis=0)
    mixed=np.einsum('kn,kc->nc',values,colors)/np.maximum(total[:,None],1e-30)
    return mixed,total
