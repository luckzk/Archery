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
        schema_name = kwargs.get("schema_name")
        sql = f"""SELECT table_name
        FROM information_schema.tables
        where table_schema =%(schema_name)s;"""
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
    ):
        template = self._get_dbdiagnostic_sql_template(diagnostic_type)
        if template:
            sql = template.sql
            db_name = template.db_name or db_name
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
