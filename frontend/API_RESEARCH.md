# Instagram Carousel Automation Platform - API Research

> Researched: 2026-04-05

---

## 1. INSTAGRAM DATA (Scraping & Data Collection)

### 1.1 HikerAPI [ESSENTIAL]
- **URL**: https://hikerapi.com
- **Docs**: https://api.hikerapi.com/docs
- **What it does**: Unofficial Instagram REST API. Scrapes user profiles, posts, reels, stories, highlights, comments, followers, hashtags, locations, and search data. 147 endpoints, no rate limits, no blocks.
- **Pricing**:
  - 100 free requests on signup
  - Start Plan: $0.02/request
  - Standard Plan: $0.001/request
  - Business Plan: $0.00069/request
  - Ultra Plan: $0.0006/request
  - Pay-per-request, no subscription required
- **Trustpilot**: 5 stars, 191 reviews
- **Key endpoints for our platform**:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v2/user/by/username` | GET | Look up competitor/channel profile |
| `/gql/user/medias` | GET | Get all posts from a user (for scraping carousel ideas) |
| `/v2/user/clips` | GET | Get user's reels |
| `/v2/user/stories` | GET | Get user's stories |
| `/v2/user/highlights/by/username` | GET | Get highlights by username |
| `/v2/media/info/by/code` | GET | Get post details by shortcode |
| `/v2/media/info/by/url` | GET | Get post details from URL |
| `/v2/media/comments` | GET | Get post comments (engagement data) |
| `/v2/media/likers` | GET | Get who liked a post |
| `/v1/media/insight` | GET | Post analytics/insights |
| `/v2/hashtag/medias/top` | GET | Top posts for a hashtag |
| `/v2/hashtag/medias/recent` | GET | Recent posts for a hashtag |
| `/v1/hashtag/by/name` | GET | Hashtag info |
| `/v2/fbsearch/topsearch` | GET | Top search results |
| `/v3/fbsearch/accounts` | GET | Search user accounts |
| `/v2/search/hashtags` | GET | Search hashtags |
| `/v2/user/followers` | GET | Followers list (audience analysis) |
| `/v2/user/suggested/profiles` | GET | Suggested/trending profiles |
| `/v1/user/medias/chunk` | GET | Paginated user media with cursor |
| `/v2/media/template` | GET | Media template/carousel data |

- **Integration notes**: All GET requests, simple API key auth via header. Returns JSON. Pagination via cursor for large datasets.

---

## 2. AI / LLM (Text Generation for Carousel Content)

### 2.1 OpenAI API [ESSENTIAL - pick one of 2.1 or 2.2]
- **URL**: https://platform.openai.com
- **What it does**: Text generation for carousel copy, captions, hashtag suggestions, content rewriting
- **Pricing (2026)**:
  - GPT-5 nano: $0.05 input / $0.40 output per 1M tokens (cheapest, good for simple tasks)
  - GPT-5: $1.25 input / $10.00 output per 1M tokens
  - GPT-5.2: $1.75 input / $14.00 output per 1M tokens (flagship)
  - Batch API: 50% discount (24h async processing)
  - Cached input tokens: 50-90% cheaper
  - Free tier: $5 credit on signup (for new accounts)
- **Key use cases**:
  - Generate carousel slide text from a topic/URL
  - Rewrite/improve existing captions
  - Generate hashtag recommendations
  - Summarize long-form content into carousel slides
  - Generate call-to-action text
- **Key endpoints**:
  - `POST /v1/chat/completions` - Main text generation
  - `POST /v1/embeddings` - For content similarity/search

### 2.2 Anthropic Claude API [ESSENTIAL - alternative to OpenAI]
- **URL**: https://platform.claude.com
- **What it does**: Same use cases as OpenAI, often better at structured/Korean content
- **Pricing (2026)**:
  - Claude Haiku 4.5: $1 input / $5 output per 1M tokens (fastest, cheapest)
  - Claude Sonnet 4.6: $3 input / $15 output per 1M tokens (balanced)
  - Claude Opus 4.6: $5 input / $25 output per 1M tokens (most capable)
  - Batch API: 50% discount
  - Prompt caching: ~90% cheaper on cache reads
  - Combined batch + caching: up to 95% savings
- **Recommendation**: Use Claude Haiku 4.5 for high-volume tasks (caption gen, hashtag suggestions) and Sonnet for complex content generation. Very strong Korean language support.

---

## 3. IMAGE PROCESSING

### 3.1 remove.bg API [OPTIONAL]
- **URL**: https://www.remove.bg/api
- **What it does**: AI background removal from images
- **Pricing**:
  - Free: 50 API calls/month (low-res preview only, 0.25 MP)
  - Pay-as-you-go: starts at $5
  - Subscription: from ~$9/month for 40 credits
  - ~$0.10-$0.20 per high-res image
- **Key endpoint**: `POST /v1.0/removebg` - Remove background from image
- **Use case**: Clean up scraped images, remove backgrounds for carousel slides
- **Note**: Free tier images are NOT licensed for commercial use

### 3.2 Sharp.js [ESSENTIAL - Free, Open Source]
- **URL**: https://www.npmjs.com/package/sharp
- **What it does**: High-performance Node.js image processing (resize, crop, format conversion, compression)
- **Pricing**: FREE (open source)
- **Use cases**: Resize scraped images to 1080x1080/1080x1350, compress for web, convert formats, add watermarks
- **Already used in**: Node.js backend, no API calls needed

### 3.3 Satori (by Vercel) [ESSENTIAL - Free, Open Source]
- **URL**: https://github.com/vercel/satori
- **What it does**: Converts HTML/CSS to SVG. Combined with Sharp, generates PNG images from JSX templates.
- **Pricing**: FREE (open source)
- **Use case**: Generate carousel slide images from HTML/CSS templates on the server side. Perfect for programmatic image generation with custom fonts, layouts, and text.
- **Workflow**: JSX template -> Satori (SVG) -> Sharp (PNG) -> carousel image

### 3.4 node-html-to-image / Puppeteer [OPTIONAL - Free, Open Source]
- **URL**: https://www.npmjs.com/package/node-html-to-image
- **What it does**: Generates PNG/JPEG from HTML using headless Chromium
- **Pricing**: FREE (open source)
- **Use case**: Alternative to Satori for more complex layouts. Better CSS support but heavier (requires Chromium).
- **Trade-off**: More accurate rendering vs. higher memory/CPU usage

---

## 4. STOCK PHOTOS

### 4.1 Unsplash API [RECOMMENDED]
- **URL**: https://unsplash.com/developers
- **Docs**: https://unsplash.com/documentation
- **What it does**: Access to millions of free high-quality stock photos
- **Pricing**: FREE (50 requests/hour)
- **License**: Free for commercial use, no attribution required (but appreciated)
- **Key endpoints**:
  - `GET /search/photos?query=...` - Search photos by keyword
  - `GET /photos/:id` - Get photo details
  - `GET /photos/random` - Get random photo
- **Use case**: Background images, decorative elements for carousel slides

### 4.2 Pexels API [RECOMMENDED]
- **URL**: https://www.pexels.com/api/
- **What it does**: Free stock photos and videos
- **Pricing**: FREE (200 requests/hour, 20,000/month; can request unlimited)
- **License**: Free for commercial use, no attribution required
- **Key endpoints**:
  - `GET /v1/search?query=...` - Search photos
  - `GET /v1/curated` - Curated photos
  - `GET /videos/search?query=...` - Search videos
- **Use case**: Same as Unsplash; use both for wider selection

---

## 5. FONTS & TYPOGRAPHY

### 5.1 Google Fonts API [ESSENTIAL - Free]
- **URL**: https://fonts.google.com / https://developers.google.com/fonts
- **Korean fonts showcase**: https://googlefonts.github.io/korean/
- **What it does**: Free web fonts including Korean fonts. Uses smart subsetting (17,388 Korean glyphs split into ~100 slices for efficient loading).
- **Pricing**: Completely FREE, open source
- **Key Korean fonts available**: Noto Sans KR, Noto Serif KR, Nanum Gothic, Nanum Myeongjo, Black Han Sans, Jua, Do Hyeon, Gothic A1, Sunflower, Gamja Flower, and more
- **Integration**:
  - CSS: `@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap')`
  - API: `GET https://www.googleapis.com/webfonts/v1/webfonts?key=API_KEY` - List all fonts
- **Use case**: Typography for carousel slides. Critical for Korean content.

### 5.2 Adobe Fonts (Typekit) [OPTIONAL]
- **URL**: https://fonts.adobe.com
- **What it does**: Premium font library including high-quality Korean fonts
- **Pricing**: Included with Adobe Creative Cloud ($22.99/month), or standalone plans
- **Use case**: Premium Korean typography if Google Fonts selection is insufficient

---

## 6. STORAGE & CDN

### 6.1 Supabase Storage [ESSENTIAL]
- **URL**: https://supabase.com
- **What it does**: File storage with CDN, plus database and auth (all-in-one BaaS)
- **Pricing (Free tier)**:
  - 2 projects
  - 500 MB database storage
  - 1 GB file storage
  - 5 GB storage egress
  - 50,000 MAUs for auth
  - 500,000 edge function invocations
  - **Caveat**: Projects auto-pause after 7 days of inactivity on free tier
- **Pro plan**: $25/month (8 GB database, 100 GB file storage, no auto-pause)
- **Key features**: S3-compatible, image transformations, public/private buckets, row-level security
- **Use case**: Store generated carousel images, user uploads, template assets

### 6.2 Cloudinary [OPTIONAL - alternative/supplement]
- **URL**: https://cloudinary.com
- **What it does**: Image/video management with transformations, CDN delivery, AI tagging
- **Pricing**:
  - Free: 25 credits/month (~25,000 transformations OR 25 GB storage OR 25 GB bandwidth)
  - Plus: from $99/month
- **Key features**: URL-based image transformations (resize, crop, overlay, text), automatic format optimization
- **Use case**: If you need advanced image transformations via URL (e.g., `https://res.cloudinary.com/demo/image/upload/w_400,h_400,c_crop/sample.jpg`)

### 6.3 Vercel Blob [OPTIONAL]
- **URL**: https://vercel.com/docs/storage/vercel-blob
- **What it does**: Simple file storage integrated with Vercel deployment
- **Pricing**: Free tier included with Vercel Hobby plan
- **Use case**: Quick file uploads if already on Vercel

---

## 7. AUTHENTICATION

### 7.1 Supabase Auth [ESSENTIAL]
- **URL**: https://supabase.com/docs/guides/auth
- **What it does**: Full authentication system with email/password, magic link, social OAuth
- **Pricing**: FREE up to 50,000 MAUs (included in Supabase free tier)
- **Social providers supported**: Google, Facebook, Instagram, Apple, GitHub, Twitter, etc.
- **Key features**:
  - `signInWithOAuth({ provider: 'facebook' })` for Facebook login
  - `signInWithOAuth({ provider: 'google' })` for Google login
  - Instagram OAuth supported via Facebook app
  - JWT tokens, row-level security
- **Use case**: User authentication for the platform

### 7.2 Auth.js (NextAuth.js) [OPTIONAL - alternative]
- **URL**: https://authjs.dev
- **What it does**: Authentication library for Next.js with Supabase adapter
- **Pricing**: FREE (open source)
- **Instagram provider**: Supported via `AUTH_INSTAGRAM_ID` / `AUTH_INSTAGRAM_SECRET`
- **Use case**: If you want more control over auth flow in Next.js; can work alongside Supabase

---

## 8. EXPORT & PUBLISHING

### 8.1 Instagram Graph API (Meta) [ESSENTIAL for auto-posting]
- **URL**: https://developers.facebook.com/docs/instagram-platform/content-publishing/
- **What it does**: Official API to publish posts/carousels to Instagram
- **Pricing**: FREE
- **Requirements**:
  - Business or Creator Instagram account (NOT personal)
  - Facebook Page linked to Instagram account
  - Facebook App with `instagram_content_publish` permission
  - App Review by Meta required for production use
- **Rate limits**: 100 posts/24h, 200 API calls/hour
- **Carousel publishing flow**:
  1. `POST /{ig-user-id}/media` with `is_carousel_item=true` for each slide (up to 10)
  2. `POST /{ig-user-id}/media` with `media_type=CAROUSEL` and `children=[id1,id2,...]`
  3. `POST /{ig-user-id}/media_publish` with the container ID
- **Key endpoints**:
  - `POST /{ig-user-id}/media` - Create media container
  - `POST /{ig-user-id}/media_publish` - Publish media
  - `GET /{ig-user-id}/media` - Get published media
  - `GET /{ig-media-id}/insights` - Get media insights
- **Carousel specs**: Max 10 slides, images cropped based on first image, default 1:1 ratio, images must be hosted at a public URL
- **Important**: Images must be publicly accessible URLs. Upload to Supabase Storage first, then pass URL to Graph API.

### 8.2 PDF Generation [OPTIONAL]
- **Library**: `jspdf` or `@react-pdf/renderer` (both FREE, open source)
- **URL**: https://www.npmjs.com/package/jspdf
- **Use case**: Export carousel as PDF for client review or offline sharing
- **Alternative**: Puppeteer screenshot to PDF (free)

---

## 9. ANALYTICS

### 9.1 Instagram Graph API Insights [ESSENTIAL]
- **URL**: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-media/insights/
- **What it does**: Get engagement metrics for published posts
- **Pricing**: FREE (same API as publishing)
- **Metrics available**: impressions, reach, engagement, saves, shares, comments, likes
- **Key endpoint**: `GET /{ig-media-id}/insights?metric=impressions,reach,engagement`

### 9.2 Vercel Analytics / PostHog [OPTIONAL]
- **Vercel Analytics**: Built into Vercel, free tier available
- **PostHog**: https://posthog.com - FREE up to 1M events/month
- **Use case**: Track platform usage (which templates are popular, user behavior)

---

## 10. TRANSLATION

### 10.1 DeepL API [OPTIONAL]
- **URL**: https://www.deepl.com/en/products/api
- **What it does**: High-quality AI translation, supports Korean <-> English and 33 languages
- **Pricing**:
  - Free: 500,000 characters/month
  - Pro: $5.49/month base + $25 per 1M characters
- **Key endpoint**: `POST /v2/translate` with `text`, `source_lang`, `target_lang`
- **Use case**: Translate carousel content for multi-language audiences

### 10.2 Google Cloud Translation API [OPTIONAL - alternative]
- **URL**: https://cloud.google.com/translate
- **Pricing**: Free up to 500,000 characters/month, then $20 per 1M characters
- **Use case**: Alternative to DeepL; slightly cheaper but generally lower quality for Korean

---

## 11. SEARCH & TRENDING CONTENT

### 11.1 HikerAPI Search Endpoints [ESSENTIAL - already included]
- Already covered in Section 1. Key endpoints:
  - `/v2/fbsearch/topsearch` - Trending content discovery
  - `/v2/search/hashtags` - Find trending hashtags
  - `/v2/hashtag/medias/top` - Top posts for any hashtag
  - `/v2/fbsearch/reels` - Search trending reels

### 11.2 Google Trends (Unofficial) [OPTIONAL]
- **Library**: `google-trends-api` npm package (free, unofficial)
- **Use case**: Discover trending topics for carousel content ideas

---

## COST ESTIMATE (Startup Monthly Budget)

| Category | Service | Monthly Cost (Est.) |
|----------|---------|-------------------|
| Instagram Data | HikerAPI (10K requests) | $10-$70 |
| AI/LLM | Claude Haiku 4.5 (carousel text gen) | $5-$20 |
| Image Processing | Sharp + Satori | $0 (free) |
| Stock Photos | Unsplash + Pexels | $0 (free) |
| Fonts | Google Fonts | $0 (free) |
| Storage/Auth | Supabase Pro | $25 |
| Publishing | Instagram Graph API | $0 (free) |
| Translation | DeepL Free | $0 (free tier) |
| Background Removal | remove.bg (50 free/mo) | $0 (free tier) |
| **TOTAL** | | **$40-$115/month** |

---

## PRIORITY IMPLEMENTATION ORDER

### Phase 1 - MVP (Week 1-2)
1. **Supabase** - Auth + Database + Storage (already implied by your backend)
2. **HikerAPI** - Scrape competitor posts and hashtags
3. **Claude Haiku or GPT-5 nano** - Generate carousel text content
4. **Google Fonts** - Korean typography
5. **Satori + Sharp** - Server-side image generation

### Phase 2 - Publishing (Week 3-4)
6. **Instagram Graph API** - Auto-publish carousels
7. **Unsplash/Pexels** - Stock photo integration in editor

### Phase 3 - Enhancement (Week 5+)
8. **remove.bg** - Background removal tool in editor
9. **DeepL** - Multi-language carousel generation
10. **PostHog** - Platform analytics
11. **Cloudinary** - Advanced image CDN (if needed)

---

## ENV VARIABLES NEEDED

```env
# HikerAPI
HIKERAPI_KEY=your_key_here

# AI/LLM (pick one or both)
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here

# Supabase
NEXT_PUBLIC_SUPABASE_URL=your_project_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# Instagram Graph API (Meta)
META_APP_ID=your_app_id
META_APP_SECRET=your_app_secret
INSTAGRAM_ACCESS_TOKEN=your_long_lived_token

# Stock Photos
UNSPLASH_ACCESS_KEY=your_key_here
PEXELS_API_KEY=your_key_here

# Background Removal
REMOVEBG_API_KEY=your_key_here

# Translation
DEEPL_API_KEY=your_key_here

# Google Fonts
GOOGLE_FONTS_API_KEY=your_key_here
```
