import { existsSync, readFileSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join, basename } from "node:path";

// One deduplicated turn from any supported CLI, reduced to the numbers we care
// about. Usage aggregates never keep prompt/response content, file paths, or
// branch names. User prompts are collected separately as UserMsg (local only).
export interface Rec {
  ts: string;
  day: string; // YYYY-MM-DD
  tool: "claude" | "codex" | "opencode" | "gemini"; // the CLI it came from
  provider: string;
  model: string;
  sessionId: string;
  input: number;
  output: number;
  cacheWrite: number;
  cacheRead: number;
  webSearch: number;
  webFetch: number;
  costUSD?: number;
}

/** Local-only user prompt. Never included in aggregates, export, or sync. */
export interface UserMsg {
  ts: string;
  day: string;
  tool: Rec["tool"];
  sessionId: string;
  text: string;
}

function textFromContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  const parts: string[] = [];
  for (const block of content) {
    if (typeof block === "string") {
      parts.push(block);
      continue;
    }
    if (!block || typeof block !== "object") continue;
    const o = block as { type?: string; text?: unknown };
    if (typeof o.text === "string" && (!o.type || o.type === "text" || o.type === "input_text" || o.type === "output_text")) {
      parts.push(o.text);
    }
  }
  return parts.join("\n");
}

function userMsg(tool: Rec["tool"], sessionId: string, ts: string, text: string): UserMsg | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  return { ts, day: ts.slice(0, 10), tool, sessionId, text: trimmed };
}

function walk(dir: string, match: (name: string) => boolean, out: string[]): void {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const e of entries) {
    const p = join(dir, e.name);
    if (e.isDirectory()) walk(p, match, out);
    else if (e.isFile() && match(e.name)) out.push(p);
  }
}

/* ----------------------------- Claude Code ----------------------------- */
// ~/.claude/projects/**/*.jsonl (also ~/.config/claude, $CLAUDE_CONFIG_DIR)
function claudeRoots(): string[] {
  const roots: string[] = [];
  const env = process.env.CLAUDE_CONFIG_DIR;
  if (env) for (const d of env.split(",")) roots.push(join(d.trim(), "projects"));
  roots.push(join(homedir(), ".claude", "projects"));
  roots.push(join(homedir(), ".config", "claude", "projects"));
  return [...new Set(roots)];
}

interface ClaudeRaw {
  type?: string;
  timestamp?: string;
  sessionId?: string;
  uuid?: string;
  message?: {
    id?: string;
    model?: string;
    role?: string;
    content?: unknown;
    usage?: {
      input_tokens?: number;
      output_tokens?: number;
      cache_creation_input_tokens?: number;
      cache_read_input_tokens?: number;
      server_tool_use?: { web_search_requests?: number; web_fetch_requests?: number };
    };
  };
}

function claudeContentBlocks(content: unknown): { type?: string; name?: string }[] {
  return Array.isArray(content) ? content as { type?: string; name?: string }[] : [];
}

export function loadClaude(roots = claudeRoots()): Rec[] {
  const files: string[] = [];
  for (const root of roots) walk(root, (n) => n.endsWith(".jsonl"), files);
  const seen = new Map<string, Rec>();
  for (const file of files) {
    let text: string;
    try {
      text = readFileSync(file, "utf8");
    } catch {
      continue;
    }
    for (const line of text.split("\n")) {
      if (!line || !line.includes('"usage"')) continue;
      let o: ClaudeRaw;
      try {
        o = JSON.parse(line) as ClaudeRaw;
      } catch {
        continue;
      }
      if (o.type !== "assistant") continue;
      const msg = o.message;
      const u = msg?.usage;
      if (!msg || !u) continue;
      const ts = o.timestamp ?? "";
      const key = "claude:" + String(msg.id ?? o.uuid ?? `${file}:${ts}`);
      const server = u.server_tool_use ?? {};
      // Claude Code's WebSearch/WebFetch are client-side tools dispatched as
      // tool_use content blocks; server_tool_use only counts the API's
      // server-side web tools, which is always zero in local transcripts.
      let webSearch = server.web_search_requests ?? 0;
      let webFetch = server.web_fetch_requests ?? 0;
      for (const block of claudeContentBlocks(msg.content)) {
        if (block?.type !== "tool_use") continue;
        if (block.name === "WebSearch") webSearch += 1;
        else if (block.name === "WebFetch") webFetch += 1;
      }
      const next: Rec = {
        ts,
        day: ts.slice(0, 10),
        tool: "claude",
        provider: "anthropic",
        model: msg.model ?? "unknown",
        sessionId: o.sessionId ?? "unknown",
        input: u.input_tokens ?? 0,
        output: u.output_tokens ?? 0,
        cacheWrite: u.cache_creation_input_tokens ?? 0,
        cacheRead: u.cache_read_input_tokens ?? 0,
        webSearch,
        webFetch,
      };
      // The same message id can appear on multiple lines (streaming partials,
      // history copied forward on resume) with growing usage. Keep the largest
      // value per counter instead of whichever line the walk hits last.
      const prev = seen.get(key);
      if (prev) {
        next.input = Math.max(prev.input, next.input);
        next.output = Math.max(prev.output, next.output);
        next.cacheWrite = Math.max(prev.cacheWrite, next.cacheWrite);
        next.cacheRead = Math.max(prev.cacheRead, next.cacheRead);
        next.webSearch = Math.max(prev.webSearch, next.webSearch);
        next.webFetch = Math.max(prev.webFetch, next.webFetch);
        if (!next.ts) {
          next.ts = prev.ts;
          next.day = prev.day;
        }
      }
      seen.set(key, next);
    }
  }
  return [...seen.values()];
}

// Real user prompts only — skip tool_result echoes that Claude also tags as type "user".
export function loadClaudeUserMessages(roots = claudeRoots()): UserMsg[] {
  const files: string[] = [];
  for (const root of roots) walk(root, (n) => n.endsWith(".jsonl"), files);
  const seen = new Map<string, UserMsg>();
  for (const file of files) {
    let text: string;
    try {
      text = readFileSync(file, "utf8");
    } catch {
      continue;
    }
    for (const line of text.split("\n")) {
      if (!line || !line.includes('"type"')) continue;
      let o: ClaudeRaw;
      try {
        o = JSON.parse(line) as ClaudeRaw;
      } catch {
        continue;
      }
      if (o.type !== "user") continue;
      const content = o.message?.content;
      const blocks = claudeContentBlocks(content);
      if (blocks.length && blocks.every((b) => b?.type === "tool_result")) continue;
      const body = textFromContent(content);
      const ts = o.timestamp ?? "";
      const msg = userMsg("claude", o.sessionId ?? "unknown", ts, body);
      if (!msg) continue;
      seen.set(o.uuid ?? `${file}:${ts}:${body.slice(0, 64)}`, msg);
    }
  }
  return [...seen.values()];
}

/* -------------------------------- Codex -------------------------------- */
// ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl. token_count events carry a
// cumulative total_token_usage; the last one per session is the session total.
function codexRoots(): string[] {
  const roots = [join(homedir(), ".codex", "sessions")];
  const env = process.env.CODEX_HOME;
  if (env) roots.push(join(env, "sessions"));
  return [...new Set(roots)];
}

function tsFromRollout(name: string): string {
  const m = name.match(/rollout-(\d{4})-(\d{2})-(\d{2})T(\d{2})-(\d{2})-(\d{2})/);
  if (!m) return "";
  return `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z`;
}

interface CodexUsage {
  input_tokens?: number;
  cached_input_tokens?: number;
  output_tokens?: number;
  reasoning_output_tokens?: number;
  total_tokens?: number;
}
function sub(a: CodexUsage, b: CodexUsage | null): CodexUsage {
  const p = b ?? {};
  return {
    input_tokens: (a.input_tokens ?? 0) - (p.input_tokens ?? 0),
    cached_input_tokens: (a.cached_input_tokens ?? 0) - (p.cached_input_tokens ?? 0),
    output_tokens: (a.output_tokens ?? 0) - (p.output_tokens ?? 0),
    reasoning_output_tokens: (a.reasoning_output_tokens ?? 0) - (p.reasoning_output_tokens ?? 0),
    total_tokens: (a.total_tokens ?? 0) - (p.total_tokens ?? 0),
  };
}

// Mirrors ccusage's Codex reader: per token_count event use last_token_usage
// (or total-minus-previous), globally dedup identical events, and — for forked/
// resumed sessions (a "forked_from_id" or "thread.spawn" marker) — skip the
// replayed parent history, whose events all carry the fork-creation second.
export function loadCodex(roots = codexRoots()): Rec[] {
  const files: string[] = [];
  for (const root of roots) walk(root, (n) => n.startsWith("rollout-") && n.endsWith(".jsonl"), files);
  files.sort();
  const recs: Rec[] = [];
  const seen = new Set<string>();
  for (const file of files) {
    let text: string;
    try {
      text = readFileSync(file, "utf8");
    } catch {
      continue;
    }
    const head = text.slice(0, 16384);
    const isReplay = head.includes("forked_from_id") || head.includes("thread.spawn");
    const lines = text.split("\n");

    let replaySec: string | null = null;
    if (isReplay) {
      for (const line of lines) {
        if (!line.includes('"token_count"')) continue;
        try {
          const o = JSON.parse(line);
          if (o?.type === "event_msg" && o?.payload?.type === "token_count" && typeof o.timestamp === "string") {
            replaySec = o.timestamp.slice(0, 19);
            break;
          }
        } catch {
          /* ignore */
        }
      }
    }

    let skip = isReplay && replaySec != null;
    let prev: CodexUsage | null = null;
    let model = "gpt-5-codex";
    for (const line of lines) {
      if (!line.includes('"token_count"')) {
        if (line.includes('"model"')) {
          const m = line.match(/"model"\s*:\s*"([^"]+)"/);
          if (m) model = m[1]!;
        }
        continue;
      }
      let o: { type?: string; timestamp?: string; payload?: { type?: string; info?: { last_token_usage?: CodexUsage; total_token_usage?: CodexUsage } } };
      try {
        o = JSON.parse(line);
      } catch {
        continue;
      }
      if (o.type !== "event_msg" || o.payload?.type !== "token_count") continue;
      const ts = o.timestamp ?? "";
      const info = o.payload.info ?? {};
      const total = info.total_token_usage ?? null;
      if (skip && ts && ts.slice(0, 19) === replaySec) {
        if (total) prev = total;
        continue;
      }
      skip = false;
      const raw: CodexUsage | null = info.last_token_usage ?? (total ? sub(total, prev) : null);
      if (total) prev = total;
      if (!raw) continue;
      const it = raw.input_tokens ?? 0;
      const rawCached = raw.cached_input_tokens ?? 0;
      const ot = raw.output_tokens ?? 0;
      const rt = raw.reasoning_output_tokens ?? 0;
      const tt = raw.total_tokens ?? 0;
      if (it === 0 && rawCached === 0 && ot === 0 && rt === 0) continue;
      const key = `${ts}|${it}|${rawCached}|${ot}|${rt}|${tt}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const cacheRead = Math.min(rawCached, it);
      recs.push({
        ts,
        day: ts.slice(0, 10),
        tool: "codex",
        provider: "openai",
        model,
        sessionId: basename(file),
        input: Math.max(0, it - cacheRead),
        output: ot + rt,
        cacheWrite: 0,
        cacheRead,
        webSearch: 0,
        webFetch: 0,
      });
    }
  }
  return recs;
}

export function loadCodexUserMessages(roots = codexRoots()): UserMsg[] {
  const files: string[] = [];
  for (const root of roots) walk(root, (n) => n.startsWith("rollout-") && n.endsWith(".jsonl"), files);
  files.sort();
  const out: UserMsg[] = [];
  const seen = new Set<string>();
  for (const file of files) {
    let text: string;
    try {
      text = readFileSync(file, "utf8");
    } catch {
      continue;
    }
    const sessionId = basename(file);
    for (const line of text.split("\n")) {
      if (!line.includes("user_message")) continue;
      let o: { type?: string; timestamp?: string; payload?: { type?: string; message?: string } };
      try {
        o = JSON.parse(line);
      } catch {
        continue;
      }
      if (o.type !== "event_msg" || o.payload?.type !== "user_message") continue;
      const body = typeof o.payload.message === "string" ? o.payload.message : "";
      // Codex injects a synthetic environment context as the first user turn.
      if (body.includes("<environment_context>")) continue;
      const ts = o.timestamp ?? "";
      const key = `${sessionId}|${ts}|${body}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const msg = userMsg("codex", sessionId, ts, body);
      if (msg) out.push(msg);
    }
  }
  return out;
}

/* ------------------------------ OpenCode ------------------------------ */
// OpenCode stores messages in ~/.local/share/opencode/opencode.db. Older
// installs may use storage/message/**/*.json; SQLite wins when both contain
// the same message ID, matching ccusage's reader.
function openCodeRoots(): string[] {
  const env = process.env.OPENCODE_DATA_DIR;
  const roots = env ? env.split(",").map((d) => d.trim()).filter(Boolean) : [];
  roots.push(join(homedir(), ".local", "share", "opencode"));
  return [...new Set(roots)];
}

interface OpenCodeRaw {
  id?: string;
  sessionID?: string;
  session_id?: string;
  providerID?: string;
  modelID?: string;
  role?: string;
  time?: { created?: number | string };
  tokens?: {
    input?: number;
    output?: number;
    total?: number;
    cache?: { read?: number; write?: number };
  };
  cost?: number;
  parts?: { type?: string; text?: string }[];
  content?: unknown;
}

interface OpenCodeRow {
  id: string;
  session_id?: string;
  data: string;
}

interface OpenCodePartRow {
  message_id: string;
  data: string;
}

interface SQLiteReader {
  rows: () => OpenCodeRow[];
  partRows: () => OpenCodePartRow[];
  close: () => void;
}

function openCodeTs(raw: OpenCodeRaw): string {
  const created = raw.time?.created;
  if (typeof created === "number") return new Date(created).toISOString();
  if (typeof created === "string") {
    const parsed = new Date(created);
    return Number.isNaN(parsed.getTime()) ? "" : parsed.toISOString();
  }
  return "";
}

function openCodeUserText(raw: OpenCodeRaw, partTexts: string[]): string {
  if (partTexts.length) return partTexts.join("\n");
  if (Array.isArray(raw.parts)) {
    return raw.parts.filter((p) => p?.type === "text" && typeof p.text === "string").map((p) => p.text!).join("\n");
  }
  return textFromContent(raw.content);
}

/* ------------------------------ notices ------------------------------ */
// Gaps that leave totals understated. A partial read must never be mistaken for
// a complete one, so the CLI prints these to stderr after collecting records.
const notices = new Set<string>();

export function usageNotices(): string[] {
  return [...notices];
}

// Test-only reset; the CLI reads notices once per process.
export function clearUsageNotices(): void {
  notices.clear();
}

function openCodeDatabaseNotice(error: unknown): string {
  const code = (error as { code?: string } | null | undefined)?.code;
  const noDriver = code === "ERR_UNKNOWN_BUILTIN_MODULE" || code === "ERR_MODULE_NOT_FOUND";
  return noDriver
    ? "OpenCode SQLite databases were skipped because this runtime has no SQLite driver, so OpenCode totals may be understated. Node.js 22.13 or newer, or Bun, reads them."
    : "OpenCode SQLite databases could not be read, so OpenCode totals may be understated.";
}

function sqlitePartRows(read: () => OpenCodePartRow[]): () => OpenCodePartRow[] {
  return () => {
    try {
      return read();
    } catch {
      return [];
    }
  };
}

async function openSQLiteReadOnly(path: string): Promise<SQLiteReader> {
  try {
    const { DatabaseSync } = await import("node:sqlite");
    const db = new DatabaseSync(path, { readOnly: true });
    return {
      rows: () => db.prepare("SELECT id, session_id, data FROM message").all() as unknown as OpenCodeRow[],
      partRows: sqlitePartRows(
        () => db.prepare("SELECT message_id, data FROM part").all() as unknown as OpenCodePartRow[],
      ),
      close: () => db.close(),
    };
  } catch (nodeError) {
    // Bun deliberately does not implement node:sqlite, but its native driver is
    // available in bunx and compiled executables. The literal specifier lets JSR
    // analyze and preserve the runtime-only import when publishing source.
    if (!process.versions.bun) throw nodeError;
    const { Database } = await import("bun:sqlite") as {
      Database: new (filename: string, options: { readonly: boolean; create: boolean }) => {
        query: (sql: string) => { all: () => OpenCodeRow[] | OpenCodePartRow[] };
        close: () => void;
      };
    };
    const db = new Database(path, { readonly: true, create: false });
    return {
      rows: () => db.query("SELECT id, session_id, data FROM message").all() as OpenCodeRow[],
      partRows: sqlitePartRows(() => db.query("SELECT message_id, data FROM part").all() as OpenCodePartRow[]),
      close: () => db.close(),
    };
  }
}

function collectPartTexts(root: string, messageId: string): string[] {
  const dir = join(root, "storage", "part", messageId);
  if (!existsSync(dir)) return [];
  const files: string[] = [];
  walk(dir, (name) => name.endsWith(".json"), files);
  const texts: string[] = [];
  for (const file of files.sort()) {
    try {
      const part = JSON.parse(readFileSync(file, "utf8")) as { type?: string; text?: string };
      if (part.type === "text" && typeof part.text === "string" && part.text.trim()) texts.push(part.text);
    } catch {
      /* ignore malformed parts */
    }
  }
  return texts;
}

function partTextMap(rows: OpenCodePartRow[]): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const row of rows) {
    try {
      const part = JSON.parse(row.data) as { type?: string; text?: string };
      if (part.type !== "text" || typeof part.text !== "string" || !part.text.trim()) continue;
      const list = map.get(row.message_id) ?? [];
      list.push(part.text);
      map.set(row.message_id, list);
    } catch {
      /* ignore */
    }
  }
  return map;
}

function openCodeRec(raw: OpenCodeRaw, fallbackId: string): Rec | null {
  const u = raw.tokens;
  if (!u || (raw.role && raw.role !== "assistant")) return null;
  const created = raw.time?.created;
  const ts = typeof created === "number"
    ? new Date(created).toISOString()
    : typeof created === "string"
      ? new Date(created).toISOString()
      : "";
  const input = Math.max(0, Number(u.input) || 0);
  const cacheRead = Math.max(0, Number(u.cache?.read) || 0);
  const cacheWrite = Math.max(0, Number(u.cache?.write) || 0);
  let output = Math.max(0, Number(u.output) || 0);
  const known = input + output + cacheRead + cacheWrite;
  const total = Math.max(0, Number(u.total) || 0);
  if (total > known) output += total - known;
  if (input + output + cacheRead + cacheWrite === 0) return null;
  return {
    ts,
    day: ts.slice(0, 10),
    tool: "opencode",
    provider: raw.providerID || "unknown",
    model: raw.modelID || "unknown",
    sessionId: raw.sessionID || raw.session_id || fallbackId,
    input,
    output,
    cacheWrite,
    cacheRead,
    webSearch: 0,
    webFetch: 0,
    ...(typeof raw.cost === "number" ? { costUSD: raw.cost } : {}),
  };
}

export async function loadOpenCode(roots = openCodeRoots()): Promise<Rec[]> {
  const records = new Map<string, Rec>();
  for (const root of roots) {
    const jsonFiles: string[] = [];
    walk(join(root, "storage", "message"), (name) => name.endsWith(".json"), jsonFiles);
    for (const file of jsonFiles) {
      try {
        const raw = JSON.parse(readFileSync(file, "utf8")) as OpenCodeRaw;
        const rec = openCodeRec(raw, basename(file));
        if (rec) records.set(raw.id || `json:${file}`, rec);
      } catch {
        /* malformed historical records are ignored */
      }
    }

    const dbFiles = existsSync(root)
      ? readdirSync(root).filter((name) => name === "opencode.db" || /^opencode-.*\.db$/.test(name)).sort()
      : [];
    if (!dbFiles.length) continue;
    try {
      for (const name of dbFiles) {
        const db = await openSQLiteReadOnly(join(root, name));
        try {
          for (const row of db.rows()) {
            try {
              const raw = JSON.parse(row.data) as OpenCodeRaw;
              raw.id ||= row.id;
              raw.sessionID ||= row.session_id;
              const rec = openCodeRec(raw, row.id);
              if (rec) records.set(row.id, rec);
            } catch {
              /* ignore malformed database rows */
            }
          }
        } finally {
          db.close();
        }
      }
    } catch (error) {
      // Deno, Bun-less runtimes, and Node before 22.13 expose no usable SQLite
      // driver. The JSON fallback above still contributes records and the other
      // sources are unaffected, but OpenCode keeps current sessions in the
      // database, so record the gap rather than reporting a silently low total.
      notices.add(openCodeDatabaseNotice(error));
    }
  }
  return [...records.values()];
}

export async function loadOpenCodeUserMessages(roots = openCodeRoots()): Promise<UserMsg[]> {
  const records = new Map<string, UserMsg>();
  for (const root of roots) {
    const jsonFiles: string[] = [];
    walk(join(root, "storage", "message"), (name) => name.endsWith(".json"), jsonFiles);
    for (const file of jsonFiles) {
      try {
        const raw = JSON.parse(readFileSync(file, "utf8")) as OpenCodeRaw;
        if (raw.role !== "user") continue;
        const id = raw.id || basename(file);
        const text = openCodeUserText(raw, collectPartTexts(root, id));
        const msg = userMsg("opencode", raw.sessionID || raw.session_id || "unknown", openCodeTs(raw), text);
        if (msg) records.set(id, msg);
      } catch {
        /* ignore */
      }
    }

    const dbFiles = existsSync(root)
      ? readdirSync(root).filter((name) => name === "opencode.db" || /^opencode-.*\.db$/.test(name)).sort()
      : [];
    if (!dbFiles.length) continue;
    try {
      for (const name of dbFiles) {
        const db = await openSQLiteReadOnly(join(root, name));
        try {
          const parts = partTextMap(db.partRows());
          for (const row of db.rows()) {
            try {
              const raw = JSON.parse(row.data) as OpenCodeRaw;
              if (raw.role !== "user") continue;
              const text = openCodeUserText(raw, parts.get(row.id) ?? collectPartTexts(root, row.id));
              const msg = userMsg("opencode", row.session_id || raw.sessionID || "unknown", openCodeTs(raw), text);
              if (msg) records.set(row.id, msg);
            } catch {
              /* ignore */
            }
          }
        } finally {
          db.close();
        }
      }
    } catch {
      // Usage path already records the SQLite gap; message extraction is best-effort.
    }
  }
  return [...records.values()];
}

/* ----------------------------- Gemini CLI ----------------------------- */
// Gemini CLI records current sessions below ~/.gemini/tmp/<project>/chats.
// GEMINI_CLI_HOME replaces the OS home directory, so its sessions live below
// $GEMINI_CLI_HOME/.gemini/tmp. Each JSONL file is an append-only stream where
// later records for the same message ID replace earlier versions.
function geminiRoots(): string[] {
  const home = process.env.GEMINI_CLI_HOME || homedir();
  return [join(home, ".gemini", "tmp")];
}

interface GeminiTokens {
  input?: number;
  output?: number;
  cached?: number;
  thoughts?: number;
  tool?: number;
  total?: number;
}

interface GeminiMessage {
  id?: string;
  timestamp?: string;
  type?: string;
  model?: string;
  content?: unknown;
  tokens?: GeminiTokens | null;
}

interface GeminiRecord {
  sessionId?: string;
  messages?: GeminiMessage[];
  $rewindTo?: string;
  $set?: {
    sessionId?: string;
    messages?: GeminiMessage[];
  };
}

function finiteToken(value: unknown): number {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, number) : 0;
}

function geminiRec(message: GeminiMessage, sessionId: string): Rec | null {
  const tokens = message.tokens;
  if (message.type !== "gemini" || !tokens) return null;

  // Gemini's prompt count includes cached input. Keep cached tokens in their
  // own bucket, and use totalTokenCount only for a positive residual such as
  // tool prompt tokens that is not represented by the named fields.
  const prompt = finiteToken(tokens.input);
  const cacheRead = Math.min(prompt, finiteToken(tokens.cached));
  const output = finiteToken(tokens.output) + finiteToken(tokens.thoughts);
  const known = prompt + output;
  const residual = Math.max(0, finiteToken(tokens.total) - known);
  const input = Math.max(0, prompt - cacheRead) + residual;
  if (input + output + cacheRead === 0) return null;

  const ts = typeof message.timestamp === "string" ? message.timestamp : "";
  return {
    ts,
    day: ts.slice(0, 10),
    tool: "gemini",
    provider: "google",
    model: message.model || "unknown",
    sessionId,
    input,
    output,
    cacheWrite: 0,
    cacheRead,
    webSearch: 0,
    webFetch: 0,
  };
}

export function loadGemini(roots = geminiRoots()): Rec[] {
  const files: string[] = [];
  for (const root of roots) walk(root, (name) => name.endsWith(".jsonl"), files);
  const records: Rec[] = [];

  for (const file of files) {
    let text: string;
    try {
      text = readFileSync(file, "utf8");
    } catch {
      continue;
    }

    let sessionId = basename(file, ".jsonl");
    const messages = new Map<string, GeminiMessage>();
    const order: string[] = [];
    const replaceMessages = (next: GeminiMessage[]): void => {
      messages.clear();
      order.length = 0;
      for (const message of next) {
        if (!message.id) continue;
        if (!messages.has(message.id)) order.push(message.id);
        messages.set(message.id, message);
      }
    };

    for (const line of text.split("\n")) {
      if (!line.trim()) continue;
      let raw: GeminiRecord & GeminiMessage;
      try {
        raw = JSON.parse(line) as GeminiRecord & GeminiMessage;
      } catch {
        continue;
      }

      if (typeof raw.sessionId === "string") sessionId = raw.sessionId;
      if (Array.isArray(raw.messages)) replaceMessages(raw.messages);
      if (raw.$set) {
        if (typeof raw.$set.sessionId === "string") sessionId = raw.$set.sessionId;
        if (Array.isArray(raw.$set.messages)) replaceMessages(raw.$set.messages);
        continue;
      }
      if (typeof raw.$rewindTo === "string") {
        const index = order.indexOf(raw.$rewindTo);
        const removed = index >= 0 ? order.splice(index) : order.splice(0);
        for (const id of removed) messages.delete(id);
        continue;
      }
      if (!raw.id) continue;
      if (!messages.has(raw.id)) order.push(raw.id);
      messages.set(raw.id, raw);
    }

    for (const id of order) {
      const rec = geminiRec(messages.get(id)!, sessionId);
      if (rec) records.push(rec);
    }
  }

  return records;
}

export function loadGeminiUserMessages(roots = geminiRoots()): UserMsg[] {
  const files: string[] = [];
  for (const root of roots) walk(root, (name) => name.endsWith(".jsonl"), files);
  const out: UserMsg[] = [];
  const seen = new Set<string>();

  for (const file of files) {
    let text: string;
    try {
      text = readFileSync(file, "utf8");
    } catch {
      continue;
    }

    let sessionId = basename(file, ".jsonl");
    const messages = new Map<string, GeminiMessage>();
    const order: string[] = [];
    const replaceMessages = (next: GeminiMessage[]): void => {
      messages.clear();
      order.length = 0;
      for (const message of next) {
        if (!message.id) continue;
        if (!messages.has(message.id)) order.push(message.id);
        messages.set(message.id, message);
      }
    };

    for (const line of text.split("\n")) {
      if (!line.trim()) continue;
      let raw: GeminiRecord & GeminiMessage;
      try {
        raw = JSON.parse(line) as GeminiRecord & GeminiMessage;
      } catch {
        continue;
      }

      if (typeof raw.sessionId === "string") sessionId = raw.sessionId;
      if (Array.isArray(raw.messages)) replaceMessages(raw.messages);
      if (raw.$set) {
        if (typeof raw.$set.sessionId === "string") sessionId = raw.$set.sessionId;
        if (Array.isArray(raw.$set.messages)) replaceMessages(raw.$set.messages);
        continue;
      }
      if (typeof raw.$rewindTo === "string") {
        const index = order.indexOf(raw.$rewindTo);
        const removed = index >= 0 ? order.splice(index) : order.splice(0);
        for (const id of removed) messages.delete(id);
        continue;
      }
      if (!raw.id) continue;
      if (!messages.has(raw.id)) order.push(raw.id);
      messages.set(raw.id, raw);
    }

    for (const id of order) {
      const message = messages.get(id)!;
      if (message.type !== "user") continue;
      const ts = typeof message.timestamp === "string" ? message.timestamp : "";
      const msg = userMsg("gemini", sessionId, ts, textFromContent(message.content));
      if (!msg) continue;
      const key = `${sessionId}|${id}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(msg);
    }
  }

  return out;
}

/* ------------------------------ registry ------------------------------ */
export interface Source {
  tool: Rec["tool"];
  label: string;
  load: () => Rec[] | Promise<Rec[]>;
}
export const SOURCES: Source[] = [
  { tool: "claude", label: "Claude Code", load: loadClaude },
  { tool: "codex", label: "Codex", load: loadCodex },
  { tool: "opencode", label: "OpenCode", load: loadOpenCode },
  { tool: "gemini", label: "Gemini CLI", load: loadGemini },
];

type MessageSource = {
  tool: Rec["tool"];
  load: () => UserMsg[] | Promise<UserMsg[]>;
};

const MESSAGE_SOURCES: MessageSource[] = [
  { tool: "claude", load: loadClaudeUserMessages },
  { tool: "codex", load: loadCodexUserMessages },
  { tool: "opencode", load: loadOpenCodeUserMessages },
  { tool: "gemini", load: loadGeminiUserMessages },
];

// Read every supported CLI. Sources with no data simply contribute nothing.
export async function collectAll(): Promise<Rec[]> {
  const all: Rec[] = [];
  for (const s of SOURCES) {
    try {
      all.push(...await s.load());
    } catch {
      /* a broken source never breaks the others */
    }
  }
  return all;
}

/** Local-only user prompts from every supported agent. Not used by export/sync. */
export async function collectUserMessages(): Promise<UserMsg[]> {
  const all: UserMsg[] = [];
  for (const s of MESSAGE_SOURCES) {
    try {
      all.push(...await s.load());
    } catch {
      /* a broken source never breaks the others */
    }
  }
  return all.sort((a, b) => a.ts.localeCompare(b.ts) || a.tool.localeCompare(b.tool));
}

/** Full role-tagged turns for Proto2 skill learning (local only). */
export interface SessionMsg {
  ts: string;
  day: string;
  tool: Rec["tool"];
  sessionId: string;
  role: "user" | "assistant" | "system";
  text: string;
}

function sessionMsg(
  tool: Rec["tool"],
  sessionId: string,
  ts: string,
  role: SessionMsg["role"],
  text: string,
): SessionMsg | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  return { ts, day: ts.slice(0, 10), tool, sessionId, role, text: trimmed };
}

export function loadClaudeSessionMessages(roots = claudeRoots()): SessionMsg[] {
  const files: string[] = [];
  for (const root of roots) walk(root, (n) => n.endsWith(".jsonl"), files);
  const seen = new Map<string, SessionMsg>();
  for (const file of files) {
    let text: string;
    try {
      text = readFileSync(file, "utf8");
    } catch {
      continue;
    }
    for (const line of text.split("\n")) {
      if (!line || !line.includes('"type"')) continue;
      let o: ClaudeRaw;
      try {
        o = JSON.parse(line) as ClaudeRaw;
      } catch {
        continue;
      }
      if (o.type !== "user" && o.type !== "assistant") continue;
      const content = o.message?.content;
      const blocks = claudeContentBlocks(content);
      if (o.type === "user" && blocks.length && blocks.every((b) => b?.type === "tool_result")) continue;
      const body = textFromContent(content);
      const ts = o.timestamp ?? "";
      const role: SessionMsg["role"] = o.type === "assistant" ? "assistant" : "user";
      const msg = sessionMsg("claude", o.sessionId ?? "unknown", ts, role, body);
      if (!msg) continue;
      seen.set(o.uuid ?? `${file}:${role}:${ts}:${body.slice(0, 64)}`, msg);
    }
  }
  return [...seen.values()];
}

export function loadCodexSessionMessages(roots = codexRoots()): SessionMsg[] {
  const files: string[] = [];
  for (const root of roots) walk(root, (n) => n.startsWith("rollout-") && n.endsWith(".jsonl"), files);
  files.sort();
  const out: SessionMsg[] = [];
  const seen = new Set<string>();
  for (const file of files) {
    let text: string;
    try {
      text = readFileSync(file, "utf8");
    } catch {
      continue;
    }
    const sessionId = basename(file);
    for (const line of text.split("\n")) {
      if (!line.includes("user_message") && !line.includes("agent_message")) continue;
      let o: { type?: string; timestamp?: string; payload?: { type?: string; message?: string } };
      try {
        o = JSON.parse(line);
      } catch {
        continue;
      }
      if (o.type !== "event_msg") continue;
      const ptype = o.payload?.type;
      if (ptype !== "user_message" && ptype !== "agent_message") continue;
      const body = typeof o.payload?.message === "string" ? o.payload.message : "";
      if (ptype === "user_message" && body.includes("<environment_context>")) continue;
      const ts = o.timestamp ?? "";
      const role: SessionMsg["role"] = ptype === "agent_message" ? "assistant" : "user";
      const key = `${sessionId}|${role}|${ts}|${body}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const msg = sessionMsg("codex", sessionId, ts, role, body);
      if (msg) out.push(msg);
    }
  }
  return out;
}

export async function loadOpenCodeSessionMessages(roots = openCodeRoots()): Promise<SessionMsg[]> {
  const records = new Map<string, SessionMsg>();
  for (const root of roots) {
    const jsonFiles: string[] = [];
    walk(join(root, "storage", "message"), (name) => name.endsWith(".json"), jsonFiles);
    for (const file of jsonFiles) {
      try {
        const raw = JSON.parse(readFileSync(file, "utf8")) as OpenCodeRaw;
        const role = raw.role === "assistant" || raw.role === "system" || raw.role === "user" ? raw.role : null;
        if (!role) continue;
        const id = raw.id || basename(file);
        const text = openCodeUserText(raw, collectPartTexts(root, id));
        const msg = sessionMsg("opencode", raw.sessionID || raw.session_id || "unknown", openCodeTs(raw), role, text);
        if (msg) records.set(id, msg);
      } catch {
        /* ignore */
      }
    }

    const dbFiles = existsSync(root)
      ? readdirSync(root).filter((name) => name === "opencode.db" || /^opencode-.*\.db$/.test(name)).sort()
      : [];
    if (!dbFiles.length) continue;
    try {
      for (const name of dbFiles) {
        const db = await openSQLiteReadOnly(join(root, name));
        try {
          const parts = partTextMap(db.partRows());
          for (const row of db.rows()) {
            try {
              const raw = JSON.parse(row.data) as OpenCodeRaw;
              const role = raw.role === "assistant" || raw.role === "system" || raw.role === "user" ? raw.role : null;
              if (!role) continue;
              const text = openCodeUserText(raw, parts.get(row.id) ?? collectPartTexts(root, row.id));
              const msg = sessionMsg(
                "opencode",
                row.session_id || raw.sessionID || "unknown",
                openCodeTs(raw),
                role,
                text,
              );
              if (msg) records.set(row.id, msg);
            } catch {
              /* ignore */
            }
          }
        } finally {
          db.close();
        }
      }
    } catch {
      /* best-effort */
    }
  }
  return [...records.values()];
}

export function loadGeminiSessionMessages(roots = geminiRoots()): SessionMsg[] {
  const files: string[] = [];
  for (const root of roots) walk(root, (name) => name.endsWith(".jsonl"), files);
  const out: SessionMsg[] = [];
  const seen = new Set<string>();

  for (const file of files) {
    let text: string;
    try {
      text = readFileSync(file, "utf8");
    } catch {
      continue;
    }

    let sessionId = basename(file, ".jsonl");
    const messages = new Map<string, GeminiMessage>();
    const order: string[] = [];
    const replaceMessages = (next: GeminiMessage[]): void => {
      messages.clear();
      order.length = 0;
      for (const message of next) {
        if (!message.id) continue;
        if (!messages.has(message.id)) order.push(message.id);
        messages.set(message.id, message);
      }
    };

    for (const line of text.split("\n")) {
      if (!line.trim()) continue;
      let raw: GeminiRecord & GeminiMessage;
      try {
        raw = JSON.parse(line) as GeminiRecord & GeminiMessage;
      } catch {
        continue;
      }

      if (typeof raw.sessionId === "string") sessionId = raw.sessionId;
      if (Array.isArray(raw.messages)) replaceMessages(raw.messages);
      if (raw.$set) {
        if (typeof raw.$set.sessionId === "string") sessionId = raw.$set.sessionId;
        if (Array.isArray(raw.$set.messages)) replaceMessages(raw.$set.messages);
        continue;
      }
      if (typeof raw.$rewindTo === "string") {
        const index = order.indexOf(raw.$rewindTo);
        const removed = index >= 0 ? order.splice(index) : order.splice(0);
        for (const id of removed) messages.delete(id);
        continue;
      }
      if (!raw.id) continue;
      if (!messages.has(raw.id)) order.push(raw.id);
      messages.set(raw.id, raw);
    }

    for (const id of order) {
      const message = messages.get(id)!;
      const role: SessionMsg["role"] | null =
        message.type === "user" ? "user" : message.type === "gemini" ? "assistant" : null;
      if (!role) continue;
      const ts = typeof message.timestamp === "string" ? message.timestamp : "";
      const msg = sessionMsg("gemini", sessionId, ts, role, textFromContent(message.content));
      if (!msg) continue;
      const key = `${sessionId}|${id}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(msg);
    }
  }

  return out;
}

/** Snapshot full transcripts from every supported coding agent. */
export async function collectSessionMessages(): Promise<SessionMsg[]> {
  const all: SessionMsg[] = [];
  const loaders: Array<() => SessionMsg[] | Promise<SessionMsg[]>> = [
    loadClaudeSessionMessages,
    loadCodexSessionMessages,
    loadOpenCodeSessionMessages,
    loadGeminiSessionMessages,
  ];
  for (const load of loaders) {
    try {
      all.push(...(await load()));
    } catch {
      /* a broken source never breaks the others */
    }
  }
  return all.sort((a, b) => a.ts.localeCompare(b.ts) || a.tool.localeCompare(b.tool));
}
