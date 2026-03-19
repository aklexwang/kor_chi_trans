# GitHub + .env + .gitignore 초보자 가이드

코드는 GitHub에 올리되, **비밀 키는 절대 올리지 않는 방법**을 단계별로 설명합니다.

---

## 1. 왜 GitHub에 올리나요?

- **코드 백업**: 컴퓨터가 고장 나도 코드를 안전하게 둘 수 있어요.
- **버전 관리**: 수정 이력을 남기고, 필요하면 예전 버전으로 돌아갈 수 있어요.
- **다른 기기에서 사용**: 다른 PC나 서버에서 `git clone` 한 번이면 같은 코드를 쓸 수 있어요.

**주의:** GitHub는 기본적으로 "누구나 볼 수 있는 공개 저장소"처럼 쓰일 수 있어요. 그래서 **비밀 정보(API 키, 비밀번호 등)는 절대 GitHub에 올리면 안 됩니다.**

---

## 2. .env 파일이 뭔가요? 왜 올리면 안 되나요?

### .env 파일이 하는 일

우리 봇은 두 가지 **비밀 키**가 필요해요.

| 키 이름 | 어디서 쓰이나요 |
|--------|------------------|
| `TELEGRAM_TOKEN` | 텔레그램이 "이 봇이 진짜 너의 봇이야"라고 인증할 때 |
| `ANTHROPIC_API_KEY` | Claude API를 쓸 때 과금·인증에 사용 |

이 값들을 **코드 안에 직접 적지 않고**, `.env`라는 파일에 따로 적어 두었어요.

```env
TELEGRAM_TOKEN=123456789:ABCdefGHI...
ANTHROPIC_API_KEY=sk-ant-...
```

- **코드**(`main.py`)에는 `os.getenv("TELEGRAM_TOKEN")`처럼 "환경 변수에서 읽어라"만 적고,
- **실제 값**은 `.env`에만 넣습니다.

### 왜 GitHub에 올리면 안 되나요?

- `.env`를 GitHub에 올리면, 그 저장소를 본 **누구나** 그 키를 볼 수 있어요.
- 그 키로 **당신 이름으로** 텔레그램 봇을 조작하거나, **당신 계정으로** API 요금이 나갈 수 있어요.
- 그래서 **.env는 "내 컴퓨터에만 두고, GitHub에는 절대 올리지 않는 것"이 규칙**입니다.

정리하면:

- **GitHub에 올리는 것:** `main.py`, `requirements.txt`, `README.md`, `.gitignore` 같은 **코드·설정 파일**
- **GitHub에 올리지 않는 것:** `.env` (비밀 키가 들어 있는 파일)

---

## 3. .gitignore가 뭔가요?

Git은 기본적으로 **폴더 안의 파일들을 “추적”**하고, `git add`한 파일들을 커밋하면 GitHub에 올라갑니다.

- 실수로 `git add .env`를 하고 커밋해 버리면, **.env가 GitHub에 올라가 버립니다.**
- **.gitignore**는 "이 파일/폴더는 Git이 **무시**해라. 추적하지도, 커밋하지도 마라"라고 적어 두는 **목록 파일**이에요.

이름 그대로 **"Git이 무시(ignore)할 것"**을 적는 파일입니다.

---

## 4. 우리 프로젝트의 .gitignore 설명

프로젝트에 들어 있는 `.gitignore` 내용을 한 줄씩 설명할게요.

```text
# API 키·비밀 (절대 GitHub에 올리지 않음)
.env
```

- **`.env`**  
  → 비밀 키가 들어 있는 파일. **반드시 제외.** 이렇게 적어 두면 `git add .` 해도 `.env`는 커밋 대상에서 빠집니다.

```text
# 가상환경
venv/
.venv/
env/
```

- **venv/, .venv/, env/**  
  → Python 가상환경 폴더. 패키지가 수백 개 들어 있어서 용량도 크고, PC마다 경로가 다를 수 있어요. GitHub에 올릴 필요 없고, 올리지 않는 게 좋아요. (다른 사람은 자기 환경에서 `pip install -r requirements.txt`로 다시 만듭니다.)

```text
# Python
__pycache__/
*.py[cod]
...
```

- **__pycache__/**  
  → Python이 실행할 때 만드는 "캐시" 폴더. 자동 생성이라 저장소에 넣을 필요 없어요.
- **기타 (*.pyc 등)**  
  → 컴파일된 파일, 빌드 결과물 등. 마찬가지로 자동 생성·로컬 전용이라 제외합니다.

```text
# IDE
.idea/
.vscode/
```

- **.idea/, .vscode/**  
  → 에디터(IDE) 설정 폴더. 개인 취향에 따라 달라지므로 보통 저장소에 넣지 않습니다.

**요약:**  
- **.env** → 비밀 키 보호 (가장 중요)  
- **venv, __pycache__ 등** → 불필요·자동 생성·개인 설정이라 제외

---

## 5. 처음 한 번만 할 설정 (Git + GitHub)

### 5-1. Git 설치

- [Git 공식 사이트](https://git-scm.com/)에서 내려받아 설치합니다.
- 설치 후 터미널(또는 Cursor 터미널)에서 `git --version` 이 나오면 됩니다.

### 5-2. GitHub 계정 + 저장소 만들기

1. [github.com](https://github.com) 에서 계정을 만듭니다.
2. 로그인 후 오른쪽 상단 **+** → **New repository** 를 누릅니다.
3. 저장소 이름(예: `telegram-interpreting-bot`)을 정하고 **Create repository** 로 만듭니다.
4. 아직 **파일을 추가하지 말고** 그대로 둡니다 (다음 단계에서 로컬에서 올릴 거예요).

### 5-3. 프로젝트 폴더에서 Git 시작하기

프로젝트 폴더(`d:\interpreting`)를 연 터미널에서:

```bash
cd d:\interpreting
git init
```

- `git init` → "이 폴더를 Git으로 관리할 거야"라고 한 번만 해 주는 명령입니다.

### 5-4. .gitignore가 제대로 있는지 확인

```bash
dir
```

또는

```bash
ls
```

- `.gitignore` 파일이 있어야 합니다.  
- **.env**는 이 폴더에 있어도 되지만, **.gitignore에 .env가 적혀 있으면** 나중에 `git add` 해도 올라가지 않습니다.

### 5-5. 파일 추가하고 첫 커밋

```bash
git add .
git status
```

- `git add .` → 현재 폴더의 변경된 파일들을 "스테이징"합니다.  
- **.gitignore에 적힌 파일(.env, venv 등)은 여기서 자동으로 제외됩니다.**
- `git status` 로 확인해 보면 **.env는 목록에 없어야** 합니다. (나타나면 .gitignore를 다시 확인해 보세요.)

그다음:

```bash
git commit -m "첫 커밋: 텔레그램 한중 통역 봇"
```

- "첫 번째 버전을 저장했다"는 뜻의 커밋을 만든 겁니다. 아직 GitHub에는 안 올라간 상태예요.

### 5-6. GitHub 저장소와 연결하고 올리기

GitHub에서 만든 저장소 페이지에 나오는 주소를 복사합니다. (예: `https://github.com/내아이디/telegram-interpreting-bot.git`)

```bash
git remote add origin https://github.com/내아이디/저장소이름.git
git branch -M main
git push -u origin main
```

- `git remote add origin ...` → "이 로컬 폴더의 원격 저장소는 이 GitHub 주소야"라고 연결합니다.
- `git push -u origin main` → 로컬의 `main` 브랜치를 GitHub의 `main`으로 올립니다.

여기까지 하면 **코드만** GitHub에 올라가고, **.env는 올라가지 않은 상태**가 됩니다.

---

## 6. 앞으로 코드 수정할 때 (일반적인 흐름)

1. `main.py` 등 코드를 수정합니다.
2. **.env는 절대 수정하지 않아도 되고, git add 할 일도 없습니다.** (.gitignore가 막아 줍니다.)
3. 터미널에서:

   ```bash
   cd d:\interpreting
   git add .
   git status   ← .env가 목록에 없는지 한 번 확인
   git commit -m "수정 내용 한 줄 요약"
   git push
   ```

이렇게 하면 **저장은 GitHub에**, **비밀 키는 .env에만** 두는 습관이 들게 됩니다.

---

## 7. 다른 PC에서 이 프로젝트를 쓸 때

1. 그 PC에서 `git clone https://github.com/내아이디/저장소이름.git` 로 코드만 받습니다.
2. **.env는 GitHub에 없으니까**, 그 PC에는 직접 만들어 줘야 합니다:
   - 프로젝트 폴더에 `.env` 파일을 만들고
   - `TELEGRAM_TOKEN=...`, `ANTHROPIC_API_KEY=...` 를 넣어 줍니다.
3. `pip install -r requirements.txt` → `python main.py` 로 실행하면 됩니다.

---

## 한 줄 요약

- **GitHub** = 코드만 올리는 곳.  
- **.env** = 비밀 키만 넣는 파일. 이 파일은 **절대 GitHub에 올리지 않는다.**  
- **.gitignore** = "`.env`랑 venv, __pycache__ 같은 건 Git이 무시해라"라고 적어 두는 목록.  
- 그래서 **저장은 GitHub에, 비밀 키는 .env에만** 두면 됩니다.

궁금한 점 있으면 "어느 단계에서 막혔는지" 알려 주면 그 부분만 더 풀어서 설명해 줄게요.
