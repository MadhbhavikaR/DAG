"""Provide a small Fail2ban stub when tests run outside a Linux host."""

import sys
import types

try:
    import fail2ban  # noqa: F401
except ImportError:
    fail2ban_module = types.ModuleType("fail2ban")
    server_module = types.ModuleType("fail2ban.server")
    actions_module = types.ModuleType("fail2ban.server.actions")

    class ActionBase:
        """Minimal initializer needed to import the action during unit tests."""

        def __init__(self, jail: object, name: str) -> None:
            self.jail = jail
            self.name = name

    actions_module.ActionBase = ActionBase
    sys.modules["fail2ban"] = fail2ban_module
    sys.modules["fail2ban.server"] = server_module
    sys.modules["fail2ban.server.actions"] = actions_module
