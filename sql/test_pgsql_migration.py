# -*- coding: UTF-8 -*-
import json
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.test import TestCase

from common.utils.global_info import global_info
from sql.models import Instance, PgSQLMigrationTask, ResourceGroup
from sql.tool_plugins import tool_plugins_for_user
from sql.utils.pgsql_migration import (
    build_sequence_preview,
    parse_tables,
    validate_identifier,
)


class PgSQLMigrationUtilsTest(TestCase):
    def setUp(self):
        self.source = Instance.objects.create(
            instance_name="source_pg",
            type="master",
            db_type="pgsql",
            host="127.0.0.1",
            port=5432,
            user="postgres",
            password="pwd",
            db_name="postgres",
        )
        self.target = Instance.objects.create(
            instance_name="target_pg",
            type="master",
            db_type="pgsql",
            host="127.0.0.1",
            port=5432,
            user="postgres",
            password="pwd",
            db_name="postgres",
        )

    def test_parse_tables_requires_schema_and_table(self):
        self.assertEqual(
            parse_tables("public.users, audit.orders"),
            [
                {"schema_name": "public", "table_name": "users"},
                {"schema_name": "audit", "table_name": "orders"},
            ],
        )
        with self.assertRaisesMessage(ValueError, "表范围格式应为 schema.table"):
            parse_tables("users")

    def test_validate_identifier_rejects_sql_fragment(self):
        with self.assertRaisesMessage(ValueError, "Schema名称只允许"):
            validate_identifier("public;drop table x", "Schema名称")

    @patch("sql.utils.pgsql_migration.scan_sequences")
    def test_build_sequence_preview_marks_missing_and_skip_greater(
        self, scan_sequences
    ):
        scan_sequences.side_effect = [
            [
                {
                    "sequence_schema": "public",
                    "sequence_name": "users_id_seq",
                    "last_value": 100,
                    "table_schema": "public",
                    "table_name": "users",
                    "column_name": "id",
                },
                {
                    "sequence_schema": "public",
                    "sequence_name": "missing_seq",
                    "last_value": 5,
                },
            ],
            [
                {
                    "sequence_schema": "public",
                    "sequence_name": "users_id_seq",
                    "last_value": 20000,
                }
            ],
        ]

        rows = build_sequence_preview(
            self.source,
            self.target,
            step=10000,
            schemas=["public"],
            skip_if_target_greater=True,
        )

        self.assertEqual(rows[0]["target_value"], 10100)
        self.assertIn('"public"."users_id_seq"', rows[0]["setval_sql"])
        self.assertFalse(rows[0]["should_apply"])
        self.assertEqual(rows[0]["reason"], "target value is already greater")
        self.assertFalse(rows[1]["should_apply"])
        self.assertEqual(rows[1]["reason"], "target sequence not found")


class PgSQLMigrationViewTest(TestCase):
    def setUp(self):
        self.group = ResourceGroup.objects.create(group_name="pg_group")
        self.source = Instance.objects.create(
            instance_name="source_pg",
            type="master",
            db_type="pgsql",
            host="127.0.0.1",
            port=5432,
            user="postgres",
            password="pwd",
            db_name="postgres",
        )
        self.target = Instance.objects.create(
            instance_name="target_pg",
            type="master",
            db_type="pgsql",
            host="127.0.0.1",
            port=5432,
            user="postgres",
            password="pwd",
            db_name="postgres",
        )
        self.source.resource_group.add(self.group)
        self.target.resource_group.add(self.group)
        user_model = __import__(
            "django.contrib.auth", fromlist=["get_user_model"]
        ).get_user_model()
        self.user = user_model.objects.create_user(username="pg_user", password="pwd")
        self.user.resource_group.add(self.group)
        for codename in ["menu_pgsql_migration", "pgsql_migration_execute"]:
            self.user.user_permissions.add(Permission.objects.get(codename=codename))
        self.client.force_login(self.user)

    def test_create_task_uses_visible_pgsql_instances(self):
        response = self.client.post(
            "/pgsql_migration/tasks/create/",
            data={
                "name": "cutover check",
                "source_instance_id": self.source.id,
                "target_instance_id": self.target.id,
                "schemas": "public",
                "tables": "public.users",
                "description": "before cutover",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["status"], 0)
        task = PgSQLMigrationTask.objects.get(name="cutover check")
        self.assertEqual(task.source_instance, self.source)
        self.assertEqual(task.target_instance, self.target)
        self.assertEqual(json.loads(task.schemas_json), ["public"])
        self.assertEqual(
            json.loads(task.tables_json),
            [{"schema_name": "public", "table_name": "users"}],
        )

    def test_page_renders_task_list_without_operation_modal(self):
        response = self.client.get("/pgsql_migration/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PgSQL 手动迁移助手")
        self.assertContains(response, "加载源库表")
        self.assertContains(response, "target-table-list")
        self.assertNotContains(response, "task-detail-modal")

    def test_tool_plugin_registry_exposes_visible_pgsql_migration_plugin(self):
        plugins = tool_plugins_for_user(self.user)

        self.assertIn("pgsql_migration", [plugin.code for plugin in plugins])
        self.assertIn("PgSQL迁移助手", [plugin.name for plugin in plugins])

    def test_base_menu_uses_enabled_tool_plugins(self):
        self.user.user_permissions.add(Permission.objects.get(codename="menu_tools"))
        response = self.client.get("/pgsql_migration/")

        self.assertContains(response, "/pgsql_migration/")
        self.assertContains(response, "PgSQL迁移助手")

    def test_global_info_exposes_tool_plugins_for_templates(self):
        self.user.user_permissions.add(Permission.objects.get(codename="menu_tools"))
        request = type("Request", (), {"user": self.user})()

        context = global_info(request)

        self.assertIn("tool_plugins", context)
        self.assertIn(
            "pgsql_migration", [plugin.code for plugin in context["tool_plugins"]]
        )

    def test_disabled_pgsql_migration_plugin_returns_404(self):
        with self.settings(ENABLED_TOOL_PLUGINS=("archive", "my2sql", "schemasync")):
            response = self.client.get("/pgsql_migration/")

        self.assertEqual(response.status_code, 404)

    def test_disabled_tool_plugin_is_hidden_from_registry(self):
        with self.settings(ENABLED_TOOL_PLUGINS=("archive", "my2sql", "schemasync")):
            plugins = tool_plugins_for_user(self.user)

        self.assertNotIn("pgsql_migration", [plugin.code for plugin in plugins])

    @patch("sql.pgsql_migration.list_tables")
    def test_instance_tables_loads_visible_pgsql_instance_tables(self, list_tables_mock):
        list_tables_mock.return_value = [
            {
                "schema_name": "public",
                "table_name": "users",
                "estimated_rows": 10,
                "replica_identity": "DEFAULT",
                "primary_key_index": "users_pkey",
            }
        ]

        response = self.client.get(
            "/pgsql_migration/instances/tables/",
            data={"instance_id": self.source.id, "schemas": "public"},
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["status"], 0)
        self.assertEqual(payload["rows"][0]["table_name"], "users")
        list_tables_mock.assert_called_once_with(self.source, ["public"])

    def test_task_detail_renders_operation_page(self):
        task = PgSQLMigrationTask.objects.create(
            name="detail task",
            source_instance=self.source,
            target_instance=self.target,
            user_name=self.user.username,
            user_display=self.user.username,
        )

        response = self.client.get(f"/pgsql_migration/tasks/{task.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PgSQL 迁移任务操作")
        self.assertContains(response, "detail task")
        self.assertContains(response, "CAN_EXECUTE_PGSQL_MIGRATION = true")
        self.assertContains(response, "返回任务列表")

    def test_create_task_rejects_same_source_and_target(self):
        response = self.client.post(
            "/pgsql_migration/tasks/create/",
            data={
                "name": "bad",
                "source_instance_id": self.source.id,
                "target_instance_id": self.source.id,
            },
        )

        payload = json.loads(response.content)
        self.assertEqual(payload["status"], 1)
        self.assertIn("源库和目标库不能相同", payload["msg"])

    def test_delete_task_allows_creator_only_without_manage_permission(self):
        task = PgSQLMigrationTask.objects.create(
            name="owner task",
            source_instance=self.source,
            target_instance=self.target,
            user_name=self.user.username,
            user_display=self.user.username,
        )
        user_model = __import__(
            "django.contrib.auth", fromlist=["get_user_model"]
        ).get_user_model()
        other_user = user_model.objects.create_user(
            username="pg_other", password="pwd"
        )
        other_user.resource_group.add(self.group)
        other_user.user_permissions.add(
            Permission.objects.get(codename="menu_pgsql_migration")
        )

        self.client.force_login(other_user)
        response = self.client.post(
            "/pgsql_migration/tasks/delete/", data={"task_id": task.id}
        )
        payload = json.loads(response.content)
        self.assertEqual(payload["status"], 1)
        self.assertTrue(PgSQLMigrationTask.objects.filter(id=task.id).exists())

        self.client.force_login(self.user)
        response = self.client.post(
            "/pgsql_migration/tasks/delete/", data={"task_id": task.id}
        )
        payload = json.loads(response.content)
        self.assertEqual(payload["status"], 0)
        self.assertFalse(PgSQLMigrationTask.objects.filter(id=task.id).exists())
