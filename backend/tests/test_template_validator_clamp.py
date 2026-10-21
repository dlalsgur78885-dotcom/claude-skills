"""편집기 저장(PATCH)이 좌표·크기를 건드리지 않는지 — 회귀 테스트.

재현한 사고(2026-10-21): 사람이 템플릿 스튜디오에서 사진·글상자를 끌거나 방향키로
옮기면 자동저장 때마다 서버가 캔버스 안으로 잘라 넣어 「자꾸 어긋났다」.
수치는 prod 템플릿 96(트립앤라이프 종합)의 실측 값이다.

실행: cd backend && python -m pytest tests/test_template_validator_clamp.py -q
"""

from app.services.template_validator import validate_and_fix_template

CANVAS = {"width": 1080, "height": 1350}


def _tpl(decorations=(), text_slots=()):
    return {
        "canvas": dict(CANVAS),
        "layouts": {
            "본문": {
                "background": {"type": "color", "value": "#000000"},
                "decorations": list(decorations),
                "text_slots": list(text_slots),
            }
        },
    }


def _hand_save(tpl):
    """편집기 자동저장이 쓰는 조합."""
    return validate_and_fix_template(tpl, deoverlap=False, clamp=False)


def test_hand_save_keeps_full_bleed_photo_width():
    """꽉 찬 사진을 오른쪽으로 10px — 폭이 깎이면 안 된다 (1080 → 1070 이었다)."""
    tpl = _tpl(decorations=[{
        "kind": "image", "src": "/x.png",
        "position": {"x": 10, "y": 0, "anchor": "top-left"},
        "size": {"width": 1080, "height": 1350},
    }])

    out = _hand_save(tpl)

    dec = out["layouts"]["본문"]["decorations"][0]
    assert (dec["position"]["x"], dec["size"]["width"]) == (10, 1080)


def test_hand_save_keeps_negative_position():
    """캔버스 밖으로 걸쳐 놓은 것을 0 으로 되돌리지 않는다."""
    tpl = _tpl(decorations=[{
        "kind": "shape",
        "position": {"x": -40, "y": -20, "anchor": "top-left"},
        "size": {"width": 400, "height": 200},
    }])

    out = _hand_save(tpl)

    pos = out["layouts"]["본문"]["decorations"][0]["position"]
    assert (pos["x"], pos["y"]) == (-40, -20)


def test_hand_save_keeps_caption_box_height():
    """아래쪽 자막 글상자를 20px 내렸을 때 높이가 줄면 안 된다 (110 → 90 이었다)."""
    tpl = _tpl(text_slots=[{
        "role": "caption",
        "position": {"x": 60, "y": 1260, "anchor": "top-left"},
        "size": {"width": 960, "height": 110},
    }])

    out = _hand_save(tpl)

    slot = out["layouts"]["본문"]["text_slots"][0]
    assert (slot["position"]["y"], slot["size"]["height"]) == (1260, 110)


def test_generate_time_still_clamps():
    """생성 단계(Gemini 출력)에선 그대로 캔버스 안으로 잘라 넣는다."""
    tpl = _tpl(decorations=[{
        "kind": "image", "src": "/x.png",
        "position": {"x": 10, "y": 0, "anchor": "top-left"},
        "size": {"width": 1080, "height": 1350},
    }])

    out = validate_and_fix_template(tpl)

    assert out["layouts"]["본문"]["decorations"][0]["size"]["width"] == 1070
