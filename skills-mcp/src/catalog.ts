import { existsSync, readdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PACKAGE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DEV_SKILLS_ROOT = join(PACKAGE_ROOT, "..", "data", "skills");
const DEV_FEEDBACK_ROOT = join(PACKAGE_ROOT, "..", "data", "langsmith", "feedback");
const HOME_SKILLS_ROOT = join(homedir(), ".proto-skills", "skills");
const HOME_FEEDBACK_ROOT = join(homedir(), ".proto-skills", "feedback");

export interface CatalogSkill {
  name: string;
  display_name?: string;
  description?: string;
  triggers?: string[];
  tags?: string[];
  tools?: string[];
  path?: string;
  references?: string[];
  scripts?: string[];
  session_count?: number;
  last_active_date?: string;
}

export interface Catalog {
  schema?: string;
  purpose?: string;
  skills: CatalogSkill[];
}

export interface MatchResult {
  name: string;
  display_name: string;
  description: string;
  score: number;
  matched_terms: string[];
  session_count: number;
  path: string;
}

function inProto2Checkout(): boolean {
  return existsSync(join(PACKAGE_ROOT, "..", "main.py")) && existsSync(join(PACKAGE_ROOT, "..", "data"));
}

export function skillsRoot(override?: string): string {
  if (override?.trim()) return resolve(override.trim());
  if (process.env.PROTO_SKILLS_ROOT?.trim()) return resolve(process.env.PROTO_SKILLS_ROOT.trim());
  return inProto2Checkout() ? DEV_SKILLS_ROOT : HOME_SKILLS_ROOT;
}

export function feedbackRoot(override?: string): string {
  if (override?.trim()) return resolve(override.trim());
  if (process.env.PROTO_FEEDBACK_ROOT?.trim()) return resolve(process.env.PROTO_FEEDBACK_ROOT.trim());
  return inProto2Checkout() ? DEV_FEEDBACK_ROOT : HOME_FEEDBACK_ROOT;
}

export function loadCatalog(root = skillsRoot()): Catalog {
  const path = join(root, "catalog.json");
  if (!existsSync(path)) {
    return { schema: "proto2-skill-catalog/1", skills: [] };
  }
  const raw = JSON.parse(readFileSync(path, "utf8")) as Catalog;
  return { ...raw, skills: Array.isArray(raw.skills) ? raw.skills : [] };
}

export function listSkills(root = skillsRoot()) {
  const catalog = loadCatalog(root);
  return {
    ok: true,
    skillsRoot: root,
    count: catalog.skills.length,
    purpose: catalog.purpose ?? "",
    skills: catalog.skills.map((s) => ({
      name: s.name,
      display_name: s.display_name ?? s.name,
      description: s.description ?? "",
      triggers: s.triggers ?? [],
      tags: s.tags ?? [],
      tools: s.tools ?? [],
      session_count: s.session_count ?? 0,
      last_active_date: s.last_active_date ?? "",
      path: s.path ?? `${s.name}/SKILL.md`,
      references: s.references ?? [],
      scripts: s.scripts ?? [],
    })),
  };
}

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[^a-z0-9+]+/g)
    .filter((t) => t.length >= 2);
}

export function matchSkills(query: string, limit = 5, root = skillsRoot()): {
  ok: true;
  query: string;
  matches: MatchResult[];
} {
  const qTokens = [...new Set(tokenize(query))];
  const catalog = loadCatalog(root);
  const scored: MatchResult[] = [];

  for (const skill of catalog.skills) {
    const matched = new Set<string>();
    let score = 0;
    const nameTokens = tokenize(`${skill.name} ${skill.display_name ?? ""}`);
    const descTokens = tokenize(skill.description ?? "");
    const triggerTokens = tokenize((skill.triggers ?? []).join(" "));
    const tagTokens = tokenize((skill.tags ?? []).join(" "));

    for (const t of qTokens) {
      if (nameTokens.includes(t)) {
        score += 5;
        matched.add(t);
      }
      if (triggerTokens.includes(t)) {
        score += 4;
        matched.add(t);
      }
      if (tagTokens.includes(t)) {
        score += 3;
        matched.add(t);
      }
      if (descTokens.includes(t)) {
        score += 2;
        matched.add(t);
      }
    }

    // light boost for popular / recent skills when there is any lexical hit
    if (score > 0) {
      score += Math.min(3, Math.floor((skill.session_count ?? 0) / 50));
      scored.push({
        name: skill.name,
        display_name: skill.display_name ?? skill.name,
        description: skill.description ?? "",
        score,
        matched_terms: [...matched],
        session_count: skill.session_count ?? 0,
        path: skill.path ?? `${skill.name}/SKILL.md`,
      });
    }
  }

  scored.sort((a, b) => b.score - a.score || b.session_count - a.session_count || a.name.localeCompare(b.name));
  return { ok: true, query, matches: scored.slice(0, Math.max(1, limit)) };
}

export function getSkill(
  name: string,
  opts: { includeReferences?: boolean; includeScripts?: boolean } = {},
  root = skillsRoot(),
) {
  const catalog = loadCatalog(root);
  const entry = catalog.skills.find((s) => s.name === name);
  if (!entry) {
    return { ok: false, error: `Skill not found: ${name}` };
  }
  const skillMdPath = join(root, entry.path ?? `${name}/SKILL.md`);
  if (!existsSync(skillMdPath)) {
    return { ok: false, error: `SKILL.md missing at ${skillMdPath}` };
  }
  const content = readFileSync(skillMdPath, "utf8");
  const result: Record<string, unknown> = {
    ok: true,
    name: entry.name,
    display_name: entry.display_name ?? entry.name,
    description: entry.description ?? "",
    path: skillMdPath,
    skill_md: content,
  };

  if (opts.includeReferences) {
    const refsDir = join(root, name, "references");
    const references: Record<string, string> = {};
    if (existsSync(refsDir)) {
      for (const file of readdirSync(refsDir)) {
        if (!file.endsWith(".md")) continue;
        references[file] = readFileSync(join(refsDir, file), "utf8");
      }
    }
    result.references = references;
  }

  if (opts.includeScripts) {
    const scriptsDir = join(root, name, "scripts");
    const scripts: Record<string, string> = {};
    if (existsSync(scriptsDir)) {
      for (const file of readdirSync(scriptsDir)) {
        scripts[file] = readFileSync(join(scriptsDir, file), "utf8");
      }
    }
    result.scripts = scripts;
  }

  return result;
}

function localToday(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export function listFeedbackDates(root = feedbackRoot()): string[] {
  if (!existsSync(root)) return [];
  return readdirSync(root)
    .filter((f) => /^\d{4}-\d{2}-\d{2}\.md$/.test(f))
    .map((f) => f.replace(/\.md$/, ""))
    .sort()
    .reverse();
}

export function getFeedback(date?: string, root = feedbackRoot()) {
  const dates = listFeedbackDates(root);
  const wanted = date?.trim() || localToday();
  const path = join(root, `${wanted}.md`);
  if (!existsSync(path)) {
    // fall back to latest available feedback if today's file is missing
    if (!date?.trim() && dates[0]) {
      const latestPath = join(root, `${dates[0]}.md`);
      return {
        ok: true,
        date: dates[0],
        path: latestPath,
        fallback: true,
        content: readFileSync(latestPath, "utf8"),
        available_dates: dates,
      };
    }
    return {
      ok: false,
      error: `Feedback not found for ${wanted}`,
      available_dates: dates,
      feedbackRoot: root,
    };
  }
  return {
    ok: true,
    date: wanted,
    path,
    fallback: false,
    content: readFileSync(path, "utf8"),
    available_dates: dates,
  };
}

export function skillsStatus(skills = skillsRoot(), feedback = feedbackRoot()) {
  const catalog = loadCatalog(skills);
  const dates = listFeedbackDates(feedback);
  return {
    ok: true,
    packageRoot: PACKAGE_ROOT,
    skillsRoot: skills,
    feedbackRoot: feedback,
    skillCount: catalog.skills.length,
    catalogExists: existsSync(join(skills, "catalog.json")),
    latestFeedbackDate: dates[0] ?? null,
    feedbackDates: dates.slice(0, 14),
  };
}
