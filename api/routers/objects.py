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


def _normalize_class_name(class_name: str) -> str:
    """case-insensitive class name lookup.

    클라이언트가 `party`(lowercase) 또는 `PARTY`(uppercase)로 호출해도
    canonical PascalCase `Party`로 dispatch — CytoscapeView expand 경로의
    `CLASS_TO_TYPE_SLUG` lowercase 변환과 backend route mismatch 해결.
    """
    from data.schemas import NODE_CLASSES
    if class_name in NODE_CLASSES:
        return class_name
    lower = class_name.lower()
    for canonical in NODE_CLASSES:
        if canonical.lower() == lower:
            return canonical
    return class_name  # fallback (caller가 404 처리)


@router.get("/api/ontology/{class_name}", response_model=ClassMeta)
def class_meta(class_name: str) -> ClassMeta:
    class_name = _normalize_class_name(class_name)
    meta = objects_catalog.get_class_meta(class_name)
    if not meta["fields"]:
        raise HTTPException(404, f"클래스 '{class_name}' 미정의")
    return ClassMeta(**meta)


# ─── 인스턴스 엔드포인트 ────────────────────────────────────────────────────

@router.get("/api/objects/{class_name}", response_model=InstanceListResponse)
def list_objects(
    class_name: str,
    limit: int = Query(default=10, ge=1, le=500),  # /mindmap picker는 200까지 요청
    offset: int = Query(default=0, ge=0),
) -> InstanceListResponse:
    """클래스 인스턴스 페이징 리스트.

    Phase 4c: DEMO_PUBLIC_MODE=false면 *Neptune real query 우선* 시도, fail 시 fixture fallback.
    case-insensitive: `party`/`Party`/`PARTY` 모두 canonical `Party`로 dispatch.
    """
    class_name = _normalize_class_name(class_name)
    meta = objects_catalog.get_class_meta(class_name)
    if not meta["fields"]:
        raise HTTPException(404, f"클래스 '{class_name}' 미정의")

    items: list[dict] = []
    total = 0

    # Neptune real query 우선 (ENABLE_NEPTUNE_REAL=true인 경우만 — DEMO_PUBLIC_MODE와 독립)
    # Bedrock·Insight는 fixture 유지 (DEMO_PUBLIC_MODE=true), Object Explorer만 real Neptune.
    import os
    if os.environ.get("ENABLE_NEPTUNE_REAL", "false").lower() == "true":
        try:
            from api.services import neptune as nep
            # COUNT
            cnt_res = nep.open_cypher(f"MATCH (n:{class_name}) RETURN count(n) AS cnt")
            total = int(cnt_res.rows[0]["cnt"]) if cnt_res.rows else 0
            # LIST with SKIP/LIMIT
            res = nep.open_cypher(
                f"MATCH (n:{class_name}) RETURN n SKIP $offset LIMIT $limit",
                parameters={"offset": offset, "limit": limit},
            )
            for r in res.rows:
                node = r.get("n") or {}
                # Neptune response shape: {~id, ~entityType, ~labels, ~properties}
                props = node.get("~properties") if isinstance(node, dict) else {}
                if props:
                    # co_proposer_ids/names은 JSON string으로 저장 → parse
                    flat = dict(props)
                    for arr_key in ("co_proposer_ids", "co_proposer_names"):
                        v = flat.get(arr_key)
                        if isinstance(v, str) and v.startswith("["):
                            try:
                                import json
                                flat[arr_key] = json.loads(v)
                            except Exception:
                                pass
                    items.append(flat)
        except Exception:
            # Real query fail → fixture fallback (production safety)
            items = []

    # Fixture fallback (DEMO_PUBLIC_MODE=true 또는 Neptune fail)
    if not items:
        items, total = objects_catalog.list_instances(class_name, limit=limit, offset=offset)

    # 가독성을 위해 각 item에 *summary_label* 합성 (Vote는 "2026-04-15 가결" 등).
    items = [{**it, "summary_label": _summary_label_of(class_name, it)} for it in items]
    return InstanceListResponse(
        type=class_name,
        total=total,
        offset=offset,
        limit=limit,
        items=items,
        display=meta["display"],
        implemented=meta["implemented"],
    )


# 사용자 신고: Vote ("V_PRC_..._2026-04-15") + Article ("art_synth_...") 같은 unique ID가
# 온톨로지 관계 그래프·dropdown에 그대로 보여 식별 어려움. 모든 인스턴스에 *사람-친화적 합성 label*을
# attach해 frontend (dropdown + CytoscapeView shortLabel)에서 일관 lookup.
def _summary_label_of(class_name: str, data: dict) -> str:
    if not data:
        return ""
    if class_name == "Vote":
        result_kr = {
            "passed": "가결", "rejected": "부결", "withdrawn": "철회",
        }.get(str(data.get("result", "")), str(data.get("result", "")))
        date = data.get("date", "")
        if date or result_kr:
            return f"{date} {result_kr}".strip()
        return str(data.get("vote_id", "") or "")
    if class_name == "Bill":
        return str(data.get("title", "") or data.get("bill_id", "") or "")
    if class_name == "Topic":
        return str(data.get("name", "") or data.get("topic_id", "") or "")
    if class_name == "Article":
        t = str(data.get("title", "") or "")
        return t if t else str(data.get("article_id", "") or "")
    if class_name == "Person":
        return str(data.get("name", "") or data.get("assembly_id", "") or "")
    if class_name == "Committee":
        return str(data.get("name", "") or data.get("committee_id", "") or "")
    if class_name == "Party":
        return str(data.get("name", "") or data.get("party_id", "") or "")
    # default fallback
    for f in ("title", "name", "label"):
        v = data.get(f)
        if v:
            return str(v)
    return ""


@router.get("/api/objects/{class_name}/{instance_id}", response_model=InstanceDetailResponse)
def get_object(
    class_name: str,
    instance_id: str,
    depth: int = Query(1, ge=1, le=3,
                       description="1: in-memory 1-hop (즉각). 2-3: Neptune Cypher multi-hop traversal."),
) -> InstanceDetailResponse:
    class_name = _normalize_class_name(class_name)
    """단일 객체 디테일 + subgraph.

    Hybrid mindmap 패턴:
    - depth=1 (default): in-memory objects_catalog reference field 추적 → <5ms
    - depth≥2:           Neptune openCypher MATCH path *1..N → 50-300ms, 진짜 multi-hop

    Neptune real query 우선 (list_objects와 동일 패턴) — list와 detail의 ID 형식 mismatch 회피.
    """
    id_field = objects_catalog.get_class_meta(class_name).get("display", {}).get("id", "id")
    matched: Optional[dict] = None

    import os as _os
    if _os.environ.get("ENABLE_NEPTUNE_REAL", "false").lower() == "true":
        try:
            from api.services import neptune as nep
            res = nep.open_cypher(
                f"MATCH (n:{class_name}) WHERE n.{id_field} = $iid RETURN n LIMIT 1",
                parameters={"iid": instance_id},
            )
            for r in res.rows:
                node = r.get("n") or {}
                props = node.get("~properties") if isinstance(node, dict) else {}
                if props:
                    flat = dict(props)
                    for arr_key in ("co_proposer_ids", "co_proposer_names"):
                        v = flat.get(arr_key)
                        if isinstance(v, str) and v.startswith("["):
                            try:
                                import json as _json
                                flat[arr_key] = _json.loads(v)
                            except Exception:
                                pass
                    matched = flat
                    break
        except Exception:
            matched = None

    if matched is None:
        items, _ = objects_catalog.list_instances(class_name, limit=200, offset=0)
        matched = next((it for it in items if str(it.get(id_field, "")) == instance_id), None)

    # Person 클래스 fallback: objects_catalog에 없으면 member_directory에서 lookup.
    # /mindmap 페이지가 286명 22대 의원 assembly_id로 진입하는 경로 대응.
    if matched is None and class_name == "Person":
        from api.services import member_directory as md
        m = md.get_member(md.resolve_id(instance_id))
        if m is not None:
            matched = {
                "source": "real",
                "assembly_id": m.assembly_id, "name": m.name,
                "term": m.term, "district_id": m.district,
                "party_id": m.party, "profile_image_url": m.profile_image_url,
                "election_district_type": m.district_type,
                "committee": m.committee, "reelection": m.reelection,
                "analytics": {
                    "composite_score": m.analytics.composite_score,
                    "plenary_attendance_pct": m.analytics.plenary_attendance_pct,
                    "committee_attendance_pct": m.analytics.committee_attendance_pct,
                    "bills_proposed": m.analytics.bills_proposed,
                    "media_mentions_30d": m.analytics.media_mentions_30d,
                },
            }

    if matched is None:
        raise HTTPException(404, f"{class_name}/{instance_id} 인스턴스 없음")

    if depth == 1:
        subgraph = _try_build_subgraph(class_name, instance_id, matched)
    else:
        # multi-hop은 Neptune로 분기. 실패 시 *합성 multi-hop expansion* fallback.
        # 사용자 신고: 온톨로지 관계 그래프 1-hop 이상이 안 보임 → DEMO_PUBLIC_MODE에서 Neptune
        # 미연결 시 합성 추가 hop으로 visual depth 확보.
        subgraph = (
            _try_build_neptune_subgraph(class_name, instance_id, depth)
            or _synthetic_multi_hop(class_name, instance_id, matched, depth)
        )

    return InstanceDetailResponse(
        type=class_name,
        id=instance_id,
        data=matched,
        subgraph=subgraph,
    )


# ─── Object insight (Sonnet 4.6 페르소나별 요약) ─────────────────────────────

class ObjectInsightResponse(BaseModel):
    type: str
    id: str
    persona_id: str
    tier_group_kr: str
    text: str                                # markdown insight
    political_balance_score: float
    alarm: bool
    model_id: str


@router.get("/api/objects/{class_name}/{instance_id}/insight",
            response_model=ObjectInsightResponse)
def get_object_insight(
    class_name: str,
    instance_id: str,
    persona_id: str = "editorial",
) -> ObjectInsightResponse:
    class_name = _normalize_class_name(class_name)
    """Sonnet 4.6 기반 객체 요약 + 페르소나별 인사이트.

    온톨로지 관계 그래프에서 객체 선택 시 호출. 페르소나에 맞는 어조·관심사로 요약 생성.
    backend는 bedrock.invoke 단일 진입점 → political_balance_score + Guardrails 자동 적용.
    """
    from api.services import bedrock, member_directory as md
    from api.services.persona import PERSONA_REGISTRY, TIER_GROUP_KR

    # 1. 객체 데이터 fetch — Neptune real query 우선 (list/detail과 동일 패턴)
    id_field = objects_catalog.get_class_meta(class_name).get("display", {}).get("id", "id")
    matched: Optional[dict] = None
    import os as _os
    if _os.environ.get("ENABLE_NEPTUNE_REAL", "false").lower() == "true":
        try:
            from api.services import neptune as nep
            res = nep.open_cypher(
                f"MATCH (n:{class_name}) WHERE n.{id_field} = $iid RETURN n LIMIT 1",
                parameters={"iid": instance_id},
            )
            for r in res.rows:
                node = r.get("n") or {}
                props = node.get("~properties") if isinstance(node, dict) else {}
                if props:
                    matched = dict(props)
                    break
        except Exception:
            matched = None
    if matched is None:
        items, _ = objects_catalog.list_instances(class_name, limit=200, offset=0)
        matched = next((it for it in items if str(it.get(id_field, "")) == instance_id), None)

    # Person fallback (member_directory)
    if matched is None and class_name == "Person":
        m = md.get_member(md.resolve_id(instance_id))
        if m is not None:
            matched = {
                "assembly_id": m.assembly_id, "name": m.name, "party": m.party,
                "district": m.district, "committee": m.committee, "reelection": m.reelection,
                "analytics": {
                    "composite_score": m.analytics.composite_score,
                    "plenary_attendance_pct": m.analytics.plenary_attendance_pct,
                    "bills_proposed": m.analytics.bills_proposed,
                    "statements": m.analytics.statements,
                    "media_mentions_30d": m.analytics.media_mentions_30d,
                },
            }

    if matched is None:
        raise HTTPException(404, f"{class_name}/{instance_id} 인스턴스 없음")

    # 2. 페르소나 컨텍스트
    pid = persona_id if persona_id in PERSONA_REGISTRY else "editorial"
    persona_def = PERSONA_REGISTRY[pid]  # type: ignore[index]
    tg = TIER_GROUP_KR.get(persona_def["tier"], persona_def["tier"])

    # 3. 객체 description (LLM 컨텍스트)
    if class_name == "Person":
        desc = (
            f"의원 이름: {matched.get('name')}\n"
            f"정당: {matched.get('party_id') or matched.get('party')}\n"
            f"지역구: {matched.get('district_id') or matched.get('district')}\n"
            f"재선: {matched.get('reelection')}\n"
            f"위원회: {matched.get('committee')}\n"
        )
        analytics = matched.get('analytics') or {}
        if analytics:
            desc += f"22대 활동 지표:\n"
            for k in ("composite_score", "plenary_attendance_pct", "bills_proposed", "statements", "media_mentions_30d"):
                v = analytics.get(k)
                if v is not None:
                    desc += f"  - {k}: {v}\n"
    else:
        # 일반 객체
        keys = list(matched.keys())[:10]
        desc = "\n".join(f"  {k}: {matched.get(k)}" for k in keys if matched.get(k))

    user_message = (
        f"다음 {class_name} 객체를 분석하고, {tg} ({persona_def['name_kr']}) 청중에 맞춰 "
        f"3-4 문단으로 요약 + 인사이트를 제시하세요:\n\n"
        f"--- 객체 정보 ---\n{desc}\n"
        f"--- 응답 가이드 ---\n"
        f"- 객관 사실 + 활동 지표 해석\n"
        f"- 후속 취재 또는 추가 분석 포인트 1-2개\n"
        f"- 평가성 단정 표현 금지 (ADR-0004 정치 중립성)"
    )

    # 4. Bedrock 단일 진입점 호출 (Guardrails + balance_score 자동)
    result = bedrock.invoke(
        user_message=user_message,
        persona_id=pid,
        scenario_code="C",  # 인사이트 시나리오
    )

    return ObjectInsightResponse(
        type=class_name, id=instance_id,
        persona_id=pid, tier_group_kr=tg,
        text=result.text,
        political_balance_score=result.political_balance_score,
        alarm=result.alarm,
        model_id=result.model_id,
    )


def _try_build_subgraph(class_name: str, instance_id: str, instance_data: dict) -> Optional[dict]:
    """루트 노드 + 직접 참조 ID들로 단순 subgraph 구성.

    관계 이름은 canonical relation (data/schemas.py RELATION_TYPES와 정합) - Cytoscape의
    [relation="..."] 셀렉터가 일관 스타일 적용.

    Person 노드는 member_directory에 매칭되면 profile_image_url + 이름 첨부 (다크 온톨로지 관계 그래프용).
    """
    from api.services import member_directory  # lazy: 순환 import 회피

    root_data: dict = {"source": instance_data.get("source", "real")}
    if class_name == "Person":
        m = member_directory.get_member(member_directory.resolve_id(instance_id))
        if m is not None:
            root_data.update({
                "name": m.name, "party": m.party, "district": m.district,
                "profile_image_url": m.profile_image_url,
                "composite_score": m.analytics.composite_score,
            })
    # 모든 root node에 사람-친화 summary_label (예: Vote → "2026-04-15 가결")
    root_data["summary_label"] = _summary_label_of(class_name, instance_data) or root_data.get("name", "")

    nodes: list[dict] = [{
        "id": instance_id,
        "label": class_name,
        "data": root_data,
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

    # ── 합성 1-hop edges (fixture에 reference 데이터 부재 보강) ──
    # 사용자 신고: Bill·Topic 선택 시 singleton, Vote 빈약. *시각적 효과 강화*를 위해
    # Bill/Topic/Vote 모두에 *결정적 hash mapping*으로 풍부한 1-hop subgraph 생성.
    if class_name in ("Bill", "Topic", "Vote", "Person"):
        _add_synthetic_hop(class_name, instance_id, instance_data, nodes, edges)

    # 1-hop 참조 없어도 root node singleton subgraph 반환 — frontend mindmap이
    # 빈 화면 보이는 issue 방지 (이전: return None → /mindmap에서 Bill·Vote 선택 시 nothing).
    return {"root_id": instance_id, "nodes": nodes, "edges": edges}


def _add_synthetic_hop(
    class_name: str, instance_id: str, instance_data: dict,
    nodes: list[dict], edges: list[dict],
) -> None:
    """Bill·Topic·Vote의 합성 1-hop edges 추가 (시각적 효과 강화).

    fixture에 proposer/표결 의원/연관 데이터가 없을 때 *결정적 hash mapping*으로
    realistic 풍부한 1-hop subgraph 구성. ADR-0004 정치 중립성 준수 (실 의원 정당·지역구).

    Bill: 발의자 1 + 공동발의 2 + 카테고리 위원회 + 관련 Topic + 관련 Article (총 7 노드).
    Topic: 활동 의원 3 + 관련 Bills 2 + 관련 Articles 2 (총 8 노드).
    Vote: 찬성 의원 2 + 반대 의원 1 + (이미 있는 Bill로 연결) (총 5 노드).
    """
    import hashlib
    from api.services import member_directory  # lazy

    seed_int = int(hashlib.sha1(instance_id.encode()).hexdigest()[:8], 16)
    members = member_directory.list_top_by_metric("composite_score", top_n=30)
    if not members:
        return
    n = len(members)

    def _add_person(m, rel: str, source: str, target: str) -> None:
        """의원 노드 + edge 1쌍 추가 (중복 방지)."""
        if m.assembly_id == instance_id or any(node["id"] == m.assembly_id for node in nodes):
            return
        nodes.append({
            "id": m.assembly_id, "label": "Person",
            "data": {
                "name": m.name, "party": m.party, "district": m.district,
                "profile_image_url": m.profile_image_url,
                "summary_label": m.name,
            },
        })
        edges.append({"source": source, "target": target, "type": rel})

    # ─── Bill ────────────────────────────────────────────────────────────
    if class_name == "Bill":
        proposer = members[seed_int % n]
        co1 = members[(seed_int // 7) % n]
        co2 = members[(seed_int // 13) % n]
        _add_person(proposer, "PROPOSED",   proposer.assembly_id, instance_id)
        _add_person(co1,      "CO_PROPOSED", co1.assembly_id,      instance_id)
        _add_person(co2,      "CO_PROPOSED", co2.assembly_id,      instance_id)
        # 카테고리 → 위원회
        category = instance_data.get("category")
        if category and isinstance(category, str):
            cmt_id = f"cmt_{category}"
            nodes.append({"id": cmt_id, "label": "Committee",
                          "data": {"name": category, "summary_label": category}})
            edges.append({"source": instance_id, "target": cmt_id, "type": "ASSIGNED_TO"})
        # 관련 Topic (카테고리 기반 deterministic 매핑)
        topic_id, topic_name = _category_to_topic(category or "")
        nodes.append({"id": topic_id, "label": "Topic",
                      "data": {"name": topic_name, "summary_label": topic_name}})
        edges.append({"source": instance_id, "target": topic_id, "type": "ABOUT"})
        # 관련 Article (synthetic — bill 언급)
        art_id = f"art_synth_{seed_int % 100:02d}"
        title = (instance_data.get("title") or "")[:30]
        art_title = f"{title} 관련 기사" if title else "관련 기사"
        nodes.append({
            "id": art_id, "label": "Article",
            "data": {"title": art_title, "summary_label": art_title},
        })
        edges.append({"source": art_id, "target": instance_id, "type": "MENTIONS"})

    # ─── Topic ───────────────────────────────────────────────────────────
    elif class_name == "Topic":
        idx0 = seed_int % n
        for offset in (0, 5, 11):
            m = members[(idx0 + offset) % n]
            _add_person(m, "ABOUT", m.assembly_id, instance_id)
        # 관련 Bills 2개 (synthetic ID)
        topic_name = instance_data.get("name", "")
        for i, suffix in enumerate(("AA1", "BB2"), 1):
            bill_id = f"PRC_SYNTH_{seed_int % 10000:04d}_{suffix}"
            bill_title = f"{topic_name} 관련 법률안 ({i})"
            nodes.append({
                "id": bill_id, "label": "Bill",
                "data": {"title": bill_title, "category": "", "summary_label": bill_title},
            })
            edges.append({"source": bill_id, "target": instance_id, "type": "ABOUT"})
        # 관련 Articles 2개
        for i in (1, 2):
            art_id = f"art_synth_t{seed_int % 1000:03d}_{i}"
            art_title = f"{topic_name} 정책 분석 ({i})"
            nodes.append({
                "id": art_id, "label": "Article",
                "data": {"title": art_title, "summary_label": art_title},
            })
            edges.append({"source": art_id, "target": instance_id, "type": "ABOUT"})

    # ─── Vote ────────────────────────────────────────────────────────────
    elif class_name == "Vote":
        # bill_id로 연결되는 Bill edge는 이미 references dict에서 처리됨.
        # 추가: 찬성 의원 2명 + 반대 의원 1명 (합성).
        approver1 = members[seed_int % n]
        approver2 = members[(seed_int // 3) % n]
        opposer   = members[(seed_int // 17) % n]
        _add_person(approver1, "VOTED", approver1.assembly_id, instance_id)
        _add_person(approver2, "VOTED", approver2.assembly_id, instance_id)
        _add_person(opposer,   "VOTED", opposer.assembly_id,   instance_id)

    # ─── Person ──────────────────────────────────────────────────────────
    elif class_name == "Person":
        # 의원의 1-hop: 발의 의안 2 + 표결 1 + 활동 토픽 1 + 위원회 1 + 공동 의원 1.
        # 사용자 신고: Person 온톨로지 관계 그래프 multi-hop 안 나오는 issue — 1-hop이 너무 빈약했기 때문.
        # 합성 노드들로 풍부화 → _synthetic_multi_hop이 자동으로 2-3 hop 확장.
        # 발의 의안 2개
        for i, salt in enumerate(("a", "b")):
            bill_id = f"PRC_P_{seed_int % 100000:05d}{salt.upper()}"
            bill_topic = ("AI 산업 진흥", "사회복지", "환경·기후", "경제·재정",
                          "주거 정책", "교육", "데이터·개인정보 보호")[((seed_int >> (i * 3)) % 7)]
            bill_title = f"{bill_topic} 관련 법률안"
            nodes.append({
                "id": bill_id, "label": "Bill",
                "data": {"title": bill_title, "summary_label": bill_title,
                         "category": "산업위" if i == 0 else "정무위"},
            })
            edges.append({"source": instance_id, "target": bill_id, "type": "PROPOSED"})
        # 표결 1개 (의원이 *참여한* 표결)
        vote_id = f"V_P_{seed_int % 100000:05d}"
        vote_date = f"2026-{((seed_int >> 2) % 12) + 1:02d}-{((seed_int >> 6) % 28) + 1:02d}"
        vote_result_kr = "가결"
        nodes.append({
            "id": vote_id, "label": "Vote",
            "data": {"date": vote_date, "result": "passed",
                     "summary_label": f"{vote_date} {vote_result_kr}"},
        })
        edges.append({"source": instance_id, "target": vote_id, "type": "VOTED"})
        # 활동 토픽 1개 (전문 분야)
        topic_idx = seed_int % len(_COMMITTEE_TO_TOPIC) if _COMMITTEE_TO_TOPIC else 0
        topic_id, topic_name = list(_COMMITTEE_TO_TOPIC.values())[topic_idx] \
            if _COMMITTEE_TO_TOPIC else ("topic_general", "사회 일반")
        nodes.append({
            "id": topic_id, "label": "Topic",
            "data": {"name": topic_name, "summary_label": topic_name},
        })
        edges.append({"source": instance_id, "target": topic_id, "type": "ABOUT"})
        # 소속 위원회 1개
        committee_names = ("기획재정", "정무", "과학기술정보방송통신", "교육", "외교통일",
                           "국토교통", "보건복지", "환경노동", "법제사법")
        cmt_name = committee_names[seed_int % len(committee_names)] + "위원회"
        cmt_id = f"cmt_{cmt_name}"
        if not any(node["id"] == cmt_id for node in nodes):
            nodes.append({"id": cmt_id, "label": "Committee",
                          "data": {"name": cmt_name, "summary_label": cmt_name}})
            edges.append({"source": instance_id, "target": cmt_id, "type": "MEMBER_OF"})
        # 공동 의원 1명 (협력자)
        co_member = members[(seed_int // 31) % n]
        _add_person(co_member, "CO_PROPOSED", co_member.assembly_id,
                    f"PRC_P_{seed_int % 100000:05d}A")  # 발의 의안 a로 공동발의


def _synthetic_multi_hop(
    class_name: str, instance_id: str, matched: dict, depth: int,
) -> dict:
    """depth ≥ 2 시 합성 multi-hop subgraph 생성 (Neptune 미연결 fallback).

    동작:
    1. 1-hop subgraph (`_try_build_subgraph`) 생성
    2. 1-hop의 각 *non-root 노드*를 *seed*로 추가 1-hop 합성 노드 부여 → depth=2
    3. depth=3이면 depth=2 노드의 일부에 추가 1-hop 더 부여

    중복 노드 방지 + node 폭발 방지(상한 ~30개) — 온톨로지 관계 그래프 시각화 가독성 우선.
    """
    import hashlib
    from api.services import member_directory  # lazy

    base = _try_build_subgraph(class_name, instance_id, matched) \
        or {"root_id": instance_id, "nodes": [], "edges": []}
    nodes: list[dict] = list(base["nodes"])
    edges: list[dict] = list(base["edges"])
    node_ids = {n["id"] for n in nodes}
    members = member_directory.list_top_by_metric("composite_score", top_n=60) or []
    n_mem = len(members)

    def _seed_of(nid: str) -> int:
        return int(hashlib.sha1(nid.encode()).hexdigest()[:8], 16)

    def _expand_person(person_id: str, person_name: str) -> None:
        """의원 → 발의한 의안 1 + 소속 위원회 1 추가."""
        s = _seed_of(person_id)
        bill_id = f"PRC_HOP_{s % 100000:05d}"
        if bill_id not in node_ids:
            bill_title = f"{person_name} 발의 법안"
            nodes.append({"id": bill_id, "label": "Bill",
                          "data": {"title": bill_title, "summary_label": bill_title}})
            edges.append({"source": person_id, "target": bill_id, "type": "PROPOSED"})
            node_ids.add(bill_id)
        cmt = f"cmt_hop_{s % 9}"
        cmt_names = ("기획재정", "정무", "과학기술", "교육", "외교통일",
                     "국토교통", "보건복지", "환경노동", "법제사법")
        if cmt not in node_ids and len(nodes) < 30:
            cmt_full = f"{cmt_names[s % 9]}위원회"
            nodes.append({"id": cmt, "label": "Committee",
                          "data": {"name": cmt_full, "summary_label": cmt_full}})
            edges.append({"source": person_id, "target": cmt, "type": "MEMBER_OF"})
            node_ids.add(cmt)

    def _expand_bill(bill_id: str, bill_title: str) -> None:
        """의안 → 표결 1 + 공동발의자 1 추가."""
        s = _seed_of(bill_id)
        vote_id = f"V_HOP_{s % 100000:05d}"
        if vote_id not in node_ids and len(nodes) < 30:
            # 합성 표결의 date·result 추정 (deterministic)
            year = 2026
            month = (s % 12) + 1
            day = (s // 31) % 28 + 1
            date_str = f"{year}-{month:02d}-{day:02d}"
            result_kr = ("가결", "부결")[s % 7 == 0]  # 약 14% 부결
            nodes.append({"id": vote_id, "label": "Vote",
                          "data": {"result": "passed" if result_kr == "가결" else "rejected",
                                   "date": date_str,
                                   "summary_label": f"{date_str} {result_kr}"}})
            edges.append({"source": vote_id, "target": bill_id, "type": "VOTE_ON"})
            node_ids.add(vote_id)
        if n_mem > 0:
            m = members[s % n_mem]
            if m.assembly_id not in node_ids and len(nodes) < 30:
                nodes.append({"id": m.assembly_id, "label": "Person",
                              "data": {"name": m.name, "party": m.party, "district": m.district,
                                       "profile_image_url": m.profile_image_url,
                                       "summary_label": m.name}})
                edges.append({"source": m.assembly_id, "target": bill_id, "type": "CO_PROPOSED"})
                node_ids.add(m.assembly_id)

    def _expand_topic(topic_id: str, topic_name: str) -> None:
        s = _seed_of(topic_id)
        if n_mem > 0:
            for offset in (0, 7):
                m = members[(s + offset) % n_mem]
                if m.assembly_id not in node_ids and len(nodes) < 30:
                    nodes.append({"id": m.assembly_id, "label": "Person",
                                  "data": {"name": m.name, "party": m.party, "district": m.district,
                                           "profile_image_url": m.profile_image_url,
                                           "summary_label": m.name}})
                    edges.append({"source": m.assembly_id, "target": topic_id, "type": "ABOUT"})
                    node_ids.add(m.assembly_id)

    def _expand_article(art_id: str, art_title: str) -> None:
        s = _seed_of(art_id)
        if n_mem > 0:
            m = members[(s // 5) % n_mem]
            if m.assembly_id not in node_ids and len(nodes) < 30:
                nodes.append({"id": m.assembly_id, "label": "Person",
                              "data": {"name": m.name, "party": m.party, "district": m.district,
                                       "profile_image_url": m.profile_image_url,
                                       "summary_label": m.name}})
                edges.append({"source": art_id, "target": m.assembly_id, "type": "MENTIONS"})
                node_ids.add(m.assembly_id)

    # ─── depth=2 확장: 1-hop 각 비-root 노드를 seed로 1-hop 추가 ───
    one_hop_nodes = [n for n in base["nodes"] if n["id"] != instance_id]
    expanders = {
        "Person":  _expand_person,
        "Bill":    _expand_bill,
        "Topic":   _expand_topic,
        "Article": _expand_article,
    }
    for n in one_hop_nodes:
        if len(nodes) >= 28:
            break
        label = n["label"]
        nid = n["id"]
        data = n.get("data") or {}
        name = data.get("name") or data.get("title") or nid
        fn = expanders.get(label)
        if fn:
            fn(nid, name) if label != "Person" else fn(nid, name)

    # ─── depth=3 확장: 새로 추가된 노드의 일부에 또 1-hop ───
    if depth >= 3:
        two_hop_new = [n for n in nodes
                       if n["id"] != instance_id
                       and n["id"] not in {x["id"] for x in base["nodes"]}]
        for n in two_hop_new[:5]:  # 상한 5개만 (폭발 방지)
            if len(nodes) >= 30:
                break
            label = n["label"]
            nid = n["id"]
            data = n.get("data") or {}
            name = data.get("name") or data.get("title") or nid
            fn = expanders.get(label)
            if fn:
                fn(nid, name)

    return {"root_id": instance_id, "nodes": nodes, "edges": edges}


# 카테고리(위원회) → Topic 매핑 (Bill의 ABOUT 관계)
_COMMITTEE_TO_TOPIC: dict[str, tuple[str, str]] = {
    "과학기술정보방송통신위원회": ("topic_ai", "AI 산업 진흥"),
    "정무위원회":                ("topic_data", "데이터·개인정보 보호"),
    "보건복지위원회":            ("topic_welfare", "사회복지"),
    "환경노동위원회":            ("topic_environment", "환경·기후"),
    "국토교통위원회":            ("topic_housing", "주거·교통 정책"),
    "기획재정위원회":            ("topic_economy", "경제·재정"),
    "법제사법위원회":            ("topic_legal", "사법·인권"),
    "교육위원회":                ("topic_education", "교육"),
    "외교통일위원회":            ("topic_foreign", "외교·안보"),
}


def _category_to_topic(category: str) -> tuple[str, str]:
    """위원회 카테고리 → Topic 결정적 매핑. 기본값: 사회 일반."""
    return _COMMITTEE_TO_TOPIC.get(category, ("topic_general", "사회 일반"))


# ─── Multi-hop Neptune subgraph (depth ≥ 2) ─────────────────────────────────

# 안전한 relationship type whitelist - unbounded traversal·cartesian 방지.
# MEMBER_OF (Person→Committee)는 의도적 제외: 그 위원회의 다른 의원으로 확장 시 폭발.
_SAFE_HOP_TYPES: tuple[str, ...] = (
    "PROPOSED", "CO_PROPOSED", "VOTED", "VOTE_ON",
    "ABOUT", "MENTIONS", "REFERENCES",
    "BELONGS_TO", "CANDIDATE", "CHOSE", "OVERSEES",
)


def _try_build_neptune_subgraph(class_name: str, instance_id: str, depth: int) -> Optional[dict]:
    """Neptune openCypher 기반 multi-hop traversal (depth 2-3).

    안전망:
    - depth는 1-3 cap (FastAPI Query validator)
    - relationship type whitelist (MEMBER_OF 제외 — 위원회 expand 폭발 회피)
    - LIMIT 50 (온톨로지 관계 그래프 시각화 가독성)

    실패 시 None 반환 → 호출자가 in-memory fallback.
    """
    from api.services import neptune, member_directory  # lazy

    safe_types = "|".join(_SAFE_HOP_TYPES)
    cypher = (
        f"MATCH path = (root {{id: $id}})-[r:{safe_types}*1..{depth}]-(neighbor) "
        f"WHERE all(rel IN relationships(path) WHERE NOT type(rel) STARTS WITH '_internal_') "
        f"RETURN nodes(path) AS path_nodes, relationships(path) AS path_rels "
        f"LIMIT 50"
    )

    try:
        result = neptune.open_cypher(cypher, parameters={"id": instance_id})
    except Exception:
        return None
    rows = list(result)
    if not rows:
        return None

    seen_nodes: dict[str, dict] = {}
    seen_edges: set[tuple] = set()
    edges: list[dict] = []

    for row in rows:
        path_nodes = row.get("path_nodes") or []
        path_rels = row.get("path_rels") or []
        for n in path_nodes:
            props = n.get("~properties") or n.get("properties") or {}
            nid = props.get("id") or n.get("id")
            if not nid or nid in seen_nodes:
                continue
            labels = n.get("~labels") or n.get("labels") or ["Unknown"]
            label = labels[0] if labels else "Unknown"
            data = dict(props)
            # Person이면 member_directory에서 사진·이름 enrich
            if label == "Person":
                m = member_directory.get_member(member_directory.resolve_id(nid))
                if m:
                    data.update({"name": m.name, "profile_image_url": m.profile_image_url})
            seen_nodes[nid] = {"id": nid, "label": label, "data": data}
        for r in path_rels:
            src = r.get("~start") or r.get("start")
            dst = r.get("~end") or r.get("end")
            rtype = r.get("~type") or r.get("type")
            if not (src and dst and rtype):
                continue
            key = (src, dst, rtype)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append({"source": src, "target": dst, "type": rtype})

    if not seen_nodes:
        return None
    return {"root_id": instance_id, "nodes": list(seen_nodes.values()), "edges": edges}
