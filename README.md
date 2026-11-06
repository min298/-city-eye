# City Eye 👁 — 생활 불편 자동 탐지 AI

> 사진 한 장으로 도시의 불편(불법 주정차·포트홀·쓰레기 투기·시설물 파손)을 AI가 분석하고,
> 민원문 작성과 알맞은 공공 신고 접수처 추천까지 이어주는 웹 서비스

- **배포 주소**: https://city-eye-wine.vercel.app
- **발표자료**: [`docs/CityEye_발표자료.pdf`](docs/CityEye_발표자료.pdf)
- **프롬프트 기록**: [`docs/PROMPTS.md`](docs/PROMPTS.md)

## 주요 기능

| 단계 | 기능 | 구현 |
|---|---|---|
| 1 | 사진 업로드 + 위치 입력 | 사진의 GPS(EXIF) → 없으면 기기 위치 → 주소 변환으로 **위치 자동 입력** (`/locate`) |
| 2 | **AI 사진 분석** | OpenAI 비전 모델이 유형·위험도·신뢰도·판단 근거·개인정보 포함 여부를 JSON으로 반환 (`/analyze`) |
| 3 | **민원문 자동 작성** | 분석 결과 + 위치로 공공기관 제출용 민원문 생성, 사실만 기반 (`/complaint`) |
| 4 | **접수처 AI 추천** | 검증된 공식 사이트 목록(안전신문고·국민신문고·서울시 응답소) 중에서만 선택 (`/route`) |
| 5 | 제출 | 사용자 최종 확인 후 접수번호 발급 (`/submit`) — **현재 모의 접수**, 아래 한계 참고 |

화면의 AI 분석 결과 맨 위에 `✅ 실제 AI 호출: OpenAI <모델> · <소요 시간>`이 표시되어
실제 모델 호출 여부를 바로 확인할 수 있습니다. (서버에 키가 없으면 `⚠ 데모 응답`으로 표시)

## 구조

```
브라우저 (app/static/index.html)
   │  사진·위치·민원문
   ▼
FastAPI (app/main.py)  ── Vercel Serverless
   ├─ analyzer.py   OpenAI 비전 분석 / 민원문 작성   (키는 서버에서만 사용)
   ├─ geo.py        EXIF GPS 추출, 좌표→주소 변환(OpenStreetMap Nominatim)
   ├─ agencies.py   공식 접수처 목록 + AI 추천 (목록 밖 값은 무시 → URL 환각 방지)
   ├─ submitter.py  제출 어댑터 (MockSubmitter → 실제 채널로 교체 가능)
   └─ db.py         SQLite 저장
```

- **키 보호**: `OPENAI_API_KEY`는 서버 환경변수/`.env.local`에서만 읽고 브라우저로 전달하지 않습니다. 저장소에는 키가 없습니다.
- **안전 장치**: 신고 대상이 아닌 사진·허위 접수처·빈 입력은 서버가 거부하고, 제출 전 사용자 확인(허위 신고 책임 안내)을 받습니다.

## 기술 스택
Python · FastAPI · OpenAI API(비전) · SQLite · Vanilla JS · Vercel

## 교내 GPU(틸론) 활용
교내 GPU 환경의 JupyterLab에서 오픈 모델 **SDXL-Turbo**로 City Eye의 **브랜드 로고를 직접 생성**했습니다.
프롬프트를 바꿔 가며 결과를 비교한 뒤 도시와 눈(Eye)이 결합된 이미지를 선택해 웹서비스 헤더 로고와
발표자료 대표 이미지로 사용했습니다. (증거: [`웹페이지/SDXL 이미지 생성.png`](웹페이지/SDXL%20이미지%20생성.png))
서비스의 핵심 AI 기능(사진 분석·민원문 작성·접수처 추천)은 외부 OpenAI API를 사용합니다.

## 실행 방법
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# .env.local 에 OPENAI_API_KEY=sk-... 입력 (없으면 데모 응답으로 동작)
uvicorn app.main:app --reload     # http://127.0.0.1:8000
```

## API
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/analyze` | 사진 → 유형·위험도·신뢰도·근거 (+ 호출 메타) |
| POST | `/locate` | 사진 EXIF/기기 좌표 → 주소 |
| POST | `/complaint` | 분석 결과 → 민원문 |
| POST | `/route` | 분석 결과 + 위치 → 추천 접수처 |
| POST | `/submit` | 확인된 민원 제출 → 접수번호 |
| GET | `/api/reports` | 저장된 신고 내역 |

## 현재 구현 범위와 한계 (솔직한 공개)
- **제출은 모의 접수입니다.** 안전신문고·국민신문고는 본인인증이 필요하고 일반 공개 제출 API가 없어,
  고객 대신 자동 로그인·제출은 하지 않았습니다(약관·인증 우회 방지). 접수번호는 `MOCK-`로 시작하며
  화면에도 "실제 기관으로 전송되지 않은 모의 접수"라고 표시합니다. 어댑터 구조(`submitter.py`)라서
  공식 API·제휴·민원 메일 채널이 확보되면 교체만 하면 됩니다.
- **데이터 영구 저장·처리 상태 추적은 미구현입니다.** 배포 환경(Vercel)의 SQLite는 임시 저장소(`/tmp`)라
  재시작 시 사라집니다. 영구 DB(예: Supabase)로 교체와 처리 상태 추적이 다음 단계입니다.
- 위치 자동 입력은 사진에 GPS가 없으면 **현재 기기 위치**를 사용하므로 촬영 장소와 다를 수 있습니다(화면에 안내).
  좌표→주소 변환은 무료 OpenStreetMap이라 상세 번지가 부정확할 수 있습니다.
- 얼굴·번호판 자동 블러는 미구현이며, 포함 가능성만 경고합니다.

## 로드맵
1. 영구 DB + 신고 처리 상태 추적(접수→처리중→완료)
2. 공식 API·제휴 또는 민원 메일 연동으로 실제 접수
3. 얼굴·번호판 자동 블러, 신고 횟수 제한·사용자 인증
