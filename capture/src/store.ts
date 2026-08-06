import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { collectSessionMessages, type Rec, type SessionMsg } from "./usage.ts";

/** Agent/host id for a message. Known CLI snapshots use claude|codex|opencode|gemini; live capture accepts any string. */
export type AgentId = Rec["tool"] | "live" | (string & {});

export interface StoredMessage {
  id: string;
  ts: string;
  day: string;
  tool: AgentId;
  sessionId: string;
  role: "user" | "assistant" | "system";
  text: string;
  source: "snapshot" | "live";
}

/** Normalize free-form agent/host names from any MCP client. */
export function normalizeAgentId(raw?: string): string {
  const s = (raw ?? "").trim().toLowerCase().replace(/[^a-z0-9._+-]+/g, "-").replace(/^-+|-+$/g, "");
  return s || "live";
}

export interface ConversationStore {
  schema: "proto-capture-conversations/1";
  updatedAt: string;
  path: string;
  count: number;
  messages: StoredMessage[];
}

const PACKAGE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
/** Global default when installed via `npm install -g` — not tied to a project folder. */
export const HOME_STORE_PATH = join(homedir(), ".proto-capture", "conversations.json");
/** Dev checkout convenience: Proto2/data/capture when running from source tree. */
const DEV_STORE_PATH = join(PACKAGE_ROOT, "..", "data", "capture", "conversations.json");

function resolveDefaultStorePath(): string {
  // Prefer in-repo store only when this package clearly lives under a Proto2 checkout.
  if (existsSync(join(PACKAGE_ROOT, "..", "main.py")) && existsSync(join(PACKAGE_ROOT, "..", "data"))) {
    return DEV_STORE_PATH;
  }
  return HOME_STORE_PATH;
}

export const DEFAULT_STORE_PATH = resolveDefaultStorePath();

function messageId(parts: {
  tool: string;
  sessionId: string;
  role: string;
  ts: string;
  text: string;
  source: string;
}): string {
  return createHash("sha256")
    .update(`${parts.tool}|${parts.sessionId}|${parts.role}|${parts.ts}|${parts.source}|${parts.text}`)
    .digest("hex")
    .slice(0, 16);
}

function fromSessionMsg(msg: SessionMsg): StoredMessage {
  const base = {
    tool: msg.tool,
    sessionId: msg.sessionId,
    role: msg.role,
    ts: msg.ts,
    text: msg.text,
    source: "snapshot" as const,
  };
  return { id: messageId(base), day: msg.day, ...base };
}

export function storePath(override?: string): string {
  if (override?.trim()) return override.trim();
  if (process.env.PROTO_CAPTURE_STORE?.trim()) return process.env.PROTO_CAPTURE_STORE.trim();
  return DEFAULT_STORE_PATH;
}

export function readStore(path = storePath()): ConversationStore {
  if (!existsSync(path)) {
    return {
      schema: "proto-capture-conversations/1",
      updatedAt: new Date(0).toISOString(),
      path,
      count: 0,
      messages: [],
    };
  }
  try {
    const raw = JSON.parse(readFileSync(path, "utf8")) as Partial<ConversationStore>;
    const messages = Array.isArray(raw.messages) ? (raw.messages as StoredMessage[]) : [];
    return {
      schema: "proto-capture-conversations/1",
      updatedAt: typeof raw.updatedAt === "string" ? raw.updatedAt : new Date(0).toISOString(),
      path,
      count: messages.length,
      messages,
    };
  } catch {
    return {
      schema: "proto-capture-conversations/1",
      updatedAt: new Date(0).toISOString(),
      path,
      count: 0,
      messages: [],
    };
  }
}

function writeStore(store: ConversationStore): ConversationStore {
  mkdirSync(dirname(store.path), { recursive: true });
  const next: ConversationStore = {
    ...store,
    schema: "proto-capture-conversations/1",
    updatedAt: new Date().toISOString(),
    count: store.messages.length,
  };
  writeFileSync(store.path, JSON.stringify(next, null, 2) + "\n", { mode: 0o600 });
  return next;
}

/** Replace snapshot rows from agent stores; keep live-appended rows. */
export async function snapshotConversations(path = storePath()): Promise<ConversationStore> {
  const existing = readStore(path);
  const live = existing.messages.filter((m) => m.source === "live");
  const snap = (await collectSessionMessages()).map(fromSessionMsg);
  const byId = new Map<string, StoredMessage>();
  for (const m of snap) byId.set(m.id, m);
  for (const m of live) byId.set(m.id, m);
  const messages = [...byId.values()].sort((a, b) => a.ts.localeCompare(b.ts) || a.id.localeCompare(b.id));
  return writeStore({ ...existing, path, messages });
}

export function appendLiveMessage(input: {
  text: string;
  role?: "user" | "assistant" | "system";
  /** Any agent/host name (cursor, claude, copilot, windsurf, custom, …). */
  tool?: string;
  sessionId?: string;
  ts?: string;
  path?: string;
}): ConversationStore {
  const text = input.text.trim();
  if (!text) throw new Error("text is required");
  const path = storePath(input.path);
  const store = readStore(path);
  const ts = input.ts && !Number.isNaN(Date.parse(input.ts)) ? new Date(input.ts).toISOString() : new Date().toISOString();
  const base = {
    tool: normalizeAgentId(input.tool),
    sessionId: input.sessionId?.trim() || "live",
    role: input.role ?? "user",
    ts,
    text,
    source: "live" as const,
  };
  const message: StoredMessage = { id: messageId(base), day: ts.slice(0, 10), ...base };
  const messages = store.messages.filter((m) => m.id !== message.id);
  messages.push(message);
  messages.sort((a, b) => a.ts.localeCompare(b.ts) || a.id.localeCompare(b.id));
  return writeStore({ ...store, path, messages });
}

export function conversationStatus(path = storePath()): {
  schema: "proto-capture-conversations/1";
  path: string;
  exists: boolean;
  count: number;
  liveCount: number;
  snapshotCount: number;
  updatedAt: string;
} {
  const store = readStore(path);
  return {
    schema: "proto-capture-conversations/1",
    path: store.path,
    exists: existsSync(path),
    count: store.count,
    liveCount: store.messages.filter((m) => m.source === "live").length,
    snapshotCount: store.messages.filter((m) => m.source === "snapshot").length,
    updatedAt: store.updatedAt,
  };
}
