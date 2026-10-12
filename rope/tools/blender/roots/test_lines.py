import copy
import unittest
import numpy as np
from .lines import tree, tubes, paint
from .painted_bark import field


STROKES = [[[0,0],[.1,1],[.45,2],[1.1,2.7]],
           [[.1,1],[-.65,1.65],[-1.2,1.9]],
           [[.45,2],[.05,2.55],[-.1,3.1]]]


class LineRootsTest(unittest.TestCase):
    def test_thick_attachment_is_a_shallow_cut_not_a_round_cap(self):
        graph=tree([[[0,0],[0,2]]])
        vertices,_=tubes(graph)
        radius=graph['branches'][0]['radius'][0]
        self.assertGreater(vertices[:,2].min(),-radius*.2)
        self.assertLess(np.abs(vertices[:,0]).max(),radius*1.1)

    def test_bark_wraps_without_seam_and_has_bounded_relief(self):
        length=np.linspace(0,4,301)
        left=field(np.full_like(length,-np.pi),length,73)
        right=field(np.full_like(length,np.pi),length,73)
        for a,b in zip(left,right): np.testing.assert_allclose(a,b,atol=1e-10)
        angle,length=np.meshgrid(np.linspace(-np.pi,np.pi,180),np.linspace(0,4,160))
        color,relief=field(angle,length,73)
        self.assertTrue(np.isfinite(color).all())
        self.assertLess(np.abs(relief).max(),.03)
        # Broad strokes remain visible within the deliberately tighter palette.
        contrast=np.percentile(color[:,:,0],90)-np.percentile(color[:,:,0],10)
        self.assertGreater(contrast,.04)
        self.assertLess(contrast,.12)

    def test_branch_graph_taper_and_preserved_inputs(self):
        original=copy.deepcopy(STROKES)
        graph=tree(STROKES)
        self.assertEqual(STROKES,original)
        self.assertEqual(len(graph['branches']),5)
        self.assertEqual(sum(b['terminal'] for b in graph['branches']),3)
        self.assertTrue(any(b['parent']>=1 for b in graph['branches']))
        for branch in graph['branches']:
            self.assertGreater(branch['radius'][0],branch['radius'][-1])
            self.assertTrue(np.isfinite(branch['points']).all())

    def test_loose_t_attachment_and_reversed_branch(self):
        graph=tree([[[0,0],[0,3]], [[-1,2],[.03,1.5]]])
        self.assertEqual(len(graph['branches']),3)
        self.assertEqual(sum(b['terminal'] for b in graph['branches']),2)

    def test_crossing_does_not_silently_join(self):
        with self.assertRaisesRegex(ValueError,'disconnected'):
            tree([[[-1,0],[1,2]],[[-1,2],[1,0]]])

    def test_invalid_graphs(self):
        for paths in ([], [[[0,0],[0,0]]], [[[0,0],[float('nan'),2]]],
                      [[[0,0],[1,0],[1,1],[0,0]]]):
            with self.assertRaises(ValueError): tree(paths)

    def test_closed_growth_volumes_and_reproducibility(self):
        graph=tree(STROKES)
        v,f=tubes(graph)
        self.assertTrue(np.array_equal(v,tubes(tree(STROKES))[0]))
        edges=np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1)
        self.assertTrue(np.all(np.unique(edges,axis=0,return_counts=True)[1]==2))
        tri=v[f]
        self.assertGreater(np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum(),0)
        self.assertGreater(np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1).min(),1e-12)
        color=paint(v[::17],graph)
        self.assertTrue(np.isfinite(color).all())
        self.assertTrue(((color>=0)&(color<=1)).all())
        self.assertFalse(np.array_equal(v,tubes(tree(STROKES,{'seed':'another'}))[0]))


if __name__=='__main__': unittest.main()
