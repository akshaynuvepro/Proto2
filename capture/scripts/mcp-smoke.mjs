#!/usr/bin/env node
/** End-to-end MCP stdio smoke test for proto-capture. */
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync, readFileSync } from "node:fs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const cli = resolve(root, "dist", "cli.js");
const store = resolve(root, "..", "data", "capture", "conversations.json");

if (!existsSync(cli)) {
  console.error("Missing dist/cli.js — run npm run build in capture/");
  process.exit(1);
}

const child = spawn(process.execPath, [cli, "mcp"], {
  stdio: ["pipe", "pipe", "pipe"],
  env: { ...process.env, PROTO_CAPTURE_STORE: store },
});

const rl = createInterface({ input: child.stdout });
let nextId = 1;
const pending = new Map();

function rpc(method, params = {}) {
  const id = nextId++;
  const msg = JSON.stringify({ jsonrpc: "2.0", id, method, params });
  return new Promise((resolvePromise, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`timeout waiting for ${method}`));
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
    child.stdin.write(msg + "\n");
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
    console.error("non-json stdout:", line.slice(0, 200));
    return;
  }
  if (msg.id != null && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(JSON.stringify(msg.error)));
    else resolve(msg.result);
  }
});

child.stderr.on("data", (buf) => {
  const t = buf.toString().trim();
  if (t) console.error("[mcp stderr]", t);
});

const results = [];

try {
  const init = await rpc("initialize", {
    protocolVersion: "2025-06-18",
    capabilities: {},
    clientInfo: { name: "proto2-smoke", version: "0.1.0" },
  });
  results.push(["initialize", init.serverInfo?.name === "proto-capture", init.serverInfo]);
  notify("notifications/initialized", {});

  // Give on-connect snapshot a moment.
  await new Promise((r) => setTimeout(r, 1500));

  const tools = await rpc("tools/list", {});
  const names = (tools.tools || []).map((t) => t.name).sort();
  const expected = ["conversation_status", "record_conversations", "record_message"];
  results.push(["tools/list", expected.every((n) => names.includes(n)), names]);

  const live = await rpc("tools/call", {
    name: "record_message",
    arguments: {
      text: "Smoke test user prompt: verify proto-capture MCP wiring",
      role: "user",
      tool: "live",
      sessionId: "smoke-session-1",
    },
  });
  const liveText = live?.content?.[0]?.text || "";
  const liveOk = liveText.includes('"ok":true') || liveText.includes('"ok": true');
  results.push(["record_message user", liveOk, liveText.slice(0, 180)]);

  const assistant = await rpc("tools/call", {
    name: "record_message",
    arguments: {
      text: "Smoke test assistant reply: MCP record_message works.",
      role: "assistant",
      tool: "live",
      sessionId: "smoke-session-1",
    },
  });
  const aText = assistant?.content?.[0]?.text || "";
  results.push(["record_message assistant", aText.includes('"ok":true') || aText.includes('"ok": true'), aText.slice(0, 180)]);

  const snap = await rpc("tools/call", {
    name: "record_conversations",
    arguments: {},
  });
  const sText = snap?.content?.[0]?.text || "";
  results.push(["record_conversations", sText.includes('"ok": true') || sText.includes('"ok":true'), sText.slice(0, 220)]);

  const status = await rpc("tools/call", {
    name: "conversation_status",
    arguments: {},
  });
  const st = status?.content?.[0]?.text || "";
  let statusJson = {};
  try {
    statusJson = JSON.parse(st);
  } catch {
    /* ignore */
  }
  results.push(["conversation_status", (statusJson.count || 0) >= 2, statusJson]);

  const onDisk = existsSync(store);
  let fileCount = 0;
  if (onDisk) {
    const raw = JSON.parse(readFileSync(store, "utf8"));
    fileCount = (raw.messages || []).length;
  }
  results.push(["store file", onDisk && fileCount >= 2, { path: store, count: fileCount }]);

  let failed = 0;
  for (const [name, ok, detail] of results) {
    console.log(`${ok ? "PASS" : "FAIL"}  ${name}`);
    if (!ok) {
      failed++;
      console.log("       ", detail);
    } else if (typeof detail === "object") {
      console.log("       ", JSON.stringify(detail));
    }
  }
  child.kill();
  process.exit(failed ? 1 : 0);
} catch (e) {
  console.error("FATAL", e);
  child.kill();
  process.exit(1);
}
