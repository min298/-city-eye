import json
import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env.local")  # OPENAI_API_KEY (서버 전용)
load_dotenv(_ROOT / ".env")

from . import agencies, analyzer, db, geo  # noqa: E402
from .analyzer import REPORT_TYPES, analyze_image, write_complaint  # noqa: E402
from .submitter import get_submitter  # noqa: E402

BASE = Path(__file__).resolve().parent
UPLOADS = (Path("/tmp") if os.getenv("VERCEL") else BASE.parent) / "uploads"
UPLOADS.mkdir(exist_ok=True)
ALLOWED = {"image/jpeg", "image/png", "image/webp"}
# Vercel 함수 요청 본문 한도(4.5MB)에 맞춤
MAX_BYTES = 4 * 1024 * 1024

app = FastAPI(title="city-eye")
db.init_db()


@app.post("/api/analyze")
async def analyze(
    image: UploadFile = File(...),
    lat: float | None = Form(None),
    lng: float | None = Form(None),
):
    if image.content_type not in ALLOWED:
        raise HTTPException(400, "jpeg/png/webp 이미지만 가능합니다")
    data = await image.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "이미지는 4MB 이하여야 합니다")

    # 위치: EXIF 우선, 없으면 브라우저 위치
    gps = geo.extract_exif_gps(data) or ((lat, lng) if lat is not None and lng is not None else None)
    place = geo.reverse_geocode(*gps) if gps else {"address": "", "city": "", "district": ""}

    try:
        analysis = analyze_image(data, image.content_type)
    except Exception as e:
        raise HTTPException(502, f"이미지 분석 실패: {e}")

    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[image.content_type]
    path = UPLOADS / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(data)

    rid = db.create_report(
        image_path=str(path),
        lat=gps[0] if gps else None,
        lng=gps[1] if gps else None,
        address=place["address"],
        agency=geo.route_agency(analysis["type"], place),
        analysis=analysis,
        title=analysis.get("title", ""),
        description=analysis.get("description", ""),
    )
    report = db.get_report(rid)
    report["needs_review"] = (
        float(analysis.get("confidence", 0)) < float(os.getenv("MIN_CONFIDENCE", "0.6"))
        or analysis["type"] == "not_reportable"
    )
    report["type_label"] = REPORT_TYPES[analysis["type"]]
    return report


@app.post("/analyze")
async def analyze_simple(file: UploadFile = File(...)):
    """웹페이지(index.html)용: 사진 → 분석 결과 JSON."""
    if file.content_type not in ALLOWED:
        raise HTTPException(400, "jpeg/png/webp 이미지만 가능합니다")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "이미지는 4MB 이하여야 합니다")
    started = time.perf_counter()
    try:
        analysis = analyze_image(data, file.content_type)
    except Exception as e:
        raise HTTPException(502, f"이미지 분석 실패: {e}")
    analysis["type_label"] = REPORT_TYPES[analysis["type"]]
    # 화면에서 "실제 AI 호출 결과인지" 확인할 수 있도록 메타 정보 제공
    analysis["meta"] = {
        "live": analyzer.is_live(),
        "model": analyzer.model_name() if analyzer.is_live() else "demo",
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
    }
    return analysis


@app.post("/locate")
async def locate(
    file: UploadFile | None = File(None),
    lat: float | None = Form(None),
    lng: float | None = Form(None),
):
    """사진 EXIF GPS → (없으면) 브라우저 위치 → 주소 변환."""
    source, coords = None, None
    if file is not None:
        if file.content_type not in ALLOWED:
            raise HTTPException(400, "jpeg/png/webp 이미지만 가능합니다")
        data = await file.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "이미지는 4MB 이하여야 합니다")
        coords = geo.extract_exif_gps(data)
        if coords:
            source = "exif"
    if coords is None and lat is not None and lng is not None:
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise HTTPException(400, "좌표 범위가 올바르지 않습니다")
        coords, source = (lat, lng), "browser"
    if coords is None:
        raise HTTPException(404, "사진에 위치 정보(EXIF)가 없고 기기 위치도 받지 못했습니다")

    place = geo.reverse_geocode(*coords)
    if not place["address"]:
        raise HTTPException(502, "좌표를 주소로 변환하지 못했습니다. 직접 입력해 주세요")
    return {"address": place["address"], "source": source,
            "lat": coords[0], "lng": coords[1]}


@app.post("/complaint")
async def complaint(
    result: str = Form(...),
    location: str = Form(""),
    extra: str = Form(""),
):
    """웹페이지(index.html)용: 분석 결과 + 위치 + 설명 → 민원문."""
    try:
        parsed = json.loads(result)
        if not isinstance(parsed, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(400, "result는 JSON 객체여야 합니다")
    try:
        text = write_complaint(parsed, location, extra)
    except Exception as e:
        raise HTTPException(502, f"민원 작성 실패: {e}")
    return {"complaint": text}


@app.post("/submit")
async def submit_one_click(
    file: UploadFile = File(...),
    result: str = Form(...),
    location: str = Form(...),
    complaint: str = Form(...),
    channel: str = Form(""),
):
    """웹페이지(index.html)용: 제출 버튼 한 번으로 접수. 사용자가 화면에서 확인한 내용만 받는다."""
    if file.content_type not in ALLOWED:
        raise HTTPException(400, "jpeg/png/webp 이미지만 가능합니다")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "이미지는 4MB 이하여야 합니다")
    if not location.strip() or not complaint.strip() or len(complaint) > 5000:
        raise HTTPException(400, "위치와 민원 내용을 확인해 주세요")
    try:
        parsed = json.loads(result)
        if not isinstance(parsed, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(400, "result는 JSON 객체여야 합니다")
    if parsed.get("type") == "not_reportable":
        raise HTTPException(400, "신고 대상이 아닌 사진은 제출할 수 없습니다")
    if channel and channel not in agencies.CHANNELS:
        raise HTTPException(400, "알 수 없는 접수처입니다")

    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[file.content_type]
    path = UPLOADS / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(data)

    report = {"title": parsed.get("title", ""), "description": complaint,
              "address": location, "analysis": parsed, "image_path": str(path)}
    submitter = get_submitter()
    try:
        receipt = submitter.submit(report)
    except Exception as e:
        raise HTTPException(502, f"제출 실패: {e}")

    channel_name = agencies.CHANNELS[channel]["name"] if channel else ""
    rid = db.create_report(
        image_path=str(path), address=location,
        agency=channel_name, analysis=parsed,
        title=report["title"], description=complaint,
        status="submitted", receipt_no=receipt,
    )
    return {"id": rid, "receipt_no": receipt, "channel": channel_name,
            "simulated": not submitter.is_real, "delivery": submitter.label,
            "to": submitter.to_masked}


@app.post("/route")
async def route(result: str = Form(...), location: str = Form("")):
    """웹페이지(index.html)용: 분석 결과 + 위치 → 신고 접수처 추천."""
    try:
        parsed = json.loads(result)
        if not isinstance(parsed, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(400, "result는 JSON 객체여야 합니다")
    return agencies.recommend(parsed, location)


class SubmitBody(BaseModel):
    title: str
    description: str
    address: str = ""


@app.post("/api/reports/{rid}/submit")
def submit(rid: int, body: SubmitBody):
    """사용자가 내용을 확인·수정한 뒤에만 제출한다 (human-in-the-loop)."""
    report = db.get_report(rid)
    if not report:
        raise HTTPException(404, "신고를 찾을 수 없습니다")
    if report["status"] == "submitted":
        raise HTTPException(409, "이미 제출된 신고입니다")
    if report["analysis"].get("type") == "not_reportable":
        raise HTTPException(400, "신고 대상이 아닌 사진입니다")

    report.update(title=body.title, description=body.description, address=body.address)
    receipt = get_submitter().submit(report)
    db.update_report(rid, title=body.title, description=body.description,
                     address=body.address, status="submitted", receipt_no=receipt)
    return db.get_report(rid)


@app.get("/api/reports")
def reports():
    return db.list_reports()


app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.get("/demo")
def demo():
    return FileResponse(BASE / "static" / "demo.html")


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")
