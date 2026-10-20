// 스레드(Threads) 검색 — 키워드로 공개 글을 긁어 JSON 한 줄씩 돌려준다.
//
// 왜 브라우저인가 — threads.com 은 주소만 받아서는 껍데기만 온다(2026-10-20 확인).
// **검색 화면은 로그인 없이 보이고, 프로필 화면은 로그인 벽에 막힌다.** 그래서 검색만 쓴다.
// 규칙(무엇을 후보로 올릴지)은 `docs/process/_유형공통.md` 에 있다. 여기 옮겨 적지 않는다.
//
// 쓰는 법:
//   node scripts/threads-search.mjs "<일본어 키워드>" [개수]        — 인기순(기본)
//   node scripts/threads-search.mjs "<키워드>" 30 --recent          — 최신순
//
// 돌려주는 것(한 줄 = 글 하나): url · author · time · likes · replies · text
// ⚠ 좋아요·답글 수는 화면에 보이는 값을 그대로 읽는다. 조회수는 스레드가 공개하지 않는다.
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { chromium } = require('../frontend/node_modules/playwright');

const query = process.argv[2];
const want = Number(process.argv[3] || 20);
const recent = process.argv.includes('--recent');
if (!query) throw new Error('검색어를 인자로 주세요.');

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';
const url = `https://www.threads.com/search?q=${encodeURIComponent(query)}&serp_type=default${recent ? '&filter=recent' : ''}`;

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ locale: 'ja-JP', userAgent: UA });
const page = await ctx.newPage();
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45_000 });
await page.waitForTimeout(6_000);

// 로그인 벽이면 글이 하나도 안 붙는다 — 그때는 빈손으로 끝낸다.
for (let i = 0; i < 8; i++) {
  const n = await page.evaluate(() => document.querySelectorAll('a[href*="/post/"]').length);
  if (n >= want * 2) break;
  await page.mouse.wheel(0, 4000);
  await page.waitForTimeout(1_500);
}

const posts = await page.evaluate(() => {
  const anchors = [...document.querySelectorAll('a[href*="/post/"]')]
    .filter((a) => !a.getAttribute('href').endsWith('/media'));
  const seen = new Set();
  const out = [];
  for (const a of anchors) {
    const href = a.getAttribute('href');
    if (seen.has(href)) continue;
    seen.add(href);
    let box = a;
    for (let i = 0; i < 9 && box.parentElement; i++) box = box.parentElement;
    const t = box.querySelector('time');
    const lines = (box.innerText || '').split('\n').map((s) => s.trim()).filter(Boolean);
    // 끝에 붙는 숫자들이 좋아요·답글·리포스트다. 본문은 그 앞까지.
    const nums = [];
    while (lines.length && /^[\d.,]+[천만KM]?$/.test(lines[lines.length - 1])) nums.unshift(lines.pop());
    out.push({
      url: 'https://www.threads.com' + href,
      author: lines[0] || null,
      time: t ? t.getAttribute('datetime') : null,
      likes: nums[0] || null,
      replies: nums[1] || null,
      text: lines.slice(2).join(' ').slice(0, 400),
    });
  }
  return out;
});

for (const p of posts.slice(0, want)) console.log(JSON.stringify(p));
if (!posts.length) console.error('글을 하나도 못 받았다 — 로그인 벽이거나 화면 구조가 바뀐 것이다.');
await browser.close();
