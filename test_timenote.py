"""Behavior tests using the installed real AstrBot SDK."""

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfoNotFoundError

root = tempfile.TemporaryDirectory(prefix="timenote-tests-")
os.environ["ASTRBOT_ROOT"] = root.name
from astrbot.api.provider import ProviderRequest  # noqa: E402
from astrbot.core.agent.message import (  # noqa: E402
    Message,
    TextPart,
    dump_messages_with_checkpoints,
)

import main as plugin  # noqa: E402


class Event:
    def __init__(self):
        self.extra = {}

    def get_extra(self, key):
        return self.extra.get(key)

    def set_extra(self, key, value):
        self.extra[key] = value


class TimeTests(unittest.TestCase):
    def test_zone_conversion_and_midnight(self):
        text = plugin.time_text(
            "Asia/Shanghai", datetime(2026, 10, 31, 16, 1, 59, tzinfo=timezone.utc)
        )
        self.assertIn("2026-11-01 00:01（星期日）", text)
        self.assertIn("UTC+08:00", text)
        self.assertNotIn("00:01:59", text)

    def test_dst(self):
        a = plugin.time_text(
            "America/New_York", datetime(2026, 7, 1, tzinfo=timezone.utc)
        )
        b = plugin.time_text(
            "America/New_York", datetime(2026, 12, 1, tzinfo=timezone.utc)
        )
        self.assertIn("UTC-04:00", a)
        self.assertIn("UTC-05:00", b)

    def test_invalid_zone_and_naive_time(self):
        with self.assertRaises(ZoneInfoNotFoundError):
            plugin.time_text("Fake/Zone")
        with self.assertRaises(ValueError):
            plugin.time_text("UTC", datetime(2026, 1, 1))


class HookTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = plugin.TimeNote(SimpleNamespace(), {})
        await self.bot.initialize()
        self.event = Event()
        self.req = ProviderRequest(prompt="你好", system_prompt="保持人格", contexts=[])

    async def test_temp_injection_preserves_persona_and_user(self):
        other = TextPart(text="其他插件")
        self.req.extra_user_content_parts.append(other)
        await self.bot.inject_time(self.event, self.req)
        self.assertEqual(self.req.system_prompt, "保持人格")
        self.assertEqual(self.req.prompt, "你好")
        self.assertIs(self.req.extra_user_content_parts[0], other)
        self.assertTrue(self.req.extra_user_content_parts[1]._no_save)
        persisted = dump_messages_with_checkpoints(
            [Message(role="user", content=self.req.extra_user_content_parts)]
        )
        self.assertNotIn("timenote_clock", str(persisted))

    async def test_repeated_hook_has_one_owned_part(self):
        await self.bot.inject_time(self.event, self.req)
        await self.bot.inject_time(self.event, self.req)
        self.assertEqual(len(self.req.extra_user_content_parts), 1)

    async def test_cross_minute_after_tool_updates_copied_context(self):
        with patch.object(plugin, "time_text", return_value="2026-10-31 23:59"):
            await self.bot.inject_time(self.event, self.req)
        copied = self.req.extra_user_content_parts[0].model_copy(deep=True)
        run = SimpleNamespace(
            messages=[Message(role="user", content=[TextPart(text="原始输入"), copied])]
        )
        with patch.object(plugin, "time_text", return_value="2026-11-01 00:00"):
            await self.bot.refresh_at_start(self.event, run)
            await self.bot.refresh_after_tool(self.event, None, {}, None)
        self.assertIn("00:00", copied.text)
        self.assertNotIn("23:59", copied.text)
        self.assertEqual(run.messages[0].content[0].text, "原始输入")
        self.assertTrue(copied._no_save)

    async def test_concurrent_sessions_do_not_share_state(self):
        e2 = Event()
        r2 = ProviderRequest(prompt="B")
        await asyncio.gather(
            self.bot.inject_time(self.event, self.req), self.bot.inject_time(e2, r2)
        )
        self.assertNotEqual(
            self.event.get_extra(plugin.KEY)["anchor"],
            e2.get_extra(plugin.KEY)["anchor"],
        )

    async def test_disabled_injection_and_available_tool(self):
        self.bot.config["enabled"] = False
        await self.bot.inject_time(self.event, self.req)
        self.assertFalse(self.req.extra_user_content_parts)
        self.assertIn("当前时间", await self.bot.current_time(self.event))

    async def test_cleanup_releases_context(self):
        await self.bot.inject_time(self.event, self.req)
        await self.bot.clear_run(self.event, None, None)
        self.assertIsNone(self.event.get_extra(plugin.KEY))

    async def test_command_is_deterministic_without_model(self):
        self.event.stop_event = lambda: None
        self.event.plain_result = lambda text: text
        result = [x async for x in self.bot.show_time(self.event)]
        self.assertIn("当前时间", result[0])
        self.assertIn("自动注入：开启", result[0])


if __name__ == "__main__":
    unittest.main()
