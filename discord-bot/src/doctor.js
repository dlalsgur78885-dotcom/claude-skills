import crypto from 'node:crypto';
import { assertRunnable, config } from './config.js';
import { api } from './api-client.js';
import { runClaude } from './claude-runner.js';
import { parseStructuredReply } from './structured-output.js';
import { TOOLS } from './tools.js';

/** 배포 전 자가진단. 디스코드 없이 설정·로그인·읽기 도구만 확인한다.
 *  실행: npm run doctor */

const line = (ok, text) => console.log(`  ${ok ? '✅' : '❌'} ${text}`);

console.log(`\nAPI: ${config.apiBase}\n`);

console.log('설정');
const problems = assertRunnable();
line(problems.length === 0, problems.length === 0 ? '문제 없음' : `${problems.length}건`);
for (const p of problems) console.log(`     · ${p}`);

console.log('\n채널 매핑');
if (config.channelAccounts.size === 0) {
  line(false, 'CHANNEL_ACCOUNTS 가 비었습니다');
} else {
  for (const [channelId, account] of config.channelAccounts) {
    try {
      const me = await api.me(account);
      line(true, `${channelId} → ${account.username} (id=${me.id}, ${me.role})`);
    } catch (error) {
      line(false, `${channelId} → ${account.username}: ${error.message}`);
    }
  }
}

const first = [...config.channelAccounts.values()][0];
if (first) {
  console.log('\n읽기 도구');
  for (const tool of TOOLS.filter((t) => t.risk === 'safe')) {
    try {
      const out = await tool.run(first, { limit: 3 });
      const n = Array.isArray(out) ? `${out.length}건` : typeof out === 'object' ? 'ok' : String(out);
      line(true, `${tool.name} → ${n}`);
    } catch (error) {
      line(false, `${tool.name}: ${error.message}`);
    }
  }
}

console.log('\n두뇌 (Claude Code CLI)');
try {
  const t0 = Date.now();
  const out = await runClaude({
    prompt: '너는 JSON 만 출력한다. 형식: {"action":"answer","answer":"ok"}\n\n사용자: 준비됐어?',
    sessionId: crypto.randomUUID()
  });
  const parsed = parseStructuredReply(out.text, {
    type: 'object',
    required: ['action'],
    properties: { action: { type: 'string', enum: ['answer'] } }
  });
  line(
    parsed.ok,
    `${config.claude.command} 응답 ${((Date.now() - t0) / 1000).toFixed(1)}초, JSON ${parsed.ok ? 'OK' : '실패'}`
  );
  if (!parsed.ok) console.log(`     · ${parsed.errors.join(', ')}`);
} catch (error) {
  line(false, `${config.claude.command}: ${error.message}`);
  console.log('     · CLI 가 로그인된 기계에서만 돕니다. 라이브 서버에는 없습니다.');
}

console.log('\n위험 도구(확인 필요, 실행하지 않음)');
for (const t of TOOLS.filter((t) => t.risk === 'danger')) console.log(`  ⚠ ${t.name}`);
console.log('');
