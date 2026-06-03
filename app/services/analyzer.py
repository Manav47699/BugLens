"""
L4 AI Analysis Engine — Ollama backend
---------------------------------------
Calls a local Ollama instance (http://localhost:11434) instead of any
paid API.  Works with any model you have pulled:
  ollama pull llama3       # recommended — good at JSON
  ollama pull mistral
  ollama pull gemma3

Set OLLAMA_MODEL and optionally OLLAMA_HOST in your .env.
"""

import json
import re
import urllib.request
import urllib.error
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.models.report import (
    BugEvidence,
    BugReport,
    DebugReport,
    score_to_severity,
)
from app.models.session import Session

log = get_logger(__name__)

_SYSTEM_PROMPT = """
You are BugLens, an expert frontend bug analysis engine.

You receive structured JSON evidence collected by an autonomous browser
agent that crawled a React/Next.js/Vite web app. Analyse it and return
a JSON array of bug reports — nothing else, no markdown, no commentary.

Each object in the array must have exactly these keys:
{
  "title": "Short (max 10 words) human-readable title",
  "problem": "One sentence: what does the user experience?",
  "cause": "One sentence: what is the likely root cause?",
  "fix": "One concrete actionable fix, with a code snippet if helpful.",
  "file": "Probable source file path if inferable from stack traces, else null",
  "route": "The route where the bug was observed",
  "disaster_score": <number 0.0 to 10.0>,
  "reproduced_ratio": "<N>/<M> attempts"
}

Disaster Score rubric:
  0-2   Minor UI glitch, no user impact
  3-5   Broken flow, some users affected
  6-8   Core feature down, most users affected
  9-10  App unusable or data loss

Extra rules:
- Return ONLY the JSON array. No backticks, no explanation before or after.
- Merge duplicate errors from the same route into one report.
- Skip: favicon 404s, HMR messages, source map warnings.
- If there are zero real bugs return exactly: []
""".strip()


class Analyzer:
    def __init__(self, session: Session):
        self.session = session

    async def analyze(
        self,
        evidence_list: list[BugEvidence],
        framework: Optional[str],
        routes_explored: list[str],
    ) -> DebugReport:
        if not evidence_list:
            self.session.log("No errors captured — app looks clean!")
            return DebugReport(
                session_id=self.session.id,
                framework=framework,
                routes_explored=routes_explored,
                bugs=[],
            )

        self.session.log(
            f"Sending {len(evidence_list)} evidence bundle(s) to "
            f"Ollama ({settings.ollama_model})…"
        )

        user_message = self._build_message(evidence_list, framework, routes_explored)
        raw = self._call_ollama(user_message)
        bugs = self._parse_bugs(raw, evidence_list)

        self.session.log(f"Analysis complete — {len(bugs)} bug(s) found.")

        return DebugReport(
            session_id=self.session.id,
            framework=framework,
            routes_explored=routes_explored,
            bugs=bugs,
        )

    # ------------------------------------------------------------------
    # Build prompt payload
    # ------------------------------------------------------------------

    def _build_message(
        self,
        evidence_list: list[BugEvidence],
        framework: Optional[str],
        routes_explored: list[str],
    ) -> str:
        payload = {
            "framework": framework or "unknown",
            "routes_explored": routes_explored,
            "evidence": [
                {
                    "route": e.route,
                    "js_errors": e.js_errors,
                    "console_warnings": e.console_warnings,
                    "failed_requests": [
                        {"method": r.method, "url": r.url, "status": r.status}
                        for r in e.failed_requests
                    ],
                    "reproduction_count": e.reproduction_count,
                    "reproduction_attempts": e.reproduction_attempts,
                }
                for e in evidence_list
            ],
        }
        return json.dumps(payload, indent=2)

    # ------------------------------------------------------------------
    # Ollama HTTP call  (uses stdlib only — no extra deps)
    # ------------------------------------------------------------------

    def _call_ollama(self, user_message: str) -> str:
        url = f"{settings.ollama_host}/api/chat"

        body = json.dumps({
            "model": settings.ollama_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            # Ask Ollama to constrain output to JSON
            "format": "json",
        }).encode()

        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read())
                return data["message"]["content"]
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Could not reach Ollama at {settings.ollama_host}. "
                f"Is it running?  Try: ollama serve\nError: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Parse the model's JSON response into BugReport objects
    # ------------------------------------------------------------------

    def _parse_bugs(
        self, raw: str, evidence_list: list[BugEvidence]
    ) -> list[BugReport]:
        # Strip accidental markdown fences some models add despite instructions
        cleaned = re.sub(r"^```[a-z]*\n?", "", raw.strip())
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()

        try:
            items = json.loads(cleaned)
        except json.JSONDecodeError:
            # Some models wrap the array in {"bugs": [...]} — unwrap it
            try:
                wrapper = json.loads(cleaned)
                items = next(
                    v for v in wrapper.values() if isinstance(v, list)
                )
            except Exception:
                log.error(f"Could not parse Ollama response as JSON:\n{cleaned[:400]}")
                return []

        if not isinstance(items, list):
            log.error("Expected a JSON array from Ollama, got something else.")
            return []

        evidence_by_route = {e.route: e for e in evidence_list}
        bugs: list[BugReport] = []

        for item in items:
            try:
                score = float(item.get("disaster_score", 5.0))
                score = max(0.0, min(10.0, score))
                route = item.get("route", "/")
                evidence = evidence_by_route.get(route, BugEvidence(route=route))

                bugs.append(BugReport(
                    title=item.get("title", "Untitled bug"),
                    problem=item.get("problem", ""),
                    cause=item.get("cause", ""),
                    fix=item.get("fix", ""),
                    file=item.get("file"),
                    route=route,
                    disaster_score=score,
                    severity=score_to_severity(score),
                    evidence=evidence,
                    reproduced=item.get("reproduced_ratio", "1/1"),
                ))
            except Exception as exc:
                log.warning(f"Skipping malformed item: {exc} — {item}")

        bugs.sort(key=lambda b: b.disaster_score, reverse=True)
        return bugs