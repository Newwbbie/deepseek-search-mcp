"""core 的单元测试：全部离线，HTTP 层用 mock 顶替。"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from deepseek_search_mcp import core


class SearchTests(unittest.TestCase):
  def test_search_returns_results_and_truncates_content(self):
    payload = {
      "results": [
        {"title": "A", "url": "https://a", "content": "x" * (core.MAX_RESULT_CONTENT_CHARS + 5)},
        {"title": "B", "url": "https://b", "content": ""},
        "ignored",
      ]
    }
    with mock.patch.object(core, "_post", return_value=payload) as post:
      result = core.search("DeepSeek", count=2, need_content=True)
    post.assert_called_once_with(
      core.SEARCH_PATH, {"query": "DeepSeek", "count": 2, "need_content": True}
    )
    self.assertEqual(result["returned"], 2)
    self.assertTrue(result["results"][0]["content_truncated"])
    self.assertEqual(len(result["results"][0]["content"]), core.MAX_RESULT_CONTENT_CHARS)

  def test_search_rejects_bad_input(self):
    for query, count in [("   ", 10), ("x" * 129, 10), ("ok", 0), ("ok", 51)]:
      with self.subTest(query=query[:10], count=count):
        with self.assertRaises(core.InvalidInput):
          core.search(query, count)

  def test_search_without_results_key(self):
    with mock.patch.object(core, "_post", return_value={}):
      with self.assertRaises(core.DeepSeekError):
        core.search("x")


class FetchTests(unittest.TestCase):
  def test_fetch_unescapes_markdown(self):
    body = {
      "title": r"\# 标题 \& 价格",
      "content": r"\# 标题 \[链接\]\(https\:\/\/a\.b\/c\)",
    }
    with mock.patch.object(core, "_post", return_value=body):
      result = core.fetch("https://example.com/a")
    self.assertEqual(result["title"], "# 标题 & 价格")
    self.assertEqual(result["content"], "# 标题 [链接](https://a.b/c)")
    self.assertEqual(result["content_chars"], len("# 标题 [链接](https://a.b/c)"))

  def test_fetch_truncates_long_content(self):
    body = {"title": "T", "content": "y" * (core.MAX_FETCH_CHARS + 10)}
    with mock.patch.object(core, "_post", return_value=body):
      result = core.fetch("https://example.com/a")
    self.assertEqual(result["title"], "T")
    self.assertTrue(result["truncated"])
    self.assertEqual(result["content_chars"], core.MAX_FETCH_CHARS + 10)
    self.assertEqual(len(result["content"]), core.MAX_FETCH_CHARS)

  def test_fetch_rejects_bad_url(self):
    for url in ["", "ftp://x/y", "https://", "https://u:p@example.com/x"]:
      with self.subTest(url=url):
        with self.assertRaises(core.InvalidInput):
          core.fetch(url)


class UnescapeTests(unittest.TestCase):
  def test_unescapes_markdown_punctuation(self):
    raw = r"\# 标题 \& 价格 \[链接\]\(https\:\/\/a\.b\/c\) 1\,000 \="
    self.assertEqual(
      core.unescape_markdown(raw), "# 标题 & 价格 [链接](https://a.b/c) 1,000 ="
    )

  def test_keeps_normal_backslashes(self):
    raw = r"C:\Users\wb\new folder"
    self.assertEqual(core.unescape_markdown(raw), raw)

  def test_double_backslash_becomes_single(self):
    self.assertEqual(core.unescape_markdown(r"\\d+"), r"\d+")


class ApiKeyTests(unittest.TestCase):
  def test_env_key_wins(self):
    with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-env"}, clear=False):
      self.assertEqual(core.resolve_api_key(), "sk-env")

  def test_reads_key_from_config(self):
    with tempfile.TemporaryDirectory() as tmp:
      config = Path(tmp) / "config.toml"
      config.write_text('model = "x"\nexperimental_bearer_token = "sk-cfg"\n', encoding="utf-8")
      env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
      env["CODEX_HOME"] = tmp
      with mock.patch.dict(os.environ, env, clear=True):
        self.assertEqual(core.resolve_api_key(), "sk-cfg")

  def test_missing_key_reports_clearly(self):
    with tempfile.TemporaryDirectory() as tmp:
      env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
      env["CODEX_HOME"] = tmp
      with mock.patch.dict(os.environ, env, clear=True):
        with self.assertRaises(core.DeepSeekError) as ctx:
          core.resolve_api_key()
        self.assertIn("API Key", str(ctx.exception))


class HttpTests(unittest.TestCase):
  def test_http_error_message_is_extracted(self):
    detail = json.dumps({"error": {"message": "bad request"}}).encode()
    err = urllib.error.HTTPError(
      "https://api.deepseek.com", 400, "Bad Request", {}, io.BytesIO(detail)
    )
    with mock.patch.object(core, "resolve_api_key", return_value="sk"), mock.patch.object(
      core.urllib.request, "urlopen", side_effect=err
    ):
      with self.assertRaises(core.DeepSeekError) as ctx:
        core._post(core.SEARCH_PATH, {"query": "x"})
    self.assertEqual(ctx.exception.status, 400)
    self.assertIn("bad request", str(ctx.exception))

  def test_network_error_is_wrapped(self):
    err = urllib.error.URLError("boom")
    with mock.patch.object(core, "resolve_api_key", return_value="sk"), mock.patch.object(
      core.urllib.request, "urlopen", side_effect=err
    ):
      with self.assertRaises(core.DeepSeekError) as ctx:
        core._post(core.SEARCH_PATH, {"query": "x"})
    self.assertIn("网络错误", str(ctx.exception))

  def test_invalid_json_response(self):
    response = mock.MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = b"not json"
    with mock.patch.object(core, "resolve_api_key", return_value="sk"), mock.patch.object(
      core.urllib.request, "urlopen", return_value=response
    ):
      with self.assertRaises(core.DeepSeekError):
        core._post(core.SEARCH_PATH, {"query": "x"})


if __name__ == "__main__":
  unittest.main()
