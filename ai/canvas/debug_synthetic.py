"""
합성 stroke 생성기 검증.

1. 샘플 음절 몇 개를 이미지로 렌더링해서 대략 글자처럼 보이는지 육안 확인.
2. 여러 글자로 된 문자열을 생성해서 stroke_grouping.py의 규칙 기반 그룹핑이
   글자 경계를 올바르게 분리하는지(생성기가 넣은 글자 간 시간/공간 간격이
   grouping 임계값을 실제로 넘는지) 확인 — 생성→그룹핑 라운드트립 테스트.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import cv2
import numpy as np

from canvas.synthetic_stroke_generator import generate_synthetic_strokes, generate_synthetic_line
from canvas.stroke_grouping import group_strokes_into_chars
from canvas.stroke_standards import get_expected_sequence


def render_strokes(strokes, out_path, canvas_size=(300, 200), margin=20):
    img = np.full((canvas_size[1], canvas_size[0], 3), 255, dtype=np.uint8)
    for stroke in strokes:
        pts = [(int(p["x"]) + margin, int(p["y"]) + margin) for p in stroke["points"]]
        for i in range(len(pts) - 1):
            cv2.line(img, pts[i], pts[i + 1], (0, 0, 0), 2, cv2.LINE_AA)
        for p in pts:
            cv2.circle(img, p, 1, (0, 0, 200), -1)
    # cv2.imwrite는 Windows에서 한글 경로를 못 씀(image_preprocessor.py의 파일 로드와
    # 동일한 문제) -> imencode 후 직접 바이트로 저장.
    ok, buf = cv2.imencode(".png", img)
    with open(out_path, "wb") as f:
        f.write(buf.tobytes())


def check_rendering():
    print("=== 1. 샘플 음절 렌더링 ===")
    out_dir = "../debug_output/synthetic_check"
    os.makedirs(out_dir, exist_ok=True)
    samples = ["가", "강", "쓰", "값", "글", "한", "이", "음"]
    for char in samples:
        strokes, _ = generate_synthetic_strokes(char, origin=(20, 20), scale=150)
        expected = get_expected_sequence(char)
        out_path = os.path.join(out_dir, f"{char}.png")
        render_strokes(strokes, out_path)
        print(f"  '{char}': stroke {len(strokes)}개 (기대 획수 {len(expected)}) -> {out_path}")
        assert len(strokes) == len(expected), (
            f"'{char}' stroke 수({len(strokes)})가 표준 획순 개수({len(expected)})와 다름"
        )
    print("  PASS: 모든 샘플의 stroke 개수가 표준 획순 개수와 일치")


def check_grouping_roundtrip():
    print("\n=== 2. 생성 -> 그룹핑 라운드트립 ===")
    text = "한이음"
    char_scale = 100
    all_strokes = generate_synthetic_line(text, origin=(20, 20), char_scale=char_scale, char_gap=50)
    groups = group_strokes_into_chars(all_strokes)

    out_dir = "../debug_output/synthetic_check"
    render_strokes(all_strokes, os.path.join(out_dir, "line_한이음.png"), canvas_size=(500, 200))

    print(f"  입력 텍스트: '{text}' ({len(text)}글자) -> stroke {len(all_strokes)}개 생성")
    print(f"  규칙 기반 그룹핑 결과: {len(groups)}개 그룹")
    for g in groups:
        print(f"    {g['char_id']}: stroke_count={g['stroke_count']} "
              f"confidence={g['confidence']} low_confidence={g['low_confidence']}")

    assert len(groups) == len(text), (
        f"기대: {len(text)}개 그룹(글자수와 동일), 실제: {len(groups)}개"
    )
    print(f"  PASS: {len(text)}글자가 정확히 {len(groups)}개 그룹으로 분리됨")


if __name__ == "__main__":
    check_rendering()
    check_grouping_roundtrip()
