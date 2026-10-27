"""进程内滑动窗口限流(开发/单实例部署适用, 集群部署建议换 Redis 实现)。"""
import time
import threading
from collections import defaultdict, deque

from app.config import settings
from app.core.exceptions import AppException


class RateLimitExceededException(AppException):
    def __init__(self, message: str = "请求过于频繁，请稍后再试"):
        super().__init__(code=20004, message=message, status_code=429)


_lock = threading.Lock()
_windows: dict = defaultdict(deque)


def check_rate_limit(key: str, limit: int = None, window_sec: int = 60) -> None:
    """超过阈值时抛出 429 异常。"""
    limit = limit or settings.rate_limit_qpm
    now = time.time()
    with _lock:
        window = _windows[key]
        while window and window[0] < now - window_sec:
            window.popleft()
        if len(window) >= limit:
            raise RateLimitExceededException(f"请求过于频繁(上限{limit}次/分钟)，请稍后再试")
        window.append(now)


def reset_rate_limit(key: str) -> None:
    with _lock:
        _windows.pop(key, None)
