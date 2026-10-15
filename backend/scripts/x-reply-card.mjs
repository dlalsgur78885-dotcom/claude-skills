// 답글 **한 개 = 캡처 한 장**. X 임베드를 그대로 찍고, 글만 한국어로 갈아 끼운다.
//
// 규칙 원본은 `docs/process/X인용_3-3단계_본문.md` 「일본 반응」 절이다(2026-10-13 교체 —
// 그 전에는 답글 3개를 손으로 그려 한 장에 몰았다). 이 파일은 그 문서가 정한 **찍는 절차**만 한다:
//
//   1. 답글 ID 로 임베드를 연다 — 답글도 게시물이라 공개 임베드가 그대로 열린다(2026-10-13 확인)
//   2. 위에 딸려 나오는 **원글 카드는 잘라낸다** (원글은 본문 첫 장에 이미 있다)
//   3. 글을 한국어로 갈아 끼우고 「N개의 답글 읽기」·「더 보기」는 숨긴다
//   4. 조회수는 게시 시각 뒤에, 답글·재게시·마음에 들어요는 그 아래 한 줄 — x.com 본 화면과 같은 자리
//   5. 쓴 사람 한 줄만 블러 (프로필 사진·이름·인증 배지·아이디·팔로우하기)
//
// 쓰는 법 (stdin 으로 JSON · 표준출력으로 PNG 경로 한 줄):
//   echo '{"id":"123","korean":"...","views":8201,"replies":1,"reposts":1,"likes":20,"out":"C:/tmp/a.png"}' \
//     | node backend/scripts/x-reply-card.mjs
//
// playwright 는 이 레포에 없다 — 봇 폴더에 깔린 것을 쓴다. 그 경로는 `PW_ENTRY` 로 받는다
// (`x_search.capture_reply` 가 넘긴다).
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const pw = process.env.PW_ENTRY
  ? await import(pathToFileURL(process.env.PW_ENTRY).href)
  : await import('playwright');
const { chromium } = pw.default ?? pw;

const job = JSON.parse(readFileSync(0, 'utf8').trim() || '{}');
if (!job.id) throw new Error('답글 id 가 없습니다.');
if (!job.out) throw new Error('저장할 경로(out)가 없습니다.');

// 카드가 작게 찍히면 글자가 뭉갠다 — x-capture.js 와 같은 값이다.
const SCALE = 3;

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({
    viewport: { width: 620, height: 2600 },
    deviceScaleFactor: SCALE,
    locale: 'ko-KR',
  });
  await page.goto(
    `https://platform.twitter.com/embed/Tweet.html?id=${encodeURIComponent(job.id)}&lang=ko`,
    { waitUntil: 'domcontentloaded', timeout: 60000 },
  );
  await page.locator('article').first().waitFor({ state: 'visible', timeout: 45000 });
  // 아바타·수치가 늦게 붙는다. 9초는 2026-10-13 실측값이다.
  await page.waitForTimeout(9000);

  const geo = await page.evaluate((job) => {
    const n = (v) => Number(v || 0).toLocaleString('ko-KR');
    const arts = [...document.querySelectorAll('article')];
    const outer = arts[0];
    // 답글 임베드는 **원글 카드를 위에 끼워** 보여 준다 — 그 article 이 안쪽에 하나 더 있다.
    const parent = arts.find((a) => a.parentElement.closest('article'));
    // 원글 카드 안의 것을 답글 것으로 잘못 집으면 원글 글자를 갈아 끼운다.
    const mine = (sel) => [...outer.querySelectorAll(sel)].filter((e) => !parent || !parent.contains(e));

    // 1. 답글 본문을 한국어로 갈아 끼운다
    const box = mine('[data-testid="tweetText"]')[0];
    if (box && job.korean) {
      const nodes = [...box.childNodes];
      nodes[0].textContent = job.korean;
      nodes.slice(1).forEach((x) => x.remove());
    }
    // 2. 접힌 줄 펴기 · 「N개의 답글 읽기」 숨기기
    for (const el of [...document.querySelectorAll('a,span,div')]) {
      const t = (el.innerText || '').trim();
      if (/^\d+개의 답글 읽기$/.test(t) && el.children.length <= 2) el.style.display = 'none';
      if (t === '더 보기' && el.children.length <= 2) el.style.display = 'none';
    }
    // 3. 게시 시각 뒤에 조회수 — 임베드는 좋아요만 보여 준다(수치는 FxTwitter 로 받은 값이다).
    const time = mine('time')[0];
    const timeRow = time?.closest('div');
    if (time && job.views) {
      const s = document.createElement('span');
      s.textContent = ` · 조회수 ${n(job.views)}회`;
      s.className = time.closest('span')?.className || '';
      time.closest('span')?.parentElement?.appendChild(s);
    }
    // 4. 수치 줄 — 답글 · 재게시 · 마음에 들어요
    if (timeRow) {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;gap:18px;padding:12px 0 2px;'
        + 'font:400 15px/20px system-ui,-apple-system,"Segoe UI",sans-serif;color:#536471;';
      row.innerHTML = [['답글', job.replies], ['재게시', job.reposts], ['마음에 들어요', job.likes]]
        .map(([k, v]) => `<span><b style="color:#0f1419">${n(v)}</b> ${k}</span>`).join('');
      timeRow.parentElement.insertBefore(row, timeRow.nextSibling);
    }
    // 5. 쓴 사람 한 줄만 블러 — 잘라내면 X 캡처 느낌이 사라진다(2026-10-13 확정).
    //    게시 시각·수치·좋아요 줄은 그대로 둔다.
    const avatar = mine('img[src*="profile_images"]')[0];
    let head = avatar;
    while (head && !(head.innerText || '').includes('@')) head = head.parentElement;
    if (head) head.style.filter = 'blur(5px)';

    return {
      outer: outer.getBoundingClientRect().toJSON(),
      parentBottom: parent ? parent.getBoundingClientRect().bottom : null,
      blurred: !!head,
    };
  }, job);

  await page.waitForTimeout(600);
  const o = geo.outer;
  // 원글 카드가 끝나는 자리부터 찍는다 — 없으면 카드 처음부터.
  const top = geo.parentBottom ?? o.top;
  await page.screenshot({
    path: job.out,
    clip: { x: o.x, y: top, width: o.width, height: o.bottom - top },
  });
  if (!geo.blurred) process.stderr.write('⚠ 쓴 사람 줄을 찾지 못해 블러를 못 넣었습니다.\n');
  process.stdout.write(job.out + '\n');
} finally {
  await browser.close();
}
