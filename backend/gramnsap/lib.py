from curl_cffi import AsyncSession
from dataclasses import dataclass, field
from fake_useragent import UserAgent
from enum import Enum, auto
import hashlib
import json
import time
import asyncio


class ErrorWhenFetchingPosts(Exception):
    def __init__(self, posts: list["Output"]):
        self.posts = posts
        super().__init__(f"Failed to fetch posts (collected {len(posts)} before failure)")


class MediaType(Enum):
    IMAGE = auto()
    VIDEO = auto()
    SIDECAR = auto()

    @classmethod
    def from_typename(cls, typename: str) -> "MediaType":
        return _TYPENAME_MAP[typename]


_TYPENAME_MAP = {
    "GraphImage": MediaType.IMAGE,
    "GraphVideo": MediaType.VIDEO,
    "GraphSidecar": MediaType.SIDECAR,
}

_MEDIA_TYPE_MAP = {
    1: MediaType.IMAGE,
    2: MediaType.VIDEO,
    8: MediaType.SIDECAR,
}


@dataclass
class Media:
    id: str
    typename: MediaType
    is_video: bool
    display_url: str
    width: int
    height: int
    video_url: str | None = None

    @classmethod
    def from_v2(cls, d: dict) -> "Media":
        return cls(
            id=d["id"],
            typename=MediaType.from_typename(d["__typename"]),
            is_video=d.get("is_video", False),
            display_url=d["display_url"],
            width=d["dimensions"]["width"],
            height=d["dimensions"]["height"],
            video_url=d.get("video_url"),
        )

    @classmethod
    def from_v1(cls, d: dict) -> "Media":
        mt = _MEDIA_TYPE_MAP.get(d.get("media_type", 1), MediaType.IMAGE)
        is_video = mt == MediaType.VIDEO
        img = d.get("image_versions2", {}).get("candidates", [{}])[0]
        vid = d.get("video_versions", [{}])[0] if is_video else {}
        return cls(
            id=str(d["pk"]),
            typename=mt,
            is_video=is_video,
            display_url=img.get("url", ""),
            width=d.get("original_width", img.get("width", 0)),
            height=d.get("original_height", img.get("height", 0)),
            video_url=vid.get("url"),
        )


@dataclass
class PostsResult:
    posts: list["Output"]

    def __iter__(self):
        return iter(self.posts)

    def __len__(self):
        return len(self.posts)


@dataclass
class Output:
    id: str
    shortcode: str
    typename: MediaType
    is_video: bool
    display_url: str
    width: int
    height: int
    caption: str
    likes: int
    comments: int
    timestamp: int
    video_url: str | None = None
    video_views: int | None = None
    children: list[Media] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"https://www.instagram.com/p/{self.shortcode}/"

    @classmethod
    def from_v2(cls, d: dict) -> "Output":
        node = d["node"] if "node" in d else d
        caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
        caption = caption_edges[0]["node"]["text"] if caption_edges else ""
        sidecar = node.get("edge_sidecar_to_children", {})
        children = [Media.from_v2(e["node"]) for e in sidecar.get("edges", [])] if sidecar else []
        return cls(
            id=node["id"],
            shortcode=node["shortcode"],
            typename=MediaType.from_typename(node["__typename"]),
            is_video=node.get("is_video", False),
            display_url=node["display_url"],
            width=node["dimensions"]["width"],
            height=node["dimensions"]["height"],
            caption=caption,
            likes=node.get("edge_media_preview_like", {}).get("count", 0),
            comments=node.get("edge_media_to_comment", {}).get("count", 0),
            timestamp=node["taken_at_timestamp"],
            video_url=node.get("video_url"),
            video_views=node.get("video_view_count"),
            children=children,
        )

    @classmethod
    def from_v1(cls, d: dict) -> "Output":
        node = d["node"] if "node" in d else d
        mt = _MEDIA_TYPE_MAP.get(node.get("media_type", 1), MediaType.IMAGE)
        is_video = mt == MediaType.VIDEO
        img = node.get("image_versions2", {}).get("candidates", [{}])[0]
        vid = node.get("video_versions", [{}])[0] if is_video else {}
        cap = node.get("caption") or {}
        children = [Media.from_v1(c) for c in (node.get("carousel_media") or [])]
        return cls(
            id=str(node["pk"]),
            shortcode=node["code"],
            typename=mt,
            is_video=is_video,
            display_url=img.get("url", ""),
            width=node.get("original_width", img.get("width", 0)),
            height=node.get("original_height", img.get("height", 0)),
            caption=cap.get("text", "") if isinstance(cap, dict) else "",
            likes=node.get("like_count", 0),
            comments=node.get("comment_count", 0),
            timestamp=node.get("taken_at", 0),
            video_url=vid.get("url"),
            video_views=node.get("view_count"),
            children=children,
        )


class GramSnap:
    def __init__(self, proxy: str | None = None):
        proxies = {"http": proxy, "https": proxy} if proxy else None
        self.session = AsyncSession(impersonate="chrome", proxies=proxies)
        ua = UserAgent(os="Windows", browsers="Chrome")
        self.session.headers.update({
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": "https://gramsnap.com",
            "referer": "https://gramsnap.com/en/instagram-profile-viewer/",
            "user-agent": ua.random,
        })

    async def close(self):
        await self.session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

    _SECRET = "34e4d4eb0f74189073c8be297e8bcc002bdff6ddce2fda624e45363a5d6c589d"
    _TS = 1773739557351
    _TSC = 0

    def __sign(self, body: dict) -> dict:
        ts = int(time.time() * 1000) - self._TSC
        raw = json.dumps(body, separators=(",", ":"), sort_keys=True) + str(ts) + self._SECRET
        _s = hashlib.sha256(raw.encode()).hexdigest()
        return {**body, "ts": ts, "_ts": self._TS, "_tsc": self._TSC, "_s": _s}

    _RETRY_DELAY = 2

    async def __request(self, url: str, body: dict, retry: int):
        attempt = 0
        while True:
            resp = await self.session.post(url, json=self.__sign(body))
            if resp.status_code == 502 and (retry == -1 or attempt < retry):
                attempt += 1
                await asyncio.sleep(self._RETRY_DELAY)
                continue
            return resp

    async def __posts_v2(self, username: str, retry: int, until_shortcode: str | None = None) -> list[Output] | None:
        posts, max_id = [], ""
        while True:
            resp = await self.__request(
                "https://gramsnap.com/api/v1/instagram/postsV2",
                {"username": username, "maxId": max_id}, retry,
            )
            if resp.status_code == 502:
                raise ErrorWhenFetchingPosts(posts)
            resp.raise_for_status()
            data = resp.json() or {}
            if data.get("success") is False:
                return None
            result = data.get("result", {}) or {}
            edges = result.get("edges", [])
            if not edges:
                break
            page = [Output.from_v2(e) for e in edges]
            posts.extend(page)
            if until_shortcode and any(p.shortcode == until_shortcode for p in page):
                break
            if not result.get("page_info", {}).get("has_next_page"):
                break
            max_id = result["page_info"]["end_cursor"]
        return posts

    async def __posts_v1(self, username: str, retry: int, until_shortcode: str | None = None) -> list[Output]:
        posts, max_id = [], ""
        while True:
            resp = await self.__request(
                "https://gramsnap.com/api/v1/instagram/posts",
                {"username": username, "maxId": max_id}, retry,
            )
            if resp.status_code == 502:
                raise ErrorWhenFetchingPosts(posts)
            resp.raise_for_status()
            result = (resp.json() or {}).get("result", {}) or {}
            edges = result.get("edges", [])
            if not edges:
                break
            page = [Output.from_v1(e) for e in edges]
            posts.extend(page)
            if until_shortcode and any(p.shortcode == until_shortcode for p in page):
                break
            if not result.get("page_info", {}).get("has_next_page"):
                break
            max_id = result["page_info"]["end_cursor"]
        return posts

    async def posts(self, username: str, retry: int = 3, until_shortcode: str | None = None) -> PostsResult:
        # v2 only exits its loop on until_shortcode, an empty page, or the last
        # page — so a non-empty result is always a complete crawl. Missing the
        # until_shortcode just means that post is gone from Instagram; falling
        # through to v1 there would re-crawl the whole profile a second time.
        v2 = await self.__posts_v2(username, retry, until_shortcode)
        if v2:
            return PostsResult(posts=v2)
        v1 = await self.__posts_v1(username, retry, until_shortcode)
        return PostsResult(posts=v1)
    
async def main():
    async with GramSnap() as gramsnap:
        posts = await gramsnap.posts("ksmartboi")
        for p in posts:
            if not p.typename == MediaType.VIDEO: continue
            print(f"[{p.typename.name}] likes={p.likes} url={p.url}")

if __name__ == "__main__":
    asyncio.run(main())