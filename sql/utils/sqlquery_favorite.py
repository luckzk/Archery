# -*- coding: UTF-8 -*-
from django.db.models import Q

from sql.models import QueryLog, SqlQueryFavorite


SQLQUERY_KNOWLEDGE_ALIAS = "__sqlquery_knowledge__"


def favorite_item_from_model(favorite):
    return {
        "id": favorite.id,
        "alias": favorite.alias,
        "sqllog": favorite.sql,
        "instance_name": favorite.instance_name,
        "db_name": favorite.db_name,
        "source_query_log_id": favorite.source_query_log_id,
        "create_time": favorite.create_time,
        "sys_time": favorite.sys_time,
    }


def migrate_legacy_favorites(user):
    legacy_logs = QueryLog.objects.filter(
        username=user.username,
        favorite=True,
    ).exclude(alias=SQLQUERY_KNOWLEDGE_ALIAS)
    existing_source_ids = set(
        SqlQueryFavorite.objects.filter(
            username=user.username,
            source_query_log_id__isnull=False,
        ).values_list("source_query_log_id", flat=True)
    )
    favorite_rows = []
    for query_log in legacy_logs:
        if query_log.id in existing_source_ids:
            continue
        favorite_rows.append(
            SqlQueryFavorite(
                username=query_log.username,
                user_display=query_log.user_display,
                alias=query_log.alias or "",
                sql=query_log.sqllog,
                instance_name=query_log.instance_name,
                db_name=query_log.db_name,
                source_query_log_id=query_log.id,
                create_time=query_log.create_time,
                sys_time=query_log.sys_time,
            )
        )
    if favorite_rows:
        SqlQueryFavorite.objects.bulk_create(favorite_rows)


def favorite_queryset_for_user(user, search=""):
    migrate_legacy_favorites(user)
    favorites = SqlQueryFavorite.objects.filter(username=user.username)
    if search:
        favorites = favorites.filter(
            Q(sql__icontains=search)
            | Q(alias__icontains=search)
            | Q(instance_name__icontains=search)
            | Q(db_name__icontains=search)
        )
    return favorites.order_by("-sys_time", "-id")


def favorite_rows_for_user(user, search=""):
    return [
        favorite_item_from_model(favorite)
        for favorite in favorite_queryset_for_user(user, search)
    ]


def favorite_rows_for_template(user, fields=None):
    rows = []
    for favorite in favorite_queryset_for_user(user):
        item = favorite_item_from_model(favorite)
        if fields:
            item = {field: item.get(field) for field in fields}
            if "sql" in fields:
                item["sql"] = favorite.sql
            item["sqllog"] = favorite.sql
        rows.append(item)
    return rows


def favorite_by_source_query_log_id(user):
    migrate_legacy_favorites(user)
    favorites = SqlQueryFavorite.objects.filter(
        username=user.username,
        source_query_log_id__isnull=False,
    )
    return {favorite.source_query_log_id: favorite for favorite in favorites}
