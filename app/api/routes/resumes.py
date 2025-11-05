# backend/app/api/routes/resumes.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from typing import Dict, Any
import traceback
import logging

# import parser and constants
from app.services.resume_parser import ImprovedResumeParser, MAX_PDF_BYTES

router = APIRouter(prefix="/resumes", tags=["resumes"])

# module logger
logger = logging.getLogger("app.api.routes.resumes")

# instantiate parser once
parser = ImprovedResumeParser()

@router.post("/upload")
async def upload_resume(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Accept a PDF or text resume upload, parse it and return extracted JSON.
    - small size guard to avoid extremely large uploads in dev
    - logs full traceback to server logs for debugging
    """
    try:
        content = await file.read()

        # Basic guards
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        # Use MAX_PDF_BYTES from parser module
        if MAX_PDF_BYTES and len(content) > MAX_PDF_BYTES:
            raise HTTPException(status_code=413, detail=f"Uploaded file too large (limit {MAX_PDF_BYTES} bytes)")

        # call parser (it accepts pdf_bytes or text)
        result = parser.parse_resume(pdf_bytes=content)

        if not isinstance(result, dict):
            # unexpected return type from parser
            raise HTTPException(status_code=500, detail="Parser returned unexpected result type")

        if "error" in result:
            # parser signalled an error; return 422 to the client
            raise HTTPException(status_code=422, detail=result["error"])

        return JSONResponse(result)

    except HTTPException:
        # re-raise known FastAPI HTTP exceptions
        raise
    except Exception as e:
        # log the full traceback so you can inspect server console
        tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        logger.exception("Resume upload failed: %s", e)
        # In dev include traceback in response to speed up debugging.
        # Remove the traceback in production for security.
        raise HTTPException(status_code=500, detail=f"Parsing error: {str(e)}\n\nTraceback:\n{tb}")


@router.get("/health")
async def health():
    return {"ok": True}
