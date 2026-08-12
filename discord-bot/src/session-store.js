import fs from 'node:fs/promises';
import path from 'node:path';

/** 채널별 최근 대화. 맥락이 이어져야 "그중에 좋아요 많은 거" 같은 말이 통한다.
 *
 *  매거진 봇은 CLI 세션 ID 를 저장해 재개하지만, 우리는 매 호출에 히스토리를 직접
 *  넘기므로 기록만 들고 있으면 된다. 대신 두 가지는 그대로 가져왔다:
 *    - 턴 수·시간 만료 (오래된 맥락이 엉뚱하게 딸려오는 걸 막는다)
 *    - .tmp 에 쓰고 rename (반쯤 쓰인 상태 파일이 안 남는다)
 */
export class SessionStore {
  constructor({ stateFile, maxTurns, maxAgeMs }) {
    this.stateFile = stateFile;
    this.maxTurns = Math.max(2, maxTurns || 8);
    this.maxAgeMs = Math.max(60_000, maxAgeMs || 2 * 60 * 60 * 1000);
    this.sessions = new Map(); // channelId → { turns: [{role,text}], updatedAt }
    this.persistChain = Promise.resolve();
  }

  async init() {
    try {
      const saved = JSON.parse(await fs.readFile(this.stateFile, 'utf8'));
      for (const [key, value] of Object.entries(saved.sessions || {})) {
        const at = Date.parse(value?.updatedAt);
        if (Number.isFinite(at) && Date.now() - at < this.maxAgeMs) {
          this.sessions.set(key, { turns: value.turns || [], updatedAt: value.updatedAt });
        }
      }
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
  }

  history(channelId) {
    const s = this.sessions.get(String(channelId));
    if (!s) return [];
    if (Date.now() - Date.parse(s.updatedAt) >= this.maxAgeMs) {
      this.sessions.delete(String(channelId));
      return [];
    }
    return s.turns;
  }

  async append(channelId, role, text) {
    const key = String(channelId);
    const s = this.sessions.get(key) || { turns: [], updatedAt: new Date().toISOString() };
    s.turns.push({ role, text: String(text).slice(0, 1500) });
    // 한 턴 = 사용자 + 봇 이므로 2배로 자른다.
    if (s.turns.length > this.maxTurns * 2) s.turns = s.turns.slice(-this.maxTurns * 2);
    s.updatedAt = new Date().toISOString();
    this.sessions.set(key, s);
    await this.persist();
  }

  async reset(channelId) {
    this.sessions.delete(String(channelId));
    await this.persist();
  }

  persist() {
    const operation = async () => {
      await fs.mkdir(path.dirname(this.stateFile), { recursive: true });
      const tmp = `${this.stateFile}.tmp`;
      await fs.writeFile(
        tmp,
        `${JSON.stringify({ version: 1, sessions: Object.fromEntries(this.sessions) }, null, 2)}\n`,
        'utf8'
      );
      await fs.rename(tmp, this.stateFile);
    };
    this.persistChain = this.persistChain.then(operation, operation);
    return this.persistChain;
  }
}
