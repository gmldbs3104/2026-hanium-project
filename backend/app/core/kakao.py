import httpx

from app.core.config import settings

KAKAO_USER_ME_URL = "https://kapi.kakao.com/v2/user/me"
KAKAO_TOKEN_INFO_URL = "https://kapi.kakao.com/v1/user/access_token_info"


class KakaoAuthError(Exception):
    """카카오 access_token 검증/조회 실패."""


async def fetch_kakao_profile(access_token: str) -> dict:
    """카카오 access_token으로 사용자 프로필을 조회한다.

    앱(카카오 SDK 로그인)에서 받은 access_token을 그대로 넘기면,
    카카오 API가 토큰을 검증하고(만료·위조면 401) 사용자 정보를 돌려준다.

    반환: {"id": str, "email": str|None, "nickname": str|None, "profile_image": str|None}
    실패 시 KakaoAuthError.
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(KAKAO_USER_ME_URL, headers=headers)
        if resp.status_code == 401:
            raise KakaoAuthError("유효하지 않은 카카오 토큰입니다.")
        if resp.status_code != 200:
            raise KakaoAuthError("카카오 사용자 정보를 가져오지 못했습니다.")
        data = resp.json()

        # (선택) 토큰이 우리 앱에서 발급된 것인지 검증 — KAKAO_APP_ID가 설정된 경우에만.
        #   미설정 시 건너뛴다(개발 편의). 운영에서는 설정을 권장한다.
        if settings.kakao_app_id is not None:
            info = await client.get(KAKAO_TOKEN_INFO_URL, headers=headers)
            if info.status_code != 200 or info.json().get("app_id") != settings.kakao_app_id:
                raise KakaoAuthError("다른 앱에서 발급된 카카오 토큰입니다.")

    kakao_id = data.get("id")
    if kakao_id is None:
        raise KakaoAuthError("카카오 응답에 사용자 id가 없습니다.")

    account = data.get("kakao_account") or {}
    profile = account.get("profile") or {}
    return {
        "id": str(kakao_id),
        "email": account.get("email"),
        "nickname": profile.get("nickname"),
        "profile_image": profile.get("profile_image_url"),
    }
