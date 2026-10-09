from typing import Any, Optional
from fastapi.responses import JSONResponse

def success_response(data: Any, message: str = "Request completed successfully", code: int = 200):
    return {
        "status": "success",
        "code": code,
        "data": data,
        "message": message
    }

def error_response(error_type: str, message: str, code: int = 400, details: Optional[list] = None):
    return JSONResponse(
        status_code=code,
        content={
            "status": "error",
            "code": code,
            "error": {
                "type": error_type,
                "message": message,
                "details": details or []
            }
        }
    )