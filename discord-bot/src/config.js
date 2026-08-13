import 'dotenv/config';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(here, '..');
export const DATA_DIR = path.join(ROOT, 'data');

function required(name) {
  const value = (process.env[name] || '').trim();
  if (!value) throw new Error(`${name} 이(가) .env 에 없습니다.`);
  return value;
}

/** "채널ID:사용자명:비밀번호;..." → Map<채널ID, {username, password}>
 *
 *  채널로 계정을 가른다(#트립앤라이프 → junhyeok, #이솔희 → solhee). 사용자로
 *  가르지 않는 이유: 한 사람이 두 브랜드를 다 다루므로, 방을 옮기는 쪽이 자연스럽다.
 *
 *  ⚠ 이 앱은 소유자 스코프다 — 채널·템플릿·캐러셀이 전부 user_id 로 걸러진다.
 *    계정을 잘못 잡으면 보이는 채널 자체가 달라지고(49개 vs 24개), 봇이 만든 결과가
 *    직원 대시보드에 안 보인다. 그래서 매핑이 이 봇의 첫 단추다.
 */
function parseChannelAccounts(raw) {
  const map = new Map();
  for (const entry of String(raw || '').split(';')) {
    const trimmed = entry.trim();
    if (!trimmed) continue;
    // 비밀번호에 ':' 이 있을 수 있으므로 앞 두 개만 자른다.
    const first = trimmed.indexOf(':');
    const second = trimmed.indexOf(':', first + 1);
    if (first < 1 || second < 0) {
      throw new Error(`CHANNEL_ACCOUNTS 항목 형식이 잘못됐습니다: ${trimmed}`);
    }
    const channelId = trimmed.slice(0, first).trim();
    const username = trimmed.slice(first + 1, second).trim();
    const password = trimmed.slice(second + 1);
    if (!channelId || !username || !password) {
      throw new Error(`CHANNEL_ACCOUNTS 항목이 비었습니다: ${trimmed}`);
    }
    map.set(channelId, { username, password });
  }
  return map;
}

function intFrom(name, fallback) {
  const n = Number(process.env[name]);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : fallback;
}

export const config = {
  discordToken: required('DISCORD_TOKEN'),
  apiBase: required('CAROUSEL_API_BASE').replace(/\/+$/, ''),
  channelAccounts: parseChannelAccounts(process.env.CHANNEL_ACCOUNTS),
  // 두뇌는 Claude Code CLI 다. CLI 가 로그인된 기계에서만 돌아가므로 이 봇은
  // 라이브 서버가 아니라 CLI 가 깔린 PC 에서 실행한다.
  claude: {
    command: (process.env.CLAUDE_COMMAND || 'claude').trim(),
    // Claude 가 문서를 읽을 작업공간. 기본은 캐러셀 자동화 프로젝트 루트(봇의 상위).
    // 여기 밖은 권한 파일에서 막는다.
    workspace: (process.env.WORKSPACE_ROOT || path.resolve(ROOT, '..')).trim(),
    model: (process.env.CLAUDE_MODEL || '').trim(),
    timeoutMs: intFrom('CLAUDE_TIMEOUT_SEC', 180) * 1000
  },
  approverIds: (process.env.APPROVER_IDS || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean),
  jobConcurrency: intFrom('JOB_CONCURRENCY', 2),
  // 멘션 없이 이어 말할 수 있는 시간. 너무 길면 옆 사람 잡담까지 봇이 받는다.
  followupWindowMs: intFrom('FOLLOWUP_WINDOW_SEC', 180) * 1000,
  session: {
    maxTurns: intFrom('SESSION_MAX_TURNS', 8),
    maxAgeMs: intFrom('SESSION_MAX_AGE_MIN', 120) * 60 * 1000
  }
};

/** 이 채널에서 어느 계정으로 일할지. 매핑에 없으면 null → 봇은 반응하지 않는다. */
export function accountForChannel(channelId) {
  return config.channelAccounts.get(String(channelId)) || null;
}

export function assertRunnable() {
  const problems = [];
  if (config.channelAccounts.size === 0) {
    problems.push('CHANNEL_ACCOUNTS 가 비어 있어 어떤 채널에도 반응하지 않습니다.');
  }
  // claude CLI 존재 확인은 doctor 가 실제로 실행해서 한다.
  if (config.approverIds.length === 0) {
    problems.push('APPROVER_IDS 가 비어 위험 작업은 전부 거부됩니다.');
  }
  return problems;
}
