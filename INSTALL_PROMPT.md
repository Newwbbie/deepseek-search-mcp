# 安装提示词（复制给接收方的 Codex）

把 `deepseek-search-mcp-0.1.0.zip` 发给同事，让他解压后，把下面整段提示词发给自己的 Codex，
并把尖括号里的内容替换成实际路径和 Key。

---

请在这台机器上安装并配置 MCP 服务 `deepseek-search-mcp`。

压缩包已解压到：`<解压后的目录，例如 D:\Tools\deepseek-search-mcp>`
我的 DeepSeek API Key：`<sk-...>`

请完成以下步骤：

1. 确认 `python --version` 不低于 3.10，并记录 python 的绝对路径。
2. 在解压目录执行 `python -m pip install -e .`，安装 `mcp` 依赖和入口。
3. 修改之前先备份 `~/.codex/config.toml`，然后只新增下面这一段，不要改动其他配置：

```toml
[mcp_servers.deepseek_search]
command = "<python 的绝对路径>"
args = ["-m", "deepseek_search_mcp.server"]
startup_timeout_sec = 30
default_tools_approval_mode = "auto"

[mcp_servers.deepseek_search.env]
DEEPSEEK_API_KEY = "<我的 Key>"
```

4. 运行 `python -m deepseek_search_mcp.client --list`，确认能看到 `search` 和 `fetch`。
5. 运行 `python -m deepseek_search_mcp.client --call search --args '{"query":"DeepSeek V4","count":3}'`，
   确认返回结果里 `returned` 大于 0。
6. 告诉我改动了哪个文件、验证结果，以及需要重启 Codex 才能让工具生效。

注意：不要把 API Key 写进代码、提交到 Git 或发到群里；只放在本机 `config.toml` 里。

---

如果对方不使用 Codex 而是其他 MCP 客户端，把第 3 步换成该客户端的 stdio 配置即可：
命令 `<python 绝对路径> -m deepseek_search_mcp.server`，环境变量 `DEEPSEEK_API_KEY`。
