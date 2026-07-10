# PythonAnywhere에 텔레그램 봇 올리기

계정 `alexwang999`로 로그인한 상태에서 아래 순서대로 진행하세요.

---

## 1단계: 프로젝트 폴더 만들기

1. 상단 **Files** 탭 클릭
2. **Enter path**에서 홈 경로 확인 (예: `/home/alexwang999/`)
3. **+ Add a new file** 옆의 **New directory**로 폴더 하나 만들기
   - 이름: `interpreting` (또는 `kor_chi_trans`)
4. 만든 폴더를 클릭해서 들어가기

---

## 2단계: 파일 올리기

이 폴더 안에 아래 파일들을 올립니다.

| 올릴 파일 | 방법 |
|-----------|------|
| `main.py` | **Upload a file** 클릭 → PC의 `d:\interpreting\main.py` 선택 |
| `requirements.txt` | 같은 방식으로 `d:\interpreting\requirements.txt` 선택 |

### `.env` 파일 만들기 (반드시 직접 입력)

PythonAnywhere에는 **`.env`를 업로드하지 말고**, 사이트에서 새 파일로 만듭니다.

1. **+ Add a new file** 클릭
2. 파일 이름에 **`.env`**를 입력하고 저장
3. `.env` 파일을 열고 아래 두 줄을 **본인 키로** 입력 (앞뒤 공백 없이 한 줄씩)

   ```
   TELEGRAM_TOKEN=여기에_텔레그램_봇_토큰
   ANTHROPIC_API_KEY=여기에_Anthropic_API_키
   ```

4. **Save** 저장

---

## 3단계: Bash 콘솔에서 패키지 설치 & 봇 실행

1. 상단 **Consoles** 탭 클릭
2. **$ Bash** 버튼 클릭 → 새 터미널(콘솔) 열림
3. 아래 명령어를 **한 줄씩** 입력 후 Enter

   ```bash
   cd ~/interpreting
   pip install -r requirements.txt
   python main.py
   ```

4. 에러 없이 실행되면 `Application started` 같은 메시지가 보입니다.
5. **이 콘솔 창을 닫지 말고** 그대로 두면 텔레그램 봇이 동작합니다.

---

## ⚠️ 무료 계정에서 알아둘 점

- **Always-on task(24시간 실행)는 무료 계정에서 사용할 수 없습니다.** (유료 전용)
- 무료에서는 **Bash 콘솔을 열어 둔 동안만** 봇이 돌아갑니다.
  - 브라우저를 닫거나 콘솔을 닫으면 봇이 멈춥니다.
- **24시간 켜 두고 싶다면**
  - PythonAnywhere **유료** 플랜으로 Always-on task 사용, 또는
  - **Oracle Cloud Always Free**, **Fly.io** 같은 다른 무료 서버를 쓰는 방법이 있습니다.

---

## 4단계: 동작 확인

1. 휴대폰/PC에서 텔레그램 앱 열기
2. 봇 이름 검색 후 대화 시작
3. 한국어나 중국어로 메시지 보내기 -> 번역 답장이 오면 성공

---

## 자주 나오는 오류

| 메시지 | 해결 |
|--------|------|
| `ModuleNotFoundError` | `pip install -r requirements.txt` 다시 실행 |
| `TELEGRAM_TOKEN ... 설정해 주세요` | `.env` 파일 경로가 `~/interpreting/.env`인지, 내용이 정확한지 확인 |
| 콘솔이 끊김 | 무료 계정은 콘솔이 일정 시간 비활성 시 끊길 수 있음. 다시 Consoles에서 Bash 열고 `cd ~/interpreting` 후 `python main.py` 다시 실행 |

---

## 요약

1. **Files** → `interpreting` 폴더 만들기 → `main.py`, `requirements.txt` 업로드 → `.env` 파일 새로 만들어서 키 입력  
2. **Consoles** → Bash 열기 → `cd ~/interpreting` → `pip install -r requirements.txt` → `python main.py`  
3. 콘솔을 닫지 않고 두면 그동안 봇이 동작합니다.

---

## 배포 후·유료 Always-on 사용 시

실제로 겪은 설정(Always-on 명령, `python3.10`용 `pip install`, `Conflict` 해결 등)은 **`PythonAnywhere_운영노트.md`**에 정리해 두었습니다. 문제가 생기면 그 파일을 먼저 보세요.
