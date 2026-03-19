# 텔레그램 한중 실시간 통역 봇

한국어 ↔ 중국어 자동 감지 후 번역본만 답장하는 텔레그램 봇입니다.  
Claude 3.5 Sonnet + python-telegram-bot v21 사용.

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

## 사용 방법

1. 텔레그램에서 봇을 찾아 대화 시작
2. **한국어**로 입력 → **중국어** 번역만 답장
3. **중국어**로 입력 → **한국어** 번역만 답장
