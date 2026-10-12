"""Broad dry painted wood planes with straight, shallow longitudinal fibres."""
import numpy as np
from .surface import noise, smoothstep


def field(angle, length, seed, age=.65):
    # Strong swirls and displaced colour clouds made the old bark look melted.
    grain = angle+.045*np.sin(angle*3+length*.7)
    grain += .025*noise(np.cos(angle)*3,length*.85+np.sin(angle),seed+4)
    broad = noise(np.cos(grain)*3.2,length*1.1+np.sin(grain)*1.7,seed+9)
    brush = smoothstep(-.15,.12,broad)
    # One muted umber family, without cream lips or multicolour knot rings.
    dark = np.array([.142,.090,.055])
    light = np.array([.235,.160,.102])
    color = dark+(light-dark)*brush[...,None]
    color *= 1-age*.045

    # Unequal fibre spacing, restrained angular drift and staggered ends.
    phase = grain*9+.48*np.sin(grain*4)+.13*np.sin(length*.65+grain*2)
    distance = np.arctan2(np.sin(phase),np.cos(phase))
    broken = smoothstep(-.45,.1,noise(np.cos(grain)*8,length*1.1+np.sin(grain)*3,seed+39))
    groove = (1-smoothstep(.13,.43,np.abs(distance)))*broken
    lip = (1-smoothstep(.09,.23,np.abs(distance-.47)))*broken
    color *= 1-.42*groove[...,None]
    color += lip[...,None]*np.array([.019,.014,.009])
    # Long dry-brush streaks affect paint only, not the silhouette.
    fibre = noise(np.cos(grain)*25,length*2.1+np.sin(grain)*12,seed+47)
    color += (smoothstep(.1,.6,fibre)*.015)[...,None]*np.array([1.,.78,.52])
    relief = -.028*groove+.004*lip
    return np.clip(color,0,1),relief
