import { config } from './config.js';
import { parseStructuredReply, schemaRetryInstruction } from './structured-output.js';
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

    // 되묻기도 정상 종료다. 후속대화 창이 열려 있으므로 사용자는 멘션 없이 답하면 된다.
    if (plan.action === 'ask') {
      return { reply: plan.question || '조금 더 자세히 알려주시겠어요?', used, asked: true };
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
