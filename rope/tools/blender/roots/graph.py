"""Topology-aware bark frames from a thinned union; NumPy only.

The grid finds branches, never the rendered contour. All output geometry still
uses the exact authored union. Open centreline guides can override inference.
"""
from collections import deque
import numpy as np


def _thin(mask):
    image = np.pad(mask, 1).astype(bool)
    for _ in range(max(image.shape)):
        changed = False
        for pass_id in (0, 1):
            p = [image[:-2, 1:-1], image[:-2, 2:], image[1:-1, 2:],
                 image[2:, 2:], image[2:, 1:-1], image[2:, :-2],
                 image[1:-1, :-2], image[:-2, :-2]]
            count = sum(x.astype(np.uint8) for x in p)
            transitions = sum((~p[i] & p[(i+1) % 8]).astype(np.uint8) for i in range(8))
            if pass_id == 0:
                keep = ~(p[0] & p[2] & p[4]) & ~(p[2] & p[4] & p[6])
            else:
                keep = ~(p[0] & p[2] & p[6]) & ~(p[0] & p[4] & p[6])
            take = image[1:-1, 1:-1] & (count >= 2) & (count <= 6) & (transitions == 1) & keep
            changed |= bool(take.any())
            image[1:-1, 1:-1][take] = False
        if not changed:
            return image[1:-1, 1:-1]
    raise ValueError("Root centreline thinning did not converge")


def segment_distance(points, segments):
    """Distance to exposed union edges, not hidden overlap edges."""
    result = np.full(len(points), np.inf)
    for a, b in segments:
        e = b-a
        t = np.clip((points-a) @ e / max(e @ e, 1e-16), 0, 1)
        result = np.minimum(result, np.linalg.norm(points-a-t[:, None]*e, axis=1))
    return result


def boundary_segments(points, faces):
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    unique, counts = np.unique(edges, axis=0, return_counts=True)
    return points[unique[counts == 1]]


def _chains(pixels):
    pixels = {tuple(p) for p in pixels}
    adj = {}
    for y, x in sorted(pixels):
        neighbors = []
        for dy, dx in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
            q = y+dy, x+dx
            if q in pixels and not (dy and dx and ((y+dy,x) in pixels or (y,x+dx) in pixels)):
                neighbors.append(q)
        adj[y,x] = sorted(neighbors)
    # Junction plateaus become one node; do not leave tiny branches between
    # neighboring junction pixels, which would cause grain reversals.
    special = {p for p in pixels if len(adj[p]) != 2}
    if not special and pixels:
        special.add(min(pixels))  # A ring remains a ring, not a filled hole.
    node_for = {}; nodes = []; pending = set(special)
    while pending:
        start = min(pending); stack = [start]; cluster = []
        while stack:
            p = stack.pop()
            if p not in pending:
                continue
            pending.remove(p); cluster.append(p)
            if len(adj[p]) > 2:
                stack.extend(q for q in adj[p] if q in pending and len(adj[q]) > 2)
        n = len(nodes); nodes.append(np.mean(cluster, axis=0))
        node_for.update((p, n) for p in cluster)
    seen = set(); edges = []
    for p in sorted(node_for):
        for q in adj[p]:
            key = tuple(sorted((p,q)))
            if key in seen or node_for.get(q) == node_for[p]:
                continue
            path = [p]; previous, current = p, q; seen.add(key)
            while current not in node_for:
                path.append(current)
                choices = [r for r in adj[current] if r != previous]
                if not choices:
                    break
                nxt = choices[0]; seen.add(tuple(sorted((current,nxt))))
                previous, current = current, nxt
            if current in node_for:
                path.append(current)
                edges.append((node_for[p], node_for[current], np.asarray(path, float)))
    return np.asarray(nodes), edges


def infer(roots, boundary, guides=None):
    from .surface import inside
    polygons = [np.asarray(r['polygon'], float) for r in roots]
    all_points = np.concatenate(polygons)
    span = np.ptp(all_points, axis=0)
    # About 180 samples across the long dimension. Narrow branches are kept
    # by reducing the step with the narrowest input's width.
    step = max(.004, float(max(span))/256, min(.025,float(max(span))/180))
    lo = all_points.min(axis=0)-step*3
    nx, ny = np.ceil((span+6*step)/step).astype(int)+1
    xx, yy = np.meshgrid(lo[0]+np.arange(nx)*step, lo[1]+np.arange(ny)*step)
    samples = np.column_stack([xx.ravel(), yy.ravel()])
    mask = np.zeros(len(samples), bool)
    for p in polygons:
        mask |= inside(samples, p)
    nodes, edges = _chains(np.argwhere(_thin(mask.reshape(ny,nx)))) if not guides else (np.empty((0,2)),[])
    if not edges and not guides:
        raise ValueError("Root is too small for a centreline; supply an open centreline guide")
    nodes = lo + nodes[:, ::-1]*step
    edges = [(a,b,lo+path[:, ::-1]*step) for a,b,path in edges]
    if guides:
        # Explicit guides must meet at their ends; nearest endpoints within
        # two grid cells share a junction. Disjoint guides are rejected.
        nodes_list = []; edges = []
        for path in guides:
            path = np.asarray(path, float)
            if path.ndim!=2 or path.shape[1]!=2 or len(path)<2 or not np.isfinite(path).all():
                raise ValueError('Centreline guide needs two or more finite points')
            samples=np.concatenate([np.linspace(a,b,max(2,int(np.linalg.norm(b-a)/step)+1))
                                    for a,b in zip(path,path[1:])])
            if not all(any(inside(q[None], p)[0] for p in polygons) for q in samples):
                raise ValueError("Centreline guide points must be inside the root outline")
            ids = []
            for endpoint in path[[0,-1]]:
                matches = [i for i,n in enumerate(nodes_list) if np.linalg.norm(n-endpoint) < step*2]
                if matches: ids.append(matches[0])
                else: ids.append(len(nodes_list)); nodes_list.append(endpoint)
            edges.append((*ids,path))
        nodes = np.asarray(nodes_list)
    # Prune skeleton's short side spurs using their local physical width.
    for _ in range(8):
        degree = np.bincount([n for a,b,_ in edges for n in (a,b)], minlength=len(nodes))
        keep = []
        for a,b,path in edges:
            length = np.linalg.norm(np.diff(path,axis=0),axis=1).sum()
            width = segment_distance(path, boundary).max()
            if not guides and len(edges) > 1 and min(degree[a],degree[b]) == 1 and length < max(step*3, width*.8):
                continue
            keep.append((a,b,path))
        if len(keep) == len(edges) or not keep: break
        edges = keep
    adjacency = {i: [] for i in range(len(nodes))}
    for i,(a,b,_) in enumerate(edges):
        adjacency[a].append((b,i)); adjacency[b].append((a,i))
    ends = [n for n,entries in adjacency.items() if len(entries) == 1]
    candidates = ends or [n for n,entries in adjacency.items() if entries]
    # Prefer a thick, low endpoint rather than a polygon's principal axis.
    # Sample the end's first third, not its whole edge: on a curved tapered
    # single limb both ends otherwise inherit the same maximum width.
    def base_score(n):
        a,b,path=edges[adjacency[n][0][1]]
        if n!=a: path=path[::-1]
        width=segment_distance(path[:max(2,len(path)//3)],boundary).max()
        return (float(width),-nodes[n,1])
    base = max(candidates,key=base_score)
    parent_edge = {}; distances = {base: 0.}; queue = deque([base]); seen_edges = set(); branches = []
    while queue:
        a = queue.popleft()
        for b,i in adjacency[a]:
            if i in seen_edges: continue
            seen_edges.add(i)
            start,end,path = edges[i]
            if start != a: path = path[::-1].copy()
            path[0] = nodes[a]; path[-1] = nodes[b]
            for _ in range(12):
                trial = path.copy()
                trial[1:-1] = (path[:-2]+2*path[1:-1]+path[2:])/4
                valid = np.zeros(len(trial),bool)
                for p in polygons: valid |= inside(trial,p)
                path[1:-1] = np.where(valid[1:-1,None],trial[1:-1],path[1:-1])
            # Simplify gently without replacing a curved branch by a chord.
            selected = [0]
            for k in range(1,len(path)-1):
                if np.linalg.norm(path[k]-path[selected[-1]]) >= step*2:
                    segment=np.linspace(path[selected[-1]],path[k],5)
                    valid=np.zeros(len(segment),bool)
                    for p in polygons: valid|=inside(segment,p)
                    if not valid.all() and k-1>selected[-1]: selected.append(k-1)
                    selected.append(k)
            selected.append(len(path)-1); path = path[selected]
            lengths = np.r_[0,np.cumsum(np.linalg.norm(np.diff(path,axis=0),axis=1))]
            if lengths[-1] < 1e-8: continue
            widths = np.maximum(segment_distance(path,boundary),step*.35)
            branch = dict(points=path, widths=widths, length=lengths,
                          offset=distances[a], parent=parent_edge.get(a,-1), start=a, end=b)
            branch['u_offset'] = 0.
            branches.append(branch)
            if b not in distances:
                distances[b] = distances[a]+lengths[-1]
                parent_edge[b] = len(branches)-1; queue.append(b)
    if len(seen_edges) != len(edges):
        raise ValueError("Centreline guides must form one connected system per root island")
    junctions = nodes[[n for n,entries in adjacency.items() if len(entries)>2]]
    graph = dict(branches=branches, junctions=junctions, boundary=boundary,
                 base=nodes[base], step=step,
                 base_width=max(float(b['widths'].max()) for b in branches))
    # Align lateral phase with the actual parent at each fork, recursively.
    for b in branches:
        if b['parent'] >= 0:
            parent = branches[b['parent']]
            u,_,_ = _project(b['points'][:1],parent)
            b['u_offset'] = float(u[0])
    return graph


def _project(points, branch):
    path = branch['points']; e = np.diff(path,axis=0)
    length = np.maximum(np.linalg.norm(e,axis=1),1e-12)
    delta = points[:,None]-path[None,:-1]
    t = np.clip(np.einsum('nsi,si->ns',delta,e)/(length*length),0,1)
    closest = delta-t[:,:,None]*e
    distance2 = np.einsum('nsi,nsi->ns',closest,closest)
    i = np.argmin(distance2,axis=1); n = np.arange(len(points)); t = t[n,i]
    tangent = e[i]/length[i,None]
    u = closest[n,i,0]*tangent[:,1]-closest[n,i,1]*tangent[:,0]+branch['u_offset']
    v = branch['length'][i]+t*length[i]+branch['offset']
    width = branch['widths'][i]*(1-t)+branch['widths'][i+1]*t
    return u,v,(distance2[n,i],width)


def coordinates(points, graph):
    points = np.asarray(points); uu=[]; vv=[]; ww=[]; dd=[]
    for b in graph['branches']:
        u,v,(d,w) = _project(points,b)
        uu.append(u); vv.append(v); ww.append(w); dd.append(d)
    dd = np.asarray(dd); widths = np.asarray(ww)
    # A smooth partition around junctions avoids a nearest-branch hard seam.
    nearest = np.argmin(dd,axis=0)
    local_width = widths[nearest,np.arange(len(points))]
    weights = np.exp(np.clip(-(dd-dd.min(axis=0))/(np.maximum(local_width*.42,graph['step'])**2),-60,0))
    weights /= weights.sum(axis=0)
    shoulders = np.zeros(len(points))
    for j in graph['junctions']:
        shoulders = np.maximum(shoulders,np.exp(-np.sum((points-j)**2,axis=1)/max(graph['base_width']*.65,.04)**2))
    return (np.sum(weights*np.asarray(uu),axis=0),np.sum(weights*np.asarray(vv),axis=0),
            shoulders, np.sum(weights*widths,axis=0))
