# -*- coding: UTF-8 -*-
from dataclasses import dataclass
from functools import wraps
from typing import Iterable, List

from django.conf import settings
from django.http import Http404


@dataclass(frozen=True)
class ToolPlugin:
    code: str
    name: str
    url: str
    menu_permission: str
    description: str = ""

    def is_allowed_for(self, user) -> bool:
        return bool(user and user.has_perm(self.menu_permission))


TOOL_PLUGINS = (
    ToolPlugin(
        code="archive",
        name="PTArchiver",
        url="/archive/",
        menu_permission="sql.menu_archive",
        description="MySQL 数据归档工具",
    ),
    ToolPlugin(
        code="pgsql_migration",
        name="PgSQL迁移助手",
        url="/pgsql_migration/",
        menu_permission="sql.menu_pgsql_migration",
        description="PostgreSQL 手动迁移准备、序列校准和数据检查",
    ),
    ToolPlugin(
        code="my2sql",
        name="My2SQL",
        url="/my2sql/",
        menu_permission="sql.menu_my2sql",
        description="MySQL binlog 解析工具",
    ),
    ToolPlugin(
        code="schemasync",
        name="SchemaSync",
        url="/schemasync/",
        menu_permission="sql.menu_schemasync",
        description="MySQL 表结构同步工具",
    ),
)


def enabled_tool_plugin_codes() -> List[str]:
    return list(getattr(settings, "ENABLED_TOOL_PLUGINS", ()))


def is_tool_plugin_enabled(code: str) -> bool:
    return code in enabled_tool_plugin_codes()


def enabled_tool_plugins() -> Iterable[ToolPlugin]:
    enabled_codes = set(enabled_tool_plugin_codes())
    return [plugin for plugin in TOOL_PLUGINS if plugin.code in enabled_codes]


def tool_plugins_for_user(user) -> List[ToolPlugin]:
    return [plugin for plugin in enabled_tool_plugins() if plugin.is_allowed_for(user)]


def tool_plugin_enabled_required(code: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not is_tool_plugin_enabled(code):
                raise Http404
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
