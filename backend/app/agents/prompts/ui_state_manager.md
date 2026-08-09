# UI State Manager Agent

## LLM
- **모델**: 없음 (규칙 기반)
- **역할**: LLM 불필요. 프론트엔드 상태 관리는 순수 규칙 기반으로 동작. 백엔드 LLM 호출 없이 클라이언트에서 실행.

## 도구/라이브러리
- **zustand**: 경량 React 상태 관리 라이브러리 (전역 스토어)
- **zundo**: zustand 기반 Undo/Redo 미들웨어
- **immer**: 불변 상태 업데이트 헬퍼

## 역할
프론트엔드 에디터의 상태를 중앙 관리하고, Undo/Redo 스택을 운영하며, 컴포넌트 간 상태 동기화와 localStorage 기반 영속성을 제공하는 에이전트.

## 핵심 책임
1. Fabric.js 캔버스 상태 중앙 관리
2. Undo/Redo 스택 운영 (최대 50단계)
3. 컴포넌트 간 상태 동기화 (슬라이드 패널, 속성 패널 등)
4. localStorage 기반 자동 저장 및 복원
5. 상태 변경 이벤트 브로드캐스트

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `set_state` | `path: string, value: any` | `void` |
| `get_state` | `path: string` | `any` |
| `undo` | (없음) | `State (이전 상태)` |
| `redo` | (없음) | `State (다음 상태)` |
| `save_to_local` | (없음) | `boolean` |
| `restore_from_local` | `project_id: string` | `State` |
| `subscribe` | `path: string, callback: Function` | `Unsubscribe` |

## 의사결정 규칙
- 상태 변경은 모두 immer를 통한 불변 업데이트
- Undo/Redo 스택 50단계 초과 시 가장 오래된 항목 삭제
- localStorage 저장은 2초 debounce 후 실행 (성능 보호)
- 캔버스 객체 100개 초과 시 성능 경고 알림
- 상태 복원 실패 시 기본 상태로 초기화 후 사용자 알림
