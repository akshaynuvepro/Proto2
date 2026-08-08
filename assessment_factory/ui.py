"""Enterprise browse UI for the assessment factory (standard library only).

Views:
- Dashboard: KPIs + records / templates / skills.
- Template detail: house style, structure, canonical example.
- Skill detail: IDE-style package browser (file tree + rendered file preview).

No review/approve controls (removed by request). Read-only.
"""

from __future__ import annotations

import html
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from .store import FactoryStore


# --------------------------------------------------------------------------
# tiny Markdown -> HTML (no third-party deps)
# --------------------------------------------------------------------------

def _inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2" target="_blank">\1</a>', text)
    return text


def md_to_html(md: str) -> str:
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    if lines and lines[0].strip() == "---":
        j = 1
        while j < n and lines[j].strip() != "---":
            j += 1
        if j < n:
            out.append(f"<div class='frontmatter'><pre>{html.escape(chr(10).join(lines[1:j]))}</pre></div>")
            i = j + 1
    while i < n:
        line = lines[i]
        s = line.strip()
        if s.startswith("```"):
            j = i + 1
            buf = []
            while j < n and not lines[j].strip().startswith("```"):
                buf.append(lines[j]); j += 1
            out.append(f"<pre class='code'>{html.escape(chr(10).join(buf))}</pre>")
            i = j + 1; continue
        if not s:
            i += 1; continue
        if s.startswith("|") and i + 1 < n and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]):
            header = [c.strip() for c in s.strip("|").split("|")]
            rows = []
            j = i + 2
            while j < n and lines[j].strip().startswith("|"):
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")]); j += 1
            thead = "".join(f"<th>{_inline(c)}</th>" for c in header)
            tbody = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f"<table class='md'><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>")
            i = j; continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            lvl = len(m.group(1)); out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>"); i += 1; continue
        if re.match(r"^-{3,}$", s):
            out.append("<hr>"); i += 1; continue
        if s.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].strip()); i += 1
            out.append(f"<blockquote>{_inline(' '.join(buf))}</blockquote>"); continue
        if re.match(r"^[-*]\s+", s):
            buf = []
            while i < n and re.match(r"^\s*[-*]\s+", lines[i]):
                buf.append(re.sub(r"^\s*[-*]\s+", "", lines[i])); i += 1
            out.append("<ul>" + "".join(f"<li>{_inline(x)}</li>" for x in buf) + "</ul>"); continue
        if re.match(r"^\d+\.\s+", s):
            buf = []
            while i < n and re.match(r"^\s*\d+\.\s+", lines[i]):
                buf.append(re.sub(r"^\s*\d+\.\s+", "", lines[i])); i += 1
            out.append("<ol>" + "".join(f"<li>{_inline(x)}</li>" for x in buf) + "</ol>"); continue
        out.append(f"<p>{_inline(s)}</p>"); i += 1
    return "\n".join(out)


# --------------------------------------------------------------------------
# design system
# --------------------------------------------------------------------------

_CSS = """
:root{
  --bg:#000000;--panel:#0c0c0e;--panel2:#111114;--line:#1c1c20;--line2:#2a2a30;
  --fg:#f3f4f6;--fg2:#c3c7cf;--mut:#7d828c;--acc:#4f8cff;--acc-soft:#0e1730;
  --ok:#42c07f;--okbg:#0d2016;--warn:#e0a53a;--warnbg:#221a08;--radius:12px;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
}
*{box-sizing:border-box;} html,body{margin:0;height:100%;}
body{font-family:var(--sans);color:var(--fg);background:var(--bg);line-height:1.6;-webkit-font-smoothing:antialiased;}
a{color:var(--acc);text-decoration:none;} a:hover{text-decoration:underline;}
::selection{background:#1d365f;}

.layout{display:grid;grid-template-columns:248px 1fr;min-height:100vh;}
aside{background:#050506;border-right:1px solid var(--line);padding:20px 14px;position:sticky;top:0;height:100vh;overflow:auto;}
.brand{display:flex;align-items:center;gap:10px;margin:4px 8px 24px;}
.brand .mark{width:32px;height:32px;border-radius:8px;background:var(--acc);display:grid;place-items:center;color:#fff;font-weight:700;font-size:13px;}
.brand .tt{font-weight:700;font-size:14px;} .brand .ss{font-size:11px;color:var(--mut);}
.navlabel{font-size:11px;color:var(--mut);margin:18px 10px 6px;font-weight:600;}
nav a{display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:8px;color:var(--fg2);font-size:13.5px;font-weight:500;margin-bottom:2px;}
nav a:hover{background:#141418;text-decoration:none;color:var(--fg);}
nav a.active{background:var(--acc-soft);color:#7fb0ff;font-weight:600;}
nav a .ic{width:20px;height:20px;display:grid;place-items:center;font-size:11px;color:#7fb0ff;background:#12141c;border:1px solid var(--line);border-radius:6px;}
nav a.active .ic{background:#14213f;}
nav a .count{margin-left:auto;color:var(--mut);font-size:12px;font-weight:600;}

.content{min-width:0;}
.topbar{display:flex;align-items:center;padding:14px 32px;border-bottom:1px solid var(--line);background:#050506;position:sticky;top:0;z-index:6;}
.crumb{font-size:13px;color:var(--mut);} .crumb b{color:var(--fg);font-weight:600;}
.pill{margin-left:auto;font-size:12px;color:var(--fg2);display:flex;align-items:center;gap:7px;}
.dot{width:7px;height:7px;border-radius:50%;background:var(--ok);box-shadow:0 0 7px var(--ok);}
main{padding:28px 32px 60px;max-width:1120px;}

h1{font-size:22px;margin:2px 0 4px;font-weight:700;}
.sub{color:var(--mut);font-size:14px;margin-bottom:20px;}
h2{font-size:13px;color:var(--fg);margin:28px 0 10px;font-weight:600;}

.statline{display:flex;gap:26px;padding:14px 18px;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);margin-bottom:8px;}
.statline .s{display:flex;flex-direction:column;} .statline .n{font-size:20px;font-weight:700;} .statline .l{font-size:12px;color:var(--mut);}

.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:18px 20px;margin-bottom:14px;}

table{width:100%;border-collapse:separate;border-spacing:0;margin:6px 0;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;}
th,td{text-align:left;padding:11px 15px;font-size:13.5px;border-bottom:1px solid var(--line);}
th{color:var(--mut);font-weight:600;background:#080809;font-size:12px;}
tr:last-child td{border-bottom:0;} tbody tr:hover td{background:#111114;}
a.item{font-weight:600;}

.tag{padding:3px 10px;border-radius:6px;font-size:12px;font-weight:600;display:inline-block;background:#141418;border:1px solid var(--line2);color:var(--fg2);}
.tag.ok{background:var(--okbg);border-color:#1c4630;color:var(--ok);}
.tag.type{background:var(--acc-soft);border-color:#22375f;color:#7fb0ff;}
.tag.warn{background:var(--warnbg);border-color:#4a3a12;color:var(--warn);}
.muted{color:var(--mut);font-size:12px;}
.grid{display:grid;grid-template-columns:190px 1fr;gap:8px 18px;font-size:13.5px;}
.grid div:nth-child(odd){color:var(--mut);}
.chips span{display:inline-block;background:#141418;border:1px solid var(--line2);border-radius:6px;padding:4px 11px;margin:4px 6px 0 0;font-size:12px;color:var(--fg2);}

/* skill package browser */
.ide{display:grid;grid-template-columns:260px 1fr;gap:16px;align-items:start;}
.tree{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:10px;position:sticky;top:80px;}
.tree .grp{font-size:11px;color:var(--mut);padding:8px 10px 4px;font-weight:600;}
.tree a{display:flex;align-items:center;gap:9px;padding:7px 10px;border-radius:7px;color:var(--fg2);font-size:13px;font-weight:500;}
.tree a:hover{background:#141418;text-decoration:none;color:var(--fg);}
.tree a.active{background:var(--acc-soft);color:#7fb0ff;font-weight:600;}
.tree a .fic{width:16px;text-align:center;color:var(--mut);}
.filebody{min-width:0;}
.filehead{display:flex;align-items:center;gap:10px;margin-bottom:10px;}
.filehead .path{font-family:var(--mono);font-size:13px;color:var(--fg2);background:#141418;border:1px solid var(--line);padding:5px 11px;border-radius:7px;}

.preview{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:6px 30px 26px;}
.preview h1{font-size:22px;border-bottom:1px solid var(--line);padding-bottom:9px;margin-top:22px;font-weight:700;}
.preview h2{font-size:17px;color:var(--fg);margin-top:24px;font-weight:600;}
.preview h3{font-size:14.5px;color:var(--fg2);margin-top:18px;}
.preview p,.preview li{color:var(--fg2);}
.preview code{background:#16161b;padding:1px 6px;border-radius:5px;font-size:12.5px;color:#ff9ecb;font-family:var(--mono);}
.preview pre.code{background:#050506;border:1px solid var(--line2);padding:15px;border-radius:9px;overflow:auto;font-size:12.5px;font-family:var(--mono);color:#d7dde6;line-height:1.55;}
.preview pre.code code{background:none;padding:0;color:inherit;}
.preview blockquote{border-left:3px solid var(--acc);margin:12px 0;padding:4px 14px;color:var(--fg2);background:var(--acc-soft);border-radius:0 8px 8px 0;}
.preview table.md th{background:#080809;}
.preview ul,.preview ol{padding-left:22px;}
.frontmatter{background:#050506;border:1px dashed var(--line2);border-radius:8px;padding:2px 14px;margin:12px 0;}
.frontmatter pre{color:#7fb0ff;font-size:12px;font-family:var(--mono);}
"""


def _tag(text: str, cls: str = "") -> str:
    return f"<span class='tag {cls}'>{html.escape(text)}</span>"


def _shell(store: FactoryStore, *, active: str, crumb: str, body: str) -> bytes:
    n_rec, n_tpl, n_skl = len(store.list_records()), len(store.list_templates()), len(store.list_skills())

    def nav(href, key, icon, label, count=None):
        cls = "active" if key == active else ""
        badge = f"<span class='count'>{count}</span>" if count is not None else ""
        return f"<a class='{cls}' href='{href}'><span class='ic'>{icon}</span>{label}{badge}</a>"

    sidebar = (
        "<aside>"
        "<div class='brand'><div class='mark'>AF</div>"
        "<div><div class='tt'>Assessment Factory</div><div class='ss'>AWS &middot; TLS house style</div></div></div>"
        "<div class='navlabel'>Workspace</div><nav>"
        f"{nav('/', 'dashboard', '&#9632;', 'Dashboard')}"
        f"{nav('/#skills', 'skills', 'S', 'Skill packages', n_skl)}"
        f"{nav('/#templates', 'templates', 'T', 'Templates', n_tpl)}"
        f"{nav('/#records', 'records', 'R', 'Source records', n_rec)}"
        "</nav>"
        "<div class='navlabel'>Pipeline</div><nav>"
        "<a href='/'><span class='ic'>1</span>Pull &amp; normalize</a>"
        "<a href='/'><span class='ic'>2</span>Build template</a>"
        "<a href='/'><span class='ic'>3</span>Generate skill</a>"
        "</nav>"
        "<div class='side-foot'>Runs fully local. Skill packages are authored by "
        "an LLM from your real assessments.</div>"
        "</aside>"
    )
    topbar = (
        f"<div class='topbar'><div class='crumb'>{crumb}</div>"
        f"<div class='pill'><span class='dot'></span>Local workspace</div></div>"
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Assessment Factory</title><style>{_CSS}</style></head><body>"
        f"<div class='layout'>{sidebar}<div class='content'>{topbar}<main>{body}</main></div></div>"
        "</body></html>"
    ).encode("utf-8")


def _dashboard(store: FactoryStore) -> str:
    records, templates, skills = store.list_records(), store.list_templates(), store.list_skills()
    stats = (
        "<div class='statline'>"
        f"<div class='s'><div class='n'>{len(records)}</div><div class='l'>Records</div></div>"
        f"<div class='s'><div class='n'>{len(templates)}</div><div class='l'>Templates</div></div>"
        f"<div class='s'><div class='n'>{len(skills)}</div><div class='l'>Skill packages</div></div>"
        "</div>"
    )
    skl_rows = "".join(
        f"<tr><td><a class='item' href='/skill?id={s.skill_id}'>{html.escape(s.name)}</a></td>"
        f"<td>{_tag(s.content_type,'type')}</td><td>{len(s.files)} files</td>"
        f"<td>{_tag((s.model_ref or {}).get('mode','?'))}</td></tr>"
        for s in skills
    ) or "<tr><td colspan=4 class='muted'>No skill packages yet.</td></tr>"
    tpl_rows = "".join(
        f"<tr><td><a class='item' href='/template?id={t.template_id}'>{html.escape(t.name)}</a></td>"
        f"<td>{_tag(t.content_type,'type')}</td><td>{len(t.derived_from)} records</td>"
        f"<td>{_tag(t.structure.get('recommended_grader_format','-'))}</td></tr>"
        for t in templates
    ) or "<tr><td colspan=4 class='muted'>No templates yet.</td></tr>"
    rec_rows = "".join(
        f"<tr><td>{html.escape(r.base_repo)}</td><td>{_tag(r.content_type,'type')}</td>"
        f"<td>{r.total_marks}</td><td>{len(r.testcases)}</td><td>{_tag(r.grader_format)}</td>"
        f"<td>{_tag('needs attention','warn') if r.warnings else _tag('clean','ok')}</td></tr>"
        for r in records
    ) or "<tr><td colspan=6 class='muted'>No records yet.</td></tr>"
    return (
        "<h1>Assessment Factory</h1>"
        "<div class='sub'>Real AWS assessments &rarr; house-style templates &rarr; reusable skill packages.</div>"
        f"{stats}"
        f"<h2 id='skills'>Skill packages ({len(skills)})</h2>"
        f"<table><tr><th>Name</th><th>Type</th><th>Files</th><th>Author</th></tr>{skl_rows}</table>"
        f"<h2 id='templates'>Templates ({len(templates)})</h2>"
        f"<table><tr><th>Name</th><th>Type</th><th>Derived from</th><th>Grader</th></tr>{tpl_rows}</table>"
        f"<h2 id='records'>Source records ({len(records)})</h2>"
        f"<table><tr><th>Repo</th><th>Type</th><th>Marks</th><th>Tests</th><th>Grader</th><th>Health</th></tr>{rec_rows}</table>"
    )


def _kv(label, value):
    return f"<div>{html.escape(label)}</div><div>{html.escape(str(value))}</div>"


def _chips(items):
    return ("<div class='chips'>" + "".join(f"<span>{html.escape(str(x))}</span>" for x in items) + "</div>") if items else "<span class='muted'>none</span>"


def _template_view(store: FactoryStore, template_id: str) -> str:
    t = store.get_template(template_id)
    hs, st, ex = t.house_style, t.structure, t.canonical_example
    facts = (
        _kv("Content type", t.content_type) + _kv("Derived from", f"{len(t.derived_from)} record(s)")
        + _kv("Recommended grader", st.get("recommended_grader_format", "-"))
        + _kv("Phases (median)", (hs.get("phase_count") or {}).get("median"))
        + _kv("Testcases (median)", (hs.get("testcase_count") or {}).get("median"))
        + _kv("Total marks (default)", (hs.get("total_marks") or {}).get("default"))
        + _kv("Duration (default)", (hs.get("duration_minutes") or {}).get("default"))
    )
    return (
        f"<h1>{html.escape(t.name)}</h1><div class='sub'>House-style blueprint distilled from real assessments.</div>"
        f"<div class='card'><div class='grid'>{facts}</div></div>"
        f"<h2>Top AWS services</h2>{_chips(hs.get('top_services', []))}"
        f"<h2>Testcase categories</h2>{_chips(hs.get('testcase_categories', []))}"
        f"<h2>Required Main files</h2>{_chips(st.get('required_main_files', []))}"
        f"<h2>Canonical example</h2><div class='card'><div class='grid'>"
        f"{_kv('Title', ex.get('title'))}{_kv('Repo', ex.get('base_repo'))}"
        f"{_kv('Total marks', ex.get('total_marks'))}{_kv('Phases', ', '.join(ex.get('phase_names', [])))}</div></div>"
        f"<h2>Full structure</h2><div class='preview'><pre class='code'>"
        f"{html.escape(json.dumps({'structure': st, 'house_style': hs, 'testcase_schema': t.testcase_schema}, indent=2, ensure_ascii=False))}"
        f"</pre></div>"
    )


def _file_icon(path: str) -> str:
    if path.endswith(".py"):
        return "&#9881;"
    if path.startswith("references/"):
        return "&#9633;"
    return "&#9632;"


def _skill_view(store: FactoryStore, skill_id: str, active_file: str) -> str:
    s = store.get_skill(skill_id)
    paths = sorted(s.files.keys(), key=lambda p: (p != "SKILL.md", p))
    if active_file not in s.files:
        active_file = s.entry if s.entry in s.files else (paths[0] if paths else "")

    def group(label, items):
        if not items:
            return ""
        links = "".join(
            f"<a class='{'active' if p == active_file else ''}' href='/skill?id={skill_id}&file={p}'>"
            f"<span class='fic'>{_file_icon(p)}</span>{html.escape(p.split('/')[-1])}</a>"
            for p in items
        )
        return f"<div class='grp'>{label}</div>{links}"

    root_files = [p for p in paths if "/" not in p]
    refs = [p for p in paths if p.startswith("references/")]
    scripts = [p for p in paths if p.startswith("scripts/")]
    tree = "<div class='tree'>" + group("Skill", root_files) + group("References", refs) + group("Scripts", scripts) + "</div>"

    content = s.files.get(active_file, "")
    if active_file.endswith(".py"):
        rendered = f"<pre class='code'>{html.escape(content)}</pre>"
    else:
        rendered = md_to_html(content)
    body = (
        f"<div class='filebody'>"
        f"<div class='filehead'><span class='path'>{html.escape(active_file)}</span>"
        f"<span class='muted'>{len(content.splitlines())} lines</span></div>"
        f"<div class='preview'>{rendered}</div></div>"
    )

    header = (
        f"<h1>{html.escape(s.name)}</h1>"
        f"<div class='sub'>Structured skill package &mdash; {len(s.files)} files. "
        f"Authored by <b>{html.escape((s.model_ref or {}).get('model') or (s.model_ref or {}).get('mode','?'))}</b>. "
        f"An agent reads <code>SKILL.md</code> first, then the references, to build the full repo set.</div>"
        f"<div class='card'><div class='grid'>"
        f"{_kv('Package id', s.skill_id)}{_kv('From template', s.template_id)}"
        f"{_kv('Content type', s.content_type)}{_kv('Hash', s.content_hash)}</div></div>"
    )
    return header + f"<div class='ide'>{tree}{body}</div>"


# --------------------------------------------------------------------------
# server (read-only)
# --------------------------------------------------------------------------

def make_handler(store: FactoryStore):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, body: bytes, code: int = 200) -> None:
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            try:
                if parsed.path == "/":
                    self._send(_shell(store, active="dashboard", crumb="<b>Dashboard</b>", body=_dashboard(store)))
                elif parsed.path == "/template":
                    t = store.get_template(qs.get("id", [""])[0])
                    self._send(_shell(store, active="templates",
                                      crumb=f"<a href='/#templates'>Templates</a> / <b>{html.escape(t.name)}</b>",
                                      body=_template_view(store, t.template_id)))
                elif parsed.path == "/skill":
                    sid = qs.get("id", [""])[0]
                    s = store.get_skill(sid)
                    self._send(_shell(store, active="skills",
                                      crumb=f"<a href='/#skills'>Skill packages</a> / <b>{html.escape(s.name)}</b>",
                                      body=_skill_view(store, sid, qs.get("file", [""])[0])))
                else:
                    self._send(_shell(store, active="dashboard", crumb="<b>Not found</b>", body="<h1>Not found</h1>"), 404)
            except Exception as exc:  # noqa: BLE001
                self._send(_shell(store, active="dashboard", crumb="<b>Error</b>",
                                  body=f"<h1>Error</h1><div class='preview'><pre class='code'>{html.escape(str(exc))}</pre></div>"), 500)

        def log_message(self, *args) -> None:
            return

    return Handler


def serve(store: FactoryStore, *, host: str = "127.0.0.1", port: int = 8799) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(store))
    print(f"Assessment Factory UI at http://{host}:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
