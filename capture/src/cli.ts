#!/usr/bin/env node
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";
import {
  appendLiveMessage,
  conversationStatus,
  DEFAULT_STORE_PATH,
  HOME_STORE_PATH,
  snapshotConversations,
  storePath,
} from "./store.ts";
import { runMcpServer } from "./mcp.ts";
import packageJson from "../package.json" with { type: "json" };

const VERSION = packageJson.version;
const PACKAGE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const argv = process.argv.slice(2);
const command = argv.find((a) => !a.startsWith("-")) ?? "help";

function flag(name: string): string | undefined {
  const i = argv.indexOf(`--${name}`);
  if (i < 0) return undefined;
  const next = argv[i + 1];
  return next && !next.startsWith("--") ? next : "true";
}
function has(name: string): boolean {
  return argv.includes(`--${name}`);
}

async function main(): Promise<void> {
  if (has("version") || has("v") || command === "version") {
    console.log(VERSION);
    return;
  }

  if (command === "mcp") {
    runMcpServer(VERSION);
    return;
  }

  if (command === "status") {
    console.log(JSON.stringify(conversationStatus(storePath(flag("out"))), null, 2));
    return;
  }

  if (command === "record") {
    // Debug / hook helper: snapshot agent stores into the JSON file.
    const store = await snapshotConversations(storePath(flag("out")));
    console.log(JSON.stringify({ ok: true, path: store.path, count: store.count, updatedAt: store.updatedAt }));
    return;
  }

  if (command === "append") {
    const text = flag("text") ?? "";
    const store = appendLiveMessage({
      text,
      role: (flag("role") as "user" | "assistant" | "system" | undefined) ?? "user",
      tool: (flag("tool") as "claude" | "codex" | "opencode" | "gemini" | "live" | undefined) ?? "live",
      sessionId: flag("session") ?? "live",
      path: flag("out"),
    });
    console.log(JSON.stringify({ ok: true, path: store.path, count: store.count }));
    return;
  }

  if (command === "skill") {
    if (!argv.includes("install")) {
      console.log("Usage: proto-capture skill install [--claude] [--codex] [--gemini] [--force]");
      return;
    }
    const source = join(PACKAGE_ROOT, "skills", "proto-capture");
    if (!existsSync(source)) {
      console.error("proto-capture skill missing from package.");
      process.exit(1);
    }
    const selected = has("claude") || has("codex") || has("gemini");
    const targets = [
      ...(!selected || has("claude") ? [join(homedir(), ".claude", "skills", "proto-capture")] : []),
      ...(!selected || has("codex")
        ? [join(process.env.CODEX_HOME || join(homedir(), ".codex"), "skills", "proto-capture")]
        : []),
      ...(!selected || has("gemini")
        ? [join(process.env.GEMINI_CLI_HOME || homedir(), ".gemini", "skills", "proto-capture")]
        : []),
    ];
    for (const target of targets) {
      if (existsSync(target) && !has("force")) {
        console.error(`${target} already exists. Re-run with --force to update.`);
        continue;
      }
      mkdirSync(dirname(target), { recursive: true });
      cpSync(source, target, { recursive: true, force: has("force") });
      console.log(`Installed proto-capture skill at ${target}`);
    }
    return;
  }

  if (command === "hook") {
    // Re-exec hook-cli logic in-process via spawning the sibling bundle when present.
    const mode = argv.find((a, i) => i > 0 && !a.startsWith("-") && a !== "hook") ?? "prompt";
    const hookJs = join(PACKAGE_ROOT, "dist", "hook-cli.js");
    if (!existsSync(hookJs)) {
      console.error("hook-cli.js missing — run npm run build");
      process.exit(1);
    }
    const { spawnSync } = await import("node:child_process");
    const r = spawnSync(process.execPath, [hookJs, mode], { stdio: "inherit", env: process.env });
    process.exit(r.status ?? 1);
  }

  if (command === "doctor" || command === "mcp-config") {
    const active = storePath();
    console.log(`proto-capture v${VERSION}`);
    console.log(`package: ${PACKAGE_ROOT}`);
    console.log(`store (active): ${active}`);
    console.log(`store (home default): ${HOME_STORE_PATH}`);
    console.log(`store (dev default):  ${DEFAULT_STORE_PATH}`);
    console.log("");
    console.log("Add this to any agent MCP config (no project folder path required):");
    console.log(
      JSON.stringify(
        {
          mcpServers: {
            "proto-capture": {
              command: "proto-capture",
              args: ["mcp"],
            },
          },
        },
        null,
        2,
      ),
    );
    console.log("");
    console.log("Install / update locally:");
    console.log("  cd capture && npm run install:local");
    return;
  }

  console.log(`proto-capture v${VERSION}

Commands:
  mcp                 Run conversation MCP server (stdio)
  status [--out p]    Show store path and counts
  record [--out p]    Debug: snapshot agent stores into JSON
  append --text t     Debug/hooks: append one live message
  hook <mode>         Cursor hook entry (sessionStart|prompt|response|stop)
  skill install       Install Agent Skill for Claude/Codex/Gemini
  doctor              Show paths + copy-paste MCP config

Env:
  PROTO_CAPTURE_STORE   Override conversations.json path
`);
}

void main();
