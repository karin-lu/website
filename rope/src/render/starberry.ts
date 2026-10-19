// A berry vine on a 2D canvas: the canvas renderer's own, and the editor's
// overlay. The same poses the 3D layer draws (`render3d/starberryVisual.ts`),
// flattened - there is no depth here, so the cord set back behind the plane
// in 3D is simply drawn first, under its stalks and berries.

import { Vec2 } from "../engine/vec2";
import { berrySide, restStarberries } from "../level/starberry";
import type { VineCord } from "../level/vines";
import {
  BERRY_CORD_COLOR,
  STALK_RADIUS,
  berryCordRadius,
  naturalStemPoint,
  roundBerryAttachment,
  stemFraction,
} from "./starberryArt";

// The standard vine's three leaf greens (`render3d/vineVisual.ts`), in sRGB.
const CAP_GREENS = ["#3c7048", "#619047", "#82954d"];

// One leaf of a berry's cap in the berry's own frame (the stalk up, -y): from
// the top of a berry `r` across to its tip at (`tipX`, `tipY`), `width` across
// at its widest, the tip turned up by `curl`. Filled and edged.
function capLeaf(
  ctx: CanvasRenderingContext2D,
  r: number,
  tipX: number,
  tipY: number,
  width: number,
  curl: number,
  fill: string,
): void {
  const baseY = -r * 1.04;
  const dx = tipX;
  const dy = tipY - baseY;
  const length = Math.hypot(dx, dy) || 1;
  // Across the leaf, and its widest point a third of the way along it.
  const nx = -dy / length;
  const ny = dx / length;
  const midX = dx * 0.38;
  const midY = baseY + dy * 0.38;
  const tx = tipX + Math.sign(tipX || 1) * Math.abs(curl);
  const ty = tipY - Math.abs(curl);
  const paint = ctx.createLinearGradient(0, baseY, tx, ty);
  paint.addColorStop(0, "#3e6342");
  paint.addColorStop(0.45, fill);
  paint.addColorStop(1, "#a0ad61");
  ctx.fillStyle = paint;
  ctx.beginPath();
  ctx.moveTo(0, baseY);
  ctx.quadraticCurveTo(midX + nx * width, midY + ny * width, tx, ty);
  ctx.quadraticCurveTo(midX - nx * width, midY - ny * width, 0, baseY);
  ctx.fill();
}

export function drawStarberry(ctx: CanvasRenderingContext2D, vine: VineCord, alpha: number): void {
  const settings = vine.starberry;
  if (!settings) return;
  const path: Vec2[] = [];
  vine.path(alpha, path);
  if (path.length < 2) return;
  const berries = vine.berryPoses?.(alpha) ?? restStarberries(path, settings);
  ctx.save();
  ctx.lineCap = "round";

  // The cord: one strand, tapering.
  let length = 0;
  for (let i = 1; i < path.length; i++) length += path[i]!.distanceTo(path[i - 1]!);
  const segments = Math.max(8, Math.min(350, Math.ceil(length / 0.045)));
  ctx.strokeStyle = BERRY_CORD_COLOR;
  for (let i = 0; i < segments; i++) {
    const a = naturalStemPoint(path, i / segments, settings.seed);
    const b = naturalStemPoint(path, (i + 1) / segments, settings.seed);
    ctx.lineWidth = 2 * berryCordRadius((i + 0.5) / segments, settings.seed);
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  }


  // The stalks and berries.
  for (const [i, berry] of berries.entries()) {
    const root = naturalStemPoint(path, stemFraction(path, berry.root), settings.seed);
    const attachment = roundBerryAttachment(root, berry.fruit, berry.radius);
    const axis = attachment.axis;
    const end = attachment.end;
    const side = berrySide(i, settings);
    ctx.lineWidth = 2 * STALK_RADIUS;
    // The cord's own brown: a stalk is the vine's growth, and the leaves are
    // the only green.
    ctx.strokeStyle = BERRY_CORD_COLOR;
    ctx.beginPath();
    ctx.moveTo(root.x, root.y);
    ctx.bezierCurveTo(
      root.x + (end.x - root.x) * 0.25 + side * 0.025,
      root.y - 0.055,
      attachment.control.x,
      attachment.control.y,
      end.x,
      end.y,
    );
    ctx.stroke();
    // karin's round berry, coloured as the 3D one is: dark translucent amber
    // with a faint light at its heart...
    const { x, y } = berry.fruit;
    const r = berry.radius;
    ctx.save();
    ctx.beginPath();
    ctx.ellipse(x + axis.x * r * 0.07, y + axis.y * r * 0.07, r * 1.04, r * 0.93, Math.atan2(axis.x, -axis.y), 0, Math.PI * 2);
    ctx.clip();
    const body = ctx.createRadialGradient(x, y, 0, x, y, r);
    body.addColorStop(0, berry.held ? "#f7c46a" : "#f4b45e");
    body.addColorStop(0.3, "#e8a55c");
    body.addColorStop(0.75, "#e2a74b");
    body.addColorStop(1, "#c18a36");
    ctx.fillStyle = body;
    ctx.fillRect(x - r * 1.1, y - r * 1.1, r * 2.2, r * 2.2);
    ctx.restore();
    // ...under its cap, seen side on: the 3D cap's outer leaves first,
    // running down over the shoulder, then the shorter inner ones over their
    // bases, each its own length, spread and green and edged a shade darker
    // so the overlaps read - a different cap on every berry.
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(Math.atan2(axis.x, -axis.y));
    ctx.lineWidth = r * 0.03;
    ctx.strokeStyle = "#2f3c1a";
    const random = (leaf: number, salt: number): number => {
      const n = Math.sin((settings.seed * 0.0137 + i * 7.31) * 127.1 + (leaf * 1.73 + salt) * 311.7) * 43758.5453;
      return n - Math.floor(n);
    };
    const n = 5;
    for (let leaf = 0; leaf < n; leaf++) {
      const spread = ((leaf / (n - 1)) * 2 - 1) + (random(leaf, 3) - 0.5) * 0.12;
      const length = 0.95 + 0.08 * random(leaf, 4);
      const tone = CAP_GREENS[random(leaf, 5) < 0.25 ? 0 : random(leaf, 5) < 0.7 ? 1 : 2]!;
      capLeaf(
        ctx,
        r,
        spread * r * length * 1.2,
        -r * (1.04 - length * (0.55 + 0.25 * (1 - Math.abs(spread)))),
        r * 0.30 * (0.95 + 0.1 * random(leaf, 6)),
        0.08 * r * (spread || 1),
        tone,
      );
    }
    ctx.restore();
  }
  ctx.restore();
}
