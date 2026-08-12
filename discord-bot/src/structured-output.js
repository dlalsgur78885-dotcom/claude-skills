// 매거진 봇(discord-bot/src/structured-output.js)의 방식을 옮겨왔다.
// 모델 답변은 코드펜스나 앞뒤 설명이 섞여 나오므로, 자유 텍스트를 그대로 믿지 않고
// JSON 을 뽑아 스키마로 검증한다. 틀리면 무엇이 틀렸는지 돌려주고 다시 시키는 게 핵심.

/** 답변에서 최상위 JSON 객체를 뽑는다. 중괄호 깊이를 세되 문자열 안 괄호는 무시한다.
 *  후보가 여럿이면 뒤쪽을 고른다 — 모델은 보통 마지막에 최종 답을 낸다. */
export function extractJsonObject(text) {
  const source = String(text || '');
  const candidates = [];

  const fence = /```(?:json)?\s*\n([\s\S]*?)```/gu;
  let m = fence.exec(source);
  while (m) {
    candidates.push(m[1]);
    m = fence.exec(source);
  }

  let depth = 0;
  let start = -1;
  let inString = false;
  let escaped = false;
  for (let i = 0; i < source.length; i += 1) {
    const ch = source[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') inString = true;
    else if (ch === '{') {
      if (depth === 0) start = i;
      depth += 1;
    } else if (ch === '}') {
      depth -= 1;
      if (depth === 0 && start !== -1) {
        candidates.push(source.slice(start, i + 1));
        start = -1;
      }
    }
  }

  for (let i = candidates.length - 1; i >= 0; i -= 1) {
    try {
      const parsed = JSON.parse(candidates[i].trim());
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed;
    } catch {
      /* 다음 후보 */
    }
  }
  return null;
}

function typeName(value) {
  if (Array.isArray(value)) return 'array';
  if (value === null) return 'null';
  return typeof value;
}

function validateValue(value, schema, path, errors) {
  if (!schema || typeof schema !== 'object') return;

  // JSON Schema 의 integer 는 number 와 별개다. typeName 은 둘 다 number 로 본다.
  if (schema.type === 'integer') {
    if (typeName(value) !== 'number' || !Number.isInteger(value)) {
      errors.push(`${path}: 정수여야 하는데 ${typeName(value)}입니다`);
      return;
    }
  } else if (schema.type && typeName(value) !== schema.type) {
    errors.push(`${path}: ${schema.type}이어야 하는데 ${typeName(value)}입니다`);
    return;
  }

  if (Array.isArray(schema.enum) && !schema.enum.includes(value)) {
    errors.push(`${path}: 허용값(${schema.enum.join(', ')})이 아닙니다`);
  }
  if (schema.type === 'string' && typeof schema.maxLength === 'number' && value.length > schema.maxLength) {
    errors.push(`${path}: 최대 ${schema.maxLength}자를 넘습니다`);
  }
  if (schema.type === 'array') {
    if (typeof schema.maxItems === 'number' && value.length > schema.maxItems) {
      errors.push(`${path}: 항목이 ${schema.maxItems}개를 넘습니다`);
    }
    if (schema.items) {
      value.forEach((item, i) => validateValue(item, schema.items, `${path}[${i}]`, errors));
    }
  }
  if (schema.type === 'object' && value && typeof value === 'object') {
    validateObject(value, schema, path, errors);
  }
}

function validateObject(value, schema, path, errors) {
  for (const key of schema.required || []) {
    if (!(key in value)) errors.push(`${path ? `${path}.` : ''}${key}: 필수 항목이 빠졌습니다`);
  }
  for (const [key, sub] of Object.entries(schema.properties || {})) {
    if (key in value) validateValue(value[key], sub, `${path ? `${path}.` : ''}${key}`, errors);
  }
}

export function parseStructuredReply(text, schema) {
  const value = extractJsonObject(text);
  if (!value) return { ok: false, value: null, errors: ['답변에서 JSON 객체를 찾지 못했습니다'] };
  const errors = [];
  validateObject(value, schema, '', errors);
  return { ok: errors.length === 0, value: errors.length === 0 ? value : null, errors };
}

export function schemaRetryInstruction(errors) {
  return [
    '직전 답변의 JSON이 규격에 맞지 않았다. 아래 문제를 고쳐 JSON만 다시 출력하라.',
    ...errors.map((e) => `- ${e}`),
    '설명 문장 없이 JSON 객체 하나만 출력한다.'
  ].join('\n');
}
