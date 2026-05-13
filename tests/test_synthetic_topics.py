"""data.synthetic.topics 카탈로그 검증."""
from __future__ import annotations

from data.synthetic import topics
from data.schemas import Topic


def test_twenty_five_topics_registered():
    """spec 25개 토픽."""
    assert len(topics.TOPIC_SEEDS) == 25


def test_topic_ids_unique():
    ids = topics.list_topic_ids()
    assert len(ids) == len(set(ids))


def test_topic_id_index_lookup():
    """get() 으로 ID lookup."""
    assert topics.get("topic_ai") is not None
    assert topics.get("topic_ai").name == "AI 산업 진흥"


def test_unknown_topic_returns_none():
    assert topics.get("nonexistent") is None


def test_all_topics_have_keywords():
    for t in topics.TOPIC_SEEDS:
        assert t.keywords, f"{t.id}: keywords 누락"


def test_topics_no_ideology_labels():
    """ADR-0004 - 토픽 name·category·keywords에 이념 라벨 금지."""
    forbidden = {"보수", "진보", "좌파", "우파", "중도"}
    for t in topics.TOPIC_SEEDS:
        for label in forbidden:
            assert label != t.name
            assert label != t.category
            for kw in t.keywords:
                assert label != kw, f"{t.id} keyword '{kw}'에 이념 라벨"


def test_to_graph_nodes_returns_pydantic_topics():
    nodes = topics.to_graph_nodes()
    assert len(nodes) == 25
    assert all(isinstance(n, Topic) for n in nodes)
    assert all(n.source == "synthetic" for n in nodes)


def test_to_graph_nodes_custom_source():
    nodes = topics.to_graph_nodes(source="real")
    assert all(n.source == "real" for n in nodes)


def test_categories_present():
    cats = topics.list_categories()
    # 최소 5개 카테고리 (다양성)
    assert len(cats) >= 5
    assert "산업" in cats
    assert "사회" in cats
