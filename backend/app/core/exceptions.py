"""Custom exception definitions."""
from fastapi import HTTPException, status


class AppException(HTTPException):
    """Base application exception."""
    def __init__(self, code: int, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


class NotFoundException(AppException):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(code=10002, message=message, status_code=404)


class AlreadyExistsException(AppException):
    def __init__(self, message: str = "资源已存在"):
        super().__init__(code=10003, message=message, status_code=409)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "未认证"):
        super().__init__(code=20001, message=message, status_code=401)


class ForbiddenException(AppException):
    def __init__(self, message: str = "权限不足"):
        super().__init__(code=20002, message=message, status_code=403)


class TokenExpiredException(AppException):
    def __init__(self, message: str = "Token已过期"):
        super().__init__(code=20003, message=message, status_code=401)


class NL2SQLGenerationError(AppException):
    def __init__(self, message: str = "SQL生成失败"):
        super().__init__(code=30001, message=message, status_code=500)


class SQLExecutionError(AppException):
    def __init__(self, message: str = "SQL执行失败"):
        super().__init__(code=30002, message=message, status_code=500)


class SQLTimeoutError(AppException):
    def __init__(self, message: str = "SQL执行超时"):
        super().__init__(code=30003, message=message, status_code=504)


class SQLSecurityError(AppException):
    def __init__(self, message: str = "SQL安全拦截"):
        super().__init__(code=30004, message=message, status_code=403)


class LLMServiceError(AppException):
    def __init__(self, message: str = "LLM服务不可用"):
        super().__init__(code=30005, message=message, status_code=503)


class DatasourceConnectionError(AppException):
    def __init__(self, message: str = "数据源连接失败"):
        super().__init__(code=40001, message=message, status_code=500)


class ValidationException(AppException):
    def __init__(self, message: str = "参数校验失败"):
        super().__init__(code=10001, message=message, status_code=422)
