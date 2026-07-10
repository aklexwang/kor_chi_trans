# 텔레그램 한중 실시간 통역 봇

한국어 ↔ 중국어 자동 감지 후 번역본만 답장하는 텔레그램 봇입니다.  
Claude API(Sonnet 등, 기본 `claude-sonnet-4-6`) + python-telegram-bot v21 사용.

## 저장 (GitHub)

- 코드는 이 저장소(GitHub)에 올립니다.
- `.env`는 `.gitignore`에 포함되어 있어 **GitHub에 올라가지 않습니다.** API 키는 반드시 로컬/서버의 `.env`에만 두세요.

## 텔레그램에서 봇이 동작하려면

봇이 **실행 중인 동안에만** 텔레그램 메시지에 답합니다.  
아래 순서대로 설정한 뒤, **`python main.py`를 실행해 두면** 텔레그램에서 봇이 작동합니다.

1. **저장소 클론**
   ```bash
   git clone https://github.com/사용자명/저장소명.git
   cd 저장소명
   ```

2. **패키지 설치**
   ```bash
   pip install -r requirements.txt
   ```

3. **`.env` 파일 생성**  
   프로젝트 루트에 `.env` 파일을 만들고 다음을 넣습니다.
   ```env
   TELEGRAM_TOKEN=봇_토큰
   ANTHROPIC_API_KEY=Anthropic_API_키
   # 선택: 다른 Claude 모델 쓰려면 (기본 claude-sonnet-4-6)
   # CLAUDE_MODEL=claude-sonnet-4-6
   ```
   - 텔레그램 봇 토큰: [@BotFather](https://t.me/BotFather)에서 봇 생성 후 발급
   - Anthropic API 키: [Anthropic 콘솔](https://console.anthropic.com/)에서 발급

4. **봇 실행**
   ```bash
   python main.py
   ```
   터미널이 켜져 있는 동안 텔레그램에서 봇에게 메시지를 보내면 번역 답장이 옵니다.

## 24시간 동작 (선택)

PC를 끄면 봇이 멈춥니다. 항상 켜 두려면:

- **로컬**: PC를 계속 켜 두고 `python main.py`를 실행하거나, 작업 스케줄러/서비스로 등록
- **서버**: AWS, GCP, Railway, Render 등에 배포 후 같은 명령으로 실행

### PythonAnywhere로 상시 실행할 때

- 처음 올리기: `PythonAnywhere_배포_가이드.md`
- **유료 Always-on·Conflict·pip 설치 등 실제 운영 메모**: **`PythonAnywhere_운영노트.md`** ← 다음에 이 폴더 열었을 때 여기부터 보면 됩니다.

## 접근 제한 (관리자만 Google OTP)

봇 아이디만 알면 누구나 쓸 수 있는 것을 막습니다. **Google Authenticator는 관리자 휴대폰에만** 등록하고, 쓰게 할 사람에게 **그때그때 6자리 코드만** 알려 주세요.

1. `.env`에 추가:
   ```env
   TOTP_SECRET=여기에_BASE32_시크릿
   ADMIN_USER_IDS=본인_텔레그램_숫자ID
   OTP_SESSION_HOURS=24
   ```
2. 시크릿 생성 (본인 PC에서만):
   ```bash
   python -c "import pyotp; print(pyotp.random_base32())"
   ```
3. **본인 휴대폰** Google Authenticator → 설정 키 입력 → `TOTP_SECRET` 등록 (다른 사람에게 QR/시크릿 공유 금지)
4. 봇 재시작
5. 사용자가 `/start` → 관리자에게 코드 요청 → 6자리 숫자를 봇에 전송 → 인증 후 번역 사용

**관리자 명령** (본인 Telegram ID만):
- `/authlist` — 인증된 사용자 목록
- `/revoke 123456789` — 특정 사용자 인증 해제
- `/revokeall` — 전원 인증 해제

- 같은 6자리 코드는 **한 사람만** 사용 가능 (코드 공유 방지)
- `OTP_SESSION_HOURS=24` — 24시간 후 다시 관리자에게 코드 필요 (0이면 만료 없음)

## 사용 방법

1. 텔레그램에서 봇을 찾아 대화 시작
2. **한국어**로 입력 → **중국어** 번역만 답장
3. **중국어**로 입력 → **한국어** 번역만 답장
