"""blob 라벨링 GUI 생성기.

전처리 이미지와 blob 박스를 임베드한 **자기완결 HTML 파일**을 만든다. 사람이
브라우저에서 blob을 클릭해 음절로 묶고(필요하면 분할선을 그어) groups.json을
생성하면, 그걸로 label_helper.py build를 돌린다. AI가 이미지를 직접 판독할 필요가
없어 토큰을 거의 쓰지 않으며, 판독은 사람이 하므로 흘림체도 정확하다.

절차
----
1. python eval/label_gui.py test_images/test5.jpg
   → eval/gt_work/test5_label.html  (전처리 이미지 + blob 박스 임베드)
2. 브라우저로 test5_label.html 열기
   - 조각(blob)을 클릭해 현재 음절에 넣고, "새 음절(Enter)"로 다음 음절 시작
   - 흘림으로 한 blob이 두 음절에 걸치면 [분할 모드]에서 세로/가로 절단선을 긋고,
     생긴 조각을 각 음절에 배정(어느 음절에도 안 넣으면 GT에서 제외 = 문장부호/장식획)
   - 하단 "groups.json 복사/다운로드"로 eval/gt_work/<stem>_groups.json 저장
3. python eval/label_helper.py build test_images/test5.jpg
   → eval/gt/test5.json + 검수 시각화

blob 번호·순서는 label_helper.py blobs와 동일(extract_blobs 공유)하며, 분할 조각
이름(<id>a, <id>b …)도 label_helper._split_blob의 규칙(행 우선, 잉크 없는 칸은
이름만 소비)과 일치하도록 브라우저에서 canvas 픽셀 판정으로 계산한다.
"""
import base64
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from label_helper import _binary_for, extract_blobs, WORK_DIR

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "label_gui_template.html")


def build_html(image_path: str) -> str:
    stem = os.path.splitext(os.path.basename(image_path))[0]
    binary = _binary_for(image_path)
    blobs = extract_blobs(binary)

    # 표시·판정용 이미지: 흰 바탕 검은 글씨 (픽셀 < 128 = 잉크)
    display = cv2.bitwise_not(binary)
    ok, buf = cv2.imencode(".png", display)
    if not ok:
        raise RuntimeError("PNG 인코딩 실패")
    b64 = base64.b64encode(buf.tobytes()).decode()

    blob_data = [{"id": i, "x": b[0], "y": b[1], "width": b[2], "height": b[3]}
                 for i, b in enumerate(blobs)]

    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()

    payload = {
        "stem": stem,
        "width": int(display.shape[1]),
        "height": int(display.shape[0]),
        "image": "data:image/png;base64," + b64,
        "blobs": blob_data,
    }
    # 템플릿의 플레이스홀더를 JSON 페이로드로 치환(중괄호 충돌 회피 위해 replace 사용)
    return template.replace("/*__PAYLOAD__*/null", json.dumps(payload, ensure_ascii=False))


def main(image_path: str):
    stem = os.path.splitext(os.path.basename(image_path))[0]
    os.makedirs(WORK_DIR, exist_ok=True)
    html = build_html(image_path)
    out_path = os.path.join(WORK_DIR, f"{stem}_label.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"라벨링 GUI → {out_path}")
    print(f"브라우저로 열어 라벨링 후 {WORK_DIR}/{stem}_groups.json 저장,")
    print(f"이어서: python eval/label_helper.py build {image_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
