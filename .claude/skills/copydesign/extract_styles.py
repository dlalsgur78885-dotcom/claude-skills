"""
URL에서 실제 computed style을 추출하는 Playwright 스크립트.
사용: python extract_styles.py <URL> [--dark] [--mobile]
출력: JSON (색상, 폰트, 간격, 반응형 등)
"""
import json
import sys
import argparse
from playwright.sync_api import sync_playwright


JS_EXTRACT = """
() => {
    const result = { colors: {}, fonts: {}, spacing: {}, borders: {}, shadows: {}, layout: {} };
    const colorMap = {};
    const fontSet = new Set();
    const fontSizes = new Set();
    const fontWeights = new Set();
    const radiusSet = new Set();
    const shadowSet = new Set();

    // CSS 변수 수집 (루트)
    const rootStyles = getComputedStyle(document.documentElement);
    const cssVars = {};
    for (const sheet of document.styleSheets) {
        try {
            for (const rule of sheet.cssRules) {
                if (rule.selectorText === ':root' || rule.selectorText === ':root, :host') {
                    for (const prop of rule.style) {
                        if (prop.startsWith('--')) {
                            cssVars[prop] = rule.style.getPropertyValue(prop).trim();
                        }
                    }
                }
            }
        } catch(e) {} // cross-origin sheets
    }
    result.cssVariables = cssVars;

    // hover/focus 등 상태 스타일 수집
    const pseudoStyles = [];
    for (const sheet of document.styleSheets) {
        try {
            for (const rule of sheet.cssRules) {
                const sel = rule.selectorText || '';
                if (sel.includes(':hover') || sel.includes(':focus') || sel.includes(':active') || sel.includes(':disabled')) {
                    const props = {};
                    for (const prop of rule.style) {
                        props[prop] = rule.style.getPropertyValue(prop).trim();
                    }
                    if (Object.keys(props).length > 0) {
                        pseudoStyles.push({ selector: sel, properties: props });
                    }
                }
            }
        } catch(e) {}
    }
    result.interactionStates = pseudoStyles.slice(0, 50); // 상위 50개

    // 주요 요소 순회
    const elements = document.querySelectorAll('body, body *');
    const sampled = Array.from(elements).slice(0, 500); // 성능 제한

    for (const el of sampled) {
        const cs = getComputedStyle(el);
        const tag = el.tagName.toLowerCase();
        const cls = el.className?.toString?.() || '';

        // 색상 수집
        const bgColor = cs.backgroundColor;
        const textColor = cs.color;
        const borderColor = cs.borderColor;

        if (bgColor && bgColor !== 'rgba(0, 0, 0, 0)') {
            colorMap[bgColor] = (colorMap[bgColor] || 0) + 1;
        }
        if (textColor) {
            colorMap[textColor] = (colorMap[textColor] || 0) + 1;
        }

        // 폰트 수집
        fontSet.add(cs.fontFamily);
        fontSizes.add(cs.fontSize);
        fontWeights.add(cs.fontWeight);

        // border-radius
        const radius = cs.borderRadius;
        if (radius && radius !== '0px') {
            radiusSet.add(radius);
        }

        // box-shadow
        const shadow = cs.boxShadow;
        if (shadow && shadow !== 'none') {
            shadowSet.add(shadow);
        }

        // 주요 컴포넌트별 스타일 캡처
        if (tag === 'button' || cls.includes('btn') || el.getAttribute('role') === 'button') {
            if (!result.components) result.components = {};
            if (!result.components.buttons) result.components.buttons = [];
            if (result.components.buttons.length < 5) {
                result.components.buttons.push({
                    text: el.textContent?.trim().slice(0, 30),
                    bg: cs.backgroundColor,
                    color: cs.color,
                    fontSize: cs.fontSize,
                    fontWeight: cs.fontWeight,
                    padding: cs.padding,
                    borderRadius: cs.borderRadius,
                    border: cs.border,
                    width: cs.width
                });
            }
        }

        if (tag === 'nav' || cls.includes('nav') || cls.includes('header')) {
            if (!result.components) result.components = {};
            if (!result.components.nav) {
                result.components.nav = {
                    height: cs.height,
                    bg: cs.backgroundColor,
                    padding: cs.padding,
                    position: cs.position
                };
            }
        }

        if (tag === 'input' || tag === 'textarea') {
            if (!result.components) result.components = {};
            if (!result.components.inputs) result.components.inputs = [];
            if (result.components.inputs.length < 3) {
                result.components.inputs.push({
                    bg: cs.backgroundColor,
                    color: cs.color,
                    border: cs.border,
                    borderRadius: cs.borderRadius,
                    padding: cs.padding,
                    fontSize: cs.fontSize
                });
            }
        }
    }

    // 빈도순 색상 정렬
    result.colors = Object.entries(colorMap)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 20)
        .map(([color, count]) => ({ color, count }));

    result.fonts = {
        families: [...fontSet].slice(0, 10),
        sizes: [...fontSizes].sort(),
        weights: [...fontWeights].sort()
    };
    result.borders = { radii: [...radiusSet] };
    result.shadows = [...shadowSet].slice(0, 10);

    // 레이아웃
    const body = document.body;
    const main = document.querySelector('main') || document.querySelector('[role="main"]') || body.firstElementChild;
    if (main) {
        const mcs = getComputedStyle(main);
        result.layout = {
            maxWidth: mcs.maxWidth,
            padding: mcs.padding,
            margin: mcs.margin
        };
    }
    result.viewport = { width: window.innerWidth, height: window.innerHeight };

    return result;
}
"""


def extract(url, dark=False, mobile=False):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context_opts = {}
        if mobile:
            context_opts = {
                "viewport": {"width": 390, "height": 844},
                "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
                "device_scale_factor": 3,
            }
        else:
            context_opts = {"viewport": {"width": 1440, "height": 900}}

        if dark:
            context_opts["color_scheme"] = "dark"

        context = browser.new_context(**context_opts)
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        # 스크린샷 저장
        mode = "dark" if dark else "light"
        device = "mobile" if mobile else "desktop"
        screenshot_path = f"/tmp/copydesign_{device}_{mode}.png"
        page.screenshot(path=screenshot_path, full_page=True)

        # computed style 추출
        data = page.evaluate(JS_EXTRACT)
        data["meta"] = {"url": url, "mode": mode, "device": device, "screenshot": screenshot_path}

        browser.close()
        return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--dark", action="store_true")
    parser.add_argument("--mobile", action="store_true")
    args = parser.parse_args()

    data = extract(args.url, dark=args.dark, mobile=args.mobile)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
