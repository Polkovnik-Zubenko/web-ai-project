from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ModelUnavailableError(RuntimeError):
    pass


class PromptRejectedError(ValueError):
    pass


def register_error_handlers(app: FastAPI) -> None:
    # Обработка ошибок
    @app.exception_handler(PromptRejectedError)
    async def prompt_rejected_handler(_: Request, exc: PromptRejectedError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc), "error_code": "prompt_rejected"},
        )

    @app.exception_handler(ModelUnavailableError)
    async def model_unavailable_handler(_: Request, exc: ModelUnavailableError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": str(exc), "error_code": "model_unavailable"},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors(), "error_code": "validation_error"},
        )
