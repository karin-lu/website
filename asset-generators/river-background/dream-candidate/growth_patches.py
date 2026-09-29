"""Deterministic, geometry-fitted growth sites shared by v5 plants and moss."""
import hashlib
import math
import random

from mathutils import Vector
from mathutils.bvhtree import BVHTree


def growth_sites(rock, distance, far=False):
    points = [rock.matrix_world @ v.co for v in rock.data.vertices]
    rock.data.calc_loop_triangles()
    bvh = BVHTree.FromPolygons(points, [tuple(t.vertices) for t in rock.data.loop_triangles], all_triangles=True)
    lo = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    scale = (distance + (lo.y + hi.y) / 2) / distance
    seed = int(hashlib.sha256(str(rock.get('river_id', rock.name)).encode()).hexdigest()[:8], 16)
    rng = random.Random(seed + 421)
    moisture = max(0., min(1., float(rock.get('river_moisture', .55))))
    ceiling = rock.get('river_attachment') == 'ceiling' or 'ceiling' in rock.name
    # Sample the actual visible contour; dry and narrow ledges often stay bare.
    candidates = []
    for i in range(64):
        x = lo.x + (hi.x - lo.x) * ((i + rng.random()) / 64)
        start, direction = (lo.z, 1) if ceiling else (hi.z, -1)
        for step in range(160):
            z = start + direction * (hi.z - lo.z) * step / 159
            hit, normal, _, _ = bvh.ray_cast(Vector((x, lo.y - 2, z)), Vector((0, 1, 0)), hi.y - lo.y + 4)
            if hit is None:
                continue
            # On floors, require an actual upward ledge just behind the lip.
            shelf, n, _, _ = bvh.ray_cast(Vector((x, hit.y + scale * .06, hi.z + 1)), Vector((0, 0, -1)))
            if ceiling or (shelf is not None and n.z > .48 and abs(shelf.z-hit.z) < scale*.30):
                candidates.append(hit)
            break
    rng.shuffle(candidates)
    budget = min(3 if far else 8, max(0, round((hi.x-lo.x)/scale * moisture * (.70 if far else 1.40))))
    sites = []
    for hit in candidates:
        radius = scale * rng.uniform(.24, .42) * (.75 + moisture*.45)
        if any(abs(hit.x-p['root'][0]) < (radius+p['radius'])*.85 for p in sites):
            continue
        if len(sites) >= budget:
            break
        sites.append({'root': list(hit), 'radius': radius, 'moisture': moisture,
                      'ceiling': ceiling, 'phase': rng.uniform(0, math.tau),
                      'style': rng.choice(('tuft', 'sparse', 'cascade')),
                      'spill': ceiling or rng.random() < .30 + moisture*.55})
    return sites


def patch_weight(x, y, sites):
    """Irregular elliptical growth masks, with exposed stone between sites."""
    weight = 0.
    for site in sites:
        if site['ceiling']:
            continue
        dx = (x-site['root'][0])/site['radius']
        dy = (y-site['root'][1])/(site['radius']*.80)
        angle = math.atan2(dy, dx)
        edge = 1 + .15*math.sin(angle*3+site['phase']) + .09*math.sin(angle*7-site['phase'])
        weight = max(weight, edge-math.hypot(dx, dy))
    return weight
