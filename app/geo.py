"""위치 처리: EXIF GPS 추출, 역지오코딩, 관할 기관 라우팅."""
import io

import httpx
from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS


def _to_deg(value, ref) -> float:
    d, m, s = (float(x) for x in value)
    deg = d + m / 60 + s / 3600
    return -deg if ref in ("S", "W") else deg


def extract_exif_gps(image_bytes: bytes) -> tuple[float, float] | None:
    try:
        exif = Image.open(io.BytesIO(image_bytes)).getexif()
        gps_ifd = exif.get_ifd(0x8825)
        if not gps_ifd:
            return None
        gps = {GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}
        lat = _to_deg(gps["GPSLatitude"], gps["GPSLatitudeRef"])
        lng = _to_deg(gps["GPSLongitude"], gps["GPSLongitudeRef"])
        return lat, lng
    except Exception:
        return None


def reverse_geocode(lat: float, lng: float) -> dict:
    """OpenStreetMap Nominatim 사용(데모용). 실서비스는 카카오/네이버 지도 API 권장."""
    try:
        r = httpx.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lng, "format": "jsonv2", "accept-language": "ko"},
            headers={"User-Agent": "city-eye-hackathon/0.1"},
            timeout=5,
        )
        data = r.json()
        a = data.get("address", {})
        return {
            "address": data.get("display_name", ""),
            "city": a.get("city") or a.get("province") or "",
            "district": a.get("borough") or a.get("city_district") or a.get("county") or "",
        }
    except Exception:
        return {"address": "", "city": "", "district": ""}


# 신고 유형 → 담당 분야 (실제 연동 시 기관별 접수 채널 매핑으로 확장)
AGENCY_BY_TYPE = {
    "illegal_parking": "교통행정과",
    "pothole": "도로관리과",
    "illegal_dumping": "청소행정과",
    "damaged_facility": "시설관리과",
    "other": "민원여권과",
}


def route_agency(report_type: str, place: dict) -> str:
    dept = AGENCY_BY_TYPE.get(report_type, "민원여권과")
    office = place.get("district") or place.get("city") or "관할 기관"
    return f"{office} {dept}"
