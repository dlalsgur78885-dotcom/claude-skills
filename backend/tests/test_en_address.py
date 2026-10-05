"""일본맛집 📍위치 한 줄 — 우편번호·층·호수·건물을 뺀다(2026-09-22 사람 지시).

입력은 전부 구글(리뷰 벤더 meta.address)이 실제로 준 값이다.
"""
import pytest

from app.services.place_lookup import en_address_lines, strip_postal_floor


@pytest.mark.parametrize("raw, want", [
    # 순서가 거꾸로 오고, 번지 뒤에 건물·층이 붙는다.
    ("Japan, 〒030-0801 Aomori, Shinmachi, 1 Chome−3−7 アウガ 地下 1F",
     "1 Chome-3-7 Shinmachi, Aomori"),
    ("Japan, 〒150-0041 Tokyo, Shibuya, Jinnan, 1 Chome−22−7 岩本ビル B1F",
     "1 Chome-22-7 Jinnan, Shibuya, Tokyo"),
    ("Japan, 〒151-0066 Tokyo, Shibuya, Nishihara, 3 Chome−2−4 フロンティア代々木上原 B1",
     "3 Chome-2-4 Nishihara, Shibuya, Tokyo"),
    ("Japan, 〒605-0073 Kyoto, Higashiyama Ward, Gionmachi Kitagawa, 329 1 階D号",
     "329 Gionmachi Kitagawa, Higashiyama Ward, Kyoto"),
    ("Japan, 〒604-8041 Kyoto, Nakagyo Ward, Uraderacho, 598",
     "598 Uraderacho, Nakagyo Ward, Kyoto"),
    # 바른 순서 — 우편번호만 떼면 된다.
    ("570-127 Gionmachi Minamigawa, Higashiyama Ward, Kyoto, 605-0074, Japan",
     "570-127 Gionmachi Minamigawa, Higashiyama Ward, Kyoto"),
    ("1 Chome-29-11 Asakusa, 台東区 Taito City, Tokyo 111-0032, Japan",
     "1 Chome-29-11 Asakusa, Taito City, Tokyo"),
    # 바른 순서인데 앞에 층이 따로 붙어 온다.
    ("1F, 2 Chome-2-1 Honmachi, Kanazawa, Ishikawa 920-0853, Japan",
     "2 Chome-2-1 Honmachi, Kanazawa, Ishikawa"),
])
def test_en_address_drops_postal_floor_unit(raw, want):
    assert en_address_lines(raw) == want


def test_en_address_empty():
    assert en_address_lines("") == ""


# 지도 축 — 가이드 주소 글자는 그대로 두고 우편번호·층·호수만 뗀다(2026-09-22 사람 지시).
# 입력은 트래블어시 가이드·지침서에 실제로 있던 값이다.
@pytest.mark.parametrize("raw, want", [
    ("📍〒104-0061 東京都中央区\n銀座4-13-17 高野ビル1F", "📍東京都中央区\n銀座4-13-17 高野ビル"),
    ("📍〒604-8055 京都市中京区錦小路通富小路西入東魚屋町182", "📍京都市中京区錦小路通富小路西入東魚屋町182"),
    ("📍〒160-0022 東京都新宿区新宿2-4-1 1階105", "📍東京都新宿区新宿2-4-1"),
    ("📍4 Chome-14 Kotabe Sawara Ward, Fukuoka, 814-0032", "📍4 Chome-14 Kotabe Sawara Ward, Fukuoka"),
    ("📍8 Chome Kitakoiwa 江戸川区 Tokyo 133-0051", "📍8 Chome Kitakoiwa 江戸川区 Tokyo"),
    ("📍서울특별시 강남구 도산대로 457 앙스돔빌딩 3층", "📍서울특별시 강남구 도산대로 457 앙스돔빌딩"),
    ("📍서울특별시 종로구 경희궁길 36 8 층", "📍서울특별시 종로구 경희궁길 36"),
    ("📍서울특별시 강남구 학동로17길 13", "📍서울특별시 강남구 학동로17길 13"),
])
def test_strip_postal_floor(raw, want):
    assert strip_postal_floor(raw) == want
