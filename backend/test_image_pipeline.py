"""
이미지 파이프라인 통합 테스트 스크립트

흐름:
1. Firebase 테스트 계정 생성 → idToken 발급
2. /auth/login 호출 → users 테이블에 사용자 생성
3. /image/preprocess 호출 → image_session_id 발급
4. /image/{id}/detect 호출 → 문자 영역 탐지
5. /image/{id}/analyze 호출 → 분석 결과 + DB 저장
6. /image/{id}/feedback 호출 → 피드백 메시지 생성

사용법:
    python test_image_pipeline.py

사전 준비:
    pip install requests opencv-python numpy
    FIREBASE_WEB_API_KEY 환경변수 설정 또는 아래 WEB_API_KEY 직접 입력
"""

import requests
import time
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

import cv2
import numpy as np

# Windows cp949 터미널에서 이모지 출력 가능하게 UTF-8로 강제 설정
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ===== 설정 =====
load_dotenv(Path(__file__).parent / ".env.test")

BASE_URL = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:8000")
WEB_API_KEY = os.environ.get("FIREBASE_WEB_API_KEY", "")

TEST_EMAIL = f"test_{int(time.time())}@example.com"
TEST_PASSWORD = "test1234"


def make_test_image() -> bytes:
    """
    손글씨를 시뮬레이션하는 테스트 이미지를 생성한다.
    흰 배경에 검은 사각형 블록들을 배치해 문자 영역처럼 보이게 한다.
    """
    img = np.ones((600, 800, 3), dtype=np.uint8) * 255  # 흰 배경

    # 1줄: 글자 블록 4개
    char_positions_row1 = [(50, 80), (180, 80), (310, 80), (440, 80)]
    # 2줄: 글자 블록 3개 (크기를 약간 다르게 해서 균일성 테스트)
    char_positions_row2 = [(50, 260), (190, 250), (330, 270)]

    for x, y in char_positions_row1:
        w, h = np.random.randint(80, 100), np.random.randint(90, 110)
        cv2.rectangle(img, (x, y), (x + w, y + h), (30, 30, 30), -1)
        # 내부에 흰 선으로 획 느낌 추가
        cv2.line(img, (x + 20, y + 30), (x + w - 20, y + 30), (255, 255, 255), 4)
        cv2.line(img, (x + w // 2, y + 10), (x + w // 2, y + h - 10), (255, 255, 255), 4)

    for x, y in char_positions_row2:
        w, h = np.random.randint(70, 110), np.random.randint(80, 120)
        cv2.rectangle(img, (x, y), (x + w, y + h), (40, 40, 40), -1)
        cv2.line(img, (x + 15, y + h // 2), (x + w - 15, y + h // 2), (255, 255, 255), 4)

    _, buffer = cv2.imencode(".jpg", img)
    return buffer.tobytes()


def fail(step: str, response: requests.Response):
    print(f"\n❌ [{step}] 실패 (status={response.status_code})")
    try:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(response.text)
    sys.exit(1)


def main():
    if not WEB_API_KEY:
        print("⚠️  FIREBASE_WEB_API_KEY가 설정되지 않았습니다.")
        print("    backend/.env.test 파일에 FIREBASE_WEB_API_KEY=AIza... 를 추가하세요.")
        print("    (참고: backend/.env.test.example)")
        sys.exit(1)

    # 1. Firebase 테스트 계정 생성 + idToken 발급
    print(f"[1] Firebase 테스트 계정 생성 중... ({TEST_EMAIL})")
    res = requests.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={WEB_API_KEY}",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "returnSecureToken": True},
    )
    if res.status_code != 200:
        fail("Firebase signUp", res)

    id_token = res.json()["idToken"]
    print(f"    ✅ idToken 발급 완료 (길이: {len(id_token)})")

    # 2. /auth/login 호출
    print("[2] /auth/login 호출 중...")
    res = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"provider": "google", "id_token": id_token},
    )
    if res.status_code != 200:
        fail("/auth/login", res)

    user_info = res.json()
    print(f"    ✅ 사용자 생성/조회 완료: {user_info['email']} (id={user_info['id']})")

    # 3. /image/preprocess 호출
    print("[3] /image/preprocess 호출 중...")
    image_bytes = make_test_image()
    res = requests.post(
        f"{BASE_URL}/api/v1/image/preprocess",
        files={"file": ("test_handwriting.jpg", image_bytes, "image/jpeg")},
    )
    if res.status_code != 200:
        fail("/image/preprocess", res)

    preprocess_result = res.json()
    image_session_id = preprocess_result["image_session_id"]
    print(f"    ✅ 전처리 완료: {preprocess_result['width']}x{preprocess_result['height']}px "
          f"(session_id={image_session_id})")

    # 4. /image/{id}/detect 호출
    print("[4] /image/{id}/detect 호출 중...")
    res = requests.post(f"{BASE_URL}/api/v1/image/{image_session_id}/detect")
    if res.status_code != 200:
        fail("/image/{id}/detect", res)

    detect_result = res.json()
    print(f"    ✅ 탐지 완료: {detect_result['total_detected']}개 문자 영역 탐지")

    # 5. /image/{id}/analyze 호출
    print("[5] /image/{id}/analyze 호출 중...")
    res = requests.post(
        f"{BASE_URL}/api/v1/image/{image_session_id}/analyze",
        headers={"Authorization": f"Bearer {id_token}"},
    )
    if res.status_code != 200:
        fail("/image/{id}/analyze", res)

    analysis_result = res.json()
    print(f"    ✅ 분석 완료")
    print(f"       크기 균일성: {analysis_result['size_uniformity_score']}점")
    print(f"       기울기 일관성: {analysis_result['slant_consistency_score']}점")
    print(f"       줄 정렬: {analysis_result['line_alignment_score']}점")
    print(f"       종합 점수: {analysis_result['overall_score']}점")

    # 6. /image/{id}/feedback 호출
    print("[6] /image/{id}/feedback 호출 중...")
    res = requests.get(f"{BASE_URL}/api/v1/image/{image_session_id}/feedback")
    if res.status_code != 200:
        fail("/image/{id}/feedback", res)

    feedback_result = res.json()
    print(f"    ✅ 피드백 생성 완료\n")

    print("=" * 60)
    print("🎉 전체 이미지 파이프라인 테스트 성공!")
    print("=" * 60)
    print(json.dumps(feedback_result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
