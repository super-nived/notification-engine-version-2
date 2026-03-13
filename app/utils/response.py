from typing import Any


def success(
    data: Any = None,
    message: str = "Success",
    status_code: int = 200,
):
    return {
        "status": "success",
        "message": message,
        "data": data,
        "status_code": status_code,
    }


def error(
    message: str = "Error",
    status_code: int = 400,
    data: Any = None,
):
    return {
        "status": "error",
        "message": message,
        "data": data,
        "status_code": status_code,
    }
