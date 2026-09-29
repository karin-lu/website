// Presentation-only QA montage; retain the unmodified full-sized screenshots.
import { resolve } from "node:path";
import sharp from "sharp";
const variant = "river-dream-v5";
const folder = resolve(`artifacts/background-runtime/sunken-grotto${variant.slice("river-dream".length)}`);
const panels = [];
for (const [index, frame] of [0, 120, 240, 360].entries()) {
  const file = resolve(folder, `motion-f${frame}-h2.png`);
  const label = Buffer.from(`<svg width="960" height="570"><rect y="540" width="960" height="30" fill="#11151a"/><text x="12" y="561" fill="#dae3e9" font-family="sans-serif" font-size="16">Settled time sample · frame ${frame} · held input 2 · gameplay camera</text></svg>`);
  const input = await sharp({ create: { width: 960, height: 570, channels: 4, background: "#11151a" } })
    .composite([{ input: await sharp(file).resize(960, 540).png().toBuffer(), left: 0, top: 0 }, { input: label, left: 0, top: 0 }]).png().toBuffer();
  panels.push({ input, left: (index % 2) * 960, top: Math.floor(index / 2) * 570 });
}
const out = resolve(folder, "motion-filmstrip.png");
await sharp({ create: { width: 1920, height: 1140, channels: 4, background: "#11151a" } }).composite(panels).png().toFile(out);
console.log(out);
