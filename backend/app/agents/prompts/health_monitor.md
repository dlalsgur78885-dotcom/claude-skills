# Health Monitor Agent

## LLM
- **모델**: 없음 (규칙 기반)
- **역할**: LLM 불필요. 모니터링은 메트릭 수집과 임계값 기반 규칙으로 동작.

## 도구/라이브러리
- **prometheus-client**: 메트릭 수집 및 Prometheus 포맷 노출
- **OpenTelemetry**: 분산 트레이싱 및 로그 상관관계 분석

## 역할
전체 에이전트 시스템의 상태를 실시간 모니터링하고, 지연/에러/병목을 감지하며, SLA 위반 시 경고를 발생시키는 에이전트.

## 핵심 책임
1. 에이전트별 응답 시간, 성공률, 처리량 수집
2. 시스템 리소스 모니터링 (CPU, 메모리, 디스크)
3. 병목 지점 자동 탐지
4. SLA 임계값 위반 시 경고 발생
5. 분산 트레이싱으로 요청 전체 경로 추적

## 사용 가능한 액션
| 액션 | 파라미터 | 출력 |
|------|---------|------|
| `get_agent_metrics` | `agent_name: str, period: str` | `AgentMetrics(latency_p50, latency_p99, success_rate, throughput)` |
| `get_system_health` | (없음) | `SystemHealth(cpu, memory, disk, status)` |
| `detect_bottleneck` | (없음) | `List[Bottleneck(agent, metric, value)]` |
| `check_sla` | `sla_config: SLAConfig` | `SLAReport(violations, at_risk)` |
| `get_trace` | `request_id: str` | `Trace(spans, duration, errors)` |
| `set_alert` | `metric: str, threshold: float, action: str` | `AlertRule(id)` |

## 의사결정 규칙
- 에이전트 응답 시간 P99 > 5초이면 경고
- 성공률 95% 미만이면 긴급 알림
- CPU 80% 이상 지속 5분이면 스케일링 제안
- 메모리 90% 이상이면 캐시 GC 트리거 (`cache_manager` 호출)
- 디스크 90% 이상이면 임시 파일 정리 및 알림
- 메트릭 수집 주기: 15초. 집계 주기: 1분.
