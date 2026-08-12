import { config } from './config.js';
import { parseStructuredReply, schemaRetryInstruction } from './structured-output.js';
import { TOOL_BY_NAME, toolCatalogText } from './tools.js';

/** 한 번에 도구 하나를 고르거나, 도구 없이 바로 답한다. */
const PLAN_SCHEMA = {
  type: 'object',
  required: ['action'],
  properties: {
    action: { type: 'string', enum: ['tool', 'answer'] },
    tool: { type: 'string' },
    args: { type: 'object' },
    answer: { type: 'string', maxLength: 1800 },
    reason: { type: 'string', maxLength: 200 }
  }
};

const MAX_STEPS = 4; // 도구 → 결과 → 도구 … 무한루프 방지

async function gemini(prompt) {
  const url =
    `https://generativelanguage.googleapis.com/v1beta/models/${config.gemini.model}:generateContent`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-goog-api-key': config.gemini.apiKey },
    body: JSON.stringify({ contents: [{ role: 'user', parts: [{ text: prompt }] }] })
  });
  if (!res.ok) {
    throw new Error(`LLM 호출 실패 (${res.status}): ${(await res.text()).slice(0, 200)}`);
  }
  const data = await res.json();
  return (data?.candidates?.[0]?.content?.parts || []).map((p) => p.text || '').join('');
}

function systemPrompt(account) {
  return [
    '너는 인스타그램 캐러셀 제작 팀의 보조다. 디스코드에서 한국어로 대화한다.',
    `지금 "${account.username}" 계정 권한으로 일한다. 이 계정이 가진 채널·템플릿만 보인다.`,
    '',
    '규칙:',
    '- 사실은 반드시 도구로 확인한다. 숫자나 목록을 지어내지 않는다.',
    '- 도구 결과가 비어 있으면 없다고 말한다. 추측으로 채우지 않는다.',
    '- 답변은 짧게. 표가 필요하면 간단한 목록으로.',
    '- 사용자가 요청하지 않은 삭제·변경은 절대 제안만 하고 실행하지 않는다.',
    '',
    '쓸 수 있는 도구:',
    toolCatalogText(),
    '',
    '출력은 항상 JSON 객체 하나다. 설명 문장을 앞뒤에 붙이지 않는다.',
    '  도구를 쓸 때 : {"action":"tool","tool":"이름","args":{...},"reason":"왜"}',
    '  답할 때     : {"action":"answer","answer":"사용자에게 보일 한국어 답변"}'
  ].join('\n');
}

/** 모델에게 JSON 을 받되, 규격에 맞을 때까지 한 번 더 기회를 준다. */
async function planStep(prompt) {
  let text = await gemini(prompt);
  let parsed = parseStructuredReply(text, PLAN_SCHEMA);
  if (!parsed.ok) {
    text = await gemini(`${prompt}\n\n${schemaRetryInstruction(parsed.errors)}\n\n직전 답변:\n${text}`);
    parsed = parseStructuredReply(text, PLAN_SCHEMA);
  }
  if (!parsed.ok) throw new Error(`모델 응답을 이해하지 못했습니다: ${parsed.errors.join(', ')}`);
  return parsed.value;
}

/**
 * 사용자 메시지를 처리한다.
 * @param account  이 채널에 매핑된 앱 계정
 * @param history  최근 대화 [{role, text}]
 * @param message  이번 사용자 메시지
 * @param onDanger 위험 도구를 고른 경우 호출. true 를 돌려주면 실행한다.
 * @returns {{reply: string, used: string[]}}
 */
export async function handleMessage({ account, history, message, onDanger }) {
  const used = [];
  const transcript = [];

  for (const turn of history || []) {
    transcript.push(`${turn.role === 'bot' ? '봇' : '사용자'}: ${turn.text}`);
  }
  transcript.push(`사용자: ${message}`);

  for (let step = 0; step < MAX_STEPS; step += 1) {
    const prompt = [systemPrompt(account), '', '대화:', ...transcript].join('\n');
    const plan = await planStep(prompt);

    if (plan.action === 'answer') {
      return { reply: plan.answer || '(답변이 비었습니다)', used };
    }

    const tool = TOOL_BY_NAME.get(plan.tool);
    if (!tool) {
      transcript.push(`도구결과(${plan.tool}): 그런 도구는 없다. 목록에 있는 것만 쓸 것.`);
      continue;
    }

    // 되돌리기 어려운 것은 사람 확인을 받는다. 승인자가 없으면 실행하지 않는다.
    if (tool.risk === 'danger') {
      const approved = onDanger ? await onDanger(tool, plan.args || {}, plan.reason || '') : false;
      if (!approved) {
        return {
          reply: `\`${tool.name}\` 은 되돌리기 어려운 작업이라 실행하지 않았습니다.`,
          used
        };
      }
    }

    used.push(tool.name);
    try {
      const result = await tool.run(account, plan.args || {});
      const shown = JSON.stringify(result ?? null);
      // 결과가 길면 잘라 넣는다. 프롬프트가 통째로 불어나면 비용과 지연이 커진다.
      transcript.push(
        `도구결과(${tool.name}): ${shown.length > 4000 ? `${shown.slice(0, 4000)}…(생략)` : shown}`
      );
    } catch (error) {
      transcript.push(`도구결과(${tool.name}): 실패 — ${error.message}`);
    }
  }

  return { reply: '여러 번 시도했지만 답을 만들지 못했습니다. 조금 더 구체적으로 말씀해 주세요.', used };
}
