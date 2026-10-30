"""Held recorded triangles; face normals are representation, never inferred growth."""
import numpy as np
from .mesh import MeshData
from .playback import _to_yup


def interface_mesh(raw, up_axis):
    vertices = np.asarray(raw['vertices'], dtype=np.float64)
    triangles = np.asarray(raw['triangles'])
    if (vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) > 200000
            or not np.all(np.isfinite(vertices)) or triangles.ndim != 2 or triangles.shape[1] != 3
            or not np.issubdtype(triangles.dtype, np.integer) or len(triangles) > 400000
            or np.any(triangles < 0) or np.any(triangles >= len(vertices))):
        raise ValueError('Invalid recorded interface mesh')
    if raw.get('inspection', {}).get('format_validated') is not True:
        raise ValueError('Interface recording has not passed engine inspection')
    points = _to_yup(vertices, up_axis)[triangles].reshape(-1,3,3)
    normals = np.cross(points[:,1]-points[:,0],points[:,2]-points[:,0])
    lengths = np.linalg.norm(normals,axis=1)
    if np.any(lengths <= 0) or not np.all(np.isfinite(lengths)):
        raise ValueError('Degenerate recorded interface')
    normals /= lengths[:,None]
    return MeshData(np.concatenate((points.reshape(-1,3), np.repeat(normals,3,axis=0)),axis=1).astype(np.float32),
                    np.arange(points.size//3,dtype=np.uint32))
