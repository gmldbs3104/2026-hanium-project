# 개발 환경 세팅

새 컴퓨터에서 이 프로젝트(프론트+백엔드+AI)를 처음 돌릴 때 참고하는 문서.

## 자동 설치 스크립트

저장소 루트에서 실행.

**Windows:**
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

**Mac / Linux / WSL:**
```bash
bash scripts/setup.sh
```

스크립트가 하는 일:
1. 필수 도구(Python, Flutter, Docker, Git) 설치 여부 확인 — 없으면 설치 링크 안내 후 중단
2. Docker 컨테이너 `hanium-postgres`, `hanium-redis` 생성/기동
3. `backend/venv` 생성 + `backend/requirements.txt`(AI 의존성 포함) 설치 + `craft-text-detector` 패치 + Alembic 마이그레이션
4. `ai/venv` 생성 (pytest, 평가 스크립트 등 AI 자가 검증용)
5. `frontend`: `flutter pub get`

**스크립트가 자동으로 못 하는 것 (직접 해야 함)**:
- `backend/.env` 값 채우기 (`FIREBASE_CREDENTIALS_PATH`, `SECRET_KEY` 등) — 스크립트가 `.env.example`을 복사만 해줌
- Firebase 연동 (`firebase login`, `flutterfire configure`) — 브라우저 로그인이 필요해서 자동화 불가. 스크립트가 안내 문구만 출력함
- Windows에서 `torch` 설치가 260자 경로 제한(`MAX_PATH`)에 걸리면, 스크립트가 자동으로 감지해서 `C:\ai_venv`에 우회 설치 후 연결해준다 (자세한 원리는 `PROJECT_STATUS_AND_AI_INTEGRATION.md` §3-2-③ 참고). 그래도 안 되면 관리자 권한으로 레지스트리 `LongPathsEnabled`를 켜는 게 근본 해결책

## 실행

```powershell
# 백엔드
cd backend
venv\Scripts\activate        # Mac/Linux: source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# 프론트 (새 터미널)
cd frontend
flutter run -d chrome --web-port=5000
```

## 다른 컴퓨터에서 접속하려면 내 컴퓨터를 계속 켜둬야 하나?

**결론: 아니요 — 지금 구조에서는 각자 자기 컴퓨터에서 위 스크립트로 전체(Docker+백엔드+프론트)를 직접 띄워서 씁니다.** 한 사람이 컴퓨터/Docker/서버를 계속 켜둔다고 해서 다른 팀원이 접속할 수 있는 구조가 아닙니다.

이유:
- 백엔드는 `http://localhost:8000`에서 뜨고, `localhost`는 "그 컴퓨터 자기 자신"만 가리키는 주소라서 원래 다른 컴퓨터에서 접근할 수 없습니다.
- Docker의 Postgres/Redis도 마찬가지로 그 컴퓨터에서만 접근 가능하게 포트가 열려 있습니다.
- 프론트(`frontend/lib/core/app_config.dart`의 `apiBaseUrl`)도 `http://localhost:8000`으로 고정되어 있어서, 각자 자기 컴퓨터에 뜬 백엔드를 보도록 되어 있습니다.

즉 팀원 A가 컴퓨터를 켜놔도 팀원 B가 그걸 통해 접속하는 게 아니라, **팀원 B도 자기 컴퓨터에서 위 스크립트로 자기만의 백엔드+DB+프론트를 따로 띄워서** 테스트하는 구조입니다. 데이터(가입 계정, 저장된 연습 기록 등)도 컴퓨터마다 완전히 독립적입니다 (Postgres가 각자 로컬 Docker 안에 있으므로).

**만약 "한 곳에 다 같이 접속하는 서버"를 원한다면** — 그건 지금과 다른 얘기로, 백엔드를 실제 클라우드 서버(AWS/GCP 등)에 배포하고, DB도 관리형 서비스나 상시 켜진 서버에 올리고, 프론트의 `apiBaseUrl`을 그 서버 주소로 바꿔야 합니다. 이건 아직 안 되어 있고, 별도로 진행해야 하는 배포 작업입니다.
