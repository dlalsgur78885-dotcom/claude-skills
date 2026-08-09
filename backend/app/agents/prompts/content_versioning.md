# Content Versioning Agent

## LLM
- **모델**: 없음 (규칙 기반)
- **역할**: LLM 불필요. 버전 관리는 diff 알고리즘과 스냅샷 기반으로 동작.

## 도구/라이브러리
- **deepdiff**: Python 객체/JSON 간 심층 비교 (diff 생성)
- **jsonpatch**: RFC 6902 JSON Patch 적용 (부분 업데이트, 롤백)

## 역할
캐러셀 프로젝트의 자동 저장, 버전 스냅샷 생성, 버전 간 비교(diff), 롤백, 분기(variation) 생성을 관리하는 에이전트.

## 핵심 책임
1. 자동 저장 (주기적 스냅샷 생성)
2. 수동 버전 스냅샷 생성 (사용자 요청)
3. 버전 간 diff 비교 (변경 사항 시각화)
4. 특정 버전으로 롤백
5. 버전에서 분기(variation) 생성

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `create_snapshot` | `project_id: str, label: Optional[str]` | `Snapshot(version, timestamp, label)` |
| `list_versions` | `project_id: str, limit: int` | `List[Snapshot]` |
| `diff_versions` | `project_id: str, v1: int, v2: int` | `DiffResult(changes, additions, deletions)` |
| `rollback` | `project_id: str, target_version: int` | `Snapshot (복원됨)` |
| `create_variation` | `project_id: str, base_version: int, name: str` | `Project(new_id, copied_from)` |
| `auto_save` | `project_id: str, data: dict` | `Snapshot` |

## 의사결정 규칙
- 자동 저장: 30초마다 변경 감지 시 스냅샷 생성
- 자동 스냅샷은 최대 100개 보존. 초과 시 오래된 것부터 삭제 (수동 스냅샷 제외).
- diff가 비어있으면 (변경 없음) 스냅샷 생성 스킵
- 롤백 시 현재 상태를 자동으로 스냅샷 저장 후 복원 (안전장치)
- 수동 스냅샷은 삭제 불가 (사용자가 직접 삭제해야 함)
