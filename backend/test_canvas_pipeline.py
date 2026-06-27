"""
캔버스 파이프라인 통합 테스트 스크립트

흐름:
1. Firebase 테스트 계정 생성 (또는 기존 계정으로 로그인) → idToken 발급
2. /auth/login 호출 → users 테이블에 사용자 생성
3. /canvas/analyze 호출 → canvas_session_id 발급
4. /canvas/{id}/group 호출 → 획 그룹핑
5. /canvas/{id}/analyze-detail 호출 → 분석 결과 + DB 저장
6. /canvas/{id}/feedback 호출 → 피드백 메시지 생성

사용법:
    python test_canvas_pipeline.py

사전 준비:
    pip install requests
    FIREBASE_WEB_API_KEY 환경변수 설정 또는 아래 WEB_API_KEY 직접 입력
"""

import requests
import time
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Windows cp949 터미널에서 이모지 출력 가능하게 UTF-8로 강제 설정
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ===== 설정 =====
load_dotenv(Path(__file__).parent / ".env.test")

BASE_URL = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:8000")
WEB_API_KEY = os.environ.get("FIREBASE_WEB_API_KEY", "")

# 테스트 계정 (매번 새로 만들면 timestamp로 유니크하게)
TEST_EMAIL = f"test_{int(time.time())}@example.com"
TEST_PASSWORD = "test1234"

# 테스트용 캔버스 입력 데이터
SAMPLE_PAYLOAD = {
    "strokes": [
        {
            "stroke_id": "s1",
            "points": [
                {"x": 10.5, "y": 20.1, "pressure": 0.8, "timestamp": 1000},
                {"x": 11.0, "y": 21.0, "pressure": 0.9, "timestamp": 1016},
            ],
        }
    ],
    "metadata": {"width": 800, "height": 600, "stroke_count": 1},
}


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

    # 2. /auth/login 호출 → users 테이블에 사용자 생성
    print("[2] /auth/login 호출 중...")
    res = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"provider": "google", "id_token": id_token},
    )
    if res.status_code != 200:
        fail("/auth/login", res)

    user_info = res.json()
    print(f"    ✅ 사용자 생성/조회 완료: {user_info['email']} (id={user_info['id']})")

    # 3. /canvas/analyze 호출 → canvas_session_id 발급
    print("[3] /canvas/analyze 호출 중...")
    res = requests.post(f"{BASE_URL}/api/v1/canvas/analyze", json=SAMPLE_PAYLOAD)
    if res.status_code != 200:
        fail("/canvas/analyze", res)

    canvas_session_id = res.json()["canvas_session_id"]
    print(f"    ✅ canvas_session_id 발급: {canvas_session_id}")

    # 4. /canvas/{id}/group 호출 → 획 그룹핑
    print("[4] /canvas/{id}/group 호출 중...")
    res = requests.post(f"{BASE_URL}/api/v1/canvas/{canvas_session_id}/group")
    if res.status_code != 200:
        fail("/canvas/{id}/group", res)

    group_result = res.json()
    print(f"    ✅ 그룹핑 완료: char_groups {len(group_result['char_groups'])}개, "
          f"저신뢰 {group_result['low_confidence_count']}개")

    # 5. /canvas/{id}/analyze-detail 호출 → 분석 + DB 저장
    print("[5] /canvas/{id}/analyze-detail 호출 중...")
    res = requests.post(
        f"{BASE_URL}/api/v1/canvas/{canvas_session_id}/analyze-detail",
        headers={"Authorization": f"Bearer {id_token}"},
    )
    if res.status_code != 200:
        fail("/canvas/{id}/analyze-detail", res)

    analysis_result = res.json()
    print(f"    ✅ 분석 완료: {len(analysis_result['results'])}개 문자 분석")

    # 6. /canvas/{id}/feedback 호출 -> 피드백 메세지 생성
    print("[6] /canvas/{id}/feedback 호출 중...")
    res = requests.get(f"{BASE_URL}/api/v1/canvas/{canvas_session_id}/feedback")
    if res.status_code != 200:
        fail("/canvas/{id}/feedback", res)
    feedback_result = res.json()
    print("     피드백 생성 완료\n")
    print("=" * 60)
    print("🎉 전체 파이프라인 테스트 성공!")
    print("=" * 60)
    print(json.dumps(analysis_result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
