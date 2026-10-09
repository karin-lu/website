import * as THREE from "three";
import type { FoliageCards, FoliageCardEdit } from "../level/foliageCards";
import { applyMossCardEdits, mossCards } from "../render3d/mossCardEdits";
import { leafOpacitySampler } from "../render3d/leafSupport";

interface Host {
  canvas: HTMLCanvasElement;
  root: HTMLElement;
  scene: THREE.Scene;
  camera: () => THREE.Camera;
  edits: () => FoliageCards;
  begin: () => void;
  changed: () => void;
  editable: () => boolean;
  enter: () => void;
  frame: (box: THREE.Box3) => void;
}

/** Editing chrome is separate from the painted material and never saved into the scene. */
export class FoliageEditor {
  active = false;
  private panel = document.createElement("section");
  private overlay = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  private patch = document.createElement("select");
  private card = document.createElement("input");
  private status = document.createElement("p");
  private fields: { input: HTMLInputElement | HTMLSelectElement; key: keyof FoliageCardEdit; scale: number; fallback: number }[] = [];
  private selected: { patch: string; card: number } | null = null;
  private listKey = "";
  private valueKey = "";
  private ray = new THREE.Raycaster();
  private opacity = new WeakMap<THREE.Material, ((uv: THREE.Vector2) => boolean) | undefined>();
  private gesture: { mesh: THREE.Mesh; edit: FoliageCardEdit; plane: THREE.Plane; start: THREE.Vector3; root: THREE.Vector3; point: number; moved: boolean } | null = null;

  constructor(private host: Host) {
    this.panel.className = "ed-inspector ed-foliage";
    this.panel.style.cssText = "display:none;width:220px;gap:8px;max-width:calc(100vw - 32px);max-height:calc(100vh - 32px);overflow:auto;z-index:30";
    this.panel.setAttribute("aria-label", "Moss foliage cards");
    const heading = document.createElement("h3"); heading.textContent = "Moss foliage cards"; heading.style.margin = "0";
    const help = document.createElement("p");
    help.textContent = "Drag a tuft to move it on the moss. Drag orange points to reshape it. Edits save with the level.";
    help.title = "Middle drag orbits; right drag pans; wheel zooms. F frames the selected card. Ctrl+Z undoes.";
    help.style.cssText = "font-size:12px;line-height:1.4;margin:0";
    this.patch.className = "ed-select"; this.patch.setAttribute("aria-label", "Moss patch");
    this.patch.onchange = () => { this.selected = { patch: this.patch.value, card: 0 }; this.refreshFields(); this.framePatch(); };
    this.card.type = "number"; this.card.min = "1"; this.card.step = "1"; this.card.className = "ed-num";
    this.card.setAttribute("aria-label", "Card number");
    this.card.onchange = () => {
      const mesh = this.meshFor(this.patch.value);
      if (!mesh) return;
      this.selected = { patch: this.patch.value, card: Math.max(0, Math.min(mesh.geometry.userData.mossFringeCards - 1, Number(this.card.value) - 1)) };
      this.refreshFields(); this.frameCard();
    };
    this.panel.append(heading, help, this.label("Moss patch", this.patch), this.label("Card number", this.card));
    const navigation = document.createElement("div"); navigation.className = "ed-row";
    for (const [title, action] of [
      ["Previous", () => this.step(-1)], ["Next", () => this.step(1)],
      ["Frame card", () => this.frameCard()], ["Frame patch", () => this.framePatch()],
    ] as const) navigation.append(this.button(title, action));
    navigation.style.flexWrap = "wrap"; this.status.style.margin = "0"; this.panel.append(navigation, this.status);
    this.number("Width (%)", "width", 20, 400, 5, 100, 1);
    this.number("Height (%)", "height", 20, 400, 5, 100, 1);
    this.number("Rotation (°)", "rotation", -180, 180, 5, 180 / Math.PI, 0);
    this.number("Curve (%)", "curve", -100, 100, 5, 100, 0);
    const variant = document.createElement("select"); variant.className = "ed-select";
    ["Original", "Tuft 1", "Tuft 2", "Tuft 3", "Tuft 4"].forEach((name, i) => { const option = new Option(name, String(i - 1)); variant.add(option); });
    variant.onchange = () => this.edit(edit => { if (variant.value === "-1") delete edit.variant; else edit.variant = Number(variant.value); });
    this.fields.push({ input: variant, key: "variant", scale: 1, fallback: -1 });
    this.panel.append(this.label("Card shape", variant));
    const actions = document.createElement("div"); actions.className = "ed-row";
    actions.append(this.button("Hide / show", () => this.edit(edit => { edit.hidden = !edit.hidden; })), this.button("Reset card", () => {
      if (!this.selected) return;
      this.host.begin(); const edits = this.host.edits();
      delete edits[this.selected.patch]?.[String(this.selected.card)];
      if (!Object.keys(edits[this.selected.patch] ?? {}).length) delete edits[this.selected.patch];
      this.host.changed(); this.refreshFields();
    }));
    this.panel.append(actions);
    this.overlay.style.cssText = "position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:25";
    this.overlay.setAttribute("aria-hidden", "true"); this.overlay.style.display = "none";
    this.host.root.append(this.panel); document.body.append(this.overlay);
    host.canvas.addEventListener("pointerdown", e => this.press(e), true);
    host.canvas.addEventListener("pointermove", e => this.move(e), true);
    host.canvas.addEventListener("pointerup", e => this.release(e), true);
    host.canvas.addEventListener("pointercancel", e => this.release(e), true);
    host.canvas.addEventListener("mousedown", e => { if (this.enabled() && e.button === 0) e.stopImmediatePropagation(); }, true);
    window.addEventListener("keydown", e => {
      if (!this.enabled() || e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.ctrlKey || e.metaKey || e.code === "Home") return;
      if (e.code === "KeyF") { this.frameCard(); e.preventDefault(); e.stopImmediatePropagation(); }
      else if (e.code === "Delete" || e.code === "Backspace") { this.edit(edit => { edit.hidden = true; }); e.preventDefault(); e.stopImmediatePropagation(); }
      else if (e.code === "Escape") { this.selected = null; this.refreshFields(); e.stopImmediatePropagation(); }
      else if (["KeyW", "KeyV", "KeyG", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.code)) e.stopImmediatePropagation();
    }, true);
  }

  setActive(active: boolean): void {
    this.active = active; this.gesture = null;
    if (active) this.host.enter();
    this.tick();
  }
  private enabled(): boolean { return this.active && this.host.editable(); }
  private label(text: string, input: HTMLElement): HTMLLabelElement {
    const label = document.createElement("label"); label.style.cssText = "display:grid;gap:4px;margin:0;font-size:12px";
    label.append(document.createTextNode(text), input); return label;
  }
  private button(text: string, action: () => void): HTMLButtonElement {
    const button = document.createElement("button"); button.className = "ed-btn"; button.textContent = text; button.onclick = action; return button;
  }
  private number(label: string, key: "width" | "height" | "rotation" | "curve", min: number, max: number, step: number, scale: number, fallback: number): void {
    const input = document.createElement("input"); input.type = "number"; input.className = "ed-num";
    input.min = String(min); input.max = String(max); input.step = String(step);
    input.onchange = () => {
      const value = Number(input.value);
      if (Number.isFinite(value)) this.edit(edit => { edit[key] = THREE.MathUtils.clamp(value, min, max) / scale; });
      this.refreshFields();
    };
    this.fields.push({ input, key, scale, fallback });
    const row = this.label(label, input); row.style.gridTemplateColumns = "1fr 80px"; row.style.alignItems = "center"; this.panel.append(row);
  }
  private meshFor(patch: string): THREE.Mesh | undefined { return mossCards(this.host.scene).find(mesh => mesh.userData.mossPatch === patch); }
  private currentMesh(): THREE.Mesh | undefined { return this.selected ? this.meshFor(this.selected.patch) : undefined; }
  private currentEdit(): FoliageCardEdit { return this.selected ? this.host.edits()[this.selected.patch]?.[String(this.selected.card)] ?? {} : {}; }
  private edit(change: (edit: FoliageCardEdit) => void): void {
    if (!this.selected || !this.host.editable()) return;
    this.host.begin(); const edits = this.host.edits(), { patch, card } = this.selected;
    const edit = structuredClone(this.currentEdit()); change(edit);
    (edits[patch] ??= {})[String(card)] = edit;
    this.host.changed(); this.refreshFields();
  }
  private refreshFields(): void {
    const mesh = this.currentMesh(), edit = this.currentEdit();
    if (this.selected) this.patch.value = this.selected.patch;
    this.card.disabled = !mesh;
    this.card.max = String(mesh?.geometry.userData.mossFringeCards ?? 1);
    this.card.value = String((this.selected?.card ?? 0) + 1);
    this.status.textContent = mesh ? `Card ${(this.selected?.card ?? 0) + 1} of ${mesh.geometry.userData.mossFringeCards}${edit.hidden ? " · hidden" : ""}` : "Select a moss tuft in the view, or choose a patch.";
    for (const field of this.fields) {
      field.input.disabled = !mesh;
      const value = edit[field.key];
      field.input.value = String(Math.round((typeof value === "number" ? value : field.fallback) * field.scale * 100) / 100);
    }
    this.valueKey = JSON.stringify([this.selected, edit]);
  }
  private step(direction: number): void {
    const mesh = this.currentMesh(); if (!mesh || !this.selected) return;
    this.selected.card = (this.selected.card + direction + mesh.geometry.userData.mossFringeCards) % mesh.geometry.userData.mossFringeCards;
    this.refreshFields(); this.frameCard();
  }
  private worldPoints(mesh: THREE.Mesh): THREE.Vector3[] {
    mesh.updateWorldMatrix(true, false);
    return Array.from({ length: 8 }, (_, i) => new THREE.Vector3().fromBufferAttribute(mesh.geometry.getAttribute("position"), this.selected!.card * 8 + i).applyMatrix4(mesh.matrixWorld));
  }
  private framePatch(): void { const mesh = this.meshFor(this.patch.value); if (mesh?.parent) this.host.frame(new THREE.Box3().setFromObject(mesh.parent)); }
  private frameCard(): void { const mesh = this.currentMesh(); if (mesh) this.host.frame(new THREE.Box3().setFromPoints(this.worldPoints(mesh)).expandByScalar(.08)); }
  private project(point: THREE.Vector3): THREE.Vector2 {
    const p = point.clone().project(this.host.camera()), rect = this.host.canvas.getBoundingClientRect();
    return new THREE.Vector2(rect.left + (p.x + 1) * rect.width / 2, rect.top + (1 - p.y) * rect.height / 2);
  }
  private rayAt(e: PointerEvent): void {
    const rect = this.host.canvas.getBoundingClientRect();
    this.ray.setFromCamera(new THREE.Vector2((e.clientX - rect.left) / rect.width * 2 - 1, 1 - (e.clientY - rect.top) / rect.height * 2), this.host.camera());
  }
  private press(e: PointerEvent): void {
    if (!this.enabled() || e.button !== 0) return;
    e.preventDefault(); e.stopImmediatePropagation(); this.rayAt(e);
    let mesh = this.currentMesh(), point = -1;
    if (mesh && !this.currentEdit().hidden) point = this.worldPoints(mesh).findIndex(p => this.project(p).distanceTo(new THREE.Vector2(e.clientX, e.clientY)) < 9);
    if (point < 0) {
      // Honour rock occlusion and the alpha cutout instead of picking transparent card rectangles.
      const hits = this.ray.intersectObjects(this.host.scene.children, true);
      const hit = hits.find(hit => {
        if (!(hit.object instanceof THREE.Mesh) || !hit.object.visible || !hit.object.userData.mossPatch) return false;
        const material = hit.object.material as THREE.MeshStandardMaterial;
        if (!this.opacity.has(material)) this.opacity.set(material, leafOpacitySampler(material));
        if (hit.uv && this.opacity.get(material)?.(hit.uv) === false) return false;
        return !hits.some(other => other.distance < hit.distance - .002 && other.object instanceof THREE.Mesh && other.object.visible &&
          (Array.isArray(other.object.material) ? other.object.material : [other.object.material]).some(m => m.visible && !m.transparent && m.alphaTest === 0));
      });
      if (!hit) { this.selected = null; this.refreshFields(); return; }
      mesh = hit.object as THREE.Mesh;
      this.selected = { patch: mesh.userData.mossPatch, card: mesh.geometry.userData.faceCards[hit.faceIndex!] };
      this.refreshFields();
    }
    if (!mesh || !this.selected) return;
    const points = this.worldPoints(mesh), origin = point < 0 ? points[2].clone().add(points[3]).multiplyScalar(.5) : points[point];
    const normal = new THREE.Vector3(); this.host.camera().getWorldDirection(normal);
    const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(normal, origin), start = new THREE.Vector3();
    if (!this.ray.ray.intersectPlane(plane, start)) return;
    const edit = structuredClone(this.currentEdit());
    const root = points[2].clone().add(points[3]).multiplyScalar(.5)
      .applyMatrix4(mesh.matrixWorld.clone().invert()).sub(new THREE.Vector3(...(edit.offset ?? [0, 0, 0])));
    this.gesture = { mesh, edit, plane, start, root, point, moved: false };
    this.host.canvas.setPointerCapture(e.pointerId);
  }
  private move(e: PointerEvent): void {
    const gesture = this.gesture; if (!gesture || !this.enabled() || !this.selected) return;
    e.preventDefault(); e.stopImmediatePropagation(); this.rayAt(e);
    const target = new THREE.Vector3(); if (!this.ray.ray.intersectPlane(gesture.plane, target)) return;
    if (target.distanceTo(gesture.start) < .0001) return;
    if (!gesture.moved) { this.host.begin(); gesture.moved = true; }
    const inverse = gesture.mesh.matrixWorld.clone().invert();
    const delta = target.applyMatrix4(inverse).sub(gesture.start.clone().applyMatrix4(inverse));
    const edit = structuredClone(gesture.edit);
    if (gesture.point < 0) {
      // Drag on the actual mound when the pointer meets it, keeping the root attached.
      const parent = gesture.mesh.parent;
      if (parent instanceof THREE.Mesh) {
        const hit = this.ray.intersectObject(parent, false)[0];
        if (hit) {
          // The reference root is captured at press, so multiple pointer events
          // between rendered frames cannot accumulate an extra translation.
          edit.offset = hit.point.clone().applyMatrix4(inverse).sub(gesture.root).toArray();
        } else return;
      } else return;
    } else {
      edit.points ??= Array.from({ length: 8 }, () => [0, 0, 0]);
      edit.points[gesture.point] = new THREE.Vector3(...(edit.points[gesture.point] ?? [0, 0, 0])).add(delta).toArray();
    }
    (this.host.edits()[this.selected.patch] ??= {})[String(this.selected.card)] = edit; this.host.changed();
  }
  private release(e: PointerEvent): void {
    if (!this.gesture) return;
    this.gesture = null;
    if (this.host.canvas.hasPointerCapture(e.pointerId)) this.host.canvas.releasePointerCapture(e.pointerId);
    this.refreshFields();
  }
  tick(): void {
    const enabled = this.enabled(); this.panel.style.display = enabled ? "" : "none"; this.overlay.style.display = enabled ? "" : "none";
    if (!this.host.editable()) { this.gesture = null; return; }
    applyMossCardEdits(this.host.scene, this.host.edits());
    if (!enabled) return;
    const meshes = mossCards(this.host.scene), key = meshes.map(mesh => mesh.userData.mossPatch).join("|");
    if (key !== this.listKey) {
      this.listKey = key; this.patch.replaceChildren(new Option("Choose moss patch…", ""));
      meshes.forEach(mesh => this.patch.add(new Option(mesh.userData.mossPatch, mesh.userData.mossPatch)));
      this.refreshFields();
    }
    if (this.valueKey !== JSON.stringify([this.selected, this.currentEdit()]) && !this.gesture) this.refreshFields();
    this.overlay.replaceChildren();
    const mesh = this.currentMesh(); if (!mesh || this.currentEdit().hidden) return;
    const points = this.worldPoints(mesh), camera = this.host.camera();
    if (points.some(p => { const z = p.clone().project(camera).z; return z < -1 || z > 1; })) return;
    const projected = points.map(p => this.project(p));
    const path = document.createElementNS(this.overlay.namespaceURI, "polyline");
    path.setAttribute("points", [0, 1, 3, 5, 7, 6, 4, 2, 0].map(i => `${projected[i].x},${projected[i].y}`).join(" "));
    path.setAttribute("fill", "none"); path.setAttribute("stroke", "#ffc06b"); path.setAttribute("stroke-width", "1.5"); this.overlay.append(path);
    projected.forEach(p => { const dot = document.createElementNS(this.overlay.namespaceURI, "circle"); dot.setAttribute("cx", String(p.x)); dot.setAttribute("cy", String(p.y)); dot.setAttribute("r", "4"); dot.setAttribute("fill", "#ffc06b"); dot.setAttribute("stroke", "#202630"); this.overlay.append(dot); });
  }
}
