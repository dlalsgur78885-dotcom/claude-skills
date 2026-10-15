// 유튜브 댓글 카드를 화면 그대로 찍는다 — 좋아요가 많은 순으로.
//
// 규칙 원본은 `docs/process/X인용_3-3단계_본문.md` 다. 여기 옮겨 적지 않는다.
// X 답글 카드(`x-replies` · `xreply_card`)와 같은 자리에 쓰는 유튜브판이다:
//   1. 영상 페이지를 열어 댓글을 넉넉히 내려 받고 **좋아요 많은 순**으로 다시 세운다
//   2. 접힌 댓글을 펴고 답글·버튼은 숨긴다
//   3. 댓글 한 개 = 카드 한 장으로 찍는다 (좋아요 수는 그대로 둔다)
//   4. 쓴 사람 한 줄만 블러 (X 답글 카드와 같은 규칙)
//
// 쓰는 법:
//   node scripts/yt-comment-capture.mjs "<영상 URL>" [장수]          — 좋아요 많은 순 N 장 (낱장마다 댓글 1개)
//   node scripts/yt-comment-capture.mjs "<영상 URL>" [장수] --stack 3 — 한 장에 댓글 3개씩 묶어서
//   node scripts/yt-comment-capture.mjs "<영상 URL>" --find "글 조각" — 고른 댓글 한 장
// 좋아요 순위는 `yt-dlp --write-comments` 쪽이 더 정확하다(화면은 다 안 붙는다).
// 거기서 고른 댓글을 --find 로 찍는 것이 이 축의 기본 길이다.
// 표준출력으로 카드마다 JSON 한 줄(path · likes · text)을 돌려준다.
// playwright 는 frontend 쪽에 깔려 있다 — 이 스크립트는 저장소 루트에서 부른다.
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { chromium } = require('../frontend/node_modules/playwright');
import { mkdirSync } from 'node:fs';
import path from 'node:path';

const url = process.argv[2];
const findAt = process.argv.indexOf('--find');
const needle = findAt > 0 ? (process.argv[findAt + 1] || '').trim() : '';
const stackAt = process.argv.indexOf('--stack');
const stack = stackAt > 0 ? Number(process.argv[stackAt + 1] || 3) : 0;
const want = needle ? 1 : Number(process.argv[3] || 6);
if (!url) throw new Error('영상 URL 을 인자로 주세요.');

const OUT_DIR = path.join(process.cwd(), 'data', 'imgtmp', 'ytcap');
const SCALE = 3;
mkdirSync(OUT_DIR, { recursive: true });

// 「1.2천」·「1.2K」 처럼 줄여 쓴 좋아요를 숫자로 되돌린다.
function parseLikes(raw) {
  if (!raw) return 0;
  const n = parseFloat(raw.replace(/[^0-9.]/g, ''));
  if (Number.isNaN(n)) return 0;
  if (/천|K/i.test(raw)) return n * 1000;
  if (/만/.test(raw)) return n * 10000;
  if (/M/i.test(raw)) return n * 1000000;
  return n;
}

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({
    deviceScaleFactor: SCALE,
    // 카드가 가로로 길면 1080×1350 낱장에 넣을 때 글자가 작아진다. 좁게 연다.
    viewport: { width: 760, height: 1600 },
    locale: 'ko-KR',
  });
  await page.goto(`${url}${url.includes('?') ? '&' : '?'}hl=ko&gl=KR`, {
    waitUntil: 'domcontentloaded',
    timeout: 90000,
  });
  // 재생 중이면 캡처가 흔들린다. 소리도 끈다.
  // 재생 화면과 애니메이션은 캡처를 흔든다.
  await page
    .addStyleTag({ content: 'video{visibility:hidden} *{animation:none!important;transition:none!important}' })
    .catch(() => {});

  // 댓글은 스크롤해야 붙는다. 좋아요 순으로 고르려면 모수가 있어야 해서 넉넉히 받는다.
  const thread = page.locator('ytd-comment-thread-renderer');
  const pool = Math.max(want * 8, 30);
  for (let i = 0; i < 40; i += 1) {
    if (needle) {
      if (await page.locator('#content-text', { hasText: needle }).count()) break;
    } else if ((await thread.count()) >= pool) break;
    await page.mouse.wheel(0, 1600);
    await page.waitForTimeout(1200);
  }
  if ((await thread.count()) === 0) throw new Error('댓글을 못 찾았습니다 (로그인 요구이거나 댓글이 꺼진 영상).');

  await page.evaluate(() => {
    // 접힌 댓글을 편다 — 「자세히 보기」로 잘리면 뒷부분이 캡처에서 사라진다.
    for (const b of document.querySelectorAll('ytd-comment-thread-renderer tp-yt-paper-button#more')) b.click();
    // 답글 줄·버튼은 카드에 들어가면 안 된다.
    for (const el of document.querySelectorAll(
      'ytd-comment-thread-renderer #replies, ytd-comment-thread-renderer ytd-button-renderer#reply-button-end',
    )) el.style.display = 'none';
  });
  await page.waitForTimeout(800);

  // --find 면 그 댓글 하나, 아니면 좋아요 많은 순으로 고른다
  // (유튜브 기본 정렬 「인기순」은 좋아요 순서가 아니다).
  const total = await thread.count();
  let picks = [];
  if (needle) {
    for (let i = 0; i < total; i += 1) {
      const t = await thread.nth(i).locator('#content-text').first().innerText().catch(() => '');
      if (t.includes(needle)) { picks = [{ i }]; break; }
    }
    if (!picks.length) throw new Error(`그 댓글을 못 찾았습니다: ${needle}`);
  } else {
    const ranked = [];
    for (let i = 0; i < total; i += 1) {
      const raw = (await thread.nth(i).locator('#vote-count-middle').first().innerText().catch(() => '')).trim();
      ranked.push({ i, likes: parseLikes(raw) });
    }
    ranked.sort((a, b) => b.likes - a.likes);
    picks = ranked.slice(0, want);
  }

  // 쓴 사람 한 줄만 블러 — 잘라내면 유튜브 캡처 느낌이 사라진다.
  const blur = async (card) => card.evaluate((el) => {
    const head = el.querySelector('#header-author');
    if (head) head.style.filter = 'blur(6px)';
    const pic = el.querySelector('#author-thumbnail');
    if (pic) pic.style.filter = 'blur(6px)';
  });
  const read = async (card) => ({
    text: (await card.locator('#content-text').first().innerText().catch(() => '')).trim(),
    likes: (await card.locator('#vote-count-middle').first().innerText().catch(() => '')).trim(),
  });

  if (!stack) {
    for (const { i } of picks) {
      const card = thread.nth(i);
      await card.scrollIntoViewIfNeeded();
      await page.waitForTimeout(400);
      const { text, likes } = await read(card);
      await blur(card);
      const out = path.join(OUT_DIR, `ytc-${Date.now()}-${i + 1}.png`);
      await card.screenshot({ path: out });
      process.stdout.write(`${JSON.stringify({ path: out, likes, text })}\n`);
    }
  } else {
    // 묶어 찍기 — 고른 댓글만 남기고 나머지는 숨긴 뒤 **댓글 목록을 통째로** 찍는다.
    // 잘라 붙이지 않는다. 유튜브가 그린 화면 그대로여야 캡처로 보인다.
    const rows = [];
    for (const { i } of picks) {
      const card = thread.nth(i);
      await card.scrollIntoViewIfNeeded();
      await page.waitForTimeout(300);
      rows.push({ i, ...(await read(card)) });
      await blur(card);
    }
    for (let g = 0; g < rows.length; g += stack) {
      const group = rows.slice(g, g + stack);
      await page.evaluate((keep) => {
        const all = [...document.querySelectorAll('ytd-comment-thread-renderer')];
        all.forEach((el, idx) => { el.style.display = keep.includes(idx) ? '' : 'none'; });
        // 고른 순서(좋아요 많은 순)대로 다시 세운다 — 부모가 같아 화면은 그대로 그려진다.
        const parent = all[keep[0]].parentElement;
        keep.forEach((idx) => parent.appendChild(all[idx]));
        // 더 불러오는 자리는 숨긴다 — 계속 붙으면 높이가 흔들려 캡처가 안 끝난다.
        for (const el of document.querySelectorAll('ytd-continuation-item-renderer')) el.style.display = 'none';
      }, group.map((r) => r.i));
      await page.waitForTimeout(900);
      // 요소 캡처는 유튜브가 계속 다시 그려 「안정될 때까지」를 못 넘긴다.
      // 고른 카드들이 차지한 자리를 재서 그 네모만 찍는다.
      const clip = await page.evaluate(() => {
        const vis = [...document.querySelectorAll('ytd-comment-thread-renderer')]
          .filter((el) => el.style.display !== 'none');
        vis[0].scrollIntoView({ block: 'start' });
        window.scrollBy(0, -24);
        const rects = vis.map((el) => el.getBoundingClientRect());
        const top = Math.min(...rects.map((r) => r.top));
        const bottom = Math.max(...rects.map((r) => r.bottom));
        const left = Math.min(...rects.map((r) => r.left));
        const right = Math.max(...rects.map((r) => r.right));
        return { x: left, y: Math.max(top, 0), width: right - left, height: bottom - Math.max(top, 0) };
      });
      await page.waitForTimeout(500);
      const out = path.join(OUT_DIR, `ytc-${Date.now()}-g${g / stack + 1}.png`);
      await page.screenshot({ path: out, clip });
      process.stdout.write(`${JSON.stringify({ path: out, comments: group.map(({ likes, text }) => ({ likes, text })) })}\n`);
    }
  }
} finally {
  await browser.close();
}
