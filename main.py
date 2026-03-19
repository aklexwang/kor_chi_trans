"""
텔레그램 실시간 통역 봇
- 한국어 → 중국어, 중국어 → 한국어 자동 감지 후 번역본만 답장
- Claude 3.5 Sonnet + python-telegram-bot v21
"""

import asyncio
import os

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

TRANSLATION_SYSTEM = """You are a translator. The user will send a short message in either Korean or Chinese.
- If the message is in Korean, translate it into Chinese only.
- If the message is in Chinese, translate it into Korean only.
Reply with ONLY the translation, no explanation, no source language label, no quotation marks. One line only."""


async def translate_with_claude(text: str) -> str:
    """Claude 3.5 Sonnet으로 한↔중 자동 감지 후 번역."""
    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=512,
        system=TRANSLATION_SYSTEM,
        messages=[{"role": "user", "content": text}],
    )
    if not response.content or not hasattr(response.content[0], "text"):
        return "번역 결과를 가져오지 못했습니다."
    return response.content[0].text.strip()


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """텍스트 메시지 수신 시 번역 후 답장."""
    if not update.message or not update.message.text:
        return
    user_text = update.message.text.strip()
    if not user_text:
        return
    try:
        translated = await translate_with_claude(user_text)
        await update.message.reply_text(translated)
    except Exception as e:
        await update.message.reply_text(f"번역 중 오류가 발생했습니다: {str(e)}")


def main() -> None:
    if not TELEGRAM_TOKEN or not ANTHROPIC_API_KEY:
        raise ValueError(
            "TELEGRAM_TOKEN과 ANTHROPIC_API_KEY를 .env 파일에 설정해 주세요."
        )
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
