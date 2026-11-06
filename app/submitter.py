"""신고 제출 어댑터.

- EmailSubmitter: 담당 기관 민원 메일로 사진(첨부)+민원문 전송. SMTP 설정이 있으면 자동 사용.
- MockSubmitter : SMTP 설정이 없을 때의 모의 접수(실제 전송 없음).

수신 주소(REPORT_TO_EMAIL)는 서버 환경변수에서만 읽는다. 사용자 입력으로 바꿀 수 없어
스팸 중계로 악용되지 않는다. 공식 API/제휴 채널이 생기면 Submitter를 상속해 교체한다.
"""
import mimetypes
import os
import random
import smtplib
import ssl
import threading
import time
from abc import ABC, abstractmethod
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from .analyzer import REPORT_TYPES


class Submitter(ABC):
    is_real = False
    label = "mock"
    to_masked = ""

    @abstractmethod
    def submit(self, report: dict) -> str:
        """제출 후 접수번호를 반환."""


def _receipt(prefix: str) -> str:
    return f"{prefix}-{time.strftime('%Y%m%d')}-{random.randint(1000, 9999)}"


class MockSubmitter(Submitter):
    """실제로 전송하지 않는 모의 접수."""

    def submit(self, report: dict) -> str:
        time.sleep(0.5)  # 네트워크 지연 흉내
        return _receipt("MOCK")


# ---- 이메일 -----------------------------------------------------------------
_sent_times: list[float] = []
_lock = threading.Lock()


def _check_rate_limit(max_per_hour: int) -> None:
    now = time.time()
    with _lock:
        _sent_times[:] = [t for t in _sent_times if now - t < 3600]
        if len(_sent_times) >= max_per_hour:
            raise RuntimeError("시간당 전송 한도를 초과했습니다. 잠시 후 다시 시도해 주세요")
        _sent_times.append(now)


def _one_line(text: str, limit: int = 120) -> str:
    """메일 헤더 인젝션 방지: 줄바꿈 제거."""
    return " ".join(str(text).split())[:limit]


def _mask(addr: str) -> str:
    name, _, domain = addr.partition("@")
    return (name[:1] + "***@" + domain) if domain else "***"


class EmailSubmitter(Submitter):
    is_real = True
    label = "email"

    def __init__(self):
        self.host = os.environ["SMTP_HOST"]
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.user = os.environ["SMTP_USER"]
        self.password = os.environ["SMTP_PASSWORD"]
        self.sender = os.getenv("MAIL_FROM") or self.user
        self.to = [a.strip() for a in os.environ["REPORT_TO_EMAIL"].split(",") if a.strip()]
        self.max_per_hour = int(os.getenv("MAIL_MAX_PER_HOUR", "10"))
        self.to_masked = ", ".join(_mask(a) for a in self.to)

    def _build(self, report: dict, receipt: str) -> EmailMessage:
        a = report.get("analysis") or {}
        type_label = REPORT_TYPES.get(a.get("type"), "기타")
        msg = EmailMessage()
        msg["Subject"] = _one_line(f"[City Eye 민원 접수 {receipt}] {report.get('title') or type_label}")
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.to)
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="city-eye")
        msg.set_content(
            f"City Eye 서비스를 통해 접수된 시민 제보입니다.\n\n"
            f"■ 접수번호: {receipt}\n"
            f"■ 신고 유형: {type_label}\n"
            f"■ 발생 위치: {report.get('address', '')}\n\n"
            f"■ 민원 내용\n{report.get('description', '')}\n\n"
            f"■ AI 사전 분석: 위험도 {a.get('severity', '-')}, 신뢰도 {a.get('confidence', '-')}\n"
            f"   (AI 분석은 참고용이며 현장 확인이 필요합니다)\n\n"
            f"※ 본 메일은 신고자가 내용을 확인하고 제출한 건을 서비스가 대신 전달한 것입니다.\n"
        )
        path = report.get("image_path")
        if path and Path(path).is_file():
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            maintype, _, subtype = ctype.partition("/")
            msg.add_attachment(Path(path).read_bytes(), maintype=maintype,
                               subtype=subtype or "octet-stream", filename=f"{receipt}{Path(path).suffix}")
        return msg

    def submit(self, report: dict) -> str:
        _check_rate_limit(self.max_per_hour)
        receipt = _receipt("CE")
        msg = self._build(report, receipt)
        ctx = ssl.create_default_context()
        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, context=ctx, timeout=20) as s:
                s.login(self.user, self.password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=20) as s:
                s.starttls(context=ctx)
                s.login(self.user, self.password)
                s.send_message(msg)
        return receipt


def email_configured() -> bool:
    return all(os.getenv(k, "").strip() for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "REPORT_TO_EMAIL"))


def get_submitter() -> Submitter:
    return EmailSubmitter() if email_configured() else MockSubmitter()
