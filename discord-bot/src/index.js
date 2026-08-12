import path from 'node:path';
import {
  ActionRowBuilder, ButtonBuilder, ButtonStyle, Client, Events, GatewayIntentBits, Partials
} from 'discord.js';
import { DATA_DIR, accountForChannel, assertRunnable, config } from './config.js';
import { SessionStore } from './session-store.js';
import { FollowupWindow } from './followup-window.js';
import { handleMessage } from './agent.js';

const sessions = new SessionStore({
  stateFile: path.join(DATA_DIR, 'sessions.json'),
  maxTurns: config.session.maxTurns,
  maxAgeMs: config.session.maxAgeMs
});

// 한 번 말을 걸면 잠시 동안은 멘션 없이 이어 말할 수 있다.
const followups = new FollowupWindow({
  stateFile: path.join(DATA_DIR, 'followups.json'),
  windowMs: config.followupWindowMs
});

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent // ⚠ 개발자 포털에서도 켜야 실제로 글이 들어온다
  ],
  partials: [Partials.Channel]
});

/** 디스코드 메시지는 2000자 제한이라 잘라 보낸다. */
async function reply(message, text) {
  const body = String(text || '').trim() || '(빈 응답)';
  for (let i = 0; i < body.length; i += 1900) {
    await message.reply(body.slice(i, i + 1900));
  }
}

/** 위험 도구는 버튼으로 확인을 받는다. 승인자만 누를 수 있고, 2분 안에 안 누르면 취소.
 *  매거진 봇의 approval-store 를 파일로 남기는 대신, 우리는 한 번의 대화 안에서
 *  끝나는 확인이라 메모리에서 처리한다. 재시작하면 대기 중 확인은 사라진다 —
 *  실행되지 않은 채로 사라지므로 안전한 쪽으로 실패한다. */
async function confirmDanger(message, tool, args, reason) {
  if (config.approverIds.length === 0) {
    await reply(message, '승인 담당자(APPROVER_IDS)가 없어 위험 작업을 실행할 수 없습니다.');
    return false;
  }

  const row = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('approve').setLabel('실행').setStyle(ButtonStyle.Danger),
    new ButtonBuilder().setCustomId('reject').setLabel('취소').setStyle(ButtonStyle.Secondary)
  );

  const prompt = await message.reply({
    content: [
      '⚠ **되돌리기 어려운 작업입니다.**',
      `도구: \`${tool.name}\``,
      `인자: \`${JSON.stringify(args)}\``,
      reason ? `이유: ${reason}` : '',
      `승인 가능: ${config.approverIds.map((id) => `<@${id}>`).join(' ')}`
    ].filter(Boolean).join('\n'),
    components: [row]
  });

  try {
    const press = await prompt.awaitMessageComponent({
      time: 120_000,
      filter: (i) => config.approverIds.includes(i.user.id)
    });
    const approved = press.customId === 'approve';
    await press.update({
      content: `${prompt.content}\n\n→ ${approved ? '✅ 승인됨' : '❌ 취소됨'} (<@${press.user.id}>)`,
      components: []
    });
    return approved;
  } catch {
    await prompt.edit({ content: `${prompt.content}\n\n→ ⌛ 시간 초과로 취소`, components: [] });
    return false;
  }
}

client.once(Events.ClientReady, (c) => {
  const rooms = [...config.channelAccounts.entries()]
    .map(([id, a]) => `${id}→${a.username}`)
    .join(', ');
  console.log(`[봇] ${c.user.tag} 준비됨`);
  console.log(`[봇] API: ${config.apiBase}`);
  console.log(`[봇] 채널 매핑: ${rooms || '(없음)'}`);
  for (const problem of assertRunnable()) console.warn(`[경고] ${problem}`);
});

client.on(Events.MessageCreate, async (message) => {
  if (message.author.bot) return;

  // 매핑된 채널에서만 일한다. 계정을 못 정하면 아무 일도 하지 않는다 —
  // 엉뚱한 계정으로 남의 채널을 건드리는 것보다 침묵이 낫다.
  //
  // 다만 **멘션했는데도 침묵하면** 사용자는 봇이 고장난 줄 안다. 그래서 매핑되지
  // 않은 채널에서 부르면 설정에 필요한 값(채널 ID·사용자 ID)을 알려준다.
  // 설정 단계에서 개발자 모드를 켜고 ID 를 찾아다닐 필요가 없어진다.
  const account = accountForChannel(message.channelId);
  if (!account) {
    if (message.mentions.has(client.user)) {
      await message.reply(
        [
          '이 채널은 아직 계정에 연결되어 있지 않습니다.',
          '',
          `• 이 채널 ID : \`${message.channelId}\``,
          `• 당신의 ID  : \`${message.author.id}\``,
          '',
          '위 값을 설정에 넣으면 이 방에서 일할 수 있습니다.'
        ].join('\n')
      );
    }
    return;
  }

  const content = message.content.replace(/<@!?\d+>/g, '').trim();
  if (!content) return;

  // 멘션은 **대화를 시작할 때만** 필요하다. 그 뒤 잠시(기본 3분)는 그냥 말하면 된다 —
  // 사람과 대화할 때 매 문장마다 이름을 부르지 않는다.
  // 창 판정은 메시지 **전송 시각** 기준이다. 앞 턴이 오래 걸리면 그 사이 보낸 말이
  // 처리 시점엔 만료된 것으로 보여 조용히 유실되기 때문이다.
  const sentAt = message.createdTimestamp;
  const mentioned = message.mentions.has(client.user);
  const following = followups.isFollowup(message.channelId, message.author.id, sentAt);
  if (!mentioned && !following) return;

  if (['/new', '새 대화', '새대화'].includes(content)) {
    await sessions.reset(message.channelId);
    await followups.clear(message.channelId, message.author.id);
    await reply(message, '대화를 새로 시작합니다.');
    return;
  }

  // 이번 발화 시점으로 창을 연장한다. 답이 늦어도 후속 메시지가 살아남는다.
  await followups.touch(message.channelId, message.author.id, sentAt);

  await message.channel.sendTyping();
  const typing = setInterval(() => message.channel.sendTyping().catch(() => {}), 8000);

  try {
    const result = await handleMessage({
      account,
      sessionId: sessions.current(message.channelId),
      message: content,
      onDanger: (tool, args, reason) => confirmDanger(message, tool, args, reason),
      onProgress: (label) => console.log(`[봇] ${message.channelId} · ${label}`)
    });
    // Claude CLI 가 대화를 들고 있으므로 세션 UUID 만 기억한다.
    await sessions.remember(message.channelId, result.sessionId);
    await reply(message, result.reply);
    // 되물었으면 답을 기다리는 중이다. 창을 지금 시점으로 다시 열어,
    // 사용자가 생각하는 동안 창이 닫혀 대답이 무시되는 일을 막는다.
    if (result.asked) await followups.touch(message.channelId, message.author.id);
  } catch (error) {
    console.error('[봇] 처리 실패:', error);
    await reply(message, `처리 중 문제가 생겼습니다: ${error.message}`);
  } finally {
    clearInterval(typing);
  }
});

process.on('unhandledRejection', (e) => console.error('[봇] 처리되지 않은 거부:', e));

await sessions.init();
await followups.init();
await client.login(config.discordToken);
