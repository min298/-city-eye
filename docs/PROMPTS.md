# 프롬프트 기록

서비스에서 실제로 사용하는 프롬프트입니다. (원본: `app/analyzer.py`, `app/agencies.py`)
모델: OpenAI `gpt-5.4-mini` (환경변수 `OPENAI_MODEL`로 변경 가능)

## 1. 사진 분석 (`analyzer.analyze_image`, 이미지 + 텍스트)
```
당신은 시민 신고 사진을 분석하는 도우미입니다.
사진을 보고 아래 JSON 형식으로만 답하세요.

{
  "type": "illegal_parking|pothole|illegal_dumping|damaged_facility|other|not_reportable 중 하나",
  "confidence": 0.0~1.0,
  "severity": "low|medium|high",
  "title": "신고 제목(40자 이내)",
  "description": "사진에서 객관적으로 보이는 사실만 서술한 신고 본문(2~4문장)",
  "evidence": ["판단 근거 목록"],
  "privacy_flags": ["얼굴", "차량번호판" 등 사진에 포함된 개인정보]
}

규칙: 보이지 않는 사실은 추측하지 말고, 신고 대상이 아니면 type을 not_reportable로 하세요.
```
- 설계 의도: 구조화 JSON 강제(`response_format=json_object`), 추측 금지로 환각 억제, 신고 대상 아님 분기.

## 2. 민원문 작성 (`analyzer.write_complaint`)
```
아래 정보로 공공기관에 제출할 정중한 민원 문서를 한국어로 작성하세요.
제목, 발생 위치, 민원 내용, 요청 사항 순서로 쓰고, 주어진 정보에 없는 사실은 지어내지 마세요.
마크다운 기호 없이 일반 텍스트로만 쓰세요.

AI 분석 결과: <분석 JSON>
발생 위치: <사용자 입력/자동 입력 주소>
추가 설명: <사용자 입력 또는 없음>
```

## 3. 접수처 추천 (`agencies.recommend`)
```
시민 민원을 접수할 가장 적합한 공식 채널을 후보 중에서 하나 고르세요.
후보 밖의 값은 금지합니다. JSON으로만 답하세요:
{"primary": "<후보 id>", "reason": "한 문장 한국어 이유"}

신고 유형: <유형>
요약: <제목>
위치: <주소>
후보:
- safetyreport: 안전신문고 / ...
- epeople: 국민신문고 / ...
- seoul_eungdapso: 서울시 응답소 / ... (서울 지역일 때만)
```
- 설계 의도: 후보 목록을 코드가 제한하고, 응답 id가 목록에 없으면 무시 → 존재하지 않는 URL 생성(환각) 방지.

## 4. 로고 이미지 생성 (교내 GPU, SDXL-Turbo)
- 모델: SDXL-Turbo, 교내 GPU 서버 JupyterLab (`results/sdxl/text2img_*.png`)
- 프롬프트: **(서버 노트북에서 확인해 기입 필요)**
