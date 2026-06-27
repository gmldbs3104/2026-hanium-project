import cv2
import numpy as np
from typing import Tuple
from app.services.ai_adapters import craft_detect_chars


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
    """문자 영역 탐지 — ai_adapters.craft_detect_chars 를 통해 실행"""
    h, w = binary_image.shape
    return craft_detect_chars(
        binary_image_list=binary_image.tolist(),
        image_width=w,
        image_height=h,
    )
