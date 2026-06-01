# ontology/ — Domain Ontology Catalog (Scaffold)

`ontology/`는 도메인 모델의 **사람용 카탈로그**를 담도록 설계된 디렉토리다. 현재는 스캐폴드 상태로 대부분 비어 있고, **실제 클래스/관계 카탈로그는 코드에 산다**:

- **코드 SSOT (Pydantic)**: `data/schemas.py` — 31 클래스 + 관계 메타.
- **표시 카탈로그 SSOT**: `api/services/objects_catalog.py` — Object Explorer(`/api/objects`)와 온톨로지 메타 API(`/api/ontology/classes`, `/api/ontology/{class}`)가 모두 여기서 서빙. 31 클래스, 7 그룹.

## 현재 디렉토리 상태

```
ontology/
├── __init__.py
├── adapters/                     __init__.py만 (외부 표준 변환 어댑터 예약 위치)
├── classes/                      (비어 있음 — 클래스 yaml 카탈로그 예약)
├── relations/                    (비어 있음 — 관계 yaml 예약)
├── mappings/                     (비어 있음 — 필드/값 매핑 예약)
└── standards/                    (비어 있음 — 외부 표준 코드 카탈로그 예약)
```

> 주의: 이전 버전 문서가 기술하던 `classes/*.yaml`, `relations/*.yaml`, `mappings/assembly_api_fields.yaml`, `standards/*.yaml`, `schema.ttl`, `upload.py`는 **현재 존재하지 않는다**. 온톨로지 메타가 필요하면 `api/services/objects_catalog.py`를 본다. 이 디렉토리를 yaml 카탈로그로 채우는 것은 향후 작업(planned).

## Key Design Decisions

- **클래스 SSOT는 `data/schemas.py`** (Pydantic v2). 표시·API 메타는 `api/services/objects_catalog.py`.
- **정치 중립성** (ADR-0004): `Person.political_leaning` 등 정치 성향 추론 속성 절대 생성 금지. 카탈로그에도 추가 금지. security-auditor agent가 차단.
- **정당명 중립 표기**: 약칭/별명 대신 공식 등록명만. 이념 라벨(보수/진보) 미포함. 정치 인물의 raw OpenAPI `POLY_NM`(예: 형식상 무소속)은 그대로 신뢰.
- **표준 코드 차용**: 국회 OpenAPI 코드(의안 카테고리, 정당, 위원회)와 KOSTAT 시도/시군구 코드를 그대로 사용. 임의 코드 신설 금지.

## Adding a New Class

`/CLAUDE.md` "Auto-Sync Rules" 참조. 새 클래스 추가 시:
1. `data/schemas.py` Pydantic 모델 (코드 SSOT)
2. `api/services/objects_catalog.py` 클래스 메타 등록 (그룹·필드·구현 여부)
3. `web/app/objects/[type]/page.tsx:TYPE_META` + 사이드바 객체 탐색 섹션
4. (persistent 시) `data/synthetic/` generator, 아니면 `data/synthetic/placeholders.py`

## 관련

- ADR-0001 (gcc 차용 — 클래스 패턴)
- ADR-0002 (Persona 클래스 — SSOT)
- ADR-0003 (Reader / ReaderProfile / SubscriptionTier)
- ADR-0004 (political_leaning 등 금지 필드)
- ADR-0010 (real data 어댑터 필드 매핑)
