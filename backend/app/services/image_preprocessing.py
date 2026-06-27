import cv2
import numpy as np
from typing import Tuple


def preprocess_image(image_bytes: bytes) -> Tuple[np.ndarray, int, int]:
    """
    Raw 이미지 바이트 → 그레이스케일 이진화 numpy 배열 반환.
    Returns (binary_image, width, height)
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("이미지를 디코딩할 수 없습니다. 지원 형식: JPG, PNG")

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    return binary, w, h


def detect_char_bboxes(binary_image: np.ndarray) -> list:
    """
    이진화 이미지에서 문자 후보 영역을 contour 기반으로 탐지한다.
    실제 서비스에서는 CRAFT 모델로 교체 예정 (placeholder).
    """
    h, w = binary_image.shape
    min_area = h * w * 0.0002
    max_area = h * w * 0.4

    contours, _ = cv2.findContours(binary_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    bboxes = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if min_area <= area <= max_area:
            x, y, cw, ch = cv2.boundingRect(contour)
            bboxes.append({
                "bounding_box": {"x": float(x), "y": float(y), "width": float(cw), "height": float(ch)},
            })

    # 좌상단 기준 정렬 (줄 단위 y, 줄 내 x)
    row_height = h / 10
    bboxes.sort(key=lambda b: (
        int(b["bounding_box"]["y"] / row_height),
        b["bounding_box"]["x"],
    ))

    for i, b in enumerate(bboxes):
        b["char_id"] = f"char_{i}"

    return bboxes
