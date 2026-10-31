# 时笺 · TimeNote

### 让智能体知道此刻，而不是猜测现在。

**分钟级时间感知 · 临时上下文 · 长任务刷新 · 沿用主人格**

时笺是一个独立 AstrBot 插件。在正常 LLM 请求前注入当前日期、星期、小时分钟、IANA 时区和 UTC 偏移；Agent 启动及工具返回后刷新插件自己的时间片段。它不要求机器人每分钟说话，也不额外请求模型或外部授时 API。

```text
当前时间：2026-10-31 20:35（星期六）
时区：Asia/Shanghai，UTC+08:00
```

## 安装

在 AstrBot 插件管理中使用仓库地址安装：

```text
https://github.com/azaleakita/astrbot_plugin_timenote
```

或上传 Release 中的 ZIP，重载插件。在插件设置中选择时区，默认 `Asia/Shanghai`。需要 **AstrBot >=4.24、<5**，Python >=3.11 且满足 AstrBot 本身的要求。已使用真实 4.28.2 和 4.29.3 SDK 验证；4.24 是官方临时内容接口的最低版本，未对该版本部署验证。

## 使用

| 入口 | 功能 |
| --- | --- |
| 正常对话 | 自动提供本轮时间，无需用户添加指令 |
| `/时笺` | 直接查看当前分钟、时区和注入开关，不调用模型 |
| `timenote_current_time` 工具 | 智能体需要确认此刻时间时主动查询，特别适合长任务后 |
| 插件配置 `timezone` | IANA 时区，例如 `Asia/Shanghai`、`Asia/Singapore`、`Europe/London` |
| 插件配置 `enabled` | 控制自动注入；关闭后指令与查询工具仍可使用 |

保存配置后重载插件。无需填写 API Key，无需额外网页服务或后台定时器。当前时间查询工具需在 AstrBot 中启用工具调用并让目标模型可见。

## 按官方扩展接口实现

- `filter.on_llm_request()`：追加 `TextPart(...).mark_as_temp()` 到 `ProviderRequest.extra_user_content_parts`。
- `filter.on_agent_begin()`：记录本次运行上下文并刷新插件片段。
- `filter.on_llm_tool_respond()`：工具结束后刷新请求与运行消息中属于本次调用的时间片段，覆盖跨分钟、跨日的旧采样。
- `filter.llm_tool()`：提供当前时间查询工具；`filter.on_agent_done()` 清理运行引用。
- 不修改 `system_prompt`、原始用户文本或其他插件片段，不全局猴子补丁，不替换人格。
- 时间片段标记为临时内容，由 AstrBot 在保存历史时排除，避免陈旧时间污染后续对话；状态按当前事件保存，会话之间不共用。

官方依据：[事件钩子、动态上下文和临时内容](https://docs.astrbot.app/dev/star/guides/listen-message-event.html)、[AI 与工具接口](https://docs.astrbot.app/dev/star/guides/ai.html)。参考源代码：AstrBot `v4.29.3` 的 `astr_agent_hooks.py`、`agent/message.py` 和 `agent/runners/tool_loop_agent_runner.py`。

## 时间精度与边界

“精确到分钟”表示每次采样输出 `YYYY-MM-DD HH:MM`，不是持续更新的模型内时钟。时间来自运行 AstrBot 的操作系统，使用明确时区转换，正确处理跨日和夏令时。服务器应正常同步时间；本插件不会修复服务器时钟偏差。模型生成过程中没有官方逐分钟中断接口；一段很长的生成不会在中途自动刷新。下一轮请求、Agent 启动、工具返回或显式时间工具调用时重新采样。

主要适用于 AstrBot 内置 Agent。自定义插件直接调用 Provider、使用空 Agent hooks 或外部 Dify/Coze 执行器时，是否经过这些钩子取决于调用方，不保证自动覆盖。插件只提供时间事实，不创建提醒、不承诺后台持续运行，也不能保证模型一定正确推理相对日期。

## 验证

测试使用真实 AstrBot SDK，而非伪造 SDK：覆盖分钟/日期边界、UTC 偏移、夏令时、无效时区、重复注入、主人格保留、临时历史过滤、工具后刷新、会话隔离和查询指令。另提供真实插件 ZIP 安装、重载与运行钩子验证。

```bash
python -m pip install 'astrbot==4.29.3' 'mcp<2' -r requirements.txt ruff
python -m unittest -v test_timenote
python verify_install.py /path/to/timenote-v0.1.0.zip
```

不包含真实 QQ 和付费模型的端到端测试。安装后可发送 `/时笺` 核对时区，再询问 bot“现在是几月几日几点几分？”。

MIT License · CREAM / azaleakita
