"""Uy vazifa fayllarini yuklash — xavfsizlik tekshiruvlari bilan.

Tekshiruvlar:
  1. Kengaytma oq ro'yxatda bo'lishi shart;
  2. Hajm chegarasi (o'qish paytida, xotirani to'ldirmasdan);
  3. Fayl boshidagi "magic" baytlar kengaytmaga mos kelishi shart
     (mijoz yuborgan Content-Type ga ishonilmaydi);
  4. Rasmlar Pillow bilan ochib ko'riladi (buzuq/soxta fayl o'tmaydi);
  5. Fayl nomi mijozdan olinmaydi — tasodifiy nom beriladi
     (path traversal va nom orqali kod ishga tushirish yo'q).
"""
import re
import uuid
from pathlib import Path
from typing import Tuple

from fastapi import HTTPException, UploadFile

MEDIA_ROOT = Path(__file__).resolve().parents[2] / "media" / "homework"
MAX_BYTES = 10 * 1024 * 1024        # 10 MB
CHUNK = 64 * 1024

# kengaytma -> (mumkin bo'lgan boshlanish baytlari, MIME)
ALLOWED = {
    ".jpg":  ((b"\xff\xd8\xff",), "image/jpeg"),
    ".jpeg": ((b"\xff\xd8\xff",), "image/jpeg"),
    ".png":  ((b"\x89PNG\r\n\x1a\n",), "image/png"),
    ".webp": ((b"RIFF",), "image/webp"),
    ".gif":  ((b"GIF87a", b"GIF89a"), "image/gif"),
    ".pdf":  ((b"%PDF-",), "application/pdf"),
}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# saqlangan fayl nomi shakli — tashqaridan kelgan nomni shu bilan tekshiramiz
SAFE_NAME = re.compile(r"^[0-9a-f]{32}\.(jpg|jpeg|png|webp|gif|pdf)$")
# URL da nuqta ishlatilmaydi: nginx ning ".png$" static regex qoidasi
# /api/ proxysidan ustun turadi va so'rovni backendga yubormay qo'yadi.
SAFE_SLUG = re.compile(r"^([0-9a-f]{32})-(jpg|jpeg|png|webp|gif|pdf)$")


def _ext_of(filename: str) -> str:
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in (filename or "") else ""
    if ext not in ALLOWED:
        raise HTTPException(400, "Faqat rasm (jpg, png, webp, gif) yoki PDF yuklash mumkin")
    return ext


async def save_upload(file: UploadFile) -> Tuple[str, str, int]:
    """Faylni tekshirib saqlaydi. -> (saqlangan_nom, asl_nom, hajm)"""
    ext = _ext_of(file.filename or "")

    data = bytearray()
    while True:
        chunk = await file.read(CHUNK)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise HTTPException(400, "Fayl hajmi 10 MB dan oshmasligi kerak")
    if not data:
        raise HTTPException(400, "Fayl bo'sh")

    magics, _mime = ALLOWED[ext]
    if not any(bytes(data).startswith(m) for m in magics):
        # kengaytma bilan ichki tarkib mos emas — masalan .png deb nomlangan skript
        raise HTTPException(400, "Fayl turi kengaytmasiga mos emas")

    if ext in IMAGE_EXTS:
        try:
            import io
            from PIL import Image
            Image.open(io.BytesIO(bytes(data))).verify()
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(400, "Rasm fayli buzuq yoki o'qib bo'lmadi")

    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    stored = uuid.uuid4().hex + ext
    (MEDIA_ROOT / stored).write_bytes(bytes(data))
    return stored, (file.filename or stored)[:300], len(data)


def to_slug(stored: str) -> str:
    """'abc.png' -> 'abc-png' (URL uchun)."""
    base, ext = stored.rsplit(".", 1)
    return f"{base}-{ext}"


def resolve_stored(slug: str) -> Tuple[Path, str]:
    """URL slug bo'yicha faylni xavfsiz ochish. -> (yo'l, MIME)"""
    m = SAFE_SLUG.match(slug or "")
    if not m:
        raise HTTPException(404, "Fayl topilmadi")
    name = f"{m.group(1)}.{m.group(2)}"
    path = (MEDIA_ROOT / name).resolve()
    # papkadan chiqib ketmaganiga ishonch hosil qilamiz
    if MEDIA_ROOT.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404, "Fayl topilmadi")
    return path, ALLOWED["." + m.group(2)][1]
