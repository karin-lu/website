import assert from "node:assert/strict";
import { emptyModel } from "../src/editor/model";
import { Guides } from "../src/editor/visuals/guides";

const model = emptyModel();
model.items[0].shape = { kind: "rect", w: 1e10, h: 1e10 };
const guides = new Guides();
guides.sync({ model, rev: 1, selectedIds: new Set(), selectedBodyIds: new Set(), selectedVerts: new Set(), visibleLayers: new Set(), lockedLayers: new Set() });
let gridVertices = 0;
guides.group.getObjectByName("guides-grid")!.traverse(o => {
  const geometry = (o as any).geometry;
  if (geometry) gridVertices += geometry.getAttribute("position").count;
});
assert.ok(gridVertices > 0 && gridVertices <= 12010, "even enormous volumes retain a bounded usable grid");
guides.dispose();
console.log("Large level collision volumes keep the editor grid bounded.");
