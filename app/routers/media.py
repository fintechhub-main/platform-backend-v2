import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/media", tags=["media"])

MEDIA_DIRS = [
    "/home/fintechadmin/platform/backend-test/src/media",
    "/home/ziyodev/platform-backend-v2/media",
]

@router.get("/{path:path}")
async def serve_media(path: str):
    for base in MEDIA_DIRS:
        full = os.path.normpath(os.path.join(base, path))
        # Prevent path traversal
        if not full.startswith(base):
            continue
        if os.path.isfile(full):
            return FileResponse(full)
    raise HTTPException(status_code=404, detail="Media file not found")
