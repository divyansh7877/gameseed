from __future__ import annotations

import json
from typing import Any, Protocol

import httpx

from app.config import Settings
from app.models import GameManifest, GenerateGameRequest, ManifestValidationReport, RunnerSpec, ValidationIssue


class ManifestValidator(Protocol):
    async def refine_runner_spec(self, request_body: GenerateGameRequest, initial_spec: RunnerSpec) -> tuple[RunnerSpec, dict[str, Any] | None]:
        ...

    async def review_manifest(
        self,
        request_body: GenerateGameRequest,
        draft_manifest: GameManifest,
    ) -> tuple[GameManifest, ManifestValidationReport | None, dict[str, Any] | None]:
        ...


class GeminiManifestValidator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.enable_gemini_validation and self.settings.gemini_api_key)

    async def refine_runner_spec(self, request_body: GenerateGameRequest, initial_spec: RunnerSpec) -> tuple[RunnerSpec, dict[str, Any] | None]:
        if not self.enabled:
            return initial_spec, None

        prompt = (
            "You are validating a side-view endless runner game design spec.\n"
            "Improve coherence with the user's prompt while staying within a runner template.\n"
            "Return JSON with keys: approved, summary, applied_fixes, runner_spec.\n"
            "Rules:\n"
            "- Keep difficulty, audience, session_length_sec, and prompt_seed unchanged.\n"
            "- runner_spec must contain exactly 3 obstacles, exactly 1 collectible, and exactly 5 hex palette colors.\n"
            "- Prefer a specific theme and title that match the user prompt.\n"
            "- Do not invent mechanics outside a runner game.\n"
            f"request={json.dumps(request_body.model_dump(mode='json'), ensure_ascii=True)}\n"
            f"initial_spec={json.dumps(initial_spec.model_dump(mode='json'), ensure_ascii=True)}"
        )
        payload = await self._generate_json(prompt)
        if not payload or "runner_spec" not in payload:
            return initial_spec, payload

        candidate = RunnerSpec.model_validate(payload["runner_spec"])
        candidate = candidate.model_copy(
            update={
                "difficulty": initial_spec.difficulty,
                "audience": initial_spec.audience,
                "session_length_sec": initial_spec.session_length_sec,
                "prompt_seed": initial_spec.prompt_seed,
                "obstacle_set": list(candidate.obstacle_set[:3]) if candidate.obstacle_set else list(initial_spec.obstacle_set),
                "collectible_set": list(candidate.collectible_set[:1]) if candidate.collectible_set else list(initial_spec.collectible_set),
                "palette": list(candidate.palette[:5]) if len(candidate.palette) >= 5 else list(initial_spec.palette),
            }
        )
        return candidate, payload

    async def review_manifest(
        self,
        request_body: GenerateGameRequest,
        draft_manifest: GameManifest,
    ) -> tuple[GameManifest, ManifestValidationReport | None, dict[str, Any] | None]:
        if not self.enabled:
            return draft_manifest, None, None

        prompt = (
            "You are validating a generated endless runner manifest for coherence.\n"
            "Check whether the manifest fits the original prompt, asset outcomes, and theme.\n"
            "You may only patch text fields, not gameplay physics, assets, or spawn_table.\n"
            "Return JSON with keys: approved, coherence_score, summary, issues, recommendations, applied_fixes, patches.\n"
            "Allowed patches keys: title, ui_title, ui_subtitle, runner_synopsis, runner_art_style.\n"
            f"request={json.dumps(request_body.model_dump(mode='json'), ensure_ascii=True)}\n"
            f"manifest={json.dumps(draft_manifest.model_dump(mode='json'), ensure_ascii=True)}"
        )
        payload = await self._generate_json(prompt)
        if not payload:
            return draft_manifest, None, payload

        report = ManifestValidationReport(
            validator="gemini",
            approved=bool(payload.get("approved", False)),
            coherence_score=float(payload.get("coherence_score", 0.0)),
            summary=str(payload.get("summary", "")),
            issues=self._normalize_issues(payload.get("issues", [])),
            recommendations=[str(item) for item in payload.get("recommendations", [])],
            applied_fixes=[str(item) for item in payload.get("applied_fixes", [])],
        )

        patches = payload.get("patches", {}) if isinstance(payload.get("patches"), dict) else {}
        updated = draft_manifest.model_copy(deep=True)
        if patches.get("title"):
            updated.title = str(patches["title"])
        if patches.get("ui_title"):
            updated.ui.title = str(patches["ui_title"])
        else:
            updated.ui.title = updated.title
        if patches.get("ui_subtitle"):
            updated.ui.subtitle = str(patches["ui_subtitle"])
        if patches.get("runner_synopsis"):
            updated.runner_spec.synopsis = str(patches["runner_synopsis"])
        if patches.get("runner_art_style"):
            updated.runner_spec.art_style = str(patches["runner_art_style"])
        updated.validation = report
        return updated, report, payload

    @staticmethod
    def _normalize_issues(raw_issues: Any) -> list[ValidationIssue]:
        if not isinstance(raw_issues, list):
            return []
        normalized: list[ValidationIssue] = []
        for item in raw_issues:
            if isinstance(item, dict):
                normalized.append(
                    ValidationIssue(
                        severity=str(item.get("severity", "info")),
                        field=str(item.get("field", "manifest")),
                        message=str(item.get("message", "")),
                    )
                )
                continue
            if isinstance(item, str):
                normalized.append(
                    ValidationIssue(
                        severity="info",
                        field="manifest",
                        message=item,
                    )
                )
        return normalized

    async def _generate_json(self, prompt: str) -> dict[str, Any] | None:
        url = f"{self.settings.gemini_base_url.rstrip('/')}/models/{self.settings.gemini_model}:generateContent"
        request_body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "response_mime_type": "application/json",
            },
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(url, params={"key": self.settings.gemini_api_key}, json=request_body)
            response.raise_for_status()
            payload = response.json()
        text = (
            payload.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        if not text:
            return None
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
