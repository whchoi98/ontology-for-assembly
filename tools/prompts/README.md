# tools/prompts/

LLM prompt 저장소 — Sonnet 4.6, Cohere embed-v4, rerank-v3에 보내는 *재사용 가능한 프롬프트 템플릿*.

## 파일 규칙

| File | Purpose |
|---|---|
| `chat-system-base.md` | 챗봇 base system prompt (페르소나 무관 공통) |
| `insight-5section.md` | 14 시나리오 insight 5-section markdown 출력 형식 |
| `multi-agent-{planner,graph,analyst,editor}.md` | Agentic AI 4 에이전트 각 system prompt |
| `bedrock-guardrails.md` | ADR-0004 정치 중립성 4-layer 가드레일 prompt |

## 작성 원칙

1. **출처 명시 강제**: 모든 정량 수치에 `(출처: ...)` 필수.
2. **정치 중립성**: 정파 단정·평가 표현 금지 (ADR-0004).
3. **persona-aware**: `{persona_name_kr}`, `{persona_kpi_focus}` 같은 변수 사용.
4. **시연 결정성**: 같은 입력 → 같은 출력 (Bedrock temperature 0.2 이하 권장).

## 사용

Backend `api/services/bedrock.py`의 `_build_prompt()` 같은 helper에서 import.
변경 시 `tests/test_bedrock.py` smoke test 통과 확인.

## 참고

- `docs/decisions/0004-political-neutrality-guardrails.md` — 가드레일 설계 근거
- `api/services/persona.py:PERSONA_REGISTRY` — 페르소나 변수 SSOT
