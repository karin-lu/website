"""Run: python -m unittest discover -s tools/blender/roots -t tools/blender"""
import copy
import unittest
import numpy as np
from .surface import build_surfaces, bark_atlas, relief_normal, inside
from .graph import coordinates, segment_distance
from .rootlets import grow
from .fixtures import fixtures, outline, ring
from .model import validate


class RootsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.examples=fixtures()
        cls.parts=[build_surfaces([r],settings={'quality':'DRAFT'})[0] for r in cls.examples]

    def test_original_contours_and_inputs_unchanged(self):
        for r,part in zip(self.examples,self.parts):
            before=copy.deepcopy(r)
            q=part['vertices'][:,[0,2]]
            polygon=np.asarray(r['polygon'])
            for p in polygon: self.assertLess(np.linalg.norm(q-p,axis=1).min(),1e-8)
            outside=~inside(q,polygon)
            self.assertLess(segment_distance(q[outside],part['graph']['boundary']).max(),1e-8)
            build_surfaces([r],settings={'quality':'DRAFT','age':1})
            self.assertEqual(r,before)

    def test_watertight_positive_volume_and_depth_bound(self):
        for part in self.parts:
            v=part['vertices'];f=part['faces'];tri=v[f]
            edges=np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1)
            _,counts=np.unique(edges,axis=0,return_counts=True)
            self.assertTrue(np.all(counts==2))
            area=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)
            self.assertGreater(area.min(),1e-14)
            self.assertGreater(np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum()/6,0)
            self.assertLessEqual(np.ptp(v[:,1]),.38000001)

    def test_fork_and_nested_fork_topology(self):
        graph=self.parts[0]['graph']
        self.assertEqual(len(graph['branches']),3)
        self.assertEqual(len(graph['junctions']),1)
        # Nested Y on one arm: parent-child-grandchild, not all child-to-trunk.
        roots=[outline('trunk',[[-.18,0],[.18,0],[.15,1.4],[-.15,1.4]]),
               outline('arm',[[-.1,1],[.12,.95],[1.15,2.3],[.95,2.4]]),
               outline('spur',[[.52,1.68],[.68,1.6],[1.25,1.72],[1.23,1.9]]),
               outline('other',[[-.1,1.1],[.1,1.3],[-.75,2.2],[-.95,2.05]])]
        p=build_surfaces(roots,settings={'quality':'DRAFT'})[0]
        branches=p['graph']['branches']
        self.assertGreaterEqual(len(p['graph']['junctions']),2)
        self.assertTrue(any(b['parent']>=0 and branches[b['parent']]['parent']>=0 for b in branches))

    def test_curved_grain_follows_length(self):
        graph=self.parts[1]['graph']
        longest=max(graph['branches'],key=lambda b:b['length'][-1])
        u,v,_,_=coordinates(longest['points'],graph)
        self.assertTrue(np.all(np.diff(v)>0))
        self.assertLess(np.max(np.abs(u)),.04)
        self.assertGreater(longest['length'][-1],np.linalg.norm(longest['points'][-1]-longest['points'][0])*1.08)

    def test_local_taper_and_quality_changes_real_geometry(self):
        root=self.examples[2]
        full=build_surfaces([root],settings={'quality':'DRAFT','taper':0})[0]
        tapered=self.parts[2]
        for p in (full,tapered):
            v=p['vertices']; tip=v[v[:,2]>1.8]
            self.assertGreater(np.ptp(tip[:,1]),.003)
        self.assertLess(np.ptp(tapered['vertices'][tapered['vertices'][:,2]>1.8,1]),
                        np.ptp(full['vertices'][full['vertices'][:,2]>1.8,1]))
        fine=build_surfaces([root],settings={'quality':'FINAL'})[0]
        self.assertGreater(len(fine['faces']),len(tapered['faces']))

    def test_union_hole_and_separate_islands(self):
        p=build_surfaces(ring(),settings={'quality':'DRAFT'})[0]
        centers=p['vertices'][p['faces']].mean(axis=1)[:,[0,2]]
        self.assertFalse(np.any(np.all(np.abs(centers)<.59,axis=1)))
        pieces=build_surfaces([outline('a',[[0,0],[.2,0],[.2,1],[0,1]]),
                               outline('b',[[1,0],[1.2,0],[1.2,1],[1,1]])],settings={'quality':'DRAFT'})
        self.assertEqual(len(pieces),2)

    def test_uv_distortion_bound_and_rootlet_volume(self):
        part=copy.copy(self.parts[0]);part['settings']={**part['settings'],'rootlet_density':1}
        children=grow(part)
        for p in [*self.parts,*children]:
            tri=p['vertices'][p['faces']];uv=p['surface_uv']
            a,b=uv[:,1]-uv[:,0],uv[:,2]-uv[:,0]
            projected=np.abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])
            actual=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)
            self.assertLessEqual((actual/projected).max(),np.sqrt(3)+1e-7)
        for p in children:
            faces=p['faces'];tri=p['vertices'][faces]
            edges=np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1)
            _,counts=np.unique(edges,axis=0,return_counts=True)
            self.assertTrue(np.all(counts==2))
            self.assertGreater(np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum()/6,0)

    def test_seam_normals_rotated_and_mirrored_bases(self):
        part=self.parts[0]
        positions=np.array([[.05,-.17,.7],[-.1,-.13,1.02]])
        normals=np.tile([0,-1.,0],(2,1))
        tangent_a=np.tile([1.,0,0],(2,1));tangent_b=np.tile([0,0,1.],(2,1))
        def world(tangent,sign):
            local=relief_normal(positions,normals,tangent,np.full(2,sign),part)*2-1
            return tangent*local[:,0,None]+np.cross(normals,tangent)*sign*local[:,1,None]+normals*local[:,2,None]
        np.testing.assert_allclose(world(tangent_a,1),world(tangent_b,-1),atol=1e-6)
        self.assertGreater(np.max(np.abs(world(tangent_a,1)-normals)),.01)

    def test_baked_maps_and_determinism(self):
        part=self.parts[0]
        a=build_surfaces([self.examples[0]],settings={'quality':'DRAFT'})[0]
        np.testing.assert_array_equal(part['vertices'],a['vertices'])
        c,n,orm=bark_atlas(part,128)
        for image in (c,n,orm):
            self.assertTrue(np.isfinite(image).all());self.assertGreaterEqual(image.min(),0);self.assertLessEqual(image.max(),1)
        self.assertGreater(np.std(n[:,:,0]),.003)
        flat=copy.copy(part);flat['settings']={**part['settings'],'bark_strength':0}
        _,nn,_=bark_atlas(flat,128)
        np.testing.assert_allclose(nn,np.broadcast_to([.5,.5,1],nn.shape),atol=1e-6)

    def test_rootlet_clearance_and_repeatability(self):
        root=copy.deepcopy(self.examples[0]);root['grab_edges']=list(range(len(root['polygon'])))
        protected=build_surfaces([root],settings={'quality':'DRAFT','rootlet_density':1})[0]
        self.assertEqual(grow(protected),[])
        part=copy.copy(self.parts[0]);part['settings']={**part['settings'],'rootlet_density':1}
        a=grow(part);b=grow(part)
        self.assertTrue(a)
        np.testing.assert_array_equal(a[0]['vertices'],b[0]['vertices'])

    def test_invalid_guides_preserve_validation(self):
        with self.assertRaises(ValueError): validate([outline('bad',[[0,0],[1,1],[0,1],[1,0]])])
        with self.assertRaises(ValueError): build_surfaces([self.examples[0]],guides=[[[0,.2],[3,4]]])

    def test_explicit_centrelines_and_broken_ends(self):
        # The open guide deliberately starts in a different direction than
        # the automatic low/thick inference; its geometric arc is retained.
        root=outline('small',[[0,0],[.01,0],[.01,.025],[0,.025]])
        p=build_surfaces([root],guides=[[[.005,.003],[.005,.022]]],settings={'quality':'DRAFT'})[0]
        self.assertEqual(len(p['graph']['branches']),1)
        with self.assertRaises(ValueError):
            build_surfaces([self.examples[0]],guides=[[[0,.1],[0,.4]],[[.5,1.5],[.7,1.7]]])
        broken=copy.deepcopy(self.examples[2])
        broken['end_profiles']=[dict(a=[.025,2.2],b=[-.025,2.2],inward=[0,-1],band=.065)]
        a=build_surfaces([broken],settings={'quality':'DRAFT'})[0]
        np.testing.assert_array_equal(a['vertices'][:,[0,2]],self.parts[2]['vertices'][:,[0,2]])
        self.assertGreater(np.max(np.abs(a['vertices'][:,1]-self.parts[2]['vertices'][:,1])),.001)


if __name__=='__main__': unittest.main()
