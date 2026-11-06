"""신고 제출 어댑터. 기본은 모의(mock) 제출.

실제 연동 시 Submitter를 상속해 구현하세요.
 - ApiSubmitter: 기관이 제공하는 공식 API/제휴 채널 (1순위)
 - EmailSubmitter: 구청 민원 메일 전송
 - PlaywrightSubmitter: 신고 사이트 양식 자동 입력 (약관·본인인증·캡차 확인 필수)
"""
import random
import time
from abc import ABC, abstractmethod


class Submitter(ABC):
    @abstractmethod
    def submit(self, report: dict) -> str:
        """제출 후 접수번호를 반환."""


class MockSubmitter(Submitter):
    """실제 기관으로 전송하지 않는 데모용 접수. 실채널 연동 시 is_real=True 어댑터로 교체."""

    is_real = False

    def submit(self, report: dict) -> str:
        time.sleep(0.5)  # 네트워크 지연 흉내
        return f"MOCK-{time.strftime('%Y%m%d')}-{random.randint(1000, 9999)}"


def get_submitter() -> Submitter:
    return MockSubmitter()
