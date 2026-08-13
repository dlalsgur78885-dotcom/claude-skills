import { spawn } from 'node:child_process';
import { config } from './config.js';

/** Claude Code CLI 를 한 턴 돌린다.
 *
 *  매거진 봇 claude-runner.js 의 방식을 따르되, 이 봇에서 Claude 는 **판단만** 한다 —
 *  데이터는 봇이 캐러셀 API 로 가져와 프롬프트에 넣어주므로 파일·셸 도구가 필요 없다.
 *  그래서 config/claude-permissions.json 으로 전부 막았다.
 *
 *  ⚠ 프롬프트는 argv 가 아니라 **stdin** 으로 넣는다. argv 로 주면 멀티라인이 첫 줄에서
 *    잘린다(매거진 봇 주석에 남아 있는 실측).
 */

function buildArgs({ sessionId, resume }) {
  const args = ['-p'];
  if (resume) args.push('-r', sessionId);
  else args.push('--session-id', sessionId);

  if (config.claude.model) args.push('--model', config.claude.model);

  // ⚠ 절대경로를 쓰면 안 된다. Windows 에서 shell:true 로 띄우면 인자가 이스케이프
  //   없이 이어붙어서, 프로젝트 경로의 공백("캐러셀 자동화")에서 잘린다.
  //   cwd 가 작업공간(프로젝트 루트)이므로 거기서의 상대경로로 준다 — 공백이 안 낀다.
  args.push('--settings', 'discord-bot/config/claude-permissions.json');
  // 플러그인·스킬 목록이 매 턴 다시 실리는 것을 막는다. 이 봇은 하나도 쓰지 않는데
  // 그대로 두면 턴마다 만 단위 토큰이 헛돈다(매거진 봇 실측 ~14,100토큰).
  args.push('--setting-sources', 'project,local');
  // 권한 확인을 건너뛰어도 위 deny 규칙은 그대로 적용된다.
  args.push('--dangerously-skip-permissions');
  args.push('--output-format', 'stream-json', '--verbose');
  return args;
}

/** stream-json 한 줄 → 우리가 쓰는 형태. 모르는 이벤트는 null. */
export function parseEvent(line) {
  let event;
  try {
    event = JSON.parse(line);
  } catch {
    return null;
  }
  if (!event || typeof event !== 'object') return null;

  // hook 관련도 type:"system" 이라 subtype 으로 걸러야 세션 id 를 잘못 잡지 않는다.
  if (event.type === 'system' && event.subtype === 'init') {
    return { kind: 'session', sessionId: event.session_id || '' };
  }
  // 한도 대기는 겉보기에 멈춘 것과 구분되지 않는다 — 진행상황으로 드러낸다.
  if (event.type === 'rate_limit_event') {
    return { kind: 'progress', label: '사용량 한도 대기 중' };
  }
  if (event.type === 'result') {
    return { kind: 'result', text: String(event.result || ''), isError: Boolean(event.is_error) };
  }
  return null;
}

/**
 * @param {string} prompt      stdin 으로 넣을 전체 프롬프트
 * @param {string} sessionId   채널별 세션 UUID
 * @param {boolean} resume     기존 세션 이어가기
 * @param {(label:string)=>void} [onProgress]
 * @returns {Promise<{text:string, sessionId:string}>}
 */
export function runClaude({ prompt, sessionId, resume = false, onProgress }) {
  return new Promise((resolve, reject) => {
    const child = spawn(config.claude.command, buildArgs({ sessionId, resume }), {
      // 프로젝트 루트에서 돈다 — 여기 문서를 읽어 질문에 답한다.
      cwd: config.claude.workspace,
      env: {
        ...process.env,
        NO_COLOR: '1',
        // 사람이 쓰는 확인 훅은 자식 프로세스에서 되물을 상대가 없다. 그대로 두면
        // 매 실행이 첫 도구에서 막힌다.
        ECC_GATEGUARD: 'off',
        // 자식에게 디스코드 토큰을 물려주지 않는다.
        DISCORD_TOKEN: ''
      },
      stdio: ['pipe', 'pipe', 'pipe'],
      shell: process.platform === 'win32'
    });

    let text = '';
    let resolvedSession = sessionId;
    let stderr = '';
    let buffer = '';
    let settled = false;

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill();
      reject(new Error(`Claude 응답이 ${config.claude.timeoutMs / 1000}초를 넘겼습니다.`));
    }, config.claude.timeoutMs);

    child.stdout.on('data', (chunk) => {
      buffer += chunk.toString();
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        const event = parseEvent(line.trim());
        if (!event) continue;
        if (event.kind === 'session' && event.sessionId) resolvedSession = event.sessionId;
        else if (event.kind === 'progress' && onProgress) onProgress(event.label);
        else if (event.kind === 'result') text = event.text || text;
      }
    });

    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });

    child.on('error', (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(new Error(`Claude CLI 실행 실패: ${error.message}`));
    });

    child.on('close', (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (!text) {
        reject(new Error(`Claude 응답이 비었습니다 (code=${code}) ${stderr.slice(0, 200)}`));
        return;
      }
      resolve({ text, sessionId: resolvedSession });
    });

    child.stdin.end(prompt);
  });
}
