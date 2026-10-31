"""Minute-resolution runtime time context for the built-in AstrBot agent."""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register
from astrbot.core.agent.message import TextPart

KEY = "astrbot_plugin_timenote.runtime"


def time_text(zone: str, now: datetime | None = None) -> str:
    """Format an aware instant in an explicit IANA time zone."""
    tz = ZoneInfo(zone)
    if now is not None and (now.tzinfo is None or now.utcoffset() is None):
        raise ValueError("An aware datetime is required")
    local = now.astimezone(tz) if now is not None else datetime.now(tz)
    offset = local.strftime("%z")
    return (
        f"当前时间：{local:%Y-%m-%d %H:%M}（星期{'一二三四五六日'[local.weekday()]}）\n"
        f"时区：{zone}，UTC{offset[:3]}:{offset[3:]}\n"
        "这是本次采样的服务器时间，精确到分钟；不是持续走动的时钟。\n"
        "以此理解今天、明天和时间先后；历史消息中的时间不代表现在。\n"
        "长任务后需要确认当前时间时调用 timenote_current_time。"
        "只在有需要时提及时间，沿用当前人格；不要声称仅凭时间上下文已经设置提醒。"
    )


@register(
    "astrbot_plugin_timenote", "CREAM", "时笺：让智能体知道此刻，精确到分钟", "0.1.0"
)
class TimeNote(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config if config is not None else {}

    async def initialize(self):
        ZoneInfo(self.config.get("timezone", "Asia/Shanghai"))

    def _refresh(self, event):
        state = event.get_extra(KEY)
        if not state:
            return
        # Requests and messages belong to this invocation, never to another session.
        text = (
            state["anchor"]
            + "\n"
            + time_text(self.config.get("timezone", "Asia/Shanghai"))
            + "\n</timenote_clock>"
        )
        if not self.config.get("enabled", True):
            text = (
                state["anchor"]
                + "\n时间上下文已关闭，请勿沿用先前的时间。\n</timenote_clock>"
            )
        state["part"].text = text
        run = state.get("run")
        if run is not None:
            # Runners may copy content parts while processing request context.
            for message in run.messages:
                if isinstance(message.content, list):
                    for part in message.content:
                        if isinstance(part, TextPart) and part.text.startswith(
                            state["anchor"] + "\n"
                        ):
                            part.text = text

    @filter.on_llm_request()
    async def inject_time(self, event: AstrMessageEvent, req: ProviderRequest):
        old = event.get_extra(KEY)
        if old:
            req.extra_user_content_parts[:] = [
                p for p in req.extra_user_content_parts if p is not old["part"]
            ]
        event.set_extra(KEY, None)
        if not self.config.get("enabled", True):
            return
        part = TextPart(text="").mark_as_temp()
        event.set_extra(
            KEY,
            {
                "anchor": f'<timenote_clock id="{uuid4().hex}">',
                "part": part,
                "run": None,
            },
        )
        self._refresh(event)
        req.extra_user_content_parts.append(part)

    @filter.on_agent_begin()
    async def refresh_at_start(self, event: AstrMessageEvent, run_context):
        state = event.get_extra(KEY)
        if state:
            state["run"] = run_context
            self._refresh(event)

    @filter.on_llm_tool_respond()
    async def refresh_after_tool(
        self, event: AstrMessageEvent, tool, tool_args, tool_result
    ):
        self._refresh(event)

    @filter.llm_tool(name="timenote_current_time")
    async def current_time(self, event: AstrMessageEvent) -> str:
        """获取当前日期、星期、时区及精确到分钟的时间。长工具执行后或需要确认此刻时间时调用，不用于设置提醒。"""
        return time_text(self.config.get("timezone", "Asia/Shanghai"))

    @filter.on_agent_done()
    async def clear_run(self, event: AstrMessageEvent, run_context, llm_response):
        event.set_extra(KEY, None)

    @filter.command("时笺")
    async def show_time(self, event: AstrMessageEvent):
        """显示当前时间和插件状态，不调用模型。"""
        event.stop_event()
        yield event.plain_result(
            "时笺 · TimeNote v0.1.0\n"
            + time_text(self.config.get("timezone", "Asia/Shanghai"))
            + f"\n自动注入：{'开启' if self.config.get('enabled', True) else '关闭'}"
        )
