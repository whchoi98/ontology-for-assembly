"""Object Explorer 라우터 - 31 클래스 인스턴스 탐색 (Phase 5 Track 5-6).

엔드포인트:
- GET /api/ontology/classes          31 클래스 메타 (그룹·필드·구현 여부)
- GET /api/ontology/{type}           클래스 단일 메타
- GET /api/objects/{type}            인스턴스 페이징 리스트
- GET /api/objects/{type}/{id}       단일 객체 + 1-hop subgraph

객체 디테일은 schemas의 Pydantic 모델 그대로 직렬화. 1-hop은 (가능한 경우) Neptune 호출.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api.services import objects_catalog

router = APIRouter(tags=["objects"])


# ─── Response 모델 ──────────────────────────────────────────────────────────

class ClassMeta(BaseModel):
    name: str
    group: str
    implemented: bool
    fields: list[dict]
    display: dict[str, str] = Field(default_factory=dict)


class ClassesResponse(BaseModel):
    total_classes: int
    implemented_count: int
    groups: dict[str, list[ClassMeta]]


class InstanceListResponse(BaseModel):
    type: str
    total: int
    offset: int
    limit: int
    items: list[dict]
    display: dict[str, str]
    implemented: bool


class InstanceDetailResponse(BaseModel):
    type: str
    id: str
    data: dict
    subgraph: Optional[dict] = None


# ─── 메타 엔드포인트 ────────────────────────────────────────────────────────

@router.get("/api/ontology/classes", response_model=ClassesResponse)
def list_classes() -> ClassesResponse:
    """31 클래스 메타 - 그룹·필드·구현 여부 한눈에."""
    from data.schemas import NODE_CLASSES
    groups: dict[str, list[ClassMeta]] = {}
    implemented_count = 0
    for group_name, members in objects_catalog.CLASS_GROUPS.items():
        group_list: list[ClassMeta] = []
        for cls_name in members:
            meta = objects_catalog.get_class_meta(cls_name)
            group_list.append(ClassMeta(**meta))
            if meta["implemented"]:
                implemented_count += 1
        groups[group_name] = group_list

    return ClassesResponse(
        total_classes=len(NODE_CLASSES),
        implemented_count=implemented_count,
        groups=groups,
    )


@router.get("/api/ontology/{class_name}", response_model=ClassMeta)
def class_meta(class_name: str) -> ClassMeta:
    meta = objects_catalog.get_class_meta(class_name)
    if not meta["fields"]:
        raise HTTPException(404, f"클래스 '{class_name}' 미정의")
    return ClassMeta(**meta)


# ─── 인스턴스 엔드포인트 ────────────────────────────────────────────────────

@router.get("/api/objects/{class_name}", response_model=InstanceListResponse)
def list_objects(
    class_name: str,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> InstanceListResponse:
    """클래스 인스턴스 페이징 리스트."""
    meta = objects_catalog.get_class_meta(class_name)
    if not meta["fields"]:
        raise HTTPException(404, f"클래스 '{class_name}' 미정의")

    items, total = objects_catalog.list_instances(class_name, limit=limit, offset=offset)
    return InstanceListResponse(
        type=class_name,
        total=total,
        offset=offset,
        limit=limit,
        items=items,
        display=meta["display"],
        implemented=meta["implemented"],
    )


@router.get("/api/objects/{class_name}/{instance_id}", response_model=InstanceDetailResponse)
def get_object(class_name: str, instance_id: str) -> InstanceDetailResponse:
    """단일 객체 디테일.

    instance list에서 id 매칭으로 검색. 발견 시 subgraph는 1-hop 시도.
    """
    items, _ = objects_catalog.list_instances(class_name, limit=200, offset=0)
    id_field = objects_catalog.get_class_meta(class_name).get("display", {}).get("id", "id")
    matched = next((it for it in items if str(it.get(id_field, "")) == instance_id), None)
    if matched is None:
        raise HTTPException(404, f"{class_name}/{instance_id} 인스턴스 없음")

    # 1-hop subgraph 시도 (실 Neptune 호출은 demo mode mock).
    subgraph = _try_build_subgraph(class_name, instance_id, matched)

    return InstanceDetailResponse(
        type=class_name,
        id=instance_id,
        data=matched,
        subgraph=subgraph,
    )


def _try_build_subgraph(class_name: str, instance_id: str, instance_data: dict) -> Optional[dict]:
    """루트 노드 + 직접 참조 ID들로 단순 subgraph 구성.

    관계 이름은 canonical relation (data/schemas.py RELATION_TYPES와 정합) - Cytoscape의
    [relation="..."] 셀렉터가 일관 스타일 적용.
    """
    nodes: list[dict] = [{
        "id": instance_id,
        "label": class_name,
        "data": {"source": instance_data.get("source", "real")},
    }]
    edges: list[dict] = []

    # 참조 필드 → (대상 클래스, 관계 이름).
    references: dict[str, tuple[str, str]] = {
        "proposer_id": ("Person", "PROPOSED"),
        "person_id": ("Person", "BY"),
        "bill_id": ("Bill", "VOTE_ON"),
        "vote_id": ("Vote", "VOTE_ON"),
        "committee_id": ("Committee", "MEMBER_OF"),
        "session_id": ("Session", "AT"),
        "party_id": ("Party", "BELONGS_TO"),
        "agency_id": ("Agency", "OVERSEES"),
        "topic_id": ("Topic", "ABOUT"),
        "article_id": ("Article", "REFERENCES"),
        "ad_id": ("Advertisement", "CANDIDATE"),
        "reader_id": ("Reader", "READ"),
    }
    for field, (ref_class, relation) in references.items():
        ref_id = instance_data.get(field)
        if ref_id and ref_id != instance_id and isinstance(ref_id, str):
            nodes.append({"id": ref_id, "label": ref_class, "data": {}})
            edges.append({"source": instance_id, "target": ref_id, "type": relation})

    # list 참조 (예: referenced_person_ids, referenced_bill_ids, topic_ids).
    list_refs: dict[str, tuple[str, str]] = {
        "referenced_person_ids": ("Person", "MENTIONS"),
        "referenced_bill_ids": ("Bill", "MENTIONS"),
        "topic_ids": ("Topic", "ABOUT"),
        "candidate_ad_ids": ("Advertisement", "CANDIDATE"),
    }
    for field, (ref_class, relation) in list_refs.items():
        values = instance_data.get(field) or []
        for v in values[:3]:  # 최대 3개
            if isinstance(v, str) and v != instance_id:
                nodes.append({"id": v, "label": ref_class, "data": {}})
                edges.append({"source": instance_id, "target": v, "type": relation})

    if len(nodes) == 1:
        return None  # 1-hop 참조 없음

    return {"root_id": instance_id, "nodes": nodes, "edges": edges}
