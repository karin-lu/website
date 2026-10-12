"""Sparse subordinate roots, with explicit clearance from playable edges."""
import numpy as np
from .graph import segment_distance, coordinates
from .model import stable_seed
from .surface import surface_bark_uv


def front_depth(part,point):
    triangle=part['vertices'][part['faces']]
    q=triangle[:,:,[0,2]];a=q[:,0];e=q[:,1]-a;f=q[:,2]-a;delta=point-a
    det=e[:,0]*f[:,1]-e[:,1]*f[:,0]
    valid=np.abs(det)>1e-12
    safe=np.where(valid,det,1)
    beta=(delta[:,0]*f[:,1]-delta[:,1]*f[:,0])/safe
    gamma=(e[:,0]*delta[:,1]-e[:,1]*delta[:,0])/safe
    valid&=(beta>=-1e-8)&(gamma>=-1e-8)&(beta+gamma<=1+1e-8)
    depth=(1-beta-gamma)*triangle[:,0,1]+beta*triangle[:,1,1]+gamma*triangle[:,2,1]
    return float(depth[valid].min()) if valid.any() else None


def grow(part):
    settings=part['settings']; density=settings['rootlet_density']
    if density <= 0: return []
    rng=np.random.default_rng(stable_seed(str(part['seed'])+part['id']+'rootlets'))
    protected=[]
    for r in part['atlas_roots']:
        p=np.asarray(r['polygon'])
        protected.extend((p[i],p[(i+1)%len(p)]) for i in r.get('grab_edges',[]))
    graph=part['graph']; vertices=[]; faces=[]; branches=[]
    for parent in graph['branches']:
        count=min(12,int(parent['length'][-1]*density*2+rng.random()))
        for slot in range(count):
            station=(.15+.7*(slot+rng.uniform(.15,.85))/count)*parent['length'][-1]
            k=min(np.searchsorted(parent['length'],station)-1,len(parent['points'])-2)
            t=(station-parent['length'][k])/max(parent['length'][k+1]-parent['length'][k],1e-8)
            anchor=parent['points'][k]*(1-t)+parent['points'][k+1]*t
            width=parent['widths'][k]*(1-t)+parent['widths'][k+1]*t
            tangent=parent['points'][k+1]-parent['points'][k]
            tangent/=np.linalg.norm(tangent)
            side=np.array([tangent[1],-tangent[0]])*rng.choice([-1,1])
            length=rng.uniform(.18,.4)+width*.7
            tt=np.linspace(0,1,13)
            # Start along the parent grain and peel away gradually; sharp
            # perpendicular attachments read as thorns or little staples.
            curve=anchor+(tt**1.55)[:,None]*side*length+tt[:,None]*tangent*.1
            curve[:,1]-=.18*tt*tt
            radius=min(.022,width*.16)*rng.uniform(.65,1.15)
            # Check the whole swept tube, not just its centreline. With all
            # outline edges playable, outward rootlets are suppressed.
            if protected and np.min(segment_distance(curve,np.asarray(protected))-(radius*(1-tt)**1.4)) < .09:
                continue
            y=front_depth(part,anchor)
            if y is None: continue
            y+=radius*.45  # bury the base slightly in the actual surface
            path=np.column_stack([curve[:,0],y-.025*np.sin(tt*np.pi/2),curve[:,1]])
            first=len(vertices); sides=8
            for i,point in enumerate(path):
                direction=path[min(i+1,len(path)-1)]-path[max(0,i-1)]
                direction/=np.linalg.norm(direction)
                a=np.cross(direction,[0,1,0]);a/=np.linalg.norm(a)
                b=np.cross(direction,a)
                r=max(.0006,radius*(1-tt[i])**1.4)
                for angle in np.arange(sides)*2*np.pi/sides:
                    vertices.append(point+r*(a*np.cos(angle)+b*np.sin(angle)))
            for i in range(len(path)-1):
                for j in range(sides):
                    a=first+i*sides+j;b=first+i*sides+(j+1)%sides
                    faces.extend([[a,b,b+sides],[a,b+sides,a+sides]])
            for end,reverse in ((first,True),(first+(len(path)-1)*sides,False)):
                center=len(vertices);vertices.append(np.mean(vertices[end:end+sides],axis=0))
                for j in range(sides):
                    face=[center,end+j,end+(j+1)%sides]
                    faces.append(face[::-1] if reverse else face)
            u,v,_,_=coordinates(anchor[None],graph)
            branches.append(dict(points=curve,widths=np.full(len(curve),radius),
                                 length=np.r_[0,np.cumsum(np.linalg.norm(np.diff(curve,axis=0),axis=1))],
                                 offset=v[0],u_offset=u[0],parent=-1,start=0,end=1))
    if not faces: return []
    vertices=np.asarray(vertices);faces=np.asarray(faces)
    uv,size,charts=surface_bark_uv(vertices,faces,part['atlas_roots'])
    child={**part,'id':part['id']+'__rootlets','vertices':vertices,'faces':faces,
           'surface_uv':uv,'uv':(uv+.015)/(size+.03),'atlas_size':size,'atlas_charts':charts,
           'graph':{**graph,'branches':branches,'junctions':np.empty((0,2))},'rootlet_count':len(branches)}
    return [child]
