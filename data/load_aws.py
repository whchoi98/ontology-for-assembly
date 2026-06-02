"""AWS 적재 모듈 - Phase 3 실 인프라 통합.

3 단계:
1. NDJSON → S3 (`emit_to_s3`)
2. S3 → Neptune Bulk Loader (`load_neptune_bulk`)
3. NDJSON → OpenSearch Serverless bulk index (`load_opensearch_bulk`)

사용:
    # 로컬 NDJSON → S3 + Neptune + OpenSearch
    python -m data.load --source synthetic --to s3 --bucket assembly-synth --neptune --opensearch

References:
- ADR-0001 D10 Neptune Bulk Loader (gcc 패턴 차용)
- AWS Neptune Bulk Loader API: https://docs.aws.amazon.com/neptune/latest/userguide/bulk-load-tutorial-format-gremlin.html
- OpenSearch Serverless aoss bulk: https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-clients.html
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Iterator

__all__ = [
    "emit_to_s3",
    "load_neptune_bulk",
    "load_neptune_opencypher",
    "load_opensearch_bulk",
    "enrich_articles_with_embedding",
    "NeptuneLoaderError",
    "OpenSearchLoaderError",
]


# NDJSON 파일 이름 → Neptune node label + primary key field 매핑.
NDJSON_NODE_MAPPING: dict[str, tuple[str, str]] = {
    "topics.ndjson": ("Topic", "topic_id"),
    "articles.ndjson": ("Article", "article_id"),
    "readers.ndjson": ("Reader", "reader_id"),
    "advertisements.ndjson": ("Advertisement", "ad_id"),
    "ad_inventories.ndjson": ("AdInventory", "inventory_id"),
    "bills.ndjson": ("Bill", "bill_id"),
    "members.ndjson": ("Person", "assembly_id"),
    "votes.ndjson": ("Vote", "vote_id"),
    "committees.ndjson": ("Committee", "committee_id"),
    "parties.ndjson": ("Party", "party_id"),
    "agencies.ndjson": ("Agency", "agency_id"),
}


# ─── 예외 ────────────────────────────────────────────────────────────────


class NeptuneLoaderError(RuntimeError):
    """Neptune Bulk Loader 실패."""


class OpenSearchLoaderError(RuntimeError):
    """OpenSearch bulk index 실패."""


# ─── 1) NDJSON → S3 ──────────────────────────────────────────────────────


def emit_to_s3(
    out_dir: Path,
    *,
    bucket: str,
    prefix: str = "ndjson/",
    verbose: bool = True,
) -> dict[str, str]:
    """로컬 NDJSON 디렉토리를 S3에 업로드.

    Args:
        out_dir: NDJSON 파일들이 있는 로컬 디렉토리.
        bucket: S3 버킷 이름.
        prefix: 키 접두사 (기본 `ndjson/`).

    Returns:
        {file_name: s3_uri} dict.
    """
    import boto3

    s3 = boto3.client("s3")
    uploaded: dict[str, str] = {}

    for f in sorted(out_dir.glob("*.ndjson")):
        key = f"{prefix.rstrip('/')}/{f.name}"
        if verbose:
            print(f"[s3] uploading {f.name} ({f.stat().st_size:,} bytes) → s3://{bucket}/{key}", flush=True)
        s3.upload_file(str(f), bucket, key)
        uploaded[f.name] = f"s3://{bucket}/{key}"

    return uploaded


# ─── 2) Neptune Bulk Loader ──────────────────────────────────────────────


def load_neptune_bulk(
    *,
    neptune_endpoint: str,
    s3_uri: str,
    iam_role_arn: str,
    region: str = "ap-northeast-2",
    format: str = "csv",
    verbose: bool = True,
    poll_interval_sec: int = 10,
    timeout_sec: int = 1800,
) -> dict:
    """Neptune Bulk Loader 호출 + 완료 폴링.

    Args:
        neptune_endpoint: Neptune cluster endpoint (e.g. `assembly-neptune-cluster.cluster-XXX.region.neptune.amazonaws.com`).
        s3_uri: S3 URI prefix (e.g. `s3://bucket/ndjson/`).
        iam_role_arn: Neptune cluster의 IAM role ARN (S3 read 권한).
        region: AWS region.
        format: `csv` 또는 `opencypher` 또는 `nquads` 등 (Neptune Loader spec).

    Returns:
        {loadId, status, errors} dict.
    """
    # Neptune Bulk Loader HTTP API + IAM SigV4.
    # Neptune cluster의 IAMDatabaseAuthenticationEnabled=true 일 때 SigV4 필수.
    # service='neptune-db'로 sign. ECS task role(권한: neptune-db:*) 사용.
    import boto3
    import requests
    from aws_requests_auth.aws_auth import AWSRequestsAuth

    creds = boto3.Session().get_credentials()
    host_only = neptune_endpoint.split(":")[0]
    auth = AWSRequestsAuth(
        aws_access_key=creds.access_key,
        aws_secret_access_key=creds.secret_key,
        aws_token=creds.token,
        aws_host=host_only,
        aws_region=region,
        aws_service="neptune-db",
    )

    url = f"https://{neptune_endpoint}:8182/loader"
    payload = {
        "source": s3_uri,
        "format": format,
        "iamRoleArn": iam_role_arn,
        "region": region,
        "failOnError": "FALSE",
        "parallelism": "MEDIUM",
        "updateSingleCardinalityProperties": "FALSE",
        "queueRequest": "TRUE",
    }
    if verbose:
        print(f"[neptune] submit bulk load (SigV4): {s3_uri} → {neptune_endpoint}", flush=True)
    response = requests.post(url, json=payload, auth=auth, timeout=60)
    if response.status_code != 200:
        raise NeptuneLoaderError(
            f"Bulk loader submission failed: HTTP {response.status_code} {response.text[:300]}"
        )
    body = response.json()
    load_id = body.get("payload", {}).get("loadId")
    if not load_id:
        raise NeptuneLoaderError(f"No loadId in response: {body}")
    if verbose:
        print(f"[neptune] loadId: {load_id}", flush=True)

    # 폴링 - SigV4 동일
    deadline = time.time() + timeout_sec
    status_url = f"{url}/{load_id}"
    while time.time() < deadline:
        s = requests.get(status_url, params={"details": "false"}, auth=auth, timeout=30)
        if s.status_code != 200:
            raise NeptuneLoaderError(f"Status poll failed: HTTP {s.status_code} {s.text[:200]}")
        sbody = s.json()
        status = sbody.get("payload", {}).get("overallStatus", {}).get("status", "UNKNOWN")
        if verbose:
            print(f"[neptune] status: {status}", flush=True)
        if status in ("LOAD_COMPLETED", "LOAD_COMPLETED_WITH_ERRORS"):
            return {"loadId": load_id, "status": status, "details": sbody}
        if status in ("LOAD_FAILED", "LOAD_CANCELLED_BY_USER"):
            raise NeptuneLoaderError(f"Bulk load failed: {sbody}")
        time.sleep(poll_interval_sec)

    raise NeptuneLoaderError(f"Bulk load timed out after {timeout_sec}s (loadId={load_id})")


# ─── 2b) Neptune OpenCypher (NDJSON 직접) ────────────────────────────────


def _sanitize_for_neptune(item: dict) -> dict:
    """Neptune property는 list/dict 미지원 - flatten 또는 JSON string화.

    - list[str]: JSON string으로 직렬화 (검색 시 LIKE 사용)
    - dict: JSON string
    - None: 키 제거
    """
    out: dict = {}
    for k, v in item.items():
        if v is None:
            continue
        if isinstance(v, (list, dict)):
            out[k] = json.dumps(v, ensure_ascii=False)
        else:
            out[k] = v
    return out


def load_neptune_opencypher(
    *,
    neptune_endpoint: str,
    ndjson_dir: Path,
    region: str = "ap-northeast-2",
    batch_size: int = 100,
    verbose: bool = True,
) -> dict[str, int]:
    """Neptune에 NDJSON 노드를 OpenCypher UNWIND MERGE로 직접 적재.

    Bulk Loader (CSV) 대신 사용 - NDJSON 그대로 사용 가능. IAM auth는 boto3 자동.

    Returns: {label: count}.
    """
    import boto3

    client = boto3.client(
        "neptunedata",
        endpoint_url=f"https://{neptune_endpoint}:8182",
        region_name=region,
    )

    counts: dict[str, int] = {}

    for f in sorted(ndjson_dir.glob("*.ndjson")):
        mapping = NDJSON_NODE_MAPPING.get(f.name)
        if not mapping:
            if verbose:
                print(f"[neptune] skip unknown file: {f.name}", flush=True)
            continue
        label, id_field = mapping

        # NDJSON 읽기 + flatten
        items: list[dict] = []
        with f.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    items.append(_sanitize_for_neptune(json.loads(line)))

        if not items:
            continue

        if verbose:
            print(f"[neptune] {label}: {len(items)} items → MERGE on .{id_field}", flush=True)

        # batch UNWIND MERGE
        total = 0
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            query = (
                f"UNWIND $items AS item "
                f"MERGE (n:{label} {{{id_field}: item.{id_field}}}) "
                f"SET n += item"
            )
            try:
                client.execute_open_cypher_query(
                    openCypherQuery=query,
                    parameters=json.dumps({"items": batch}, ensure_ascii=False),
                )
                total += len(batch)
            except Exception as e:
                raise NeptuneLoaderError(f"{label} batch {i}: {e}") from e

        counts[label] = total
        if verbose:
            print(f"[neptune] {label}: {total} merged", flush=True)

    return counts


# ─── 3) OpenSearch Serverless bulk ───────────────────────────────────────


# Nori (한국어 형태소 분석기) 인덱스 매핑 - hybrid search (BM25 + KNN).
ARTICLE_INDEX_MAPPING = {
    "settings": {
        "index": {
            "knn": True,
            "knn.algo_param": {"ef_search": 100},
        },
        "analysis": {
            "analyzer": {
                "nori_kr": {
                    "type": "custom",
                    "tokenizer": "nori_tokenizer",
                    "filter": ["nori_part_of_speech", "lowercase"],
                }
            }
        },
    },
    "mappings": {
        "properties": {
            "article_id": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "nori_kr"},
            "content": {"type": "text", "analyzer": "nori_kr"},
            "published_at": {"type": "date"},
            "author": {"type": "keyword"},
            "topic_ids": {"type": "keyword"},
            "embedding": {
                "type": "knn_vector",
                "dimension": 1024,  # cohere embed-v4
                "method": {"name": "hnsw", "engine": "nmslib"},
            },
        }
    },
}


def _aoss_client(endpoint: str, region: str = "ap-northeast-2"):
    """OpenSearch Serverless 인증 client - AWS SigV4 ('aoss' service)."""
    from opensearchpy import OpenSearch, RequestsHttpConnection
    from aws_requests_auth.aws_auth import AWSRequestsAuth
    import boto3

    creds = boto3.Session().get_credentials()
    host = endpoint.replace("https://", "").replace("http://", "").rstrip("/")
    auth = AWSRequestsAuth(
        aws_access_key=creds.access_key,
        aws_secret_access_key=creds.secret_key,
        aws_token=creds.token,
        aws_host=host,
        aws_region=region,
        aws_service="aoss",
    )
    return OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=60,
        max_retries=3,
        retry_on_timeout=True,
    )


# ─── 3b) Bedrock embedding (Cohere embed-v4) ─────────────────────────────


def _embed_batch(
    bedrock_client,
    texts: list[str],
    *,
    model_id: str = "global.cohere.embed-v4:0",
    input_type: str = "search_document",
) -> list[list[float]]:
    """Cohere embed-v4 호출 - 한국어 지원. 1024-dim float vector 반환."""
    body = {
        "texts": texts[:96],  # Cohere limit: 96 per call
        "input_type": input_type,
        "embedding_types": ["float"],
        "output_dimension": 1024,  # OS index mapping과 정합 (default 1536 → 1024)
        "truncate": "END",
    }
    resp = bedrock_client.invoke_model(
        modelId=model_id,
        body=json.dumps(body, ensure_ascii=False),
        contentType="application/json",
    )
    parsed = json.loads(resp["body"].read())
    # v4: response structure {"embeddings": {"float": [[...], ...]}, ...}
    embeddings = parsed.get("embeddings", [])
    if isinstance(embeddings, dict):
        embeddings = embeddings.get("float", [])
    return embeddings


def enrich_articles_with_embedding(
    *,
    endpoint: str,
    index_name: str = "assembly-dev-kb-index",
    bedrock_model_id: str = "global.cohere.embed-v4:0",
    region: str = "ap-northeast-2",
    batch_size: int = 32,
    verbose: bool = True,
) -> dict:
    """기존 색인된 article 문서를 읽어와 Cohere embedding을 추가 후 update.

    이 함수는 색인 후 별도 실행 (사후 enrichment).

    Returns: {updated: int, total: int}
    """
    import boto3

    client = _aoss_client(endpoint, region)
    bedrock = boto3.client("bedrock-runtime", region_name=region)

    # 모든 article 가져오기 - full _source (re-index 시 full replace).
    resp = client.search(
        index=index_name,
        body={"query": {"match_all": {}}, "size": 1000},
    )
    docs = resp["hits"]["hits"]
    total = len(docs)
    if verbose:
        print(f"[embed] {total} articles found", flush=True)

    updated = 0
    for i in range(0, total, batch_size):
        batch = docs[i:i + batch_size]
        texts = [(d["_source"].get("title", "") + " " + d["_source"].get("content", ""))[:2000] for d in batch]
        try:
            embeddings = _embed_batch(bedrock, texts, model_id=bedrock_model_id)
        except Exception as e:
            if verbose:
                print(f"[embed] FAILED batch {i}: {e}", flush=True)
            continue

        # AOSS Serverless는 partial update 제약 - index(full replace) 사용.
        # _id 명시는 AOSS 제약상 안 됨 → 옛 문서 delete 후 새 문서 index.
        bulk_body = []
        for doc, vec in zip(batch, embeddings):
            doc_id = doc["_id"]
            source = doc["_source"]
            source["embedding"] = vec
            # delete old + index new (without _id - auto-gen)
            bulk_body.append({"delete": {"_index": index_name, "_id": doc_id}})
            bulk_body.append({"index": {"_index": index_name}})
            bulk_body.append(source)
        result = client.bulk(body=bulk_body)

        sample_err = None
        for item in result.get("items", []):
            if "index" in item:
                if "error" in item["index"]:
                    if sample_err is None:
                        sample_err = item["index"]["error"]
                else:
                    updated += 1
        if verbose:
            if sample_err:
                print(f"[embed] sample error: {sample_err}", flush=True)
            print(f"[embed] {updated}/{total} embeddings stored", flush=True)

    return {"updated": updated, "total": total}


def load_opensearch_bulk(
    *,
    endpoint: str,
    index_name: str = "assembly-dev-kb-index",
    ndjson_path: Path,
    region: str = "ap-northeast-2",
    batch_size: int = 500,
    verbose: bool = True,
) -> dict:
    """OpenSearch Serverless에 article NDJSON bulk index.

    인덱스 미존재 시 자동 생성 (Nori + KNN 매핑).

    Args:
        endpoint: AOSS collection endpoint.
        index_name: 인덱스 이름.
        ndjson_path: article NDJSON 파일 경로.
        batch_size: 한 bulk 요청 배치 크기.

    Returns:
        {indexed: int, errors: int, took_ms: int}
    """
    client = _aoss_client(endpoint, region)

    # 인덱스 생성 (이미 있으면 skip).
    if not client.indices.exists(index=index_name):
        if verbose:
            print(f"[opensearch] create index: {index_name}", flush=True)
        client.indices.create(index=index_name, body=ARTICLE_INDEX_MAPPING)

    indexed = 0
    errors = 0
    start = time.time()

    def _batches(it: Iterator[dict], size: int) -> Iterator[list[dict]]:
        batch: list[dict] = []
        for item in it:
            batch.append(item)
            if len(batch) >= size:
                yield batch
                batch = []
        if batch:
            yield batch

    def _read_ndjson(p: Path) -> Iterator[dict]:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    for batch in _batches(_read_ndjson(ndjson_path), batch_size):
        bulk_body = []
        for doc in batch:
            # AOSS Serverless는 client-supplied _id 미허용 - 자동 생성됨.
            # article_id는 doc body에 유지 (필드로 검색 가능).
            bulk_body.append({"index": {"_index": index_name}})
            bulk_body.append(doc)
        resp = client.bulk(body=bulk_body)
        if resp.get("errors"):
            failed_sample = None
            for item in resp.get("items", []):
                if "error" in item.get("index", {}):
                    errors += 1
                    if failed_sample is None:
                        failed_sample = item["index"]["error"]
            if verbose and failed_sample:
                print(f"[opensearch] sample error: {failed_sample}", flush=True)
        indexed += len(batch)
        if verbose and indexed % (batch_size * 4) == 0:
            print(f"[opensearch] indexed {indexed:,}, errors {errors}", flush=True)

    took_ms = int((time.time() - start) * 1000)
    if verbose:
        print(f"[opensearch] DONE indexed={indexed:,} errors={errors} took={took_ms}ms", flush=True)
    return {"indexed": indexed, "errors": errors, "took_ms": took_ms}
