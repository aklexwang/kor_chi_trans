# PythonAnywhere 운영 노트 (참고용)

이 폴더를 다시 열었을 때 **배포·24시간 실행·에러**를 빠르게 떠올리기 위한 메모입니다.  
상세한 처음 올리기 순서는 `PythonAnywhere_배포_가이드.md`를 보세요.

---

## 운영 방침

- **로컬(PC)에서는 봇을 실행하지 않음** -> 텔레그램 폴링은 **PythonAnywhere 한 곳에서만** 사용.
- 계정·경로 예시: 사용자 `alexwang999`, 프로젝트 **`/home/alexwang999/interpreting`**.

---

## 24시간 실행 (유료 · Always-on task)

1. 상단 **Tasks** → 페이지 아래 **Always-on tasks**
2. **Run** 에 넣을 명령 예:

   ```bash
   bash -lc "cd /home/alexwang999/interpreting && python3.10 main.py"
   ```

3. 표의 **State** 열 확인  
   - **`Running`** -> 정상적으로 상시 실행 중  
   - **`Starting`이 오래 지속** -> 시작 직후 반복 크래시 가능. **로그(Actions 첫 번째 아이콘)** 또는 아래 "수동 실행"으로 원인 확인.

공식 도움말: [Always-on tasks](https://help.pythonanywhere.com/pages/AlwaysOnTasks/)

---

## 최초 1회(또는 `requirements.txt` 변경 후): 패키지 설치

Always-on이 **`python3.10`**을 사용하므로, **같은 인터프리터에** 패키지를 설치해야 합니다.

```bash
cd ~/interpreting
python3.10 -m pip install --user -r requirements.txt
```

- 예: `ModuleNotFoundError: No module named 'anthropic'` -> 위 명령으로 해결.

---

## `.env`

- 위치: **`~/interpreting/.env`** (PythonAnywhere **Files**에서 새 파일로 만들고 직접 입력; 업로드는 가이드대로 비권장)
- 필수: `TELEGRAM_TOKEN`, `ANTHROPIC_API_KEY`
- `main.py`는 `load_dotenv()`로 **현재 작업 디렉터리**의 `.env`를 읽으므로, Always-on 명령은 **`cd .../interpreting` 후** `main.py`를 실행하는 형태가 맞습니다.

---

## `telegram.error.Conflict` … only one bot instance

**의미:** 같은 봇 토큰으로 **`getUpdates`(폴링)** 를 **둘 이상이 동시에** 호출하는 상태.

**흔한 원인**

- **Always-on**으로 이미 `main.py`가 실행 중인데, **Bash 콘솔**에서도 `python3.10 main.py` / `python3.10 -u main.py`를 추가 실행
- 예전에 다른 PC·서버에서 같은 토큰으로 폴링

**해결**

- **항상 한 가지만** 선택:  
  - 24시간 운영 = **Always-on만 사용** -> 콘솔에서는 **`main.py`를 다시 실행하지 않기**
- 이미 겹쳤다면: **Consoles** -> **Running processes** -> **Fetch process list** ->  
  **`python3.10 ... main.py` 줄만 Kill** (가능하면 **`bash` 줄은 Kill하지 않기** - 콘솔 세션 끊김 방지)  
  또는 해당 콘솔에서 **Ctrl+C**
- 그 후 **Tasks -> Always-on**에서 필요 시 **재시작**

---

## Always-on Actions(로그)가 잘 눌리지 않을 때

- 다른 브라우저/시크릿 창 사용, 광고 차단 확장 끄기, 페이지 줌 100%로 조정
- 대안: Bash에서 동일하게 실행해 에러 확인

  ```bash
  cd ~/interpreting
  python3.10 -u main.py
  ```

---

## 상태 확인 요약

| 보는 곳 | 내용 |
|--------|------|
| **Tasks -> Always-on -> State** | `Running` / `Starting` |
| **Consoles -> Running processes** | 콘솔에서 띄운 `python3.10 ... main.py` 중복 여부 |

---

## 관련 파일

- `PythonAnywhere_배포_가이드.md` — 처음 폴더·파일·`.env`·콘솔 테스트 순서
- `README.md` — 로컬 개발 시 일반 실행 방법
