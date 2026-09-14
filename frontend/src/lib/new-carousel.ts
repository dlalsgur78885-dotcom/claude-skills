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
 *  ⚠ 예전엔 `source_slides` 를 안 남겼고, 그래서 에디터의 "템플릿 변경"이 잠겨 있었다.
 *    주석에는 "의도된 동작" 이라고 적혀 있었지만 실제로는 막힌 길이었다 —
 *    참고 글 없이 새 파일을 만든 사람은 **템플릿을 아예 못 씌운다**(2026-09-03 피드백 1·2번,
 *    두 건이 같은 원인이었다). 빈 원본이라도 남겨 두면 템플릿을 씌우고 그 위에 글을 채울 수 있다.
 */
export async function createBlankCarousel(): Promise<number> {
  const carousel = await api.createCarousel({
    title: "제목 없는 캐러셀",
    canvas_data: {
      canvas_slides: [createEmptySlide()],
      // 글자는 비어 있어도 **자리**는 있어야 한다. 렌더러가 이걸 보고 낱장을 그린다.
      source_slides: [{ index: 0, type: "cover", headline: "", subtext: "", body: "", tag: "" }],
    },
  });
  return carousel.id;
}
