# ADR-0010: 국회 OpenAPI Real Data Adapter Mapping

**Status**: Phase 4b (planned, 2026-05-20 정리)
**Context**: 2026-05-20 Phase 4a S3 + Neptune + OpenSearch 적재 검증 중 *adapter endpoint / field name mismatch* 발견. 사용자가 국회 열린데이터광장 OpenAPI 정확한 mapping을 제공.

## 핵심 포털

- **출발점**: 열린국회정보 OpenAPI (`https://open.assembly.go.kr/portal/openapi/main.do`)
- **인증**: 단일 API key (Secrets Manager `assembly/openapi-key`)
- **전체 API 목록**: `OPENSRVAPI` endpoint 호출 후 grep (UI 검색은 중복 표시 issue)

## 1) Proposer (발의자) — 핵심 구분

**제안자 ≠ 대표발의자 + 공동발의자**:
- `PROPOSER`: "강경숙의원 등 11인" (UI 표시용 문자열)
- `RST_PROPOSER`: 강경숙 (대표발의자, lead)
- `PUBL_PROPOSER`: "김재원, 백선희, 황운하, ..." (공동발의자 콤마 구분, co)

→ 그래프 엣지를 `lead` / `co` 두 타입으로 분리:
- `Legislator -[PROPOSED {type:'lead'}]-> Bill`
- `Legislator -[PROPOSED {type:'co'}]-> Bill`
- `Legislator -[CO_PROPOSED_WITH {count:N}]- Legislator` (PUBL_PROPOSER 파싱 → cohort 가중치)

### Endpoint 매핑

| 용도 | API | endpoint key | 필수인자 |
|---|---|---|---|
| 대표·공동발의 구분 | 국회의원 발의법률안 | `nzmimeepazxkubdpn` | AGE (22대) |
| 의안 메타·링크·종류 | 의안정보 통합 | `ALLBILL` | BILL_NO |
| 제안자 상세 | 의안 제안자정보 | `BILLINFOPPSR` | BILL_ID |
| 전체 의안 (예결산·결의안·청원 포함) | 의안 접수목록 | `BILLRCP` | AGE (22대 약 115,786건) |

**Scope 주의**: 의원 발의 법률안 10,139건 ≠ 전체 접수 115,786건. demo 안정성으로 *법률안 + 쟁점 N건*으로 좁히는 게 안전.

## 2) Vote (표결) — 함정 포인트

이름이 비슷한 두 API 중 **그래프 분석용은 후자**:

| API | granularity | 22대 건수 | 용도 |
|---|---|---|---|
| 의안별 표결현황 (`ncocpgfiaoituanbr`) | 의안 단위 (찬·반·기권·총수) | ~673건 | 대시보드 집계 |
| **국회의원 본회의 표결정보** | **의원 × 의안 단위 (개별 투표값)** | 의안수 × 의원수 | **그래프 분석 ← 필수** |

호출 패턴:
1. `nkalemivaqmoibxro` (본회의 처리안건_법률안) 또는 `nxjuyqnxadtotdrbw` (최근 본회의처리 의안) → 의안 ID 리스트
2. (의안 ID + MONA_CD) → 표결정보 → `Legislator -[VOTED {value:찬성|반대|기권|불참}]-> Bill`

## 3) Committee 연관

- `BILLCNTLAWCMIT` (위원회별 법률안)
- `BILLJUDGECONF` (위원회심사 회의정보)
- `BILLLWJUDGECONF` (법사위 회의정보 — 의안별 법사위 통과)

→ `Legislator -[MEMBER_OF]-> Committee -[REVIEWED]-> Bill`

## ID Key 정리

- `BILL_ID` / `BILL_NO` — 의안 식별자 (API마다 다름)
- `MONA_CD` — 의원 코드 (조인 키, member 어댑터 ↔ vote/proposer 연결)
- `AGE` / `DAESU` — 대수 (22대 등 필수인자)

## 권장 적재 순서 (Neptune 기준)

1. **국회의원 정보 통합** → `Legislator` 노드 (MONA_CD, 정당, 선거구, 위원회 매핑)
2. **국회의원 발의법률안** (`nzmimeepazxkubdpn`) → `Bill` 노드 + `PROPOSED(lead/co)` 엣지
3. **ALLBILL** → `Bill` 노드 속성 보강 (종류·링크·SUMMARY)
4. **본회의 처리안건** (`nkalemivaqmoibxro`) → 표결 대상 `Bill` 마킹
5. **국회의원 본회의 표결정보** → `VOTED {value: 찬성|반대|기권|불참}` 엣지

## 현재 코드 fix 필요 사항 (2026-05-20 적재 검증 기반)

### `data/real/bill.py:_row_to_bill`
- 현재: `row.get("BILL_NM", "")` → 빈 string
- **변경**: `row.get("BILL_NAME") or row.get("BILL_KIND_NM")` (정확 필드명 확인 필요)
- 현재 endpoint default: ? → `nzmimeepazxkubdpn` 권장
- `proposer_id` 매핑 추가: `RST_PROPOSER` (대표) + `PUBL_PROPOSER` parse (공동)

### `data/real/vote.py:_row_to_vote`
- 현재 endpoint `nojepdqqaweusdfbi` → **존재하지 않음**
- **변경**: 2-phase fetch
  1. `nkalemivaqmoibxro` → 의안 ID list
  2. (BILL_ID, MONA_CD) → 표결 row → `Vote` 엣지

### `data/real/committee.py`, `party.py`, `agency.py`, `session.py`
- 현재 endpoint들 (`npffdutiapkzbfyvr`, `nyozqwxvtfpfknpqz`, `nbslryaivedhrfyer`, `nktulghyaivebdpnz`) → ERROR-310 (서비스 미존재)
- **변경**: `BILLCNTLAWCMIT`, `BILLJUDGECONF` 등 위 표 참조

### `data/real/member.py:_row_to_member`
- 현재 `party_id` 필드 사용 → service code가 `party` field 사용 → mismatch
- **변경**: schema에서 `party_id` → `party`로 통일 또는 service에서 `m.party_id` 사용

## Demo 안정성 권장

- 22대 전체보다 **특정 회기 + 쟁점 법안 N건 (~100-500)**으로 scope 축소
- 의원 300 × 표결 600+건 = **엣지 18만+** → Bedrock agent 응답 시간 고려
- snapshot freeze (1회 적재 후 read-only) + Neptune cluster cache 활용

## 핵심 design 결정 (ADR로 승격)

**표결 데이터는 *의안별 표결현황 (`ncocpgfiaoituanbr`)* 이 아닌 *국회의원 본회의 표결정보* 사용한다 — granularity가 *의원 × 의안 단위*여야 그래프 분석 (클러스터링·라인업·당론 이탈 detection)이 가능.**

## Related ADRs

- ADR-0001 (gcc 패턴 차용 — Bulk Loader, source 태깅)
- ADR-0004 (정치 중립성 — 표결 분석 시 정파 단정 표현 차단)
- ADR-0010 (본 ADR — real data adapter mapping)

## References

- 사용자 제공 자료 (2026-05-20 conversation): 국회 OpenAPI proposer + vote endpoint 매핑
- velog 정리: (실전 정보 source, velog.io에서 검색)
- 국회 열린데이터광장 OpenAPI: https://open.assembly.go.kr
