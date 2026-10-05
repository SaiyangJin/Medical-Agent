"""脚本公用工具：UTF-8 输出、统一 UA、带重试的 HTTP 请求。

放在 scripts/ 下用 `import _common` 直接引用——Python 会把"被执行脚本所在目录"
自动放进 sys.path[0]，所以不需要装成包。
"""

from __future__ import annotations

import sys
import time

import httpx

USER_AGENT = "LangChain-Medical-Agent/0.1 (educational; contact: student)"

# 命中这些状态码说明"再试一次可能就好了"；其余 4xx 是确定性错误，重试没意义。
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def setup_stdout() -> None:
    """Windows 控制台默认是 GBK，直接 print 中文/emoji 会抛 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, OSError):
            pass


def make_client(timeout: float = 120.0) -> httpx.Client:
    return httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT})


def _retry_after(resp: httpx.Response) -> float | None:
    """读 Retry-After 头（单位：秒）。

    服务端明说了要等多久，就别自己瞎猜——盲目指数退避（1s/2s/4s）在限流面前
    根本不够，只会让服务端觉得你在硬闯，把封禁时间拉得更长。
    """
    raw = resp.headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None  # 也可能是 HTTP-date 格式，本项目用不上


def fetch(
    client: httpx.Client,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    retries: int = 5,
) -> httpx.Response:
    """GET + 智能退避重试。网络层异常与 5xx/429 重试，其余 4xx 立刻抛。

    两种失败模式要区别对待：
      - 连接被重置（WinError 10054）：偶发，指数退避就够
      - 429 限流：服务端会给出 Retry-After，必须老实等够时间
    """
    last: Exception | None = None
    for attempt in range(retries):
        try:
            resp = client.get(url, params=params, headers=headers)
            if resp.status_code in RETRYABLE_STATUS:
                raise httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}", request=resp.request, response=resp
                )
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in RETRYABLE_STATUS:
                raise  # 404 / 403 之类，重试也白搭
            last = exc
            reason = f"HTTP {exc.response.status_code}"
            wait = _retry_after(exc.response) or 2**attempt
        except Exception as exc:  # 连接重置、超时等
            last = exc
            reason = type(exc).__name__
            wait = 2**attempt

        if attempt < retries - 1:
            print(f"    {reason}，等 {wait:.0f}s 后重试（{attempt + 1}/{retries - 1}）")
            time.sleep(wait)

    raise RuntimeError(f"连续 {retries} 次失败: {url}") from last
