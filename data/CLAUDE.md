# data/ — Real + Synthetic + External Data Pipeline

`data/`는 3종 데이터 소스를 단일 진실원으로 통합 적재한다. **API 이미지가 일회성 ECS 태스크로 `python -m data.load`를 실행**해 Neptune + OpenSearch에 ~100만+ 노드 적재.

## Structure

```
data/
├── load.py                       CLI 진입점 (argparse: --source --to --bucket --seed --neptune --opensearch)
├── load_aws.py                   AWS 적재: NDJSON→S3 + S3→Neptune Bulk Loader + NDJSON→OpenSearch
├── schemas.py                    31 클래스 Pydantic v2 + 관계 메타 (코드 SSOT)
├── real/                         국회 OpenAPI 어댑터
│   ├── _client.py                공통 HTTP 클라이언트 (retry + rate limit)
│   ├── bill.py                   /bill, /bill_history → :Bill, :Amendment
│   ├── member.py                 /member, /member_profile → :Person, :District
│   ├── vote.py                   /vote, /vote_result → :Vote
│   ├── committee.py              /committee, /committee_members → :Committee
│   ├── session.py                /session_minutes → :Session, :Statement
│   ├── party.py                  /party → :Party
│   └── agency.py                 /agency, /audit_target → :Agency
├── synthetic/                    합성 generator
│   ├── reader.py                 :Reader + :ReadingEvent
│   ├── advertisement.py          :Advertisement + :AdInventory
│   ├── article.py                :Article + author 매핑
│   ├── topics.py                 :Topic 시드
│   ├── placeholders.py           미구현 클래스 placeholder 인스턴스
│   └── seeds.py                  PDF 시그니처 시연 시드 (3-stage chat, 광고 거절 예시)
├── external/                     외부 API ETL
│   ├── naver_news.py             네이버 뉴스 검색 → :SocialSignal
│   └── poll_result.py            여론조사 (real 가능 시) / synthetic
├── loader/                       Bulk Loader 헬퍼 패키지 (현재 __init__만)
├── public/                       표준 어댑터 디렉토리 (현재 비어 있음)
└── output/                       JSON/NDJSON 출력 (S3 sync)
```

## Key Design Decisions

- **`schemas.py` SSOT**: 31 클래스 Pydantic 모델 + 관계 메타. API 측 표시 카탈로그는 `api/services/objects_catalog.py`.
- **3-tier source 태깅**: 모든 노드에 `source ∈ {real, synthetic, external}` 속성. `DataSourceBadge`가 이걸로 표시.
- **Reader 익명화** (ADR-0003 + ADR-0004): `reader_id`는 솔티드 SHA-256 해시. IP/UA 원본 절대 저장 금지. `political_leaning` 등 정치 성향 필드 절대 생성 금지.
- **Neptune Bulk Loader 우선** (ADR-0001 gcc D10): ~100만 노드 7~8배 빠름. CSV 포맷 불일치 시 `cypher_bulk.py` 폴백.
- **국회 OpenAPI rate limit**: 분당 1,000 req. 어댑터에 retry + S3 캐시 (24h TTL).

## Conventions

- **어댑터 함수 시그니처**: `def fetch_<entity>(since: date | None = None) -> Iterator[<EntityModel>]`. Generator로 큰 컬렉션 lazy 처리.
- **국회 API 응답 매핑**: 어댑터 코드 내부에 인라인 정의 (예: `data/real/member.py`에서 `MONA_CD` → `assembly_id`). 매핑 근거는 ADR-0010.
- **합성 시드**: `seeds.py`에 PDF 시그니처(시나리오 B 3-stage, L 광고 거절, K 표결 이탈) 명시 시나리오 시드.
- **외부 API 키**: 절대 코드 하드코딩 금지. `aws_clients.py:get_secret()` 경유.

## Adding a New Class

`/CLAUDE.md` "Auto-Sync Rules" — 새 클래스 추가 시 6곳 동시 수정:
1. `data/schemas.py` Pydantic 모델 추가
2. `data/synthetic/` (persistent 시) generator 작성, 아니면 `synthetic/placeholders.py`
3. `api/services/objects_catalog.py` 클래스 메타 등록 (`/api/objects`·`/api/ontology` 카탈로그 SSOT)
4. `web/app/objects/[type]/page.tsx:TYPE_META` + 사이드바 객체 탐색 섹션

## Running the Loader

배포된 환경에서 (one-shot ECS task):
```bash
aws ecs run-task \
  --cluster assembly-dev-cluster \
  --task-definition assembly-dev-api \
  --launch-type FARGATE \
  --overrides '{"containerOverrides":[{"name":"api","command":["python","-m","data.load","--source","all","--to","s3","--bucket","assembly-dev-synthetic-data","--neptune","--opensearch"]}]}'
```

로컬 dev (Neptune VPC 접근 불가 — DB 적재 플래그 생략, NDJSON만 로컬/S3로):
```bash
python -m data.load --source synthetic --to local --out-dir ./data/output
```

## 데이터 검증

- 적재/데이터셋 검증: `python scripts/verify_demo_dataset.py` (각 클래스 노드 수 + 핵심 관계 카운트 + source 태그 무결성). 테스트는 `tests/test_verify_demo_dataset.py`.
- 출처 배지 무결성: 모든 노드가 `source ∈ {real, synthetic, external}` 속성을 가져야 함.
- 정치 성향 필드 미존재: `Reader.political_leaning` 등 추론 필드 생성 금지 (ADR-0004). `tests/test_schemas.py`가 스키마 레벨에서 강제.

## Related ADRs

- ADR-0001 (gcc 패턴 차용 — Bulk Loader, source 태깅)
- ADR-0003 (Reader 익명화 - 솔티드 해시)
- ADR-0004 (정치 성향 필드 생성 금지)
