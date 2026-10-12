"""Small authoring examples used by structural tests and the render study."""
import numpy as np


def outline(id,points,**kw):
    return dict(id=id,polygon=np.asarray(points,float).tolist(),**kw)


def curved():
    t=np.linspace(0,1,19)
    path=np.column_stack([.45*np.sin(t*np.pi*1.6),t*2.3])
    direction=np.gradient(path,axis=0)
    normal=np.column_stack([direction[:,1],-direction[:,0]])
    normal/=np.linalg.norm(normal,axis=1,keepdims=True)
    width=.19*(1-.72*t)
    return outline('curved',np.concatenate([path+normal*width[:,None],
                                          (path-normal*width[:,None])[::-1]]))


def fixtures():
    return [outline('fork',[[-.3,0],[.3,0],[.22,1],[1.1,1.8],[.85,2],
                           [0,1.2],[-.8,1.9],[-1,1.7],[-.2,.9]]),
            curved(),outline('taper',[[-.22,0],[.22,0],[.025,2.2],[-.025,2.2]])]


def ring():
    return [outline('bottom',[[-1,-1],[1,-1],[1,-.6],[-1,-.6]]),
            outline('left',[[-1,-1],[-.6,-1],[-.6,1],[-1,1]]),
            outline('right',[[.6,-1],[1,-1],[1,1],[.6,1]]),
            outline('top',[[-1,.6],[1,.6],[1,1],[-1,1]])]
