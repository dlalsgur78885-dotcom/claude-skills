# Notification Agent

## LLM
- **모델**: 없음 (규칙 기반)
- **역할**: LLM 불필요. 알림 표시는 이벤트 타입에 따른 규칙 기반 매핑.

## 도구/라이브러리
- **sonner**: Toast 알림 라이브러리 (성공, 에러, 정보, 경고)

## 역할
사용자에게 토스트 알림, 진행 상태, 에러 메시지, 온보딩 팁 등을 적시에 전달하고, 활동 로그를 관리하는 에이전트.

## 핵심 책임
1. 이벤트별 적절한 토스트 알림 표시
2. 장기 작업 진행률 표시 (프로그레스 바)
3. 에러 메시지 사용자 친화적 변환
4. 활동 로그 기록 및 조회
5. 알림 중복 방지 및 우선순위 관리

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `show_toast` | `message: string, type: "success"\|"error"\|"info"\|"warning", duration: number` | `ToastId` |
| `show_progress` | `task_id: string, label: string, percent: number` | `ProgressId` |
| `update_progress` | `progress_id: string, percent: number` | `void` |
| `dismiss` | `toast_id: string` | `void` |
| `get_activity_log` | `limit: number, offset: number` | `List[ActivityEntry]` |

## 의사결정 규칙
- 성공 알림: 3초 후 자동 닫힘 (초록)
- 에러 알림: 수동 닫기 필요 (빨강), 액션 버튼 포함 가능
- 경고 알림: 5초 후 자동 닫힘 (노랑)
- 동일 메시지가 2초 이내 반복되면 중복 무시
- 동시 토스트 최대 3개. 초과 시 큐에 대기.
- 진행률 100% 도달 시 자동으로 성공 토스트로 전환
