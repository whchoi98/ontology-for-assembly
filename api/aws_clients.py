"""boto3 session factory — neptune·opensearch·bedrock service들의 공통 진입점.

@lru_cache로 단일 session 재사용 (boto3 thread-safe). 환경변수 `AWS_REGION` 사용.

사용:
    from api.aws_clients import session as boto_session
    bedrock = boto_session().client("bedrock-runtime")
"""
from __future__ import annotations

import os
from functools import lru_cache

import boto3


@lru_cache(maxsize=1)
def session() -> boto3.Session:
    """프로세스당 단일 boto3 Session 재사용."""
    return boto3.Session(region_name=os.environ.get("AWS_REGION", "ap-northeast-2"))


def get_secret(secret_id: str) -> str:
    """Secrets Manager에서 값 가져오기. JSON·plain string 모두 지원.

    Args:
        secret_id: Secret ARN 또는 name (예: 'assembly/openapi-key').

    Returns:
        secret value (string).

    Raises:
        보안: 절대 raw secret 값을 print/log하지 말 것.
    """
    sm = session().client("secretsmanager")
    resp = sm.get_secret_value(SecretId=secret_id)
    return resp.get("SecretString") or resp.get("SecretBinary", b"").decode("utf-8")
