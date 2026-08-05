import { rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outdir = resolve(root, "dist");

rmSync(outdir, { recursive: true, force: true });

await build({
  entryPoints: [resolve(root, "src/cli.ts"), resolve(root, "src/hook-cli.ts")],
  outdir,
  bundle: true,
  platform: "node",
  format: "esm",
  target: "node18",
  external: ["bun:sqlite", "node:sqlite"],
  sourcemap: false,
  legalComments: "none",
});
// npm's global bin shim launches this with `node`; do not prepend a shebang
// into ESM output (it becomes a syntax error if not byte-0).

console.log("built dist/cli.js and dist/hook-cli.js");
