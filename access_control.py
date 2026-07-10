"""Google Authenticator(TOTP) 기반 봇 사용 인증 — 관리자만 OTP 앱 보유, 코드를 알려준 사람만 사용."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pyotp

logger = logging.getLogger(__name__)

_OTP_CODE_RE = re.compile(r"^\d{6}$")


def generate_totp_secret() -> str:
    """새 TOTP 시크릿 생성(관리자 Google Authenticator 등록용)."""
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, issuer: str, account_name: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=issuer)


class TotpAccessControl:
    def __init__(
        self,
        *,
        store_path: Path,
        secret: str,
        enabled: bool,
        session_hours: int = 24,
        valid_window: int = 1,
        issuer: str = "KorChiTrans Bot",
        max_failures: int = 5,
        lockout_minutes: int = 15,
    ) -> None:
        self.store_path = store_path
        self.secret = secret.strip()
        self.enabled = enabled and bool(self.secret)
        self.session_hours = max(0, session_hours)
        self.valid_window = max(0, valid_window)
        self.issuer = issuer
        self.max_failures = max(1, max_failures)
        self.lockout_minutes = max(1, lockout_minutes)
        self._totp = pyotp.TOTP(self.secret) if self.enabled else None
        self._records: dict[str, dict] = {}
        self._failures: dict[str, dict] = {}
        self._used_codes: dict[str, str] = {}
        if self.enabled:
            self._load()

    def _load(self) -> None:
        if not self.store_path.is_file():
            self._records = {}
            return
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                users = raw.get("users")
                if isinstance(users, dict):
                    self._records = {str(k): v for k, v in users.items() if isinstance(v, dict)}
                else:
                    self._records = {str(k): v for k, v in raw.items() if isinstance(v, dict)}
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("인증 목록 로드 실패(빈 목록으로 시작): %s", e)
            self._records = {}

    def _save(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"users": self._records}
        self.store_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _session_expires_at(self, now: datetime) -> Optional[str]:
        if self.session_hours <= 0:
            return None
        return (now + timedelta(hours=self.session_hours)).isoformat()

    def is_authorized(self, user_id: int) -> bool:
        if not self.enabled:
            return True
        key = str(user_id)
        rec = self._records.get(key)
        if not rec:
            return False
        expires_at = rec.get("expires_at")
        if not expires_at:
            return True
        try:
            exp = datetime.fromisoformat(expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        if datetime.now(timezone.utc) >= exp:
            del self._records[key]
            self._save()
            return False
        return True

    def _is_locked_out(self, user_id: int) -> bool:
        rec = self._failures.get(str(user_id))
        if not rec:
            return False
        until = rec.get("locked_until")
        if not until:
            return False
        try:
            lock = datetime.fromisoformat(until)
            if lock.tzinfo is None:
                lock = lock.replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        if datetime.now(timezone.utc) < lock:
            return True
        self._failures.pop(str(user_id), None)
        return False

    def _record_failure(self, user_id: int) -> None:
        key = str(user_id)
        rec = self._failures.get(key, {"count": 0})
        rec["count"] = int(rec.get("count", 0)) + 1
        if rec["count"] >= self.max_failures:
            rec["locked_until"] = (
                datetime.now(timezone.utc) + timedelta(minutes=self.lockout_minutes)
            ).isoformat()
            rec["count"] = 0
        self._failures[key] = rec

    def _clear_failure(self, user_id: int) -> None:
        self._failures.pop(str(user_id), None)

    def _code_already_used(self, code: str, user_id: int) -> bool:
        """같은 6자리 코드로 다른 사람이 먼저 인증했으면 재사용 불가."""
        owner = self._used_codes.get(code)
        if owner is None:
            return False
        return owner != str(user_id)

    def authorize(self, user_id: int, code: str) -> None:
        now = datetime.now(timezone.utc)
        self._records[str(user_id)] = {
            "authorized_at": now.isoformat(),
            "expires_at": self._session_expires_at(now),
        }
        self._used_codes[code] = str(user_id)
        self._clear_failure(user_id)
        self._save()
        logger.info("TOTP 인증 성공 user_id=%s", user_id)

    def revoke(self, user_id: int) -> bool:
        key = str(user_id)
        if key not in self._records:
            return False
        del self._records[key]
        self._save()
        logger.info("TOTP 인증 해제 user_id=%s", user_id)
        return True

    def revoke_all(self) -> int:
        count = len(self._records)
        self._records = {}
        self._save()
        logger.info("TOTP 인증 전체 해제 count=%s", count)
        return count

    def list_authorized(self) -> list[tuple[int, dict]]:
        out: list[tuple[int, dict]] = []
        for key, rec in self._records.items():
            try:
                out.append((int(key), rec))
            except ValueError:
                continue
        return sorted(out, key=lambda x: x[0])

    def parse_otp_code(self, text: str) -> Optional[str]:
        code = text.strip().replace(" ", "")
        if _OTP_CODE_RE.match(code):
            return code
        return None

    def verify_code(self, code: str) -> bool:
        if not self._totp:
            return False
        return bool(self._totp.verify(code, valid_window=self.valid_window))

    def is_locked_out(self, user_id: int) -> bool:
        return self._is_locked_out(user_id)

    def try_authenticate(self, user_id: int, code: str) -> tuple[bool, str]:
        """(성공 여부, 사용자에게 보낼 메시지)"""
        if self._is_locked_out(user_id):
            return False, (
                f"인증 시도가 너무 많습니다. {self.lockout_minutes}분 후 다시 시도하거나 "
                "관리자에게 문의하세요."
            )
        if self._code_already_used(code, user_id):
            return False, (
                "이 인증 코드는 이미 사용되었습니다.\n"
                "관리자에게 새 6자리 코드를 요청해 주세요."
            )
        if not self.verify_code(code):
            self._record_failure(user_id)
            return False, self.denied_message()
        self.authorize(user_id, code)
        return True, self.success_message()

    @property
    def start_message(self) -> str:
        return (
            "이 봇은 관리자 승인이 필요합니다.\n\n"
            "관리자에게 연락해 **지금 유효한 6자리 인증 코드**를 받은 뒤, "
            "그 숫자만 이 채팅에 보내 주세요.\n"
            "예: 482913\n\n"
            "코드는 약 30초마다 바뀝니다. 만료됐으면 관리자에게 새 코드를 요청하세요."
        )

    def success_message(self) -> str:
        if self.session_hours > 0:
            return (
                f"인증되었습니다. 이제 번역을 사용할 수 있습니다.\n"
                f"({self.session_hours}시간 후에는 관리자에게 새 코드가 필요합니다.)"
            )
        return "인증되었습니다. 이제 번역을 사용할 수 있습니다."

    def denied_message(self) -> str:
        return (
            "인증 코드가 올바르지 않거나 만료되었습니다.\n"
            "관리자에게 **최신 6자리 코드**를 다시 요청해 주세요."
        )

    def prompt_message(self) -> str:
        return (
            "번역을 사용하려면 관리자가 알려준 6자리 인증 코드가 필요합니다.\n"
            "코드만 보내 주세요. (/start 로 안내 보기)"
        )

    def lockout_message(self) -> str:
        return (
            f"인증 시도가 너무 많습니다. {self.lockout_minutes}분 후 다시 시도하거나 "
            "관리자에게 문의하세요."
        )
