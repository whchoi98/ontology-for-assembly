# ECS One-shot 데이터 적재 — Python 처리 흐름

**문서 목적**: 국회 OpenAPI에서 데이터를 fetch하여 S3 → Neptune → OpenSearch에 적재하는 ECS one-shot task의 Python 구현을 시퀀스·코드 예시로 정리.

**관련 문서**:
- `docs/data-sources.md` (데이터 참조 매트릭스)
- `docs/call-flow.md` (런타임 호출 흐름)
- `docs/architecture-rationale.md` (RAG vs KG+Agent 의사결정)
- `data/CLAUDE.md` (data 모듈 메모리)
- ADR-0001 (gcc 패턴 차용 — Bulk Loader, source 태깅)
- ADR-0003 (Reader 익명화)
- ADR-0004 (정치 성향 필드 생성 금지)

> **핵심 메시지**: ECS one-shot 패턴의 핵심은 *같은 Docker 이미지*가 두 가지 역할을 한다는 것 —
> 평소엔 *FastAPI 서버*, `run-task` 시 *command override*로 `python -m data.load`를 실행해서
> *적재 batch job*이 됩니다. 별도 이미지·별도 cluster 안 필요.
> VPC private subnet 안에서 Neptune·OpenSearch 접근 권한을 가진 상태로 실행되므로
> 보안과 편의를 동시에 잡습니다.

---

## 1. ECS run-task 실행 명령

```bash
aws ecs run-task \
  --cluster assembly-dev-cluster \
  --task-definition assembly-dev-api \
  --launch-type FARGATE \
  --network-configuration 'awsvpcConfiguration={subnets=[subnet-...],securityGroups=[sg-...]}' \
  --overrides '{
    "containerOverrides": [{
      "name": "api",
      "command": ["python", "-m", "data.load", "--source", "all", "--to", "s3", "--bucket", "<bucket>", "--neptune", "--opensearch"]
    }]
  }'
```

| 옵션 | 의미 |
|---|---|
| `--task-definition` | API용 TD를 *재활용* — 별도 TD 등록 불필요 |
| `--overrides.command` | Dockerfile의 `CMD ["uvicorn", ...]` 대신 *python module 실행*으로 교체 |
| `--launch-type FARGATE` | 일회성 컨테이너, 작업 끝나면 종료 |
| network | API와 *동일 SG·subnet* → Neptune·OpenSearch private endpoint 접근 가능 |
| task-role | API task role 그대로 사용 → S3·Neptune·OpenSearch·Secrets Manager 권한 보유 |

---

## 2. Dual-purpose Docker 이미지 구조

```dockerfile
# api/Dockerfile (단순화)
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY api/ ./api/
COPY data/ ./data/        # ← loader도 포함
COPY ontology/ ./ontology/

# 기본 CMD: API 서버 모드
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

→ `data/` 디렉토리가 같은 이미지 안에 포함되어 있고, ECS task가 `python -m data.load`로 *다른 entrypoint를 호출*합니다.

---

## 3. `data/load.py` CLI 진입점

```python
# data/load.py:main (argparse)
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser("data.load")
    parser.add_argument("--source", choices=["synthetic", "real", "external", "all"], default="synthetic")  # Phase 2 = synthetic만
    parser.add_argument("--to", choices=["local", "s3"], default="local")
    parser.add_argument("--bucket", help="S3 bucket (--to=s3 필수)")
    parser.add_argument("--neptune", action="store_true", help="S3 → Neptune Bulk Load")
    parser.add_argument("--opensearch", action="store_true", help="NDJSON → OpenSearch bulk")
    # 실제 코드엔 --neptune-mode·--neptune-endpoint·--opensearch-index 등 Phase 3 플래그가 추가로 존재 (총 28개). --from-s3 플래그는 없음.
    args = parser.parse_args(argv)

    # 1. fetch (real OpenAPI / synthetic generate / external ETL)
    if args.source in ("synthetic", "all"):
        emit_synthetic_local(out_dir, ...)
    if args.source in ("real", "all"):
        emit_real_local(out_dir, ...)
    if args.source in ("external", "all"):
        emit_external_local(out_dir, ...)

    # 2. S3 업로드 (intermediate format)
    if args.to == "s3":
        emit_to_s3(out_dir, bucket=args.bucket)

    # 3. Neptune 적재
    if args.neptune:
        load_neptune_bulk(...) or load_neptune_opencypher(...)

    # 4. OpenSearch 적재
    if args.opensearch:
        load_opensearch_bulk(...)

    return 0
```

---

## 4. 국회 OpenAPI fetch — Generator 패턴 (lazy iterator)

```python
# data/real/_client.py — 공유 HTTP 클라이언트
class AssemblyClient:
    def __init__(self, api_key=None, timeout=30):
        self.api_key = api_key or os.environ["ASSEMBLY_OPENAPI_KEY"]
        self.base_url = "https://open.assembly.go.kr/portal/openapi"
        self.timeout = timeout

    def fetch_page(self, endpoint: str, *, p_index=1, p_size=100, **params) -> ApiResponse:
        """단일 페이지 fetch + retry."""
        import requests
        url = f"{self.base_url}/{endpoint}"
        q = {"KEY": self.api_key, "Type": "json", "pIndex": p_index, "pSize": p_size, **params}
        for attempt in range(3):  # 3회 재시도
            try:
                r = requests.get(url, params=q, timeout=self.timeout)
                r.raise_for_status()
                return _parse_response(r.json(), endpoint)
            except (requests.RequestException, ValueError) as e:
                if attempt == 2:
                    raise AssemblyApiError(f"{endpoint} fetch 실패: {e}")
                time.sleep(2 ** attempt)  # 지수 backoff
```

```python
# data/real/bill.py — Bill 어댑터 (Generator 패턴)
def fetch_bills(max_rows: int | None = None) -> Iterator[Bill]:
    """국회 OpenAPI 의안 → Bill Pydantic model.

    Generator: 한 페이지 fetch → yield 변환 → 다음 페이지 → ...
    대량 데이터를 메모리 효율적으로 처리.
    """
    client = AssemblyClient()
    p_index = 1
    yielded = 0
    while True:
        resp = client.fetch_page("nzmimeepazxkubdpn", p_index=p_index, p_size=100, AGE=22)
        if not resp.rows:
            break
        for row in resp.rows:
            # OpenAPI 필드 매핑 (BILL_NAME → title 등)
            bill = Bill(
                source="real",
                bill_id=row.get("BILL_ID") or "",
                title=row.get("BILL_NAME") or row.get("BILL_NM") or "",
                proposer_id=row.get("RST_PROPOSER") or row.get("PUBL_PROPOSER") or "",
                co_proposer_ids=_parse_co_proposers(row.get("PUBL_PROPOSER", "")),
                category=row.get("COMMITTEE_NM"),
                status=_map_status(row.get("PROC_RESULT_CD")),
            )
            yield bill
            yielded += 1
            if max_rows and yielded >= max_rows:
                return
        p_index += 1
        if yielded >= resp.total_count:
            break
```

→ **Generator + Pydantic v2**: lazy iteration으로 100K+ rows도 메모리 안정

---

## 5. NDJSON 직렬화 (Pydantic → 파일)

```python
# data/load.py:write_ndjson
def write_ndjson(items: Iterable[BaseModel], path: Path) -> int:
    """Pydantic 모델 iterator → NDJSON 파일.

    각 행이 단일 JSON object — Neptune Bulk Loader · OpenSearch bulk API 호환.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(item.model_dump_json() + "\n")  # Pydantic v2 직렬화
            count += 1
    return count
```

NDJSON 예시:
```
{"source":"real","bill_id":"PRC_X1...","title":"AI 산업 진흥법","proposer_id":"MONA_001",...}
{"source":"real","bill_id":"PRC_X2...","title":"개인정보 보호법 일부개정",...}
```

---

## 6. NDJSON → S3 업로드

```python
# data/load_aws.py:emit_to_s3
def emit_to_s3(out_dir: Path, *, bucket: str, prefix: str = "ndjson/") -> dict[str, str]:
    """로컬 NDJSON 디렉토리 → S3 (boto3)."""
    import boto3
    s3 = boto3.client("s3")  # ECS task role 자동 사용
    uploaded = {}
    for f in sorted(out_dir.glob("*.ndjson")):
        key = f"{prefix.rstrip('/')}/{f.name}"
        print(f"[s3] uploading {f.name} → s3://{bucket}/{key}", flush=True)
        s3.upload_file(str(f), bucket, key)
        uploaded[f.name] = f"s3://{bucket}/{key}"
    return uploaded
```

→ **boto3 자동 자격증명**: ECS task role을 IMDSv2로 자동 획득 → AccessKey 코드 하드코딩 불필요

---

## 7. S3 → Neptune 적재 (2가지 모드)

### Mode A: Bulk Loader (HTTP API · 대량용)

```python
# data/load_aws.py:load_neptune_bulk
def load_neptune_bulk(*, neptune_endpoint, s3_uri, iam_role_arn, region):
    """Neptune Bulk Loader HTTP API 호출 + SigV4 + 폴링."""
    from aws_requests_auth.aws_auth import AWSRequestsAuth
    import requests, boto3

    creds = boto3.Session().get_credentials()
    auth = AWSRequestsAuth(
        aws_access_key=creds.access_key,
        aws_secret_access_key=creds.secret_key,
        aws_token=creds.token,
        aws_host=neptune_endpoint,
        aws_region=region,
        aws_service="neptune-db",   # SigV4 service name
    )

    # POST /loader
    response = requests.post(
        f"https://{neptune_endpoint}:8182/loader",
        json={
            "source": s3_uri,                  # s3://bucket/ndjson/
            "format": "csv",
            "iamRoleArn": iam_role_arn,        # Neptune cluster의 S3 read 권한 role
            "region": region,
            "failOnError": "FALSE",
            "parallelism": "MEDIUM",
        },
        auth=auth,
        timeout=60,
    )
    load_id = response.json()["payload"]["loadId"]

    # GET /loader/{loadId} 폴링 — 10초 간격
    while True:
        s = requests.get(f"{url}/{load_id}", auth=auth, timeout=30)
        status = s.json()["payload"]["overallStatus"]["status"]
        if status == "LOAD_COMPLETED":
            return {"loadId": load_id, "status": status}
        if status == "LOAD_FAILED":
            raise NeptuneLoaderError(...)
        time.sleep(10)
```

### Mode B: openCypher UNWIND MERGE (소량·디버깅용)

```python
def load_neptune_opencypher(*, neptune_endpoint, ndjson_dir, batch_size=100):
    """NDJSON → openCypher MERGE 배치 적재.

    Bulk Loader CSV 포맷 불일치 시 폴백.
    """
    import boto3
    client = boto3.client("neptunedata",
                          endpoint_url=f"https://{neptune_endpoint}:8182",
                          region_name="ap-northeast-2")

    for ndjson_path in ndjson_dir.glob("*.ndjson"):
        label, pk = NDJSON_NODE_MAPPING[ndjson_path.name]  # ("Bill", "bill_id")
        items = []
        for line in ndjson_path.read_text(encoding="utf-8").splitlines():
            items.append(_sanitize_for_neptune(json.loads(line)))
            if len(items) >= batch_size:
                _flush_batch(client, label, pk, items)
                items = []
        if items:
            _flush_batch(client, label, pk, items)

def _flush_batch(client, label: str, pk: str, items: list[dict]):
    """UNWIND $items AS row MERGE (n:Label {pk: row.pk}) SET n += row"""
    cypher = (
        f"UNWIND $items AS row "
        f"MERGE (n:{label} {{{pk}: row.{pk}}}) "
        f"SET n += row"
    )
    client.execute_open_cypher_query(
        openCypherQuery=cypher,
        parameters=json.dumps({"items": items}, ensure_ascii=False),
    )
```

→ **boto3 `neptunedata` SDK**: SigV4 자동 처리 (Phase 4d의 핵심 발견)

---

## 8. NDJSON → OpenSearch Serverless 적재

```python
# data/load_aws.py:load_opensearch_bulk (단순화)
def load_opensearch_bulk(
    *,
    endpoint: str,
    index_name: str = "assembly-dev-kb-index",
    ndjson_path: Path,                 # 단일 NDJSON 파일 (articles.ndjson)
    region: str = "ap-northeast-2",
    batch_size: int = 500,
    verbose: bool = True,
):
    """OpenSearch Serverless _bulk API — 단일 NDJSON 파일을 단일 인덱스로 적재.

    NDJSON → bulk 형식 변환 → POST /_bulk (SigV4 auth, service=aoss)
    """
    from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
    import boto3

    creds = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(creds, region, "aoss")
    client = OpenSearch(
        hosts=[{"host": endpoint, "port": 443}],
        http_auth=auth, use_ssl=True, verify_certs=True,
        connection_class=RequestsHttpConnection,
    )

    # NDJSON → bulk 명령 형식 (action line + doc line 페어)
    bulk_lines = []
    for line in ndjson_path.read_text(encoding="utf-8").splitlines():
        bulk_lines.append({"index": {"_index": index_name}})
        bulk_lines.append(json.loads(line))

    for chunk in _chunks(bulk_lines, batch_size):  # 배치 단위 split
        client.bulk(body=chunk)
```

> 참고: 멀티 클래스를 인덱스별로 적재하는 디렉토리 glob 루프는 Neptune 경로(`load_neptune_opencypher`)에 해당. OpenSearch는 현재 단일 `articles.ndjson` → 단일 KB 인덱스(`load.py`가 `ndjson_path=articles_ndjson`로 호출).

→ **Cohere embed-v4 enrichment**: bulk 전에 `enrich_articles_with_embedding`이 각 row에 `embedding` 벡터 첨부 → KNN 검색용

---

## 9. 안전장치 — 정치 중립성 + 데이터 무결성

### Reader 익명화 (ADR-0003)

```python
# data/synthetic/reader.py
def _hash_reader_id(raw_id: str) -> str:
    """솔티드 SHA-256 — IP/UA 원본 절대 저장 금지."""
    salt = os.environ["READER_HASH_SALT"]
    return hashlib.sha256(f"{salt}:{raw_id}".encode()).hexdigest()[:16]
```

### 정치 성향 필드 차단 (ADR-0004)

```python
# data/synthetic/reader.py
class Reader(BaseModel):
    reader_id: str
    age_bucket: str
    region: str
    # political_leaning 등 정치 성향 필드 ❌ 절대 생성 금지
```

### Graceful 어댑터 실패 처리

```python
def _safe_fetch(name: str, gen_fn, path: Path) -> int:
    """한 entity 실패가 전체 abort 안 되도록."""
    try:
        return write_ndjson(gen_fn(), path)
    except Exception as e:
        failures.append(name)
        print(f"[{name}] ⚠️ 실패 — skip 후 계속: {type(e).__name__}: {e}")
        return 0
```

---

## 10. 전체 흐름 (한 장)

```
┌────────────────────────────────────────────────────────────────┐
│  ECS run-task --task-definition assembly-dev-api               │
│    --overrides command=["python","-m","data.load",...]         │
└────────────────────────────────────────────────────────────────┘
                              │ ECS Fargate 컨테이너 시작
                              ▼
┌────────────────────────────────────────────────────────────────┐
│  data/load.py:main(argv)                                       │
│    ├─ argparse: --source, --to, --neptune, --opensearch        │
│    └─ DEMO_PUBLIC_MODE / ASSEMBLY_OPENAPI_KEY 환경변수 체크    │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│  Phase 1: Fetch (Generator iterators)                          │
│    ├─ data/real/bill.py:fetch_bills() — 국회 OpenAPI           │
│    ├─ data/real/member.py:fetch_members() — Person 286명       │
│    ├─ data/real/vote.py:fetch_votes() — 표결 28K              │
│    ├─ data/synthetic/article.py:generate_articles()            │
│    └─ data/external/naver_news.py — RSS                       │
│                                                                  │
│  각 어댑터: HTTP retry(3회) + 페이징(pIndex/pSize) + Pydantic  │
└────────────────────────────────────────────────────────────────┘
                              │ write_ndjson() — 한 행 = 한 JSON
                              ▼
┌────────────────────────────────────────────────────────────────┐
│  로컬 /tmp/data/output/                                         │
│    ├─ bills.ndjson  (2,098 rows)                                │
│    ├─ members.ndjson  (286 rows)                                │
│    ├─ votes.ndjson  (28,528 rows)                               │
│    ├─ articles.ndjson  (2,000 rows synthetic)                  │
│    └─ ...                                                        │
└────────────────────────────────────────────────────────────────┘
                              │ emit_to_s3() — boto3 upload_file
                              ▼
┌────────────────────────────────────────────────────────────────┐
│  S3: s3://assembly-dev/ndjson/{file}.ndjson                    │
└────────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┴─────────────┐
                ▼                            ▼
┌─────────────────────┐    ┌──────────────────────────────────┐
│ Neptune Bulk Loader │    │  OpenSearch Serverless _bulk      │
│ POST /loader        │    │  + Cohere embed-v4 enrichment     │
│ + SigV4 auth        │    │  + AWSV4SignerAuth (aoss)         │
│ + 10s polling       │    │  + 500-doc batch                  │
└─────────────────────┘    └──────────────────────────────────┘
        │                                  │
        ▼                                  ▼
   74,249 edges                    KNN-indexed 의안·기사
   (PROPOSED, VOTED, ...)          (BM25 + dense vector)
```

---

## 11. 운영 모니터링

```bash
# 1. task 실행 시작
TASK_ARN=$(aws ecs run-task ... --query 'tasks[0].taskArn' --output text)

# 2. 로그 실시간 follow
aws logs tail /ecs/assembly-dev-api --follow \
  --filter-pattern '[bill] OR [member] OR [vote] OR [neptune] OR [opensearch]'

# 3. 완료까지 wait
aws ecs wait tasks-stopped --cluster assembly-dev-cluster --tasks $TASK_ARN

# 4. exit code 확인
aws ecs describe-tasks --cluster assembly-dev-cluster --tasks $TASK_ARN \
  --query 'tasks[0].containers[0].exitCode'
```

---

## 12. 핵심 Python 패턴 정리

| 패턴 | 위치 | 이유 |
|---|---|---|
| **Generator (`yield`)** | `data/real/*.py` | 100K+ rows lazy iteration → 메모리 효율 |
| **Pydantic v2 model** | `data/schemas.py` | 타입 검증 + `model_dump_json()` 직렬화 |
| **NDJSON 중간 포맷** | `data/load.py:write_ndjson` | Neptune Bulk Loader + OpenSearch _bulk 양쪽 호환 |
| **boto3 + IMDSv2 자동 자격증명** | 전체 | ECS task role 자동 사용 → AccessKey 하드코딩 금지 |
| **SigV4 manual signing** | `load_neptune_bulk` | `aws_requests_auth.AWSRequestsAuth` (neptune-db service) |
| **boto3 `neptunedata` SDK** | `load_neptune_opencypher` | SigV4 자동 처리 (Phase 4d 발견) |
| **3회 지수 backoff retry** | `AssemblyClient.fetch_page` | OpenAPI rate limit 회피 |
| **Graceful per-entity 실패** | `_safe_fetch` | 한 어댑터 실패해도 나머지 적재 진행 |
| **`argparse` CLI** | `data/load.py:main` | ECS overrides 명령 동일 인터페이스 |
| **Same Docker image dual-purpose** | `Dockerfile` | API + loader 통합 — 별도 image build 회피 |

---

## 13. 시연 narrative 활용

이 흐름은 *PoC의 데이터 신뢰성 narrative*의 backbone:

- **"실제 국회 OpenAPI에서 fetch"** → real 데이터 검증 가능
- **"Generator + lazy iteration"** → 100만+ scale 처리 가능 (성능 narrative)
- **"같은 Docker 이미지 dual-purpose"** → 운영 간소함·비용 효율 narrative
- **"3-tier source 태깅 (real·synthetic·external)"** → 데이터 출처 투명성 (정치 중립성 narrative)
- **"Reader 익명화 + 정치 성향 필드 차단"** → GDPR/PIPA 준수 narrative

---

## 14. 후속 개선 후보

| Phase | 작업 |
|---|---|
| Phase 4g 후보 | OpenAPI rate limit *adaptive throttling* (현재 fixed 3회 retry) |
| Phase 5 polish | Bulk Loader → Bulk Loader v2 (CSV 대신 NDJSON 직접 지원) |
| 거버넌스 | Neptune 적재 후 *자동 검증* (`scripts/verify_source_tags.py` CI 통합) |
| 모니터링 | CloudWatch alarm — bulk load 실패·OpenAPI 응답 시간 초과 |
| 확장 | 다른 정부 OpenAPI 어댑터 추가 (행정안전부·법제처 등) — 동일 generator 패턴 재사용 |
