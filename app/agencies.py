"""검증된 공식 신고 채널 목록 + AI 추천.

AI는 이 목록 안에서만 고른다(URL을 지어내지 않도록). 새 채널은 CHANNELS에 추가하면 된다.
"""
import json
import re

from . import analyzer

ALL_TYPES = ["illegal_parking", "pothole", "illegal_dumping", "damaged_facility", "other"]

CHANNELS = {
    "safetyreport": {
        "name": "안전신문고",
        "url": "https://www.safetyreport.go.kr",
        "desc": "불법 주정차, 도로 파손, 쓰레기 투기, 시설물 파손 등 생활 속 안전·불편 신고 (전국, 행정안전부)",
        "types": ALL_TYPES,
        "regions": None,
        "steps": ["로그인(본인인증)", "신고 유형 선택 후 사진 첨부", "복사한 민원 내용 붙여넣기", "위치 확인 후 제출"],
    },
    "epeople": {
        "name": "국민신문고",
        "url": "https://www.epeople.go.kr",
        "desc": "모든 행정기관 대상 종합 민원 창구 (전국, 국민권익위원회)",
        "types": ALL_TYPES,
        "regions": None,
        "steps": ["로그인(본인인증)", "민원 신청 선택", "복사한 민원 내용 붙여넣기", "관련 기관 선택 후 제출"],
    },
    "seoul_eungdapso": {
        "name": "서울시 응답소",
        "url": "https://eungdapso.seoul.go.kr",
        "desc": "서울시 및 자치구 관할 민원 접수 (서울 지역 한정)",
        "types": ALL_TYPES,
        "regions": ["서울"],
        "steps": ["서울시 응답소 접속", "민원 신청 선택", "복사한 민원 내용 붙여넣기", "제출"],
    },
}


def eligible_channels(report_type: str, location: str) -> list[str]:
    ids = []
    for cid, c in CHANNELS.items():
        if report_type not in c["types"]:
            continue
        if c["regions"] and not any(r in location for r in c["regions"]):
            continue
        ids.append(cid)
    # 지역 전용 채널을 앞으로, 그다음 안전신문고, 국민신문고 순
    order = {"seoul_eungdapso": 0, "safetyreport": 1, "epeople": 2}
    return sorted(ids, key=lambda i: order.get(i, 9))


def _view(cid: str, primary: bool) -> dict:
    c = CHANNELS[cid]
    return {"id": cid, "name": c["name"], "url": c["url"], "desc": c["desc"],
            "steps": c["steps"], "primary": primary}


def recommend(result: dict, location: str) -> dict:
    rtype = result.get("type", "other")
    if rtype == "not_reportable":
        return {"channels": [], "reason": "신고 대상이 아닌 사진이라 접수처를 추천하지 않습니다."}

    cands = eligible_channels(rtype, location)
    if not cands:
        return {"channels": [], "reason": "추천 가능한 접수처가 없습니다."}

    primary, reason = cands[0], "문제 유형과 위치에 맞는 공식 접수처입니다."

    client = analyzer._client()
    if client is not None and len(cands) > 1:
        try:
            prompt = (
                "시민 민원을 접수할 가장 적합한 공식 채널을 후보 중에서 하나 고르세요. "
                "후보 밖의 값은 금지합니다. JSON으로만 답하세요: "
                '{"primary": "<후보 id>", "reason": "한 문장 한국어 이유"}\n\n'
                f"신고 유형: {analyzer.REPORT_TYPES.get(rtype, rtype)}\n"
                f"요약: {result.get('title', '')}\n위치: {location}\n"
                "후보:\n" + "\n".join(f"- {i}: {CHANNELS[i]['name']} / {CHANNELS[i]['desc']}" for i in cands)
            )
            resp = client.chat.completions.create(
                model=analyzer._model(),
                max_completion_tokens=2000,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
            )
            m = re.search(r"\{.*\}", resp.choices[0].message.content or "", re.S)
            data = json.loads(m.group(0)) if m else {}
            if data.get("primary") in cands:  # 목록에 있는 id만 허용
                primary = data["primary"]
                reason = str(data.get("reason") or reason)[:200]
        except Exception:
            pass  # 실패하면 규칙 기반 결과 사용

    ordered = [primary] + [c for c in cands if c != primary]
    return {"channels": [_view(c, c == primary) for c in ordered], "reason": reason}
