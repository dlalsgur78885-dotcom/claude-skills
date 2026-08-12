import fs from 'node:fs/promises';
import path from 'node:path';

/** 채널별 Claude 세션.
 *
 *  대화 내용 자체는 Claude CLI 가 세션(--session-id / -r)으로 들고 있다. 우리는 그
 *  세션 UUID 만 기억하면 된다 — 매 턴 히스토리를 다시 실어 보낼 필요가 없다.
 *
 *  만료를 두는 이유(매거진 봇과 같다): 세션이 무한정 이어지면 어제 하던 얘기가
 *  오늘 엉뚱하게 딸려온다. 턴 수와 시간 둘 다로 끊는다.
 *
 *  저장은 .tmp 에 쓰고 rename — 반쯤 쓰인 상태 파일이 남지 않는다.
 */
export class SessionStore {
  constructor({ stateFile, maxTurns, maxAgeMs }) {
    this.stateFile = stateFile;
    this.maxTurns = Math.max(2, maxTurns || 8);
    this.maxAgeMs = Math.max(60_000, maxAgeMs || 2 * 60 * 60 * 1000);
    this.sessions = new Map(); // channelId → { sessionId, turns, updatedAt }
    this.persistChain = Promise.resolve();
  }

  async init() {
    try {
      const saved = JSON.parse(await fs.readFile(this.stateFile, 'utf8'));
      for (const [key, value] of Object.entries(saved.sessions || {})) {
        const at = Date.parse(value?.updatedAt);
        if (
          value?.sessionId &&
          Number.isFinite(at) &&
          Date.now() - at < this.maxAgeMs &&
          (value.turns || 0) < this.maxTurns
        ) {
          this.sessions.set(key, {
            sessionId: value.sessionId,
            turns: value.turns || 0,
            updatedAt: value.updatedAt
          });
        }
      }
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
  }

  /** 이어갈 세션 UUID. 없거나 만료면 null → 새 대화로 시작한다. */
  current(channelId) {
    const key = String(channelId);
    const s = this.sessions.get(key);
    if (!s) return null;
    const stale =
      Date.now() - Date.parse(s.updatedAt) >= this.maxAgeMs || s.turns >= this.maxTurns;
    if (stale) {
      this.sessions.delete(key);
      return null;
    }
    return s.sessionId;
  }

  async remember(channelId, sessionId) {
    const key = String(channelId);
    const previous = this.sessions.get(key);
    this.sessions.set(key, {
      sessionId,
      turns: previous?.sessionId === sessionId ? (previous.turns || 0) + 1 : 1,
      updatedAt: new Date().toISOString()
    });
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
