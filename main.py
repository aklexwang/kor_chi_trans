"""
텔레그램 실시간 통역 봇
- 한국어 → 중국어, 중국어 → 한국어 자동 감지 후 번역본만 답장
- 일반 텍스트 + 사진/동영상 등 캡션(caption) 동일 처리
- Claude Sonnet + python-telegram-bot v21
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional

import httpx
from anthropic import APITimeoutError, AsyncAnthropic
from dotenv import load_dotenv
from telegram import Update
from telegram.error import Conflict, NetworkError, TimedOut
from telegram.ext import Application, ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)

# 작업 디렉터리와 무관하게 main.py와 같은 폴더의 .env만 사용 (Always-on·경로 이슈 방지)
_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")

TELEGRAM_TOKEN = (os.getenv("TELEGRAM_TOKEN") or "").strip()
ANTHROPIC_API_KEY = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
# Anthropic HTTP: 응답 지연·네트워크 불안정 대비 (초). 생략 시 read 180 / connect 30
_anthropic_read_timeout = float(os.getenv("ANTHROPIC_READ_TIMEOUT", "180"))
_anthropic_connect_timeout = float(os.getenv("ANTHROPIC_CONNECT_TIMEOUT", "30"))

_anthropic_client: Optional[AsyncAnthropic] = None


def _anthropic_http_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=_anthropic_connect_timeout,
        read=_anthropic_read_timeout,
        write=120.0,
        pool=120.0,
    )


def _get_anthropic() -> AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = AsyncAnthropic(
            api_key=ANTHROPIC_API_KEY,
            timeout=_anthropic_http_timeout(),
        )
    return _anthropic_client


def _format_user_error(exc: BaseException) -> str:
    """타임아웃·일시 오류는 한국어 안내로 통일."""
    friendly = "현재 번역 서버가 혼잡합니다. 잠시 후 다시 시도해 주세요."
    if isinstance(exc, (APITimeoutError, asyncio.TimeoutError)):
        return friendly
    if isinstance(exc, httpx.TimeoutException):
        return friendly
    raw = str(exc).lower()
    if "timed out" in raw or "timeout" in raw:
        return friendly
    if "overloaded" in raw or "529" in str(exc):
        return friendly
    return str(exc)


def _is_url_only_message(text: str) -> bool:
    """메시지 전체가 URL 한 덩어리일 때만 True (번역 생략하고 그대로 답장)."""
    t = text.strip()
    if not t or "\n" in t:
        return False
    return bool(re.match(r"^https?://\S+$", t, re.IGNORECASE))


def _strip_bilingual_artifact(reply: str) -> str:
    """모델이 '원문 다듬기\\n---\\n번역'처럼 줄 때 번역부만 사용."""
    t = reply.strip()
    if not t:
        return t
    chunks = re.split(r"\n\s*-{3,}\s*\n", t)
    if len(chunks) >= 2:
        return chunks[-1].strip()
    return t


def _extract_message_text(message: Optional[object]) -> Optional[str]:
    """일반 본문(text) 또는 사진·동영상·파일 등 캡션(caption)."""
    if message is None:
        return None
    for key in ("text", "caption"):
        raw = getattr(message, key, None)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _log_incoming_request(update: Update, user_text: str) -> None:
    """누가 어떤 채팅에서 썼는지 서버 로그에 남김(PythonAnywhere 콘솔·Always-on 로그)."""
    u = update.effective_user
    c = update.effective_chat
    preview = user_text if len(user_text) <= 100 else user_text[:100] + "…"
    uname = getattr(u, "username", None) if u else None
    full = getattr(u, "full_name", None) if u else None
    logger.info(
        "요청 chat_id=%s type=%s user_id=%s username=%s name=%r 미리보기=%r",
        getattr(c, "id", None),
        getattr(c, "type", None),
        getattr(u, "id", None),
        ("@" + uname) if uname else "(없음)",
        full or "",
        preview,
    )


TRANSLATION_SYSTEM = """You are a professional Korean–Chinese interpreter who is fluent in both languages' spoken, everyday registers (Korean 구어체 and Chinese 口语 / colloquial Mandarin as people actually talk).

Your job is NOT literal word-for-word translation, but you **only interpret what the user actually said** into the other language—same speech act (question stays a question, command stays a command, statement stays a statement). Use natural spoken phrasing: fillers, idioms, word order as a native would say it out loud. Avoid stiff written Chinese (文绉绉), dictionary-ish phrasing, and awkward calques.

**You are an interpreter, not a Q&A assistant.** Never answer the user's question, never supply facts, geography, explanations, or advice they did not say. Do not "helpfully" respond to what they asked—only translate their **words** (their utterance) into the target language.
- Korean question (e.g. **한국은 어디 있니?**) → Chinese must be the **same question** in natural 口语 (e.g. **韩国在哪儿啊？** / **韩国在什么地方？**), **not** an answer like **韩国在亚洲东部…**.
- Chinese question → Korean must stay a **question** in 구어체, not an answer.
- Same for commands, complaints, small talk: output only the equivalent utterance, with no added content.

- Korean input → output only in natural spoken Chinese (口语). Match formality to the message (chatty stays chatty; polite/formal stays appropriately polite but still sounds like real speech).
- Chinese input (Simplified or Traditional) → output only in natural spoken Korean (구어체), same principles.

Short replies about already knowing / being aware (very common in chat):
- Korean phrases like **알고 있어**, **알고 있다**, **이미 알아**, **그거 알아** (meaning the speaker *already* knew—often replying in a group that they were not newly informed) → Chinese should use **我知道**, **我都知道**, **这个我知道**, **我早就知道了**, etc. as fits the tone. **Avoid defaulting to 知道了** when it would sound like a fresh acknowledgment ("got it / noted") rather than prior awareness. 知道了 fits "OK I hear you" after new info; **我知道** fits "I'm already aware of that."
- Chinese **我知道** in dialogue (stating awareness, same page as others) → Korean should express ongoing/shared prior knowledge: **나도 알고 있어**, **(그거) 알고 있어**, **이미 알고 있어**, **나도 알고 있다**. Do not default to bare **나 알아** for 我知道; it often sounds too curt or mismatched compared to "I'm aware too / already knew."

Pronouns and "who acts on whom" (do not flip perspective):
- Chinese **他 / 她 / 他们 / 人家** and Korean **그 / 그녀 / 그들 / 걔 / 쟤** refer to **third parties** unless context clearly says otherwise. **Never** render **他** (him/her) as **나** (me) or **我** as the object of **问** when the source means asking **another person**. Example: **我问他一下** = "I'll ask him / let me ask him" → natural Korean e.g. **그한테 물어볼게**, **걔한테 한번 물어볼게** — **not** **나한테 물어볼게** (that means asking oneself). Same care for **你/您 ↔ 너/당신**, **我 ↔ 나/저**: keep subject/object roles aligned with the source.

Reply with ONLY the translation in the target language: one single continuous reply. Do not echo, repeat, "correct", normalize, or rewrite the source text. Never output the source language at all (no bilingual pairs, no "original / translation" layout). Do not use --- or any separator to show two versions. Do not change the user's Arabic numerals into Chinese characters in any echoed text—because you must not echo the source. No explanations, no labels, no quotation marks. Use line breaks only if the original clearly uses multiple lines."""


async def translate_with_claude(
    text: str, reply_context: Optional[str] = None
) -> str:
    """Claude로 한↔중 자동 감지 후 번역. reply_context가 있으면 답장 대상 문맥을 함께 전달."""
    if reply_context:
        user_content = f"이전 메시지 문맥: {reply_context}\n\n{text}"
    else:
        user_content = text
    client = _get_anthropic()

    last_error: Optional[Exception] = None
    max_attempts = 3
    retry_delays = [1.2, 2.5]  # 1차 실패 후 1.2초, 2차 실패 후 2.5초 대기

    for attempt in range(max_attempts):
        try:
            response = await client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=512,
                system=TRANSLATION_SYSTEM,
                messages=[{"role": "user", "content": user_content}],
            )
            if not response.content or not hasattr(response.content[0], "text"):
                return "번역 결과를 가져오지 못했습니다."
            return _strip_bilingual_artifact(response.content[0].text)
        except Exception as e:
            last_error = e
            # API 529/overloaded, 429, 일시적 네트워크 오류 등은 재시도
            error_text = str(e).lower()
            status_code = getattr(e, "status_code", None)
            retryable = (
                status_code in {429, 500, 502, 503, 504, 529}
                or "overloaded" in error_text
                or "timeout" in error_text
                or "connection" in error_text
                or "temporarily unavailable" in error_text
            )
            if not retryable or attempt == max_attempts - 1:
                break
            await asyncio.sleep(retry_delays[attempt])

    if last_error:
        raise RuntimeError(
            "현재 번역 서버가 혼잡합니다. 잠시 후 다시 시도해 주세요."
        ) from last_error
    raise RuntimeError("번역 중 알 수 없는 오류가 발생했습니다.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """텍스트 또는 미디어 캡션 수신 시 번역 후 답장."""
    if not update.message:
        return
    user_text = _extract_message_text(update.message)
    if not user_text:
        return
    _log_incoming_request(update, user_text)
    reply_context: Optional[str] = None
    if update.message.reply_to_message:
        reply_context = _extract_message_text(update.message.reply_to_message)

    if _is_url_only_message(user_text):
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=user_text,
            )
        except (TimedOut, NetworkError) as e:
            logger.warning(
                "링크 전송 후 텔레그램 네트워크/타임아웃(이미 전달됐을 수 있음): %s",
                e,
            )
        except Exception as e:
            error_text = _format_user_error(e)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"전송에 실패했습니다: {error_text}",
            )
        return

    try:
        translated = await translate_with_claude(
            user_text, reply_context=reply_context
        )
    except Exception as e:
        error_text = _format_user_error(e)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"번역 중 오류가 발생했습니다: {error_text}",
        )
        return

    # 번역은 성공했는데 sendMessage만 응답 읽기 타임아웃이 나는 경우가 많음(채팅에는 이미 올라감).
    # 그때 '번역 오류'를 보내면 사용자가 혼란스러우므로 TimedOut은 조용히 로그만 남김.
    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=translated,
        )
    except (TimedOut, NetworkError) as e:
        logger.warning(
            "번역 전송 후 텔레그램 네트워크/타임아웃(채팅에는 이미 표시됐을 수 있음): %s",
            e,
        )
    except Exception as e:
        error_text = _format_user_error(e)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"번역은 되었지만 전송에 실패했습니다: {error_text}",
        )


async def _telegram_error_handler(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """폴링·핸들러에서 터진 예외를 잡아 프로세스가 죽지 않게 함."""
    err = context.error
    if err is None:
        return
    if isinstance(err, Conflict):
        logger.error(
            "Conflict: 다른 곳에서 같은 봇으로 getUpdates(폴링) 중입니다. "
            "Bash·다른 서버·예전 프로세스를 모두 끄거나, 웹훅을 쓰던 적이 있으면 "
            "이번 main.py는 시작 시 delete_webhook을 호출합니다. 토큰이 유출됐다면 BotFather에서 Revoke.",
        )
        return
    if isinstance(err, NetworkError):
        logger.warning(
            "Telegram NetworkError (연결 일시 끊김·재시도 가능): %s",
            err,
            exc_info=err,
        )
        return
    logger.error("텔레그램 봇 처리 중 예외", exc_info=err)


async def _post_init(application: Application) -> None:
    """웹훅이 남아 있으면 폴링과 충돌(409 Conflict)하므로 제거."""
    await application.bot.delete_webhook(drop_pending_updates=False)
    logger.info("delete_webhook 완료(폴링 전용)")


def _verify_telegram_token(token: str) -> None:
    """폴링 전 getMe로 토큰 검사 — InvalidToken 시 로그에 한국어 안내가 먼저 보이게 함."""
    try:
        r = httpx.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=20.0,
        )
    except httpx.RequestError as e:
        raise RuntimeError(
            "Telegram 서버에 연결하지 못했습니다. 네트워크를 확인해 주세요."
        ) from e
    if r.status_code == 401:
        raise ValueError(
            "TELEGRAM_TOKEN이 거절되었습니다(Unauthorized). "
            "BotFather에서 해당 봇 → API Token → 문자를 다시 복사해 "
            ".env에 TELEGRAM_TOKEN=한줄로만 넣으세요(따옴표·앞뒤 공백 없음). "
            "Revoke 후에는 새로 받은 토큰만 유효합니다."
        )
    if r.status_code != 200:
        raise ValueError(f"getMe HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    if not data.get("ok"):
        raise ValueError(f"getMe 응답 실패: {data}")
    res = data.get("result") or {}
    logger.info(
        "Telegram 연결 확인됨: @%s (%s)",
        res.get("username", "?"),
        res.get("first_name", ""),
    )


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    # httpx INFO는 요청 URL에 봇 토큰이 포함되어 로그에 노출됨
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not TELEGRAM_TOKEN or not ANTHROPIC_API_KEY:
        raise ValueError(
            "TELEGRAM_TOKEN과 ANTHROPIC_API_KEY를 .env 파일에 설정해 주세요."
        )
    if ":" not in TELEGRAM_TOKEN:
        raise ValueError(
            "TELEGRAM_TOKEN 형식이 잘못되었습니다. BotFather가 준 '숫자:문자열' 전체를 한 줄로 넣어 주세요."
        )
    logger.info("환경파일 경로: %s", _ROOT / ".env")
    logger.info("TELEGRAM_TOKEN 로드됨 (봇 id=%s)", TELEGRAM_TOKEN.split(":", 1)[0])
    _verify_telegram_token(TELEGRAM_TOKEN)
    # PythonAnywhere ↔ api.telegram.org 구간이 불안정할 때 ReadError·NetworkError 완화
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(_post_init)
        .connect_timeout(45.0)
        .read_timeout(120.0)
        .write_timeout(120.0)
        .pool_timeout(60.0)
        .get_updates_connect_timeout(45.0)
        .get_updates_read_timeout(120.0)
        .get_updates_write_timeout(120.0)
        .get_updates_pool_timeout(60.0)
        .build()
    )
    app.add_error_handler(_telegram_error_handler)
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.Caption) & ~filters.COMMAND,
            handle_message,
        )
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
