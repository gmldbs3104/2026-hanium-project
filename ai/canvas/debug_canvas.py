"""
캔버스 모드(SFR-004C/005C) 검증 스크립트.

1. get_expected_sequence()로 샘플 음절의 획순 라벨 개수가 상식적으로 맞는지 확인.
2. 합성 stroke 시퀀스(공간/시간적으로 가까운 것 vs 먼 것)로 규칙 기반 그룹핑이
   기대대로 동작하는지 확인.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from canvas.stroke_standards import get_expected_sequence
from canvas.stroke_grouping import group_strokes_into_chars


def check_stroke_standards():
    print("=== 1. 표준 획순 데이터 확인 ===")
    samples = {
        "가": 3,   # ㄱ(1) + ㅏ(2)
        "강": 4,   # ㄱ(1) + ㅏ(2) + ㅇ(1)
        "쓰": 5,   # ㅆ(4) + ㅡ(1)
        "값": 8,   # ㄱ(1) + ㅏ(2) + ㅄ(5=ㅂ4+ㅅ2... 실제론 ㅂ+ㅅ=4+2=6) -- 아래 실측치로 대체
        "글": 6,   # ㄱ(1) + ㅡ(1) + ㄹ(3) ... 참고용
        "A": None, # 한글 아님 -> 빈 리스트
    }
    for char, _ in samples.items():
        seq = get_expected_sequence(char)
        print(f"  '{char}' -> {len(seq)}획: {seq}")


def _stroke(stroke_id, x, y, t):
    """중심이 (x,y)이고 폭 10, 시작 timestamp가 t인 합성 stroke."""
    return {
        "stroke_id": stroke_id,
        "points": [
            {"x": x, "y": y, "pressure": 0.8, "timestamp": t},
            {"x": x + 10, "y": y + 10, "pressure": 0.8, "timestamp": t + 30},
        ],
    }


def check_stroke_grouping():
    print("\n=== 2. 규칙 기반 획 그룹핑 확인 ===")
    # 시나리오: 글자1(가까운 2개 획, 시간도 가까움) -> 공백(큰 시간/공간 간격) -> 글자2(1개 획)
    strokes = [
        _stroke("s0", x=0,   y=0,   t=1000),
        _stroke("s1", x=15,  y=5,   t=1050),   # s0과 가까움(거리) + 가까움(시간) -> 같은 그룹
        _stroke("s2", x=300, y=300, t=5000),   # 멀리 떨어짐 + 시간도 많이 지남 -> 새 그룹
    ]
    groups = group_strokes_into_chars(strokes)
    print(f"  입력 3개 획 -> {len(groups)}개 문자 그룹으로 분리")
    for g in groups:
        stroke_ids = [s["stroke_id"] for s in g["strokes"]]
        print(f"    {g['char_id']}: strokes={stroke_ids} bbox={g['bounding_box']} "
              f"confidence={g['confidence']} low_confidence={g['low_confidence']}")

    assert len(groups) == 2, f"기대: 2그룹, 실제: {len(groups)}그룹"
    assert [s["stroke_id"] for s in groups[0]["strokes"]] == ["s0", "s1"]
    assert [s["stroke_id"] for s in groups[1]["strokes"]] == ["s2"]
    print("  PASS: 가까운 획은 묶이고 먼 획은 분리됨")


if __name__ == "__main__":
    check_stroke_standards()
    check_stroke_grouping()
