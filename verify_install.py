"""Exercise the real AstrBot ZIP installer, reload, hooks and cleanup."""

import asyncio
import inspect
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


async def verify(archive):
    from astrbot.api.provider import ProviderRequest
    from astrbot.core import astrbot_config, db_helper
    from astrbot.core.agent.message import Message, dump_messages_with_checkpoints
    from astrbot.core.conversation_mgr import ConversationManager
    from astrbot.core.star.context import Context
    from astrbot.core.star.star import star_registry
    from astrbot.core.star.star_manager import PluginManager

    await db_helper.initialize()
    astrbot_config["disable_metrics"] = True
    fields = {
        n: None
        for n, p in inspect.signature(Context).parameters.items()
        if p.default is inspect.Parameter.empty
    }
    fields.update(
        event_queue=asyncio.Queue(),
        config=astrbot_config,
        db=db_helper,
        provider_manager=SimpleNamespace(),
        platform_manager=SimpleNamespace(platform_insts=[]),
        conversation_manager=ConversationManager(db_helper),
        astrbot_config_mgr=SimpleNamespace(get_conf=lambda *a, **kw: astrbot_config),
    )
    context = Context(**fields)
    manager = PluginManager(context, astrbot_config)
    plugin = None
    try:
        await manager.install_plugin_from_file(str(archive))
        success, error = await manager.reload("astrbot_plugin_timenote")
        assert success, error
        plugin = next(
            m.star_cls
            for m in star_registry
            if m.name == "astrbot_plugin_timenote" and m.star_cls
        )
        extra = {}
        event = SimpleNamespace(
            get_extra=extra.get, set_extra=lambda k, v: extra.__setitem__(k, v)
        )
        req = ProviderRequest(prompt="你好", system_prompt="人格不变")
        await plugin.inject_time(event, req)
        assert (
            req.system_prompt == "人格不变" and len(req.extra_user_content_parts) == 1
        )
        run = SimpleNamespace(
            messages=[Message(role="user", content=req.extra_user_content_parts)]
        )
        await plugin.refresh_at_start(event, run)
        await plugin.refresh_after_tool(event, None, {}, None)
        assert "当前时间" in req.extra_user_content_parts[0].text
        assert "timenote_clock" not in str(dump_messages_with_checkpoints(run.messages))
        assert "当前时间" in await plugin.current_time(event)
        await plugin.clear_run(event, run, None)
        assert all(v is None for v in extra.values())
        print(
            "PASS: actual ZIP install, reload, hook injection, temp history, time tool, cleanup"
        )
    finally:
        if plugin:
            await plugin.terminate()
        await db_helper.engine.dispose()


if __name__ == "__main__":
    archive = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="timenote-install-") as root:
        os.environ["ASTRBOT_ROOT"] = root
        sys.path.insert(0, root)
        for path in ("data/config", "data/plugins"):
            (Path(root) / path).mkdir(parents=True, exist_ok=True)
        isolated_archive = Path(root) / "plugin.zip"
        shutil.copy2(archive, isolated_archive)
        asyncio.run(verify(isolated_archive))
