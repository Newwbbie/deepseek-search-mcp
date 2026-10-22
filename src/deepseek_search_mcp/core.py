"""DeepSeek Search / Fetch 接口的最小封装（仅标准库）。"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API_BASE = "https://api.deepseek.com"
SEARCH_PATH = "/v1/tools/search"
FETCH_PATH = "/v1/tools/fetch"
DEFAULT_TIMEOUT = 30
MAX_QUERY_CHARS = 128
MAX_URL_CHARS = 8192
MAX_FETCH_CHARS = 60_000
MAX_RESULT_CONTENT_CHARS = 15_000

# DeepSeek 的 Fetch 接口会把 Markdown 标点转义（例如 ``\#``、``\[``、``\:``）。
# 只还原这些标点前的反斜杠；``C:\Users``、``\n`` 这类普通文本保持原样。
_MARKDOWN_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|>~:&/,=])")


class DeepSeekError(Exception):
  """对外错误。``status`` 是 HTTP 状态码（网络错误时为 None）。"""

  def __init__(self, message: str, status: int | None = None):
    super().__init__(message)
    self.status = status


class InvalidInput(DeepSeekError):
  """参数不合法，尚未发请求。"""


def codex_home() -> Path:
  raw = os.environ.get("CODEX_HOME")
  return Path(raw) if raw else Path.home() / ".codex"


def resolve_api_key() -> str:
  """优先环境变量，其次 Codex 配置里的 experimental_bearer_token。"""
  key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
  if key:
    return key

  config_path = codex_home() / "config.toml"
  try:
    text = config_path.read_text(encoding="utf-8")
  except FileNotFoundError:
    text = ""
  except OSError as exc:
    raise DeepSeekError(f"读不到 {config_path}: {exc}") from exc

  match = re.search(
    r'^\s*experimental_bearer_token\s*=\s*"([^"]+)"', text, re.MULTILINE
  )
  if not match:
    raise DeepSeekError(
      "未找到 DeepSeek API Key：请设置 DEEPSEEK_API_KEY，"
      "或在 ~/.codex/config.toml 中配置 experimental_bearer_token"
    )
  return match.group(1)


def _post(path: str, payload: dict[str, Any], timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
  body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
  request = urllib.request.Request(
    API_BASE + path,
    data=body,
    method="POST",
    headers={
      "Authorization": f"Bearer {resolve_api_key()}",
      "Content-Type": "application/json",
      "Accept": "application/json",
    },
  )

  try:
    with urllib.request.urlopen(request, timeout=timeout) as response:
      raw = response.read().decode("utf-8", "replace")
  except urllib.error.HTTPError as exc:
    detail = exc.read().decode("utf-8", "replace")
    message = detail[:500]
    try:
      message = json.loads(detail).get("error", {}).get("message") or message
    except (ValueError, AttributeError):
      pass
    raise DeepSeekError(f"HTTP {exc.code}: {message}", status=exc.code) from exc
  except urllib.error.URLError as exc:
    raise DeepSeekError(f"网络错误: {exc.reason}") from exc
  except TimeoutError as exc:
    raise DeepSeekError("请求超时") from exc

  try:
    data = json.loads(raw)
  except ValueError as exc:
    raise DeepSeekError(f"响应不是合法 JSON: {raw[:200]}") from exc
  if not isinstance(data, dict):
    raise DeepSeekError("响应不是 JSON 对象")
  return data


def search(query: str, count: int = 10, need_content: bool = False) -> dict[str, Any]:
  """搜索网页，返回结构化结果。"""
  text = (query or "").strip()
  if not text:
    raise InvalidInput("query 不能为空")
  if len(query) > MAX_QUERY_CHARS:
    raise InvalidInput(f"query 超过 {MAX_QUERY_CHARS} 个字符")
  if not 1 <= count <= 50:
    raise InvalidInput("count 必须在 1-50 之间")

  data = _post(
    SEARCH_PATH,
    {"query": query, "count": count, "need_content": bool(need_content)},
  )
  results = data.get("results")
  if not isinstance(results, list):
    raise DeepSeekError("响应缺少 results 数组")

  trimmed: list[dict[str, Any]] = []
  for item in results:
    if not isinstance(item, dict):
      continue
    entry = dict(item)
    content = entry.get("content") or ""
    if len(content) > MAX_RESULT_CONTENT_CHARS:
      entry["content"] = content[:MAX_RESULT_CONTENT_CHARS]
      entry["content_truncated"] = True
    trimmed.append(entry)

  return {"query": query, "returned": len(trimmed), "results": trimmed}


def unescape_markdown(text: str) -> str:
  """还原 DeepSeek Fetch 返回内容里被转义的 Markdown 标点。"""
  return _MARKDOWN_ESCAPE_RE.sub(r"\1", text)


def fetch(url: str) -> dict[str, Any]:
  """抓取单个网页，返回 Markdown 正文。"""
  raw = (url or "").strip()
  parts = urllib.parse.urlsplit(raw)
  if parts.scheme not in ("http", "https") or not parts.netloc:
    raise InvalidInput("url 必须是带 host 的 http/https 地址")
  if parts.username or parts.password:
    raise InvalidInput("url 不能包含用户名或密码")
  if len(raw) > MAX_URL_CHARS:
    raise InvalidInput(f"url 超过 {MAX_URL_CHARS} 个字符")

  data = _post(FETCH_PATH, {"url": raw})
  content = unescape_markdown(data.get("content") or "")
  title = unescape_markdown(data.get("title") or "")
  return {
    "url": raw,
    "title": title,
    "content": content[:MAX_FETCH_CHARS],
    "content_chars": len(content),
    "truncated": len(content) > MAX_FETCH_CHARS,
  }
