"""Open strokes -> a rooted tree with flowing, tapered limbs (NumPy only).

Only endpoints attach to other strokes. A crossing in the middle of two lines
is not a junction. The first point of the first stroke is the growth base.
"""
import numpy as np
from .model import DEFAULTS, stable_seed


def tree(strokes, settings=None):
    settings = dict(DEFAULTS, **(settings or {}))
    paths = []
    for stroke in strokes:
        p = np.asarray(stroke, float)
        if p.ndim != 2 or p.shape[1] != 2 or len(p) < 2 or not np.isfinite(p).all():
            raise ValueError('Each root line needs at least two finite XZ points')
        p = p[np.r_[True, np.linalg.norm(np.diff(p, axis=0), axis=1) > 1e-7]]
        if len(p) < 2:
            raise ValueError('Root line has no length')
        paths.append(p.copy())
    if not paths:
        raise ValueError('Select open root lines')
    thickness = float(settings['depth'])
    if not .02 <= thickness <= 5:
        raise ValueError('Root thickness must be between .02 and 5 metres')
    snap = thickness * .3
    # Project loose endpoints onto other strokes, inserting attachment points.
    cuts = [[[(0., a.copy()), (1., b.copy())] for a, b in zip(p, p[1:])] for p in paths]
    for i, p in enumerate(paths):
        for end in (0, len(p)-1):
            best = None
            for j, q in enumerate(paths):
                if i == j:
                    continue
                for k, (a, b) in enumerate(zip(q, q[1:])):
                    d = b-a
                    t = np.clip((p[end]-a) @ d / (d @ d), 0., 1.)
                    hit = a+t*d
                    distance = np.linalg.norm(hit-p[end])
                    if distance <= snap and (best is None or distance < best[0]):
                        best = (distance, j, k, t, hit)
            if best is not None:
                _, j, k, t, hit = best
                cuts[j][k].append((t, hit.copy()))
                cuts[i][0 if end == 0 else -1][0 if end == 0 else 1] = (0. if end == 0 else 1., hit.copy())
    nodes, edges = [], set()
    def node(point):
        match = next((i for i, p in enumerate(nodes) if np.linalg.norm(p-point) < snap*.08), None)
        if match is None:
            match = len(nodes)
            nodes.append(point.copy())
        return match
    base = None
    for segments in cuts:
        for entries in segments:
            ids = [node(p) for _, p in sorted(entries, key=lambda e: e[0])]
            if base is None:
                base = ids[0]
            for a, b in zip(ids, ids[1:]):
                if a != b:
                    edges.add(tuple(sorted((a, b))))
    nodes = np.asarray(nodes)
    adjacency = [[] for _ in nodes]
    for a, b in sorted(edges):
        adjacency[a].append(b)
        adjacency[b].append(a)
    parents = {base: -1}
    order = [base]
    for a in order:
        for b in adjacency[a]:
            if b == parents[a]:
                continue
            if b in parents:
                raise ValueError('Root lines form a loop; use a branching tree')
            parents[b] = a
            order.append(b)
    if len(order) != len(nodes):
        raise ValueError('Root lines are disconnected; join their ends or grow separate roots')
    children = [[b for b in adjacency[a] if parents.get(b) == a] for a in range(len(nodes))]
    remaining = np.zeros(len(nodes))
    for a in reversed(order):
        remaining[a] = sum(remaining[b]+np.linalg.norm(nodes[b]-nodes[a]) for b in children[a])
    total = max(remaining[base], 1e-8)
    # A pipe-like area budget: a parent supports its downstream growth.
    radius = thickness*.5*(np.maximum(remaining, total*.0003)/total)**(.42+.12*settings['taper'])
    # The attachment continues the trunk, without a swollen basal bulb.
    branches = []
    by_end = {}
    rng = np.random.default_rng(stable_seed(settings['seed']))
    for start in order:
        if start != base and len(children[start]) == 1:
            continue
        for first in children[start]:
            chain = [start, first]
            while len(children[chain[-1]]) == 1:
                chain.append(children[chain[-1]][0])
            p = nodes[chain].copy()
            parent = by_end.get(start, -1)
            # A soft curve interprets the gesture rather than preserving corners.
            for _ in range(1):
                p[1:-1] = .7*p[1:-1]+.15*(p[:-2]+p[2:])
            tangent = np.empty_like(p)
            tangent[0], tangent[-1] = p[1]-p[0], p[-1]-p[-2]
            tangent[1:-1] = (p[2:]-p[:-2])*.5
            if parent >= 0:
                upstream = (branches[parent]['points'][-1]-branches[parent]['points'][-2])[[0,2]]
                upstream /= max(np.linalg.norm(upstream), 1e-8)
                direction = tangent[0]/max(np.linalg.norm(tangent[0]), 1e-8)
                # Ease growth out of the parent; do not force backward branches forward.
                if upstream @ direction > -.65:
                    direction = .55*upstream+.45*direction
                    tangent[0] = direction/max(np.linalg.norm(direction), 1e-8)*np.linalg.norm(p[1]-p[0])
            samples, radii = [], []
            for k, (a, b) in enumerate(zip(p, p[1:])):
                count = max(5, min(160, int(np.linalg.norm(b-a)/(thickness*.09))+2))
                t = np.linspace(0, 1, count, endpoint=k == len(p)-2)
                h = t[:, None]
                q = (2*h**3-3*h**2+1)*a+(h**3-2*h**2+h)*tangent[k]+(-2*h**3+3*h**2)*b+(h**3-h**2)*tangent[k+1]
                samples.extend(q)
                # Interpolate area for gradual taper all the way to the tips.
                radii.extend(np.sqrt((1-t)*radius[chain[k]]**2+t*radius[chain[k+1]]**2))
            q = np.asarray(samples)
            r = np.asarray(radii)
            if parent >= 0:
                # Allocate the fork's area between its children, instead of
                # starting every child at the full trunk diameter (a cuff).
                budget = remaining[first]+np.linalg.norm(nodes[first]-nodes[start])
                share = np.sqrt(budget/max(remaining[start],1e-8))
                influence = np.linspace(1,0,len(r))**2
                r *= 1-(1-share)*influence
            arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))]
            progress = arc/max(arc[-1], 1e-8)
            phase = rng.uniform(0, 2*np.pi)
            derivative = np.gradient(q, axis=0)
            lateral = np.column_stack([-derivative[:, 1], derivative[:, 0]])
            lateral /= np.maximum(np.linalg.norm(lateral, axis=1, keepdims=True), 1e-8)
            gesture = np.sin(progress*6+phase)
            q += lateral*(np.sin(progress*np.pi)**2*gesture*np.minimum(r*.20, arc[-1]*.025))[:, None]
            r *= 1+.04*np.sin(progress*8+phase)*np.sin(progress*np.pi)
            # Gentle flattening in depth, never the old extruded board profile.
            depth = np.sin(progress*np.pi)**2*np.sin(progress*4+phase)*thickness*.22
            points = np.column_stack([q[:, 0], depth, q[:, 1]])
            if parent >= 0:
                upstream = branches[parent]['points'][-1]-branches[parent]['points'][-2]
                upstream /= max(np.linalg.norm(upstream),1e-8)
                # Bury the start volume inside the parent, allowing the union
                # to produce a shoulder rather than exposing a flat cap.
                points = np.vstack([points[0]-upstream*radius[start]*.85, points])
                r = np.r_[r[0]*.85,r]
                arc = np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
            flow_start = 0. if parent < 0 else branches[parent]['flow_start']+branches[parent]['length'][-1]-radius[start]*.85
            branches.append(dict(points=points, radius=r, parent=parent, phase=phase, flow_start=flow_start,
                                 length=arc, terminal=not children[chain[-1]]))
            by_end[chain[-1]] = len(branches)-1
    return dict(branches=branches, nodes=nodes, base=base, settings=settings)


def tubes(graph):
    """Closed overlapping growth volumes, ready for Blender's voxel union."""
    vertices, faces = [], []
    sides = {'DRAFT':12, 'PREVIEW':24, 'FINAL':36}[graph['settings']['quality']]
    for branch in graph['branches']:
        p, radius = branch['points'], branch['radius']
        tangent = np.gradient(p, axis=0)
        tangent /= np.maximum(np.linalg.norm(tangent, axis=1, keepdims=True), 1e-8)
        across = np.cross(tangent, np.array([0., 1., 0.]))
        across /= np.maximum(np.linalg.norm(across, axis=1, keepdims=True), 1e-8)
        front = np.cross(tangent, across)
        offset = len(vertices)
        for i, (center, r) in enumerate(zip(p, radius)):
            for angle in np.arange(sides)*2*np.pi/sides:
                # Six long wood planes, with a slow twist and slight asymmetry.
                twist = branch['phase']*.12+branch['length'][i]*.055
                sector = (angle+twist+np.pi/6) % (np.pi/3)-np.pi/6
                plane = np.cos(np.pi/6)/np.cos(sector)
                asymmetry = 1+.045*np.sin(angle*3+branch['phase'])
                vertices.append(center+r*plane*asymmetry*(np.cos(angle)*across[i]+.82*np.sin(angle)*front[i]))
        for i in range(len(p)-1):
            for j in range(sides):
                a = offset+i*sides+j
                b = offset+i*sides+(j+1)%sides
                faces.extend([(a,b,b+sides),(a,b+sides,a+sides)])
        for ring, sign in ((0,-1),(len(p)-1,1)):
            previous = offset+ring*sides
            if sign < 0 and branch['parent'] < 0:
                # A shallow slanted cut replaces the finger-like round base.
                for j in range(sides):
                    angle = j*2*np.pi/sides
                    vertices[previous+j] += tangent[ring]*radius[ring]*(.12*np.cos(angle)+.05*np.sin(angle*3))
                tip = len(vertices)
                vertices.append(p[ring]-tangent[ring]*radius[ring]*.015)
                for j in range(sides):
                    faces.append((tip,previous+(j+1)%sides,previous+j))
                continue
            # Rounded growth ends. A shallow conical cap creates a visible
            # collar at every fork even after the volumes have been joined.
            for latitude in (np.pi/8,np.pi/4,3*np.pi/8):
                current = len(vertices)
                for angle in np.arange(sides)*2*np.pi/sides:
                    vertices.append(p[ring]+tangent[ring]*radius[ring]*sign*np.sin(latitude)+
                                    radius[ring]*np.cos(latitude)*(np.cos(angle)*across[ring]+.86*np.sin(angle)*front[ring]))
                for j in range(sides):
                    a,b = previous+j,previous+(j+1)%sides
                    c,d = current+j,current+(j+1)%sides
                    faces.extend([(a,c,b),(b,c,d)] if sign < 0 else [(a,b,c),(b,d,c)])
                previous = current
            tip=len(vertices)
            vertices.append(p[ring]+tangent[ring]*radius[ring]*sign)
            for j in range(sides):
                a,b=previous+j,previous+(j+1)%sides
                faces.append((tip,b,a) if sign<0 else (tip,a,b))
    return np.asarray(vertices), np.asarray(faces)


def surface_details(points, graph):
    """Blend growth-aligned colour and real bark relief through the forks."""
    from .painted_bark import field
    phase = stable_seed(graph['settings']['seed']) % 10000
    colors = np.zeros((len(points),3))
    relief = np.zeros(len(points))
    weights = np.zeros(len(points))
    for branch in graph['branches']:
        best = np.full(len(points), np.inf)
        along = np.zeros(len(points))
        around = np.zeros(len(points))
        radius = np.zeros(len(points))
        p = branch['points']
        for i, (a, b) in enumerate(zip(p, p[1:])):
            d = b-a
            t = np.clip((points-a) @ d/max(d @ d, 1e-12), 0, 1)
            delta = points-a-t[:, None]*d
            distance = np.linalg.norm(delta, axis=1)
            take = distance < best
            across = np.array([-d[2], 0., d[0]])
            across /= max(np.linalg.norm(across), 1e-8)
            best[take] = distance[take]
            along[take] = branch['flow_start']+branch['length'][i]+t[take]*np.linalg.norm(d)
            around[take] = np.arctan2(delta[take] @ across, -delta[take, 1])
            radius[take] = branch['radius'][i]*(1-t[take])+branch['radius'][i+1]*t[take]
        color, height = field(around,along,phase,graph['settings']['age'])
        # A continuous partition blends the paint through forks. Hard nearest
        # branch assignment draws an artificial ring around each junction.
        weight = 1/(best+graph['settings']['depth']*.08)**8
        colors += color*weight[:,None]
        relief += height*radius*weight
        weights += weight
    return np.clip(colors/weights[:,None],0,1),relief/weights*graph['settings']['bark_strength']


def paint(points, graph):
    return surface_details(points,graph)[0]
