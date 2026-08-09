import type { SlideData } from "./types";

export function createEmptySlide(
  width = 1080,
  height = 1080,
  background = "#FFFFFF"
): SlideData {
  return {
    version: "6.0.0",
    width,
    height,
    background,
    objects: [],
  };
}

export function createCoverSlide(
  title = "제목을 입력하세요",
  subtitle = "부제목"
): SlideData {
  return {
    version: "6.0.0",
    width: 1080,
    height: 1080,
    background: "#FFFFFF",
    objects: [
      {
        type: "textbox",
        left: 100,
        top: 400,
        width: 880,
        text: title,
        fontSize: 48,
        fontFamily: "Pretendard, sans-serif",
        fontWeight: "bold",
        fill: "#1A1A1A",
        textAlign: "center",
      },
      {
        type: "textbox",
        left: 100,
        top: 520,
        width: 880,
        text: subtitle,
        fontSize: 24,
        fontFamily: "Pretendard, sans-serif",
        fill: "#666666",
        textAlign: "center",
      },
    ],
  };
}

export function createCtaSlide(
  headline = "더 알아보기",
  ctaText = "팔로우하고 더 많은 정보를 받아보세요"
): SlideData {
  return {
    version: "6.0.0",
    width: 1080,
    height: 1080,
    background: "#1A1A1A",
    objects: [
      {
        type: "textbox",
        left: 100,
        top: 380,
        width: 880,
        text: headline,
        fontSize: 40,
        fontFamily: "Pretendard, sans-serif",
        fontWeight: "bold",
        fill: "#FFFFFF",
        textAlign: "center",
      },
      {
        type: "textbox",
        left: 100,
        top: 500,
        width: 880,
        text: ctaText,
        fontSize: 24,
        fontFamily: "Pretendard, sans-serif",
        fill: "#CCCCCC",
        textAlign: "center",
      },
    ],
  };
}

export async function exportSlideAsPng(
  canvas: unknown
): Promise<string | null> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fabricCanvas = canvas as any;
  if (!fabricCanvas?.toDataURL) return null;
  return fabricCanvas.toDataURL({
    format: "png",
    quality: 1,
    multiplier: 1,
  });
}

export function downloadDataUrl(dataUrl: string, filename: string) {
  const link = document.createElement("a");
  link.download = filename;
  link.href = dataUrl;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
