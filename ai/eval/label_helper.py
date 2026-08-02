"""
음절 단위 정답셋 라벨링 보조 도구.

절차
----
1. blobs 모드: 이미지를 전처리(이진화)한 뒤 connected component로 잉크 blob을 추출,
   각 blob에 번호를 붙인 시각화 이미지와 blob bbox JSON을 저장한다.
     python eval/label_helper.py blobs test_images/test.jpg
   → eval/gt_work/test_blobs.jpg  (번호 매겨진 시각화)
   → eval/gt_work/test_blobs.json (blob별 bbox)

2. 사람이 시각화를 보고 "어떤 blob들이 한 음절인지"를 그룹 파일로 작성한다.
     eval/gt_work/test_groups.json 형식: {"syllables": [[0,1,2], [3,4], ...]}
   (리스트 순서는 읽기 순서 권장이나 평가에는 영향 없음)

   흘림 등으로 한 blob이 두 음절에 걸쳐 이어진 경우, "splits"로 x좌표 세로 절단을
   지정할 수 있다. 분할된 조각은 왼쪽부터 "<id>a", "<id>b", ... 이름으로 그룹에 쓴다.
     {"splits": {"41": [366]},
      "syllables": [[40, "41a", 42], ["41b", 43, 44, 45], ...]}
   조각 bbox는 절단 구간 내 실제 잉크 픽셀의 tight bbox로 계산된다.
   윗줄 글자 꼬리가 아랫줄에 닿은 경우처럼 가로 절단이 필요하면 {"y": [...]} 형식을
   쓴다(조각은 위부터 a, b, ...). x·y를 함께 주면 격자 절단(조각 이름은 행 우선:
   위 행의 왼쪽부터 a, b, ...; 잉크 없는 칸은 이름만 차지하고 생성되지 않음).
   값이 리스트면 x 절단으로 해석한다(하위 호환).
     {"splits": {"197": {"x": [138], "y": [970]}}}

3. build 모드: 그룹 파일을 읽어 blob bbox들의 합집합으로 음절 GT bbox를 만들어 저장.
     python eval/label_helper.py build test_images/test.jpg
   → eval/gt/test.json  {"image": ..., "syllable_boxes": [{"x","y","width","height"}, ...]}

주의: GT 좌표계는 "전처리(이진화+deskew) 이후" 이미지 기준이다. 평가 스크립트
(evaluate_detection.py)도 같은 전처리를 거친 뒤 탐지하므로 좌표계가 일치한다.
"""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from preprocessing.image_preprocessor import ImagePreprocessor

WORK_DIR = os.path.join(os.path.dirname(__file__), "gt_work")
GT_DIR = os.path.join(os.path.dirname(__file__), "gt")

# 노이즈 점 제거: 이 면적(px) 미만 blob은 무시
MIN_BLOB_AREA = 40


def _binary_for(image_path: str) -> np.ndarray:
    pre = ImagePreprocessor()
    return pre.preprocess_from_file(image_path).binary_image


def extract_blobs(binary: np.ndarray):
    """잉크 blob 목록 [(x, y, w, h, area), ...] (면적 필터 적용)."""
    n, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    blobs = []
    for i in range(1, n):  # 0은 배경
        x, y, w, h, area = stats[i]
        if area < MIN_BLOB_AREA:
            continue
        blobs.append((int(x), int(y), int(w), int(h), int(area)))
    # 읽기 순서 비슷하게 정렬(위→아래, 왼→오)해서 번호가 덜 튀게
    blobs.sort(key=lambda b: (b[1] // 80, b[0]))
    return blobs


def mode_blobs(image_path: str):
    os.makedirs(WORK_DIR, exist_ok=True)
    stem = os.path.splitext(os.path.basename(image_path))[0]
    binary = _binary_for(image_path)
    blobs = extract_blobs(binary)

    vis = cv2.cvtColor(cv2.bitwise_not(binary), cv2.COLOR_GRAY2BGR)
    for i, (x, y, w, h, _) in enumerate(blobs):
        cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 160, 255), 1)
        cv2.putText(vis, str(i), (x, max(12, y - 3)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 0, 0), 2, cv2.LINE_AA)

    vis_path = os.path.join(WORK_DIR, f"{stem}_blobs.jpg")
    cv2.imwrite(vis_path, vis)
    json_path = os.path.join(WORK_DIR, f"{stem}_blobs.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {"image": image_path,
             "blobs": [{"id": i, "x": b[0], "y": b[1], "width": b[2], "height": b[3]}
                        for i, b in enumerate(blobs)]},
            f, ensure_ascii=False, indent=1)
    print(f"blob {len(blobs)}개")
    print(f"시각화 → {vis_path}")
    print(f"bbox   → {json_path}")
    print(f"다음: {WORK_DIR}/{stem}_groups.json 에 음절별 blob id 그룹을 작성 후 build 실행")


def _split_blob(binary: np.ndarray, blob: dict, x_cuts, y_cuts):
    """blob bbox 영역의 잉크 픽셀을 x/y 절단선 격자로 나눠 칸별 tight bbox 반환.

    칸 순서는 행 우선(위 행의 왼쪽부터). 잉크 없는 칸은 None.
    connected component를 다시 돌리지 않고 bbox 내 픽셀만 쓴다 — 같은 bbox에
    다른 blob의 픽셀이 섞이는 극단 케이스에선 조각이 약간 넓어질 수 있으나,
    절단 대상은 사람이 지정하므로 실용상 충분하다.
    """
    x0, y0 = blob["x"], blob["y"]
    x1, y1 = x0 + blob["width"], y0 + blob["height"]
    region = binary[y0:y1, x0:x1]
    xb = [x0] + sorted(x_cuts) + [x1]
    yb = [y0] + sorted(y_cuts) + [y1]
    parts = []
    for ylo, yhi in zip(yb[:-1], yb[1:]):
        for xlo, xhi in zip(xb[:-1], xb[1:]):
            sub = region[max(0, ylo - y0):max(0, yhi - y0),
                         max(0, xlo - x0):max(0, xhi - x0)]
            ys, xs = np.nonzero(sub)
            if len(xs) == 0:
                parts.append(None)
                continue
            parts.append({"x": int(xlo + xs.min()), "y": int(ylo + ys.min()),
                          "width": int(xs.max() - xs.min() + 1),
                          "height": int(ys.max() - ys.min() + 1)})
    if all(p is None for p in parts):
        raise ValueError(f"blob {blob['id']} 절단 결과가 전부 비었습니다")
    return parts


def mode_build(image_path: str):
    os.makedirs(GT_DIR, exist_ok=True)
    stem = os.path.splitext(os.path.basename(image_path))[0]
    with open(os.path.join(WORK_DIR, f"{stem}_blobs.json"), encoding="utf-8") as f:
        blob_data = json.load(f)
    with open(os.path.join(WORK_DIR, f"{stem}_groups.json"), encoding="utf-8") as f:
        group_data = json.load(f)
    groups = group_data["syllables"]
    splits = {int(k): v for k, v in group_data.get("splits", {}).items()}

    blob_by_id = {b["id"]: b for b in blob_data["blobs"]}

    binary = _binary_for(image_path) if splits else None
    for bid, spec in splits.items():
        if isinstance(spec, dict):
            x_cuts, y_cuts = spec.get("x", []), spec.get("y", [])
        else:
            x_cuts, y_cuts = spec, []
        parts = _split_blob(binary, blob_by_id[bid], x_cuts, y_cuts)
        for i, part in enumerate(parts):
            if part is not None:
                blob_by_id[f"{bid}{chr(ord('a') + i)}"] = part
        del blob_by_id[bid]

    used = [bid for g in groups for bid in g]
    if len(used) != len(set(used)):
        raise ValueError("같은 blob id가 두 그룹에 들어있습니다")
    unknown = [bid for bid in used if bid not in blob_by_id]
    if unknown:
        raise ValueError(f"blobs에 없는 id가 그룹에 있습니다: {unknown} "
                         f"(분할된 blob은 조각 이름 '<id>a'/'<id>b'로 써야 합니다)")
    unused = set(blob_by_id) - set(used)
    if unused:
        print(f"경고: 그룹에 안 들어간 blob {sorted(unused, key=str)} — 노이즈로 간주하고 무시합니다")

    boxes = []
    for g in groups:
        xs0 = [blob_by_id[i]["x"] for i in g]
        ys0 = [blob_by_id[i]["y"] for i in g]
        xs1 = [blob_by_id[i]["x"] + blob_by_id[i]["width"] for i in g]
        ys1 = [blob_by_id[i]["y"] + blob_by_id[i]["height"] for i in g]
        boxes.append({"x": min(xs0), "y": min(ys0),
                      "width": max(xs1) - min(xs0), "height": max(ys1) - min(ys0)})

    out_path = os.path.join(GT_DIR, f"{stem}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"image": image_path, "syllable_boxes": boxes}, f, ensure_ascii=False, indent=1)

    # 검수용 시각화
    binary = _binary_for(image_path)
    vis = cv2.cvtColor(cv2.bitwise_not(binary), cv2.COLOR_GRAY2BGR)
    for i, b in enumerate(boxes):
        cv2.rectangle(vis, (b["x"], b["y"]), (b["x"] + b["width"], b["y"] + b["height"]),
                      (0, 180, 0), 2)
        cv2.putText(vis, str(i), (b["x"], max(14, b["y"] - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 100, 0), 2, cv2.LINE_AA)
    check_path = os.path.join(WORK_DIR, f"{stem}_gt_check.jpg")
    cv2.imwrite(check_path, vis)
    print(f"음절 GT {len(boxes)}개 → {out_path}")
    print(f"검수 시각화 → {check_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("blobs", "build"):
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == "blobs":
        mode_blobs(sys.argv[2])
    else:
        mode_build(sys.argv[2])
