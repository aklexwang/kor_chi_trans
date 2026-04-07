"""
텔레그램 실시간 통역 봇
- 한국어 → 중국어, 중국어 → 한국어 자동 감지 후 번역본만 답장
- 한글·한자 없이 영어만 있으면 API 없이 영어 원문 그대로 답장
- .env의 ALLOWED_USER_IDS / ALLOWED_CHAT_IDS 로 허용 사용자·채팅만 사용 가능(비우면 전체 공개)
- 일반 텍스트 + 사진/동영상 등 캡션(caption) 동일 처리
- Claude Sonnet + python-telegram-bot v21
"""

import asyncio
import difflib
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

import httpx
from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)
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
CLAUDE_MODEL = (os.getenv("CLAUDE_MODEL") or "claude-sonnet-4-6").strip() or "claude-sonnet-4-6"
# Anthropic HTTP: 응답 지연·네트워크 불안정 대비 (초). 생략 시 read 180 / connect 30
_anthropic_read_timeout = float(os.getenv("ANTHROPIC_READ_TIMEOUT", "180"))
_anthropic_connect_timeout = float(os.getenv("ANTHROPIC_CONNECT_TIMEOUT", "30"))


def _env_int_id_set(var: str) -> frozenset[int]:
    """콤마로 구분된 정수 ID 목록(공백 무시). 잘못된 항목은 건너뜀."""
    raw = (os.getenv(var) or "").strip()
    if not raw:
        return frozenset()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            logger.warning("%s에 숫자가 아닌 값 무시: %r", var, part)
    return frozenset(out)


# 비어 있으면 제한 없음(누구나 사용). 하나라도 넣으면 화이트리스트만 허용.
ALLOWED_USER_IDS = _env_int_id_set("ALLOWED_USER_IDS")
ALLOWED_CHAT_IDS = _env_int_id_set("ALLOWED_CHAT_IDS")

_anthropic_client: Optional[AsyncAnthropic] = None


def _anthropic_model_candidates() -> list[str]:
    """우선 CLAUDE_MODEL, API가 404일 때만 콤마 구분 폴백(기본: 널리 쓰이는 스냅샷) 순서로 시도."""
    primary = CLAUDE_MODEL
    raw_fb = (os.getenv("CLAUDE_MODEL_FALLBACK") or "").strip()
    if not raw_fb:
        raw_fb = "claude-sonnet-4-20250514,claude-3-5-sonnet-20241022"
    extras = [x.strip() for x in raw_fb.split(",") if x.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for m in [primary, *extras]:
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


class TranslationValidationError(RuntimeError):
    """모델 출력이 타깃 언어/형식 규칙을 위반했을 때 내부 재시도용 예외."""


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


def _anthropic_error_detail_text(exc: BaseException) -> str:
    """Messages API 오류 JSON의 error.message 추출(로그·사용자 안내용)."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()
    return ""


def _runtime_message_for_translation_api_error(exc: BaseException) -> Optional[str]:
    """Anthropic/HTTP 오류를 사용자용 한국어로. None이면 원인 불명으로 간주."""
    if isinstance(exc, AuthenticationError):
        return (
            "Anthropic API 키가 인증되지 않았습니다. .env의 ANTHROPIC_API_KEY를 "
            "console.anthropic.com 에서 복사한 값으로 다시 넣어 주세요(따옴표·앞뒤 공백 없음)."
        )
    if isinstance(exc, PermissionDeniedError):
        return (
            "Anthropic API 사용이 거부되었습니다(403). 계정·결제·조직 정책을 콘솔에서 확인해 주세요."
        )
    if isinstance(exc, NotFoundError):
        return (
            "지정한 Claude 모델을 API에서 찾을 수 없습니다(404). "
            f".env의 CLAUDE_MODEL(현재: {CLAUDE_MODEL})을 계정에서 지원하는 모델 ID로 바꿔 주세요. "
            "예: claude-sonnet-4-20250514, claude-3-5-sonnet-20241022"
        )
    if isinstance(exc, BadRequestError):
        detail = _anthropic_error_detail_text(exc)
        base = "번역 요청이 API에서 거절되었습니다(400)."
        if detail:
            if len(detail) > 300:
                detail = detail[:297] + "..."
            return f"{base} 사유: {detail}"
        return base + " 서버 로그를 확인해 주세요."
    if isinstance(exc, RateLimitError):
        return (
            "Anthropic API 요청 한도에 걸렸습니다(429). "
            "잠시 후 다시 시도하거나 호출 빈도를 줄여 주세요."
        )
    if isinstance(exc, APIStatusError):
        if 500 <= exc.status_code < 600 or exc.status_code == 529:
            return "현재 번역 서버가 혼잡합니다. 잠시 후 다시 시도해 주세요."
        if 400 <= exc.status_code < 500:
            return (
                f"번역 API 오류(HTTP {exc.status_code})입니다. "
                "서버 로그를 확인하거나 잠시 후 다시 시도해 주세요."
            )
    if isinstance(exc, APIConnectionError):
        return "번역 API에 연결하지 못했습니다. 네트워크를 확인하고 잠시 후 다시 시도해 주세요."
    return None


def _format_user_error(exc: BaseException) -> str:
    """타임아웃·일시 오류는 한국어 안내로 통일."""
    friendly = "현재 번역 서버가 혼잡합니다. 잠시 후 다시 시도해 주세요."
    raw = str(exc).lower()
    if "credit balance is too low" in raw or "purchase credits" in raw:
        return (
            "Anthropic API 크레딧이 부족합니다. "
            "콘솔의 Plans & Billing에서 크레딧을 충전한 뒤 다시 시도해 주세요."
        )
    if isinstance(exc, (APITimeoutError, asyncio.TimeoutError)):
        return friendly
    if isinstance(exc, httpx.TimeoutException):
        return friendly
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


def _is_english_only_message(text: str) -> bool:
    """한글·한자가 없고 라틴 문자(A–Z)가 있으면 영어로 보고 번역 없이 그대로 답장."""
    if not text.strip():
        return False
    if _hangul_len(text) > 0 or _hanzi_len(text) > 0:
        return False
    return bool(re.search(r"[A-Za-z]", text))


def _first_text_block_from_response(response: Any) -> Optional[str]:
    """응답 content에서 첫 text 블록만 사용(4.x thinking 블록이 앞에 올 수 있음)."""
    blocks = getattr(response, "content", None) or []
    for block in blocks:
        t = getattr(block, "text", None)
        if isinstance(t, str) and t.strip():
            return t
    return None


def _strip_bilingual_artifact(reply: str) -> str:
    """모델이 '원문 다듬기\\n---\\n번역'처럼 줄 때 번역부만 사용."""
    t = reply.strip()
    if not t:
        return t
    chunks = re.split(r"\n\s*-{3,}\s*\n", t)
    if len(chunks) >= 2:
        return chunks[-1].strip()
    return t


def _hangul_len(s: str) -> int:
    return len(re.findall(r"[\uAC00-\uD7A3]", s))


def _hanzi_len(s: str) -> int:
    return len(re.findall(r"[\u4e00-\u9FFF]", s))


def _squish_ws(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _utterance_near_duplicate(a: str, b: str, threshold: float = 0.88) -> bool:
    """모델이 원문을 한 줄 더 붙인 경우(거의 동일 문장) 제거용."""
    x, y = _squish_ws(a), _squish_ws(b)
    if not x or not y:
        return False
    if x == y:
        return True
    if min(len(x), len(y)) < 6:
        return x == y
    return difflib.SequenceMatcher(None, x, y).ratio() >= threshold


def _strip_source_language_echo(user_text: str, reply: str) -> str:
    """한→중인데 한글 줄을 그대로 붙이거나, 중→한인데 한 줄이 원문 복제인 경우 제거."""
    reply = reply.strip()
    if not reply:
        return reply
    h_in, z_in = _hangul_len(user_text), _hanzi_len(user_text)
    if h_in == 0 and z_in == 0:
        return reply
    target_zh = h_in > z_in
    target_ko = z_in > h_in
    if not target_zh and not target_ko:
        return reply

    lines = [ln.strip() for ln in reply.split("\n") if ln.strip()]
    if not lines:
        return reply

    if target_zh:
        kept: list[str] = []
        for ln in lines:
            if _utterance_near_duplicate(ln, user_text):
                continue
            hg, hz = _hangul_len(ln), _hanzi_len(ln)
            if hg > 0 and hz == 0:
                continue
            if hz > hg:
                kept.append(ln)
        if kept:
            return "\n".join(kept).strip()
        # 한 줄에 한글+한자 혼용(예: "한 시간만 睡一觉")은 통과시키지 않음 — 순수 한자(중국어) 줄만 후보
        candidates = [
            ln
            for ln in lines
            if _hanzi_len(ln) > 0
            and _hangul_len(ln) == 0
            and not _utterance_near_duplicate(ln, user_text)
        ]
        if candidates:
            return max(
                candidates,
                key=lambda ln: (_hanzi_len(ln), -_hangul_len(ln)),
            ).strip()
        # 한→중인데 모델이 한국어로만 답한 경우 사용자에게 노출하지 않고 재시도
        if _hangul_len(reply) > _hanzi_len(reply):
            logger.warning(
                "한→중 요청인데 응답이 한국어 위주(재시도): %r",
                reply[:160],
            )
            raise TranslationValidationError(
                "expected_chinese_only_but_got_korean"
            )
        return reply

    kept_ko: list[str] = []
    for ln in lines:
        if _utterance_near_duplicate(ln, user_text):
            continue
        hg, hz = _hangul_len(ln), _hanzi_len(ln)
        if hz > 0 and hg == 0:
            continue
        if hg > hz:
            kept_ko.append(ln)
    if kept_ko:
        return "\n".join(kept_ko).strip()
    candidates_ko = [
        ln
        for ln in lines
        if _hangul_len(ln) > 0 and not _utterance_near_duplicate(ln, user_text)
    ]
    if candidates_ko:
        return max(
            candidates_ko,
            key=lambda ln: (_hangul_len(ln) - _hanzi_len(ln), _hangul_len(ln)),
        ).strip()
    if _hanzi_len(reply) > _hangul_len(reply):
        logger.warning(
            "중→한 요청인데 응답이 중국어 위주(재시도): %r",
            reply[:160],
        )
        raise TranslationValidationError("expected_korean_only_but_got_chinese")
    return reply


def _assert_pure_target_script(user_text: str, translated: str) -> str:
    """한→중이면 출력에 한글 음절 1개도 없어야 함. 중→한이면 한자만인 출력 등은 거부."""
    t = translated.strip()
    if not t:
        return t
    h_in, z_in = _hangul_len(user_text), _hanzi_len(user_text)
    if not (h_in > z_in or z_in > h_in):
        return t
    if h_in > z_in:
        if _hangul_len(t) > 0:
            logger.warning("한→중인데 번역에 한글 잔류: %r", t[:200])
            raise TranslationValidationError("hangul_found_in_chinese_output")
        return t
    if z_in > h_in:
        if _hangul_len(t) == 0 and _hanzi_len(t) > 0:
            logger.warning("중→한인데 출력이 한자만: %r", t[:200])
            raise TranslationValidationError("hanzi_only_in_korean_output")
        if _hanzi_len(t) > _hangul_len(t):
            logger.warning("중→한인데 출력에 한자 비중이 더 큼: %r", t[:200])
            raise TranslationValidationError("hanzi_dominant_in_korean_output")
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

**Correct output language (non-negotiable):**
- **Korean source** → output **Chinese only** (口语, Hanzi). **Never** answer in Korean. **Never** “rephrase” Korean into different Korean (same-language rewriting is forbidden).
- **Chinese source** → output **Korean only** (Hangul). **Never** answer in Chinese. **Never** “rephrase” Chinese into different Chinese.
- **Zero Hangul in Chinese output:** If the source is Korean, **every** meaningful part must be in Chinese. **Wrong:** **한 시간만 睡一觉。** (Korean time phrase + Chinese verb). **Right:** one full 口语 sentence such as **我就睡一个小时。** / **我睡一个小时就行。** — **no** Hangul letters anywhere in your reply.

**Tone, respect, and propositional fidelity:**
- You are interpreting for people who **do not share a language**: the other side will read your output. Keep the **same meaning and degree of criticism** as the source—do **not** weaken facts or deny what the speaker said.
- **Do not escalate vulgarity or swap insults** for different, harsher ones (e.g. do **not** turn **그지같다**-level wording into **개같다** or other stronger slurs). Match strength; do not “spice up.”
- Where the source is rough but the idea is “very bad / terrible (work style, attitude),” prefer natural target-language equivalents that convey that judgment **without** piling gratuitous extra offense toward the listener’s face—still **honest** to the speaker’s intent (e.g. work style “真差劲 / 真不像话 / 太差了” style 口语, not inventing new attacks).

**You are an interpreter, not a Q&A assistant.** Never answer the user's question, never supply facts, geography, explanations, or advice they did not say. Do not "helpfully" respond to what they asked—only translate their **words** (their utterance) into the target language.
- Korean question (e.g. **한국은 어디 있니?**) → Chinese must be the **same question** in natural 口语 (e.g. **韩国在哪儿啊？** / **韩国在什么地方？**), **not** an answer like **韩国在亚洲东部…**.
- Chinese question → Korean must stay a **question** in 구어체, not an answer.
- Same for commands, complaints, small talk: output only the equivalent utterance, with no added content.

**Faithfulness and zero hallucination (mandatory):**
- Every situation you describe in the translation must appear in the source. **Never** invent body parts, senses, disabilities, medical states, or random plot details (e.g. if the source does **not** mention vision, **never** output Korean like **눈이 안 보여** or any “can’t see” wording).
- **Never** add parenthetical glosses or alternatives the speaker did not say (no **(혹은 …)**, no “or it could mean…”, no footnotes).
- **稍等 / 等一下 / 你稍等我 / 你等我(一下)** = “wait a moment” / “wait for me (a bit).” Natural Korean examples: **잠깐만 기다려 주세요**, **당신은 나를 잠시만 기다려 주세요**, **나 좀만 기다려줘** (match **你** politeness). **Wrong:** any unrelated scenario (blindness, “I can’t see,” etc.).
- **稍等我问下 … 几个人** (asking how many people **妹妹** is coming with): keep **妹妹** as **여동생** (or **그 여동생**) as context implies; use natural **몇 명이랑 같이 오는지**-style wording. Do **not** over-explain kinship with extra parentheses.

- Korean input → output only in natural spoken Chinese (口语). Match formality to the message (chatty stays chatty; polite/formal stays appropriately polite but still sounds like real speech).
- Chinese input (Simplified or Traditional) → output only in natural spoken Korean (구어체), same principles.

Short replies about already knowing / being aware (very common in chat):
- Korean phrases like **알고 있어**, **알고 있다**, **이미 알아**, **그거 알아** (meaning the speaker *already* knew—often replying in a group that they were not newly informed) → Chinese should use **我知道**, **我都知道**, **这个我知道**, **我早就知道了**, etc. as fits the tone. **Avoid defaulting to 知道了** when it would sound like a fresh acknowledgment ("got it / noted") rather than prior awareness. 知道了 fits "OK I hear you" after new info; **我知道** fits "I'm already aware of that."
- Chinese **我知道** in dialogue (stating awareness, same page as others) → Korean should express ongoing/shared prior knowledge: **나도 알고 있어**, **(그거) 알고 있어**, **이미 알고 있어**, **나도 알고 있다**. Do not default to bare **나 알아** for 我知道; it often sounds too curt or mismatched compared to "I'm aware too / already knew."

Pronouns and "who acts on whom" (do not flip perspective):
- Chinese **他 / 她 / 他们 / 人家** and Korean **그 / 그녀 / 그들 / 걔 / 쟤** refer to **third parties** unless context clearly says otherwise. **Never** render **他** (him/her) as **나** (me) or **我** as the object of **问** when the source means asking **another person**. Example: **我问他一下** = "I'll ask him / let me ask him" → natural Korean e.g. **그한테 물어볼게**, **걔한테 한번 물어볼게** — **not** **나한테 물어볼게** (that means asking oneself). Same care for **你/您 ↔ 너/당신**, **我 ↔ 나/저**: keep subject/object roles aligned with the source.

Language choice (critical):
- If the message is **mostly Korean** (hangul dominates) → output **Chinese only** (口语).
- If the message is **mostly Chinese** (hanzi dominates) → output **Korean only** (구어체).
- Never output **English** except unavoidable proper nouns/brand names as natives would leave them.
- If Korean and Chinese are mixed in one message, translate each segment into the other language so the whole reply reads naturally in **one** target language (do not leave one language untranslated).

**Single-script output (no echo, no bilingual lines):**
- **Never** repeat the user’s message in the source script. Do **not** put Korean on the first line and Chinese on the second (that is forbidden). The entire reply must be **only** the target language.
- Do **not** mix Hangul and Hanzi inside one word or token (wrong: **관心도**). Write normal **关心** / **关心度** in pure Chinese, or pure Korean **관심도**—never hybrid spellings.

**Context (when a “replied-to” block is provided):**
- That block is **only** for disambiguation (who is 他, topic continuity). **Do not** translate it as the main output, **do not** reply to it with unrelated sentences, and **do not** output lines that belong only to the context (e.g. if the final utterance to translate does not say “没兴趣做这件事,” you must **not** output that). **Only** the **last** utterance in the user message—the one explicitly marked as what to translate—gets rendered into the other language.

Reply with ONLY the translation in the target language: one single continuous reply. Do not echo, repeat, "correct", normalize, or rewrite the source text. Never output the source language at all (no bilingual pairs, no "original / translation" layout). Do not use --- or any separator to show two versions. Do not change the user's Arabic numerals into Chinese characters in any echoed text—because you must not echo the source. No explanations, no labels, no quotation marks. Use line breaks only if the original clearly uses multiple lines."""


async def translate_with_claude(
    text: str, reply_context: Optional[str] = None
) -> str:
    """Claude로 한↔중 자동 감지 후 번역. reply_context가 있으면 답장 대상 문맥을 함께 전달."""
    # 문맥은 한국어로 쓰이면 모델이 문맥까지 중국어로 번역하는 경우가 있어, 영어 메타 지시로 분리
    if reply_context:
        user_content = (
            "Context from the message being replied to (for disambiguation only; "
            "do NOT translate this block as your answer, do NOT respond to it, "
            "and do NOT output sentences that appear only in this block):\n"
            f"{reply_context}\n\n"
            "Translate ONLY the following final utterance into the other language "
            "(Korean ↔ spoken Chinese). Your entire reply must be that translation "
            "and nothing else:\n"
            f"{text}"
        )
    else:
        user_content = (
            "Translate ONLY the following utterance into the other language "
            "(Korean ↔ spoken Chinese). Output nothing else:\n"
            f"{text}"
        )
    client = _get_anthropic()
    base_user_content = user_content
    models = _anthropic_model_candidates()
    last_error: Optional[Exception] = None
    max_attempts = 4
    retry_delays = [1.0, 2.0, 3.0]

    for model_name in models:
        user_content = base_user_content
        try_next_model = False
        for attempt in range(max_attempts):
            try:
                # temperature 미지정: Claude 4.x 계열은 temperature+top_p 동시 지정 시 400이 나는 경우가 있어
                # SDK/게이트웨이 조합을 피하고 API 기본 샘플링을 씀.
                response = await client.messages.create(
                    model=model_name,
                    max_tokens=1024,
                    system=TRANSLATION_SYSTEM,
                    messages=[{"role": "user", "content": user_content}],
                )
                raw_text = _first_text_block_from_response(response)
                if not raw_text:
                    return "번역 결과를 가져오지 못했습니다."
                raw = _strip_bilingual_artifact(raw_text)
                out = _strip_source_language_echo(text, raw)
                return _assert_pure_target_script(text, out)
            except (AuthenticationError, PermissionDeniedError) as e:
                msg = _runtime_message_for_translation_api_error(e) or str(e)
                raise RuntimeError(msg) from e
            except BadRequestError as e:
                logger.error(
                    "Anthropic 400 model=%s body=%r",
                    model_name,
                    getattr(e, "body", None),
                )
                msg = _runtime_message_for_translation_api_error(e) or str(e)
                raise RuntimeError(msg) from e
            except NotFoundError as e:
                last_error = e
                logger.warning(
                    "Claude 모델 404(%s) — 다음 후보 시도: %s",
                    model_name,
                    models,
                )
                try_next_model = True
                break
            except Exception as e:
                last_error = e
                lowered = str(e).lower()
                if "credit balance is too low" in lowered or "purchase credits" in lowered:
                    raise RuntimeError(
                        "Anthropic API 크레딧이 부족합니다. "
                        "Plans & Billing에서 충전 후 다시 시도해 주세요."
                    ) from e
                error_text = lowered
                status_code = getattr(e, "status_code", None)
                retryable = (
                    isinstance(e, TranslationValidationError)
                    or status_code
                    in {429, 500, 502, 503, 504, 529}
                    or "overloaded" in error_text
                    or "timeout" in error_text
                    or "connection" in error_text
                    or "temporarily unavailable" in error_text
                )
                if not retryable or attempt == max_attempts - 1:
                    break
                if isinstance(e, TranslationValidationError):
                    h_in, z_in = _hangul_len(text), _hanzi_len(text)
                    if h_in > z_in:
                        user_content = (
                            "Korean source detected. Retry now.\n"
                            "Output MUST be Chinese (Hanzi) only.\n"
                            "Do not output any Hangul, labels, explanations, or source echo.\n"
                            "Translate this utterance only:\n"
                            f"{text}"
                        )
                    elif z_in > h_in:
                        user_content = (
                            "Chinese source detected. Retry now.\n"
                            "Output MUST be Korean (Hangul) only.\n"
                            "Do not output Chinese characters, labels, explanations, or source echo.\n"
                            "Translate this utterance only:\n"
                            f"{text}"
                        )
                await asyncio.sleep(retry_delays[attempt])
        if try_next_model:
            continue
        break

    if last_error:
        if isinstance(last_error, TranslationValidationError):
            raise RuntimeError(
                "번역 결과가 불안정했습니다. 같은 문장을 한 번 더 보내 주세요."
            ) from last_error
        if isinstance(last_error, NotFoundError):
            user_msg = (
                "Claude 모델을 API에서 찾을 수 없습니다(404). "
                f"시도한 모델: {', '.join(models)}. "
                "Anthropic 콘솔에서 계정에 열린 모델 ID를 확인해 주세요."
            )
            logger.error(user_msg, exc_info=last_error)
            raise RuntimeError(user_msg) from last_error
        user_msg = _runtime_message_for_translation_api_error(last_error)
        if user_msg is None:
            logger.error(
                "translate_with_claude 실패(원인 분류 불가). models=%s err=%r",
                models,
                last_error,
                exc_info=last_error,
            )
            user_msg = (
                "번역 중 오류가 발생했습니다. 서버 로그를 확인해 주세요. "
                "(API 키·모델명·네트워크 문제일 수 있습니다.)"
            )
        else:
            logger.warning(
                "translate_with_claude 최종 실패: models=%s %s",
                models,
                last_error,
            )
        raise RuntimeError(user_msg) from last_error
    raise RuntimeError("번역 중 알 수 없는 오류가 발생했습니다.")


_ACCESS_DENIED_TEXT = (
    "이 봇은 허용된 사용자·채팅방에서만 쓸 수 있습니다. 관리자에게 문의하세요."
)


def _telegram_access_allowed(update: Update) -> bool:
    """ALLOWED_USER_IDS / ALLOWED_CHAT_IDS 가 모두 비어 있으면 제한 없음. 하나라도 있으면 화이트리스트만."""
    if not ALLOWED_USER_IDS and not ALLOWED_CHAT_IDS:
        return True
    u = update.effective_user
    c = update.effective_chat
    uid = getattr(u, "id", None)
    cid = getattr(c, "id", None)
    if uid is None or cid is None:
        return False
    if ALLOWED_USER_IDS and not ALLOWED_CHAT_IDS:
        return uid in ALLOWED_USER_IDS
    if ALLOWED_CHAT_IDS and not ALLOWED_USER_IDS:
        return cid in ALLOWED_CHAT_IDS
    return uid in ALLOWED_USER_IDS or cid in ALLOWED_CHAT_IDS


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """텍스트 또는 미디어 캡션 수신 시 번역 후 답장."""
    if not update.message:
        return
    user_text = _extract_message_text(update.message)
    if not user_text:
        return
    if not _telegram_access_allowed(update):
        logger.info(
            "접근 거부 chat_id=%s user_id=%s username=%s",
            getattr(update.effective_chat, "id", None),
            getattr(update.effective_user, "id", None),
            getattr(update.effective_user, "username", None),
        )
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=_ACCESS_DENIED_TEXT,
            )
        except (TimedOut, NetworkError):
            pass
        except Exception:
            pass
        return
    _log_incoming_request(update, user_text)
    reply_context: Optional[str] = None
    if update.message.reply_to_message:
        reply_context = _extract_message_text(update.message.reply_to_message)

    if _is_url_only_message(user_text) or _is_english_only_message(user_text):
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=user_text,
            )
        except (TimedOut, NetworkError) as e:
            logger.warning(
                "원문 그대로 전송 후 텔레그램 네트워크/타임아웃(이미 전달됐을 수 있음): %s",
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
    logger.info(
        "Claude 모델 시도 순서(404 시 자동 폴백): %s",
        " → ".join(_anthropic_model_candidates()),
    )
    if ALLOWED_USER_IDS or ALLOWED_CHAT_IDS:
        logger.info(
            "텔레그램 접근 제한 활성화: 허용 user_ids=%s chat_ids=%s",
            sorted(ALLOWED_USER_IDS) if ALLOWED_USER_IDS else "(미사용)",
            sorted(ALLOWED_CHAT_IDS) if ALLOWED_CHAT_IDS else "(미사용)",
        )
    else:
        logger.info("텔레그램 접근 제한 없음(ALLOWED_USER_IDS/ALLOWED_CHAT_IDS 비어 있음)")
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
