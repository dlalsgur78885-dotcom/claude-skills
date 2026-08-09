# Models — SQLAlchemy ORM

SQLAlchemy 2.0 `Mapped` 타입 + `DeclarativeBase` 패턴.

## 테이블

- `user.py` — `User` (users): id, username, password_hash, role(admin/worker)
- `channel.py` — `BenchmarkChannel` (benchmark_channels): instagram_handle, category, style_tags(JSON), is_active
- `post.py` — `CollectedPost` (collected_posts): caption, hashtags(JSON), like_count, comment_count, post_date, slide_count
- `image.py` — `PostImage` (post_images): slide_index, raw_path, processed_path, width, height
- `carousel.py` — `GeneratedCarousel` (generated_carousels): canvas_data(JSON), template_id, status(draft/editing/finalized)
- `category.py` — `Category` (categories): name, sort_order

## 관계

- User → Channels, Carousels
- Channel → Posts
- Post → Images
- Carousel → source Post (nullable)
