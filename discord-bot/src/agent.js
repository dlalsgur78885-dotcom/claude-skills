import crypto from 'node:crypto';
import { parseStructuredReply, schemaRetryInstruction } from './structured-output.js';
import { runClaude } from './claude-runner.js';
import { TOOL_BY_NAME, toolCatalogText } from './tools.js';

/** 도구를 쓰거나, 답하거나, 되묻는다.
 *  `ask` 가 없으면 애매한 요청에 짐작으로 답하게 된다 — 대화가 아니라 주문 접수가 된다. */
const PLAN_SCHEMA = {
  type: 'object',
  required: ['action'],
  properties: {
    action: { type: 'string', enum: ['tool', 'answer', 'ask'] },
    tool: { type: 'string' },
    args: { type: 'object' },
    answer: { type: 'string', maxLength: 1800 },
    question: { type: 'string', maxLength: 400 },
    reason: { type: 'string', maxLength: 200 }
  }
};

const MAX_STEPS = 4; // 도구 → 결과 → 도구 … 무한루프 방지

function systemPrompt(account) {
  return [
    '너는 인스타그램 캐러셀 제작 팀의 동료다. 디스코드에서 한국어로 **대화한다.**',
    `지금 "${account.username}" 계정 권한으로 일한다. 이 계정이 가진 채널·템플릿만 보인다.`,
    '',
    '대화하는 법:',
    '- 보고서를 쓰지 말고 사람에게 말하듯 답한다. 매번 인사하거나 자기소개하지 않는다.',
    '- 앞 대화를 기억한다. "그거", "아까 그 채널", "거기서" 같은 말은 앞 내용에서 찾아 푼다.',
    '  못 찾겠으면 짐작하지 말고 무엇을 말하는지 되묻는다.',
    '- 요청이 애매하면 **되묻는다.** 예: "좋아요 많은 거"라고만 하면 기준을 묻는다.',
    '  단, 이미 아는 것을 또 묻지는 않는다. 한 번에 하나만 묻는다.',
    '- 이미 말한 내용을 처음부터 다시 나열하지 않는다. 달라진 것만 말한다.',
    '- 결과가 길면 다 쏟지 말고 요점을 말한 뒤 더 볼지 묻는다.',
    '',
    '지켜야 할 것:',
    '- 사실은 반드시 도구로 확인한다. 숫자나 목록을 지어내지 않는다.',
    '- 도구 결과가 비어 있으면 없다고 말한다. 추측으로 채우지 않는다.',
    '- 사용자가 시키지 않은 삭제·변경은 하지 않는다. 필요해 보이면 말로 제안만 한다.',
    '- 너에게는 파일·셸·웹 도구가 없다. 아래 목록의 도구만 쓸 수 있다.',
    '',
    '쓸 수 있는 도구:',
    toolCatalogText(),
    '',
    '출력은 항상 JSON 객체 하나다. 설명 문장을 앞뒤에 붙이지 않는다.',
    '  도구를 쓸 때 : {"action":"tool","tool":"이름","args":{...},"reason":"왜"}',
    '  답할 때     : {"action":"answer","answer":"사용자에게 보일 한국어 답변"}',
    '  되물을 때   : {"action":"ask","question":"확인하고 싶은 것 한 가지"}'
  ].join('\n');
}

/**
 * 한 턴을 돌려 계획을 받는다. 규격에 안 맞으면 무엇이 틀렸는지 알려주고 한 번 더 준다.
 * 재시도도 같은 세션에서 이어가므로 앞 맥락이 유지된다.
 */
async function planTurn(state, promptText, onProgress) {
  let out = await runClaude({
    prompt: promptText,
    sessionId: state.sessionId,
    resume: state.resume,
    onProgress
  });
  state.sessionId = out.sessionId;
  state.resume = true;

  let parsed = parseStructuredReply(out.text, PLAN_SCHEMA);
  if (!parsed.ok) {
    out = await runClaude({
      prompt: schemaRetryInstruction(parsed.errors),
      sessionId: state.sessionId,
      resume: true,
      onProgress
    });
    state.sessionId = out.sessionId;
    parsed = parseStructuredReply(out.text, PLAN_SCHEMA);
  }
  if (!parsed.ok) throw new Error(`응답을 이해하지 못했습니다: ${parsed.errors.join(', ')}`);
  return parsed.value;
}

/**
 * 사용자 메시지를 처리한다.
 *
 * 대화 맥락은 Claude CLI 가 세션(--session-id / -r)으로 들고 있다. 그래서 매 턴
 * 히스토리를 다시 실어 보내지 않는다 — 시스템 프롬프트도 세션당 한 번만 나간다.
 *
 * @param account       이 채널에 매핑된 앱 계정
 * @param sessionId     이어갈 Claude 세션 UUID (없으면 새로 시작)
 * @param message       이번 사용자 메시지
 * @param onDanger      위험 도구 확인. true 를 돌려주면 실행한다.
 * @param onProgress    진행 상황 라벨
 * @returns {{reply, used, asked, sessionId}}
 */
export async function handleMessage({ account, sessionId, message, onDanger, onProgress }) {
  const state = {
    sessionId: sessionId || crypto.randomUUID(),
    resume: Boolean(sessionId)
  };
  const used = [];

  // 새 세션이면 규칙과 도구 목록을 한 번 깔아준다. 이어가는 세션이면 이미 알고 있다.
  let prompt = state.resume
    ? `사용자: ${message}`
    : `${systemPrompt(account)}\n\n사용자: ${message}`;

  for (let step = 0; step < MAX_STEPS; step += 1) {
    const plan = await planTurn(state, prompt, onProgress);

    if (plan.action === 'answer') {
      return { reply: plan.answer || '(답변이 비었습니다)', used, sessionId: state.sessionId };
    }
    // 되묻기도 정상 종료다. 후속대화 창이 열려 있어 사용자는 멘션 없이 답하면 된다.
    if (plan.action === 'ask') {
      return {
        reply: plan.question || '조금 더 자세히 알려주시겠어요?',
        used,
        asked: true,
        sessionId: state.sessionId
      };
    }

    const tool = TOOL_BY_NAME.get(plan.tool);
    if (!tool) {
      prompt = `도구결과(${plan.tool}): 그런 도구는 없다. 목록에 있는 것만 쓸 것.`;
      continue;
    }

    if (tool.risk === 'danger') {
      const approved = onDanger ? await onDanger(tool, plan.args || {}, plan.reason || '') : false;
      if (!approved) {
        return {
          reply: `\`${tool.name}\` 은 되돌리기 어려운 작업이라 실행하지 않았습니다.`,
          used,
          sessionId: state.sessionId
        };
      }
    }

    if (onProgress) onProgress(tool.name);
    used.push(tool.name);
    try {
      const result = await tool.run(account, plan.args || {});
      const shown = JSON.stringify(result ?? null);
      // 결과가 길면 잘라 넣는다. 프롬프트가 통째로 불어나면 비용과 지연이 커진다.
      prompt =
        `도구결과(${tool.name}): ` +
        (shown.length > 4000 ? `${shown.slice(0, 4000)}…(생략)` : shown);
    } catch (error) {
      prompt = `도구결과(${tool.name}): 실패 — ${error.message}`;
    }
  }

  return {
    reply: '여러 번 시도했지만 답을 만들지 못했습니다. 조금 더 구체적으로 말씀해 주세요.',
    used,
    sessionId: state.sessionId
  };
}
