"use client";

import { PostsExplorer } from "@/components/PostsExplorer";

// 캐러셀과 릴스는 사이드바에서 갈라진 별도 라우트다. 목록 화면 자체는 같아서
// PostsExplorer 하나를 공유하고 mediaType 으로만 구분한다.
export default function PostsPage() {
  return <PostsExplorer mediaType="carousel" />;
}
