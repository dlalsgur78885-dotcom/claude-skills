---
name: copydesign
description: 디자인 스크린샷 또는 URL에서 CSS 변수, 컬러 팔레트, 타이포그래피, 간격 체계를 추출합니다.
argument-hint: [이미지 경로 또는 URL]
allowed-tools: Read Bash
---

# 디자인 분석

`$ARGUMENTS` 를 분석하여 디자인 시스템을 추출합니다.

## 입력 판별

인자를 확인하여 모드를 결정합니다:
- **URL** (http로 시작): URL 모드 → Playwright로 실제 CSS 추출 + 스크린샷 자동 캡처
- **이미지 경로**: 스크린샷 모드 → AI 시각 분석
- **URL + 이미지 경로 둘 다**: 하이브리드 모드 → 실제 CSS 추출 + 스크린샷 교차 검증

## URL 모드 실행 절차

URL이 포함된 경우 아래 스크립트를 실행하여 실측 데이터를 수집합니다.
스크립트 경로: 이 SKILL.md와 같은 디렉토리의 `extract_styles.py`

```bash
# 1단계: 라이트모드 데스크탑
python <skill_dir>/extract_styles.py "<URL>" > /tmp/copydesign_desktop_light.json

# 2단계: 다크모드 데스크탑
python <skill_dir>/extract_styles.py "<URL>" --dark > /tmp/copydesign_desktop_dark.json

# 3단계: 모바일 라이트
python <skill_dir>/extract_styles.py "<URL>" --mobile > /tmp/copydesign_mobile_light.json
```

`<skill_dir>`은 이 SKILL.md 파일이 위치한 디렉토리의 절대 경로로 치환합니다.

3개 JSON 결과 + 자동 캡처된 스크린샷(`/tmp/copydesign_*.png`)을 모두 읽어서 종합 분석합니다.

## 분석 항목

### 1. 색상 시스템
- **URL 모드**: 실제 computed style에서 추출한 정확한 hex 값 사용
- **스크린샷 모드**: AI 추론 (근사값, `~` 접두어 표기)
- 메인 컬러 (Primary) + hover/active 상태
- 보조 컬러 (Secondary)
- 배경색 (기본 / 카드 / 구분)
- 텍스트 색상 3단계 (제목 / 본문 / 보조)
- 구분선 색상
- 상태 색상 (성공 / 경고 / 에러)

### 2. 타이포그래피
- **URL 모드**: 실제 font-family, font-size, font-weight, line-height 정확값
- **스크린샷 모드**: 추정값
- 폰트 패밀리
- 크기 단계 (xs / sm / base / md / lg / xl)
- 각 단계별 font-weight
- line-height
- letter-spacing

### 3. 간격 체계
- **URL 모드**: 실제 padding, margin, gap 값
- 카드 내부 패딩
- 카드 간 간격 (gap)
- 섹션 간 구분 방식 (선 / 간격 / 배경색)
- 아이템 간 간격

### 4. 모서리 & 그림자
- border-radius 단계 (sm / md / lg) — URL 모드에서 실측
- box-shadow 실측값
- border 사용 패턴

### 5. 컴포넌트 패턴
- 버튼: 크기, radius, 색상, hover/active/disabled 상태, 전체너비 여부
- 카드: padding, radius, 구분 방식
- 인풋: padding, border, radius, placeholder 색상
- 헤더: 높이, 구조
- 네비게이션: 높이, 아이콘 크기
- 리스트 아이템: 높이, 패딩, 구분선

### 6. 레이아웃 & 반응형
- max-width (앱 컨테이너)
- 전체 배경 vs 카드 배경 차이
- 고정 영역 (헤더, 탭, 하단네비)
- **URL 모드**: 데스크탑 vs 모바일 차이 비교

## 출력 형식

분석 결과를 바로 사용할 수 있는 CSS 변수로 출력합니다.
URL 모드에서 추출한 값은 정확값, 스크린샷 추론값은 `/* ~추정 */` 주석을 붙입니다.

```css
:root {
  /* 색상 */
  --color-primary: #...;
  --color-primary-hover: #...;
  --color-primary-active: #...;
  --color-secondary: #...;
  --color-danger: #...;
  --color-success: #...;
  --color-warning: #...;
  --color-black: #...;
  --color-dark: #...;
  --color-gray: #...;
  --color-light-gray: #...;
  --color-border: ...;
  --color-bg: #...;
  --color-bg-secondary: #...;
  --color-bg-card: #...;

  /* 타이포그래피 */
  --font-family: '...', sans-serif;
  --font-xs: ...rem;
  --font-sm: ...rem;
  --font-base: ...rem;
  --font-md: ...rem;
  --font-lg: ...rem;
  --font-xl: ...rem;
  --line-height-tight: ...;
  --line-height-normal: ...;
  --line-height-relaxed: ...;

  /* 모서리 */
  --radius-sm: ...px;
  --radius-md: ...px;
  --radius-lg: ...px;
  --radius-full: 9999px;

  /* 그림자 */
  --shadow-sm: ...;
  --shadow-md: ...;
  --shadow-lg: ...;

  /* 간격 */
  --spacing-xs: ...px;
  --spacing-sm: ...px;
  --spacing-md: ...px;
  --spacing-lg: ...px;
  --spacing-xl: ...px;

  /* 레이아웃 */
  --header-height: ...px;
  --bottom-nav-height: ...px;
  --max-width: ...px;
}

/* 다크 모드 */
[data-theme='dark'] {
  --color-bg: #...;
  --color-bg-secondary: #...;
  --color-bg-card: #...;
  --color-black: #...;
  --color-dark: #...;
  --color-gray: #...;
  --color-border: ...;
}

/* 반응형 (URL 모드에서 모바일 캡처 기반) */
@media (max-width: 768px) {
  :root {
    --font-lg: ...rem;
    --font-xl: ...rem;
    --spacing-lg: ...px;
    --spacing-xl: ...px;
  }
}
```

추가로 **디자인 핵심 원칙 3줄 요약**과 **데이터 신뢰도 표시**(실측/추정)를 제공합니다.
