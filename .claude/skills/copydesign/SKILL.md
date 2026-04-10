---
name: copydesign
description: 디자인 스크린샷을 분석하여 CSS 변수, 컬러 팔레트, 타이포그래피, 간격 체계를 추출합니다.
argument-hint: [이미지 경로]
allowed-tools: Read Bash
---

# 디자인 분석

`$ARGUMENTS` 스크린샷을 분석하여 디자인 시스템을 추출합니다.

## 분석 항목

### 1. 색상 시스템
- 메인 컬러 (Primary)
- 보조 컬러 (Secondary)
- 배경색 (기본 / 카드 / 구분)
- 텍스트 색상 3단계 (제목 / 본문 / 보조)
- 구분선 색상
- 상태 색상 (성공 / 경고 / 에러)

### 2. 타이포그래피
- 폰트 패밀리 (추정)
- 크기 단계 (xs / sm / base / md / lg / xl)
- 각 단계별 font-weight
- line-height
- letter-spacing

### 3. 간격 체계
- 카드 내부 패딩
- 카드 간 간격 (gap)
- 섹션 간 구분 방식 (선 / 간격 / 배경색)
- 아이템 간 간격

### 4. 모서리 & 그림자
- border-radius 단계 (sm / md / lg)
- box-shadow 사용 여부 및 값
- border 사용 패턴

### 5. 컴포넌트 패턴
- 버튼: 크기, radius, 색상, 전체너비 여부
- 카드: padding, radius, 구분 방식
- 헤더: 높이, 구조
- 네비게이션: 높이, 아이콘 크기
- 리스트 아이템: 높이, 패딩, 구분선

### 6. 레이아웃
- max-width (앱 컨테이너)
- 전체 배경 vs 카드 배경 차이
- 고정 영역 (헤더, 탭, 하단네비)

## 출력 형식

분석 결과를 바로 사용할 수 있는 CSS 변수로 출력:

```css
:root {
  /* 색상 */
  --color-primary: #...;
  --color-primary-hover: #...;
  --color-danger: #...;
  --color-black: #...;
  --color-dark: #...;
  --color-gray: #...;
  --color-light-gray: #...;
  --color-border: ...;
  --color-bg: #...;
  --color-bg-secondary: #...;

  /* 타이포그래피 */
  --font-xs: ...rem;
  --font-sm: ...rem;
  --font-base: ...rem;
  --font-md: ...rem;
  --font-lg: ...rem;
  --font-xl: ...rem;

  /* 모서리 */
  --radius-sm: ...px;
  --radius-md: ...px;
  --radius-lg: ...px;

  /* 레이아웃 */
  --header-height: ...px;
  --bottom-nav-height: ...px;
  --max-width: ...px;
}

/* 다크 모드 */
[data-theme='dark'] {
  --color-bg: #...;
  --color-bg-secondary: #...;
  --color-black: #...;
  --color-dark: #...;
  --color-gray: #...;
  --color-border: ...;
}
```

추가로 **디자인 핵심 원칙 3줄 요약**을 제공합니다.
