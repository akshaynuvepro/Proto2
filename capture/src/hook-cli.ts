#!/usr/bin/env node
/**
 * Cursor hook entry: read hook JSON from stdin, append to capture store, exit 0.
 * Fail-open: never block the agent on record failures.
 */
import { appendLiveMessage, snapshotConversations, storePath } from "./store.ts";

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks).toString("utf8");
}

function ok(): void {
  // Most Cursor hook events accept empty/`{}` success; keep fail-open.
  process.stdout.write("{}\n");
}

async function main(): Promise<void> {
  const mode = process.argv[2] ?? "prompt";
  let raw = "";
  try {
    raw = await readStdin();
  } catch {
    ok();
    return;
  }

  let data: Record<string, unknown> = {};
  try {
    data = raw.trim() ? (JSON.parse(raw) as Record<string, unknown>) : {};
  } catch {
    ok();
    return;
  }

  try {
    if (mode === "sessionStart") {
      await snapshotConversations(storePath());
      ok();
      return;
    }

    const prompt =
      (typeof data.prompt === "string" && data.prompt) ||
      (typeof data.text === "string" && data.text) ||
      (typeof data.user_prompt === "string" && data.user_prompt) ||
      "";
    const response =
      (typeof data.response === "string" && data.response) ||
      (typeof data.text === "string" && data.text && mode !== "prompt" ? data.text : "") ||
      (typeof data.agent_response === "string" && data.agent_response) ||
      "";

    if (mode === "prompt" && prompt.trim()) {
      appendLiveMessage({
        text: prompt,
        role: "user",
        tool: "live",
        sessionId: typeof data.session_id === "string" ? data.session_id : "cursor",
      });
    } else if ((mode === "response" || mode === "stop") && (response || prompt).trim()) {
      appendLiveMessage({
        text: (response || prompt).trim(),
        role: "assistant",
        tool: "live",
        sessionId: typeof data.session_id === "string" ? data.session_id : "cursor",
      });
    }
  } catch {
    /* fail open */
  }
  ok();
}

void main();
