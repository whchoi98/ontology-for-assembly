"""pytest 글로벌 설정 — 모든 env 변수에 더미 값을 collection time에 주입.

production 배포는 이 값들을 미설정 상태로 둠 (fail-closed). 테스트는 boto3 호출이
실제 발생하지 않도록 import-site에서 모든 외부 서비스를 mock.
"""
from __future__ import annotations
import os

# Settings에 필요한 모든 env에 더미 값 주입 (collection time 보장).
_DEFAULTS = {
    "AWS_REGION": "ap-northeast-2",
    "ASSEMBLY_ENV": "test",
    "PUBLIC_DOMAIN": "test.example",
    "NEPTUNE_ENDPOINT": "neptune-test.local",
    "NEPTUNE_PORT": "8182",
    "OPENSEARCH_ENDPOINT": "https://os-test.local",
    "OPENSEARCH_INDEX": "ontology-assembly-test-kb-index",
    "BEDROCK_CHAT_MODEL_ID": "global.anthropic.claude-sonnet-4-6",
    "BEDROCK_EMBED_MODEL_ID": "global.cohere.embed-v4:0",
    "BEDROCK_RERANKER_INFERENCE_PROFILE_ARN": "arn:aws:bedrock:test::reranker",
    "BEDROCK_KB_ID": "kb-test",
    "BEDROCK_GUARDRAIL_ID": "gr-test",
    "AGENTCORE_MEMORY_ID": "mem-test",
    "COGNITO_USER_POOL_ID": "ap-northeast-2_test",
    "COGNITO_GUEST_IDENTITY_POOL_ID": "ap-northeast-2:test-guest",
    "COGNITO_APP_CLIENT_ID": "test-client",
    "ORIGIN_AUTH_SECRET_ARN": "arn:aws:secretsmanager:test::origin",
    "ASSEMBLY_OPENAPI_KEY": "test-key",
    "NAVER_NEWS_API_CLIENT_ID": "test-naver-id",
    "NAVER_NEWS_API_CLIENT_SECRET": "test-naver-secret",
    "POLL_SOURCE_ENDPOINT": "https://poll-test.local",
    "RAW_DOCS_BUCKET": "ontology-assembly-test-raw-docs",
    "UPLOADS_BUCKET": "ontology-assembly-test-uploads",
    "SYNTHETIC_DATA_BUCKET": "ontology-assembly-test-synthetic",
    "B2B_API_KEY_TABLE": "ontology-assembly-test-b2b-keys",
    "AD_MATCH_MODE": "agent",
    "AD_INVENTORY_TABLE": "ontology-assembly-test-ad-inventory",
    # 테스트 모드: Cognito·origin 인증 우회. production은 절대 설정하지 말 것.
    "DEMO_PUBLIC_MODE": "true",
    "REQUIRE_ORIGIN_AUTH": "false",
}

for key, value in _DEFAULTS.items():
    os.environ.setdefault(key, value)
