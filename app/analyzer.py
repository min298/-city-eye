"""AI 기능(서버 전용): OpenAI gpt-5-mini로 사진 분석 및 민원문 작성.

OPENAI_API_KEY는 .env.local 에서 서버 프로세스가 읽으며, 브라우저로는 전달되지 않는다.
"""
import base64
import json
import os
import re

REPORT_TYPES = {
    "illegal_parking": "불법 주정차",
    "pothole": "도로 파손(포트홀)",
    "illegal_dumping": "쓰레기 불법 투기",
    "damaged_facility": "공공시설물 파손",
    "other": "기타",
    "not_reportable": "신고 대상 아님",
}

MODEL = "gpt-5-mini"

PROMPT = f"""당신은 시민 신고 사진을 분석하는 도우미입니다.
사진을 보고 아래 JSON 형식으로만 답하세요.

{{
  "type": "{'|'.join(REPORT_TYPES)} 중 하나",
  "confidence": 0.0~1.0,
  "severity": "low|medium|high",
  "title": "신고 제목(40자 이내)",
  "description": "사진에서 객관적으로 보이는 사실만 서술한 신고 본문(2~4문장)",
  "evidence": ["판단 근거 목록"],
  "privacy_flags": ["얼굴", "차량번호판" 등 사진에 포함된 개인정보]
}}

규칙: 보이지 않는 사실은 추측하지 말고, 신고 대상이 아니면 type을 not_reportable로 하세요."""


def _model() -> str:
    return os.getenv("OPENAI_MODEL", MODEL)


def _client():
    """키가 없으면 None (데모 모드)."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    from openai import OpenAI

    return OpenAI(api_key=api_key)


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("모델 응답에서 JSON을 찾지 못했습니다")
    return json.loads(m.group(0))


def _mock_result() -> dict:
    return {
        "type": "other",
        "confidence": 0.3,
        "severity": "low",
        "title": "[데모] 분석 결과 예시",
        "description": ".env.local 에 OPENAI_API_KEY가 설정되지 않아 데모 응답을 반환했습니다.",
        "evidence": [],
        "privacy_flags": [],
    }


def analyze_image(image_bytes: bytes, media_type: str) -> dict:
    client = _client()
    if client is None:
        return _mock_result()

    data_url = f"data:{media_type};base64,{base64.b64encode(image_bytes).decode()}"
    resp = client.chat.completions.create(
        model=_model(),
        # gpt-5 계열은 추론 토큰도 이 한도에 포함되므로 넉넉히 둔다
        max_completion_tokens=4000,
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
    )
    result = _extract_json(resp.choices[0].message.content or "")
    if result.get("type") not in REPORT_TYPES:
        result["type"] = "other"
    return result


def write_complaint(result: dict, location: str, extra: str) -> str:
    """분석 결과로 민원 본문 작성. API 키가 없으면 템플릿으로 대체."""
    label = REPORT_TYPES.get(result.get("type"), "기타")
    fallback = (
        f"[{label}] {result.get('title', '')}\n\n"
        f"■ 발생 위치: {location}\n"
        f"■ 내용: {result.get('description', '')}\n"
        + (f"■ 추가 설명: {extra}\n" if extra else "")
        + "\n위 사항에 대해 확인 및 조치를 요청드립니다."
    )
    client = _client()
    if client is None:
        return fallback

    prompt = (
        "아래 정보로 공공기관에 제출할 정중한 민원 문서를 한국어로 작성하세요. "
        "제목, 발생 위치, 민원 내용, 요청 사항 순서로 쓰고, 주어진 정보에 없는 사실은 지어내지 마세요. "
        "마크다운 기호 없이 일반 텍스트로만 쓰세요.\n\n"
        f"AI 분석 결과: {json.dumps(result, ensure_ascii=False)}\n"
        f"발생 위치: {location}\n추가 설명: {extra or '없음'}"
    )
    resp = client.chat.completions.create(
        model=_model(),
        max_completion_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    return (resp.choices[0].message.content or "").strip() or fallback
