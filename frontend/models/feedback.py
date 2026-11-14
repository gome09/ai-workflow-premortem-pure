# frontend/models/feedback.py
"""前端统一的 API 错误契约与一次性反馈。

传输层（``models/api_client.py``）只抛 :class:`ApiError`，不直接渲染提示；
控制器在用户动作边界调用 :func:`show_api_error` 提示一次；需要跨
``st.rerun()`` 保留的反馈通过 :func:`set_flash` / :func:`render_flash` 传递。
"""

from __future__ import annotations

import streamlit as st

_FLASH_KEY = "_flash"


class ApiError(Exception):
    """后端调用失败的显式契约。

    kind:
        timeout | connection | auth_transient | http | invalid_response | unknown
    """

    def __init__(
        self,
        kind: str = "unknown",
        *,
        status_code: int = 0,
        detail: object = None,
        error_code: str = "",
        retryable: bool | None = None,
        recovery_endpoint: str = "",
    ) -> None:
        self.kind = kind
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code
        self.retryable = retryable
        self.recovery_endpoint = recovery_endpoint
        super().__init__(f"{kind}:{status_code}" if status_code else kind)


def _detail_text(detail: object) -> str:
    """从后端 detail 中提取可直接展示的短文本（不读取 provider 原文）。"""
    if isinstance(detail, str):
        return detail.strip()
    if isinstance(detail, dict):
        for key in ("error_message", "message", "detail"):
            value = detail.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _describe_http_error(exc: ApiError) -> str:
    status = exc.status_code
    detail_dict = exc.detail if isinstance(exc.detail, dict) else {}
    detail_text = _detail_text(exc.detail)

    if status == 401:
        return "登录已失效，请重新登录。"
    if status == 403:
        return detail_text or "当前账号无权执行该操作。"
    if status == 404:
        return "目标资源不存在或已被删除。"
    if status == 409:
        result_status = str(detail_dict.get("result_status") or "")
        if result_status in {"stale", "conflict", "not_pending"}:
            message = "数据已被其他操作更新，请刷新后重试。"
        else:
            message = detail_text or "当前状态与请求冲突，请刷新后重试。"
        if exc.recovery_endpoint:
            message = f"{message}可使用恢复入口。"
        return message
    if status == 422:
        if isinstance(exc.detail, list):
            parts: list[str] = []
            for item in exc.detail[:3]:
                if not isinstance(item, dict):
                    continue
                loc = ".".join(str(part) for part in item.get("loc") or [] if str(part) != "body")
                msg = str(item.get("msg") or "").strip()
                if loc and msg:
                    parts.append(f"{loc}: {msg}")
                elif msg:
                    parts.append(msg)
            if parts:
                return "提交内容未通过校验：" + "；".join(parts) + "。"
        return detail_text or "提交内容未通过校验，请检查后重试。"
    if status == 502:
        code = exc.error_code or "provider_error"
        if exc.retryable is True:
            tail = "可重试。"
        elif exc.retryable is False:
            tail = "不可重试，请联系管理员。"
        else:
            tail = "请稍后重试。"
        return f"模型服务暂时不可用（{code}），{tail}"
    if status >= 500:
        return f"服务暂时不可用（HTTP {status}），请稍后重试。"
    return detail_text or f"请求失败（HTTP {status}）。"


def describe_api_error(exc: object) -> str:
    """生成一次可行动的中文提示；非 ApiError 返回空串交由调用方兜底。"""
    if not isinstance(exc, ApiError):
        return ""
    if exc.kind == "timeout":
        return "请求超时；结果可能未确定，请先刷新核对，不要自动重复提交。"
    if exc.kind == "connection":
        return "无法连接后端服务，请确认 API 已启动。"
    if exc.kind == "auth_transient":
        return "登录状态校验暂时不可用，请稍后重试。"
    if exc.kind == "invalid_response":
        suffix = f"（HTTP {exc.status_code}）" if exc.status_code else ""
        return f"服务端返回了无法识别的响应{suffix}，请稍后重试。"
    if exc.kind == "http":
        return _describe_http_error(exc)
    return "发生未知错误，请稍后重试或联系管理员。"


def show_api_error(exc: object, *, fallback: str = "") -> None:
    """单点展示一次错误；同一失败不得在 client 与 view 重复提示。"""
    message = describe_api_error(exc) or fallback or "操作失败，请稍后重试。"
    st.error(message)


def set_flash(level: str, message: str) -> None:
    """写入一次性反馈，供必须 rerun 的路径（如聊天发送）跨 rerun 保留。"""
    st.session_state[_FLASH_KEY] = {"level": level, "message": message}


def clear_flash() -> None:
    st.session_state.pop(_FLASH_KEY, None)


def render_flash() -> None:
    """读取并清除一次性反馈。"""
    flash = st.session_state.pop(_FLASH_KEY, None)
    if not isinstance(flash, dict):
        return
    message = str(flash.get("message") or "")
    if not message:
        return
    level = flash.get("level")
    if level == "success":
        st.success(message)
    elif level == "warning":
        st.warning(message)
    elif level == "info":
        st.info(message)
    else:
        st.error(message)
