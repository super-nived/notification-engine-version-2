from typing import Any

from fastapi.responses import JSONResponse


def success(
    data: Any = None,
    message: str = "Success",
    status_code: int = 200,
) -> JSONResponse:
    return JSONResponse(
        content={
            "status": "success",
            "message": message,
            "data": data,
        },
        status_code=status_code,
    )


def error(
    message: str = "Error",
    status_code: int = 400,
    data: Any = None,
) -> JSONResponse:
    return JSONResponse(
        content={
            "status": "error",
            "message": message,
            "data": data,
        },
        status_code=status_code,
    )
