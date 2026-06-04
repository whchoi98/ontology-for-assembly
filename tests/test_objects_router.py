"""Object Explorer 라우터 검증 (Phase 5 Track 5-6)."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# ─── 메타 (ontology) ────────────────────────────────────────────────────────

def test_classes_meta_returns_31(client):
    r = client.get("/api/ontology/classes").json()
    assert r["total_classes"] == 31


def test_classes_meta_has_seven_groups(client):
    r = client.get("/api/ontology/classes").json()
    expected_groups = {"인물·조직", "입법", "주제·외부", "미디어", "독자 측", "광고", "분석 메타"}
    assert set(r["groups"].keys()) == expected_groups


def test_implemented_count(client):
    """Phase 5 polish 완료 - 31/31 dispatcher 모두 등록."""
    r = client.get("/api/ontology/classes").json()
    assert r["implemented_count"] == 31
    assert r["implemented_count"] == r["total_classes"]


def test_class_meta_for_bill(client):
    r = client.get("/api/ontology/Bill").json()
    assert r["name"] == "Bill"
    assert r["group"] == "입법"
    assert r["implemented"] is True
    field_names = {f["name"] for f in r["fields"]}
    assert "bill_id" in field_names
    assert "title" in field_names
    assert "status" in field_names


def test_class_meta_unknown_returns_404(client):
    r = client.get("/api/ontology/NonExistent")
    assert r.status_code == 404


# ─── 인스턴스 리스트 ────────────────────────────────────────────────────────

def test_list_bills(client):
    r = client.get("/api/objects/Bill?limit=5").json()
    assert r["type"] == "Bill"
    assert len(r["items"]) <= 5
    assert all("bill_id" in item for item in r["items"])


def test_list_persons(client):
    r = client.get("/api/objects/Person?limit=3").json()
    assert r["type"] == "Person"
    assert len(r["items"]) <= 3
    assert all("assembly_id" in item for item in r["items"])


def test_list_pagination(client):
    """offset + limit 페이징."""
    first = client.get("/api/objects/Person?limit=2&offset=0").json()
    second = client.get("/api/objects/Person?limit=2&offset=2").json()
    if first["total"] > 2 and second["items"]:
        first_ids = {item["assembly_id"] for item in first["items"]}
        second_ids = {item["assembly_id"] for item in second["items"]}
        assert first_ids.isdisjoint(second_ids)


def test_list_unknown_class_returns_404(client):
    r = client.get("/api/objects/NonExistent")
    assert r.status_code == 404


def test_list_implemented_flag_true(client):
    r = client.get("/api/objects/Bill").json()
    assert r["implemented"] is True


def test_list_all_31_classes_have_items(client):
    """Phase 5 polish - 31 클래스 모두 dispatcher 등록 + 1+ 인스턴스 반환."""
    all_classes = client.get("/api/ontology/classes").json()
    for group_classes in all_classes["groups"].values():
        for cls_meta in group_classes:
            cls_name = cls_meta["name"]
            r = client.get(f"/api/objects/{cls_name}?limit=2").json()
            assert r["implemented"] is True, f"{cls_name}: implemented=False"
            assert len(r["items"]) >= 1, f"{cls_name}: 0 items returned"


# ─── 단일 객체 디테일 ───────────────────────────────────────────────────────

def test_get_single_bill(client):
    # 먼저 리스트로 ID 알아내기
    list_resp = client.get("/api/objects/Bill?limit=1").json()
    bill_id = list_resp["items"][0]["bill_id"]
    r = client.get(f"/api/objects/Bill/{bill_id}").json()
    assert r["type"] == "Bill"
    assert r["id"] == bill_id
    assert r["data"]["bill_id"] == bill_id


def test_get_single_person_detail_has_photo(client):
    """Person 상세 data.profile_image_url 이 채워져야 함 (상단 detail-card 사진).

    회귀 방지: objects_catalog 경로(_list_persons → fetch_members)는
    profile_image_url=None이므로, 핸들러가 subgraph(_try_build_subgraph)와 동일하게
    member_directory(국회 공식 사진 URL)로 enrich해야 한다. 누락 시 상단 detail-card가
    이니셜 글자 placeholder만 노출 — ADR-0004 "회색 placeholder 금지" 위반 (사용자 신고
    2026-06-04: /objects/Person/{id} 상단 박스 "초"/"조" 텍스트만 출력).
    """
    lst = client.get("/api/objects/Person?limit=1").json()
    assert lst["items"], "Person 인스턴스 없음"
    pid = lst["items"][0]["assembly_id"]
    r = client.get(f"/api/objects/Person/{pid}").json()
    photo = r["data"].get("profile_image_url")
    assert isinstance(photo, str) and photo.startswith("https://"), (
        f"profile_image_url 누락 → 상단 detail-card 이니셜 placeholder 노출: {photo!r}"
    )


def test_get_single_person_subgraph_when_party_id_exists(client):
    """Person에 party_id가 있으면 subgraph에 Party 노드 추가."""
    list_resp = client.get("/api/objects/Person?limit=10").json()
    person_with_party = next(
        (p for p in list_resp["items"] if p.get("party_id")), None,
    )
    if person_with_party is None:
        pytest.skip("party_id 있는 Person 없음")
    r = client.get(f"/api/objects/Person/{person_with_party['assembly_id']}").json()
    if r.get("subgraph"):
        node_labels = {n["label"] for n in r["subgraph"]["nodes"]}
        assert "Party" in node_labels


def test_get_unknown_instance_returns_404(client):
    r = client.get("/api/objects/Bill/nonexistent_id_xyz")
    assert r.status_code == 404


# ─── 다양한 클래스 통합 ─────────────────────────────────────────────────────

@pytest.mark.parametrize("cls", [
    # 인물·조직 (6)
    "Person", "Party", "Staff", "Committee", "District", "Term",
    # 입법 (7)
    "Bill", "Law", "Amendment", "Vote", "Statement", "Session", "Budget",
    # 주제·외부 (6)
    "Topic", "Policy", "Agency", "ElectionResult", "PollResult", "SocialSignal",
    # 미디어 (2)
    "Article", "Tag",
    # 독자 측 (5)
    "Reader", "ReaderProfile", "SubscriptionTier", "ReadingEvent", "Bookmark",
    # 광고 (4)
    "Advertisement", "AdInventory", "AdImpression", "AdMatchDecision",
    # 분석 메타 (1)
    "Cluster",
])
def test_list_each_implemented_class_returns_items(client, cls):
    """31 클래스 모두 인스턴스 조회 가능 (Phase 5 polish 완료)."""
    r = client.get(f"/api/objects/{cls}?limit=3").json()
    assert r["type"] == cls
    assert r["implemented"] is True
    assert len(r["items"]) >= 1


# ─── 유효성 ────────────────────────────────────────────────────────────────

def test_limit_out_of_range_rejected(client):
    r = client.get("/api/objects/Bill?limit=200")
    assert r.status_code == 422


def test_offset_negative_rejected(client):
    r = client.get("/api/objects/Bill?offset=-1")
    assert r.status_code == 422
