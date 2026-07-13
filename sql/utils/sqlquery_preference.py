# -*- coding: UTF-8 -*-

from sql.models import SqlQueryPreference

SQLQUERY_THEME_CHOICES = ("archery", "aliyun")
SQLQUERY_RESOURCE_TAB_CHOICES = ("table", "program")
SQLQUERY_MYSQL_TAB_CHOICES = ("knowledge", "favorite", "history")

SQLQUERY_PREFERENCE_DEFAULTS = {
    "theme": "archery",
    "resource_tab": "table",
    "mysql_tab": "knowledge",
}


def _normalize_choice(value, choices, default):
    value = (value or "").strip()
    return value if value in choices else default


def normalize_sqlquery_preference(values):
    values = values or {}
    return {
        "theme": _normalize_choice(
            values.get("theme"),
            SQLQUERY_THEME_CHOICES,
            SQLQUERY_PREFERENCE_DEFAULTS["theme"],
        ),
        "resource_tab": _normalize_choice(
            values.get("resource_tab"),
            SQLQUERY_RESOURCE_TAB_CHOICES,
            SQLQUERY_PREFERENCE_DEFAULTS["resource_tab"],
        ),
        "mysql_tab": _normalize_choice(
            values.get("mysql_tab"),
            SQLQUERY_MYSQL_TAB_CHOICES,
            SQLQUERY_PREFERENCE_DEFAULTS["mysql_tab"],
        ),
    }


def sqlquery_preference_from_model(preference):
    return normalize_sqlquery_preference(
        {
            "theme": preference.theme,
            "resource_tab": preference.resource_tab,
            "mysql_tab": preference.mysql_tab,
        }
    )


def get_sqlquery_preference(user):
    preference, _ = SqlQueryPreference.objects.get_or_create(
        username=user.username,
        defaults={
            "user_display": getattr(user, "display", "") or "",
            **SQLQUERY_PREFERENCE_DEFAULTS,
        },
    )
    return sqlquery_preference_from_model(preference)


def update_sqlquery_preference(user, values):
    preference, _ = SqlQueryPreference.objects.get_or_create(
        username=user.username,
        defaults={
            "user_display": getattr(user, "display", "") or "",
            **SQLQUERY_PREFERENCE_DEFAULTS,
        },
    )
    normalized = normalize_sqlquery_preference(
        {
            "theme": values.get("theme", preference.theme),
            "resource_tab": values.get("resource_tab", preference.resource_tab),
            "mysql_tab": values.get("mysql_tab", preference.mysql_tab),
        }
    )
    preference.user_display = getattr(user, "display", "") or preference.user_display
    preference.theme = normalized["theme"]
    preference.resource_tab = normalized["resource_tab"]
    preference.mysql_tab = normalized["mysql_tab"]
    preference.save()
    return sqlquery_preference_from_model(preference)
