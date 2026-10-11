import { Vector3 } from "three";

// Small render-only damped spring driven by motion of a fixed leaf attachment.
// The explicit simulation clock freezes it on pause and resets it on seek.
export class VineLeafLag {
  readonly offset = new Vector3();
  private readonly velocity = new Vector3();
  private readonly root = new Vector3();
  private time = NaN;
  private readonly scratch = new Vector3();

  update(root: Vector3, time: number, length: number): Vector3 {
    const dt = time - this.time, moved = this.root.distanceTo(root);
    if (!Number.isFinite(dt) || dt < 0 || dt > .1 || moved > .5 || (dt === 0 && moved > 1e-8)) {
      this.offset.set(0, 0, 0); this.velocity.set(0, 0, 0);
    } else if (dt > 0) {
      this.offset.addScaledVector(this.scratch.subVectors(root, this.root), -.5);
      const decay = Math.exp(-7.5 * dt), frequency = Math.sqrt(100 - 7.5 * 7.5);
      const c = Math.cos(frequency * dt), s = Math.sin(frequency * dt) / frequency;
      this.scratch.copy(this.velocity).addScaledVector(this.offset, 7.5);
      this.velocity.multiplyScalar(c - 7.5 * s).addScaledVector(this.offset, -100 * s).multiplyScalar(decay);
      this.offset.multiplyScalar(c).addScaledVector(this.scratch, s).multiplyScalar(decay);
      this.offset.clampLength(0, length * .18);
    }
    this.root.copy(root); this.time = time;
    return this.offset;
  }
}
