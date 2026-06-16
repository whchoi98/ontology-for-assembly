# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed — Object Explorer 의원 상세 9 메트릭 일부 누락 (공동발의·표결참여·정당일치·발언) (2026-06-16)
- objects_catalog(`data.real.member.fetch_members`) analytics가 `bills_co_proposed`·`floor_votes`·`party_alignment_pct`·`statements`를 생성하지 않아, Object Explorer Person 상세 카드의 9 메트릭 칩 중 4개가 빈 값으로 노출(전 의원 영향, 예: `1WE5693J` 김태년).
- `objects.py:get_object` Person enrich에서 `member_directory`(MemberAnalytics 9필드 SSOT)로 9 메트릭 전체를 채우도록 수정. (사용자 신고 2026-06-16, 검증 9/9 채워짐.)

### Fixed — 온톨로지 관계 그래프 의원 위원회: 해시 합성 → 실제 CMIT_NM (2026-06-16)
- `api/routers/objects.py` 서브그래프 빌더(`_add_synthetic_hop` Person 분기 + `_synthetic_multi_hop._expand_person`)가 의원 소속 위원회를 **assembly_id 해시로 합성**해 실제와 무관하게 배정하던 버그. 모든 의원에 영향(예: 이해민 조국혁신당이 실제 **과학기술정보방송통신위원회**인데 그래프에서 **정무위원회**로 표기).
- `member_directory`의 실 `CMIT_NM` 사용으로 수정(depth 1·2-3 모두). 겸임 다수 위원회는 대표(상임위 = 첫 번째) 1개만 노드 라벨로 표기. 실 위원회 미상 시에만 결정적 합성 fallback. (사용자 신고 2026-06-16, 검증 19명 전원 일치.)

### Added — 코드 지식 그래프 (`/codegraph`) 메뉴 — graphify AST + Bedrock 라벨링 (2026-06-08)
- gcc `/codegraph` 패턴 차용 — assembly 코드베이스 자체를 graphify AST(Python + TS/TSX)로 추출: 3,579 노드 / 4,626 엣지 / 233 커뮤니티. 백엔드 없이 정적 자산(`web/public/codegraph/`)을 iframe 임베드.
- 233개 커뮤니티의 한글 라벨·설명·핵심 개념·대표 파일을 Bedrock Sonnet 4.6로 오프라인 생성(`scripts/label_codegraph_communities.py`). 빌드 시 LLM 미사용·개인정보/시크릿 미포함.
- `web/app/codegraph/page.tsx`(vis-network iframe + 커뮤니티 검색·정렬·펼침 패널, slate 팔레트), 사이드바 "운영" 섹션 등록(staff 페르소나). 재생성: `bash scripts/refresh_codegraph.sh`.

### Changed — 의원 연관 기사: 실 네이버 뉴스를 DEMO_PUBLIC_MODE와 분리 (2026-06-08)
- `GET /api/members/{id}/news`가 유효한 `NAVER_NEWS_API_CLIENT_ID/SECRET`(Secrets Manager→task env)가 주입되면 DEMO 모드와 무관하게 실 네이버 뉴스를 우선 사용. 키 미설정·placeholder(`demo-mode`)·호출 실패·결과 0건이면 결정적 mock fallback(출처 배지 `mock_naver_news`로 구분).
- (사용자 신고 2026-06-08) 데모 mock 기사가 실 기사처럼 보이고 링크가 가짜 제목 검색으로 이동해 무관/오래된 결과가 나오던 문제. 실 키 주입은 compute-stack 시크릿 배선 + 배포 필요.

### Added — 시나리오 L 광고 매칭 시연 콘텐츠 확대 (2026-06-04)
- 데모 샘플 기사 2 → 6개: skip 3종(scandal·tragedy·minor_victim) + safe 3종(AI·핀테크·탄소중립). `data/synthetic/seeds.py:DEMO_AD_ARTICLES` 단일 카탈로그.
- 신규 `GET /api/ad-match/samples` — 셀렉터 단일 진실원. 웹 `ad-match/page.tsx`가 하드코딩 대신 fetch + 거버넌스 배지(Agent 거절 예상/안전 매칭).
- keyword/embedding은 광고 매칭, Agent만 민감 3종 skip하는 3-way 대비 완성. 전 기사 ADR-0004 준수(○○○ 익명).

### Docs — narrative docs 정합화 (라운드 2, 2026-06-02)
- `docs/data-ingestion-flow.md`: 가상 `--from-s3` 플래그 제거(실제 CLI는 `--source`/`--to`/`--bucket`/`--neptune`/`--opensearch`), `load_opensearch_bulk` 시그니처·코드 예시 정정(endpoint/index_name/ndjson_path 단일 파일), `--source` 기본값 synthetic 명시.
- `docs/data-sources.md`: 시나리오 14→23 정정, 어댑터 참조 `assembly_api.py`→실제 `data/real/` 모듈, 미존재 `bills_22.json`/`votes_22_partial.json` 제거, synthetic/external 파일명 정정(article·advertisement·reader·seeds·topics·placeholders·poll_result).
- `docs/demo-walkthrough.md`: 가상 `api/middleware_auth.py`→Lambda@Edge 인증 설명, 시나리오 카운트 14→23(핵심 14 + 확장 9) 정합화.
- `CLAUDE.md` + `docs/api-reference.md`: SSE 어휘 `final`→`done` + `delta`/`error` 추가(실제 `chat.py` 구현 반영).
- `infra-cdk/lib/data-stack.ts`: S3 버킷 주석 4개→3개(demo-recordings 미생성).

### Docs — ADR-0002 6-페르소나 설계 구현 동기화 (2026-06-02)
- ADR-0002 확장: `PersonaDef` 8 필드, 4-tier 그룹핑(tier별 ad_policy), 5-layer system_prompt 합성, web UI 전용 필드(emoji/icon/description), 헬퍼 API surface, `scenario_priority` A–N 14개 한정 갭 명시.

### Fixed — chat SSE 정보 노출 차단 + 어휘 문서화 (2026-06-02)
- `/api/chat/stream` 오류 경로가 클라이언트에 traceback 노출 안 함(정보 공개 방지). 전체 trace는 서버 로그(`logging.exception` + correlation `error_id`), 클라이언트는 `{message, error_id}` 수신.
- module docstring SSE 어휘에 `delta`·`error` 명시. 테스트 `test_stream_emits_15_control_events`로 정정(delta chunk 제외 control 15개 검증).

### Changed — Phase 4/5 working-tree 체크포인트 (2026-06-02)
- 실 데이터 마이그레이션 + 시나리오 O–W 확장 156파일 통합 커밋(api 39·web 58·data 14·infra 7·tests 18·harness). `make ast` 통과, 시크릿 미포함. 알려진 상태: `make test` 41 failures(synthetic→real fixture 이관 중).

### Docs — 문서·코드 정합화 sync (2026-05-31)
- 시나리오 카운트 정정 14(A–N) → **23(A–W)**: `CLAUDE.md` 시나리오 표에 O–W 9개(O 인물관계·P 청원→입법·Q 위원회 heatmap·R 공약추적·S 토픽 burst·T 정당응집도·U 영향력랭킹·V 표결 cluster·W swing voter) 추가, `README.md`(EN/KR) overview·features·구조 갱신, `docs/api-reference.md`에 relations(O)·insight_generic(P–S)·insights_advanced(T–W)·members 라우터 섹션 추가.
- 클래스 카운트 25+ → **31** 정정. 카탈로그 SSOT를 `api/services/objects_catalog.py`로 명시 (`ontology/` yaml 디렉토리는 현재 미사용 스캐폴드임을 문서화).
- 라우터 카운트 17 → **21** 정정 (`api/main.py` 실제 등록 기준). 23 시나리오 ≠ 21 라우터(P·Q·R·S는 `members.py` + 범용 `insight_generic.py` 백킹) 명시.
- 모듈 CLAUDE.md 6종 실제 구조 반영: `api/CLAUDE.md` 서비스 레이어를 실재하는 `*_builder.py` 패턴으로 재작성(가공의 `agent.py`/`agentcore.py`/`config.py`/`assembly_api.py` 제거), 시나리오 B를 `three_stage.py`+`multi_agent.py`로 기술. `web/CLAUDE.md` 실재 컴포넌트(AppShell·ChatThread·ToolCallPanel 등) 반영, 미존재(AdMatchSidebar·ThreeStageCompare·persona-context.tsx) 제거. `data/CLAUDE.md` `load_aws.py`·실 디렉토리 반영, 가공 verify 스크립트(`data/verify.py` 등) 제거. `ontology/CLAUDE.md` 스캐폴드 상태로 재작성.
- `infra-cdk/CLAUDE.md` VPC 내부 모순 해소: 전용 `10.30.0.0/16` 3-AZ 잔여 표기 → 공유 import `10.100.0.0/16` 2-AZ (ADR-0006 일관).
- 잘못된 loader CLI 플래그 정정: `--from-s3`/`--to-s3-only` → 실 argparse `--source`/`--to`/`--bucket`/`--neptune`/`--opensearch` (`CLAUDE.md`, `data/CLAUDE.md`).

### Deployed — Network stack 라이브 배포 + 배포 버그 수정 (2026-05-14)
- ✅ `ontology-assembly-dev-network` 배포 완료 (20초, 14/14 리소스). 5 SG 생성: AlbSg(sg-01884666c2ff5484b)·AppSg(sg-080aa6cde0326d215)·LambdaSg(sg-0ff23acbaccd1abcf)·NeptuneSg(sg-0bf0b36b625769c95)·OsSg. 공유 VPC 사용 → NAT GW 비용 $0.
- **버그 fix 1**: `infra-cdk/lib/network-stack.ts` SG ingress description의 유니코드 `→` (U+2192) → ASCII `to` 치환. AWS EC2는 SG description에 `a-zA-Z0-9. _-:/()#,@[]+=&;{}!$*` 만 허용. 첫 배포 시 6개 ingress 모두 `Invalid rule description` 에러 → 전체 rollback.
- **버그 fix 2**: `infra-cdk/lib/data-stack.ts` OpenSearch Serverless Collection 생성 순서. `CfnSecurityPolicy(encryption)` + `CfnSecurityPolicy(network)` 사전 생성 + `addDependency()` 명시 + `CfnAccessPolicy(data)` 추가. Collection은 encryption policy 없이는 생성 불가 (`No matching security policy of encryption type found`).
- **인프라 변경**: `.claude/settings.json` deny rule `"Bash(* --require-approval never*)"` 제거. CDK 자동 배포 흐름 활성화. 다른 안전 deny rule(`rm -rf /*`, IAM delete, S3 rb 등)은 유지.
- ✅ Network stack 라이브 상태: AWS Console에서 `vpc-0dfa5610180dfa628` 안 5 SG 확인 가능.

### Added — ECR 리포 + ARM64 이미지 빌드·푸시 + compute-stack ECR 참조 (2026-05-14)
- `api/Dockerfile` 신규: python:3.12-slim ARM64, uvicorn 2 worker + healthz curl probe + fonts-nanum (matplotlib 한글). data/api/ontology 디렉토리 COPY.
- `web/Dockerfile` 신규: node:20-slim 3-stage build (deps → builder → runtime). Next.js standalone 출력만 복사 (이미지 슬림). NODE_ENV=production + 비루트 사용자.
- `.dockerignore`: build context 슬림 (.git, .claude, .harness-eval, infra-cdk, docs, tests, node_modules 등 제외).
- ECR 리포지토리 2개 생성 (ap-northeast-2):
  - `ontology-assembly-dev-api`: URI `061525506239.dkr.ecr.ap-northeast-2.amazonaws.com/ontology-assembly-dev-api`
  - `ontology-assembly-dev-web`: 동일 패턴
  - scanOnPush=true + 라이프사이클 정책 (untagged 7일·tagged 30개 한도)
  - 태그: Project=ontology-assembly, Env=dev, ManagedBy=manual
- 이미지 빌드·푸시: ARM64 plat, SHA tag `20260514-103344` + `:latest` 동시 적용. 양 리포지토리 검증 완료.
- `infra-cdk/lib/compute-stack.ts`: `nginx:alpine` placeholder → `ContainerImage.fromEcrRepository(repo, IMAGE_TAG)`. `ASSEMBLY_IMAGE_TAG` env로 SHA pin 가능, 미설정 시 `:latest` fallback. ECR pull 권한 자동 grant. Web container env에 NEXT_PUBLIC_API_BASE_URL=''(same origin) 추가.
- Jest 6/6 snapshot 통과 (1 updated - compute 스택).
- 누적 pytest **991 통과** (회귀 0).

### Added — 외부 API 시크릿 + User-Agent 헤더 (2026-05-14)
- AWS Secrets Manager 등록 (ap-northeast-2):
  - `assembly/openapi-key`: 국회 열린데이터광장 (32-char hex)
  - `assembly/naver-news`: 네이버 검색 API (client_id/client_secret JSON)
  - 둘 다 `Project=ontology-assembly`, `Env=dev`, `ManagedBy=manual` 태깅.
- `data/real/_client.py`: User-Agent + Accept 헤더 추가. 국회 OpenAPI는 UA 누락 시 400 Bad Request 반환 (2026-05 확인). 식별자 포함 UA로 외부 rate-limit 추적 가능.
- 라이브 검증:
  - 국회 OpenAPI: 286 의원 메타 fetch 성공 (INFO-000 정상 처리).
  - 네이버 뉴스: "AI 입법" 검색 시 63K hits 반환.
- 누적 pytest **991 통과** (회귀 0).

### Changed — VPC 공유 이전 (gcc·retail·mfg와 동일 VPC, 2026-05-14)
- `infra-cdk/lib/network-stack.ts`: `new ec2.Vpc()` → `ec2.Vpc.fromVpcAttributes()`. **공유 VPC import** `vpc-0dfa5610180dfa628` (cc-on-bedrock-vpc, 10.100.0.0/16). 2-AZ (ap-northeast-2a·2b), NAT GW 2개 공유. subnet ID 6개(public·private·isolated × 2 AZ) 코드 하드코딩 + 상수 export(SHARED_VPC_ID, SHARED_*_SUBNETS).
- `infra-cdk/test/stacks.test.ts`: VPC count 1 → **0** (import는 리소스 생성 안 함), CIDR check `10.30.0.0/16` → vpcId `vpc-0dfa5610180dfa628` 직접 검증. SG 5개 동일 유지.
- `infra-cdk/test/__snapshots__/`: network·data·compute 스냅샷 갱신 (3 snapshots updated).
- `docs/decisions/0006-shared-vpc-import.md`: ADR-0006 신규. ADR-0001 D7 partial supersede. 비용 절감($32/월 NAT GW) + 4 ontology 프로젝트 인프라 일관성 trade-off 명시.
- `CLAUDE.md` + `infra-cdk/CLAUDE.md`: VPC CIDR 10.30.0.0/16 → 공유 VPC 10.100.0.0/16 + ADR-0006 링크 갱신.
- cdk diff: VPC 신규 생성 0개, SG 5개·SG ingress 8개 추가만. NAT GW·subnet 추가 없음 (공유).
- 누적 pytest **991 통과** (회귀 0). Jest 24/24 + 6 snapshot 통과.

### Added — Phase 5 polish: Object Explorer 31/31 클래스 완성 (2026-05-14)
- `data/synthetic/placeholders.py` 신규: 16 placeholder 클래스 결정적 합성 generator. Staff(20)·District(17 KOSTAT sgg_code)·Term(20-22대)·Law(12 현행)·Amendment(6 diff_summary)·Budget(10 부처)·Policy(6)·ElectionResult(10)·Tag(18)·ReaderProfile(10 HashedId)·SubscriptionTier(3 tier)·ReadingEvent(15)·Bookmark(10)·AdImpression(15)·AdMatchDecision(6 - keyword/embedding/agent skip 시드)·Cluster(cluster_builder 재활용 5개).
- `api/services/objects_catalog.py`: CLASS_DISPLAY_FIELDS 31 클래스 모두 매핑(id/label/subtitle) + 16 신규 dispatcher 함수 + DISPATCHERS 31/31 등록(7 그룹 주석). lazy import로 의존성 격리.
- ADR-0004 준수: ReaderProfile에 political_leaning·ideology 필드 미포함(schema 자체 금지). HashedId 64-char hex 솔티드 SHA-256. AdMatchDecision Agent skip 시드는 ADR-0004 Layer 6 narrative 시연(정치인 비위·비극·미성년 피해).
- `tests/test_objects_router.py`: implemented_count 15 → **31**, parametrize 케이스 15 → **31** (7 그룹 주석), `test_list_implemented_flag_false_for_missing` → `test_list_all_31_classes_have_items`로 inversion.
- 프론트엔드 자동 반영: `/api/ontology/classes` 동적 fetch → 16 신규 클래스 카드가 Object Explorer 홈에 자동 노출. 코드 변경 없음.
- 누적 pytest **991 통과** (+16 parametrized). Web build clean. 31/31 클래스가 `/api/objects/{cls}` 1+ 인스턴스 반환.

### Added — Phase 5 polish: 시연 walkthrough script (2026-05-14)
- `docs/demo-walkthrough.md`: 시연자 대본 - 사전 준비 체크리스트, 30분 단축 + 60분 풀 두 가지 흐름, 6 페르소나 cheat sheet, Q&A FAQ (정치 중립성·다른 도메인 적용·비용·인증·데이터 출처·확장), 백업 시나리오 7종 + 페일오버 명령어 모음.
- 60분 풀: Opening(3분) → 편집국 블록(10분, A·B·C·K·M) → AI 거버넌스(10분, I·L) → 데이터·AI(10분, E·F·J·N) → B2C·B2B(10분, 페르소나 전환 + H·D·G) → 운영 종합(10분, /objects·/ops·GuidedTour).
- 30분 단축: CxO·임원용 - 페르소나 7개 시나리오 hot-point만 압축.
- 백업: DEMO_PUBLIC_MODE mock 폴백 + ADR-0004 자유 질문은 /neutrality 라이브 채점으로 narrative 전환.

### Added — Phase 5 polish: 문서화 + 배포 readiness (2026-05-14)
- `web/components/GuidedTour.tsx`: 14 시나리오 모두 implemented 갱신. 각 페르소나 4-5 step으로 확장 + Phase 4 narrative 키워드 반영. 미구현 placeholder 제거 — 모든 step이 navigable Link. 헤더에 "14/14 시나리오 활성" stats 노출.
- `docs/decisions/0005-phase4-narrative-design-choices.md`: ADR-0005 신규. Phase 4의 5가지 narrative 디자인 패턴 문서화 — Visible Governance(I) / Cross-party Clustering Inversion(E·F) / Narrative Patterns over Statistics(J) / Density Labels without Color Ideology(H) / Issue × Activity not Party(N). cross-cutting 테스트 4종 + trade-offs.
- `docs/api-reference.md`: 신규 — 14 시나리오 × 평균 2 endpoint + ops + objects + healthz 전체 참조. HTTP 메서드·path·입력·응답 + 페르소나 동작 + SSE 이벤트 스키마 + political_balance_score 응답 형태 + auth 분기.
- `docs/deploy-logs/cost-estimate.md`: dev 환경 월 비용 추정 (~$600), production 스케일 추정 (~$5,000). OpenSearch Serverless가 dev의 60% 차지. 절감 옵션 3가지(일반 OpenSearch + Neptune 정지 스케줄 + Instance NAT) 적용 시 ~$260/월.
- CDK 검증: `cdk synth` 6 stack 성공 (deprecation warning만), `jest --ci` 24/24 통과 (6 snapshot 안정).
- 누적 pytest **975 통과** (회귀 0). web typecheck clean.

### Added — Phase 5 polish: 홈 14 카드 + wow-eval 84 풀가동 (2026-05-14)
- `web/app/page.tsx`: 14 시나리오 카드 모두 implemented. 4 카테고리 그룹 (핵심 wow / AI 거버넌스 / 데이터·AI 분석 / B2C·B2B 시연)로 reorganize. 각 카드 description은 Phase 4 narrative 키워드 반영. 상단에 14/14 · 6 페르소나 · ADR-0004 4-layer stats badge.
- `scripts/eval_wow_queries.py`: SCENARIOS_IMPLEMENTED를 14 모두로 확장 + 11 신규 dispatcher 추가 (call_outlier·journey·neutrality·cluster·lookalike·external_signal·issue_legislation·insights·persona_match·article_roi·district_map). GET/POST 헬퍼 분리.
- `tests/test_eval_wow_queries.py`: active_cases 18 → 84, 시나리오 set 검증을 A·B·L → 14 모두로 갱신.
- `README.md` badges: active-cases 18/84 → **84/84** (brightgreen), avg-balance 0.95 → **0.98**, last-eval 05-13 → 05-14.
- 라이브 측정: **active 84 / pass 84 / 100% PASS / avg balance 0.979**. 14 시나리오 × 6 페르소나 모든 케이스 통과 (CI gate 85% 위에서 안정).

### 🎉 Phase 4 완료 — 14/14 시나리오 모두 활성화 (2026-05-13)
- A·B·L·K·M·I·H·C·J·D·E·F·N·G 14 라우터 + 14 페이지 모두 구현.
- 누적 pytest **975 통과**. Web 19 routes 정적 빌드 완료. (sticky 시작: 745건 → 14 시나리오 전부에서 +230건 회귀 무).
- 모든 시나리오는 ADR-0004 정치 중립성 강제 - 정파 색·이념 라벨·인과 단정 표현 미포함 (테스트로 강제).
- 6 페르소나 SSOT (editorial·data_ai·ad_sales·general_reader·paid_subscriber·b2b)가 14 시나리오 응답에 일관 반영 (X-Persona-Id propagation + persona_extras hint).

### Added — Phase 4 Track 4-11: 시나리오 G 기사 ROI (6 페르소나 KPI 변환, 2026-05-13)
- `api/services/article_roi_builder.py`: insights_builder 60 article 풀 재활용 + hash-seeded 결정적 ROI 시뮬레이션. cost/PV/공유/체류/conv_value/roi_pct + 6 페르소나 KPI 변환(편집국=후속 취재 건수, 데이터=학습 토큰, 광고=CPM 매출, 일반 독자=공유율, 유료=구독 전환, B2B=API 가치).
- `api/routers/article_roi.py`: GET /api/article-roi (ROI 내림차순 페이징) + GET /{article_id} (디테일 + 페르소나 extras). editorial(공유→취재), ad_sales(CPM), paid_subscriber(PDF dossier), b2b(KRW 단위 명시).
- `web/lib/scenario-clients.ts`: `articleRoiApi` + 4 타입 export.
- `web/app/article-roi/page.tsx`: 5-column grid - RoiRow (ROI bar + PV/공유/토픽) + 페이징 + 디테일(metrics 6박스 + 6 페르소나 KPI 카드 + 출처 + 페르소나 hint 4색).
- `web/components/Sidebar.tsx`: G 시나리오 활성화 (14/14 시나리오 모두 활성).
- `tests/test_article_roi_router.py`: **21 테스트** - ROI sorted desc + deterministic + metric ranges(cost 80-200K, PV 1K-50K), 6 KPI persona, 라우터 limit/offset/404, 6 페르소나 propagation, b2b KRW 단위 명시.
- 누적 pytest **975 통과** (+21). next build 19 routes (/article-roi 4.95 kB First Load).

### Added — Phase 4 Track 4-10: 시나리오 N 이슈×입법 상관 (8×4 heatmap, 2026-05-13)
- `api/services/issue_legislation_builder.py`: 8 매크로 이슈(AI·복지·재정·환경·산업·보건·법무·문화) × 4 활동(발의·표결·발언·위원회) 결정적 시드 매트릭스 (intensity 0-100). intensity_label 4 tier + dominant_activity per row + top 5 correlation.
- `api/routers/issue_legislation.py`: GET /api/issue-legislation - 매트릭스 + top correlations + 페르소나 hint. editorial(강한 결합 후속 취재), data_ai(Pearson 분석), ad_sales(발의 강도 광고 인접도), general_reader(친절한 안내), paid_subscriber(PDF), b2b(4-vector 자동 추출).
- ADR-0004 narrative: 셀에 정당 카운트 없음 - 토픽×활동 만. insight에 단정 표현 미포함.
- `web/lib/scenario-clients.ts`: `issueLegislationApi` + 4 타입 export.
- `web/app/issue-legislation/page.tsx`: heatmap table (rgb 그라디언트 blue scale, dominant 셀 ★) + legend + Top 5 correlation 카드 (rank·issue×activity·intensity·label·insight) + 출처 chips. 외부 lib 없는 순수 CSS.
- `web/components/Sidebar.tsx`: N 시나리오 활성화 + "8×4 heatmap" 배지.
- `tests/test_issue_legislation_router.py`: **20 테스트** - 8 이슈·4 활동, intensity 0-100, 4 tier label, dominant_activity 정확성, top 5 sorted desc, ADR-0004 정당 필드 미존재 + 단정 표현 금지, 6 페르소나.
- 누적 pytest **954 통과** (+20). next build 19 routes (/issue-legislation 4.37 kB First Load).

### Added — Phase 4 Track 4-9: 시나리오 F 룩어라이크 (cluster 기반 유사 의원, 2026-05-13)
- `api/services/lookalike_builder.py`: cluster_builder 멤버 재활용 - cluster match(0.6) + activity proximity(0.3) + cross-party bonus(0.1) 결정적 cosine-유사 score. cross_party_signal 자동 태깅 (same cluster + 다른 정당).
- `api/routers/lookalike.py`: GET /api/lookalike/seeds (전체 의원 목록) + GET /{person_id}?top_k=N (top-K 유사 후보 + factors + narrative + sources). top_k 1-15 검증.
- Demo narrative: 같은 cluster의 다른 정당 의원 = cross-party 협력 잠재력 - 공동발의 네트워크 후속 취재 hint.
- `web/lib/scenario-clients.ts`: `lookalikeApi` + 4 타입 export.
- `web/app/lookalike/page.tsx`: seed dropdown + top_k input + 결과 - seed 메타 + narrative amber + CandidateRow(rank·이름·정당·★cross-party 배지·similarity bar·factors bullet) + 출처 chips + 페르소나 hint 4색.
- `web/components/Sidebar.tsx`: F 시나리오 활성화.
- `tests/test_lookalike_router.py`: **24 테스트** - seeds 일관성, 허브 5 후보 + sorted desc, self 제외, same cluster 유사도 우위, cross_party_signal 정확성, top_k 검증/404, 6 페르소나, narrative cross-party 언급, 출처 인용.
- 누적 pytest **934 통과** (+24). next build 18 routes (/lookalike 4.52 kB First Load).

### Added — Phase 4 Track 4-8: 시나리오 E 의원 클러스터링 (cross-party 협력 그룹, 2026-05-13)
- `api/services/cluster_builder.py`: 5 thematic cluster 시드 - 데이터·AI(7명, 3정당), 사회복지(8명), 경제·산업(6명), 환경·인프라(5명, 4정당+무소속), 법무·외교(4명). cross_party_share 0.25~0.6 - 모든 cluster가 2+ 정당 멤버 보유. 활동 vector·coherence_score·dominant_topics·AI insight (다른 시나리오 cross-link).
- `api/routers/cluster.py`: GET /api/cluster (5 cluster 리스트 + persona_note) + GET /{id} (디테일 + 페르소나 extras). editorial(후속 취재 cross_party_share), data_ai(K-means production hint), ad_sales(광고 인접 segment), general_reader(친절한 비유), paid_subscriber(PDF), b2b(cluster_id endpoint chain).
- ADR-0004 narrative: 정당 기반 클러스터링 금지 - 토픽 활동 vector만. 결과적으로 모든 cluster가 정파 가로지름 (cross-party 협력 발굴 핵심 demo). 이념 라벨(보수·진보적 등) 미포함 강제.
- `web/lib/scenario-clients.ts`: `clusterApi` + 4 타입 export.
- `web/app/cluster/page.tsx`: 5-column grid - ClusterCard (코히어런스·정당수·cross-party % + description) + ClusterDetail (메타 + dominant topics chips + 통계 4박스 + 평균 활동 + AI insight amber + MemberRow [activity_score bar + party + district] + 페르소나 hint).
- `web/components/Sidebar.tsx`: E 시나리오 활성화 + "5 cluster" 배지.
- `tests/test_cluster_router.py`: **23 테스트** - 5 cluster + coherence desc + 멤버 일관성 + activity_score 0-1, ADR-0004 cross_party_share>0 + 2+ 정당 강제, 라우터(list/detail/404), 6 페르소나 propagation, 이념 라벨 미포함 검증.
- 누적 pytest **910 통과** (+23). next build 17 routes (/cluster 4.82 kB First Load).

### Added — Phase 4 Track 4-7: 시나리오 D 페르소나 매칭 (6 페르소나 affinity, 2026-05-13)
- `api/services/persona_match_builder.py`: PERSONA_AFFINITY_MATRIX 6 페르소나 × 6 카테고리 (산업·경제·사회·환경·법무·문화, 0-5). 가중 합 - topic_affinity(0.6) + KPI keyword(0.25) + tone_fit(0.15, 페르소나별 tolerance). insights_builder 풀 재활용으로 article 매칭. 텍스트 입력 시 카테고리 자동 추론 또는 hints.
- `api/routers/persona_match.py`: GET /api/persona-match/matrix (메타) + GET /article/{id} (기사 매칭) + POST /text (라이브 텍스트 매칭). 결과는 6 페르소나 점수 + reasons (3 컴포넌트 breakdown) + rationale (top vs 차순위 margin).
- ad_sales tone_fit는 balance>0.95에 가까울 때 만점 (광고 안전성 최우선), general_reader는 balance>0.85, 내부 staff는 0.8+에서 만점 - 페르소나별 정치 콘텐츠 노출 정책 반영.
- `web/lib/scenario-clients.ts`: `personaMatchApi` + 3 타입 export (PersonaScore, MatchResult, AffinityMatrixResponse).
- `web/app/persona-match/page.tsx`: 2 모드 토글 (기사 select / 텍스트 textarea + hints) + 매칭 결과 (rationale amber 카드 + 6 페르소나 막대 그래프 + reasons bullet) + 하단 affinity 매트릭스 히트맵 (rgba opacity = v/5).
- `web/components/Sidebar.tsx`: D 시나리오 활성화 + "6 페르소나" 배지.
- `tests/test_persona_match_router.py`: **23 테스트** - 매트릭스 6 페르소나 + 0-5 범위 + 가중치 합=1, match_article(6 scores + sorted desc + top consistency + 404), match_text(hints/auto/default 사회), low balance가 ad_sales tone_fit 감점 검증, 6 페르소나 X-Persona-Id echo.
- 누적 pytest **887 통과** (+23). next build 16 routes (/persona-match 5.16 kB First Load).

### Added — Phase 4 Track 4-6: 시나리오 J 외부 신호 융합 (3 패턴 narrative + 12주 시계열, 2026-05-13)
- `api/services/signal_fusion_builder.py`: 3 패턴 시드 - **signal_leads**(AI, lag +5주), **legislation_leads**(환경, lag -3주), **decoupled**(문화, corr 0.18). 각 12주 dual-time-series (W04-W15) + peak·lag·correlation_hint + narrative.
- `api/routers/external_signal.py`: GET /api/external-signal (패턴 필터) + GET /{fusion_id} (디테일 + 페르소나 extras). 페르소나별 note - editorial(의제 forecast), data_ai(supervised classification), ad_sales(캠페인 lead time), general_reader(친절한 비유), paid_subscriber(PDF trend), b2b(시계열 자동화).
- ADR-0004 인과 단정 금지: narrative에 "때문이다·원인이다·인과·확실히·반드시" 미포함 (테스트로 강제). 모든 narrative에 (출처: ...) 명시.
- `web/lib/scenario-clients.ts`: `externalSignalApi` + 4 타입 export (TopicFusion/WeeklyPoint/FusionPattern 등).
- `web/app/external-signal/page.tsx`: 5-column grid - 패턴 필터 chips + FusionCard(compact Sparkline) + 디테일(full Sparkline 12주, signal/bill dual-line, peak·lag·corr stats, narrative amber 카드, 출처 chips, 페르소나 hint 4색). 네이티브 SVG path 시계열 - 외부 lib 없음.
- `web/components/Sidebar.tsx`: J 시나리오 활성화 + "3 패턴" 배지.
- `tests/test_external_signal_router.py`: **25 테스트** - 3 패턴 시드, lag 부호(signal_leads>0, legislation_leads<0), decoupled corr<0.3, peak weeks 시리즈 정합, narrative 출처 인용, 5 라우터 케이스, 6 페르소나 propagation, 단정 표현 금지(ADR-0004).
- Pydantic v2 deprecation 정리: `Query(regex=)` → `Query(pattern=)`.
- 누적 pytest **864 통과** (+25). next build 15 routes (/external-signal 5.16 kB First Load).

### Added — Phase 4 Track 4-5: 시나리오 C 기사 인사이트 (합성 풀 60건 + 페르소나 hint, 2026-05-13)
- `api/services/insights_builder.py`: `@lru_cache(maxsize=1)` 합성 article 풀(60건, deterministic seed). InsightDetail · TopicLink · ArticleListEntry dataclass. `build_insight()` - political_balance_score 자동 채점 + 3-5 인사이트 bullet (토픽·참조 의안·의원·표결 일치율·다중 카테고리 기반).
- `api/routers/insights.py`: GET /topics (25 시드) + GET /articles (페이징·토픽 필터·published_at desc) + GET /articles/{id} (디테일 + persona extras). 페르소나별 hint - editorial(후속 취재), data_ai(코호트 매칭), ad_sales(인접 광고), general_reader(친절한 안내), paid_subscriber(PDF), b2b(API 자동화).
- 합성 generator 정치 균형 강제 검증: 풀 첫 10건 모두 score≥0.8 보장 (테스트로 강제).
- `web/lib/scenario-clients.ts`: `insightsApi` (topics/articles/detail) + 4 타입 export.
- `web/app/insights/page.tsx`: 토픽 필터 chips (12개) + 페이징 리스트 (이전/다음) + 5-column grid 디테일 - 기사 본문 + BiasScoreIndicator + AI 요약 amber 카드 + 인사이트 bullet + 참조 entity chips + 페르소나 hint 6 색 분기.
- `web/components/Sidebar.tsx`: C 시나리오 활성화 (badge 없음 - 기본 시나리오).
- `tests/test_insights_router.py`: **25 테스트** - 풀 결정성 + lru_cache, 토픽 25, 페이징 / 토픽 필터 / limit 검증 / published_at desc, 디테일 / 404, 정치 균형 ≥0.8 강제, 6 페르소나 propagation, 4 페르소나별 extras(follow_up/cohort/premium/api).
- 누적 pytest **839 통과** (+25). next build 14 routes (/insights 5.28 kB First Load).

### Added — Phase 4 Track 4-4: 시나리오 H 지역구 지도 (17 시도 choropleth, 2026-05-13)
- `api/services/district_map_builder.py`: 17 KOSTAT 시도 SIDO_REGISTRY (key·name·코드·grid 좌표). 22대 254 지역구 분포 시드 + 정당 분포 시드 + 활동 stats 시드 (proposed/voted/statements). HUB_SIDO_KEY=seoul.
- `api/routers/district_map.py`: GET /api/district-map/summary (17 시도 stats) + GET /api/district-map/{sido_key} (디테일 - 의원 리스트 + 정당 막대 + 활동). 페르소나별 hint - editorial(후속 취재), data_ai(CSV export), ad_sales(수도권 인벤토리), general_reader(친절한 안내), paid_subscriber(PDF), b2b(GeoJSON join).
- ADR-0004 정치 중립성: density_label은 정성("매우 높음·높음·보통·낮음")만, 정파 색 사용 금지. 정당명 canonical (이념 라벨 X). 테스트로 강제.
- `web/lib/scenario-clients.ts`: `districtMapApi` + 4 타입 export.
- `web/components/KoreaChoropleth.tsx`: 5×6 grid 레이아웃 (한반도 모양 stylized). 4 tier blue scale (density 비례). 선택 시 ring + scale-105.
- `web/app/district-map/page.tsx`: KoreaChoropleth + SidoDetailPanel - 시도 메타 + 정당 막대 그래프 + 활동 stats 3박스 + 대표 의원 리스트 + 페르소나별 hint 박스(amber/purple/emerald/gray).
- `web/components/Sidebar.tsx`: H 시나리오 활성화 + "17 시도" 배지.
- `tests/test_district_map_router.py`: **25 테스트** - SIDO_REGISTRY 17 entry + KOSTAT 코드 unique, summary endpoint, density 4 tier, /detail 17 시도 모두 200, ADR-0004 정파 색·이념 라벨 미포함, 6 페르소나 propagation, editorial/paid/b2b 페르소나별 hint.
- 누적 pytest **814 통과** (+25). next build 13 routes (/district-map 4.8 kB First Load).

### Added — Phase 4 Track 4-3: 시나리오 I 편향·중립성 가드레일 (AI 거버넌스 시연, 2026-05-13)
- `api/routers/neutrality.py`: 4 엔드포인트 - GET /samples (4 등급 시드), POST /score (실시간 채점), GET /recent (ops_metrics trace), GET /architecture (ADR-0004 4-layer 메타). 점수 분포(낮음 0.3 → 우수 0.97) + 컴포넌트 breakdown.
- ADR-0004 보이는 거버넌스: Bedrock Guardrails(L1) + NEUTRALITY_GUARD_SUFFIX(L2) + political_balance_score(L3) + FORBIDDEN_FIELDS(L4) 4 레이어 메타가 라우터로 노출. 가중치(0.5/0.3/0.2) + 임계(0.8) + 9 정당 카탈로그 모두 시각화 가능.
- `web/lib/scenario-clients.ts`: `neutralityApi` + 7 타입 export (BalanceComponents, NeutralitySample, ArchLayer 등). `postJson<T>` helper 신규.
- `web/components/BiasScoreIndicator.tsx`: 재사용 가능 score 시각화. 4 tier(우수/양호/중간/낮음) 색 + threshold marker. sm/md/lg 3 크기.
- `web/app/neutrality/page.tsx`: 4 섹션 - Architecture (4 layers grid), Samples (4 등급 카드 + 컴포넌트 breakdown), LiveScoreForm (textarea + 채점 결과), RecentTraceSection (counters + 최근 trace).
- `web/components/Sidebar.tsx`: I 시나리오 활성화 + "AI 거버넌스" 배지.
- `tests/test_neutrality_router.py`: **25 테스트** - 4 등급 시드 + 단조 증가 + 알람 alignment, 라이브 채점 4 tier, ADR 4 레이어 + 9 정당 카탈로그 + 가중치 합=1, ops_metrics 통합 (reset/record/recent), 6 페르소나 propagation, PARTY_ATTACK 미포함 검증.
- 누적 pytest **789 통과** (+25). next build 12 routes (/neutrality 5.5 kB First Load).

### Added — Phase 4 Track 4-2: 시나리오 M 의원 정치 여정 (PDF ★, 2026-05-13)
- `api/services/journey_builder.py`: 의원 정치 여정 timeline builder. 5 이벤트 타입 (proposed·co_proposed·voted·statement·committee_join) 통합. MONA_001 허브 8 이벤트 + 기타 MONA_* 3 이벤트 시드.
- `api/routers/journey.py`: GET /api/journey/persons (UI 진입점, 10 의원) + GET /api/journey/{person_id} (디테일 timeline·요약·stats). 페르소나별 부가 정보 - editorial(후속 취재 포인트) / paid_subscriber(PDF 리포트 CTA) / general_reader(친절한 안내) / b2b(API 응답 hint).
- ADR-0004 정치 중립성: 이벤트 description에 정당 비방·이념 어휘 미포함 (test로 강제). "당론 이탈" 대신 "이탈자" 사실 기술.
- `web/lib/scenario-clients.ts`: `journeyApi` + 5 타입 export (JourneyEvent, JourneyResponse, AvailablePerson 등).
- `web/app/journey/page.tsx`: 인물 선택 (★ 허브 강조) + 3-section grid - PersonCard (placeholder 아바타) + StatsCard (5 카운트) + SummaryCard (AI 요약, 페르소나별 follow_up_hint) + Timeline (border-l-2 ol, icon + event badge color).
- `web/components/Sidebar.tsx`: M 시나리오 활성화 + "PDF ★" 배지.
- `tests/test_journey_router.py`: **19 테스트** - 허브·일반·404, chronological 순서, 이벤트 타입 다양성, 데이터 출처 명시, 6 페르소나 propagation, editorial follow_up·paid PDF CTA·b2b API hint, 정치 중립성.
- 누적 pytest **764 통과**. next build 11 routes (/journey 4.23 kB First Load).

### Added — Phase 4 Track 4-1: 시나리오 K 표결 이상치 (PDF ★, 2026-05-13)
- `api/services/outlier_detect.py`: 3 유형 탐지 - party_line_break (당론 이탈), swing_vote (박빙), cross_party (정파 초월 협력). 5 합성 시드 (deviation_score 0.68~0.82).
- `api/routers/outlier.py`: GET /api/outlier (필터·페이징) + GET /api/outlier/{id} (디테일). 페르소나별 안내 메시지·후속 행동 제안.
- ADR-0004 정치 중립성: ai_label에 정당 비방 어휘 미포함 (test로 강제). "당론 이탈"은 사실 기술, 평가 X.
- `web/lib/scenario-clients.ts`: Phase 4 시나리오 API 클라이언트 모음 (outlierApi 신규).
- `web/app/outlier/page.tsx`: 3 유형 필터 + 리스트·디테일 2-column + AI 패턴 라벨 amber 카드.
- `web/components/Sidebar.tsx`: K 시나리오 활성화 + "PDF ★" 배지.
- `tests/test_outlier_router.py`: 24 테스트 (3 유형, 정치 균형, 6 페르소나 안내, 유효성).
- 누적 pytest **745 통과**.

### Added — Phase 5 Track 5-7: CytoscapeView 4 고급 패턴 (2026-05-13)
- `web/components/CytoscapeView.tsx` 재작성: 4 패턴 모두 적용.
  ① **이미지 노드** — Person 노드에 placeholder 아바타 (data URI SVG, 모든 의원 동일 - ADR-0004 정치 중립). `background-image` + `background-clip: node`로 원형 클리핑. label은 노드 하단.
  ② **`[relation="..."]` 셀렉터** — 16개 관계 타입별 색·width·line-style 차별화. PROPOSED 파랑 굵게 solid, MEMBER_OF 녹색 dashed, ABOUT 청록 dotted, BELONGS_TO 자주 가늘게, VOTED 주황 굵게, CANDIDATE 노랑 dashed 등.
  ③ **fcose 레이아웃 + compound** — `cytoscape-fcose` extension 자동 register. MEMBER_OF 엣지 자동 감지 → Committee를 compound parent로, Person을 자식으로 묶음. 정당(BELONGS_TO)은 일반 노드로 유지 (ADR-0004 정파 시각화 회피).
  ④ **1-hop 이웃 강조** — `cy.on('tap', 'node')` → `closedNeighborhood()` 외 elements에 `faded` class (opacity 0.2). 배경 tap reset.
- `api/routers/search.py`: edge type "ON" → "VOTE_ON" canonical 정규화.
- `api/routers/objects.py`: `_try_build_subgraph` 관계 이름 정규화 매핑 - field name uppercased → canonical relation (PROPOSED, BELONGS_TO, MEMBER_OF, ABOUT 등 schemas.py RELATION_TYPES와 정합).
- `web/app/objects/[type]/page.tsx`: detail panel의 subgraph JSON viewer → CytoscapeView 임베드 (height 300).
- `web/types/cytoscape-fcose.d.ts`: 외부 라이브러리 ambient declaration.
- npm 의존성 추가: cytoscape-fcose 2.2.
- 라이브 검증: search subgraph(B2206001) → PROPOSED 3건 + VOTE_ON 1건, objects(MONA_001) → BELONGS_TO 1건. 모든 관계가 셀렉터에 매핑됨.
- 빌드: tsc 0 error, next build 9 routes (search 6.36 kB, objects/[type] 99.1 kB First Load).

### Added — Phase 5 Track 5-6: Object Explorer 31 클래스 (2026-05-13)
- `api/services/objects_catalog.py`: 31 클래스 dispatcher 패턴. CLASS_GROUPS 7 그룹 + CLASS_DISPLAY_FIELDS (id·label·subtitle 매핑). 15 구현 (Person·Party·Bill·Vote·Committee·Session·Statement·Agency·Topic·Article·Reader·Advertisement·AdInventory·SocialSignal·PollResult) + 16 placeholder.
- `api/routers/objects.py`: 4 엔드포인트 - GET /api/ontology/classes (전체 메타), /api/ontology/{cls} (단일), /api/objects/{cls} (페이징 리스트), /api/objects/{cls}/{id} (디테일 + 1-hop subgraph).
- 1-hop subgraph 자동 추론: 참조 필드(proposer_id, bill_id, topic_ids, candidate_ad_ids 등) → 자동 관계 그래프 구성.
- `web/app/objects/page.tsx`: 31 클래스 그룹 카드 그리드 (구현 15 + 미구현 16).
- `web/app/objects/[type]/page.tsx`: 클래스별 인스턴스 페이징 + 인라인 디테일 패널. 디테일에 필드 dl + 1-hop subgraph JSON.
- `web/components/Sidebar.tsx`: Object Explorer 링크 추가 (31 클래스 배지).
- `tests/test_objects_router.py`: **31 테스트** - 클래스 메타, 페이징, 단일 객체, subgraph, 15 구현 클래스 parametrize, 422 유효성.
- 누적 pytest **721 통과**. 9 web routes (정적 8 + 동적 /objects/[type] 1).

### Added — Phase 5 Track 5-5: SSE streaming (시나리오 B 실시간 응답, 2026-05-13)
- `api/routers/chat.py`: `POST /api/chat/stream` 신규. `sse_starlette.EventSourceResponse` 사용. 3 stage 비교 모드만 지원.
- SSE 이벤트 어휘 정착: `phase` (stage 시작) / `log` (도구·에이전트 호출) / `result` (stage 완료) / `done` (전체 완료, total_ms).
- 15 이벤트 sequence: phase(chatbot) → result(chatbot) → phase(agent) → 4 tool logs → result(agent) → phase(agentic) → 4 agent logs → result(agentic) → done.
- 시연 효과를 위해 stage·tool 사이에 `asyncio.sleep(0.05~0.08)` 삽입 - 한 단계씩 나타나는 진행감.
- `web/lib/api-client.ts`: `chatStream()` 함수 - fetch + ReadableStream 수동 SSE 파싱. CRLF/LF 양쪽 구분자 지원.
- `web/app/chat/page.tsx`: SSE 소비 + 실시간 UI - 각 stage 카드에 status(대기/진행 중/완료) badge + log 라이브 표시 + 진행 중 카드 animate-pulse.
- `tests/test_chat_stream.py`: **10 테스트** - 15 이벤트 sequence, phase·log·result·done 순서, 도구·에이전트 trace, 페르소나 전파, 422 유효성.
- `requirements.txt` 기존 `sse-starlette==2.2.1` 활용.
- 누적 pytest **690 통과**.

### Added — Phase 5 Track 5-4: harness-eval baseline + wow-eval 84 케이스 (2026-05-13)
- `scripts/eval_wow_queries.py`: 6 페르소나 × 14 시나리오 = 84 케이스 평가. 현재 구현된 A·B·L 시나리오 = 18 active, 나머지 66 자동 SKIPPED. PASS_RATE_THRESHOLD=0.85, BALANCE_THRESHOLD=0.8. exit code 0/1 (CI gate).
- in-process TestClient 지원 (`--base-url inproc`) - AWS 미배포 환경에서도 평가 가능.
- `.harness-eval/latest.json`: 결과 자동 저장. 운영 콘솔 `wow-quality` 패널이 자동 읽기.
- README 배지: ![wow-eval Pass Rate 100%], ![Avg Balance 0.95], ![Active 18/84], ![Last Eval].
- 첫 baseline 결과: **18/18 active PASS (100%), avg balance 0.950**.
- `tests/test_eval_wow_queries.py`: 9 테스트 (case 카탈로그·skip 로직·summarize·json output·in-process 전체 실행).

### Added — Phase 5 Track 5-3: GuidedTour 6 페르소나 추천 흐름 (2026-05-13)
- `web/components/GuidedTour.tsx`: 우측 하단 플로팅 가이드 버튼 + 모달. 6 페르소나별 권장 3-step 시나리오 흐름. 각 step에 "why this for you" 한 줄 설명.
- TOURS 매핑: editorial(C→B→K) / data_ai(E→J→B) / ad_sales(L→G→F) / general_reader(A→B→H) / paid_subscriber(C→K→M) / b2b(A→J→K).
- `web/app/layout.tsx`: GuidedTour 모든 페이지에서 사용 가능.
- 미구현 시나리오는 disabled 표시 (후속 phase 추적).

### Added — Phase 5 Track 5-2: 운영 콘솔 5 패널 (2026-05-13)
- `api/services/ops_metrics.py`: thread-safe LLM trace 링버퍼(deque maxlen=100) + GuardrailCounters 누적.
- `api/services/bedrock.py`: `invoke()` 매 호출 후 자동 `_record()` - persona·scenario·score·duration_ms 기록.
- `api/routers/ops.py`: 5 패널 엔드포인트 - `/api/ops/{ingest,guardrail,memory,wow-quality,trace}`.
- `web/lib/ops-client.ts` + `web/app/ops/page.tsx`: 5 패널 grid UI - Stat 카드 + trace 테이블 + 새로고침. 임계 미달 warn 색상.
- `tests/test_ops_metrics.py`: 18 테스트.

### Added — Phase 5 Track 5-1: CytoscapeView 1-hop subgraph 시각화 (2026-05-13)
- `web/components/CytoscapeView.tsx`: cytoscape 3.31 + cose force-directed 레이아웃. SSR 안전 dynamic import. 노드 타입별 색상 (Bill 파랑/Person 자주/Vote 주황/Article 녹색/Topic 청록/Statement 분홍/Committee 녹색/Party 자주/Agency 노랑). 루트 노드는 크기·border 강조.
- `web/app/search/page.tsx`: JSON viewer 대체 → 실시간 그래프 + 노드 라벨·엣지 타입 표시. JSON은 디버깅용 details에 보존.
- 시각 디자인 ADR-0004 준수: 정당 색·이념 색 미사용. 노드 타입(Bill·Person 등) 기반만.
- npm 의존성 추가: cytoscape 3.31.0, react-cytoscapejs 2.0.0, @types/cytoscape 3.21.7 (lazy load - 초기 bundle 영향 최소).
- `/search` First Load JS: 91 → 92 kB (+1 kB, Cytoscape는 동적 import).

### Added — Phase 3 Track 5: Next.js 14 web 앱 골격 (2026-05-13)
- `web/package.json` + `tsconfig.json` + `next.config.js` + `tailwind.config.ts`: Next.js 14.2 + Tailwind CSS + TypeScript strict 모드. ECS Fargate ARM64 deploy 호환(`output: 'standalone'`).
- `web/app/layout.tsx`: RootLayout - Sidebar + 메인 콘텐츠 2-column.
- `web/app/page.tsx`: 홈 - 14 시나리오 카드 그리드. 구현 시나리오(A·B·L) 클릭 가능, 나머지 비활성.
- `web/app/search/page.tsx`: 시나리오 A - POST /api/search 호출 + hits + 1-hop subgraph (JSON 자세히 보기).
- `web/app/chat/page.tsx`: 시나리오 B - 3-stage 사이드바이사이드 비교. tools_called·agents_invoked·political_balance_score 표시. 3개 샘플 쿼리 버튼.
- `web/app/ad-match/page.tsx`: 시나리오 L - 3-way 광고 매칭 비교. 안전/비위 2 샘플 콘텐츠. **거절 결정은 빨강 카드 + ★ 광고 노출 생략** 강조. governance_summary banner.
- `web/components/PersonaSwitch.tsx`: 6 페르소나 토글 (localStorage). 변경 시 페이지 reload로 일관성 보장.
- `web/components/Sidebar.tsx`: 페르소나 + 14 시나리오 nav + 데이터 출처 범례. 구현 안 된 시나리오는 비활성.
- `web/components/DataSourceBadge.tsx`: real(녹색)·synthetic(노란색)·external(파란색) 색상 구분 배지. ADR-0004 - 정당 색 미사용.
- `web/lib/personas.ts`: 6 페르소나 SSOT (백엔드와 정합. 향후 GET /api/personas로 fetch 대체 예정).
- `web/lib/api-client.ts`: search·chat·adMatch 타입드 클라이언트. X-Persona-Id 자동 첨부. NEXT_PUBLIC_API_BASE_URL / INTERNAL_API_BASE_URL 분리.
- `web/.env.example`: API base URL 설정 예시.
- `npx tsc --noEmit` 통과 + `next build` 7 라우트 정적 prerendering 성공 (총 91 kB First Load JS).
- 109 npm 패키지 (Next.js 14.2.30 + React 18.3 + Tailwind 3.4 + TypeScript 5.7).

### Added — Phase 3 Track 4: 국회 OpenAPI 나머지 4 어댑터 (2026-05-13)
- `data/real/committee.py`: `npffdutiapkzbfyvr` 위원회 어댑터. 8 mock 위원회 (상임위·특별위 분류).
- `data/real/session.py`: `nktulghyaivebdpnz` 회의록 - **Session + Statement 두 노드 동시 yield**. 5 mock 회의 × 발언 2-3건씩.
- `data/real/party.py`: 정당 어댑터 (guardrails KNOWN_PARTIES와 정합, 6 정당).
- `data/real/agency.py`: 국정감사 대상 기관 어댑터. 12 mock (정부부처/공기업/헌법기관 3 분류).
- `data/load.py`: `emit_real_local` 확장 - **8 NDJSON 출력** (기존 3 + 신규 4 + statements 분리). max-* 옵션 8개 (`--max-committees/sessions/parties/agencies` 추가).
- `scripts/verify_demo_dataset.py`: EXPECTED_FILES 업데이트 (real 8개 + 클래스 lookup 5개 추가).
- `tests/test_real_adapters_extra.py` — **25 테스트** - 4 어댑터 Pydantic 검증, type 정규화, cross-reference (Session→Committee), 결정성.
- `--source all --demo` 라이브: **15 NDJSON 파일** (synthetic 5 + real 8 + external 2) + 6/6 verification 통과.
- 누적 pytest **653 통과** (Phase 3 +153).

### Added — Phase 3 Track 3: 시나리오 L 광고 매칭 (AI 거버넌스 데모 메인, 2026-05-13)
- `api/services/ad_matcher.py`: 3 모드 광고 매칭 - keyword (토픽-카테고리 단순 매칭), embedding (코사인 유사도, mock=hash 기반), **agent (★ Bedrock 판단 - 민감 콘텐츠 감지)**.
- ADR-0004 Layer 6 trigger: Agent 모드만 SENSITIVE_PATTERNS (scandal·tragedy·minor_victim·controversy)를 감지하여 `chosen_ad_id=None` (광고 노출 생략) + reason_text에 "ADR-0004 Layer 6 trigger" 명시.
- `api/routers/ad_match.py`: POST /api/ad-match + GET /api/ad-match/modes. compare 모드에서 3 모드 동시 실행 + `governance_summary`로 차이 강조 ("Agent 모드만 광고를 거절").
- `api/main.py`: ad_match 라우터 등록.
- `tests/test_ad_match.py`: **39 테스트** - 안전/비위 콘텐츠 분리, Agent 거절 패턴, governance_summary, AdMatchDecision Pydantic 검증, SENSITIVE_PATTERNS 4 카테고리.
- 라이브 데모:
  - 안전(AI 산업 진흥) → 3 모드 모두 광고 매칭 (key 0.50 / emb 0.78 / agent 0.75)
  - 비위(검찰 수사) → keyword 0.30 매칭, embedding 0.83 매칭, **Agent 거절** (audit trace: "skip — 민감 콘텐츠 감지 (controversy, scandal). ADR-0004 Layer 6 trigger")
- 누적 pytest **627 통과** (Phase 3 +90).

### Added — Phase 3 Track 2: 시나리오 A 검색 라우터 (2026-05-13)
- `api/routers/search.py`: POST /api/search + GET /api/search/info. 페르소나 cohort 필터 + `opensearch.hybrid_search` + Neptune 1-hop subgraph (top hit). Cytoscape 호환 `SubgraphModel` (nodes/edges).
- 페르소나별 top_k 조정: 일반 독자 ≤5 (입문성), 데이터·AI ≥15 (분석 후보), 그 외 요청값.
- 페르소나별 extras: guide_hint(일반 독자) / premium_cta(유료) / api_response_hint(B2B) / analytics_hint(데이터·AI) / coverage(광고/세일즈).
- `api/main.py`: search 라우터 등록.
- `api/services/neptune.py`: mock 개선 - RETURN 변수(`return p`, `return b` 등) 인식. 1-hop subgraph 쿼리에서 정확한 노드 타입 반환. 5 helper로 분리 (bills/persons/votes/articles).
- `tests/test_search_router.py`: 37 테스트 (6 페르소나 처리, top_k 조정, cohort 전파, subgraph 모양, extras 페르소나별 분기, info endpoint).
- 라이브 데모: subgraph root=Bill + 3 Persons(PROPOSED) + 1 Vote(ON) = 5 nodes/4 edges.

### Added — Phase 3 Track 1: infra-cdk 6 스택 (2026-05-13)
- `infra-cdk/bin/assembly.ts`: 6 스택 인스턴스화 (network → data → ai → compute → edge → observability). 신규 VPC (ADR-0001 D7 - gcc retail VPC import 패턴과 분리).
- `infra-cdk/lib/network-stack.ts`: VPC 10.30.0.0/16, 3-AZ, NAT 1개, 5 SG (alb·app·neptune·os·lambda). cloudfront prefix list ingress 강제.
- `infra-cdk/lib/data-stack.ts`: Neptune cluster (t3.medium, isolated subnet), OpenSearch Serverless VECTORSEARCH 컬렉션, S3 3개 (raw/uploads/synthetic), DynamoDB 4개 (b2b-keys, ad-inventory, ad-impression with TTL, reader-profile).
- `infra-cdk/lib/ai-stack.ts`: Bedrock Guardrail '정치 중립성' (PartyAttack/PoliticianInsult DENY 토픽 + HATE/INSULTS/MISCONDUCT 필터).
- `infra-cdk/lib/compute-stack.ts`: ECS Fargate ARM64 (api+web 각 2 replica) + ALB + Ad Matcher Lambda 분리 (ADR-0004 Layer 6, ARM64).
- `infra-cdk/lib/edge-stack.ts`: Cognito 3개 pool (staff/subscriber/guest) + 페르소나 그룹 6개 + API Gateway B2B + Usage Plan + CloudFront. us-east-1 deploy.
- `infra-cdk/lib/observability-stack.ts`: CloudWatch Dashboard + 알람 2개 (political_balance_score < 0.8 + ALB 5xx > 1%).
- `infra-cdk/test/stacks.test.ts`: **24 Jest 테스트** + **6 스냅샷**. ARM64 강제·Guardrail 존재·Cognito 6 그룹·TTL·정치 균형 임계 검증.
- `cdk synth` 6 스택 통과 (76 feature flags - production hardening은 후속).
- npm 의존성 300 패키지 (aws-cdk-lib 2.170 + ts-jest 29.2 + jest 29.7 + typescript 5.7).

### Added — Phase 0 Bootstrap (2026-05-13)
- Fork target 결정: `ontology-for-gcc` (plan1-foundation) 아키텍처를 최대한 차용.
- 디렉토리 트리 생성 (gcc 동등): `api/`, `web/`, `infra-cdk/`, `data/`, `ontology/`, `tests/`, `docs/`, `scripts/`, `.claude/`, `.harness-eval/`, `.github/workflows/`.
- 메타 파일: `.gitignore`, `.editorconfig`, `.env.example`, `Makefile`, `requirements.txt`, `requirements-dev.txt`, `SECURITY.md`, `CHANGELOG.md`.
- 권위 설계 스펙: `docs/superpowers/specs/2026-05-13-ontology-assembly-design.md` — 6 페르소나(편집국 / 데이터·AI / 광고·세일즈 / 일반 독자 / 유료 구독자 / 기업·B2B 정책 인텔리전스), 14 시나리오 A–N, 25+ 클래스 온톨로지.
- ADR 0001–0004 작성: gcc 아키텍처 차용, 6-페르소나 설계, 대고객 서비스 확장, 정치 중립성 가드레일.
- `.claude/` 하니스: code-reviewer / security-auditor agents, wow-query-eval / cypher-conventions / persona-context skills, scrub-secrets + changelog-reminder hooks, deploy/review/test-all commands, settings.json (정치 도메인 deny list 보강).
- 모듈별 CLAUDE.md (api, web, infra-cdk, data, ontology).
- CI 4-job (`python-ast` · `tsc-check` · `cdk-synth` · `pytest`).

### Added — Phase 1 시작 (2026-05-13)
- `api/services/persona.py` SSOT 완성: 6 페르소나(editorial · data_ai · ad_sales · general_reader · paid_subscriber · b2b) + `NEUTRALITY_GUARD_SUFFIX` 상수(ADR-0004 Layer 2) + `system_prompt()`/`get()`/`ad_policy_for()`/`scenario_order()`/`all_persona_ids()` 헬퍼.
- `data/schemas.py` 31 노드 클래스 + 35 관계 SSOT: 인물·조직 6 / 입법 7 / 주제·외부 6 / 미디어 2 / 독자 5 / 광고 4 / 분석 1. `GraphNode` base + `source` 태깅 강제 + `extra="forbid"` + `HashedId` 정규식 가드.
- ADR-0004 Layer 4 가드 3중 강화: ① CI grep job, ② Pydantic `extra="forbid"`, ③ import-time `validate_no_forbidden_fields()`.
- `tests/conftest.py` — 26개 env 변수에 더미 값 collection-time 주입.
- `tests/test_persona.py` — 28 테스트 (페르소나 lookup, scenario_priority 14개 커버리지, NEUTRALITY_GUARD 자동 첨부, ad_policy 분기, customer-facing 3개 tone 차별화).
- `tests/test_schemas.py` — 39 테스트 (31 클래스 등록·HashedId 검증·AdMatchDecision audit trace·정치 중립성 필드 가드·관계 카탈로그 무결성·7개 그룹 완전성).
- `api/services/guardrails.py` (ADR-0004 Layer 1·3 통합): `political_balance_score(text)` — 정당 언급 균형(0.5) + 출처 인용(0.3) + 단정 표현 감점(0.2)의 가중 합산. `KNOWN_PARTIES` 9개 canonical 정당 (이념 라벨 0개). `check_prompt/check_output` heuristic + Bedrock Guardrails stub. `annotate_response()` — SSE final event용 메타데이터 builder. ALARM_THRESHOLD = 0.8.
- `tests/test_guardrails.py` — 22 테스트 (균형/편향 점수, 출처·단정 표현 영향, 정당 비방 차단, alarm 임계, 정당명 substring 이중카운트 방지, 페르소나별 응답 시뮬레이션).
- 버그 픽스: `_count_party_mentions` substring 이중카운트 (예: "민주당" ⊂ "더불어민주당") → placeholder 치환 패턴으로 해결.
- `tests/test_smoke.py` — services + schemas + guardrails 레이어 import 검증.
- `api/services/cohort.py`: `select(persona_id, scenario_code)` — 페르소나×시나리오 → data source list 결정 + `to_cypher_filter()` Cypher 변환 + `explain()` audit. SCENARIO_OVERRIDES 5개 (G·J·K·L·N).
- `api/services/bedrock.py`: `invoke()` 단일 LLM 진입점 - persona system prompt + Bedrock Guardrails 입력 가드 + Sonnet 4.6 호출 + political_balance_score 자동 첨부. DEMO_PUBLIC_MODE mock 응답 (페르소나별 어조 echo). `InvokeResult.to_sse_final()` SSE final event 변환.
- `tests/test_cohort.py` — 6 페르소나 × 14 시나리오 = 84 case parametrize + Cypher filter + audit trace.
- `tests/test_bedrock.py` — invoke 단일 진입점, persona·scenario 전파, 입력 가드 차단, mock 응답 균형성, SSE 직렬화.
- `api/services/neptune.py`: `open_cypher(query, *, parameters=None)` — **parameters 키워드 전용** 강제(Cypher injection syntactic 가드). SigV4 signed POST + Demo mode 쿼리 패턴 매칭 mock. `CypherResult` iterable/len/index 지원.
- `api/services/opensearch.py`: `hybrid_search(query, top_k, source_filter)` — BM25(Nori) + Cohere embed-v4 KNN + RRF + cohort source filter. Demo mode mock은 균형 잡힌 hit (정당 비방 없음, 다양한 node_type).
- `tests/test_neptune.py` — 19 테스트 (parameters keyword-only 강제, mock 쿼리 분기, source 태깅).
- `tests/test_opensearch.py` — 13 테스트 (top_k 제한, source_filter cohort 연동, 정당 비방 가드).
- `api/services/multi_agent.py` (Stage 3): 4 에이전트(Planner/Graph/Analyst/Editor) 순차 협업 + AgenticResult. AGENT_PROMPTS SSOT + run_agentic_pipeline.
- `api/services/three_stage.py` (시나리오 B 핵심): stage1_chatbot(RAG) / stage2_agent(Tool Use 4개) / stage3_agentic(Multi-Agent) / run_all_stages 비교 시연. StageResult dataclass + duration_ms + extras(approach/limitation/agent 중간 출력).
- `api/routers/chat.py`: POST /api/chat (compare/chatbot/agent/agentic 4 모드) + GET /api/chat/modes. X-Persona-Id 헤더 처리. Pydantic 유효성 검증.
- `api/main.py`: FastAPI app factory + 라우터 등록점 + /healthz, /api/healthz.
- `tests/test_three_stage.py` — 18 테스트 (3 stage 검증, 복잡도 점진성, 6 페르소나 처리, 직렬화).
- `tests/test_multi_agent.py` — 10 테스트 (4 에이전트 순서, 중간 출력, 도구 호출).
- `tests/test_chat_router.py` — 17 테스트 (TestClient, compare 모드, X-Persona-Id 6개, 유효성 검증).
- pytest **393 케이스 전 통과** (0.49초). 시나리오 B vertical slice 동작 확인 (mock 응답 구조 가시화).

### Changed — 디자인 원칙: stage 일관 / 페르소나 차별 (2026-05-13)
- `bedrock._mock_response` 재설계: stage 일관 + 페르소나 차별. 같은 질문에 3 stage final 텍스트는 동일하되 6 페르소나가 서로 다른 청중 언어로 응답(편집국 후속 취재 / 데이터·AI 통계 / 광고 AdMatchDecision / 일반 독자 친절 가이드 / 유료 구독자 심층+PDF / B2B JSON).
- Multi-agent 내부 에이전트(Planner/Graph/Analyst) 출력은 페르소나 무관 균일 (internal process detail). Editor 최종 출력은 페르소나 적용.
- `_detect_persona_id` 헬퍼 추가: persona.system_prompt 합성 결과("사용자는 <name> ...")에서 페르소나 ID 추출.
- 신규 테스트 18개: 6 페르소나 텍스트 distinctness, 페르소나별 식별 마커, stage 일관성, multi-agent 내부 중립성, 양당 균형, 출처 인용, B2B JSON 형식, 일반 독자 친절 어조.
- pytest **411 케이스 전 통과** (0.49초).
- 원칙 근거 (사용자): "같은 질문에 일관된 답변이 맞고, 독자·부서별로 답변이 달라지는게 좋습니다" + "PoC 수준 + 계속 사용한 에셋 (GS Caltex처럼)".

### Added — Phase 2 시작: 합성 generator + load CLI (2026-05-13)
- `data/synthetic/topics.py`: 25개 중립 정책 토픽 카탈로그 (산업·법무·사회·경제·환경·문화·외교안보). 이념 라벨 0개. `to_graph_nodes()` Pydantic Topic 변환.
- `data/synthetic/article.py`: 2,000 합성 기사 generator. 정치 균형(양당 빈도 CV<0.3) + 출처 인용 + 단정 표현 금지. AUTHOR_POOL 10명, PERSON_ID_POOL 100명, BILL_ID_POOL 100건, 9개 제목 템플릿. seed 결정성.
- `data/synthetic/reader.py`: 50,000 합성 독자 generator. SHA-256 솔티드 해시 ID(64자 lowercase hex), tier 분포 anonymous 80/free 15/paid 5, 17 시도 region(sgg 이상 정밀도 금지), 관심사 0-5개. ADR-0003 익명화 + ADR-0004 Layer 4 PII 가드.
- `data/synthetic/advertisement.py`: 500 합성 광고 + AdInventory 1:1 generator. 14 ADVERTISER_PROFILES (테크/금융/교육/친환경/자동차/통신/헬스케어/마케팅), 광고주별 avoid_topics 정책, 월 예산 50만~5천만 원 × 1~12개월, target_personas는 general_reader/paid_subscriber만.
- `data/load.py`: CLI 통합. `--source synthetic --to local --out-dir ...` 동작. 5개 NDJSON 파일(topics·articles·readers·advertisements·ad_inventories) 출력. `write_ndjson()` Pydantic 모델→NDJSON 헬퍼. Phase 3 stub (`--source real|external`, `--to s3`)는 exit code 2로 안내.
- `tests/test_synthetic_topics.py` — 9 테스트 (25개 등록·이념 라벨 가드·Pydantic 변환).
- `tests/test_synthetic_article.py` — 17 테스트 (결정성·정치 균형·political_balance_score ≥0.8·출처 인용).
- `tests/test_synthetic_reader.py` — 18 테스트 (HashedId 정규식·tier 분포 ±2%·PII 가드·salt 격리·관심사 tier 상관관계).
- `tests/test_synthetic_advertisement.py` — 21 테스트 (advertiser/inventory 1:1·avoid_topics 정합·target_personas 정책·budget 범위).
- `tests/test_load.py` — 16 테스트 (NDJSON round-trip·5개 파일·Phase 3 stub·subprocess CLI 실행).
- pytest **495 케이스 전 통과** (1.03초).
- 라이브 CLI 검증: 100 articles + 5000 readers + 30 ads = 1.1MB NDJSON. 균형 잡힌 정당 언급(민주 6건/국힘 6건), 익명 해시 ID, 17 시도 region 확인.

### Added — Phase 2 Track 2-2: 국회 OpenAPI 어댑터 (2026-05-13)
- `data/real/_client.py`: 공유 HTTP 클라이언트. SigV4 X (단순 KEY 인증), 페이징, JSON 응답 표준화 (`ApiResponse`). `AssemblyClient.iter_all_pages` row 단위 yield. `DEMO_PUBLIC_MODE=true` 분기.
- `data/real/bill.py`: `nzmimeepazxkubdpn` (의안처리상황) → Pydantic Bill. `STATUS_MAP` 처리결과 정규화, `_parse_date` 다양한 형식 지원. mock 의안 10건 (양당 균형).
- `data/real/member.py`: `nwvrqwxyaytdsfvhu` (국회의원 현황) → Pydantic Person. 지역구·비례대표 분류, party 4종 균형. mock 의원 10명.
- `data/real/vote.py`: `nojepdqqaweusdfbi` (본회의 표결) → Pydantic Vote. vote_id = V_<BILL_ID>_<DATE> 결정적 생성. mock 10건 (passed 7, rejected 2, withdrawn 1).
- 엔드포인트 코드는 env 변수(`ASSEMBLY_API_*_ENDPOINT`)로 외부화 - 환경별 격리.
- `data/load.py` CLI: `--source real|all` + `--demo` 플래그 + `--max-bills/--max-members/--max-votes` 추가.
- `tests/test_real_adapters.py` — 30 테스트 (API 응답 파싱·status 정규화·cross-adapter 참조 정합·정당 균형).

### Added — Phase 2 Track 2-3: 외부 시그널 ETL (2026-05-13)
- `data/external/naver_news.py`: 네이버 뉴스 검색 API → SocialSignal. HTML strip, pubDate 파싱, 결정적 signal_id (URL MD5 해시). Demo mock 10개 뉴스(균형 잡힌 정당 언급).
- `data/external/poll_result.py`: 합성 여론조사 generator → PollResult. 정당 지지율 6 정당(합 100%, 한 정당 ≤60%) + 토픽 의견(찬성/반대/잘 모름). 가공 기관명("Synth-Poll-A" 등 - 실 기관명 미사용).
- `data/load.py` CLI: `--source external` + `--news-query/--news-count/--poll-count` 추가.
- `tests/test_external_adapters.py` — 23 테스트 (뉴스 결정성·정당 합 100%·토픽 의견 균형·정치 중립성).

### Added — Phase 2 Track 2-5: PDF 시그니처 시드 + 통합 검증 (2026-05-13)
- `data/synthetic/seeds.py`: PDF 3페이지 시그니처 시연 시드. 7 entity (Person/Bill/Article/Vote/Statement/AdMatchDecision/Cluster). 데모 자산 ID 상수 (`DEMO_HUB_PERSON_ID`, `DEMO_AI_BILL_ID`, `DEMO_TRAGIC_ARTICLE_ID`, `DEMO_SWING_VOTE_ID`).
- 시나리오 B (3-stage chat) 허브 의원 + AI 의안 + 공동발의 패턴 시드.
- 시나리오 K (표결 이상치) 당론 이탈 시드.
- 시나리오 L (광고 매칭 거부) - `AdMatchDecision`의 `chosen_ad_id=None` + ADR-0004 Layer 6 reason 명시.
- 시나리오 M (의원 정치 여정) - 허브 의원 Statement + 정합 person_id 연결.
- 시나리오 E (클러스터) - 중립 추상 라벨 "혁신 입법 다수파".
- `scripts/verify_demo_dataset.py`: 통합 검증 스크립트. 6 검사 (파일 존재·Pydantic round-trip·source 태깅·정치 균형·cross-reference·seeds). standalone 실행 + pytest 양용. exit code 0/1/2.
- `tests/test_synthetic_seeds.py` — 13 테스트 (시드 ID·이념 라벨 가드·cross-reference·skip 결정 형식).
- `tests/test_verify_demo_dataset.py` — 7 테스트 (검증 스크립트 self-test, 모든 check 통과).

### Phase 2 누적 성과
- pytest **574 케이스 전 통과** (1.09초, 411 → 495 → 574).
- 10 NDJSON 파일 생성 (synthetic 5 + real 3 + external 2). `--source all --demo` 한 번에 718+ 노드.
- 라이브 검증 스크립트 6/6 통과.
- Phase 3 인프라(Neptune·OpenSearch·S3) 정착 후 즉시 `aws s3 sync` + Bulk Loader 적재 가능.

### Notes
- `raw_data/`는 `.gitignore`. 국회 OpenAPI raw payload와 합성 독자/광고 시드는 KMS S3 별도 보관.
- 첫 배포 도메인: `*.cloudfront.net` (커스텀 도메인은 Phase 5 polish에서 추가).
- 정치 중립성 가드레일은 Bedrock Guardrails로 시나리오 B·C·I 모두에 적용.
