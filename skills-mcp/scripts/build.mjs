import { rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outdir = resolve(root, "dist");

rmSync(outdir, { recursive: true, force: true });

await build({
  entryPoints: [resolve(root, "src/cli.ts")],
  outdir,
  bundle: true,
  platform: "node",
  format: "esm",
  target: "node18",
  sourcemap: false,
  legalComments: "none",
});

console.log("built dist/cli.js");
