# Original layered ivy and moss rims

The rock-hugging bushes use their original Blender-grown ivy geometry again.
The original leaf count, size, growth direction, atlas cells, vertex colours,
solid underlay and clump detail are preserved. Added backing blobs, duplicated
outer fans, atlas substitutions and camera-facing coverage have been removed.

Only individual rectangular leaf cards are bent. Their stalk-to-tip path has
a small arch, mild tip curl and a slight cross-blade fold. Layers are processed
from the host outward. Each visible stalk is seated 2 mm above the original
solid underlay, a previously seated leaf, or the rock if no leaf supports it.
Supporting leaves are checked against their atlas alpha: transparent space
around a leaf does not count as contact. Blade samples are kept clear of the
underlying leaves and the rock. Stalk attachment has no capped translation,
so unsupported original leaves cannot remain suspended above their host.

Unnamed glTF groups are traversed to find the named ivy ancestor and its rock.
Connected underlays, constant-UV stems and segmented hanging strands retain
their source geometry. Original foliage materials and lighting are preserved.

The separately requested moss-rim improvements remain. Opaque moss mounds
receive 6–12 cm tuft cards from the supplied atlas. Bases conform to the moss,
colours sample its painted texture, and tips lighten by 6%. Placement follows
open rims and front silhouettes, with up to 1400 cards per mound and one draw
per mound. The atlas was supplied in files.zip on 2026-10-09.

Checks:

- bun run scripts/test-ivy-geometry.ts
- bun run scripts/test-foliage-scene.mts
- bun run scripts/test-moss-fringe.ts
- bun run typecheck
- bun run build
