import json
from datetime import timedelta, datetime
from unittest.mock import MagicMock, patch, Mock, ANY
try:
    from pytest_mock import MockerFixture
except ImportError:
    MockerFixture = object

import sqlparse
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import TestCase

from common.config import SysConfig
from sql.engines import EngineBase
from sql.engines.goinception import GoInceptionEngine
from sql.engines.models import ResultSet, ReviewSet, ReviewResult
from sql.engines.redis import RedisEngine
from sql.engines.pgsql import PgSQLEngine
from sql.engines.oracle import OracleEngine
from sql.engines.mongo import MongoEngine
from sql.engines.clickhouse import ClickHouseEngine
from sql.engines.odps import ODPSEngine
from sql.models import (
    DataMaskingColumns,
    DBDiagnosticSQLTemplate,
    Instance,
    SqlWorkflow,
    SqlWorkflowContent,
    Tunnel,
)

User = get_user_model()


class TestReviewSet(TestCase):
    def test_review_set(self):
        new_review_set = ReviewSet()
        new_review_set.rows = [{"id": "1679123"}]
        self.assertIn("1679123", new_review_set.json())


class TestEngineBase(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.u1 = User(username="some_user", display="用户1")
        cls.u1.save()
        cls.ins1 = Instance(
            instance_name="some_ins",
            type="master",
            db_type="mssql",
            host="some_host",
            port=1366,
            user="ins_user",
            password="some_str",
        )
        cls.ins1.save()
        cls.wf1 = SqlWorkflow.objects.create(
            workflow_name="some_name",
            group_id=1,
            group_name="g1",
            engineer=cls.u1.username,
            engineer_display=cls.u1.display,
            audit_auth_groups="some_group",
            create_time=datetime.now() - timedelta(days=1),
            status="workflow_finish",
            is_backup=True,
            instance=cls.ins1,
            db_name="some_db",
            syntax_type=1,
        )
        cls.wfc1 = SqlWorkflowContent.objects.create(
            workflow=cls.wf1,
            sql_content="some_sql",
            execute_result=json.dumps([{"id": 1, "sql": "some_content"}]),
        )

    @classmethod
    def tearDownClass(cls):
        cls.wfc1.delete()
        cls.wf1.delete()
        cls.ins1.delete()
        cls.u1.delete()

    def test_init_with_ins(self):
        engine = EngineBase(instance=self.ins1)
        self.assertEqual(self.ins1.instance_name, engine.instance_name)
        self.assertEqual(self.ins1.user, engine.user)


class TestRedis(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ins = Instance(
            instance_name="some_ins",
            type="slave",
            db_type="redis",
            mode="standalone",
            host="some_host",
            port=1366,
            user="ins_user",
            password="some_str",
        )
        cls.ins.save()

    @classmethod
    def tearDownClass(cls):
        cls.ins.delete()
        SqlWorkflow.objects.all().delete()
        SqlWorkflowContent.objects.all().delete()

    @patch("redis.Redis")
    def test_engine_base_info(self, _conn):
        new_engine = RedisEngine(instance=self.ins)
        self.assertEqual(new_engine.name, "Redis")
        self.assertEqual(new_engine.info, "Redis engine")

    @patch("redis.Redis")
    def test_get_connection(self, _conn):
        new_engine = RedisEngine(instance=self.ins)
        new_engine.get_connection()
        _conn.assert_called_once()

    @patch("redis.Redis.execute_command", return_value=[1, 2, 3])
    def test_query_return_list(self, _execute_command):
        new_engine = RedisEngine(instance=self.ins)
        query_result = new_engine.query(db_name=0, sql="keys *", limit_num=100)
        self.assertIsInstance(query_result, ResultSet)
        self.assertTupleEqual(query_result.rows, ([1], [2], [3]))

    @patch("redis.Redis.execute_command", return_value="text")
    def test_query_return_str(self, _execute_command):
        new_engine = RedisEngine(instance=self.ins)
        query_result = new_engine.query(db_name=0, sql="keys *", limit_num=100)
        self.assertIsInstance(query_result, ResultSet)
        self.assertTupleEqual(query_result.rows, (["text"],))

    @patch("redis.Redis.execute_command", return_value="text")
    def test_query_execute(self, _execute_command):
        new_engine = RedisEngine(instance=self.ins)
        query_result = new_engine.query(db_name=0, sql="keys *", limit_num=100)
        self.assertIsInstance(query_result, ResultSet)
        self.assertTupleEqual(query_result.rows, (["text"],))

    @patch("redis.Redis.execute_command")
    def test_query_with_dict_response(self, _execute_command):
        # 定义 execute_command 的字典响应
        dict_response = {
            "key1": "value1",
            "key2": {"subkey": "subvalue"},
            "key3": ["listitem1", "listitem2"],
        }
        _execute_command.return_value = dict_response
        new_engine = RedisEngine(instance=self.ins)
        query_result = new_engine.query(db_name=0, sql="keys *", limit_num=100)

        # 验证结果集
        expected_rows = [
            ["key1", "value1"],
            ["key2", json.dumps({"subkey": "subvalue"})],
            ["key3", json.dumps(["listitem1", "listitem2"])],
        ]
        self.assertIsInstance(query_result, ResultSet)
        self.assertEqual(query_result.column_list, ["field", "value"])
        self.assertEqual(query_result.rows, tuple(expected_rows))
        self.assertEqual(query_result.affected_rows, len(expected_rows))

    @patch("redis.Redis.info")
    def test_get_all_databases(self, mock_info):
        mock_info.return_value = {
            "db0": {"keys": 10, "expires": 0},
            "db1": {"keys": 5, "expires": 0},
            "db2": {"keys": 0, "expires": 0},
            "db3": {"keys": 0, "expires": 0},
        }
        new_engine = RedisEngine(instance=self.ins)
        dbs = new_engine.get_all_databases()
        # 应返回 db0~db15，补充缺失库
        self.assertEqual(len(dbs.rows), 16)
        self.assertEqual(dbs.rows[0], {"value": "0", "text": "db0[10]"})
        self.assertEqual(dbs.rows[1], {"value": "1", "text": "db1[5]"})
        self.assertEqual(dbs.rows[4], {"value": "4", "text": "db4"})

    @patch("redis.Redis.info")
    def test_get_all_databases_exception_handling(self, mock_info):
        # 模拟info方法返回特定的Keyspace信息
        mock_info.return_value = {
            "db0": {"keys": 10, "expires": 0},
            "db1": {"keys": 5, "expires": 0},
            "db18": {"keys": 20, "expires": 0},
        }
        # 实例化RedisEngine并调用get_all_databases方法
        new_engine = RedisEngine(instance=self.ins)
        result = new_engine.get_all_databases()
        # 验证返回的数据库列表是否符合预期，0~18，共19个
        self.assertEqual(len(result.rows), 19)
        self.assertEqual(result.rows[0], {"value": "0", "text": "db0[10]"})
        self.assertEqual(result.rows[18], {"value": "18", "text": "db18[20]"})
        # 验证info方法被调用
        mock_info.assert_called_once_with("Keyspace")

    @patch("redis.Redis.info")
    def test_get_all_databases_with_empty_return_value(self, mock_info):
        """
        测试当info命令返回空Keyspace信息时，
        get_all_databases方法应正确处理并返回包含从0到15的数据库索引列表。
        """
        # 模拟info方法返回空的Keyspace信息
        mock_info.return_value = {}
        # 实例化RedisEngine并调用get_all_databases方法
        new_engine = RedisEngine(instance=self.ins)
        result = new_engine.get_all_databases()
        # 验证返回的数据库列表，应该包括0到15，总共16个数据库
        self.assertEqual(len(result.rows), 16)
        self.assertEqual(result.rows[0], {"value": "0", "text": "db0"})
        self.assertEqual(result.rows[15], {"value": "15", "text": "db15"})
        # 验证info方法的调用
        mock_info.assert_called_once_with("Keyspace")

    @patch("redis.Redis.info")
    def test_get_all_databases_with_less_than_15_dbs(self, mock_info):
        """
        测试当info命令返回的Keyspace信息
        db num数据库值小于15时，get_all_databases方法应正确处理并返回包含从0到15的数据库索引列表。
        """
        # 模拟info方法返回小于15个数据库的Keyspace信息
        mock_info.return_value = {
            "db0": {"keys": 10, "expires": 0},
            "db1": {"keys": 5, "expires": 0},
            "db5": {"keys": 0, "expires": 0},
            # 假设只有3个数据库
        }
        # 实例化RedisEngine并调用get_all_databases方法
        new_engine = RedisEngine(instance=self.ins)
        result = new_engine.get_all_databases()
        # 验证返回的数据库列表，应该包括0到15，总共16个数据库
        self.assertEqual(len(result.rows), 16)
        self.assertEqual(result.rows[0], {"value": "0", "text": "db0[10]"})
        self.assertEqual(result.rows[1], {"value": "1", "text": "db1[5]"})
        self.assertEqual(result.rows[5], {"value": "5", "text": "db5"})
        # 验证info方法的调用
        mock_info.assert_called_once_with("Keyspace")

    @patch(
        "redis.Redis.scan_iter", return_value=["table1", "table2", "table3", "table4"]
    )
    def test_get_all_tables_success(self, _scan_iter):
        # 创建 RedisEngine 实例
        new_engine = RedisEngine(instance=self.ins)

        # 调用 get_all_tables 方法
        db_name = "4"
        result = new_engine.get_all_tables(db_name)
        mask_result_rows = ["table1", "table2", "table3", "table4"]
        # 验证返回的表格信息
        self.assertEqual(result.rows, mask_result_rows)

    @patch("redis.Redis.scan_iter", side_effect=Exception("Test Exception"))
    def test_get_all_tables_exception(self, _scan_iter):
        # 创建 RedisEngine 实例
        new_engine = RedisEngine(instance=self.ins)

        # 调用 get_all_tables 方法并模拟异常
        db_name = "4"
        result = new_engine.get_all_tables(db_name)

        # 验证返回的异常信息
        self.assertEqual(result.rows, [])
        self.assertIn(result.message, "Test Exception")

    def test_query_check_safe_cmd(self):
        safe_cmd = "keys 1*"
        new_engine = RedisEngine(instance=self.ins)
        check_result = new_engine.query_check(db_name=0, sql=safe_cmd)
        self.assertDictEqual(
            check_result,
            {
                "msg": "禁止执行该命令！",
                "bad_query": True,
                "filtered_sql": safe_cmd,
                "has_star": False,
            },
        )

    def test_query_check_danger_cmd(self):
        safe_cmd = "keys *"
        new_engine = RedisEngine(instance=self.ins)
        check_result = new_engine.query_check(db_name=0, sql=safe_cmd)
        self.assertDictEqual(
            check_result,
            {
                "msg": "禁止执行该命令！",
                "bad_query": True,
                "filtered_sql": safe_cmd,
                "has_star": False,
            },
        )

    def test_filter_sql(self):
        safe_cmd = "keys 1*"
        new_engine = RedisEngine(instance=self.ins)
        check_result = new_engine.filter_sql(sql=safe_cmd, limit_num=100)
        self.assertEqual(check_result, "keys 1*")

    def test_query_masking(self):
        query_result = ResultSet()
        new_engine = RedisEngine(instance=self.ins)
        masking_result = new_engine.query_masking(
            db_name=0, sql="", resultset=query_result
        )
        self.assertEqual(masking_result, query_result)

    def test_execute_check(self):
        sql = "set 1 1"
        row = ReviewResult(
            id=1,
            errlevel=0,
            stagestatus="Audit completed",
            errormessage="暂不支持显示影响行数",
            sql=sql,
            affected_rows=0,
            execute_time=0,
        )
        new_engine = RedisEngine(instance=self.ins)
        check_result = new_engine.execute_check(db_name=0, sql=sql)
        self.assertIsInstance(check_result, ReviewSet)
        self.assertEqual(check_result.rows[0].__dict__, row.__dict__)

    @patch("redis.Redis.execute_command", return_value="text")
    def test_execute_workflow_success(self, _execute_command):
        sql = "set 1 1"
        row = ReviewResult(
            id=1,
            errlevel=0,
            stagestatus="Execute Successfully",
            errormessage="暂不支持显示影响行数",
            sql=sql,
            affected_rows=0,
            execute_time=0,
        )
        wf = SqlWorkflow.objects.create(
            workflow_name="some_name",
            group_id=1,
            group_name="g1",
            engineer_display="",
            audit_auth_groups="some_group",
            create_time=datetime.now() - timedelta(days=1),
            status="workflow_finish",
            is_backup=True,
            instance=self.ins,
            db_name="some_db",
            syntax_type=1,
        )
        SqlWorkflowContent.objects.create(workflow=wf, sql_content=sql)
        new_engine = RedisEngine(instance=self.ins)
        execute_result = new_engine.execute_workflow(workflow=wf)
        self.assertIsInstance(execute_result, ReviewSet)
        self.assertEqual(execute_result.rows[0].__dict__.keys(), row.__dict__.keys())

    @patch("sql.engines.redis.RedisEngine.get_connection")
    def test_processlist(self, mock_get_connection):
        """测试 processlist 方法，模拟获取连接并返回客户端列表"""

        # 模拟 Redis 连接的客户端列表
        mock_conn = Mock()

        return_value_mock = [
            {"id": "1", "idle": 10, "name": "client_1"},
            {"id": "2", "idle": 5, "name": "client_2"},
            {"id": "3", "idle": 20, "name": "client_3"},
        ]
        mock_conn.client_list.return_value = return_value_mock

        # 设置 get_connection 返回模拟连接
        mock_get_connection.return_value = mock_conn

        # 创建 RedisEngine 实例
        new_engine = RedisEngine(instance=self.ins)

        # 调用 processlist 方法并测试其返回值
        command_types = ["All"]  # 假设支持的命令类型
        for command_type in command_types:
            result_set = new_engine.processlist(command_type=command_type)

            # 验证返回值是 ResultSet 实例
            self.assertIsInstance(result_set, ResultSet)

            # 验证返回的客户端列表被正确排序
            sorted_clients = sorted(
                return_value_mock, key=lambda client: client.get("idle"), reverse=False
            )
            self.assertEqual(result_set.rows, sorted_clients)

        # 验证 get_connection 是否被调用
        mock_get_connection.assert_called()


class TestPgSQL(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ins = Instance(
            instance_name="some_ins",
            type="slave",
            db_type="pgsql",
            host="some_host",
            port=1366,
            user="ins_user",
            password="some_str",
        )
        cls.ins.save()
        cls.sys_config = SysConfig()

    def tearDown(self):
        DBDiagnosticSQLTemplate.objects.all().delete()

    @classmethod
    def tearDownClass(cls):
        DBDiagnosticSQLTemplate.objects.all().delete()
        cls.ins.delete()
        cls.sys_config.purge()

    @patch("psycopg2.connect")
    def test_engine_base_info(self, _conn):
        new_engine = PgSQLEngine(instance=self.ins)
        self.assertEqual(new_engine.name, "PgSQL")
        self.assertEqual(new_engine.info, "PgSQL engine")

    def test_get_table_ref_with_schema_and_default(self):
        """带 schema 的表用其 schema, 不带 schema 的表用传入的 schema_name 补全"""
        new_engine = PgSQLEngine(instance=self.ins)
        table_ref = new_engine.get_table_ref(
            "select * from s1.t1 join t2 on t1.id = t2.id",
            db_name="archery",
            schema_name="public",
        )
        self.assertIn({"schema": "s1", "name": "t1"}, table_ref)
        self.assertIn({"schema": "public", "name": "t2"}, table_ref)
        self.assertEqual(len(table_ref), 2)

    def test_get_table_ref_excludes_cte(self):
        """CTE (with 子句) 定义的临时表名不应被当作真实表"""
        new_engine = PgSQLEngine(instance=self.ins)
        table_ref = new_engine.get_table_ref(
            "with c as (select * from public.orders) "
            "select * from c join s2.items i on 1=1",
            db_name="archery",
            schema_name="public",
        )
        names = [t["name"] for t in table_ref]
        self.assertNotIn("c", names)
        self.assertIn({"schema": "public", "name": "orders"}, table_ref)
        self.assertIn({"schema": "s2", "name": "items"}, table_ref)

    def test_get_table_ref_skips_system_schema(self):
        """pg_catalog / information_schema 系统 schema 应被跳过"""
        new_engine = PgSQLEngine(instance=self.ins)
        table_ref = new_engine.get_table_ref(
            "select * from pg_catalog.pg_stat_activity",
            db_name="archery",
            schema_name="public",
        )
        self.assertEqual(table_ref, [])

    @patch("psycopg2.connect")
    def test_get_connection(self, _conn):
        new_engine = PgSQLEngine(instance=self.ins)
        new_engine.get_connection("some_dbname")
        _conn.assert_called_once()

    @patch("psycopg2.connect.cursor.execute")
    @patch("psycopg2.connect.cursor")
    @patch("psycopg2.connect")
    def test_query(self, _conn, _cursor, _execute):
        _conn.return_value.cursor.return_value.fetchmany.return_value = [(1,)]
        new_engine = PgSQLEngine(instance=self.ins)
        query_result = new_engine.query(
            db_name="some_dbname",
            sql="select 1",
            limit_num=100,
            schema_name="some_schema",
        )
        self.assertIsInstance(query_result, ResultSet)
        self.assertListEqual(query_result.rows, [(1,)])

    @patch("psycopg2.connect.cursor.execute")
    @patch("psycopg2.connect.cursor")
    @patch("psycopg2.connect")
    def test_query_not_limit(self, _conn, _cursor, _execute):
        # 模拟数据库连接和游标
        mock_cursor = MagicMock()
        _conn.return_value.cursor.return_value = mock_cursor

        # 模拟 SQL 查询的返回结果，包含 JSONB 类型、字符串和数字数据
        mock_cursor.fetchall.return_value = [
            ({"key": "value"}, "test_string", 123)  # 返回一行数据，三列
        ]
        mock_cursor.description = [
            ("json_column", 3802),  # JSONB 类型
            ("string_column", 25),  # 25 表示 TEXT 类型的 OID
            ("number_column", 23),  # 23 表示 INTEGER 类型的 OID
        ]

        # _conn.return_value.cursor.return_value.fetchall.return_value = [(1,)]
        new_engine = PgSQLEngine(instance=self.ins)
        query_result = new_engine.query(
            db_name="some_dbname",
            sql="SELECT json_column, string_column, number_column FROM some_table",
            limit_num=0,
            schema_name="some_schema",
        )

        # 断言查询结果的类型和数据
        self.assertIsInstance(query_result, ResultSet)
        # 验证返回的 JSONB 列已转换为 JSON 字符串
        expected_row = ('{"key": "value"}', "test_string", 123)
        self.assertListEqual(query_result.rows, [expected_row])

        expected_column = ["json_column", "string_column", "number_column"]
        # 验证列名是否正确
        self.assertEqual(query_result.column_list, expected_column)

        # 验证受影响的行数
        self.assertEqual(query_result.affected_rows, 1)

        # 验证类型代码是否正确（3802 表示 JSONB，25 表示 TEXT，23 表示 INTEGER）
        expected_column_type_codes = [3802, 25, 23]
        actual_column_type_codes = [desc[1] for desc in mock_cursor.description]
        self.assertListEqual(actual_column_type_codes, expected_column_type_codes)

    @patch(
        "sql.engines.pgsql.PgSQLEngine.query",
        return_value=ResultSet(
            rows=[("postgres",), ("archery",), ("template1",), ("template0",)]
        ),
    )
    def test_get_all_databases(self, query):
        new_engine = PgSQLEngine(instance=self.ins)
        dbs = new_engine.get_all_databases()
        self.assertListEqual(dbs.rows, ["postgres", "archery"])

    @patch(
        "sql.engines.pgsql.PgSQLEngine.query",
        return_value=ResultSet(
            rows=[("information_schema",), ("archery",), ("pg_catalog",)]
        ),
    )
    def test_get_all_schemas(self, _query):
        new_engine = PgSQLEngine(instance=self.ins)
        schemas = new_engine.get_all_schemas(db_name="archery")
        self.assertListEqual(schemas.rows, ["archery"])

    @patch(
        "sql.engines.pgsql.PgSQLEngine.query",
        return_value=ResultSet(rows=[("test",), ("test2",)]),
    )
    def test_get_all_tables(self, _query):
        new_engine = PgSQLEngine(instance=self.ins)
        tables = new_engine.get_all_tables(db_name="archery", schema_name="archery")
        self.assertListEqual(tables.rows, ["test2"])

    @patch(
        "sql.engines.pgsql.PgSQLEngine.query",
        return_value=ResultSet(rows=[("id",), ("name",)]),
    )
    def test_get_all_columns_by_tb(self, _query):
        new_engine = PgSQLEngine(instance=self.ins)
        columns = new_engine.get_all_columns_by_tb(
            db_name="archery", tb_name="test2", schema_name="archery"
        )
        self.assertListEqual(columns.rows, ["id", "name"])

    @patch(
        "sql.engines.pgsql.PgSQLEngine.query",
        return_value=ResultSet(
            rows=[("postgres",), ("archery",), ("template1",), ("template0",)]
        ),
    )
    def test_describe_table(self, _query):
        new_engine = PgSQLEngine(instance=self.ins)
        describe = new_engine.describe_table(
            db_name="archery", schema_name="archery", tb_name="text"
        )
        self.assertIsInstance(describe, ResultSet)

    def test_query_check_disable_sql(self):
        sql = "update xxx set a=1 "
        new_engine = PgSQLEngine(instance=self.ins)
        check_result = new_engine.query_check(db_name="archery", sql=sql)
        self.assertDictEqual(
            check_result,
            {
                "msg": "不支持的查询语法类型!",
                "bad_query": True,
                "filtered_sql": sql.strip(),
                "has_star": False,
            },
        )

    def test_query_check_star_sql(self):
        sql = "select * from xx "
        new_engine = PgSQLEngine(instance=self.ins)
        check_result = new_engine.query_check(db_name="archery", sql=sql)
        self.assertDictEqual(
            check_result,
            {
                "msg": "SQL语句中含有 * ",
                "bad_query": False,
                "filtered_sql": sql.strip(),
                "has_star": True,
            },
        )

    def test_query_check_explain(self):
        sql = "explain select x from xx "
        new_engine = PgSQLEngine(instance=self.ins)
        check_result = new_engine.query_check(db_name="archery", sql=sql)
        self.assertDictEqual(
            check_result,
            {
                "msg": "",
                "bad_query": False,
                "filtered_sql": sql.strip(),
                "has_star": False,
            },
        )

    def test_filter_sql_with_delimiter(self):
        sql = "select * from xx;"
        new_engine = PgSQLEngine(instance=self.ins)
        check_result = new_engine.filter_sql(sql=sql, limit_num=100)
        self.assertEqual(check_result, "select * from xx limit 100;")

    def test_filter_sql_without_delimiter(self):
        sql = "select * from xx"
        new_engine = PgSQLEngine(instance=self.ins)
        check_result = new_engine.filter_sql(sql=sql, limit_num=100)
        self.assertEqual(check_result, "select * from xx limit 100;")

    def test_filter_sql_with_limit(self):
        sql = "select * from xx limit 10"
        new_engine = PgSQLEngine(instance=self.ins)
        check_result = new_engine.filter_sql(sql=sql, limit_num=1)
        self.assertEqual(check_result, "select * from xx limit 10;")

    def test_query_masking(self):
        query_result = ResultSet()
        new_engine = PgSQLEngine(instance=self.ins)
        masking_result = new_engine.query_masking(
            db_name=0, sql="", resultset=query_result
        )
        self.assertEqual(masking_result, query_result)

    def test_execute_check_select_sql(self):
        sql = "select * from user;"
        row = ReviewResult(
            id=1,
            errlevel=2,
            stagestatus="驳回不支持语句",
            errormessage="仅支持DML和DDL语句，查询语句请使用SQL查询功能！",
            sql=sql,
        )
        new_engine = PgSQLEngine(instance=self.ins)
        check_result = new_engine.execute_check(db_name="archery", sql=sql)
        self.assertIsInstance(check_result, ReviewSet)
        self.assertEqual(check_result.rows[0].__dict__, row.__dict__)

    def test_execute_check_critical_sql(self):
        self.sys_config.set("critical_ddl_regex", "^|update")
        self.sys_config.get_all_config()
        sql = "update user set id=1"
        row = ReviewResult(
            id=1,
            errlevel=2,
            stagestatus="驳回高危SQL",
            errormessage="禁止提交匹配" + "^|update" + "条件的语句！",
            sql=sql,
        )
        new_engine = PgSQLEngine(instance=self.ins)
        check_result = new_engine.execute_check(db_name="archery", sql=sql)
        self.assertIsInstance(check_result, ReviewSet)
        self.assertEqual(check_result.rows[0].__dict__, row.__dict__)

    def test_execute_check_normal_sql(self):
        self.sys_config.purge()
        sql = "alter table tb set id=1"
        row = ReviewResult(
            id=1,
            errlevel=0,
            stagestatus="Audit completed",
            errormessage="None",
            sql=sql,
            affected_rows=0,
            execute_time=0,
        )
        new_engine = PgSQLEngine(instance=self.ins)
        check_result = new_engine.execute_check(db_name="archery", sql=sql)
        self.assertIsInstance(check_result, ReviewSet)
        self.assertEqual(check_result.rows[0].__dict__, row.__dict__)

    @patch("psycopg2.connect.cursor.execute")
    @patch("psycopg2.connect.cursor")
    @patch("psycopg2.connect")
    def test_execute_workflow_success(self, _conn, _cursor, _execute):
        sql = "update user set id=1"
        row = ReviewResult(
            id=1,
            errlevel=0,
            stagestatus="Execute Successfully",
            errormessage="None",
            sql=sql,
            affected_rows=0,
            execute_time=0,
        )
        wf = SqlWorkflow.objects.create(
            workflow_name="some_name",
            group_id=1,
            group_name="g1",
            engineer_display="",
            audit_auth_groups="some_group",
            create_time=datetime.now() - timedelta(days=1),
            status="workflow_finish",
            is_backup=True,
            instance=self.ins,
            db_name="some_db",
            syntax_type=1,
        )
        SqlWorkflowContent.objects.create(workflow=wf, sql_content=sql)
        new_engine = PgSQLEngine(instance=self.ins)
        execute_result = new_engine.execute_workflow(workflow=wf)
        self.assertIsInstance(execute_result, ReviewSet)
        self.assertEqual(execute_result.rows[0].__dict__.keys(), row.__dict__.keys())

    @patch("psycopg2.connect.cursor.execute")
    @patch("psycopg2.connect.cursor")
    @patch("psycopg2.connect", return_value=RuntimeError)
    def test_execute_workflow_exception(self, _conn, _cursor, _execute):
        sql = "update user set id=1"
        row = ReviewResult(
            id=1,
            errlevel=2,
            stagestatus="Execute Failed",
            errormessage=f'异常信息：{f"Oracle命令执行报错，语句：{sql}"}',
            sql=sql,
            affected_rows=0,
            execute_time=0,
        )
        wf = SqlWorkflow.objects.create(
            workflow_name="some_name",
            group_id=1,
            group_name="g1",
            engineer_display="",
            audit_auth_groups="some_group",
            create_time=datetime.now() - timedelta(days=1),
            status="workflow_finish",
            is_backup=True,
            instance=self.ins,
            db_name="some_db",
            syntax_type=1,
        )
        SqlWorkflowContent.objects.create(workflow=wf, sql_content=sql)
        with self.assertRaises(AttributeError):
            new_engine = PgSQLEngine(instance=self.ins)
            execute_result = new_engine.execute_workflow(workflow=wf)
            self.assertIsInstance(execute_result, ReviewSet)
            self.assertEqual(
                execute_result.rows[0].__dict__.keys(), row.__dict__.keys()
            )

    def test_dbdiagnostic_template_rejects_non_pgsql_and_write_sql(self):
        template = DBDiagnosticSQLTemplate(
            db_type="mysql",
            diagnostic_type="pgsql_processlist",
            template_name="bad",
            sql="update t set id = 1",
        )

        with self.assertRaises(ValidationError) as context:
            template.full_clean()

        self.assertIn("db_type", context.exception.message_dict)
        self.assertIn("sql", context.exception.message_dict)

    def test_dbdiagnostic_validate_select_sql_accepts_cte(self):
        ok, message, safe_sql = DBDiagnosticSQLTemplate.validate_select_sql(
            "WITH RECURSIVE x AS (SELECT 1 AS id) SELECT id FROM x;"
        )

        self.assertTrue(ok)
        self.assertEqual(message, "")
        self.assertEqual(
            safe_sql, "WITH RECURSIVE x AS (SELECT 1 AS id) SELECT id FROM x"
        )

    def test_dbdiagnostic_validate_select_sql_rejects_empty_and_multiple(self):
        ok, message, safe_sql = DBDiagnosticSQLTemplate.validate_select_sql("")

        self.assertFalse(ok)
        self.assertEqual(message, "SQL不能为空")
        self.assertEqual(safe_sql, "")

        ok, message, safe_sql = DBDiagnosticSQLTemplate.validate_select_sql(
            "SELECT 1; SELECT 2;"
        )

        self.assertFalse(ok)
        self.assertEqual(message, "只允许单条SELECT语句")
        self.assertEqual(safe_sql, "")

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_dbdiagnostic_sql_rejects_invalid_template_at_runtime(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_processlist",
            template_name="invalid runtime sql",
            sql="SELECT 1; SELECT 2;",
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.processlist(command_type="All")

        self.assertEqual(result.error, "只允许单条SELECT语句")
        mock_query.assert_not_called()

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_dbdiagnostic_sql_ignores_disabled_templates(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_processlist",
            template_name="enabled template",
            sql=(
                "SELECT 1 AS pid, 'postgres' AS datname, 'u' AS usename, "
                "'active' AS state, 'enabled' AS query"
            ),
            timeout_ms=1111,
        )
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_processlist",
            template_name="disabled template",
            sql=(
                "SELECT 2 AS pid, 'postgres' AS datname, 'u' AS usename, "
                "'active' AS state, 'disabled' AS query"
            ),
            timeout_ms=2222,
            enabled=False,
        )
        mock_query.return_value = ResultSet(
            column_list=["pid", "datname", "usename", "state", "query"],
            rows=[(1, "postgres", "u", "active", "enabled")],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.processlist(command_type="All")

        self.assertIsNone(result.error)
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["max_execution_time"], 1111)
        self.assertIn("enabled", call_kwargs["sql"])
        self.assertNotIn("disabled", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_processlist_uses_custom_template_and_not_idle_replacement(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_processlist",
            template_name="process custom",
            sql="SELECT 1 AS pid, 'postgres' AS datname, 'u' AS usename, 'active' AS state, 'select 1' AS query WHERE 1=1 $state_not_idle$",
            db_name="archery",
            timeout_ms=4567,
        )
        mock_query.return_value = ResultSet(
            column_list=["pid", "datname", "usename", "state", "query"],
            rows=[(1, "postgres", "u", "active", "select 1")],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.processlist(command_type="Not Idle")

        self.assertIsNone(result.error)
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["db_name"], "archery")
        self.assertEqual(call_kwargs["max_execution_time"], 4567)
        self.assertIn("and psa.state<>'idle'", call_kwargs["sql"])
        self.assertNotIn("$state_not_idle$", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_dbdiagnostic_sql_reports_missing_required_columns(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_processlist",
            template_name="missing columns",
            sql="SELECT 1 AS pid",
        )
        mock_query.return_value = ResultSet(column_list=["pid"], rows=[(1,)])

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.processlist(command_type="All")

        self.assertEqual(
            result.error, "自定义SQL缺少必要输出字段：datname, usename, state, query"
        )

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_trxandlocks_uses_pgsql_diagnostic_sql(self, mock_query):
        mock_query.return_value = ResultSet(
            column_list=[
                "waiting_pid",
                "blocking_pid",
                "blocking_chain",
                "waiting_query",
                "blocking_query",
            ],
            rows=[(1, 2, "1 -> 2", "update t", "select t")],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.trxandlocks()

        self.assertIsNone(result.error)
        mock_query.assert_called_once()
        self.assertIn("WITH RECURSIVE lock_edges", mock_query.call_args.kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_pubsub_uses_pgsql_diagnostic_sql(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_pubsub",
            template_name="pubsub custom",
            sql="SELECT 'publication' AS object_type, 'pub1' AS object_name, 'true' AS enabled, 'u' AS owner_name, 'postgres' AS database_name",
            db_name="postgres",
            timeout_ms=2345,
        )
        mock_query.return_value = ResultSet(
            column_list=[
                "object_type",
                "object_name",
                "enabled",
                "owner_name",
                "database_name",
            ],
            rows=[("publication", "pub1", "true", "u", "postgres")],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.pubsub()

        self.assertIsNone(result.error)
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["db_name"], "postgres")
        self.assertEqual(call_kwargs["max_execution_time"], 2345)
        self.assertIn("pub1", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_replication_status_uses_pgsql_diagnostic_sql(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_replication",
            template_name="replication custom",
            sql="SELECT 1 AS pid, 'rep' AS usename, 'standby' AS application_name, '127.0.0.1' AS client_addr, 'streaming' AS state, 'async' AS sync_state",
            db_name="postgres",
            timeout_ms=2345,
        )
        mock_query.return_value = ResultSet(
            column_list=[
                "pid",
                "usename",
                "application_name",
                "client_addr",
                "state",
                "sync_state",
            ],
            rows=[(1, "rep", "standby", "127.0.0.1", "streaming", "async")],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.replication_status()

        self.assertIsNone(result.error)
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["db_name"], "postgres")
        self.assertEqual(call_kwargs["max_execution_time"], 2345)
        self.assertIn("standby", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_replication_slots_uses_pgsql_diagnostic_sql(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_replication_slots",
            template_name="slot custom",
            sql="SELECT 'slot1' AS slot_name, 'physical' AS slot_type, true AS active, '0/1' AS restart_lsn",
            db_name="postgres",
            timeout_ms=3456,
        )
        mock_query.return_value = ResultSet(
            column_list=["slot_name", "slot_type", "active", "restart_lsn"],
            rows=[("slot1", "physical", True, "0/1")],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.replication_slots()

        self.assertIsNone(result.error)
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["db_name"], "postgres")
        self.assertEqual(call_kwargs["max_execution_time"], 3456)
        self.assertIn("slot1", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_progress_status_uses_pgsql_diagnostic_sql(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_progress",
            template_name="progress custom",
            sql="SELECT 'vacuum' AS progress_type, 1 AS pid, 'postgres' AS database_name, 'public.t1' AS relation_name, 'scanning heap' AS phase, 50 AS progress_percent, 10 AS blocks_done, 20 AS blocks_total, 'vacuum public.t1' AS query",
            db_name="postgres",
            timeout_ms=4567,
        )
        mock_query.return_value = ResultSet(
            column_list=[
                "progress_type",
                "pid",
                "database_name",
                "relation_name",
                "phase",
                "progress_percent",
                "blocks_done",
                "blocks_total",
                "query",
            ],
            rows=[("vacuum", 1, "postgres", "public.t1", "scanning heap", 50, 10, 20, "vacuum public.t1")],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.progress_status()

        self.assertIsNone(result.error)
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["db_name"], "postgres")
        self.assertEqual(call_kwargs["max_execution_time"], 4567)
        self.assertIn("vacuum public.t1", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_wait_event_summary_uses_pgsql_diagnostic_sql(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_wait_events",
            template_name="wait custom",
            sql="SELECT 'active' AS state, 'Lock' AS wait_event_type, 'relation' AS wait_event, 2 AS session_count, 30 AS max_wait_seconds, 60 AS max_query_seconds",
            db_name="postgres",
            timeout_ms=5678,
        )
        mock_query.return_value = ResultSet(
            column_list=[
                "state",
                "wait_event_type",
                "wait_event",
                "session_count",
                "max_wait_seconds",
                "max_query_seconds",
            ],
            rows=[("active", "Lock", "relation", 2, 30, 60)],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.wait_event_summary()

        self.assertIsNone(result.error)
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["db_name"], "postgres")
        self.assertEqual(call_kwargs["max_execution_time"], 5678)
        self.assertIn("relation", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_extension_status_uses_pgsql_diagnostic_sql(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_extensions",
            template_name="extension custom",
            sql="SELECT 'pg_stat_statements' AS extension_name, true AS installed, '1.9' AS default_version, '1.9' AS installed_version",
            db_name="postgres",
            timeout_ms=6789,
        )
        mock_query.return_value = ResultSet(
            column_list=[
                "extension_name",
                "installed",
                "default_version",
                "installed_version",
            ],
            rows=[("pg_stat_statements", True, "1.9", "1.9")],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.extension_status()

        self.assertIsNone(result.error)
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["db_name"], "postgres")
        self.assertEqual(call_kwargs["max_execution_time"], 6789)
        self.assertIn("pg_stat_statements", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_extension_status_page_db_name_overrides_template_db_name(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_extensions",
            template_name="extension custom db",
            sql="SELECT 'pg_trgm' AS extension_name, true AS installed, '1.6' AS default_version, '1.6' AS installed_version",
            db_name="postgres",
            timeout_ms=6789,
        )
        mock_query.return_value = ResultSet(
            column_list=[
                "extension_name",
                "installed",
                "default_version",
                "installed_version",
            ],
            rows=[("pg_trgm", True, "1.6", "1.6")],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.extension_status(db_name="dynadot")

        self.assertIsNone(result.error)
        self.assertEqual(mock_query.call_args.kwargs["db_name"], "dynadot")

    def test_get_cancel_command_uses_pg_cancel_backend(self):
        new_engine = PgSQLEngine(instance=self.ins)

        self.assertEqual(
            new_engine.get_cancel_command([1, "2"]),
            "SELECT pg_cancel_backend(1);SELECT pg_cancel_backend(2);",
        )
        self.assertEqual(new_engine.get_cancel_command([]), "")
        self.assertIsNone(new_engine.get_cancel_command(["bad"]))

    def test_get_kill_command_uses_pg_terminate_backend(self):
        new_engine = PgSQLEngine(instance=self.ins)

        self.assertEqual(
            new_engine.get_kill_command([1, "2"]),
            "SELECT pg_terminate_backend(1);SELECT pg_terminate_backend(2);",
        )
        self.assertEqual(new_engine.get_kill_command([]), "")
        self.assertIsNone(new_engine.get_kill_command(["bad"]))

    @patch("sql.engines.pgsql.PgSQLEngine.get_connection")
    def test_cancel_backend_cancels_pgsql_backends(self, mock_get_connection):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.side_effect = [[(True,)], [(False,)]]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_connection.return_value = mock_conn

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.cancel_backend([1, "2"])

        self.assertIsNone(result.error)
        self.assertEqual(result.column_list, ["pg_cancel_backend"])
        self.assertEqual(result.rows, [(True,), (False,)])
        self.assertEqual(result.affected_rows, 2)
        self.assertEqual(
            result.full_sql,
            "SELECT pg_cancel_backend(1);SELECT pg_cancel_backend(2);",
        )
        mock_cursor.execute.assert_any_call("SELECT pg_cancel_backend(%s);", (1,))
        mock_cursor.execute.assert_any_call("SELECT pg_cancel_backend(%s);", (2,))
        mock_conn.commit.assert_called_once()

    @patch("sql.engines.pgsql.PgSQLEngine.get_connection")
    def test_kill_terminates_pgsql_backends(self, mock_get_connection):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [(True,)]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_connection.return_value = mock_conn

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.kill([3])

        self.assertIsNone(result.error)
        self.assertEqual(result.column_list, ["pg_terminate_backend"])
        self.assertEqual(result.rows, [(True,)])
        self.assertEqual(result.full_sql, "SELECT pg_terminate_backend(3);")
        mock_cursor.execute.assert_called_once_with(
            "SELECT pg_terminate_backend(%s);", (3,)
        )
        mock_conn.commit.assert_called_once()

    @patch("sql.engines.pgsql.PgSQLEngine.get_connection")
    def test_kill_rejects_invalid_pgsql_pid(self, mock_get_connection):
        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.kill(["bad"])

        self.assertEqual(result.full_sql, "")
        self.assertEqual(result.rows, [])
        mock_get_connection.assert_not_called()

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_get_long_transaction_queries_pg_stat_activity(self, mock_query):
        mock_query.return_value = ResultSet(
            column_list=["pid", "datname", "usename", "state", "xact_start", "query"],
            rows=[],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.get_long_transaction()

        self.assertIsInstance(result, ResultSet)
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["db_name"], "postgres")
        self.assertEqual(call_kwargs["max_execution_time"], 3000)
        self.assertIn("pg_stat_activity", call_kwargs["sql"])
        self.assertIn("transaction_duration_seconds", call_kwargs["sql"])
        self.assertIn("make_interval(secs => 3)", call_kwargs["sql"])
        self.assertNotIn("$thread_time$", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_get_long_transaction_uses_custom_template(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_trx",
            template_name="trx custom",
            sql="SELECT 1 AS pid, 'postgres' AS datname, 'u' AS usename, 'idle in transaction' AS state, now() AS xact_start, 'select 1' AS query WHERE $thread_time$ = 9",
            db_name="postgres",
            timeout_ms=4567,
        )
        mock_query.return_value = ResultSet(
            column_list=["pid", "datname", "usename", "state", "xact_start", "query"],
            rows=[(1, "postgres", "u", "idle in transaction", "now", "select 1")],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.get_long_transaction(thread_time=9)

        self.assertIsNone(result.error)
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["db_name"], "postgres")
        self.assertEqual(call_kwargs["max_execution_time"], 4567)
        self.assertIn("WHERE 9 = 9", call_kwargs["sql"])
        self.assertNotIn("$thread_time$", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_tablespace_uses_pgsql_diagnostic_sql(self, mock_query):
        mock_query.return_value = ResultSet(
            column_list=[
                "schema_name",
                "table_name",
                "total_size_bytes",
                "total_size",
            ],
            rows=[("public", "t1", 1024, "1024 bytes")],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.tablespace(offset=5, row_count=10, schema_name="public")

        self.assertIsNone(result.error)
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["db_name"], "postgres")
        self.assertEqual(call_kwargs["max_execution_time"], 3000)
        self.assertIn("pg_total_relation_size", call_kwargs["sql"])
        self.assertIn("LIMIT 10 OFFSET 5", call_kwargs["sql"])
        self.assertIn("'public' = '' OR namespace.nspname = 'public'", call_kwargs["sql"])
        self.assertNotIn("$limit$", call_kwargs["sql"])
        self.assertNotIn("$offset$", call_kwargs["sql"])
        self.assertNotIn("$schema_name$", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_tablespace_uses_custom_template(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_tablespace",
            template_name="tablespace custom",
            sql="SELECT 'public' AS schema_name, 't1' AS table_name, 1 AS total_size_bytes, '1 byte' AS total_size WHERE $schema_name$ = 'public' LIMIT $limit$ OFFSET $offset$",
            db_name="postgres",
            timeout_ms=4567,
        )
        mock_query.return_value = ResultSet(
            column_list=[
                "schema_name",
                "table_name",
                "total_size_bytes",
                "total_size",
            ],
            rows=[("public", "t1", 1, "1 byte")],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.tablespace(offset=2, row_count=3, schema_name="public")

        self.assertIsNone(result.error)
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["max_execution_time"], 4567)
        self.assertIn("WHERE 'public' = 'public'", call_kwargs["sql"])
        self.assertIn("LIMIT 3 OFFSET 2", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_tablespace_page_db_name_overrides_template_db_name(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_tablespace",
            template_name="tablespace custom db",
            sql="SELECT 'public' AS schema_name, 't1' AS table_name, 1 AS total_size_bytes, '1 byte' AS total_size LIMIT $limit$ OFFSET $offset$",
            db_name="postgres",
            timeout_ms=4567,
        )
        mock_query.return_value = ResultSet(
            column_list=[
                "schema_name",
                "table_name",
                "total_size_bytes",
                "total_size",
            ],
            rows=[("public", "t1", 1, "1 byte")],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.tablespace(offset=0, row_count=3, db_name="dynadot")

        self.assertIsNone(result.error)
        self.assertEqual(mock_query.call_args.kwargs["db_name"], "dynadot")

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_tablespace_count_page_db_name_overrides_template_db_name(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_tablespace",
            template_name="tablespace count custom db",
            sql="SELECT 'public' AS schema_name, 't1' AS table_name, 1 AS total_size_bytes, '1 byte' AS total_size LIMIT $limit$ OFFSET $offset$",
            db_name="postgres",
            timeout_ms=4567,
        )
        mock_query.return_value = ResultSet(column_list=["total"], rows=[(1,)])

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.tablespace_count(db_name="dynadot")

        self.assertIsNone(result.error)
        self.assertEqual(mock_query.call_args.kwargs["db_name"], "dynadot")

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_tablespace_rejects_invalid_schema_name(self, mock_query):
        new_engine = PgSQLEngine(instance=self.ins)

        result = new_engine.tablespace(schema_name="public';drop table x;--")

        self.assertEqual(
            result.error, "Schema名称只允许字母、数字、下划线、点、美元符号和短横线"
        )
        mock_query.assert_not_called()

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_tablespace_count_wraps_tablespace_sql(self, mock_query):
        mock_query.return_value = ResultSet(column_list=["total"], rows=[(1,)])

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.tablespace_count(schema_name="public")

        self.assertIsNone(result.error)
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["db_name"], "postgres")
        self.assertIn("SELECT count(*) AS total FROM", call_kwargs["sql"])
        self.assertIn("dbdiagnostic_tablespace_count", call_kwargs["sql"])
        self.assertIn("'public' = '' OR namespace.nspname = 'public'", call_kwargs["sql"])
        self.assertNotIn("$schema_name$", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_vacuum_risk_uses_pgsql_diagnostic_sql(self, mock_query):
        mock_query.return_value = ResultSet(
            column_list=[
                "schema_name",
                "table_name",
                "n_live_tup",
                "n_dead_tup",
                "dead_tuple_ratio",
                "relfrozenxid_age",
            ],
            rows=[("public", "t1", 10, 2, 16.67, 1000)],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.vacuum_risk(offset=5, row_count=10, schema_name="public")

        self.assertIsNone(result.error)
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["db_name"], "postgres")
        self.assertEqual(call_kwargs["max_execution_time"], 3000)
        self.assertIn("pg_stat_user_tables", call_kwargs["sql"])
        self.assertIn("LIMIT 10 OFFSET 5", call_kwargs["sql"])
        self.assertIn("'public' = '' OR namespace.nspname = 'public'", call_kwargs["sql"])
        self.assertNotIn("$limit$", call_kwargs["sql"])
        self.assertNotIn("$offset$", call_kwargs["sql"])
        self.assertNotIn("$schema_name$", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_vacuum_risk_uses_custom_template(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_vacuum",
            template_name="vacuum custom",
            sql="SELECT 'public' AS schema_name, 't1' AS table_name, 10 AS n_live_tup, 2 AS n_dead_tup, 16.67 AS dead_tuple_ratio, 1000 AS relfrozenxid_age WHERE $schema_name$ = 'public' LIMIT $limit$ OFFSET $offset$",
            db_name="postgres",
            timeout_ms=4567,
        )
        mock_query.return_value = ResultSet(
            column_list=[
                "schema_name",
                "table_name",
                "n_live_tup",
                "n_dead_tup",
                "dead_tuple_ratio",
                "relfrozenxid_age",
            ],
            rows=[("public", "t1", 10, 2, 16.67, 1000)],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.vacuum_risk(offset=2, row_count=3, schema_name="public")

        self.assertIsNone(result.error)
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["max_execution_time"], 4567)
        self.assertIn("WHERE 'public' = 'public'", call_kwargs["sql"])
        self.assertIn("LIMIT 3 OFFSET 2", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_vacuum_risk_page_db_name_overrides_template_db_name(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_vacuum",
            template_name="vacuum custom db",
            sql="SELECT 'public' AS schema_name, 't1' AS table_name, 10 AS n_live_tup, 2 AS n_dead_tup, 16.67 AS dead_tuple_ratio, 1000 AS relfrozenxid_age LIMIT $limit$ OFFSET $offset$",
            db_name="postgres",
            timeout_ms=4567,
        )
        mock_query.return_value = ResultSet(
            column_list=[
                "schema_name",
                "table_name",
                "n_live_tup",
                "n_dead_tup",
                "dead_tuple_ratio",
                "relfrozenxid_age",
            ],
            rows=[("public", "t1", 10, 2, 16.67, 1000)],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.vacuum_risk(offset=0, row_count=3, db_name="dynadot")

        self.assertIsNone(result.error)
        self.assertEqual(mock_query.call_args.kwargs["db_name"], "dynadot")

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_vacuum_risk_count_page_db_name_overrides_template_db_name(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_vacuum",
            template_name="vacuum count custom db",
            sql="SELECT 'public' AS schema_name, 't1' AS table_name, 10 AS n_live_tup, 2 AS n_dead_tup, 16.67 AS dead_tuple_ratio, 1000 AS relfrozenxid_age LIMIT $limit$ OFFSET $offset$",
            db_name="postgres",
            timeout_ms=4567,
        )
        mock_query.return_value = ResultSet(column_list=["total"], rows=[(1,)])

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.vacuum_risk_count(db_name="dynadot")

        self.assertIsNone(result.error)
        self.assertEqual(mock_query.call_args.kwargs["db_name"], "dynadot")

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_vacuum_risk_rejects_invalid_schema_name(self, mock_query):
        new_engine = PgSQLEngine(instance=self.ins)

        result = new_engine.vacuum_risk(schema_name="public';drop table x;--")

        self.assertEqual(
            result.error, "Schema名称只允许字母、数字、下划线、点、美元符号和短横线"
        )
        mock_query.assert_not_called()

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_vacuum_risk_count_wraps_vacuum_sql(self, mock_query):
        mock_query.return_value = ResultSet(column_list=["total"], rows=[(1,)])

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.vacuum_risk_count(schema_name="public")

        self.assertIsNone(result.error)
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["db_name"], "postgres")
        self.assertIn("SELECT count(*) AS total FROM", call_kwargs["sql"])
        self.assertIn("dbdiagnostic_vacuum_count", call_kwargs["sql"])
        self.assertIn("'public' = '' OR namespace.nspname = 'public'", call_kwargs["sql"])
        self.assertNotIn("$schema_name$", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_index_diagnostic_uses_pgsql_diagnostic_sql(self, mock_query):
        mock_query.return_value = ResultSet(
            column_list=[
                "diagnostic_type",
                "schema_name",
                "table_name",
                "index_name",
                "index_size",
                "idx_scan",
                "seq_scan",
                "is_valid",
                "is_unique",
                "reason",
            ],
            rows=[("unused_index", "public", "t1", "idx_t1", "1 MB", 0, 10, True, False, "unused")],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.index_diagnostic(offset=5, row_count=10, schema_name="public")

        self.assertIsNone(result.error)
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["db_name"], "postgres")
        self.assertEqual(call_kwargs["max_execution_time"], 3000)
        self.assertIn("pg_stat_user_indexes", call_kwargs["sql"])
        self.assertIn("LIMIT 10 OFFSET 5", call_kwargs["sql"])
        self.assertIn("'public' = '' OR namespace.nspname = 'public'", call_kwargs["sql"])
        self.assertNotIn("$limit$", call_kwargs["sql"])
        self.assertNotIn("$offset$", call_kwargs["sql"])
        self.assertNotIn("$schema_name$", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_index_diagnostic_uses_custom_template(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_indexes",
            template_name="indexes custom",
            sql="SELECT 'unused_index' AS diagnostic_type, 'public' AS schema_name, 't1' AS table_name, 'idx_t1' AS index_name, '1 MB' AS index_size, 0 AS idx_scan, 10 AS seq_scan, true AS is_valid, false AS is_unique, 'unused' AS reason WHERE $schema_name$ = 'public' LIMIT $limit$ OFFSET $offset$",
            db_name="postgres",
            timeout_ms=4567,
        )
        mock_query.return_value = ResultSet(
            column_list=[
                "diagnostic_type",
                "schema_name",
                "table_name",
                "index_name",
                "index_size",
                "idx_scan",
                "seq_scan",
                "is_valid",
                "is_unique",
                "reason",
            ],
            rows=[("unused_index", "public", "t1", "idx_t1", "1 MB", 0, 10, True, False, "unused")],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.index_diagnostic(offset=2, row_count=3, schema_name="public")

        self.assertIsNone(result.error)
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["max_execution_time"], 4567)
        self.assertIn("WHERE 'public' = 'public'", call_kwargs["sql"])
        self.assertIn("LIMIT 3 OFFSET 2", call_kwargs["sql"])

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_index_diagnostic_page_db_name_overrides_template_db_name(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_indexes",
            template_name="indexes custom db",
            sql="SELECT 'unused_index' AS diagnostic_type, 'public' AS schema_name, 't1' AS table_name, 'idx_t1' AS index_name, '1 MB' AS index_size, 0 AS idx_scan, 10 AS seq_scan, true AS is_valid, false AS is_unique, 'unused' AS reason LIMIT $limit$ OFFSET $offset$",
            db_name="postgres",
            timeout_ms=4567,
        )
        mock_query.return_value = ResultSet(
            column_list=[
                "diagnostic_type",
                "schema_name",
                "table_name",
                "index_name",
                "index_size",
                "idx_scan",
                "seq_scan",
                "is_valid",
                "is_unique",
                "reason",
            ],
            rows=[("unused_index", "public", "t1", "idx_t1", "1 MB", 0, 10, True, False, "unused")],
        )

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.index_diagnostic(offset=0, row_count=3, db_name="dynadot")

        self.assertIsNone(result.error)
        self.assertEqual(mock_query.call_args.kwargs["db_name"], "dynadot")

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_index_diagnostic_count_page_db_name_overrides_template_db_name(self, mock_query):
        DBDiagnosticSQLTemplate.objects.create(
            db_type="pgsql",
            diagnostic_type="pgsql_indexes",
            template_name="indexes count custom db",
            sql="SELECT 'unused_index' AS diagnostic_type, 'public' AS schema_name, 't1' AS table_name, 'idx_t1' AS index_name, '1 MB' AS index_size, 0 AS idx_scan, 10 AS seq_scan, true AS is_valid, false AS is_unique, 'unused' AS reason LIMIT $limit$ OFFSET $offset$",
            db_name="postgres",
            timeout_ms=4567,
        )
        mock_query.return_value = ResultSet(column_list=["total"], rows=[(1,)])

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.index_diagnostic_count(db_name="dynadot")

        self.assertIsNone(result.error)
        self.assertEqual(mock_query.call_args.kwargs["db_name"], "dynadot")

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_index_diagnostic_rejects_invalid_schema_name(self, mock_query):
        new_engine = PgSQLEngine(instance=self.ins)

        result = new_engine.index_diagnostic(schema_name="public';drop table x;--")

        self.assertEqual(
            result.error, "Schema名称只允许字母、数字、下划线、点、美元符号和短横线"
        )
        mock_query.assert_not_called()

    @patch("sql.engines.pgsql.PgSQLEngine.query")
    def test_index_diagnostic_count_wraps_index_sql(self, mock_query):
        mock_query.return_value = ResultSet(column_list=["total"], rows=[(1,)])

        new_engine = PgSQLEngine(instance=self.ins)
        result = new_engine.index_diagnostic_count(schema_name="public")

        self.assertIsNone(result.error)
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args.kwargs
        self.assertEqual(call_kwargs["db_name"], "postgres")
        self.assertIn("SELECT count(*) AS total FROM", call_kwargs["sql"])
        self.assertIn("dbdiagnostic_indexes_count", call_kwargs["sql"])
        self.assertIn("'public' = '' OR namespace.nspname = 'public'", call_kwargs["sql"])
        self.assertNotIn("$schema_name$", call_kwargs["sql"])

    @patch("psycopg2.connect")
    def test_processlist_not_idle(self, mock_connect):
        # 模拟数据库连接和游标
        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor

        # 假设 query 方法返回的结果
        mock_cursor.fetchall.return_value = [
            (123, "test_db", "user", "app_name", "active")
        ]

        # 创建 PgSQLEngine 实例
        new_engine = PgSQLEngine(instance=self.ins)

        # 调用 processlist 方法
        result = new_engine.processlist(command_type="Not Idle")
        self.assertEqual(result.rows, mock_cursor.fetchall.return_value)

    @patch("psycopg2.connect")
    def test_processlist_idle(self, mock_connect):
        # 模拟数据库连接和游标
        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor

        # 假设 query 方法返回的结果
        mock_cursor.fetchall.return_value = [
            (123, "test_db", "user", "app_name", "idle")
        ]
        # 创建 PgSQLEngine 实例
        new_engine = PgSQLEngine(instance=self.ins)
        # 调用 processlist 方法
        result = new_engine.processlist(command_type="Idle")
        self.assertEqual(result.rows, mock_cursor.fetchall.return_value)


class TestModel(TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_result_set_rows_shadow(self):
        # 测试默认值为空列表的坑
        # 如果默认值是空列表，又使用的是累加的方法更新，会导致残留上次的列表
        result_set1 = ResultSet()
        for i in range(10):
            result_set1.rows += [i]
        brand_new_result_set = ResultSet()
        self.assertEqual(brand_new_result_set.rows, [])

        review_set1 = ReviewSet()
        for i in range(10):
            review_set1.rows += [i]
        brand_new_review_set = ReviewSet()
        self.assertEqual(brand_new_review_set.rows, [])


class TestGoInception(TestCase):
    def setUp(self):
        self.ins = Instance.objects.create(
            instance_name="some_ins",
            type="slave",
            db_type="mysql",
            host="some_host",
            port=3306,
            user="ins_user",
            password="some_str",
        )
        self.ins_inc = Instance.objects.create(
            instance_name="some_ins_inc",
            type="slave",
            db_type="goinception",
            host="some_host",
            port=4000,
        )
        self.wf = SqlWorkflow.objects.create(
            workflow_name="some_name",
            group_id=1,
            group_name="g1",
            engineer_display="",
            audit_auth_groups="some_group",
            create_time=datetime.now() - timedelta(days=1),
            status="workflow_finish",
            is_backup=True,
            instance=self.ins,
            db_name="some_db",
            syntax_type=1,
        )
        SqlWorkflowContent.objects.create(workflow=self.wf)

    def tearDown(self):
        self.ins.delete()
        self.ins_inc.delete()
        SqlWorkflow.objects.all().delete()
        SqlWorkflowContent.objects.all().delete()

    @patch("MySQLdb.connect")
    def test_get_connection(self, _connect):
        new_engine = GoInceptionEngine()
        new_engine.get_connection()
        _connect.assert_called_once()

    @patch("sql.engines.goinception.GoInceptionEngine.query")
    def test_execute_check_normal_sql(self, _query):
        sql = "update user set id=100"
        row = [
            1,
            "CHECKED",
            0,
            "Audit completed",
            "None",
            "use archery",
            0,
            "'0_0_0'",
            "None",
            "0",
            "",
            "",
        ]
        _query.return_value = ResultSet(full_sql=sql, rows=[row])
        new_engine = GoInceptionEngine()
        check_result = new_engine.execute_check(instance=self.ins, db_name=0, sql=sql)
        self.assertIsInstance(check_result, ReviewSet)

    @patch("sql.engines.goinception.GoInceptionEngine.query")
    def test_execute_exception(self, _query):
        sql = "update user set id=100"
        row = [
            1,
            "CHECKED",
            1,
            "Execute failed",
            "None",
            "use archery",
            0,
            "'0_0_0'",
            "None",
            "0",
            "",
            "",
        ]
        column_list = [
            "order_id",
            "stage",
            "error_level",
            "stage_status",
            "error_message",
            "sql",
            "affected_rows",
            "sequence",
            "backup_dbname",
            "execute_time",
            "sqlsha1",
            "backup_time",
        ]
        _query.return_value = ResultSet(
            full_sql=sql, rows=[row], column_list=column_list
        )
        new_engine = GoInceptionEngine()
        execute_result = new_engine.execute(workflow=self.wf)
        self.assertIsInstance(execute_result, ReviewSet)

    @patch("sql.engines.goinception.GoInceptionEngine.query")
    def test_execute_finish(self, _query):
        sql = "update user set id=100"
        row = [
            1,
            "CHECKED",
            0,
            "Execute Successfully",
            "None",
            "use archery",
            0,
            "'0_0_0'",
            "None",
            "0",
            "",
            "",
        ]
        column_list = [
            "order_id",
            "stage",
            "error_level",
            "stage_status",
            "error_message",
            "sql",
            "affected_rows",
            "sequence",
            "backup_dbname",
            "execute_time",
            "sqlsha1",
            "backup_time",
        ]
        _query.return_value = ResultSet(
            full_sql=sql, rows=[row], column_list=column_list
        )
        new_engine = GoInceptionEngine()
        execute_result = new_engine.execute(workflow=self.wf)
        self.assertIsInstance(execute_result, ReviewSet)

    @patch("MySQLdb.connect.cursor.execute")
    @patch("MySQLdb.connect.cursor")
    @patch("MySQLdb.connect")
    def test_query(self, _conn, _cursor, _execute):
        _conn.return_value.cursor.return_value.fetchall.return_value = [(1,)]
        new_engine = GoInceptionEngine()
        query_result = new_engine.query(db_name=0, sql="select 1", limit_num=100)
        self.assertIsInstance(query_result, ResultSet)

    @patch("MySQLdb.connect.cursor.execute")
    @patch("MySQLdb.connect.cursor")
    @patch("MySQLdb.connect")
    def test_query_not_limit(self, _conn, _cursor, _execute):
        _conn.return_value.cursor.return_value.fetchall.return_value = [(1,)]
        new_engine = GoInceptionEngine(instance=self.ins)
        query_result = new_engine.query(db_name=0, sql="select 1", limit_num=0)
        self.assertIsInstance(query_result, ResultSet)

    @patch("sql.engines.goinception.GoInceptionEngine.query")
    def test_osc_get(self, _query):
        new_engine = GoInceptionEngine()
        command = "get"
        sqlsha1 = "xxxxx"
        sql = f"inception get osc_percent '{sqlsha1}';"
        _query.return_value = ResultSet(full_sql=sql, rows=[], column_list=[])
        new_engine.osc_control(sqlsha1=sqlsha1, command=command)
        _query.assert_called_once_with(sql=sql)

    @patch("sql.engines.goinception.GoInceptionEngine.query")
    def test_osc_pause(self, _query):
        new_engine = GoInceptionEngine()
        command = "pause"
        sqlsha1 = "xxxxx"
        sql = f"inception {command} osc '{sqlsha1}';"
        _query.return_value = ResultSet(full_sql=sql, rows=[], column_list=[])
        new_engine.osc_control(sqlsha1=sqlsha1, command=command)
        _query.assert_called_once_with(sql=sql)

    @patch("sql.engines.goinception.GoInceptionEngine.query")
    def test_osc_resume(self, _query):
        new_engine = GoInceptionEngine()
        command = "resume"
        sqlsha1 = "xxxxx"
        sql = f"inception {command} osc '{sqlsha1}';"
        _query.return_value = ResultSet(full_sql=sql, rows=[], column_list=[])
        new_engine.osc_control(sqlsha1=sqlsha1, command=command)
        _query.assert_called_once_with(sql=sql)

    @patch("sql.engines.goinception.GoInceptionEngine.query")
    def test_osc_kill(self, _query):
        new_engine = GoInceptionEngine()
        command = "kill"
        sqlsha1 = "xxxxx"
        sql = f"inception kill osc '{sqlsha1}';"
        _query.return_value = ResultSet(full_sql=sql, rows=[], column_list=[])
        new_engine.osc_control(sqlsha1=sqlsha1, command=command)
        _query.assert_called_once_with(sql=sql)

    @patch("sql.engines.goinception.GoInceptionEngine.query")
    def test_get_variables(self, _query):
        new_engine = GoInceptionEngine(instance=self.ins_inc)
        new_engine.get_variables()
        sql = f"inception get variables;"
        _query.assert_called_once_with(sql=sql)

    @patch("sql.engines.goinception.GoInceptionEngine.query")
    def test_get_variables_filter(self, _query):
        new_engine = GoInceptionEngine(instance=self.ins_inc)
        new_engine.get_variables(variables=["inception_osc_on"])
        sql = f"inception get variables like 'inception_osc_on';"
        _query.assert_called_once_with(sql=sql)

    @patch("sql.engines.goinception.GoInceptionEngine.query")
    def test_set_variable(self, _query):
        new_engine = GoInceptionEngine(instance=self.ins)
        new_engine.set_variable("inception_osc_on", "on")
        _query.assert_called_once_with(sql="inception set inception_osc_on=on;")


class TestOracle(TestCase):
    """Oracle 测试"""

    def setUp(self):
        self.ins = Instance.objects.create(
            instance_name="some_ins",
            type="slave",
            db_type="oracle",
            host="some_host",
            port=3306,
            user="ins_user",
            password="some_str",
            sid="some_id",
        )
        self.wf = SqlWorkflow.objects.create(
            workflow_name="some_name",
            group_id=1,
            group_name="g1",
            engineer_display="",
            audit_auth_groups="some_group",
            create_time=datetime.now() - timedelta(days=1),
            status="workflow_finish",
            is_backup=True,
            instance=self.ins,
            db_name="some_db",
            syntax_type=1,
        )
        SqlWorkflowContent.objects.create(workflow=self.wf)
        self.sys_config = SysConfig()

    def tearDown(self):
        self.ins.delete()
        self.sys_config.purge()
        SqlWorkflow.objects.all().delete()
        SqlWorkflowContent.objects.all().delete()

    @patch("cx_Oracle.makedsn")
    @patch("cx_Oracle.connect")
    def test_get_connection(self, _connect, _makedsn):
        # 填写 sid 测试
        new_engine = OracleEngine(self.ins)
        new_engine.get_connection()
        _connect.assert_called_once()
        _makedsn.assert_called_once()
        # 填写 service_name 测试
        _connect.reset_mock()
        _makedsn.reset_mock()
        self.ins.service_name = "some_service"
        self.ins.sid = ""
        self.ins.save()
        new_engine = OracleEngine(self.ins)
        new_engine.get_connection()
        _connect.assert_called_once()
        _makedsn.assert_called_once()
        # 都不填写, 检测 ValueError
        _connect.reset_mock()
        _makedsn.reset_mock()
        self.ins.service_name = ""
        self.ins.sid = ""
        self.ins.save()
        new_engine = OracleEngine(self.ins)
        with self.assertRaises(ValueError):
            new_engine.get_connection()

    @patch("cx_Oracle.connect")
    def test_engine_base_info(self, _conn):
        new_engine = OracleEngine(instance=self.ins)
        self.assertEqual(new_engine.name, "Oracle")
        self.assertEqual(new_engine.info, "Oracle engine")
        _conn.return_value.version = "12.1.0.2.0"
        self.assertTupleEqual(new_engine.server_version, ("12", "1", "0"))

    @patch("cx_Oracle.connect.cursor.execute")
    @patch("cx_Oracle.connect.cursor")
    @patch("cx_Oracle.connect")
    def test_query(self, _conn, _cursor, _execute):
        _conn.return_value.cursor.return_value.fetchmany.return_value = [(1,)]
        new_engine = OracleEngine(instance=self.ins)
        query_result = new_engine.query(
            db_name="archery", sql="select 1", limit_num=100
        )
        self.assertIsInstance(query_result, ResultSet)
        self.assertListEqual(query_result.rows, [(1,)])

    @patch("cx_Oracle.connect.cursor.execute")
    @patch("cx_Oracle.connect.cursor")
    @patch("cx_Oracle.connect")
    def test_query_not_limit(self, _conn, _cursor, _execute):
        _conn.return_value.cursor.return_value.fetchall.return_value = [(1,)]
        new_engine = OracleEngine(instance=self.ins)
        query_result = new_engine.query(db_name=0, sql="select 1", limit_num=0)
        self.assertIsInstance(query_result, ResultSet)
        self.assertListEqual(query_result.rows, [(1,)])

    @patch(
        "sql.engines.oracle.OracleEngine.query",
        return_value=ResultSet(rows=[("AUD_SYS",), ("archery",), ("ANONYMOUS",)]),
    )
    def test_get_all_databases(self, _query):
        new_engine = OracleEngine(instance=self.ins)
        dbs = new_engine.get_all_databases()
        self.assertListEqual(dbs.rows, ["archery"])

    @patch(
        "sql.engines.oracle.OracleEngine.query",
        return_value=ResultSet(rows=[("AUD_SYS",), ("archery",), ("ANONYMOUS",)]),
    )
    def test__get_all_databases(self, _query):
        new_engine = OracleEngine(instance=self.ins)
        dbs = new_engine._get_all_databases()
        self.assertListEqual(dbs.rows, ["AUD_SYS", "archery", "ANONYMOUS"])

    @patch(
        "sql.engines.oracle.OracleEngine.query",
        return_value=ResultSet(rows=[("archery",)]),
    )
    def test__get_all_instances(self, _query):
        new_engine = OracleEngine(instance=self.ins)
        dbs = new_engine._get_all_instances()
        self.assertListEqual(dbs.rows, ["archery"])

    @patch(
        "sql.engines.oracle.OracleEngine.query",
        return_value=ResultSet(rows=[("ANONYMOUS",), ("archery",), ("SYSTEM",)]),
    )
    def test_get_all_schemas(self, _query):
        new_engine = OracleEngine(instance=self.ins)
        schemas = new_engine._get_all_schemas()
        self.assertListEqual(schemas.rows, ["archery"])

    @patch(
        "sql.engines.oracle.OracleEngine.query",
        return_value=ResultSet(rows=[("test",), ("test2",)]),
    )
    def test_get_all_tables(self, _query):
        new_engine = OracleEngine(instance=self.ins)
        tables = new_engine.get_all_tables(db_name="archery")
        self.assertListEqual(tables.rows, ["test2"])

    @patch(
        "sql.engines.oracle.OracleEngine.query",
        return_value=ResultSet(rows=[("id",), ("name",)]),
    )
    def test_get_all_columns_by_tb(self, _query):
        new_engine = OracleEngine(instance=self.ins)
        columns = new_engine.get_all_columns_by_tb(db_name="archery", tb_name="test2")
        self.assertListEqual(columns.rows, ["id", "name"])

    @patch(
        "sql.engines.oracle.OracleEngine.query",
        return_value=ResultSet(rows=[("archery",), ("template1",), ("template0",)]),
    )
    def test_describe_table(self, _query):
        new_engine = OracleEngine(instance=self.ins)
        describe = new_engine.describe_table(db_name="archery", tb_name="text")
        self.assertIsInstance(describe, ResultSet)

    def test_query_check_disable_sql(self):
        sql = "update xxx set a=1;"
        new_engine = OracleEngine(instance=self.ins)
        check_result = new_engine.query_check(db_name="archery", sql=sql)
        self.assertDictEqual(
            check_result,
            {
                "msg": "不支持语法!",
                "bad_query": True,
                "filtered_sql": sql.strip(";"),
                "has_star": False,
            },
        )

    @patch(
        "sql.engines.oracle.OracleEngine.explain_check",
        return_value={"msg": "", "rows": 0},
    )
    def test_query_check_star_sql(self, _explain_check):
        sql = "select * from xx;"
        new_engine = OracleEngine(instance=self.ins)
        check_result = new_engine.query_check(db_name="archery", sql=sql)
        self.assertDictEqual(
            check_result,
            {
                "msg": "禁止使用 * 关键词\n",
                "bad_query": False,
                "filtered_sql": sql.strip(";"),
                "has_star": True,
            },
        )

    def test_query_check_IndexError(self):
        sql = ""
        new_engine = OracleEngine(instance=self.ins)
        check_result = new_engine.query_check(db_name="archery", sql=sql)
        self.assertDictEqual(
            check_result,
            {
                "msg": "没有有效的SQL语句",
                "bad_query": True,
                "filtered_sql": sql.strip(),
                "has_star": False,
            },
        )

    def test_query_masking(self):
        query_result = ResultSet()
        new_engine = OracleEngine(instance=self.ins)
        masking_result = new_engine.query_masking(
            sql="select 1 from dual", resultset=query_result
        )
        self.assertEqual(masking_result, query_result)

    def test_execute_check_select_sql(self):
        sql = "select * from user;"
        row = ReviewResult(
            id=1,
            errlevel=2,
            stagestatus="驳回不支持语句",
            errormessage="仅支持DML和DDL语句，查询语句请使用SQL查询功能！",
            sql=sqlparse.format(
                sql, strip_comments=True, reindent=True, keyword_case="lower"
            ),
        )
        new_engine = OracleEngine(instance=self.ins)
        check_result = new_engine.execute_check(db_name="archery", sql=sql)
        self.assertIsInstance(check_result, ReviewSet)
        self.assertEqual(check_result.rows[0].__dict__, row.__dict__)

    def test_execute_check_critical_sql(self):
        self.sys_config.set("critical_ddl_regex", "^|update")
        self.sys_config.get_all_config()
        sql = "update user set id=1"
        row = ReviewResult(
            id=1,
            errlevel=2,
            stagestatus="驳回高危SQL",
            errormessage="禁止提交匹配" + "^|update" + "条件的语句！",
            sql=sqlparse.format(
                sql, strip_comments=True, reindent=True, keyword_case="lower"
            ),
        )
        new_engine = OracleEngine(instance=self.ins)
        check_result = new_engine.execute_check(db_name="archery", sql=sql)
        self.assertIsInstance(check_result, ReviewSet)
        self.assertEqual(check_result.rows[0].__dict__, row.__dict__)

    @patch(
        "sql.engines.oracle.OracleEngine.explain_check",
        return_value={"msg": "", "rows": 0},
    )
    @patch(
        "sql.engines.oracle.OracleEngine.get_sql_first_object_name", return_value="tb"
    )
    @patch("sql.engines.oracle.OracleEngine.object_name_check", return_value=True)
    def test_execute_check_normal_sql(
        self, _explain_check, _get_sql_first_object_name, _object_name_check
    ):
        self.sys_config.purge()
        sql = "alter table tb set id=1"
        row = ReviewResult(
            id=1,
            errlevel=1,
            stagestatus="当前平台，此语法不支持审核！",
            errormessage="当前平台，此语法不支持审核！",
            sql=sqlparse.format(
                sql, strip_comments=True, reindent=True, keyword_case="lower"
            ),
            affected_rows=0,
            execute_time=0,
            stmt_type="SQL",
            object_owner="",
            object_type="",
            object_name="",
        )
        new_engine = OracleEngine(instance=self.ins)
        check_result = new_engine.execute_check(db_name="archery", sql=sql)
        self.assertIsInstance(check_result, ReviewSet)
        self.assertEqual(check_result.rows[0].__dict__, row.__dict__)

    def test_get_sql_first_object_name(self):
        """
        测试获取sql文本中的object_name
        :return:
        """
        new_engine = OracleEngine(instance=self.ins)
        sql = """create or replace procedure INSERTUSER
(id IN NUMBER,    
name IN VARCHAR2)    
is    
begin    
    insert into user1 values(id,name);
end;"""
        object_name = new_engine.get_sql_first_object_name(sql)
        self.assertEqual(object_name, "INSERTUSER")

    @patch(
        "sql.engines.oracle.OracleEngine.get_sql_first_object_name",
        return_value="INSERTUSER",
    )
    @patch("sql.engines.oracle.OracleEngine.object_name_check", return_value=True)
    def test_execute_check_replace_exist_plsql_object(
        self, _get_sql_first_object_name, _object_name_check
    ):
        sql = """create or replace procedure INSERTUSER
(id IN NUMBER,    
name IN VARCHAR2)    
is    
begin    
    insert into user1 values(id,name);    
end;"""
        row = ReviewResult(
            id=1,
            errlevel=1,
            stagestatus=""""TRADE".INSERTUSER对象已经存在，请确认是否替换！""",
            errormessage=""""TRADE".INSERTUSER对象已经存在，请确认是否替换！""",
            sql=sqlparse.format(
                sql, strip_comments=True, reindent=True, keyword_case="lower"
            ),
            affected_rows=0,
            execute_time=0,
            stmt_type="SQL",
            object_owner="",
            object_type="",
            object_name="",
        )
        new_engine = OracleEngine(instance=self.ins)
        check_result = new_engine.execute_check(db_name="TRADE", sql=sql)
        self.assertIsInstance(check_result, ReviewSet)
        self.assertEqual(check_result.rows[0].__dict__, row.__dict__)

    @patch(
        "sql.engines.oracle.OracleEngine.get_sql_first_object_name",
        return_value="INSERTUSER",
    )
    @patch("sql.engines.oracle.OracleEngine.object_name_check", return_value=True)
    def test_execute_check_exist_plsql_object(
        self, _get_sql_first_object_name, _object_name_check
    ):
        sql = """create procedure INSERTUSER
(id IN NUMBER,    
name IN VARCHAR2)    
is    
begin    
    insert into user1 values(id,name);    
end;"""
        row = ReviewResult(
            id=1,
            errlevel=2,
            stagestatus=""""TRADE".INSERTUSER对象已经存在！""",
            errormessage=""""TRADE".INSERTUSER对象已经存在！""",
            sql=sqlparse.format(
                sql, strip_comments=True, reindent=True, keyword_case="lower"
            ),
        )
        new_engine = OracleEngine(instance=self.ins)
        check_result = new_engine.execute_check(db_name="TRADE", sql=sql)
        self.assertIsInstance(check_result, ReviewSet)
        self.assertEqual(check_result.rows[0].__dict__, row.__dict__)

    @patch("cx_Oracle.connect.cursor.execute")
    @patch("cx_Oracle.connect.cursor")
    @patch("cx_Oracle.connect")
    def test_execute_workflow_success(self, _conn, _cursor, _execute):
        sql = "update user set id=1"
        review_row = ReviewResult(
            id=1,
            errlevel=0,
            stagestatus="Execute Successfully",
            errormessage="None",
            sql=sql,
            affected_rows=0,
            execute_time=0,
            stmt_type="SQL",
            object_owner="",
            object_type="",
            object_name="",
        )
        execute_row = ReviewResult(
            id=1,
            errlevel=0,
            stagestatus="Execute Successfully",
            errormessage="None",
            sql=sql,
            affected_rows=0,
            execute_time=0,
        )
        wf = SqlWorkflow.objects.create(
            workflow_name="some_name",
            group_id=1,
            group_name="g1",
            engineer_display="",
            audit_auth_groups="some_group",
            create_time=datetime.now() - timedelta(days=1),
            status="workflow_finish",
            is_backup=True,
            instance=self.ins,
            db_name="some_db",
            syntax_type=1,
        )
        SqlWorkflowContent.objects.create(
            workflow=wf,
            sql_content=sql,
            review_content=ReviewSet(rows=[review_row]).json(),
        )
        new_engine = OracleEngine(instance=self.ins)
        execute_result = new_engine.execute_workflow(workflow=wf)
        self.assertIsInstance(execute_result, ReviewSet)
        self.assertEqual(
            execute_result.rows[0].__dict__.keys(), execute_row.__dict__.keys()
        )

    @patch("cx_Oracle.connect.cursor.execute")
    @patch("cx_Oracle.connect.cursor")
    @patch("cx_Oracle.connect", return_value=RuntimeError)
    def test_execute_workflow_exception(self, _conn, _cursor, _execute):
        sql = "update user set id=1"
        row = ReviewResult(
            id=1,
            errlevel=2,
            stagestatus="Execute Failed",
            errormessage=f'异常信息：{f"Oracle命令执行报错，语句：{sql}"}',
            sql=sql,
            affected_rows=0,
            execute_time=0,
            stmt_type="SQL",
            object_owner="",
            object_type="",
            object_name="",
        )
        wf = SqlWorkflow.objects.create(
            workflow_name="some_name",
            group_id=1,
            group_name="g1",
            engineer_display="",
            audit_auth_groups="some_group",
            create_time=datetime.now() - timedelta(days=1),
            status="workflow_finish",
            is_backup=True,
            instance=self.ins,
            db_name="some_db",
            syntax_type=1,
        )
        SqlWorkflowContent.objects.create(
            workflow=wf, sql_content=sql, review_content=ReviewSet(rows=[row]).json()
        )
        with self.assertRaises(AttributeError):
            new_engine = OracleEngine(instance=self.ins)
            execute_result = new_engine.execute_workflow(workflow=wf)
            self.assertIsInstance(execute_result, ReviewSet)
            self.assertEqual(
                execute_result.rows[0].__dict__.keys(), row.__dict__.keys()
            )

    @patch("cx_Oracle.connect.cursor.execute")
    @patch("cx_Oracle.connect.cursor")
    @patch("cx_Oracle.connect")
    def test_execute(self, _connect, _cursor, _execute):
        new_engine = OracleEngine(instance=self.ins)
        sql = "update abc set count=1 where id=1;"
        execute_result = new_engine.execute(sql)
        self.assertIsInstance(execute_result, ResultSet)

    @patch("sql.engines.oracle.OracleEngine.query")
    def test_processlist(self, _query):
        new_engine = OracleEngine(instance=self.ins)
        _query.return_value = ResultSet()
        for command_type in ["All", "Active", "Others"]:
            r = new_engine.processlist(command_type)
            self.assertIsInstance(r, ResultSet)

    @patch("sql.engines.oracle.OracleEngine.query")
    def test_get_kill_command(self, _query):
        new_engine = OracleEngine(instance=self.ins)
        _query.return_value.rows = (
            ("alter system kill session '12,123';",),
            ("alter system kill session '34,345';",),
        )
        r = new_engine.get_kill_command([[12, 123], [34, 345]])
        self.assertEqual(
            r, "alter system kill session '12,123';alter system kill session '34,345';"
        )

    @patch("sql.engines.oracle.OracleEngine.query")
    @patch("cx_Oracle.connect.cursor.execute")
    @patch("cx_Oracle.connect.cursor")
    @patch("cx_Oracle.connect")
    def test_kill_session(self, _query, _connect, _cursor, _execute):
        new_engine = OracleEngine(instance=self.ins)
        _query.return_value.rows = (
            ("alter system kill session '12,123';",),
            ("alter system kill session '34,345';",),
        )
        _execute.return_value = ResultSet()
        r = new_engine.kill_session([[12, 123], [34, 345]])
        self.assertIsInstance(r, ResultSet)

    @patch("sql.engines.oracle.OracleEngine.query")
    def test_tablespace(self, _query):
        new_engine = OracleEngine(instance=self.ins)
        _query.return_value = ResultSet()
        r = new_engine.tablespace()
        self.assertIsInstance(r, ResultSet)

    @patch("sql.engines.oracle.OracleEngine.query")
    def test_tablespace_count(self, _query):
        new_engine = OracleEngine(instance=self.ins)
        _query.return_value = ResultSet()
        r = new_engine.tablespace_count()
        self.assertIsInstance(r, ResultSet)

    @patch("sql.engines.oracle.OracleEngine.query")
    def test_lock_info(self, _query):
        new_engine = OracleEngine(instance=self.ins)
        _query.return_value = ResultSet()
        r = new_engine.lock_info()
        self.assertIsInstance(r, ResultSet)

    @patch("sql.engines.oracle.OracleEngine.query")
    def test_get_table_desc_data(self, _query):
        """测试获取表格字段信息方法"""
        new_engine = OracleEngine(instance=self.ins)

        # 模拟查询返回结果
        mock_result = ResultSet()
        mock_result.column_list = [
            "列名",
            "列注释",
            "字段类型",
            "字段默认值",
            "是否为空",
            "所属索引",
            "约束类型",
        ]
        mock_result.rows = [
            ("ID", "主键ID", "NUMBER(10)", "1", " NOT NULL", "PK_USER", "P")
        ]
        _query.return_value = mock_result

        # 调用被测试方法
        result = new_engine.get_table_desc_data(db_name="TEST_SCHEMA", tb_name="USERS")

        # 验证结果结构
        self.assertIsInstance(result, dict)
        self.assertIn("column_list", result)
        self.assertIn("rows", result)
        self.assertIsInstance(result["column_list"], list)
        self.assertIsInstance(result["rows"], list)

        # 验证query方法被正确调用
        _query.assert_called_once()

    @patch("sql.engines.oracle.OracleEngine.query")
    def test_get_table_index_data(self, _query):
        """测试获取表格索引信息方法"""
        new_engine = OracleEngine(instance=self.ins)

        # 模拟查询返回结果
        mock_result = ResultSet()
        mock_result.column_list = [
            "索引名称",
            "唯一性",
            "索引类型",
            "压缩属性",
            "表空间",
            "状态",
            "分区",
        ]
        mock_result.rows = [
            ("PK_USERS", "UNIQUE", "NORMAL", "DISABLED", "USERS_TBS", "VALID", "NO")
        ]
        _query.return_value = mock_result

        # 调用被测试方法
        result = new_engine.get_table_index_data(db_name="TEST_SCHEMA", tb_name="USERS")

        # 验证结果结构
        self.assertIsInstance(result, dict)
        self.assertIn("column_list", result)
        self.assertIn("rows", result)
        self.assertIsInstance(result["column_list"], list)
        self.assertIsInstance(result["rows"], list)

        # 验证query方法被正确调用
        _query.assert_called_once()


class MongoTest(TestCase):
    def setUp(self) -> None:
        self.ins = Instance.objects.create(
            instance_name="some_ins",
            type="slave",
            db_type="mongo",
            host="some_host",
            port=3306,
            user="ins_user",
        )
        self.engine = MongoEngine(instance=self.ins)
        self.sys_config = SysConfig()
        # rule_type=100的规则不需要加，会自动创建。只需要加脱敏字段
        DataMaskingColumns.objects.create(
            rule_type=100,
            active=True,
            instance=self.ins,
            table_schema="*",
            table_name="*",
            column_name="mobile",
        )

    def tearDown(self) -> None:
        self.ins.delete()
        DataMaskingColumns.objects.all().delete()

    @patch("sql.engines.mongo.pymongo")
    def test_get_connection(self, mock_pymongo):
        _ = self.engine.get_connection()
        mock_pymongo.MongoClient.assert_called_once()

    @patch("sql.engines.mongo.MongoEngine.get_connection")
    def test_query(self, mock_get_connection):
        # TODO 正常查询还没做
        test_sql1 = """db.job.find().count()"""
        test_sql2 = """db.job.find({ goofy :{"$exists":false}})"""
        self.assertIsInstance(self.engine.query("some_db", test_sql1), ResultSet)
        self.assertIsInstance(self.engine.query("some_db", test_sql2), ResultSet)

    @patch("sql.engines.mongo.MongoEngine.get_all_tables")
    def test_query_check(self, mock_get_all_tables):
        test_sql = """db.job.find().count()"""
        mock_get_all_tables.return_value.rows = "job"
        check_result = self.engine.query_check("some_db", sql=test_sql)
        mock_get_all_tables.assert_called_once()
        self.assertEqual(False, check_result.get("bad_query"))

    @patch("sql.engines.mongo.MongoEngine.get_connection")
    def test_get_all_databases(self, mock_get_connection):
        db_list = self.engine.get_all_databases()
        self.assertIsInstance(db_list, ResultSet)
        # mock_get_connection.return_value.list_database_names.assert_called_once()

    @patch("sql.engines.mongo.MongoEngine.get_connection")
    def test_get_all_tables(self, mock_get_connection):
        mock_db = Mock()
        # 下面是查表示例返回结果
        mock_db.list_collection_names.return_value = ["u", "v", "w"]
        mock_get_connection.return_value = {"some_db": mock_db}
        table_list = self.engine.get_all_tables("some_db")
        mock_db.list_collection_names.assert_called_once()
        self.assertEqual(table_list.rows, ["u", "v", "w"])

    def test_filter_sql(self):
        sql = """explain db.job.find().count()"""
        check_result = self.engine.filter_sql(sql, 0)
        self.assertEqual(check_result, "db.job.find().count().explain()")

    @patch("sql.engines.mongo.MongoEngine.get_connection")
    def test_get_slave(self, mock_get_connection):
        mock_conn = Mock()
        mock_conn.admin.command.return_value = {
            "members": [{"stateStr": "SECONDARY", "name": "172.30.2.123:27017"}]
        }
        mock_get_connection.return_value = mock_conn
        flag = self.engine.get_slave()
        self.assertEqual(True, flag)

    @patch("sql.engines.mongo.MongoEngine.get_all_columns_by_tb")
    def test_parse_tuple(self, mock_get_all_columns_by_tb):
        cols = ["_id", "title", "tags", "likes"]
        mock_get_all_columns_by_tb.return_value.rows = cols
        cursor = [
            {
                "_id": {"$oid": "5f10162029684728e70045ab"},
                "title": "MongoDB",
                "tags": "mongodb",
                "likes": 100,
            }
        ]
        rows, columns = self.engine.parse_tuple(cursor, "some_db", "job")
        alldata = json.dumps(
            cursor[0], ensure_ascii=False, indent=2, separators=(",", ":")
        )
        rerows = (
            alldata,
            "ObjectId('5f10162029684728e70045ab')",
            "MongoDB",
            "mongodb",
            "100",
        )
        self.assertEqual(columns, ["mongodballdata", "_id", "title", "tags", "likes"])
        self.assertEqual(rows[0], rerows)

    @patch("sql.engines.mongo.MongoEngine.get_table_conut")
    @patch("sql.engines.mongo.MongoEngine.get_all_tables")
    def test_execute_check(self, mock_get_all_tables, mock_get_table_conut):
        sql = """db.job.createIndex({"skuId":1},{background:true});"""
        mock_get_all_tables.return_value.rows = "job"
        mock_get_table_conut.return_value = 1000
        row = ReviewResult(
            id=1,
            errlevel=0,
            stagestatus="Audit completed",
            errormessage="检测通过",
            affected_rows=1000,
            sql=sql,
            execute_time=0,
        )
        check_result = self.engine.execute_check("some_db", sql)
        self.assertEqual(
            check_result.rows[0].__dict__["errormessage"], row.__dict__["errormessage"]
        )

    @patch("sql.engines.mongo.MongoEngine.get_all_tables")
    def test_execute_check_include_dot(self, mock_get_all_tables):
        sql = """db.job.insert({
                                    fileName: "现金明细20230103075728.xls",
                                    contentType: ".xls",
                                    createdTime: ISODate("2023-01-03T12:05:27.402Z"),
                                    reportDate: ISODate("2023-01-03T12:05:27.402Z"),
                                    updatedTime: ISODate("2023-01-03T12:09:30.88Z")
                               });;"""
        mock_get_all_tables.return_value.rows = "job"
        check_result = self.engine.execute_check("some_db", sql)
        self.assertEqual(
            check_result.rows[0].__dict__["stagestatus"], "Audit completed"
        )

    @patch("sql.engines.mongo.MongoEngine.get_all_tables")
    def test_execute_check_on_dml_without_real_row_count(self, mock_get_all_tables):
        sql = """db.job.insert([{"orderCode":1001},{"orderCode":1002}]);"""
        mock_get_all_tables.return_value.rows = "job"
        check_result = self.engine.execute_check("some_db", sql)
        self.assertEqual(check_result.rows[0].__dict__["affected_rows"], 0)

    @patch("sql.engines.mongo.MongoEngine.get_all_tables")
    def test_execute_check_on_insert_one(self, mock_get_all_tables):
        self.sys_config.set("real_row_count", True)
        sql = """db.job.insertOne({"orderCode":1001});"""
        mock_get_all_tables.return_value.rows = "job"
        check_result = self.engine.execute_check("some_db", sql)
        self.assertEqual(check_result.rows[0].__dict__["affected_rows"], 1)

    @patch("sql.engines.mongo.MongoEngine.get_all_tables")
    def test_execute_check_on_insert_single(self, mock_get_all_tables):
        self.sys_config.set("real_row_count", True)
        sql = """db.job.insert({"orderCode":1001});"""
        mock_get_all_tables.return_value.rows = "job"
        check_result = self.engine.execute_check("some_db", sql)
        self.assertEqual(check_result.rows[0].__dict__["affected_rows"], 1)

    @patch("sql.engines.mongo.MongoEngine.get_all_tables")
    def test_execute_check_on_insert_multiple(self, mock_get_all_tables):
        self.sys_config.set("real_row_count", True)
        sql = """db.job.insert([{"orderCode":1001},{"orderCode":1002}]);"""
        mock_get_all_tables.return_value.rows = "job"
        check_result = self.engine.execute_check("some_db", sql)
        self.assertEqual(check_result.rows[0].__dict__["affected_rows"], 2)

    @patch("sql.engines.mongo.MongoEngine.get_all_tables")
    def test_execute_check_on_insert_except(self, mock_get_all_tables):
        self.sys_config.set("real_row_count", True)
        sql = """db.job.insert(("orderCode":1001));"""
        mock_get_all_tables.return_value.rows = "job"
        check_result = self.engine.execute_check("some_db", sql)
        self.assertEqual(check_result.rows[0].__dict__["affected_rows"], 0)

    @patch("sql.engines.mongo.MongoEngine.get_all_tables")
    @patch("sql.engines.mongo.MongoEngine.query")
    def test_execute_check_on_update_with_find(self, mock_get_all_tables, mock_query):
        self.sys_config.set("real_row_count", True)
        sql = """db.job.find({"orderCode":1001}).update(({"orderCode":1002}));"""
        mock_get_all_tables.return_value.rows = "job"
        mock_query.return_value.rows = (('{"count": 0}',),)
        check_result = self.engine.execute_check("some_db", sql)
        self.assertEqual(check_result.rows[0].__dict__["affected_rows"], 0)

    @patch("sql.engines.mongo.MongoEngine.get_all_tables")
    @patch("sql.engines.mongo.MongoEngine.query")
    def test_execute_check_on_update_without_find(
        self, mock_get_all_tables, mock_query
    ):
        self.sys_config.set("real_row_count", True)
        sql = """db.job.update({"orderCode":1001},{$set:{"orderCode":1002}}));"""
        mock_get_all_tables.return_value.rows = "job"
        mock_query.return_value.rows = (('{"count": 0}',),)
        check_result = self.engine.execute_check("some_db", sql)
        self.assertEqual(check_result.rows[0].__dict__["affected_rows"], 0)

    @patch("sql.engines.mongo.MongoEngine.get_all_tables")
    def test_execute_check_with_syntax_error(self, mock_get_all_tables):
        sql = """db.job.insert({"orderCode":1001);"""
        mock_get_all_tables.return_value.rows = "job"
        check_result = self.engine.execute_check("some_db", sql)
        self.assertEqual(check_result.rows[0].__dict__["stagestatus"], "语法错误")

    @patch("sql.engines.mongo.MongoEngine._execute_shell_sql")
    @patch("sql.engines.mongo.MongoEngine.get_master")
    def test_execute(self, mock_get_master, mock_execute_shell_sql):
        sql = """db.job.find().createIndex({"skuId":1},{background:true})"""
        mock_execute_shell_sql.return_value = (True, '{"ok": 1}', 0)

        check_result = self.engine.execute("some_db", sql)
        mock_get_master.assert_called_once()
        self.assertEqual(check_result.rows[0].__dict__["errlevel"], 0)

    @patch("sql.engines.mongo.MongoEngine._execute_shell_sql")
    @patch("sql.engines.mongo.MongoEngine.get_master")
    def test_execute_on_dml(self, mock_get_master, mock_execute_shell_sql):
        sql = """db.job.insertMany([{"title":"test1"},{"title":test2"},{"title":test3"}]);"""
        mock_execute_shell_sql.return_value = (True, '{"acknowledged": true}', 3)

        check_result = self.engine.execute("some_db", sql)
        mock_get_master.assert_called_once()
        self.assertEqual(check_result.rows[0].__dict__["affected_rows"], 3)

    @patch("sql.engines.mongo.MongoEngine._execute_shell_sql")
    @patch("sql.engines.mongo.MongoEngine.get_master")
    def test_execute_return_error(self, mock_get_master, mock_execute_shell_sql):
        sql = """db.job.insertMany({"title":"test1"},{"title":test2"},{"title":test3"});"""
        mock_execute_shell_sql.return_value = (
            False,
            "uncaught exception: TypeError: documents.map is not a function",
            0,
        )
        check_result = self.engine.execute("some_db", sql)
        mock_get_master.assert_called_once()
        self.assertEqual(check_result.rows[0].__dict__["stagestatus"], "异常终止")

    def test_fill_query_columns(self):
        columns = ["_id", "title", "tags", "likes"]
        cursor = [
            {
                "_id": {"$oid": "5f10162029684728e70045ab"},
                "title": "MongoDB",
                "text": "archery",
                "likes": 100,
            },
            {"_id": {"$oid": "7f10162029684728e70045ab"}, "author": "archery"},
        ]
        cols = self.engine.fill_query_columns(cursor, columns=columns)
        self.assertEqual(cols, ["_id", "title", "tags", "likes", "text", "author"])

    @patch("sql.engines.mongo.MongoEngine.get_connection")
    def test_processlist(self, mock_get_connection):
        # 模拟 MongoDB aggregate 的游标行为
        class AggregateCursor:
            def __enter__(self):
                yield {
                    "client": "single_client",
                    "effectiveUsers": [{"user": "user_1"}],
                    "clientMetadata": {"mongos": {"client": "sharding_client"}},
                }
                yield {
                    "clientMetadata": {"mongos": {}},
                    "effectiveUsers": [{"user": "user_2"}],
                }
                yield {"effectiveUsers": []}

            def __exit__(self, exc_type, exc_value, traceback):
                pass

        mock_conn = Mock()
        mock_conn.admin.aggregate.return_value = AggregateCursor()
        mock_get_connection.return_value = mock_conn
        command_types = ["Full", "All", "Inner", "Active"]
        for command_type in command_types:
            result_set = self.engine.processlist(command_type)
            self.assertIsInstance(result_set, ResultSet)

    @patch("sql.engines.mongo.MongoEngine.get_connection")
    def test_get_kill_command(self, mock_get_connection):
        class Aggregate:
            def __enter__(self):
                yield {"opid": 111}
                yield {"opid": "shard1: 111"}

            def __exit__(self, *arg, **kwargs):
                pass

        mock_conn = Mock()
        mock_conn.admin.aggregate.return_value = Aggregate()
        mock_get_connection.return_value = mock_conn
        kill_command1 = self.engine.get_kill_command([111, 222])
        kill_command2 = self.engine.get_kill_command(["shard1: 111", "shard2: 222"])
        self.assertEqual(kill_command1, "db.killOp(111);")
        self.assertEqual(kill_command2, 'db.killOp("shard1: 111");')

    @patch("sql.engines.mongo.MongoEngine.get_connection")
    def test_kill_op(self, mock_get_connection):
        def command(self, *arg, **kwargs):
            pass

        mock_conn = Mock()
        mock_conn.admin.command.return_value = command
        mock_get_connection.return_value = mock_conn
        self.engine.kill_op([111, 222])
        self.engine.kill_op(["shards: 111", "shards: 222"])
        mock_conn.admin.command.assert_called()

    @patch("pymongo.database.Database.command")
    @patch("sql.engines.mongo.MongoEngine.get_all_databases")
    def test_get_all_databases_summary(self, _mock_all_databases, _mock_command):
        db_result = ResultSet()
        db_result.rows = ["admin"]
        _mock_all_databases.return_value = db_result
        _mock_command.return_value = {
            "users": [
                {
                    "_id": "admin.root",
                    "user": "root",
                    "db": "admin",
                    "roles": [{"role": "root", "db": "admin"}],
                    "mechanisms": ["SCRAM-SHA-1", "SCRAM-SHA-256"],
                }
            ],
            "ok": 1.0,
        }
        database_summary = self.engine.get_all_databases_summary()
        self.assertEqual(
            database_summary.rows,
            [
                {
                    "db_name": "admin",
                    "grantees": [
                        "{'user': 'root', 'roles': [{'role': 'root', 'db': 'admin'}]}"
                    ],
                    "saved": False,
                }
            ],
        )

    @patch("pymongo.database.Database.command")
    @patch("sql.engines.mongo.MongoEngine.get_all_databases")
    def test_get_instance_users_summary(self, _mock_all_databases, _mock_command):
        db_result = ResultSet()
        db_result.rows = ["admin"]
        _mock_all_databases.return_value = db_result
        _mock_command.return_value = {
            "users": [
                {
                    "_id": "admin.root",
                    "user": "root",
                    "db": "admin",
                    "roles": [{"role": "root", "db": "admin"}],
                    "mechanisms": ["SCRAM-SHA-1", "SCRAM-SHA-256"],
                }
            ],
            "ok": 1.0,
        }
        database_summary = self.engine.get_instance_users_summary()
        self.assertEqual(
            database_summary.rows,
            [
                {
                    "db_name_user": "admin.root",
                    "db_name": "admin",
                    "user": "root",
                    "roles": ["root"],
                    "saved": False,
                }
            ],
        )

    @patch("pymongo.database.Database.command")
    def test_create_instance_user(self, _mock_command):
        result = self.engine.create_instance_user(
            db_name="test", user="some_user", password1="123456", remark=""
        )
        self.assertEqual(
            result.rows,
            [
                {
                    "instance": self.ins,
                    "db_name": "test",
                    "user": "some_user",
                    "password": "123456",
                    "remark": "",
                }
            ],
        )

    def test_query_masking(self):
        query_result = ResultSet()
        new_engine = MongoEngine(instance=self.ins)
        query_result.column_list = ["id", "mobile"]
        query_result.rows = (
            ("a11", "18888888888"),
            ("a12", ""),
            ("a13", None),
            ("a14", "18888888889"),
        )
        masking_result = new_engine.query_masking(
            db_name="archery", sql="db.test_collection.find()", resultset=query_result
        )
        mask_result_rows = [
            ["a11", "188****8888"],
            ["a12", ""],
            ["a13", None],
            ["a14", "188****8889"],
        ]
        self.assertEqual(masking_result.rows, mask_result_rows)


class TestClickHouse(TestCase):
    def setUp(self):
        self.ins1 = Instance(
            instance_name="some_ins",
            type="slave",
            db_type="clickhouse",
            host="some_host",
            port=9000,
            user="ins_user",
            password="some_str",
        )
        self.ins1.save()
        self.sys_config = SysConfig()
        self.wf = SqlWorkflow.objects.create(
            workflow_name="some_name",
            group_id=1,
            group_name="g1",
            engineer_display="",
            audit_auth_groups="some_group",
            create_time=datetime.now() - timedelta(days=1),
            status="workflow_finish",
            is_backup=False,
            instance=self.ins1,
            db_name="some_db",
            syntax_type=1,
        )
        SqlWorkflowContent.objects.create(workflow=self.wf)

    def tearDown(self):
        self.ins1.delete()
        self.sys_config.purge()
        SqlWorkflow.objects.all().delete()
        SqlWorkflowContent.objects.all().delete()

    @patch.object(ClickHouseEngine, "query")
    def test_server_version(self, mock_query):
        result = ResultSet()
        result.rows = [("ClickHouse 22.1.3.7",)]
        mock_query.return_value = result
        new_engine = ClickHouseEngine(instance=self.ins1)
        server_version = new_engine.server_version
        self.assertTupleEqual(server_version, (22, 1, 3))

    @patch.object(ClickHouseEngine, "query")
    def test_table_engine(self, mock_query):
        table_name = "default.tb_test"
        result = ResultSet()
        result.rows = [("MergeTree",)]
        mock_query.return_value = result
        new_engine = ClickHouseEngine(instance=self.ins1)
        table_engine = new_engine.get_table_engine(table_name)
        self.assertDictEqual(table_engine, {"status": 1, "engine": "MergeTree"})

    @patch("clickhouse_driver.connect")
    def test_engine_base_info(self, _conn):
        new_engine = ClickHouseEngine(instance=self.ins1)
        self.assertEqual(new_engine.name, "ClickHouse")
        self.assertEqual(new_engine.info, "ClickHouse engine")

    @patch.object(ClickHouseEngine, "get_connection")
    def testGetConnection(self, connect):
        new_engine = ClickHouseEngine(instance=self.ins1)
        new_engine.get_connection()
        connect.assert_called_once()

    @patch.object(ClickHouseEngine, "query")
    def testQuery(self, mock_query):
        result = ResultSet()
        result.rows = [
            ("v1", "v2"),
        ]
        mock_query.return_value = result
        new_engine = ClickHouseEngine(instance=self.ins1)
        query_result = new_engine.query(sql="some_sql", limit_num=100)
        self.assertListEqual(
            query_result.rows,
            [
                ("v1", "v2"),
            ],
        )

    @patch.object(ClickHouseEngine, "query")
    def testAllDb(self, mock_query):
        db_result = ResultSet()
        db_result.rows = [("db_1",), ("db_2",)]
        mock_query.return_value = db_result
        new_engine = ClickHouseEngine(instance=self.ins1)
        dbs = new_engine.get_all_databases()
        self.assertEqual(dbs.rows, ["db_1", "db_2"])

    @patch.object(ClickHouseEngine, "query")
    def testAllTables(self, mock_query):
        table_result = ResultSet()
        table_result.rows = [("tb_1", "some_des"), ("tb_2", "some_des")]
        mock_query.return_value = table_result
        new_engine = ClickHouseEngine(instance=self.ins1)
        tables = new_engine.get_all_tables("some_db")
        mock_query.assert_called_once_with(db_name="some_db", sql=ANY)
        self.assertEqual(tables.rows, ["tb_1", "tb_2"])

    @patch.object(ClickHouseEngine, "query")
    def testAllColumns(self, mock_query):
        db_result = ResultSet()
        db_result.rows = [("col_1", "type"), ("col_2", "type2")]
        mock_query.return_value = db_result
        new_engine = ClickHouseEngine(instance=self.ins1)
        dbs = new_engine.get_all_columns_by_tb("some_db", "some_tb")
        self.assertEqual(dbs.rows, ["col_1", "col_2"])

    @patch.object(ClickHouseEngine, "query")
    def testDescribe(self, mock_query):
        new_engine = ClickHouseEngine(instance=self.ins1)
        new_engine.describe_table("some_db", "some_db")
        mock_query.assert_called_once()

    def test_query_check_wrong_sql(self):
        new_engine = ClickHouseEngine(instance=self.ins1)
        wrong_sql = "-- 测试"
        check_result = new_engine.query_check(db_name="some_db", sql=wrong_sql)
        self.assertDictEqual(
            check_result,
            {
                "msg": "不支持的查询语法类型!",
                "bad_query": True,
                "filtered_sql": "-- 测试",
                "has_star": False,
            },
        )

    def test_query_check_update_sql(self):
        new_engine = ClickHouseEngine(instance=self.ins1)
        update_sql = "update user set id=0"
        check_result = new_engine.query_check(db_name="some_db", sql=update_sql)
        self.assertDictEqual(
            check_result,
            {
                "msg": "不支持的查询语法类型!",
                "bad_query": True,
                "filtered_sql": "update user set id=0",
                "has_star": False,
            },
        )

    @patch.object(ClickHouseEngine, "query")
    def test_explain_check(self, mock_query):
        result = ResultSet()
        result.rows = [("ClickHouse 20.1.3.7",)]
        mock_query.return_value = result
        new_engine = ClickHouseEngine(instance=self.ins1)
        server_version = new_engine.server_version
        sql = "insert into tb_test(note) values ('xbb');"
        check_result = ReviewSet(full_sql=sql)
        explain_result = new_engine.explain_check(
            check_result, db_name="some_db", line=1, statement=sql
        )
        self.assertEqual(explain_result.stagestatus, "Audit completed")

    def test_execute_check_select_sql(self):
        new_engine = ClickHouseEngine(instance=self.ins1)
        select_sql = "select id,name from tb_test"
        check_result = new_engine.execute_check(db_name="some_db", sql=select_sql)
        self.assertEqual(
            check_result.rows[0].errormessage,
            "仅支持DML和DDL语句，查询语句请使用SQL查询功能！",
        )

    @patch.object(ClickHouseEngine, "query")
    def test_execute_check_alter_sql(self, mock_query):
        table_name = "default.tb_test"
        result = ResultSet()
        result.rows = [("Log",)]
        mock_query.return_value = result
        new_engine = ClickHouseEngine(instance=self.ins1)
        table_engine = new_engine.get_table_engine(table_name)
        alter_sql = "alter table tb_test add column remark String"
        check_result = new_engine.execute_check(db_name="some_db", sql=alter_sql)
        self.assertEqual(
            check_result.rows[0].errormessage,
            "ALTER TABLE仅支持*MergeTree，Merge以及Distributed等引擎表！",
        )

    @patch.object(ClickHouseEngine, "query")
    def test_execute_check_truncate_sql(self, mock_query):
        table_name = "default.tb_test"
        result = ResultSet()
        result.rows = [("File",)]
        mock_query.return_value = result
        new_engine = ClickHouseEngine(instance=self.ins1)
        table_engine = new_engine.get_table_engine(table_name)
        alter_sql = "truncate table tb_test"
        check_result = new_engine.execute_check(db_name="some_db", sql=alter_sql)
        self.assertEqual(
            check_result.rows[0].errormessage,
            "TRUNCATE不支持View,File,URL,Buffer和Null表引擎！",
        )

    @patch.object(ClickHouseEngine, "query")
    def test_execute_check_insert_sql(self, mock_query):
        table_name = "default.tb_test"
        result = ResultSet()
        result.rows = [("Log",)]
        mock_query.return_value = result
        new_engine = ClickHouseEngine(instance=self.ins1)
        table_engine = new_engine.get_table_engine(table_name)
        alter_sql = "insert into tb_test(name) values('nick');"
        check_result = new_engine.execute_check(db_name="some_db", sql=alter_sql)
        self.assertEqual(
            check_result.rows[0].errlevel,
            0,
        )

    def test_filter_sql_with_delimiter(self):
        new_engine = ClickHouseEngine(instance=self.ins1)
        sql_without_limit = "select user from usertable;"
        check_result = new_engine.filter_sql(sql=sql_without_limit, limit_num=100)
        self.assertEqual(check_result, "select user from usertable limit 100;")

    def test_filter_sql_without_delimiter(self):
        new_engine = ClickHouseEngine(instance=self.ins1)
        sql_without_limit = "select user from usertable"
        check_result = new_engine.filter_sql(sql=sql_without_limit, limit_num=100)
        self.assertEqual(check_result, "select user from usertable limit 100;")

    def test_filter_sql_with_limit(self):
        new_engine = ClickHouseEngine(instance=self.ins1)
        sql_without_limit = "select user from usertable limit 10"
        check_result = new_engine.filter_sql(sql=sql_without_limit, limit_num=1)
        self.assertEqual(check_result, "select user from usertable limit 1;")

    def test_filter_sql_with_limit_min(self):
        new_engine = ClickHouseEngine(instance=self.ins1)
        sql_without_limit = "select user from usertable limit 10"
        check_result = new_engine.filter_sql(sql=sql_without_limit, limit_num=100)
        self.assertEqual(check_result, "select user from usertable limit 10;")

    def test_filter_sql_with_limit_offset(self):
        new_engine = ClickHouseEngine(instance=self.ins1)
        sql_without_limit = "select user from usertable limit 10 offset 100"
        check_result = new_engine.filter_sql(sql=sql_without_limit, limit_num=1)
        self.assertEqual(check_result, "select user from usertable limit 1 offset 100;")

    def test_filter_sql_with_limit_nn(self):
        new_engine = ClickHouseEngine(instance=self.ins1)
        sql_without_limit = "select user from usertable limit 10, 100"
        check_result = new_engine.filter_sql(sql=sql_without_limit, limit_num=1)
        self.assertEqual(check_result, "select user from usertable limit 10,1;")

    def test_filter_sql_upper(self):
        new_engine = ClickHouseEngine(instance=self.ins1)
        sql_without_limit = "SELECT USER FROM usertable LIMIT 10, 100"
        check_result = new_engine.filter_sql(sql=sql_without_limit, limit_num=1)
        self.assertEqual(check_result, "SELECT USER FROM usertable limit 10,1;")

    def test_filter_sql_not_select(self):
        new_engine = ClickHouseEngine(instance=self.ins1)
        sql_without_limit = "show create table usertable;"
        check_result = new_engine.filter_sql(sql=sql_without_limit, limit_num=1)
        self.assertEqual(check_result, "show create table usertable;")

    @patch("clickhouse_driver.connect.cursor.execute")
    @patch("clickhouse_driver.connect.cursor")
    @patch("clickhouse_driver.connect")
    def test_execute(self, _connect, _cursor, _execute):
        new_engine = ClickHouseEngine(instance=self.ins1)
        execute_result = new_engine.execute(self.wf)
        self.assertIsInstance(execute_result, ResultSet)

    @patch("clickhouse_driver.connect.cursor.execute")
    @patch("clickhouse_driver.connect.cursor")
    @patch("clickhouse_driver.connect")
    def test_execute_workflow_success(self, _conn, _cursor, _execute):
        sql = "insert into tb_test values('test')"
        row = ReviewResult(
            id=1,
            errlevel=0,
            stagestatus="Execute Successfully",
            errormessage="None",
            sql=sql,
            affected_rows=0,
            execute_time=0,
        )
        wf = SqlWorkflow.objects.create(
            workflow_name="some_name",
            group_id=1,
            group_name="g1",
            engineer_display="",
            audit_auth_groups="some_group",
            create_time=datetime.now() - timedelta(days=1),
            status="workflow_finish",
            is_backup=False,
            instance=self.ins1,
            db_name="some_db",
            syntax_type=1,
        )
        SqlWorkflowContent.objects.create(workflow=wf, sql_content=sql)
        new_engine = ClickHouseEngine(instance=self.ins1)
        execute_result = new_engine.execute_workflow(workflow=wf)
        self.assertIsInstance(execute_result, ReviewSet)
        self.assertEqual(execute_result.rows[0].__dict__.keys(), row.__dict__.keys())


class ODPSTest(TestCase):
    def setUp(self) -> None:
        self.ins = Instance.objects.create(
            instance_name="some_ins",
            type="slave",
            db_type="odps",
            host="some_host",
            port=9200,
            user="ins_user",
            db_name="some_db",
        )
        self.engine = ODPSEngine(instance=self.ins)

    def tearDown(self) -> None:
        self.ins.delete()

    @patch("sql.engines.odps.ODPSEngine.get_connection")
    def test_get_connection(self, mock_odps):
        _ = self.engine.get_connection()
        mock_odps.assert_called_once()

    @patch("sql.engines.odps.ODPSEngine.get_connection")
    def test_query(self, mock_get_connection):
        test_sql = """select 123"""
        self.assertIsInstance(self.engine.query("some_db", test_sql), ResultSet)

    def test_query_check(self):
        test_sql = """select 123; -- this is comment
                      select 456;"""

        result_sql = "select 123;"

        check_result = self.engine.query_check(sql=test_sql)

        self.assertIsInstance(check_result, dict)
        self.assertEqual(False, check_result.get("bad_query"))
        self.assertEqual(result_sql, check_result.get("filtered_sql"))

    def test_query_check_error(self):
        test_sql = """drop table table_a"""

        check_result = self.engine.query_check(sql=test_sql)

        self.assertIsInstance(check_result, dict)
        self.assertEqual(True, check_result.get("bad_query"))

    @patch("sql.engines.odps.ODPSEngine.get_connection")
    def test_get_all_databases(self, mock_get_connection):
        mock_conn = Mock()
        mock_conn.exist_project.return_value = True
        mock_conn.project = "some_db"

        mock_get_connection.return_value = mock_conn

        result = self.engine.get_all_databases()

        self.assertIsInstance(result, ResultSet)
        self.assertEqual(result.rows, ["some_db"])

    @patch("sql.engines.odps.ODPSEngine.get_connection")
    def test_get_all_tables(self, mock_get_connection):
        # 下面是查表示例返回结果
        class T:
            def __init__(self, name):
                self.name = name

        mock_conn = Mock()
        mock_conn.list_tables.return_value = [T("u"), T("v"), T("w")]
        mock_get_connection.return_value = mock_conn

        table_list = self.engine.get_all_tables("some_db")

        self.assertEqual(table_list.rows, ["u", "v", "w"])

    @patch("sql.engines.odps.ODPSEngine.get_all_columns_by_tb")
    def test_describe_table(self, mock_get_all_columns_by_tb):
        self.engine.describe_table("some_db", "some_table")
        mock_get_all_columns_by_tb.assert_called_once()

    @patch("sql.engines.odps.ODPSEngine.get_connection")
    def test_get_all_columns_by_tb(self, mock_get_connection):
        mock_conn = Mock()

        mock_cols = Mock()

        mock_col = Mock()
        mock_col.name, mock_col.type, mock_col.comment = "XiaoMing", "string", "name"

        mock_cols.schema.columns = [mock_col]
        mock_conn.get_table.return_value = mock_cols
        mock_get_connection.return_value = mock_conn

        result = self.engine.get_all_columns_by_tb("some_db", "some_table")
        mock_get_connection.assert_called_once()
        mock_conn.get_table.assert_called_once()
        self.assertEqual(result.rows, [["XiaoMing", "string", "name"]])
        self.assertEqual(
            result.column_list, ["COLUMN_NAME", "COLUMN_TYPE", "COLUMN_COMMENT"]
        )


def test_ssh(db_instance, mocker: MockerFixture):
    tunnel = Tunnel.objects.create(tunnel_name="test", host="test", port=22)
    db_instance.tunnel = tunnel
    db_instance.save()

    class FakeTunnel:
        def get_ssh(self):
            return "remote_host", "remote_password"

    mocker.patch("sql.engines.SSHConnection", return_value=FakeTunnel())
    from sql.engines import EngineBase

    engine = EngineBase(instance=db_instance)
    remote_host, remote_password, _, _ = engine.remote_instance_conn(
        instance=engine.instance
    )
    assert (remote_host, remote_password) == ("remote_host", "remote_password")
