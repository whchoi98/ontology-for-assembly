# data/ — Real + Synthetic + External Data Pipeline

`data/`는 3종 데이터 소스를 단일 진실원으로 통합 적재한다. **API 이미지가 일회성 ECS 태스크로 `python -m data.load`를 실행**해 Neptune + OpenSearch에 ~100만+ 노드 적재.

## Structure

```
data/
├── load.py                       CLI 진입점 (--neptune --opensearch --from-s3)
├── load_graph.py                 Neptune Bulk Loader 호출 + 폴백 openCypher MERGE
├── load_search.py                OpenSearch 인덱스 적재
├── schemas.py                    25+ 클래스 Pydantic v2 + 관계 메타 (SSOT)
├── real/                         국회 OpenAPI 어댑터
│   ├── bill.py                   /bill, /bill_history → :Bill, :Amendment
│   ├── member.py                 /member, /member_profile → :Person, :District
│   ├── vote.py                   /vote, /vote_result → :Vote
│   ├── committee.py              /committee, /committee_members → :Committee
│   ├── session.py                /session_minutes → :Session, :Statement
│   ├── party.py                  /party → :Party
│   └── agency.py                 /agency, /audit_target → :Agency
├── synthetic/                    합성 generator
│   ├── reader.py                 ~50,000 :Reader + :ReadingEvent
│   ├── advertisement.py          ~500 :Advertisement + :AdInventory
│   ├── article.py                ~2,000 :Article + author 매핑
│   └── seeds.py                  PDF 시그니처 시연 시드 (3-stage chat, 광고 거절 예시)
├── external/                     외부 API ETL
│   ├── naver_news.py             네이버 뉴스 검색 → :SocialSignal
│   ├── sns_signal.py             SNS 합성 (Phase 5 polish에서 실 API)
│   └── poll_result.py            여론조사 (real 가능 시) / synthetic
├── loader/                       Bulk Loader 헬퍼
│   ├── csv_writer.py             클래스별 CSV 출력
│   └── cypher_bulk.py            UNWIND MERGE 폴백 (CSV 포맷 불일치 시)
├── public/                       표준 어댑터 (sido_code, party_code etc.)
└── output/                       JSON/NDJSON 출력 (S3 sync)
```

## Key Design Decisions

- **`schemas.py` SSOT**: 25+ 클래스 Pydantic 모델 + 관계 메타. `ontology/classes/*.yaml`은 사람용 카탈로그.
- **3-tier source 태깅**: 모든 노드에 `source ∈ {real, synthetic, external}` 속성. `DataSourceBadge`가 이걸로 표시.
- **Reader 익명화** (ADR-0003 + ADR-0004): `reader_id`는 솔티드 SHA-256 해시. IP/UA 원본 절대 저장 금지. `political_leaning` 등 정치 성향 필드 절대 생성 금지.
- **Neptune Bulk Loader 우선** (ADR-0001 gcc D10): ~100만 노드 7~8배 빠름. CSV 포맷 불일치 시 `cypher_bulk.py` 폴백.
- **국회 OpenAPI rate limit**: 분당 1,000 req. 어댑터에 retry + S3 캐시 (24h TTL).

## Conventions

- **어댑터 함수 시그니처**: `def fetch_<entity>(since: date | None = None) -> Iterator[<EntityModel>]`. Generator로 큰 컬렉션 lazy 처리.
- **국회 API 응답 매핑**: `mappings/assembly_api_fields.yaml` (예: `MONA_CD` → `assembly_id`).
- **합성 시드**: `seeds.py`에 PDF 시그니처(시나리오 B 3-stage, L 광고 거절, K 표결 이탈) 명시 시나리오 시드.
- **외부 API 키**: 절대 코드 하드코딩 금지. `aws_clients.py:get_secret()` 경유.

## Adding a New Class

`/CLAUDE.md` "Auto-Sync Rules" — 새 클래스 추가 시 6곳 동시 수정:
1. `data/schemas.py` Pydantic 모델 추가
2. `data/synthetic/` (persistent 시) generator 작성
3. `ontology/classes/<name>.yaml` 카탈로그 entry
4. `api/routers/objects.py:_TYPE_REGISTRY` 등록
5. `api/routers/ontology.py:_CLASSES`/`_RELATIONS` 등록
6. `web/app/objects/[type]/page.tsx:TYPE_META` + 사이드바 객체 탐색 섹션

## Running the Loader

배포된 환경에서 (one-shot ECS task):
```bash
aws ecs run-task \
  --cluster assembly-dev-cluster \
  --task-definition assembly-dev-api \
  --launch-type FARGATE \
  --overrides '{"containerOverrides":[{"name":"api","command":["python","-m","data.load","--neptune","--opensearch","--from-s3"]}]}'
```

로컬 dev (Neptune VPC 접근 불가 — DB 적재는 SKIP, 합성·외부 ETL만 S3로):
```bash
python -m data.load --to-s3-only
```

## 데이터 검증

- 적재 후 검증: `python -m data.verify` (각 클래스 노드 수 + 핵심 관계 카운트).
- 출처 배지 무결성: 모든 노드가 `source` 속성을 가져야 함 (`scripts/verify_source_tags.py`).
- 정치 성향 필드 미존재 확인: `scripts/verify_no_political_leaning.py` (CI에서 실행).

## Related ADRs

- ADR-0001 (gcc 패턴 차용 — Bulk Loader, source 태깅)
- ADR-0003 (Reader 익명화 - 솔티드 해시)
- ADR-0004 (정치 성향 필드 생성 금지)
