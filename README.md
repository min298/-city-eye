# City Eye

사진 → AI 분석(신고 유형/본문 생성) → 위치·관할 라우팅 → **사용자 확인** → 제출(현재 mock).

## 실행
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# .env.local 에 OPENAI_API_KEY=sk-... 입력 (없으면 데모 응답). 모델: gpt-5-mini
uvicorn app.main:app --reload
```
http://127.0.0.1:8000 접속 (모바일 카메라/위치는 HTTPS 또는 localhost 필요)

## 구조
- `app/analyzer.py` 비전 LLM 분석 → 구조화 JSON
- `app/geo.py` EXIF GPS, 역지오코딩, 관할 라우팅
- `app/submitter.py` 제출 어댑터 (MockSubmitter → Api/Email/Playwright로 교체)
- `app/main.py` FastAPI, `app/static/index.html` 프론트

## TODO
- 얼굴·번호판 자동 블러
- 실제 제출 채널 연동 (공식 API/제휴 우선, 약관·본인인증 확인)
- 사용자 인증, 신고 횟수 제한, 처리 상태 추적
