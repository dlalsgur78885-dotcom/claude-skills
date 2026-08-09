# Interaction Handler Agent

## LLM
- **모델**: 없음 (규칙 기반)
- **역할**: LLM 불필요. UI 인터랙션은 이벤트 핸들러와 규칙 기반으로 동작.

## 도구/라이브러리
- **@dnd-kit**: 드래그 앤 드롭 (슬라이드 재정렬, 에셋 드롭)
- **react-hotkeys-hook**: 키보드 단축키 바인딩 및 처리

## 역할
사용자의 드래그 앤 드롭, 키보드 단축키, 컨텍스트 메뉴, 제스처 등 UI 인터랙션을 시스템 명령으로 변환하고, 입력 유효성을 검증하는 에이전트.

## 핵심 책임
1. 키보드 단축키 매핑 및 실행
2. 드래그 앤 드롭 처리 (슬라이드 순서 변경, 에셋 배치)
3. 컨텍스트 메뉴 (우클릭) 액션 처리
4. 제스처 인식 (핀치 줌, 스와이프)
5. 입력 이벤트를 표준 커맨드로 변환

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `handle_shortcut` | `key_combo: string, context: EditorContext` | `Command` |
| `handle_drag_drop` | `source: DragItem, target: DropZone` | `Command` |
| `handle_context_menu` | `position: Point, selected: List[Element]` | `MenuItems[]` |
| `handle_gesture` | `gesture: GestureEvent` | `Command` |
| `register_shortcut` | `key_combo: string, command: string` | `void` |

## 의사결정 규칙
- `Ctrl+Z` = Undo, `Ctrl+Y` = Redo, `Ctrl+S` = 저장, `Delete` = 선택 요소 삭제
- `Ctrl+C/V` = 복사/붙여넣기 (캔버스 요소 단위)
- 드래그 중 5px 미만 이동은 클릭으로 처리 (오드래그 방지)
- 드래그 앤 드롭 시 스냅 가이드라인 표시 (8px 그리드)
- 다중 선택 시 `Shift+Click`, 전체 선택 시 `Ctrl+A`
- 포커스가 텍스트 입력에 있을 때 단축키 비활성화
