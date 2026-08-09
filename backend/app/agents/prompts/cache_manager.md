# Cache Manager Agent

## LLM
- **모델**: 없음 (규칙 기반)
- **역할**: LLM 불필요. 캐시 정책은 TTL, LRU 등 규칙 기반 알고리즘으로 동작.

## 도구/라이브러리
- **aiocache**: 비동기 캐시 인터페이스 (Redis/메모리 백엔드)
- **diskcache**: 로컬 디스크 캐시 (대용량 이미지, 임시 파일)
- **redis-py**: 분산 캐시 백엔드

## 역할
시스템 전반의 데이터 캐싱을 관리하고, TTL 기반 만료 처리, 중복 데이터 제거, 스토리지 쿼터 관리 및 가비지 컬렉션을 수행하는 에이전트.

## 핵심 책임
1. 다계층 캐시 관리 (메모리 → Redis → 디스크)
2. TTL 기반 자동 만료 및 갱신
3. 캐시 키 중복 제거 (deduplication)
4. 스토리지 쿼터 관리 및 가비지 컬렉션
5. 캐시 히트율 모니터링 및 최적화

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `cache_get` | `key: str, namespace: str` | `CachedValue \| None` |
| `cache_set` | `key: str, value: Any, ttl: int, namespace: str` | `bool` |
| `cache_invalidate` | `pattern: str, namespace: str` | `int (삭제된 키 수)` |
| `run_gc` | `max_age: int, max_size_mb: int` | `GCResult(freed_mb, deleted_keys)` |
| `get_stats` | `namespace: Optional[str]` | `CacheStats(hit_rate, size, key_count)` |

## 의사결정 규칙
- 스크래핑 데이터 TTL: 1시간. 이미지 TTL: 24시간. LLM 응답 TTL: 6시간.
- 캐시 히트율이 70% 미만이면 TTL 정책 재조정 알림
- 디스크 캐시 500MB 초과 시 자동 GC 실행 (LRU 기반)
- Redis 메모리 80% 도달 시 낮은 우선순위 키부터 삭제
- 동일 요청이 5초 이내 반복되면 캐시 강제 사용 (thundering herd 방지)
