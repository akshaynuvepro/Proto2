#!/usr/bin/env node
/** Smoke-test the globally installed `proto-capture mcp` (not dist/cli.js directly). */
import { spawn, execSync } from "node:child_process";
import { createInterface } from "node:readline";
import { existsSync, readFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function whichProtoCapture() {
  try {
    if (process.platform === "win32") {
      return execSync("where proto-capture", { encoding: "utf8" }).trim().split(/\r?\n/)[0];
    }
    return execSync("which proto-capture", { encoding: "utf8" }).trim();
  } catch {
    return null;
  }
}

const bin = whichProtoCapture();
if (!bin) {
  console.error("FAIL  proto-capture not on PATH — run: cd capture && npm run install:local");
  process.exit(1);
}

const storeDir = mkdtempSync(join(tmpdir(), "proto-capture-smoke-"));
const store = join(storeDir, "conversations.json");

const child = spawn(bin, ["mcp"], {
  stdio: ["pipe", "pipe", "pipe"],
  env: { ...process.env, PROTO_CAPTURE_STORE: store },
  shell: process.platform === "win32",
});

const rl = createInterface({ input: child.stdout });
let nextId = 1;
const pending = new Map();

function rpc(method, params = {}) {
  const id = nextId++;
  return new Promise((resolvePromise, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`timeout: ${method}`));
    }, 30_000);
    pending.set(id, {
      resolve: (v) => {
        clearTimeout(timer);
        resolvePromise(v);
      },
      reject: (e) => {
        clearTimeout(timer);
        reject(e);
      },
    });
    child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n");
  });
}
function notify(method, params = {}) {
  child.stdin.write(JSON.stringify({ jsonrpc: "2.0", method, params }) + "\n");
}

rl.on("line", (line) => {
  if (!line.trim()) return;
  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    return;
  }
  if (msg.id != null && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(JSON.stringify(msg.error)));
    else resolve(msg.result);
  }
});

const results = [];
const pass = (name, ok, detail) => {
  results.push([name, ok, detail]);
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}`);
  if (detail !== undefined) console.log("       ", typeof detail === "string" ? detail : JSON.stringify(detail));
};

try {
  pass("global binary found", true, bin);

  const init = await rpc("initialize", {
    protocolVersion: "2025-06-18",
    capabilities: {},
    clientInfo: { name: "global-smoke", version: "1" },
  });
  pass("initialize", init.serverInfo?.name === "proto-capture", init.serverInfo);
  notify("notifications/initialized", {});
  await new Promise((r) => setTimeout(r, 800));

  const tools = await rpc("tools/list", {});
  const names = (tools.tools || []).map((t) => t.name).sort();
  pass(
    "tools/list",
    ["conversation_status", "record_conversations", "record_message"].every((n) => names.includes(n)),
    names,
  );

  const r1 = await rpc("tools/call", {
    name: "record_message",
    arguments: { text: "global-smoke user", role: "user", tool: "live", sessionId: "g1" },
  });
  const t1 = r1?.content?.[0]?.text || "";
  pass("record_message user", t1.includes('"ok":true') || t1.includes('"ok": true'), t1.slice(0, 160));

  const r2 = await rpc("tools/call", {
    name: "record_message",
    arguments: { text: "global-smoke assistant", role: "assistant", tool: "live", sessionId: "g1" },
  });
  const t2 = r2?.content?.[0]?.text || "";
  pass("record_message assistant", t2.includes('"ok":true') || t2.includes('"ok": true'), t2.slice(0, 160));

  const r3 = await rpc("tools/call", { name: "record_conversations", arguments: {} });
  const t3 = r3?.content?.[0]?.text || "";
  pass("record_conversations", t3.includes('"ok":true') || t3.includes('"ok": true'), t3.slice(0, 200));

  const r4 = await rpc("tools/call", { name: "conversation_status", arguments: {} });
  const st = JSON.parse(r4?.content?.[0]?.text || "{}");
  pass("conversation_status count>=2", (st.count || 0) >= 2, st);

  pass("store file exists", existsSync(store), store);
  const file = JSON.parse(readFileSync(store, "utf8"));
  pass("store messages>=2", (file.messages || []).length >= 2, { count: file.messages?.length, path: file.path });

  // unknown tool should error softly
  const bad = await rpc("tools/call", { name: "usage_summary", arguments: {} });
  const badText = bad?.content?.[0]?.text || "";
  pass("unknown tool rejected", badText.includes("Unknown tool") || bad?.isError, badText.slice(0, 120));

  child.kill();
  rmSync(storeDir, { recursive: true, force: true });
  const failed = results.filter(([, ok]) => !ok).length;
  console.log(failed ? `\n${failed} failed` : "\nAll global MCP checks passed");
  process.exit(failed ? 1 : 0);
} catch (e) {
  console.error("FATAL", e);
  child.kill();
  rmSync(storeDir, { recursive: true, force: true });
  process.exit(1);
}
