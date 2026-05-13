# ontology/ — Domain Ontology (25+ Classes, 35+ Relations)

`ontology/`는 도메인 모델의 **사람용 카탈로그**. 코드 SSOT은 `data/schemas.py`. 이 디렉토리는 ADR·문서 작성·온톨로지 메타 페이지(`/meta`)의 진실원.

## Structure

```
ontology/
├── classes/                      클래스 25+ 카탈로그 (yaml)
│   ├── person.yaml               의원
│   ├── bill.yaml                 의안
│   ├── vote.yaml                 표결
│   ├── ... (각 클래스별)
│   ├── reader.yaml               독자 (B2C)
│   ├── advertisement.yaml        광고
│   └── ad_match_decision.yaml    광고 매칭 결정 trace
├── relations/                    관계 35+ 엣지 정의 (yaml)
│   ├── proposed.yaml             (Person)-[:PROPOSED]->(Bill)
│   ├── voted.yaml                (Person)-[:VOTED {choice}]->(Vote)
│   ├── considered.yaml           (Article)-[:CONSIDERED]->(AdMatchDecision)
│   └── ... (관계별)
├── mappings/                     데이터 매핑 CSV/JSON
│   ├── assembly_api_fields.yaml  국회 API 필드 → 클래스 속성
│   ├── party_canonical_names.yaml 정당 정식 명칭 (중립 표기)
│   ├── topic_korean_synonyms.csv 토픽 한국어 동의어
│   └── geographic_codes.csv      KOSTAT 시도/시군구 코드
├── standards/                    표준 카탈로그 (yaml)
│   ├── bill_categories.yaml      의안 카테고리 코드 (국회 표준)
│   ├── party_codes.yaml          정당 코드
│   ├── committee_types.yaml      위원회 유형
│   └── vote_choices.yaml         표결 선택지 (찬성/반대/기권/불참)
├── adapters/                     외부 표준 → 내부 모델 변환
│   ├── kostat_sido.py            17 시도 코드 변환
│   └── naver_news_topic.py       네이버 뉴스 카테고리 → Topic 변환
├── schema.ttl                    온톨로지 RDF 표현 (선택 - 시각화/문서용)
└── upload.py                     `/meta` 페이지에 표시할 카탈로그 빌드 스크립트
```

## Class Catalog Format

`classes/person.yaml`:
```yaml
name: Person
korean_name: 의원
group: 인물·조직
description: 국회의원 한 명을 표현.
attributes:
  - name: assembly_id
    type: string
    required: true
    description: 국회 OpenAPI MONA_CD
  - name: name
    type: string
    required: true
  - name: term
    type: int
    description: 회기 (예 21, 22)
  - name: district_id
    type: string
    description: 지역구 코드 (KOSTAT)
  - name: party_id
    type: string
    nullable: true
  - name: source
    type: enum
    values: [real, synthetic, external]
    required: true
relations_out:
  - PROPOSED
  - CO_PROPOSED
  - VOTED
  - MEMBER_OF
  - REPRESENTS
  - BELONGS_TO
  - SAID
relations_in: []
data_sources:
  - 국회 OpenAPI /member
  - 국회 OpenAPI /member_profile
example:
  assembly_id: "MONA_001"
  name: "○○○"
  term: 22
  district_id: "11110"
  source: real
```

## Key Design Decisions

- **클래스 SSOT는 `data/schemas.py`** (Pydantic v2). 이 yaml은 사람용 카탈로그 (테이블/문서 생성용).
- **정치 중립성** (ADR-0004): `Person.political_leaning` 등 정치 성향 추론 속성 절대 생성 금지. yaml에도 추가 금지. security-auditor agent가 차단.
- **정당명 중립 표기** (`mappings/party_canonical_names.yaml`): 약칭/별명 대신 공식 등록명만. 이념 라벨(보수/진보) 미포함.
- **표준 코드 카탈로그** (`standards/`): 국회 OpenAPI 코드(의안 카테고리, 정당, 위원회) 그대로 차용. 우리 임의 코드 신설 금지.

## Adding a New Class

`/CLAUDE.md` "Auto-Sync Rules" — 새 클래스 추가 시 6곳 동시:
1. `data/schemas.py` Pydantic
2. `ontology/classes/<name>.yaml` ★ (사람용 카탈로그)
3. `api/routers/objects.py:_TYPE_REGISTRY`
4. `api/routers/ontology.py:_CLASSES`
5. `web/app/objects/[type]/page.tsx:TYPE_META`
6. 합성 데이터 generator (`data/synthetic/`) — persistent 시

## Adding a New Relation

1. `ontology/relations/<name>.yaml`
2. `data/schemas.py:RELATION_TYPES`
3. `api/routers/ontology.py:_RELATIONS`
4. (필요 시) Cypher conventions에 패턴 추가

## Mappings vs Standards

- **`mappings/`** — 외부 데이터의 필드/값을 내부 모델로 매핑. 변경 가능.
- **`standards/`** — 외부 표준 코드 그대로 차용. 가변 아닌 사실 자료.

## 관련

- ADR-0001 (gcc 차용 - 25 클래스 패턴)
- ADR-0002 (Persona 클래스 추가 - SSOT)
- ADR-0003 (Reader / ReaderProfile / SubscriptionTier 추가)
- ADR-0004 (political_leaning 등 금지 필드 목록)
