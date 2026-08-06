#!/usr/bin/env node
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";
import {
  feedbackRoot,
  getFeedback,
  getSkill,
  listSkills,
  matchSkills,
  skillsRoot,
  skillsStatus,
} from "./catalog.ts";
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
    console.log(JSON.stringify(skillsStatus(), null, 2));
    return;
  }

  if (command === "list") {
    console.log(JSON.stringify(listSkills(), null, 2));
    return;
  }

  if (command === "match") {
    const query = flag("query") ?? argv.filter((a) => !a.startsWith("-") && a !== "match").join(" ");
    const limit = Number(flag("limit") ?? "5");
    console.log(JSON.stringify(matchSkills(query, Number.isFinite(limit) ? limit : 5), null, 2));
    return;
  }

  if (command === "get") {
    const name = flag("name") ?? argv.find((a, i) => i > 0 && !a.startsWith("-") && a !== "get");
    if (!name) {
      console.error("Usage: proto-skills get --name <slug>");
      process.exit(1);
    }
    console.log(
      JSON.stringify(
        getSkill(name, {
          includeReferences: has("references"),
          includeScripts: has("scripts"),
        }),
        null,
        2,
      ),
    );
    return;
  }

  if (command === "feedback") {
    console.log(JSON.stringify(getFeedback(flag("date")), null, 2));
    return;
  }

  if (command === "skill") {
    if (!argv.includes("install")) {
      console.log("Usage: proto-skills skill install [--claude] [--codex] [--gemini] [--force]");
      return;
    }
    const source = join(PACKAGE_ROOT, "skills", "proto-skills");
    if (!existsSync(source)) {
      console.error("proto-skills skill missing from package.");
      process.exit(1);
    }
    const selected = has("claude") || has("codex") || has("gemini");
    const targets = [
      ...(!selected || has("claude") ? [join(homedir(), ".claude", "skills", "proto-skills")] : []),
      ...(!selected || has("codex")
        ? [join(process.env.CODEX_HOME || join(homedir(), ".codex"), "skills", "proto-skills")]
        : []),
      ...(!selected || has("gemini")
        ? [join(process.env.GEMINI_CLI_HOME || homedir(), ".gemini", "skills", "proto-skills")]
        : []),
    ];
    for (const target of targets) {
      if (existsSync(target) && !has("force")) {
        console.error(`${target} already exists. Re-run with --force to update.`);
        continue;
      }
      mkdirSync(dirname(target), { recursive: true });
      cpSync(source, target, { recursive: true, force: has("force") });
      console.log(`Installed proto-skills skill at ${target}`);
    }
    return;
  }

  if (command === "doctor" || command === "mcp-config") {
    console.log(`proto-skills v${VERSION}`);
    console.log(`package: ${PACKAGE_ROOT}`);
    console.log(`skills root: ${skillsRoot()}`);
    console.log(`feedback root: ${feedbackRoot()}`);
    console.log("");
    console.log("Add this to any agent MCP config:");
    console.log(
      JSON.stringify(
        {
          mcpServers: {
            "proto-skills": {
              command: "proto-skills",
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
    console.log("  cd skills-mcp && npm run install:local");
    return;
  }

  console.log(`proto-skills v${VERSION}

Commands:
  mcp                 Run skills MCP server (stdio)
  status              Show skills/feedback paths and counts
  list                List catalog skills
  match --query t     Rank skills for a request
  get --name slug     Load SKILL.md
  feedback [--date d] Load daily reinforcement feedback
  skill install       Install Agent Skill for Claude/Codex/Gemini
  doctor              Show paths + copy-paste MCP config

Env:
  PROTO_SKILLS_ROOT     Override data/skills path
  PROTO_FEEDBACK_ROOT   Override feedback markdown folder
`);
}

void main();
