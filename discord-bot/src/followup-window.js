import fs from 'node:fs/promises';
import path from 'node:path';

// 매거진 봇(discord-bot/src/followup-window.js)의 방식을 옮겨왔다.
//
// 사람과 대화할 때 매 문장마다 이름을 부르지 않는다. 한 번 말을 걸면 잠시 동안은
// 멘션 없이 이어 말할 수 있어야 한다. 그 "잠시"를 관리한다.
//
// 파일에 저장하는 이유: 봇을 재시작하면 창이 닫혀 후속 메시지가 조용히 유실된다.
const DEFAULT_WINDOW_MS = 3 * 60 * 1000;

const entryKey = (channelId, userId) => `${channelId}:${userId}`;

export class FollowupWindow {
  constructor({ stateFile, windowMs = DEFAULT_WINDOW_MS }) {
    this.stateFile = stateFile;
    this.windowMs = Math.max(1000, Number(windowMs) || DEFAULT_WINDOW_MS);
    this.entries = new Map();
    this.persistChain = Promise.resolve();
  }

  async init() {
    try {
      const saved = JSON.parse(await fs.readFile(this.stateFile, 'utf8'));
      const now = Date.now();
      for (const [key, value] of Object.entries(saved.entries || {})) {
        const at = Number(value);
        if (Number.isFinite(at) && now - at < this.windowMs) this.entries.set(key, at);
      }
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
  }

  /** 창 안에 있는가.
   *
   *  ⚠ 기준은 처리 시각이 아니라 **메시지 전송 시각**이다. 앞 턴이 오래 걸리면
   *    그 사이 보낸 후속 메시지가 처리 시점엔 이미 만료된 것으로 보여 유실된다. */
  isFollowup(channelId, userId, sentAtMs = Date.now()) {
    const at = this.entries.get(entryKey(channelId, userId));
    if (!Number.isFinite(at)) return false;
    return sentAtMs - at < this.windowMs;
  }

  /** 창을 연다(또는 연장한다). */
  touch(channelId, userId, sentAtMs = Date.now()) {
    this.entries.set(entryKey(channelId, userId), sentAtMs);
    return this.persist();
  }

  clear(channelId, userId) {
    this.entries.delete(entryKey(channelId, userId));
    return this.persist();
  }

  persist() {
    const operation = async () => {
      const now = Date.now();
      for (const [key, at] of this.entries) {
        if (now - at >= this.windowMs) this.entries.delete(key);
      }
      await fs.mkdir(path.dirname(this.stateFile), { recursive: true });
      const tmp = `${this.stateFile}.tmp`;
      await fs.writeFile(
        tmp,
        `${JSON.stringify({ version: 1, entries: Object.fromEntries(this.entries) }, null, 2)}\n`,
        'utf8'
      );
      await fs.rename(tmp, this.stateFile);
    };
    this.persistChain = this.persistChain.then(operation, operation);
    return this.persistChain;
  }
}
