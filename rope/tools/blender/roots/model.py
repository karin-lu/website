"""Authored inputs and reproducible settings; no Blender dependency."""
import hashlib
import numpy as np


def stable_seed(text):
    return int.from_bytes(hashlib.sha256(str(text).encode()).digest()[:8], 'little')


DEFAULTS = dict(depth=.38, taper=.65, age=.65, bark_strength=.7,
                rootlet_density=.25, quality='PREVIEW', seed='roots')


def validate(roots):
    from .surface import cross, crossing
    if not roots: raise ValueError('Select at least one closed root outline')
    ids = set()
    for r in roots:
        if not r['id'] or r['id'] in ids: raise ValueError('Root outline names must be unique')
        ids.add(r['id'])
        p = np.asarray(r['polygon'],float)
        if p.ndim != 2 or p.shape[1] != 2 or len(p)<3 or not np.isfinite(p).all():
            raise ValueError('Root outline needs at least three finite points')
        if np.any(np.linalg.norm(np.roll(p,-1,axis=0)-p,axis=1)<1e-8):
            raise ValueError('Root outline has duplicate neighboring points')
        area = sum(cross(a,b) for a,b in zip(p,np.roll(p,-1,axis=0)))/2
        if abs(area)<1e-8: raise ValueError('Root outline has no area')
        for i in range(len(p)):
            for j in range(i+1,len(p)):
                if j == i+1 or (i == 0 and j == len(p)-1): continue
                a,b,c,d = p[i],p[(i+1)%len(p)],p[j],p[(j+1)%len(p)]
                if crossing(a,b,c,d) is not None:
                    raise ValueError('Root outline crosses or touches itself')
                # Parallel overlaps are not detected by crossing().
                if abs(cross(b-a,c-a))<1e-10 and abs(cross(b-a,d-a))<1e-10:
                    axis = int(np.argmax(np.abs(b-a)))
                    if max(min(a[axis],b[axis]),min(c[axis],d[axis])) <= min(max(a[axis],b[axis]),max(c[axis],d[axis])):
                        raise ValueError('Root outline has overlapping edges')
        depth = float(r.get('depth',DEFAULTS['depth']))
        if not .02 <= depth <= 5: raise ValueError('Root depth must be between .02 and 5 metres')
        if any(not isinstance(e,int) or not 0<=e<len(p) for e in r.get('grab_edges',[])):
            raise ValueError('Invalid playable edge index')
    return roots
