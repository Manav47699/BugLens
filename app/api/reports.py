"""
Reports API
GET  /reports            — list all reports
GET  /reports/{id}       — full report as JSON
GET  /reports/{id}/view  — human-readable HTML page
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.db import store
from app.models.report import Severity

router = APIRouter(prefix="/reports", tags=["reports"])


# ── JSON endpoints ────────────────────────────────────────────────────

@router.get("")
async def list_reports():
    reports = store.list_reports()
    return [_summary(r) for r in reports]


@router.get("/{report_id}")
async def get_report(report_id: str):
    r = store.load_report(report_id)
    if not r:
        raise HTTPException(status_code=404, detail="Report not found.")
    return _full(r)


# ── HTML viewer ───────────────────────────────────────────────────────

@router.get("/{report_id}/view", response_class=HTMLResponse)
async def view_report(report_id: str):
    r = store.load_report(report_id)
    if not r:
        raise HTTPException(status_code=404, detail="Report not found.")
    return HTMLResponse(_render_html(r))


# ── Helpers ───────────────────────────────────────────────────────────

def _summary(r: dict) -> dict:
    bugs = r.get("bugs", [])
    critical = sum(1 for b in bugs if b.get("severity") == "critical")
    high     = sum(1 for b in bugs if b.get("severity") == "high")
    top      = max((b.get("disaster_score", 0) for b in bugs), default=0.0)
    return {
        "id":                r["id"],
        "session_id":        r["session_id"],
        "framework":         r.get("framework"),
        "bug_count":         len(bugs),
        "critical_count":    critical,
        "high_count":        high,
        "top_disaster_score": top,
        "created_at":        r.get("created_at"),
        "view_url":          f"/reports/{r['id']}/view",
    }


def _full(r: dict) -> dict:
    bugs = r.get("bugs", [])
    critical = sum(1 for b in bugs if b.get("severity") == "critical")
    high     = sum(1 for b in bugs if b.get("severity") == "high")
    top      = max((b.get("disaster_score", 0) for b in bugs), default=0.0)
    return {
        "id":             r["id"],
        "session_id":     r["session_id"],
        "framework":      r.get("framework"),
        "routes_explored": r.get("routes_explored", []),
        "created_at":     r.get("created_at"),
        "view_url":       f"/reports/{r['id']}/view",
        "summary": {
            "total_bugs":        len(bugs),
            "critical":          critical,
            "high":              high,
            "top_disaster_score": top,
        },
        "bugs": [
            {
                "id":             b.get("id"),
                "title":          b.get("title"),
                "severity":       b.get("severity"),
                "disaster_score": b.get("disaster_score"),
                "problem":        b.get("problem"),
                "cause":          b.get("cause"),
                "fix":            b.get("fix"),
                "file":           b.get("file"),
                "route":          b.get("route"),
                "reproduced":     b.get("reproduced"),
                "evidence": {
                    "js_errors":       b.get("evidence", {}).get("js_errors", []),
                    "console_warnings": b.get("evidence", {}).get("console_warnings", []),
                    "failed_requests": b.get("evidence", {}).get("failed_requests", []),
                    "screenshot_path": b.get("evidence", {}).get("screenshot_path"),
                },
            }
            for b in bugs
        ],
    }


# ── HTML renderer ─────────────────────────────────────────────────────

def _esc(s) -> str:
    return str(s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"','&quot;')

def _score_color(score: float) -> str:
    if score >= 9: return "#f85149"
    if score >= 6: return "#f0883e"
    if score >= 3: return "#d29922"
    return "#3fb950"

def _sev_style(sev: str) -> str:
    return {
        "critical": "background:#2d1a1a;color:#f85149;border:1px solid #f8514955",
        "high":     "background:#2a1f12;color:#f0883e;border:1px solid #f0883e55",
        "medium":   "background:#26220d;color:#d29922;border:1px solid #d2992255",
        "low":      "background:#0d2416;color:#3fb950;border:1px solid #3fb95055",
    }.get(sev, "background:#21262d;color:#8b949e;border:1px solid #30363d")


def _render_html(r: dict) -> str:
    bugs = r.get("bugs", [])
    routes = r.get("routes_explored", [])
    framework = r.get("framework") or "unknown"
    created = r.get("created_at", "")[:19].replace("T", " ")
    top_score = max((b.get("disaster_score", 0) for b in bugs), default=0.0)
    critical  = sum(1 for b in bugs if b.get("severity") == "critical")
    high      = sum(1 for b in bugs if b.get("severity") == "high")

    bugs_html = ""
    if not bugs:
        bugs_html = """
        <div style="text-align:center;padding:60px 20px;color:#8b949e">
          <div style="font-size:48px;margin-bottom:16px">✅</div>
          <h2 style="color:#e6edf3;margin-bottom:8px">No bugs found</h2>
          <p>BugLens explored every route and found nothing. Ship it.</p>
        </div>"""
    else:
        for b in bugs:
            score = b.get("disaster_score", 0)
            sev   = b.get("severity", "low")
            color = _score_color(score)
            ev    = b.get("evidence", {})
            js_errors    = ev.get("js_errors", [])
            failed_reqs  = ev.get("failed_requests", [])
            warnings     = ev.get("console_warnings", [])

            evidence_html = ""
            if js_errors:
                items = "".join(f'<div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:8px 12px;font-family:monospace;font-size:12px;color:#f85149;word-break:break-all;margin-bottom:6px">{_esc(e)}</div>' for e in js_errors)
                evidence_html += f'<div style="margin-top:12px"><div style="font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">JS Errors</div>{items}</div>'

            if failed_reqs:
                items = ""
                for req in failed_reqs:
                    sc = req.get("status", 0)
                    sc_color = "#f85149" if sc >= 500 else "#f0883e"
                    items += f'<div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:8px 12px;font-family:monospace;font-size:12px;display:flex;gap:10px;margin-bottom:6px"><span style="color:#d29922;font-weight:700">{_esc(req.get("method",""))}</span><span style="color:#8b949e;flex:1;word-break:break-all">{_esc(req.get("url",""))}</span><span style="color:{sc_color};font-weight:700">{sc}</span></div>'
                evidence_html += f'<div style="margin-top:12px"><div style="font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Failed Requests</div>{items}</div>'

            if warnings:
                items = "".join(f'<div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:8px 12px;font-family:monospace;font-size:12px;color:#d29922;word-break:break-all;margin-bottom:6px">{_esc(w)}</div>' for w in warnings)
                evidence_html += f'<div style="margin-top:12px"><div style="font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Console Warnings</div>{items}</div>'

            file_html = ""
            if b.get("file"):
                file_html = f'<div style="margin-bottom:16px"><div style="font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">File</div><code style="background:#21262d;padding:4px 10px;border-radius:4px;font-size:13px;color:#00d4e8">{_esc(b["file"])}</code></div>'

            evidence_section = ""
            if evidence_html:
                evidence_section = f'<details style="margin-top:16px"><summary style="cursor:pointer;font-size:13px;color:#8b949e;padding:6px 0">▶ Raw Evidence ({len(js_errors)+len(failed_reqs)+len(warnings)} item(s))</summary>{evidence_html}</details>'

            bugs_html += f"""
            <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;margin-bottom:20px;overflow:hidden">
              <!-- Card header -->
              <div style="padding:18px 22px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
                <span style="{_sev_style(sev)};font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;text-transform:uppercase;letter-spacing:.5px">{sev.upper()}</span>
                <span style="font-size:16px;font-weight:700;flex:1">{_esc(b.get("title",""))}</span>
                <span style="font-family:monospace;font-size:12px;color:#00d4e8;background:rgba(0,212,232,.08);padding:3px 10px;border-radius:4px">{_esc(b.get("route",""))}</span>
                <span style="font-size:22px;font-weight:800;color:{color}">{score:.1f}</span>
              </div>
              <!-- Score bar -->
              <div style="padding:0 22px 16px;display:flex;align-items:center;gap:10px">
                <span style="font-size:11px;color:#8b949e;width:90px">Disaster Score</span>
                <div style="flex:1;height:6px;background:#30363d;border-radius:3px;overflow:hidden">
                  <div style="width:{score/10*100:.0f}%;height:100%;background:{color};border-radius:3px"></div>
                </div>
              </div>
              <!-- Body -->
              <div style="padding:0 22px 22px">
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
                  <div>
                    <div style="font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Problem</div>
                    <div style="font-size:14px;line-height:1.7;color:#e6edf3">{_esc(b.get("problem",""))}</div>
                  </div>
                  <div>
                    <div style="font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Cause</div>
                    <div style="font-size:14px;line-height:1.7;color:#e6edf3">{_esc(b.get("cause",""))}</div>
                  </div>
                </div>
                {file_html}
                <div style="background:#161b22;border:1px solid #30363d;border-left:3px solid #3fb950;border-radius:6px;padding:16px 18px">
                  <div style="font-size:11px;color:#3fb950;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">💡 Suggested Fix</div>
                  <div style="font-size:14px;line-height:1.7;color:#e6edf3">{_esc(b.get("fix",""))}</div>
                </div>
                <div style="margin-top:10px;font-size:12px;color:#8b949e">
                  Reproduced: <b style="color:#e6edf3">{_esc(b.get("reproduced",""))}</b>
                </div>
                {evidence_section}
              </div>
            </div>"""

    routes_html = " ".join(
        f'<span style="background:#21262d;border:1px solid #30363d;border-radius:4px;padding:3px 10px;font-family:monospace;font-size:12px;color:#00d4e8">{_esc(rt)}</span>'
        for rt in routes
    ) or "—"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>BugLens Report — {_esc(r["id"][:8])}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.5}}
    details summary:hover{{color:#e6edf3}}
    @media(max-width:600px){{.grid-2{{grid-template-columns:1fr!important}}}}
  </style>
</head>
<body>
<!-- Header -->
<div style="background:#161b22;border-bottom:1px solid #30363d;padding:16px 32px;display:flex;align-items:center;gap:12px">
  <span style="font-size:20px;font-weight:700;color:#00d4e8">🔍 BugLens</span>
  <span style="color:#8b949e;font-size:13px">Bug Report</span>
  <div style="flex:1"></div>
  <a href="/reports" style="color:#8b949e;font-size:13px;text-decoration:none">← All Reports</a>
</div>

<div style="max-width:1000px;margin:0 auto;padding:32px 24px">

  <!-- Meta -->
  <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px 22px;margin-bottom:24px;display:flex;gap:24px;flex-wrap:wrap;font-size:13px;color:#8b949e">
    <span><b style="color:#e6edf3">Report ID:</b> {_esc(r["id"])}</span>
    <span><b style="color:#e6edf3">Framework:</b> {_esc(framework)}</span>
    <span><b style="color:#e6edf3">Generated:</b> {_esc(created)}</span>
  </div>

  <!-- Summary cards -->
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:16px;margin-bottom:32px">
    <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px;text-align:center">
      <div style="font-size:38px;font-weight:800;color:{_score_color(top_score)}">{top_score:.1f}</div>
      <div style="font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-top:4px">Top Score</div>
    </div>
    <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px;text-align:center">
      <div style="font-size:38px;font-weight:800;color:#f85149">{critical}</div>
      <div style="font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-top:4px">Critical</div>
    </div>
    <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px;text-align:center">
      <div style="font-size:38px;font-weight:800;color:#f0883e">{high}</div>
      <div style="font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-top:4px">High</div>
    </div>
    <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px;text-align:center">
      <div style="font-size:38px;font-weight:800;color:#a371f7">{len(bugs)}</div>
      <div style="font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-top:4px">Total Bugs</div>
    </div>
    <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px;text-align:center">
      <div style="font-size:38px;font-weight:800;color:#a371f7">{len(routes)}</div>
      <div style="font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-top:4px">Routes Tested</div>
    </div>
  </div>

  <!-- Routes -->
  <div style="margin-bottom:28px">
    <div style="font-size:13px;font-weight:600;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px">Routes Explored</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">{routes_html}</div>
  </div>

  <!-- Bug list -->
  <div style="font-size:13px;font-weight:600;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:16px">
    Bug Reports &nbsp;<span style="background:#21262d;border:1px solid #30363d;border-radius:20px;padding:2px 10px;font-size:12px;color:#e6edf3">{len(bugs)}</span>
  </div>
  {bugs_html}

</div>
</body>
</html>"""