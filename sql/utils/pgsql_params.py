# -*- coding: UTF-8 -*-
import logging

from sql.engines import get_engine
from sql.models import ParamTemplate
from sql.utils.pgsql_metrics import (
    result_rows_to_dicts,
    sanitize_error,
    validate_metric_sql,
)

logger = logging.getLogger("default")

DEFAULT_PGSQL_PARAM_SQL = """
SELECT
  name AS variable_name,
  setting AS runtime_value,
  COALESCE(boot_val, reset_val, '') AS default_value,
  CASE
    WHEN enumvals IS NOT NULL THEN array_to_string(enumvals, '|')
    WHEN min_val IS NOT NULL OR max_val IS NOT NULL THEN concat('[', COALESCE(min_val, ''), '-', COALESCE(max_val, ''), ']')
    ELSE ''
  END AS valid_values,
  COALESCE(short_desc, '') AS description
FROM pg_settings
ORDER BY name
""".strip()


def configured_pgsql_param_queries(instance):
    templates = list(
        ParamTemplate.objects.filter(
            db_type="pgsql",
            param_query_enabled=True,
        )
        .exclude(param_query_sql="")
        .order_by("id")
    )
    if templates:
        return [
            {
                "name": item.variable_name,
                "sql": item.param_query_sql,
                "db_name": item.param_query_db_name,
                "timeout_ms": item.param_query_timeout_ms or 3000,
            }
            for item in templates
        ]

    return [
        {
            "name": "pg_settings参数展示",
            "sql": DEFAULT_PGSQL_PARAM_SQL,
            "db_name": "",
            "timeout_ms": 3000,
        }
    ]


def query_pgsql_params_for_instance(instance, search="", editable=False):
    # PostgreSQL 参数当前只展示，不支持在线修改。
    if editable:
        return []

    param_queries = configured_pgsql_param_queries(instance)
    templates = {
        item.variable_name.lower(): item
        for item in ParamTemplate.objects.filter(
            db_type="pgsql",
            param_query_sql="",
        )
    }
    engine = get_engine(instance=instance)
    rows = []

    for param_query in param_queries:
        ok, message, safe_sql = validate_metric_sql(param_query["sql"])
        if not ok:
            raise ValueError(f"{param_query['name']}：{message}")

        result_set = engine.query(
            db_name=param_query["db_name"] or instance.db_name or None,
            sql=safe_sql,
            max_execution_time=param_query["timeout_ms"],
        )
        if result_set.error:
            raise ValueError(
                f"{param_query['name']}：{sanitize_error(result_set.error)}"
            )

        for raw_row in result_rows_to_dicts(result_set):
            lower_row = {str(key).lower(): value for key, value in raw_row.items()}
            variable_name = lower_row.get("variable_name")
            if variable_name is None:
                variable_name = lower_row.get("name")
            if variable_name is None:
                continue

            variable_name = str(variable_name)
            if search and search.lower() not in variable_name.lower():
                continue

            template = templates.get(variable_name.lower())
            row = {
                "variable_name": variable_name,
                "runtime_value": lower_row.get(
                    "runtime_value", lower_row.get("setting", "")
                ),
                "default_value": lower_row.get("default_value", ""),
                "valid_values": lower_row.get("valid_values", ""),
                "description": lower_row.get("description", ""),
                "editable": False,
            }
            if template:
                row.update(
                    {
                        "id": template.id,
                        "default_value": template.default_value or row["default_value"],
                        "valid_values": template.valid_values or row["valid_values"],
                        "description": template.description or row["description"],
                        "editable": False,
                    }
                )
            rows.append(row)

    return rows
