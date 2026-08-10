import { api } from "./api";
import { createEmptySlide } from "./canvas-utils";

/** 빈 캐러셀을 만들고 그 id 를 돌려준다 (피드백 1).
 *
 *  경쟁사 URL 이 없으면 캐러셀을 아예 시작할 수 없었다. 참고할 게 없거나 직접 처음부터
 *  그리고 싶을 때 쓰는 길이다.
 *
 *  에디터는 **저장된** 캐러셀을 여는 화면이라(마운트하자마자 getCarousel 을 부른다)
 *  "빈 문서" 라는 화면 상태가 따로 없다. 그래서 진짜 행을 하나 만들고 그리로 보낸다 —
 *  대시보드에 오래 걸려 있던 `/editor/new` 링크가 늘 깨졌던 이유도 이것이다.
 *
 *  source_slides 가 없으므로 에디터의 "템플릿 변경"은 비활성으로 뜬다. 원본 슬라이드에서
 *  다시 그리는 기능이라 빈 문서에는 적용할 대상이 없다 — 의도된 동작이다.
 */
export async function createBlankCarousel(): Promise<number> {
  const carousel = await api.createCarousel({
    title: "제목 없는 캐러셀",
    canvas_data: { canvas_slides: [createEmptySlide()] },
  });
  return carousel.id;
}
