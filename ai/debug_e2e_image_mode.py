# -*- coding: utf-8 -*-
"""이미지 모드 end-to-end 수동 점검 스크립트 — 백엔드 어댑터 경로 그대로.

백엔드 라우트가 수행할 순서와 동일한 흐름을 test_images 4장에 대해 실행한다:
  1. preprocess_image_full  — 이진화/deskew/리사이즈 + 품질 판정 (SFR-003I)
  2. craft_detect_chars     — 문자 박스 탐지 (SFR-004I)
  3. analyze_size_angle     — 크기/기울기/기준선 평가 + 피드백 (SFR-005I)

사용법:  ai/venv/Scripts/python.exe ai/debug_e2e_image_mode.py
(최초 실행 시 CRAFT 로드로 첫 이미지 탐지에 +4초가량 걸린다)
"""
import json
import os
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "backend"))

from app.services.ai_adapters import (  # noqa: E402
    preprocess_image_full, craft_detect_chars, analyze_size_angle)

IMAGES = ["test.jpg", "test2.png", "test3_crop.png", "test6.jpg"]


def main():
    report = {}
    for name in IMAGES:
        path = os.path.join(REPO, "ai", "test_images", name)
        with open(path, "rb") as f:
            raw = f.read()

        t0 = time.perf_counter()
        pre = preprocess_image_full(raw)
        t1 = time.perf_counter()
        chars = craft_detect_chars(pre["binary_image"], pre["width"], pre["height"])
        t2 = time.perf_counter()
        ana = analyze_size_angle(chars)
        t3 = time.perf_counter()

        flags_size, flags_angle = {}, {}
        for c in ana["chars"]:
            flags_size[c["size_flag"]] = flags_size.get(c["size_flag"], 0) + 1
            flags_angle[c["angle_flag"]] = flags_angle.get(c["angle_flag"], 0) + 1

        report[name] = {
            "품질": {
                "quality_total": pre["quality_score"]["total"],
                "retake_required": pre["retake_required"],
                "skew_angle": round(pre["skew_angle"], 2),
                "size": f'{pre["width"]}x{pre["height"]}',
            },
            "탐지": {"chars": len(chars)},
            "평가": {
                "size_uniformity_score": round(ana["size_uniformity_score"], 1),
                "line_alignment_score": round(ana["line_alignment_score"], 1),
                "mean_angle": round(ana["mean_angle"], 2),
                "angle_std": round(ana["angle_std"], 2),
                "overall_tilt": ana["overall_tilt"],
                "size_flags": flags_size,
                "angle_flags": flags_angle,
                "tilt_consistency_score": round(ana["tilt_consistency_score"], 1),
                "issues": ana["issues"],
            },
            "시간(s)": {
                "전처리": round(t1 - t0, 2),
                "탐지": round(t2 - t1, 2),
                "평가": round(t3 - t2, 3),
            },
        }
        print(f"[{name}] 완료")

    print()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
