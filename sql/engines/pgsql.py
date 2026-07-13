# -*- coding: UTF-8 -*-
"""
@author: hhyo、yyukai
@license: Apache Licence
@file: pgsql.py
@time: 2019/03/29
"""

import json
import re
import psycopg2
import logging
import traceback
import sqlparse
import sqlglot
from sqlglot import expressions as sqlglot_exp

from common.config import SysConfig
from common.utils.timer import FuncTimer
from sql.utils.sql_utils import get_syntax_type
from . import EngineBase
from .models import ResultSet, ReviewSet, ReviewResult
from sql.utils.data_masking import simple_column_mask

__author__ = "hhyo、yyukai"

logger = logging.getLogger("default")


class PgSQLEngine(EngineBase):
    test_query = "SELECT 1"

    def get_connection(self, db_name=None):
        db_name = db_name or self.db_name or "postgres"
        if self.conn:
            return self.conn
        self.conn = psycopg2.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            client_encoding=self.instance.charset,
            dbname=db_name,
            connect_timeout=10,
        )
        return self.conn

    name = "PgSQL"

    info = "PgSQL engine"

    def get_all_databases(self):
        """
        获取数据库列表
        :return:
        """
        result = self.query(sql=f"SELECT datname FROM pg_database;")
        db_list = [
            row[0] for row in result.rows if row[0] not in ["template0", "template1"]
        ]
        result.rows = db_list
        return result

    def get_all_schemas(self, db_name, **kwargs):
        """
        获取模式列表
        :return:
        """
        result = self.query(
            db_name=db_name, sql=f"select schema_name from information_schema.schemata;"
        )
        schema_list = [
            row[0]
            for row in result.rows
            if row[0]
            not in [
                "information_schema",
                "pg_catalog",
                "pg_toast_temp_1",
                "pg_temp_1",
                "pg_toast",
            ]
        ]
        result.rows = schema_list
        return result

    def get_all_tables(self, db_name, **kwargs):
        """
        获取表列表
        :param db_name:
        :param schema_name:
        :return:
        """
        schema_name = kwargs.get("schema_name") or "public"
        sql = """SELECT c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %(schema_name)s
        AND c.relkind IN ('r', 'p')
        ORDER BY c.relname;"""
        result = self.query(
            db_name=db_name, sql=sql, parameters={"schema_name": schema_name}
        )
        tb_list = [row[0] for row in result.rows if row[0] not in ["test"]]
        result.rows = tb_list
        return result

    def get_all_columns_by_tb(self, db_name, tb_name, **kwargs):
        """
        获取字段列表
        :param db_name:
        :param tb_name:
        :param schema_name:
        :return:
        """
        schema_name = kwargs.get("schema_name")
        sql = f"""SELECT column_name
        FROM information_schema.columns
        where table_name=%(tb_name)s
        and table_schema=%(schema_name)s;"""
        result = self.query(
            db_name=db_name,
            sql=sql,
            parameters={"schema_name": schema_name, "tb_name": tb_name},
        )
        column_list = [row[0] for row in result.rows]
        result.rows = column_list
        return result

    def describe_table(self, db_name, tb_name, **kwargs):
        """
        获取表结构信息
        :param db_name:
        :param tb_name:
        :param schema_name:
        :return:
        """
        schema_name = kwargs.get("schema_name")
        sql = f"""select
        col.column_name,
        col.data_type,
        col.character_maximum_length,
        col.numeric_precision,
        col.numeric_scale,
        col.is_nullable,
        col.column_default,
        des.description
        from
        information_schema.columns col left join pg_description des on
        col.table_name::regclass = des.objoid
        and col.ordinal_position = des.objsubid
        where table_name = %(tb_name)s
        and col.table_schema = %(schema_name)s
        order by ordinal_position;"""
        result = self.query(
            db_name=db_name,
            schema_name=schema_name,
            sql=sql,
            parameters={"schema_name": schema_name, "tb_name": tb_name},
        )
        return result

    def get_table_index_data(self, db_name, tb_name, **kwargs):
        """
        获取表格索引信息
        :param db_name:
        :param tb_name:
        :param schema_name:
        :return:
        """
        schema_name = kwargs.get("schema_name")
        sql = """SELECT
        index_cls.relname AS index_name,
        COALESCE(string_agg(attr.attname, ',' ORDER BY cols.ordinality), '') AS column_names,
        pg_get_indexdef(index_info.indexrelid) AS index_definition
        FROM pg_class table_cls
        JOIN pg_namespace namespace ON namespace.oid = table_cls.relnamespace
        JOIN pg_index index_info ON table_cls.oid = index_info.indrelid
        JOIN pg_class index_cls ON index_cls.oid = index_info.indexrelid
        LEFT JOIN LATERAL unnest(index_info.indkey) WITH ORDINALITY AS cols(attnum, ordinality)
        ON TRUE
        LEFT JOIN pg_attribute attr
        ON attr.attrelid = table_cls.oid
        AND attr.attnum = cols.attnum
        WHERE namespace.nspname = %(schema_name)s
        AND table_cls.relname = %(tb_name)s
        GROUP BY index_cls.relname, index_info.indexrelid
        ORDER BY index_cls.relname;"""
        result = self.query(
            db_name=db_name,
            schema_name=schema_name,
            sql=sql,
            parameters={"schema_name": schema_name, "tb_name": tb_name},
        )
        return result

    def get_table_overview_data(self, db_name, tb_name, **kwargs):
        """获取表概要、注释和分区角色"""
        schema_name = kwargs.get("schema_name") or "public"
        sql = """SELECT
        c.relname AS table_name,
        CASE c.relkind
            WHEN 'p' THEN 'partitioned table'
            WHEN 'r' THEN 'table'
            WHEN 'm' THEN 'materialized view'
            ELSE c.relkind::text
        END AS object_type,
        pg_get_userbyid(c.relowner) AS owner,
        COALESCE(obj_description(c.oid, 'pg_class'), '') AS comment,
        COALESCE(pg_size_pretty(pg_total_relation_size(c.oid)), '') AS total_size,
        CASE WHEN c.relispartition THEN 'partition child' ELSE '' END AS partition_role
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %(schema_name)s
        AND c.relname = %(tb_name)s
        AND c.relkind IN ('r', 'p', 'm');"""
        return self.query(
            db_name=db_name,
            schema_name=schema_name,
            sql=sql,
            parameters={"schema_name": schema_name, "tb_name": tb_name},
        )

    def get_table_constraint_data(self, db_name, tb_name, **kwargs):
        """获取表约束信息"""
        schema_name = kwargs.get("schema_name") or "public"
        sql = """SELECT
        con.conname AS constraint_name,
        CASE con.contype
            WHEN 'p' THEN 'PRIMARY KEY'
            WHEN 'u' THEN 'UNIQUE'
            WHEN 'f' THEN 'FOREIGN KEY'
            WHEN 'c' THEN 'CHECK'
            WHEN 'x' THEN 'EXCLUDE'
            ELSE con.contype::text
        END AS constraint_type,
        COALESCE(pg_get_constraintdef(con.oid, true), '') AS constraint_definition
        FROM pg_constraint con
        JOIN pg_class cls ON cls.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = cls.relnamespace
        WHERE n.nspname = %(schema_name)s
        AND cls.relname = %(tb_name)s
        ORDER BY con.contype, con.conname;"""
        return self.query(
            db_name=db_name,
            schema_name=schema_name,
            sql=sql,
            parameters={"schema_name": schema_name, "tb_name": tb_name},
        )

    def get_table_partition_data(self, db_name, tb_name, **kwargs):
        """获取表分区信息"""
        schema_name = kwargs.get("schema_name") or "public"
        sql = """WITH target AS (
            SELECT c.oid, c.relname, c.relispartition
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %(schema_name)s
            AND c.relname = %(tb_name)s
        )
        SELECT
        'parent' AS relation_role,
        parent.relname AS relation_name,
        COALESCE(pg_get_expr(target_class.relpartbound, target_class.oid), '') AS partition_definition
        FROM target
        JOIN pg_class target_class ON target_class.oid = target.oid
        JOIN pg_inherits inh ON inh.inhrelid = target.oid
        JOIN pg_class parent ON parent.oid = inh.inhparent
        UNION ALL
        SELECT
        'child' AS relation_role,
        child.relname AS relation_name,
        COALESCE(pg_get_expr(child.relpartbound, child.oid), '') AS partition_definition
        FROM target
        JOIN pg_inherits inh ON inh.inhparent = target.oid
        JOIN pg_class child ON child.oid = inh.inhrelid
        ORDER BY relation_role, relation_name;"""
        return self.query(
            db_name=db_name,
            schema_name=schema_name,
            sql=sql,
            parameters={"schema_name": schema_name, "tb_name": tb_name},
        )

    def get_materialized_views_list(self, db_name, **kwargs):
        """获取物化视图列表，按首字符分组"""
        schema_name = kwargs.get("schema_name") or "public"
        sql = """SELECT
        matviewname AS object_name,
        'materialized view' AS object_type
        FROM pg_matviews
        WHERE schemaname = %(schema_name)s
        ORDER BY matviewname;"""
        result = self.query(
            db_name=db_name,
            schema_name=schema_name,
            sql=sql,
            parameters={"schema_name": schema_name},
        )
        return self._group_program_objects(result.rows)

    def get_materialized_view_detail(self, db_name, matview_name, **kwargs):
        """获取物化视图详情"""
        schema_name = kwargs.get("schema_name") or "public"
        sql = """SELECT
        schemaname AS schema_name,
        matviewname AS matview_name,
        matviewowner AS owner,
        tablespace,
        hasindexes,
        ispopulated,
        definition,
        'CREATE MATERIALIZED VIEW ' || quote_ident(schemaname) || '.' ||
            quote_ident(matviewname) || ' AS ' || definition || E'\\n;' AS create_sql
        FROM pg_matviews
        WHERE schemaname = %(schema_name)s
        AND matviewname = %(matview_name)s;"""
        result = self.query(
            db_name=db_name,
            schema_name=schema_name,
            sql=sql,
            parameters={"schema_name": schema_name, "matview_name": matview_name},
        )
        return {
            "meta_data": {"column_list": result.column_list, "rows": result.rows},
            "create_sql": [[row[-1]] for row in result.rows if row[-1]],
        }

    def get_sequences_list(self, db_name, **kwargs):
        """获取序列列表，按首字符分组"""
        schema_name = kwargs.get("schema_name") or "public"
        sql = """SELECT
        sequence_name,
        data_type || ' start ' || start_value || ' increment ' || increment
        FROM information_schema.sequences
        WHERE sequence_schema = %(schema_name)s
        ORDER BY sequence_name;"""
        result = self.query(
            db_name=db_name,
            schema_name=schema_name,
            sql=sql,
            parameters={"schema_name": schema_name},
        )
        return self._group_program_objects(result.rows)

    def get_sequence_detail(self, db_name, sequence_name, **kwargs):
        """获取序列详情"""
        schema_name = kwargs.get("schema_name") or "public"
        sql = """SELECT
        sequence_schema,
        sequence_name,
        data_type,
        start_value,
        minimum_value,
        maximum_value,
        increment,
        cycle_option,
        'CREATE SEQUENCE ' || quote_ident(sequence_schema) || '.' ||
            quote_ident(sequence_name) ||
            ' START WITH ' || start_value ||
            ' INCREMENT BY ' || increment ||
            ' MINVALUE ' || minimum_value ||
            ' MAXVALUE ' || maximum_value ||
            CASE WHEN cycle_option = 'YES' THEN ' CYCLE' ELSE ' NO CYCLE' END ||
            E';' AS create_sql
        FROM information_schema.sequences
        WHERE sequence_schema = %(schema_name)s
        AND sequence_name = %(sequence_name)s;"""
        result = self.query(
            db_name=db_name,
            schema_name=schema_name,
            sql=sql,
            parameters={"schema_name": schema_name, "sequence_name": sequence_name},
        )
        return {
            "meta_data": {"column_list": result.column_list, "rows": result.rows},
            "create_sql": [[row[-1]] for row in result.rows if row[-1]],
        }

    def get_blocking_chain(self, db_name, **kwargs):
        """获取锁等待和阻塞链信息"""
        sql = """WITH waiting AS (
            SELECT
                wait_activity.pid AS waiting_pid,
                blocker_pid AS blocking_pid,
                wait_activity.usename AS waiting_user,
                block_activity.usename AS blocking_user,
                now() - wait_activity.query_start AS waiting_duration,
                wait_activity.wait_event_type,
                wait_activity.wait_event,
                wait_activity.state AS waiting_state,
                block_activity.state AS blocking_state,
                wait_activity.query AS waiting_query,
                block_activity.query AS blocking_query
            FROM pg_stat_activity wait_activity
            JOIN LATERAL unnest(pg_blocking_pids(wait_activity.pid)) AS blocker_pid ON true
            LEFT JOIN pg_stat_activity block_activity ON block_activity.pid = blocker_pid
            WHERE cardinality(pg_blocking_pids(wait_activity.pid)) > 0
        )
        SELECT
            waiting.waiting_pid,
            waiting.blocking_pid,
            waiting.waiting_user,
            waiting.blocking_user,
            waiting.waiting_duration::text AS waiting_duration,
            waiting.wait_event_type,
            waiting.wait_event,
            COALESCE(lock_info.locktype, '') AS lock_type,
            COALESCE(lock_info.relation::regclass::text, '') AS relation_name,
            waiting.waiting_state,
            waiting.blocking_state,
            waiting.waiting_query,
            waiting.blocking_query,
            'SELECT pg_cancel_backend(' || waiting.blocking_pid || ');' AS cancel_sql,
            'SELECT pg_terminate_backend(' || waiting.blocking_pid || ');' AS terminate_sql
        FROM waiting
        LEFT JOIN LATERAL (
            SELECT locktype, relation
            FROM pg_locks
            WHERE pid = waiting.waiting_pid
            AND NOT granted
            ORDER BY relation NULLS LAST
            LIMIT 1
        ) lock_info ON true
        ORDER BY waiting.waiting_duration DESC, waiting.waiting_pid;"""
        return self.query(db_name=db_name, sql=sql)

    @staticmethod
    def _group_program_objects(rows):
        data = {}
        for row in rows:
            obj_name = row[0]
            if not obj_name:
                continue
            initial = obj_name[0]
            if initial not in data:
                data[initial] = []
            data[initial].append(row)
        return data

    def get_views_list(self, db_name, **kwargs):
        """获取视图列表，按首字符分组"""
        schema_name = kwargs.get("schema_name") or "public"
        sql = """SELECT table_name, 'VIEW'
        FROM information_schema.views
        WHERE table_schema = %(schema_name)s
        ORDER BY table_name;"""
        result = self.query(
            db_name=db_name,
            schema_name=schema_name,
            sql=sql,
            parameters={"schema_name": schema_name},
        )
        return self._group_program_objects(result.rows)

    def get_view_detail(self, db_name, view_name, **kwargs):
        """获取视图详情"""
        schema_name = kwargs.get("schema_name") or "public"
        sql = """SELECT
        viewname AS view_name,
        schemaname AS schema_name,
        viewowner AS view_owner,
        definition AS view_definition,
        'CREATE OR REPLACE VIEW ' || quote_ident(schemaname) || '.' ||
            quote_ident(viewname) || ' AS ' || definition || E'\\n;' AS create_sql
        FROM pg_views
        WHERE schemaname = %(schema_name)s
        AND viewname = %(view_name)s;"""
        result = self.query(
            db_name=db_name,
            schema_name=schema_name,
            sql=sql,
            parameters={"schema_name": schema_name, "view_name": view_name},
        )
        desc = self.describe_table(
            db_name=db_name, schema_name=schema_name, tb_name=view_name
        )
        create_sql = result.rows[0][4] if result.rows else ""
        view_definition = result.rows[0][3] if result.rows else ""
        return {
            "meta_data": {
                "column_list": result.column_list,
                "rows": result.rows[0] if result.rows else [],
            },
            "desc": {"column_list": desc.column_list, "rows": desc.rows},
            "view_definition": view_definition,
            "create_sql": [[create_sql]] if create_sql else [],
        }

    def get_functions_list(self, db_name, **kwargs):
        """获取函数列表，按首字符分组"""
        schema_name = kwargs.get("schema_name") or "public"
        sql = """SELECT
        p.proname || '(' || COALESCE(pg_get_function_identity_arguments(p.oid), '') || ')' AS display_name,
        'returns ' || COALESCE(pg_get_function_result(p.oid), '') AS return_type,
        p.oid::text AS object_id,
        p.proname AS object_name,
        COALESCE(pg_get_function_identity_arguments(p.oid), '') AS identity_arguments
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = %(schema_name)s
        AND p.prokind = 'f'
        ORDER BY p.proname, pg_get_function_identity_arguments(p.oid);"""
        result = self.query(
            db_name=db_name,
            schema_name=schema_name,
            sql=sql,
            parameters={"schema_name": schema_name},
        )
        return self._group_program_objects(result.rows)

    def get_function_detail(self, db_name, func_name, **kwargs):
        """获取函数详情"""
        schema_name = kwargs.get("schema_name") or "public"
        object_id = kwargs.get("object_id")
        sql = """SELECT
        p.oid::text AS object_id,
        p.proname AS routine_name,
        n.nspname AS routine_schema,
        pg_get_function_result(p.oid) AS return_type,
        pg_get_function_arguments(p.oid) AS arguments,
        pg_get_function_identity_arguments(p.oid) AS identity_arguments,
        l.lanname AS language,
        pg_get_userbyid(p.proowner) AS owner,
        pg_get_functiondef(p.oid) AS create_sql
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_language l ON l.oid = p.prolang
        WHERE n.nspname = %(schema_name)s
        AND p.prokind = 'f'
        AND p.proname = %(func_name)s
        ORDER BY p.proname, pg_get_function_arguments(p.oid);"""
        parameters = {"schema_name": schema_name, "func_name": func_name}
        if object_id:
            sql = """SELECT
        p.oid::text AS object_id,
        p.proname AS routine_name,
        n.nspname AS routine_schema,
        pg_get_function_result(p.oid) AS return_type,
        pg_get_function_arguments(p.oid) AS arguments,
        pg_get_function_identity_arguments(p.oid) AS identity_arguments,
        l.lanname AS language,
        pg_get_userbyid(p.proowner) AS owner,
        pg_get_functiondef(p.oid) AS create_sql
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_language l ON l.oid = p.prolang
        WHERE n.nspname = %(schema_name)s
        AND p.prokind = 'f'
        AND p.oid = %(object_id)s::oid;"""
            parameters = {"schema_name": schema_name, "object_id": object_id}
        result = self.query(
            db_name=db_name,
            schema_name=schema_name,
            sql=sql,
            parameters=parameters,
        )
        return {
            "meta_data": {"column_list": result.column_list, "rows": result.rows},
            "create_sql": [[row[-1]] for row in result.rows if row[-1]],
        }

    def get_procedures_list(self, db_name, **kwargs):
        """获取存储过程列表，按首字符分组"""
        schema_name = kwargs.get("schema_name") or "public"
        sql = """SELECT
        p.proname || '(' || COALESCE(pg_get_function_identity_arguments(p.oid), '') || ')' AS display_name,
        'procedure' AS routine_type,
        p.oid::text AS object_id,
        p.proname AS object_name,
        COALESCE(pg_get_function_identity_arguments(p.oid), '') AS identity_arguments
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = %(schema_name)s
        AND p.prokind = 'p'
        ORDER BY p.proname, pg_get_function_identity_arguments(p.oid);"""
        result = self.query(
            db_name=db_name,
            schema_name=schema_name,
            sql=sql,
            parameters={"schema_name": schema_name},
        )
        return self._group_program_objects(result.rows)

    def get_procedure_detail(self, db_name, proc_name, **kwargs):
        """获取存储过程详情"""
        schema_name = kwargs.get("schema_name") or "public"
        object_id = kwargs.get("object_id")
        sql = """SELECT
        p.oid::text AS object_id,
        p.proname AS routine_name,
        n.nspname AS routine_schema,
        pg_get_function_arguments(p.oid) AS arguments,
        pg_get_function_identity_arguments(p.oid) AS identity_arguments,
        l.lanname AS language,
        pg_get_userbyid(p.proowner) AS owner,
        pg_get_functiondef(p.oid) AS create_sql
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_language l ON l.oid = p.prolang
        WHERE n.nspname = %(schema_name)s
        AND p.prokind = 'p'
        AND p.proname = %(proc_name)s
        ORDER BY p.proname, pg_get_function_arguments(p.oid);"""
        parameters = {"schema_name": schema_name, "proc_name": proc_name}
        if object_id:
            sql = """SELECT
        p.oid::text AS object_id,
        p.proname AS routine_name,
        n.nspname AS routine_schema,
        pg_get_function_arguments(p.oid) AS arguments,
        pg_get_function_identity_arguments(p.oid) AS identity_arguments,
        l.lanname AS language,
        pg_get_userbyid(p.proowner) AS owner,
        pg_get_functiondef(p.oid) AS create_sql
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_language l ON l.oid = p.prolang
        WHERE n.nspname = %(schema_name)s
        AND p.prokind = 'p'
        AND p.oid = %(object_id)s::oid;"""
            parameters = {"schema_name": schema_name, "object_id": object_id}
        result = self.query(
            db_name=db_name,
            schema_name=schema_name,
            sql=sql,
            parameters=parameters,
        )
        return {
            "meta_data": {"column_list": result.column_list, "rows": result.rows},
            "create_sql": [[row[-1]] for row in result.rows if row[-1]],
        }

    def get_triggers_list(self, db_name, **kwargs):
        """获取触发器列表，按首字符分组"""
        schema_name = kwargs.get("schema_name") or "public"
        sql = """SELECT
        trigger_name,
        action_timing || ' ' || event_manipulation || ' ON ' || event_object_table
        FROM information_schema.triggers
        WHERE trigger_schema = %(schema_name)s
        ORDER BY trigger_name;"""
        result = self.query(
            db_name=db_name,
            schema_name=schema_name,
            sql=sql,
            parameters={"schema_name": schema_name},
        )
        return self._group_program_objects(result.rows)

    def get_trigger_detail(self, db_name, trigger_name, **kwargs):
        """获取触发器详情"""
        schema_name = kwargs.get("schema_name") or "public"
        sql = """SELECT
        t.tgname AS trigger_name,
        n.nspname AS trigger_schema,
        c.relname AS event_object_table,
        CASE t.tgenabled
            WHEN 'O' THEN 'enabled'
            WHEN 'D' THEN 'disabled'
            WHEN 'R' THEN 'replica'
            WHEN 'A' THEN 'always'
            ELSE t.tgenabled::text
        END AS trigger_status,
        pg_get_triggerdef(t.oid, true) AS create_sql
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE NOT t.tgisinternal
        AND n.nspname = %(schema_name)s
        AND t.tgname = %(trigger_name)s
        ORDER BY c.relname, t.tgname;"""
        result = self.query(
            db_name=db_name,
            schema_name=schema_name,
            sql=sql,
            parameters={"schema_name": schema_name, "trigger_name": trigger_name},
        )
        return {
            "column_list": result.column_list,
            "rows": result.rows[0] if result.rows else [],
            "create_sql": [[row[-1]] for row in result.rows if row[-1]],
        }

    def query_check(self, db_name=None, sql=""):
        # 查询语句的检查、注释去除、切分
        result = {"msg": "", "bad_query": False, "filtered_sql": sql, "has_star": False}
        # 删除注释语句，进行语法判断，执行第一条有效sql
        try:
            sql = sqlparse.format(sql, strip_comments=True)
            sql = sqlparse.split(sql)[0]
            result["filtered_sql"] = sql.strip()
        except IndexError:
            result["bad_query"] = True
            result["msg"] = "没有有效的SQL语句"
        if re.match(r"^select|^explain", sql, re.I) is None:
            result["bad_query"] = True
            result["msg"] = "不支持的查询语法类型!"
        if "*" in sql:
            result["has_star"] = True
            result["msg"] += "SQL语句中含有 * "
        return result

    # PostgreSQL 系统 schema, 表级鉴权时无需校验
    SYSTEM_SCHEMAS = frozenset(["pg_catalog", "information_schema"])

    def get_table_ref(self, sql, db_name=None, schema_name=None):
        """
        解析 SQL, 提取语句涉及的表引用, 用于查询权限的表级校验。
        返回与 GoInceptionEngine.get_table_ref 一致的结构:
        [{"schema": <schema>, "name": <table>}, ...]
        - 不带 schema 的表引用, 使用传入的 schema_name 补全, 缺省为 public
        - 排除 CTE (with 子句) 定义的临时表名
        - 跳过 pg_catalog / information_schema 等系统 schema
        解析失败时抛出异常, 由调用方兜底处理。
        """
        default_schema = schema_name or "public"
        try:
            tree = sqlglot.parse_one(sql, dialect="postgres")
        except Exception as e:
            raise RuntimeError(f"SQL 解析失败: {e}")
        if tree is None:
            return []
        # 收集 CTE 名称, 这些是查询内定义的临时表, 不是真实表
        cte_names = {cte.alias_or_name for cte in tree.find_all(sqlglot_exp.CTE)}
        table_ref = []
        seen = set()
        for table in tree.find_all(sqlglot_exp.Table):
            schema = table.db or default_schema
            name = table.name
            if not name:
                continue
            # 跳过 CTE 引用 (无显式 schema 且名称命中 CTE)
            if not table.db and name in cte_names:
                continue
            # 跳过系统 schema
            if schema in self.SYSTEM_SCHEMAS:
                continue
            key = (schema, name)
            if key in seen:
                continue
            seen.add(key)
            table_ref.append({"schema": schema, "name": name})
        return table_ref

    def query(
        self,
        db_name=None,
        sql="",
        limit_num=0,
        close_conn=True,
        parameters=None,
        **kwargs,
    ):
        """返回 ResultSet"""
        schema_name = kwargs.get("schema_name")
        result_set = ResultSet(full_sql=sql)
        conn = None
        try:
            conn = self.get_connection(db_name=db_name)
            conn.autocommit = False
            max_execution_time = kwargs.get("max_execution_time", 0)
            cursor = conn.cursor()
            try:
                cursor.execute(f"SET statement_timeout TO {max_execution_time};")
            except:
                pass
            cursor.execute("SET transaction ISOLATION LEVEL READ COMMITTED READ ONLY;")
            if schema_name:
                cursor.execute(
                    f"SET search_path TO %(schema_name)s;", {"schema_name": schema_name}
                )
            cursor.execute(sql, parameters)
            # effect_row = cursor.rowcount
            if int(limit_num) > 0:
                rows = cursor.fetchmany(size=int(limit_num))
            else:
                rows = cursor.fetchall()
            conn.commit()
            fields = cursor.description
            column_type_codes = [i[1] for i in fields] if fields else []
            # 定义 JSON 和 JSONB 的 type_code,# 114 是 json，3802 是 jsonb
            JSON_TYPE_CODE = 114
            JSONB_TYPE_CODE = 3802
            # 对 rows 进行循环处理，判断是否是 jsonb 或 json 类型
            converted_rows = []
            for row in rows:
                new_row = []
                for idx, col_value in enumerate(row):
                    # 理论上, 下标不会越界的
                    column_type_code = (
                        column_type_codes[idx] if idx < len(column_type_codes) else None
                    )
                    # 只在列类型为 json 或 jsonb 时转换
                    if column_type_code in [JSON_TYPE_CODE, JSONB_TYPE_CODE]:
                        if isinstance(col_value, (dict, list)):
                            new_row.append(
                                json.dumps(col_value, ensure_ascii=False)
                            )  # 转为 JSON 字符串
                        else:
                            new_row.append(col_value)
                    else:
                        new_row.append(col_value)
                converted_rows.append(tuple(new_row))

            result_set.column_list = [i[0] for i in fields] if fields else []
            result_set.rows = converted_rows
            result_set.affected_rows = len(converted_rows)
        except Exception as e:
            if conn:
                conn.rollback()
            logger.warning(
                f"PgSQL命令执行报错，语句：{sql}， 错误信息：{traceback.format_exc()}"
            )
            result_set.error = str(e)
        finally:
            if close_conn:
                self.close()
        return result_set

    def _normalize_backend_pids(self, thread_ids, thread_ids_check=True):
        if not thread_ids:
            return []

        pids = []
        for thread_id in thread_ids:
            try:
                pid = int(thread_id)
            except (TypeError, ValueError):
                if thread_ids_check:
                    return None
                continue
            if pid > 0:
                pids.append(pid)
            elif thread_ids_check:
                return None
        return pids

    def get_cancel_command(self, thread_ids, thread_ids_check=True):
        """由传入的后端PID列表生成取消查询命令"""
        pids = self._normalize_backend_pids(thread_ids, thread_ids_check)
        if pids is None:
            return None
        cancel_sql = ""
        for pid in pids:
            cancel_sql += "SELECT pg_cancel_backend({});".format(pid)
        return cancel_sql

    def get_kill_command(self, thread_ids, thread_ids_check=True):
        """由传入的后端PID列表生成终止会话命令"""
        pids = self._normalize_backend_pids(thread_ids, thread_ids_check)
        if pids is None:
            return None
        kill_sql = ""
        for pid in pids:
            kill_sql += "SELECT pg_terminate_backend({});".format(pid)
        return kill_sql

    def _execute_backend_control(self, thread_ids, function_name, thread_ids_check=True):
        pids = self._normalize_backend_pids(thread_ids, thread_ids_check)
        if pids is None or not pids:
            return ResultSet(full_sql="")

        sql = "SELECT {}(%s);".format(function_name)
        display_sql = "".join(
            "SELECT {}({});".format(function_name, pid) for pid in pids
        )
        result_set = ResultSet(full_sql=display_sql)
        conn = None
        try:
            conn = self.get_connection(db_name="postgres")
            conn.autocommit = False
            cursor = conn.cursor()
            rows = []
            for pid in pids:
                cursor.execute(sql, (pid,))
                rows.extend(cursor.fetchall())
            conn.commit()
            result_set.column_list = [function_name]
            result_set.rows = rows
            result_set.affected_rows = len(rows)
        except Exception as e:
            if conn:
                conn.rollback()
            logger.warning(
                f"PgSQL会话控制执行报错，语句：{display_sql}，错误信息：{traceback.format_exc()}"
            )
            result_set.error = str(e)
        finally:
            self.close()
        return result_set

    def cancel_backend(self, thread_ids, thread_ids_check=True):
        """取消后端正在执行的查询"""
        return self._execute_backend_control(
            thread_ids, "pg_cancel_backend", thread_ids_check
        )

    def terminate_backend(self, thread_ids, thread_ids_check=True):
        """终止后端连接"""
        return self._execute_backend_control(
            thread_ids, "pg_terminate_backend", thread_ids_check
        )

    def kill(self, thread_ids, thread_ids_check=True):
        """终止后端连接"""
        return self.terminate_backend(thread_ids, thread_ids_check)

    def filter_sql(self, sql="", limit_num=0):
        # 对查询sql增加limit限制，# TODO limit改写待优化
        sql_lower = sql.lower().rstrip(";").strip()
        if re.match(r"^select", sql_lower):
            if re.search(r"limit\s+(\d+)$", sql_lower) is None:
                if re.search(r"limit\s+\d+\s*,\s*(\d+)$", sql_lower) is None:
                    return f"{sql.rstrip(';')} limit {limit_num};"
        return f"{sql.rstrip(';')};"

    def query_masking(self, db_name=None, sql="", resultset=None):
        """简单字段脱敏规则, 仅对select有效"""
        if re.match(r"^select", sql, re.I):
            filtered_result = simple_column_mask(self.instance, resultset)
            filtered_result.is_masked = True
        else:
            filtered_result = resultset
        return filtered_result

    def execute_check(self, db_name=None, sql=""):
        """上线单执行前的检查, 返回Review set"""
        config = SysConfig()
        check_result = ReviewSet(full_sql=sql)
        # 禁用/高危语句检查
        line = 1
        critical_ddl_regex = config.get("critical_ddl_regex", "")
        p = re.compile(critical_ddl_regex)
        check_result.syntax_type = 2  # TODO 工单类型 0、其他 1、DDL，2、DML
        for statement in sqlparse.split(sql):
            statement = sqlparse.format(statement, strip_comments=True)
            # 禁用语句
            if re.match(r"^select", statement.lower()):
                result = ReviewResult(
                    id=line,
                    errlevel=2,
                    stagestatus="驳回不支持语句",
                    errormessage="仅支持DML和DDL语句，查询语句请使用SQL查询功能！",
                    sql=statement,
                )
            # 高危语句
            elif critical_ddl_regex and p.match(statement.strip().lower()):
                result = ReviewResult(
                    id=line,
                    errlevel=2,
                    stagestatus="驳回高危SQL",
                    errormessage="禁止提交匹配" + critical_ddl_regex + "条件的语句！",
                    sql=statement,
                )

            # 正常语句
            else:
                result = ReviewResult(
                    id=line,
                    errlevel=0,
                    stagestatus="Audit completed",
                    errormessage="None",
                    sql=statement,
                    affected_rows=0,
                    execute_time=0,
                )
            # 判断工单类型
            if get_syntax_type(statement) == "DDL":
                check_result.syntax_type = 1
            check_result.rows += [result]
            line += 1
        # 统计警告和错误数量
        for r in check_result.rows:
            if r.errlevel == 1:
                check_result.warning_count += 1
            if r.errlevel == 2:
                check_result.error_count += 1
        return check_result

    def execute_workflow(self, workflow, close_conn=True):
        """执行上线单，返回Review set"""
        sql = workflow.sqlworkflowcontent.sql_content
        execute_result = ReviewSet(full_sql=sql)
        # 删除注释语句，切分语句，将切换CURRENT_SCHEMA语句增加到切分结果中
        sql = sqlparse.format(sql, strip_comments=True)
        split_sql = sqlparse.split(sql)
        line = 1
        statement = None
        db_name = workflow.db_name
        try:
            conn = self.get_connection(db_name=db_name)
            conn.autocommit = False
            cursor = conn.cursor()
            cursor.execute("SET transaction ISOLATION LEVEL READ COMMITTED READ WRITE;")
            # 逐条执行切分语句，追加到执行结果中
            for statement in split_sql:
                statement = statement.rstrip(";")
                with FuncTimer() as t:
                    cursor.execute(statement)
                execute_result.rows.append(
                    ReviewResult(
                        id=line,
                        errlevel=0,
                        stagestatus="Execute Successfully",
                        errormessage="None",
                        sql=statement,
                        affected_rows=cursor.rowcount,
                        execute_time=t.cost,
                    )
                )
                line += 1
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.warning(
                f"PGSQL命令执行报错，语句：{statement or sql}， 错误信息：{traceback.format_exc()}"
            )
            execute_result.error = str(e)
            # 追加当前报错语句信息到执行结果中
            execute_result.rows.append(
                ReviewResult(
                    id=line,
                    errlevel=2,
                    stagestatus="Execute Failed",
                    errormessage=f"异常信息：{e}",
                    sql=statement or sql,
                    affected_rows=0,
                    execute_time=0,
                )
            )
            line += 1
            # 报错语句后面的语句标记为审核通过、未执行，追加到执行结果中
            for statement in split_sql[line - 1 :]:
                execute_result.rows.append(
                    ReviewResult(
                        id=line,
                        errlevel=0,
                        stagestatus="Audit completed",
                        errormessage=f"前序语句失败, 未执行",
                        sql=statement,
                        affected_rows=0,
                        execute_time=0,
                    )
                )
                line += 1
        finally:
            if close_conn:
                self.close()
        return execute_result

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def _get_dbdiagnostic_sql_template(self, diagnostic_type):
        from sql.models import DBDiagnosticSQLTemplate

        return (
            DBDiagnosticSQLTemplate.objects.filter(
                db_type="pgsql",
                diagnostic_type=diagnostic_type,
                enabled=True,
            )
            .order_by("-update_time", "-id")
            .first()
        )

    def _validate_dbdiagnostic_sql(self, sql):
        from sql.models import DBDiagnosticSQLTemplate

        return DBDiagnosticSQLTemplate.validate_select_sql(sql)

    def _query_dbdiagnostic_sql(
        self,
        diagnostic_type,
        default_sql,
        db_name="postgres",
        timeout_ms=3000,
        replacements=None,
        required_columns=None,
        template_db_name_override=True,
    ):
        template = self._get_dbdiagnostic_sql_template(diagnostic_type)
        if template:
            sql = template.sql
            if template_db_name_override:
                db_name = template.db_name or db_name
            else:
                db_name = db_name or template.db_name
            timeout_ms = template.timeout_ms or timeout_ms
        else:
            sql = default_sql

        for source, target in (replacements or {}).items():
            sql = sql.replace(source, target)

        ok, message, safe_sql = self._validate_dbdiagnostic_sql(sql)
        if not ok:
            result = ResultSet(full_sql=sql)
            result.error = message
            return result

        result = self.query(
            db_name=db_name or "postgres",
            sql=safe_sql,
            max_execution_time=timeout_ms,
        )
        if not result.error and required_columns:
            missing_columns = [
                column for column in required_columns if column not in result.column_list
            ]
            if missing_columns:
                result.error = "自定义SQL缺少必要输出字段：{}".format(
                    ", ".join(missing_columns)
                )
        return result

    def trxandlocks(self):
        """获取 PostgreSQL 锁等待和阻塞链信息"""
        sql = """
WITH RECURSIVE lock_edges AS (
    SELECT
        activity.pid AS waiting_pid,
        blocking_pid
    FROM pg_stat_activity activity
    CROSS JOIN LATERAL unnest(pg_blocking_pids(activity.pid)) AS blocking_pid
    WHERE activity.pid <> pg_backend_pid()
),
lock_chains AS (
    SELECT
        waiting_pid AS root_pid,
        waiting_pid AS current_pid,
        ARRAY[waiting_pid] AS path,
        0 AS depth
    FROM lock_edges
    UNION ALL
    SELECT
        lock_chains.root_pid,
        lock_edges.blocking_pid AS current_pid,
        lock_chains.path || lock_edges.blocking_pid,
        lock_chains.depth + 1
    FROM lock_chains
    JOIN lock_edges ON lock_edges.waiting_pid = lock_chains.current_pid
    WHERE NOT lock_edges.blocking_pid = ANY(lock_chains.path)
      AND lock_chains.depth < 20
),
terminal_chains AS (
    SELECT DISTINCT ON (root_pid)
        root_pid,
        array_to_string(path, ' -> ') AS blocking_chain
    FROM lock_chains
    WHERE NOT EXISTS (
        SELECT 1
        FROM lock_edges next_edge
        WHERE next_edge.waiting_pid = lock_chains.current_pid
          AND NOT next_edge.blocking_pid = ANY(lock_chains.path)
    )
    ORDER BY root_pid, cardinality(path) DESC
),
waiting_locks AS (
    SELECT
        locks.*,
        activity.datname,
        activity.usename,
        activity.application_name,
        activity.client_addr::text AS client_addr,
        activity.state,
        activity.wait_event_type,
        activity.wait_event,
        activity.xact_start,
        activity.query_start,
        activity.query,
        lock_edges.blocking_pid
    FROM pg_locks locks
    JOIN pg_stat_activity activity ON activity.pid = locks.pid
    JOIN lock_edges ON lock_edges.waiting_pid = locks.pid
    WHERE NOT locks.granted
)
SELECT
    waiting_locks.pid AS waiting_pid,
    waiting_locks.blocking_pid AS blocking_pid,
    terminal_chains.blocking_chain AS blocking_chain,
    waiting_locks.datname AS database_name,
    waiting_locks.usename AS waiting_user,
    blocking_activity.usename AS blocking_user,
    waiting_locks.application_name AS waiting_application,
    blocking_activity.application_name AS blocking_application,
    waiting_locks.client_addr AS waiting_client_addr,
    blocking_activity.client_addr::text AS blocking_client_addr,
    waiting_locks.state AS waiting_state,
    blocking_activity.state AS blocking_state,
    waiting_locks.wait_event_type AS wait_event_type,
    waiting_locks.wait_event AS wait_event,
    waiting_locks.locktype AS lock_type,
    waiting_locks.mode AS waiting_lock_mode,
    blocking_lock.mode AS blocking_lock_mode,
    concat_ws(
        '/',
        waiting_locks.locktype,
        NULLIF(waiting_locks.relation::regclass::text, ''),
        CASE WHEN waiting_locks.page IS NOT NULL THEN 'page=' || waiting_locks.page END,
        CASE WHEN waiting_locks.tuple IS NOT NULL THEN 'tuple=' || waiting_locks.tuple END,
        CASE WHEN waiting_locks.transactionid IS NOT NULL THEN 'xid=' || waiting_locks.transactionid END,
        CASE WHEN waiting_locks.virtualxid IS NOT NULL THEN 'vxid=' || waiting_locks.virtualxid END,
        CASE WHEN waiting_locks.classid IS NOT NULL THEN 'classid=' || waiting_locks.classid END,
        CASE WHEN waiting_locks.objid IS NOT NULL THEN 'objid=' || waiting_locks.objid END,
        CASE WHEN waiting_locks.objsubid IS NOT NULL THEN 'objsubid=' || waiting_locks.objsubid END
    ) AS lock_object,
    round(GREATEST(EXTRACT(EPOCH FROM (now() - waiting_locks.query_start)), 0)::numeric, 4) AS waiting_duration_seconds,
    waiting_locks.xact_start AS waiting_xact_start,
    waiting_locks.query_start AS waiting_query_start,
    blocking_activity.xact_start AS blocking_xact_start,
    blocking_activity.query_start AS blocking_query_start,
    waiting_locks.query AS waiting_query,
    blocking_activity.query AS blocking_query
FROM waiting_locks
LEFT JOIN pg_stat_activity blocking_activity ON blocking_activity.pid = waiting_locks.blocking_pid
LEFT JOIN pg_locks blocking_lock ON blocking_lock.pid = waiting_locks.blocking_pid
    AND blocking_lock.granted
    AND blocking_lock.locktype IS NOT DISTINCT FROM waiting_locks.locktype
    AND blocking_lock.database IS NOT DISTINCT FROM waiting_locks.database
    AND blocking_lock.relation IS NOT DISTINCT FROM waiting_locks.relation
    AND blocking_lock.page IS NOT DISTINCT FROM waiting_locks.page
    AND blocking_lock.tuple IS NOT DISTINCT FROM waiting_locks.tuple
    AND blocking_lock.virtualxid IS NOT DISTINCT FROM waiting_locks.virtualxid
    AND blocking_lock.transactionid IS NOT DISTINCT FROM waiting_locks.transactionid
    AND blocking_lock.classid IS NOT DISTINCT FROM waiting_locks.classid
    AND blocking_lock.objid IS NOT DISTINCT FROM waiting_locks.objid
    AND blocking_lock.objsubid IS NOT DISTINCT FROM waiting_locks.objsubid
LEFT JOIN terminal_chains ON terminal_chains.root_pid = waiting_locks.pid
ORDER BY waiting_duration_seconds DESC, waiting_locks.pid, waiting_locks.blocking_pid;
        """
        return self._query_dbdiagnostic_sql(
            diagnostic_type="pgsql_trxandlocks",
            default_sql=sql,
            db_name="postgres",
            timeout_ms=3000,
            required_columns=[
                "waiting_pid",
                "blocking_pid",
                "blocking_chain",
                "waiting_query",
                "blocking_query",
            ],
        )

    def pubsub(self):
        """获取 PostgreSQL 发布订阅信息"""
        sql = """
WITH publication_rows AS (
    SELECT
        'publication'::text AS object_type,
        publication.pubname::text AS object_name,
        'true'::text AS enabled,
        pg_get_userbyid(publication.pubowner)::text AS owner_name,
        current_database()::text AS database_name,
        publication.pubname::text AS publication_names,
        CASE
            WHEN publication.puballtables THEN 'ALL TABLES'
            ELSE concat_ws('.', publication_tables.schemaname, publication_tables.tablename)
        END::text AS table_name,
        concat_ws(
            ',',
            CASE WHEN publication.pubinsert THEN 'insert' END,
            CASE WHEN publication.pubupdate THEN 'update' END,
            CASE WHEN publication.pubdelete THEN 'delete' END,
            CASE WHEN publication.pubtruncate THEN 'truncate' END
        )::text AS operations,
        NULL::integer AS subscription_pid,
        NULL::text AS slot_name,
        NULL::text AS sync_commit,
        NULL::text AS received_lsn,
        NULL::text AS latest_end_lsn,
        NULL::timestamp with time zone AS last_msg_send_time,
        NULL::timestamp with time zone AS last_msg_receipt_time,
        NULL::timestamp with time zone AS latest_end_time,
        NULL::numeric AS lag_seconds,
        NULL::text AS conninfo
    FROM pg_publication publication
    LEFT JOIN pg_publication_tables publication_tables
        ON publication_tables.pubname = publication.pubname
),
subscription_rows AS (
    SELECT
        'subscription'::text AS object_type,
        subscription.subname::text AS object_name,
        subscription.subenabled::text AS enabled,
        pg_get_userbyid(subscription.subowner)::text AS owner_name,
        current_database()::text AS database_name,
        array_to_string(subscription.subpublications, ', ')::text AS publication_names,
        NULL::text AS table_name,
        NULL::text AS operations,
        subscription_stat.pid AS subscription_pid,
        subscription.subslotname::text AS slot_name,
        subscription.subsynccommit::text AS sync_commit,
        subscription_stat.received_lsn::text AS received_lsn,
        subscription_stat.latest_end_lsn::text AS latest_end_lsn,
        subscription_stat.last_msg_send_time AS last_msg_send_time,
        subscription_stat.last_msg_receipt_time AS last_msg_receipt_time,
        subscription_stat.latest_end_time AS latest_end_time,
        CASE
            WHEN subscription_stat.latest_end_time IS NULL THEN NULL
            ELSE round(GREATEST(EXTRACT(EPOCH FROM (now() - subscription_stat.latest_end_time)), 0)::numeric, 4)
        END AS lag_seconds,
        regexp_replace(subscription.subconninfo, 'password=[^ ]+', 'password=****', 'gi')::text AS conninfo
    FROM pg_subscription subscription
    LEFT JOIN pg_stat_subscription subscription_stat
        ON subscription_stat.subid = subscription.oid
)
SELECT *
FROM publication_rows
UNION ALL
SELECT *
FROM subscription_rows
ORDER BY object_type, object_name, table_name NULLS FIRST;
        """
        return self._query_dbdiagnostic_sql(
            diagnostic_type="pgsql_pubsub",
            default_sql=sql,
            db_name="postgres",
            timeout_ms=3000,
            required_columns=[
                "object_type",
                "object_name",
                "enabled",
                "owner_name",
                "database_name",
            ],
        )

    def replication_status(self):
        """获取 PostgreSQL 流复制状态"""
        sql = """
SELECT
    replication.pid,
    replication.usename,
    replication.application_name,
    replication.client_addr::text AS client_addr,
    replication.client_hostname,
    replication.client_port,
    replication.backend_start,
    replication.backend_xmin,
    replication.state,
    replication.sent_lsn::text AS sent_lsn,
    replication.write_lsn::text AS write_lsn,
    replication.flush_lsn::text AS flush_lsn,
    replication.replay_lsn::text AS replay_lsn,
    replication.write_lag,
    replication.flush_lag,
    replication.replay_lag,
    replication.sync_priority,
    replication.sync_state,
    replication.reply_time,
    CASE
        WHEN replication.sent_lsn IS NULL OR replication.replay_lsn IS NULL THEN NULL
        ELSE pg_wal_lsn_diff(replication.sent_lsn, replication.replay_lsn)
    END AS replay_lag_bytes,
    CASE
        WHEN replication.sent_lsn IS NULL OR replication.flush_lsn IS NULL THEN NULL
        ELSE pg_wal_lsn_diff(replication.sent_lsn, replication.flush_lsn)
    END AS flush_lag_bytes,
    CASE
        WHEN replication.sent_lsn IS NULL OR replication.write_lsn IS NULL THEN NULL
        ELSE pg_wal_lsn_diff(replication.sent_lsn, replication.write_lsn)
    END AS write_lag_bytes
FROM pg_stat_replication replication
ORDER BY replication.application_name, replication.client_addr::text, replication.pid;
        """
        return self._query_dbdiagnostic_sql(
            diagnostic_type="pgsql_replication",
            default_sql=sql,
            db_name="postgres",
            timeout_ms=3000,
            required_columns=[
                "pid",
                "usename",
                "application_name",
                "client_addr",
                "state",
                "sync_state",
            ],
        )

    def replication_slots(self):
        """获取 PostgreSQL replication slot 状态"""
        sql = """
SELECT
    slot.slot_name,
    slot.plugin,
    slot.slot_type,
    slot.datoid,
    slot.database AS database_name,
    slot.temporary,
    slot.active,
    slot.active_pid,
    slot.xmin,
    slot.catalog_xmin,
    slot.restart_lsn::text AS restart_lsn,
    slot.confirmed_flush_lsn::text AS confirmed_flush_lsn,
    CASE
        WHEN slot.restart_lsn IS NULL THEN NULL
        ELSE pg_wal_lsn_diff(pg_current_wal_lsn(), slot.restart_lsn)
    END AS retained_wal_bytes,
    pg_size_pretty(
        CASE
            WHEN slot.restart_lsn IS NULL THEN 0
            ELSE pg_wal_lsn_diff(pg_current_wal_lsn(), slot.restart_lsn)
        END
    ) AS retained_wal_size,
    to_jsonb(slot)->>'wal_status' AS wal_status,
    NULLIF(to_jsonb(slot)->>'safe_wal_size', '')::numeric AS safe_wal_size
FROM pg_replication_slots slot
ORDER BY retained_wal_bytes DESC NULLS LAST, slot.slot_name;
        """
        return self._query_dbdiagnostic_sql(
            diagnostic_type="pgsql_replication_slots",
            default_sql=sql,
            db_name="postgres",
            timeout_ms=3000,
            required_columns=[
                "slot_name",
                "slot_type",
                "active",
                "restart_lsn",
            ],
        )

    def _pgsql_vacuum_sql(self):
        return """
WITH table_stats AS (
    SELECT
        namespace.nspname AS schema_name,
        relation.relname AS table_name,
        pg_get_userbyid(relation.relowner) AS owner_name,
        COALESCE(stat.n_live_tup, 0) AS n_live_tup,
        COALESCE(stat.n_dead_tup, 0) AS n_dead_tup,
        CASE
            WHEN COALESCE(stat.n_live_tup, 0) + COALESCE(stat.n_dead_tup, 0) = 0 THEN 0
            ELSE round(
                COALESCE(stat.n_dead_tup, 0)::numeric
                * 100
                / (COALESCE(stat.n_live_tup, 0) + COALESCE(stat.n_dead_tup, 0)),
                2
            )
        END AS dead_tuple_ratio,
        stat.last_vacuum,
        stat.last_autovacuum,
        stat.last_analyze,
        stat.last_autoanalyze,
        stat.vacuum_count,
        stat.autovacuum_count,
        stat.analyze_count,
        stat.autoanalyze_count,
        CASE
            WHEN relation.relfrozenxid::text = '0' THEN 0
            ELSE age(relation.relfrozenxid)
        END AS relfrozenxid_age,
        pg_total_relation_size(relation.oid) AS total_size_bytes,
        pg_size_pretty(pg_total_relation_size(relation.oid)) AS total_size
    FROM pg_class relation
    JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
    LEFT JOIN pg_stat_user_tables stat ON stat.relid = relation.oid
    WHERE relation.relkind IN ('r', 'p', 'm')
      AND namespace.nspname NOT IN ('pg_catalog', 'information_schema')
      AND namespace.nspname NOT LIKE 'pg_toast%%'
      AND ($schema_name$ = '' OR namespace.nspname = $schema_name$)
)
SELECT
    schema_name,
    table_name,
    owner_name,
    n_live_tup,
    n_dead_tup,
    dead_tuple_ratio,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    vacuum_count,
    autovacuum_count,
    analyze_count,
    autoanalyze_count,
    relfrozenxid_age,
    total_size_bytes,
    total_size,
    CASE
        WHEN relfrozenxid_age >= 1500000000 THEN 'xid高风险'
        WHEN dead_tuple_ratio >= 30 AND n_dead_tup >= 100000 THEN 'dead tuple高风险'
        WHEN last_autovacuum IS NULL AND last_vacuum IS NULL AND n_live_tup + n_dead_tup > 0 THEN '未vacuum'
        WHEN dead_tuple_ratio >= 10 AND n_dead_tup >= 10000 THEN '需要关注'
        ELSE '正常'
    END AS risk_level
FROM table_stats
ORDER BY
    CASE
        WHEN relfrozenxid_age >= 1500000000 THEN 1
        WHEN dead_tuple_ratio >= 30 AND n_dead_tup >= 100000 THEN 2
        WHEN last_autovacuum IS NULL AND last_vacuum IS NULL AND n_live_tup + n_dead_tup > 0 THEN 3
        WHEN dead_tuple_ratio >= 10 AND n_dead_tup >= 10000 THEN 4
        ELSE 5
    END,
    relfrozenxid_age DESC,
    n_dead_tup DESC,
    dead_tuple_ratio DESC,
    total_size_bytes DESC
LIMIT $limit$ OFFSET $offset$
        """

    def vacuum_risk(self, offset=0, row_count=30, db_name="", schema_name=""):
        """获取 PostgreSQL 表级 autovacuum 和膨胀风险"""
        ok, schema_literal = self._schema_name_literal(schema_name)
        if not ok:
            result = ResultSet(full_sql="")
            result.error = schema_literal
            return result

        return self._query_dbdiagnostic_sql(
            diagnostic_type="pgsql_vacuum",
            default_sql=self._pgsql_vacuum_sql(),
            db_name=db_name,
            timeout_ms=3000,
            replacements={
                "$limit$": str(int(row_count)),
                "$offset$": str(int(offset)),
                "$schema_name$": schema_literal,
            },
            required_columns=[
                "schema_name",
                "table_name",
                "n_live_tup",
                "n_dead_tup",
                "dead_tuple_ratio",
                "relfrozenxid_age",
            ],
            template_db_name_override=False,
        )

    def vacuum_risk_count(self, db_name="", schema_name=""):
        """获取 PostgreSQL vacuum 风险记录数"""
        ok, schema_literal = self._schema_name_literal(schema_name)
        if not ok:
            result = ResultSet(full_sql="")
            result.error = schema_literal
            return result

        template = self._get_dbdiagnostic_sql_template("pgsql_vacuum")
        if template:
            sql = template.sql
            query_db_name = db_name or template.db_name or "postgres"
            timeout_ms = template.timeout_ms or 3000
        else:
            sql = self._pgsql_vacuum_sql()
            query_db_name = db_name or "postgres"
            timeout_ms = 3000

        sql = (
            sql.replace("$limit$", "9223372036854775807")
            .replace("$offset$", "0")
            .replace("$schema_name$", schema_literal)
        )
        ok, message, safe_sql = self._validate_dbdiagnostic_sql(sql)
        if not ok:
            result = ResultSet(full_sql=sql)
            result.error = message
            return result

        count_sql = "SELECT count(*) AS total FROM ({}) dbdiagnostic_vacuum_count".format(
            safe_sql.rstrip(";")
        )
        return self.query(
            db_name=query_db_name or "postgres",
            sql=count_sql,
            max_execution_time=timeout_ms,
        )

    def _pgsql_indexes_sql(self):
        return """
WITH index_stats AS (
    SELECT
        namespace.nspname AS schema_name,
        table_relation.relname AS table_name,
        index_relation.relname AS index_name,
        pg_get_userbyid(table_relation.relowner) AS owner_name,
        index_relation.oid AS index_oid,
        table_relation.oid AS table_oid,
        pg_relation_size(index_relation.oid) AS index_size_bytes,
        pg_size_pretty(pg_relation_size(index_relation.oid)) AS index_size,
        pg_total_relation_size(table_relation.oid) AS table_size_bytes,
        pg_size_pretty(pg_total_relation_size(table_relation.oid)) AS table_size,
        COALESCE(index_stat.idx_scan, 0) AS idx_scan,
        COALESCE(index_stat.idx_tup_read, 0) AS idx_tup_read,
        COALESCE(index_stat.idx_tup_fetch, 0) AS idx_tup_fetch,
        COALESCE(table_stat.seq_scan, 0) AS seq_scan,
        COALESCE(table_stat.seq_tup_read, 0) AS seq_tup_read,
        COALESCE(table_stat.n_live_tup, 0) AS n_live_tup,
        pg_index.indisvalid AS is_valid,
        pg_index.indisready AS is_ready,
        pg_index.indisunique AS is_unique,
        pg_index.indisprimary AS is_primary,
        pg_get_indexdef(index_relation.oid) AS index_def
    FROM pg_class table_relation
    JOIN pg_namespace namespace ON namespace.oid = table_relation.relnamespace
    JOIN pg_index ON pg_index.indrelid = table_relation.oid
    JOIN pg_class index_relation ON index_relation.oid = pg_index.indexrelid
    LEFT JOIN pg_stat_user_indexes index_stat ON index_stat.indexrelid = index_relation.oid
    LEFT JOIN pg_stat_user_tables table_stat ON table_stat.relid = table_relation.oid
    WHERE table_relation.relkind IN ('r', 'p', 'm')
      AND namespace.nspname NOT IN ('pg_catalog', 'information_schema')
      AND namespace.nspname NOT LIKE 'pg_toast%%'
      AND ($schema_name$ = '' OR namespace.nspname = $schema_name$)
),
diagnostic_rows AS (
    SELECT
        'invalid_index'::text AS diagnostic_type,
        schema_name,
        table_name,
        index_name,
        owner_name,
        index_size_bytes,
        index_size,
        table_size_bytes,
        table_size,
        idx_scan,
        idx_tup_read,
        idx_tup_fetch,
        seq_scan,
        seq_tup_read,
        n_live_tup,
        is_valid,
        is_ready,
        is_unique,
        is_primary,
        index_def,
        '索引无效或未ready，需要检查并重建/删除'::text AS reason,
        1 AS priority
    FROM index_stats
    WHERE NOT is_valid OR NOT is_ready

    UNION ALL

    SELECT
        'unused_index'::text AS diagnostic_type,
        schema_name,
        table_name,
        index_name,
        owner_name,
        index_size_bytes,
        index_size,
        table_size_bytes,
        table_size,
        idx_scan,
        idx_tup_read,
        idx_tup_fetch,
        seq_scan,
        seq_tup_read,
        n_live_tup,
        is_valid,
        is_ready,
        is_unique,
        is_primary,
        index_def,
        '索引扫描次数为0且占用空间较大，建议结合业务确认是否可删除'::text AS reason,
        2 AS priority
    FROM index_stats
    WHERE idx_scan = 0
      AND NOT is_primary
      AND index_size_bytes >= 1048576

    UNION ALL

    SELECT
        'high_seq_scan'::text AS diagnostic_type,
        schema_name,
        table_name,
        index_name,
        owner_name,
        index_size_bytes,
        index_size,
        table_size_bytes,
        table_size,
        idx_scan,
        idx_tup_read,
        idx_tup_fetch,
        seq_scan,
        seq_tup_read,
        n_live_tup,
        is_valid,
        is_ready,
        is_unique,
        is_primary,
        index_def,
        '表顺序扫描次数较高，建议结合SQL和选择性评估索引设计'::text AS reason,
        3 AS priority
    FROM index_stats
    WHERE seq_scan >= 100
      AND seq_scan > idx_scan * 2
)
SELECT
    diagnostic_type,
    schema_name,
    table_name,
    index_name,
    owner_name,
    index_size,
    index_size_bytes,
    table_size,
    table_size_bytes,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    seq_scan,
    seq_tup_read,
    n_live_tup,
    is_valid,
    is_ready,
    is_unique,
    is_primary,
    reason,
    index_def
FROM diagnostic_rows
ORDER BY priority, index_size_bytes DESC, seq_scan DESC, schema_name, table_name, index_name
LIMIT $limit$ OFFSET $offset$
        """

    def index_diagnostic(self, offset=0, row_count=30, db_name="", schema_name=""):
        """获取 PostgreSQL 索引诊断结果"""
        ok, schema_literal = self._schema_name_literal(schema_name)
        if not ok:
            result = ResultSet(full_sql="")
            result.error = schema_literal
            return result

        return self._query_dbdiagnostic_sql(
            diagnostic_type="pgsql_indexes",
            default_sql=self._pgsql_indexes_sql(),
            db_name=db_name,
            timeout_ms=3000,
            replacements={
                "$limit$": str(int(row_count)),
                "$offset$": str(int(offset)),
                "$schema_name$": schema_literal,
            },
            required_columns=[
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
            template_db_name_override=False,
        )

    def index_diagnostic_count(self, db_name="", schema_name=""):
        """获取 PostgreSQL 索引诊断记录数"""
        ok, schema_literal = self._schema_name_literal(schema_name)
        if not ok:
            result = ResultSet(full_sql="")
            result.error = schema_literal
            return result

        template = self._get_dbdiagnostic_sql_template("pgsql_indexes")
        if template:
            sql = template.sql
            query_db_name = db_name or template.db_name or "postgres"
            timeout_ms = template.timeout_ms or 3000
        else:
            sql = self._pgsql_indexes_sql()
            query_db_name = db_name or "postgres"
            timeout_ms = 3000

        sql = (
            sql.replace("$limit$", "9223372036854775807")
            .replace("$offset$", "0")
            .replace("$schema_name$", schema_literal)
        )
        ok, message, safe_sql = self._validate_dbdiagnostic_sql(sql)
        if not ok:
            result = ResultSet(full_sql=sql)
            result.error = message
            return result

        count_sql = "SELECT count(*) AS total FROM ({}) dbdiagnostic_indexes_count".format(
            safe_sql.rstrip(";")
        )
        return self.query(
            db_name=query_db_name or "postgres",
            sql=count_sql,
            max_execution_time=timeout_ms,
        )

    def _pgsql_progress_sql(self):
        return """
WITH progress_rows AS (
    SELECT
        'vacuum'::text AS progress_type,
        progress.pid,
        progress.datname::text AS database_name,
        concat_ws('.', namespace.nspname, relation.relname)::text AS relation_name,
        progress.phase::text AS phase,
        progress.heap_blks_scanned::bigint AS blocks_done,
        progress.heap_blks_total::bigint AS blocks_total,
        CASE
            WHEN progress.heap_blks_total > 0 THEN round(progress.heap_blks_scanned::numeric * 100 / progress.heap_blks_total, 2)
            ELSE NULL
        END AS progress_percent,
        progress.heap_blks_scanned::bigint AS heap_blks_scanned,
        progress.heap_blks_total::bigint AS heap_blks_total,
        progress.index_vacuum_count::bigint AS index_vacuum_count,
        progress.max_dead_tuples::bigint AS max_dead_tuples,
        progress.num_dead_tuples::bigint AS num_dead_tuples,
        NULL::bigint AS blocks_total_alt,
        NULL::bigint AS blocks_done_alt,
        NULL::bigint AS tuples_total,
        NULL::bigint AS tuples_done,
        NULL::text AS command
    FROM pg_stat_progress_vacuum progress
    LEFT JOIN pg_class relation ON relation.oid = progress.relid
    LEFT JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace

    UNION ALL

    SELECT
        'create_index'::text AS progress_type,
        progress.pid,
        progress.datname::text AS database_name,
        concat_ws('.', namespace.nspname, relation.relname)::text AS relation_name,
        progress.phase::text AS phase,
        progress.blocks_done::bigint AS blocks_done,
        progress.blocks_total::bigint AS blocks_total,
        CASE
            WHEN progress.blocks_total > 0 THEN round(progress.blocks_done::numeric * 100 / progress.blocks_total, 2)
            WHEN progress.tuples_total > 0 THEN round(progress.tuples_done::numeric * 100 / progress.tuples_total, 2)
            ELSE NULL
        END AS progress_percent,
        NULL::bigint AS heap_blks_scanned,
        NULL::bigint AS heap_blks_total,
        NULL::bigint AS index_vacuum_count,
        NULL::bigint AS max_dead_tuples,
        NULL::bigint AS num_dead_tuples,
        progress.blocks_total::bigint AS blocks_total_alt,
        progress.blocks_done::bigint AS blocks_done_alt,
        progress.tuples_total::bigint AS tuples_total,
        progress.tuples_done::bigint AS tuples_done,
        progress.command::text AS command
    FROM pg_stat_progress_create_index progress
    LEFT JOIN pg_class relation ON relation.oid = progress.relid
    LEFT JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace

    UNION ALL

    SELECT
        'analyze'::text AS progress_type,
        progress.pid,
        progress.datname::text AS database_name,
        concat_ws('.', namespace.nspname, relation.relname)::text AS relation_name,
        progress.phase::text AS phase,
        progress.sample_blks_scanned::bigint AS blocks_done,
        progress.sample_blks_total::bigint AS blocks_total,
        CASE
            WHEN progress.sample_blks_total > 0 THEN round(progress.sample_blks_scanned::numeric * 100 / progress.sample_blks_total, 2)
            ELSE NULL
        END AS progress_percent,
        NULL::bigint AS heap_blks_scanned,
        NULL::bigint AS heap_blks_total,
        NULL::bigint AS index_vacuum_count,
        NULL::bigint AS max_dead_tuples,
        NULL::bigint AS num_dead_tuples,
        progress.sample_blks_total::bigint AS blocks_total_alt,
        progress.sample_blks_scanned::bigint AS blocks_done_alt,
        NULL::bigint AS tuples_total,
        NULL::bigint AS tuples_done,
        NULL::text AS command
    FROM pg_stat_progress_analyze progress
    LEFT JOIN pg_class relation ON relation.oid = progress.relid
    LEFT JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
)
SELECT
    progress_rows.progress_type,
    progress_rows.pid,
    progress_rows.database_name,
    progress_rows.relation_name,
    progress_rows.phase,
    COALESCE(progress_rows.progress_percent, 0) AS progress_percent,
    COALESCE(progress_rows.blocks_done, 0) AS blocks_done,
    COALESCE(progress_rows.blocks_total, 0) AS blocks_total,
    progress_rows.heap_blks_scanned,
    progress_rows.heap_blks_total,
    progress_rows.index_vacuum_count,
    progress_rows.max_dead_tuples,
    progress_rows.num_dead_tuples,
    progress_rows.blocks_done_alt,
    progress_rows.blocks_total_alt,
    progress_rows.tuples_done,
    progress_rows.tuples_total,
    progress_rows.command,
    activity.usename,
    activity.application_name,
    activity.client_addr::text AS client_addr,
    activity.query_start,
    round(GREATEST(EXTRACT(EPOCH FROM (now() - activity.query_start)), 0)::numeric, 4) AS elapsed_time_seconds,
    activity.wait_event_type,
    activity.wait_event,
    activity.query
FROM progress_rows
LEFT JOIN pg_stat_activity activity ON activity.pid = progress_rows.pid
ORDER BY elapsed_time_seconds DESC NULLS LAST, progress_rows.progress_type, progress_rows.pid;
        """

    def progress_status(self):
        """获取 PostgreSQL 正在执行的维护任务进度"""
        return self._query_dbdiagnostic_sql(
            diagnostic_type="pgsql_progress",
            default_sql=self._pgsql_progress_sql(),
            db_name="postgres",
            timeout_ms=3000,
            required_columns=[
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
        )

    def _pgsql_wait_events_sql(self):
        return """
SELECT
    COALESCE(activity.state, 'unknown') AS state,
    COALESCE(activity.wait_event_type, 'None') AS wait_event_type,
    COALESCE(activity.wait_event, 'None') AS wait_event,
    count(*) AS session_count,
    round(
        max(
            CASE
                WHEN activity.wait_event IS NULL THEN 0
                ELSE GREATEST(EXTRACT(EPOCH FROM (now() - activity.state_change)), 0)
            END
        )::numeric,
        4
    ) AS max_wait_seconds,
    round(
        max(
            CASE
                WHEN activity.query_start IS NULL THEN 0
                ELSE GREATEST(EXTRACT(EPOCH FROM (now() - activity.query_start)), 0)
            END
        )::numeric,
        4
    ) AS max_query_seconds,
    count(*) FILTER (WHERE activity.state = 'active') AS active_count,
    count(*) FILTER (WHERE activity.state LIKE 'idle in transaction%%') AS idle_in_transaction_count,
    min(activity.query_start) AS oldest_query_start,
    min(activity.state_change) AS oldest_state_change,
    string_agg(DISTINCT activity.datname, ', ' ORDER BY activity.datname) AS database_names,
    string_agg(DISTINCT activity.usename, ', ' ORDER BY activity.usename) AS user_names,
    string_agg(DISTINCT activity.application_name, ', ' ORDER BY activity.application_name) AS application_names
FROM pg_stat_activity activity
WHERE activity.pid <> pg_backend_pid()
GROUP BY
    COALESCE(activity.state, 'unknown'),
    COALESCE(activity.wait_event_type, 'None'),
    COALESCE(activity.wait_event, 'None')
ORDER BY
    session_count DESC,
    max_wait_seconds DESC,
    max_query_seconds DESC,
    state,
    wait_event_type,
    wait_event;
        """

    def wait_event_summary(self):
        """获取 PostgreSQL 当前等待事件聚合"""
        return self._query_dbdiagnostic_sql(
            diagnostic_type="pgsql_wait_events",
            default_sql=self._pgsql_wait_events_sql(),
            db_name="postgres",
            timeout_ms=3000,
            required_columns=[
                "state",
                "wait_event_type",
                "wait_event",
                "session_count",
                "max_wait_seconds",
                "max_query_seconds",
            ],
        )

    def _pgsql_extensions_sql(self):
        return """
SELECT
    available.name AS extension_name,
    (installed.oid IS NOT NULL) AS installed,
    available.default_version,
    available.installed_version,
    installed.extversion AS installed_version_detail,
    namespace.nspname AS schema_name,
    installed.extrelocatable AS relocatable,
    installed.extconfig::text AS config_oids,
    installed.extcondition::text AS conditions,
    available.comment AS description
FROM pg_available_extensions available
LEFT JOIN pg_extension installed ON installed.extname = available.name
LEFT JOIN pg_namespace namespace ON namespace.oid = installed.extnamespace
ORDER BY
    (installed.oid IS NOT NULL) DESC,
    available.name;
        """

    def extension_status(self, db_name=""):
        """获取 PostgreSQL 当前数据库可用和已安装插件状态"""
        return self._query_dbdiagnostic_sql(
            diagnostic_type="pgsql_extensions",
            default_sql=self._pgsql_extensions_sql(),
            db_name=db_name,
            timeout_ms=3000,
            required_columns=[
                "extension_name",
                "installed",
                "default_version",
                "installed_version",
            ],
            template_db_name_override=False,
        )

    def processlist(self, command_type, **kwargs):
        """获取连接信息"""
        sql = """
            select psa.pid
                                ,concat('{',array_to_string(pg_blocking_pids(psa.pid),','),'}') block_pids
                                ,psa.leader_pid
                                ,psa.datname,psa.usename
                                ,psa.application_name
                                ,psa.state
                                ,psa.client_addr::text client_addr
                                ,round(GREATEST(EXTRACT(EPOCH FROM (now() - psa.query_start)),0)::numeric,4) elapsed_time_seconds
                ,GREATEST(now() - psa.query_start, INTERVAL '0 second') AS elapsed_time
                        ,(case when psa.leader_pid is null then psa.query end) query
                                ,psa.wait_event_type,psa.wait_event
                                ,psa.query_start
                                ,psa.backend_start
                                ,psa.client_hostname,psa.client_port
                                ,psa.xact_start transaction_start_time
                ,psa.state_change,psa.backend_xid,psa.backend_xmin,psa.backend_type
                                from  pg_stat_activity psa
                                where 1=1
                                AND psa.pid <> pg_backend_pid()
                                $state_not_idle$
                                order by (case 
                                    when psa.state='active' then 10 
                                    when psa.state like 'idle in transaction%' then 5
                                    when psa.state='idle' then 99 else 100 end)
                                    ,elapsed_time_seconds desc
                                ,(case when psa.leader_pid is not null then 1 else 0 end);
            """
        # escape
        command_type = self.escape_string(command_type)
        if not command_type:
            command_type = "Not Idle"

        replacements = {"$state_not_idle$": ""}
        if command_type == "Not Idle":
            replacements["$state_not_idle$"] = "and psa.state<>'idle'"

        return self._query_dbdiagnostic_sql(
            diagnostic_type="pgsql_processlist",
            default_sql=sql,
            db_name="postgres",
            timeout_ms=3000,
            replacements=replacements,
            required_columns=["pid", "datname", "usename", "state", "query"],
        )

    def get_long_transaction(self, thread_time=3):
        """获取 PostgreSQL 长事务和 idle in transaction 会话"""
        sql = """
SELECT
    psa.pid,
    psa.datname,
    psa.usename,
    psa.application_name,
    psa.client_addr::text AS client_addr,
    psa.client_hostname,
    psa.client_port,
    psa.state,
    psa.xact_start,
    round(GREATEST(EXTRACT(EPOCH FROM (now() - psa.xact_start)), 0)::numeric, 4) AS transaction_duration_seconds,
    GREATEST(now() - psa.xact_start, INTERVAL '0 second') AS transaction_duration,
    psa.query_start,
    round(GREATEST(EXTRACT(EPOCH FROM (now() - psa.query_start)), 0)::numeric, 4) AS query_duration_seconds,
    GREATEST(now() - psa.query_start, INTERVAL '0 second') AS query_duration,
    psa.wait_event_type,
    psa.wait_event,
    psa.backend_xid,
    psa.backend_xmin,
    psa.backend_type,
    psa.state_change,
    psa.query
FROM pg_stat_activity psa
WHERE psa.pid <> pg_backend_pid()
  AND psa.xact_start IS NOT NULL
  AND (
      psa.state LIKE 'idle in transaction%%'
      OR now() - psa.xact_start > make_interval(secs => $thread_time$)
  )
ORDER BY transaction_duration_seconds DESC, psa.pid;
        """
        return self._query_dbdiagnostic_sql(
            diagnostic_type="pgsql_trx",
            default_sql=sql,
            db_name="postgres",
            timeout_ms=3000,
            replacements={"$thread_time$": str(int(thread_time))},
            required_columns=["pid", "datname", "usename", "state", "xact_start", "query"],
        )

    def _pgsql_tablespace_sql(self, include_pagination=True):
        pagination_sql = "LIMIT $limit$ OFFSET $offset$" if include_pagination else ""
        return """
WITH relation_sizes AS (
    SELECT
        namespace.nspname AS schema_name,
        relation.relname AS table_name,
        pg_get_userbyid(relation.relowner) AS owner_name,
        pg_total_relation_size(relation.oid) AS total_size_bytes,
        pg_relation_size(relation.oid) AS table_size_bytes,
        pg_indexes_size(relation.oid) AS index_size_bytes,
        relation.reltuples AS relation_estimated_rows,
        GREATEST(
            pg_total_relation_size(relation.oid)
            - pg_relation_size(relation.oid)
            - pg_indexes_size(relation.oid),
            0
        ) AS toast_size_bytes,
        CASE
            WHEN relation.reltuples >= 0 THEN relation.reltuples::bigint
            ELSE COALESCE(stat.n_live_tup, 0)
        END AS estimated_rows,
        COALESCE(stat.n_dead_tup, 0) AS dead_tuples,
        CASE
            WHEN stat.relid IS NULL THEN '未采集'
            WHEN COALESCE(stat.n_live_tup, 0) = 0
             AND COALESCE(stat.n_dead_tup, 0) = 0
             AND stat.last_vacuum IS NULL
             AND stat.last_autovacuum IS NULL
             AND stat.last_analyze IS NULL
             AND stat.last_autoanalyze IS NULL THEN '统计为空'
            ELSE '已采集'
        END AS stats_status,
        stat.last_vacuum,
        stat.last_autovacuum,
        stat.last_analyze,
        stat.last_autoanalyze
    FROM pg_class relation
    JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
    LEFT JOIN pg_stat_user_tables stat ON stat.relid = relation.oid
    WHERE relation.relkind IN ('r', 'p', 'm')
      AND namespace.nspname NOT IN ('pg_catalog', 'information_schema')
      AND namespace.nspname NOT LIKE 'pg_toast%%'
      AND ($schema_name$ = '' OR namespace.nspname = $schema_name$)
)
SELECT
    schema_name,
    table_name,
    owner_name,
    total_size_bytes,
    pg_size_pretty(total_size_bytes) AS total_size,
    table_size_bytes,
    pg_size_pretty(table_size_bytes) AS table_size,
    index_size_bytes,
    pg_size_pretty(index_size_bytes) AS index_size,
    toast_size_bytes,
    pg_size_pretty(toast_size_bytes) AS toast_size,
    estimated_rows,
    dead_tuples,
    stats_status,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM relation_sizes
ORDER BY total_size_bytes DESC, schema_name, table_name
""" + pagination_sql

    def _schema_name_literal(self, schema_name):
        schema_name = (schema_name or "").strip()
        if not schema_name:
            return True, "''"
        if not re.match(r"^[A-Za-z0-9_.$-]+$", schema_name):
            return False, "Schema名称只允许字母、数字、下划线、点、美元符号和短横线"
        return True, "'{}'".format(schema_name.replace("'", "''"))

    def tablespace(self, offset=0, row_count=14, db_name="", schema_name=""):
        """获取 PostgreSQL 表级空间占用"""
        ok, schema_literal = self._schema_name_literal(schema_name)
        if not ok:
            result = ResultSet(full_sql="")
            result.error = schema_literal
            return result

        sql = self._pgsql_tablespace_sql(include_pagination=True)
        return self._query_dbdiagnostic_sql(
            diagnostic_type="pgsql_tablespace",
            default_sql=sql,
            db_name=db_name,
            timeout_ms=3000,
            replacements={
                "$limit$": str(int(row_count)),
                "$offset$": str(int(offset)),
                "$schema_name$": schema_literal,
            },
            required_columns=[
                "schema_name",
                "table_name",
                "total_size_bytes",
                "total_size",
            ],
            template_db_name_override=False,
        )

    def tablespace_count(self, db_name="", schema_name=""):
        """获取 PostgreSQL 表空间记录数"""
        ok, schema_literal = self._schema_name_literal(schema_name)
        if not ok:
            result = ResultSet(full_sql="")
            result.error = schema_literal
            return result

        template = self._get_dbdiagnostic_sql_template("pgsql_tablespace")
        if template:
            sql = template.sql
            query_db_name = db_name or template.db_name or "postgres"
            timeout_ms = template.timeout_ms or 3000
        else:
            sql = self._pgsql_tablespace_sql(include_pagination=False)
            query_db_name = db_name or "postgres"
            timeout_ms = 3000

        sql = (
            sql.replace("$limit$", "9223372036854775807")
            .replace("$offset$", "0")
            .replace("$schema_name$", schema_literal)
        )
        ok, message, safe_sql = self._validate_dbdiagnostic_sql(sql)
        if not ok:
            result = ResultSet(full_sql=sql)
            result.error = message
            return result

        count_sql = "SELECT count(*) AS total FROM ({}) dbdiagnostic_tablespace_count".format(
            safe_sql.rstrip(";")
        )
        return self.query(
            db_name=query_db_name or "postgres",
            sql=count_sql,
            max_execution_time=timeout_ms,
        )
