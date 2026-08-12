import { api } from './api-client.js';

/** 봇이 쓸 수 있는 도구 목록.
 *
 *  매거진 봇의 workspace-policy 가 "어느 **파일**을 건드려도 되나"였다면, 여기는
 *  "어느 **행동**을 해도 되나"다. 캐러셀 봇은 파일이 아니라 API 를 호출하므로
 *  위험의 축이 경로가 아니라 동사(조회/생성/삭제)로 바뀐다.
 *
 *  risk:
 *    'safe'     조회. 되돌릴 것이 없다 → 바로 실행
 *    'create'   만들기·수집. 결과가 남지만 지우면 그만이고 비용도 작다 → 바로 실행
 *    'danger'   삭제·덮어쓰기. 되돌리기 어렵다 → 승인 담당자 확인 후 실행
 */
export const TOOLS = [
  {
    name: 'list_channels',
    risk: 'safe',
    desc: '등록된 벤치마크 채널 목록. 그룹(category)과 마지막 수집 시각을 함께 본다.',
    args: {},
    run: async (acct) => {
      const rows = await api.channels(acct);
      return rows.map((c) => ({
        id: c.id,
        handle: c.instagram_handle,
        group: c.category || null,
        active: c.is_active,
        last_scraped_at: c.last_scraped_at
      }));
    }
  },
  {
    name: 'list_posts',
    risk: 'safe',
    desc:
      '수집된 소재를 조건으로 조회한다. is_video=true 면 릴스만, false 면 캐러셀만. ' +
      'category 는 채널 그룹 이름. min_likes 로 인기 소재만 볼 수 있다. limit 는 최대 200.',
    args: {
      is_video: 'boolean?', category: 'string?', min_likes: 'integer?',
      channel_id: 'integer?', q: 'string?', limit: 'integer?', date_from: 'string?', date_to: 'string?'
    },
    run: async (acct, a) => {
      const rows = await api.posts(acct, { ...a, limit: Math.min(Number(a.limit) || 20, 200) });
      const list = Array.isArray(rows) ? rows : rows?.items || [];
      return list.map((p) => ({
        id: p.id,
        caption: String(p.caption || '').slice(0, 120),
        likes: p.like_count,
        comments: p.comment_count,
        slides: p.slide_count,
        is_video: p.is_video,
        posted_at: p.posted_at,
        url: p.post_url
      }));
    }
  },
  {
    name: 'list_groups',
    risk: 'safe',
    desc: '채널 그룹(카테고리) 목록.',
    args: {},
    run: async (acct) => api.categories(acct)
  },
  {
    name: 'list_templates',
    risk: 'safe',
    desc: '내가 쓸 수 있는 템플릿 목록(내 것 + 시스템).',
    args: {},
    run: async (acct) => {
      const res = await api.templates(acct);
      return (res?.templates || []).map((t) => ({
        id: t.id, name: t.name, layouts: t.layouts, is_system: t.user_id === null
      }));
    }
  },
  {
    name: 'list_layouts',
    risk: 'safe',
    desc: '템플릿을 낱장으로 펼친 목록. 분류(표지/격자/CTA/본문·단일)와 격자 크기가 붙어 있다.',
    args: {},
    run: async (acct) => {
      const res = await api.layouts(acct);
      return (res?.layouts || []).filter((l) => !l.hidden).map((l) => ({
        template_id: l.template_id, key: l.layout_key, label: l.label, category: l.category
      }));
    }
  },
  {
    name: 'scrape_status',
    risk: 'safe',
    desc: '지금 수집이 돌고 있는지 확인한다.',
    args: {},
    run: async (acct) => api.scrapeStatus(acct)
  },
  {
    name: 'scrape_channel',
    risk: 'create',
    desc: '채널 하나를 지금 수집한다. handle 은 @ 없이 준다.',
    args: { handle: 'string' },
    run: async (acct, a) => api.scrapeChannel(acct, String(a.handle || '').replace(/^@/, ''))
  },
  {
    name: 'scrape_all',
    risk: 'create',
    desc: '활성 채널 전체를 지금 수집한다. 오래 걸리고 외부 API 를 많이 쓴다.',
    args: {},
    run: async (acct) => api.scrapeAll(acct)
  },
  {
    name: 'create_group',
    risk: 'create',
    desc: '채널 그룹을 만든다.',
    args: { name: 'string' },
    run: async (acct, a) => api.createCategory(acct, { name: String(a.name).trim() })
  },
  {
    name: 'set_channel_group',
    risk: 'create',
    desc: '채널의 그룹을 지정하거나 바꾼다. group 을 빈 문자열로 주면 해제한다.',
    args: { channel_id: 'integer', group: 'string' },
    run: async (acct, a) => api.updateChannel(acct, a.channel_id, { category: a.group ?? '' })
  },
  {
    name: 'rename_group',
    risk: 'danger',
    desc: '그룹 이름을 바꾼다. 이 그룹을 쓰던 채널들도 함께 옮겨진다.',
    args: { category_id: 'integer', name: 'string' },
    run: async (acct, a) => api.updateCategory(acct, a.category_id, { name: String(a.name).trim() })
  },
  {
    name: 'delete_group',
    risk: 'danger',
    desc: '그룹을 삭제한다.',
    args: { category_id: 'integer' },
    run: async (acct, a) => api.deleteCategory(acct, a.category_id)
  },
  {
    name: 'delete_channel',
    risk: 'danger',
    desc: '벤치마크 채널을 삭제한다. 수집 이력도 함께 사라진다.',
    args: { channel_id: 'integer' },
    run: async (acct, a) => api.deleteChannel(acct, a.channel_id)
  }
];

export const TOOL_BY_NAME = new Map(TOOLS.map((t) => [t.name, t]));

/** 모델에게 보여줄 도구 설명. 실행 코드는 빼고 이름·설명·인자만 준다. */
export function toolCatalogText() {
  return TOOLS.map((t) => {
    const args = Object.entries(t.args).map(([k, v]) => `${k}:${v}`).join(', ') || '없음';
    return `- ${t.name} [${t.risk}] ${t.desc}\n  인자: ${args}`;
  }).join('\n');
}
