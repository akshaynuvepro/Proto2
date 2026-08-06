import { createInterface } from "node:readline";
import {
  feedbackRoot,
  getFeedback,
  getSkill,
  listSkills,
  matchSkills,
  skillsRoot,
  skillsStatus,
} from "./catalog.ts";

interface JsonRpcMessage {
  jsonrpc?: string;
  id?: number | string | null;
  method?: string;
  params?: {
    protocolVersion?: string;
    name?: string;
    arguments?: Record<string, unknown>;
  };
}

const PROTOCOL_VERSION = "2025-06-18";

const INSTRUCTIONS =
  "Proto Skills serves Proto2 skill packages and daily reinforcement feedback. " +
  "For a user/sandbox request: call match_skill, then get_skill for the best match. " +
  "At session start, optionally call get_feedback and follow its behavior rules. " +
  "Do not invent conflicting instructions. Skills are local/read-only.";

const TOOLS = [
  {
    name: "list_skills",
    description: "List available Proto2 skills from catalog.json (name, description, triggers, tags).",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
  },
  {
    name: "match_skill",
    description:
      "Rank skills for a user/sandbox request using keyword overlap on name/description/triggers/tags. Returns top matches with scores.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "User or sandbox request text" },
        limit: { type: "number", description: "Max matches (default 5)" },
      },
      required: ["query"],
      additionalProperties: false,
    },
  },
  {
    name: "get_skill",
    description:
      "Load a skill package by name. Returns SKILL.md content; optionally includes references/ and scripts/.",
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string", description: "Skill slug / catalog name" },
        include_references: { type: "boolean", description: "Include references/*.md (default false)" },
        include_scripts: { type: "boolean", description: "Include scripts/* (default false)" },
      },
      required: ["name"],
      additionalProperties: false,
    },
  },
  {
    name: "get_feedback",
    description:
      "Load daily reinforcement feedback markdown. Default date is today (falls back to latest available).",
    inputSchema: {
      type: "object",
      properties: {
        date: { type: "string", description: "YYYY-MM-DD (optional)" },
      },
      additionalProperties: false,
    },
  },
  {
    name: "skills_status",
    description: "Show skills root, catalog count, and available feedback dates.",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
  },
];

function result(id: number | string | null | undefined, value: unknown): string {
  return JSON.stringify({ jsonrpc: "2.0", id: id ?? null, result: value });
}

function rpcError(id: number | string | null | undefined, code: number, message: string): string {
  return JSON.stringify({ jsonrpc: "2.0", id: id ?? null, error: { code, message } });
}

function toolText(payload: unknown, isError = false): unknown {
  return { content: [{ type: "text", text: JSON.stringify(payload, null, 2) }], isError };
}

async function callTool(name: string | undefined, args: Record<string, unknown>): Promise<unknown> {
  if (name === "list_skills") {
    return toolText(listSkills(skillsRoot()));
  }
  if (name === "match_skill") {
    const query = String(args.query ?? "").trim();
    if (!query) return toolText({ ok: false, error: "query is required" }, true);
    const limit = typeof args.limit === "number" && args.limit > 0 ? Math.floor(args.limit) : 5;
    return toolText(matchSkills(query, limit, skillsRoot()));
  }
  if (name === "get_skill") {
    const skillName = String(args.name ?? "").trim();
    if (!skillName) return toolText({ ok: false, error: "name is required" }, true);
    const payload = getSkill(
      skillName,
      {
        includeReferences: Boolean(args.include_references),
        includeScripts: Boolean(args.include_scripts),
      },
      skillsRoot(),
    );
    return toolText(payload, !payload.ok);
  }
  if (name === "get_feedback") {
    const date = typeof args.date === "string" ? args.date : undefined;
    const payload = getFeedback(date, feedbackRoot());
    return toolText(payload, !payload.ok);
  }
  if (name === "skills_status") {
    return toolText(skillsStatus(skillsRoot(), feedbackRoot()));
  }
  return toolText({ error: `Unknown tool "${name}".` }, true);
}

export async function handleMessage(msg: JsonRpcMessage, version: string): Promise<string | null> {
  const { id, method, params } = msg;
  const isNotification = id === undefined;
  try {
    if (method === "initialize") {
      return result(id, {
        protocolVersion: params?.protocolVersion || PROTOCOL_VERSION,
        capabilities: { tools: {} },
        serverInfo: { name: "proto-skills", version },
        instructions: INSTRUCTIONS,
      });
    }
    if (method === "notifications/initialized") return null;
    if (method === "notifications/cancelled") return null;
    if (method === "ping") return result(id, {});
    if (method === "tools/list") return result(id, { tools: TOOLS });
    if (method === "tools/call") {
      const value = await callTool(params?.name, params?.arguments ?? {});
      return result(id, value);
    }
    return isNotification ? null : rpcError(id, -32601, `Method not found: ${method}`);
  } catch (e) {
    return isNotification ? null : rpcError(id, -32603, (e as Error).message);
  }
}

export function runMcpServer(version: string): void {
  const rl = createInterface({ input: process.stdin, terminal: false });
  rl.on("line", (line) => {
    const text = line.trim();
    if (!text) return;
    let msg: JsonRpcMessage;
    try {
      msg = JSON.parse(text) as JsonRpcMessage;
    } catch {
      process.stdout.write(rpcError(null, -32700, "Parse error") + "\n");
      return;
    }
    void handleMessage(msg, version).then((response) => {
      if (response) process.stdout.write(response + "\n");
    });
  });
}
