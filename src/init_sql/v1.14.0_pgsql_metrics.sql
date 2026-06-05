-- PostgreSQL 实时指标定义表
CREATE TABLE IF NOT EXISTS pgsql_metric_definition (
  id INT AUTO_INCREMENT PRIMARY KEY,
  metric_key VARCHAR(100) NOT NULL UNIQUE,
  metric_name VARCHAR(100) NOT NULL,
  description LONGTEXT NOT NULL,
  sql LONGTEXT NOT NULL,
  db_name VARCHAR(64) NOT NULL DEFAULT '',
  value_column VARCHAR(100) NOT NULL DEFAULT 'value',
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  timeout_ms INT UNSIGNED NOT NULL DEFAULT 3000,
  create_time DATETIME(6) NOT NULL,
  update_time DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- PostgreSQL 指标指定实例关系表，未指定时对所有可见 PostgreSQL 实例可用
CREATE TABLE IF NOT EXISTS pgsql_metric_definition_instances (
  id INT AUTO_INCREMENT PRIMARY KEY,
  pgsqlmetricdefinition_id INT NOT NULL,
  instance_id INT NOT NULL,
  UNIQUE KEY uniq_pgsql_metric_instance_scope (pgsqlmetricdefinition_id, instance_id),
  KEY idx_pgsql_metric_scope_instance (instance_id),
  CONSTRAINT fk_pgsql_metric_scope_metric FOREIGN KEY (pgsqlmetricdefinition_id) REFERENCES pgsql_metric_definition(id) ON DELETE CASCADE,
  CONSTRAINT fk_pgsql_metric_scope_instance FOREIGN KEY (instance_id) REFERENCES sql_instance(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 内置 PostgreSQL 指标模板，可在后台手工维护
-- 输入约定：页面选择 PostgreSQL 实例，系统在该实例上执行单条 SELECT；采集数据库为空时使用实例默认库。
-- 输出约定：建议返回 value 列作为指标值，也可以通过 value_column 指定其他列；未命中时取首行首列。
INSERT IGNORE INTO pgsql_metric_definition
(metric_key, metric_name, description, sql, db_name, value_column, enabled, timeout_ms, create_time, update_time)
VALUES
('pgsql_lock_waiting_count', '锁等待数量', '当前处于锁等待状态的会话数量。', 'SELECT count(*) AS value FROM pg_stat_activity WHERE wait_event_type = ''Lock'';', '', 'value', 1, 3000, NOW(6), NOW(6)),
('pgsql_deadlocks_total', '死锁累计次数', '当前数据库 pg_stat_database.deadlocks 累计值。', 'SELECT sum(deadlocks) AS value FROM pg_stat_database;', '', 'value', 1, 3000, NOW(6), NOW(6)),
('pgsql_connections_active', '活跃连接数', '当前 active 状态连接数。', 'SELECT count(*) AS value FROM pg_stat_activity WHERE state = ''active'';', '', 'value', 1, 3000, NOW(6), NOW(6)),
('pgsql_connections_total', '总连接数', '当前 pg_stat_activity 连接总数。', 'SELECT count(*) AS value FROM pg_stat_activity;', '', 'value', 1, 3000, NOW(6), NOW(6)),
('pgsql_long_transaction_count', '长事务数量', '事务持续超过 10 分钟的会话数量。', 'SELECT count(*) AS value FROM pg_stat_activity WHERE xact_start IS NOT NULL AND now() - xact_start > interval ''10 minutes'';', '', 'value', 1, 3000, NOW(6), NOW(6)),
('pgsql_idle_in_transaction_count', 'idle in transaction 数量', '当前 idle in transaction 状态会话数量。', 'SELECT count(*) AS value FROM pg_stat_activity WHERE state = ''idle in transaction'';', '', 'value', 1, 3000, NOW(6), NOW(6)),
('pgsql_replication_lag_bytes_max', '复制 WAL 延迟最大字节数', '基于 pg_stat_replication 计算的最大 WAL 发送延迟。', 'SELECT COALESCE(max(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)), 0) AS value FROM pg_stat_replication;', '', 'value', 1, 3000, NOW(6), NOW(6)),
('pgsql_replication_client_count', '复制客户端数量', '当前 pg_stat_replication 复制客户端数量。', 'SELECT count(*) AS value FROM pg_stat_replication;', '', 'value', 1, 3000, NOW(6), NOW(6)),
('pgsql_subscription_disabled_count', '禁用订阅数量', '当前禁用的逻辑订阅数量。', 'SELECT count(*) AS value FROM pg_subscription WHERE NOT subenabled;', '', 'value', 1, 3000, NOW(6), NOW(6));

-- PostgreSQL 参数展示SQL合并到实例参数模板配置表
-- MySQL 模板仍使用 variable_name/default_value/editable/valid_values/description 配置具体参数。
-- PostgreSQL 模板使用 variable_name 作为配置名称，param_query_sql 作为参数展示SQL。
DROP PROCEDURE IF EXISTS add_param_template_pgsql_query_columns;
DELIMITER //
CREATE PROCEDURE add_param_template_pgsql_query_columns()
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'param_template'
      AND COLUMN_NAME = 'param_query_sql'
  ) THEN
    ALTER TABLE param_template ADD COLUMN param_query_sql LONGTEXT NOT NULL;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'param_template'
      AND COLUMN_NAME = 'param_query_db_name'
  ) THEN
    ALTER TABLE param_template ADD COLUMN param_query_db_name VARCHAR(64) NOT NULL DEFAULT '';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'param_template'
      AND COLUMN_NAME = 'param_query_enabled'
  ) THEN
    ALTER TABLE param_template ADD COLUMN param_query_enabled TINYINT(1) NOT NULL DEFAULT 1;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'param_template'
      AND COLUMN_NAME = 'param_query_timeout_ms'
  ) THEN
    ALTER TABLE param_template ADD COLUMN param_query_timeout_ms INT UNSIGNED NOT NULL DEFAULT 3000;
  END IF;
END//
DELIMITER ;
CALL add_param_template_pgsql_query_columns();
DROP PROCEDURE IF EXISTS add_param_template_pgsql_query_columns;

-- 内置 PostgreSQL 参数展示SQL，可在后台 /admin/sql/paramtemplate/ 手工维护。
-- 输出约定：至少返回 variable_name、runtime_value 两列；可选返回 default_value、valid_values、description。
INSERT IGNORE INTO param_template
(db_type, variable_name, default_value, editable, valid_values, description, param_query_sql, param_query_db_name, param_query_enabled, param_query_timeout_ms, create_time, sys_time)
VALUES
('pgsql', 'pg_settings参数展示', '', 0, '', '基于 pg_settings 展示 PostgreSQL 当前实例参数。', 'SELECT name AS variable_name, setting AS runtime_value, COALESCE(boot_val, reset_val, '''') AS default_value, CASE WHEN enumvals IS NOT NULL THEN array_to_string(enumvals, ''|'') WHEN min_val IS NOT NULL OR max_val IS NOT NULL THEN concat(''['', COALESCE(min_val, ''''), ''-'', COALESCE(max_val, ''''), '']'') ELSE '''' END AS valid_values, COALESCE(short_desc, '''') AS description FROM pg_settings ORDER BY name', '', 1, 3000, NOW(6), NOW(6));

-- DB诊断会话管理自定义SQL配置表
CREATE TABLE IF NOT EXISTS dbdiagnostic_sql_template (
  id INT AUTO_INCREMENT PRIMARY KEY,
  db_type VARCHAR(20) NOT NULL,
  diagnostic_type VARCHAR(50) NOT NULL,
  template_name VARCHAR(100) NOT NULL,
  description LONGTEXT NOT NULL,
  `sql` LONGTEXT NOT NULL,
  db_name VARCHAR(64) NOT NULL DEFAULT '',
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  timeout_ms INT UNSIGNED NOT NULL DEFAULT 3000,
  create_time DATETIME(6) NOT NULL,
  update_time DATETIME(6) NOT NULL,
  UNIQUE KEY uniq_dbdiagnostic_sql_template (db_type, diagnostic_type, template_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- PgSQL 会话管理默认自定义SQL，可在后台 /admin/sql/dbdiagnosticsqltemplate/ 维护。
INSERT IGNORE INTO dbdiagnostic_sql_template
(db_type, diagnostic_type, template_name, description, `sql`, db_name, enabled, timeout_ms, create_time, update_time)
VALUES
('pgsql', 'pgsql_processlist', 'PgSQL进程状态默认SQL', '/dbdiagnostic/ 进程状态 PgSQL 默认 SQL。', '            select psa.pid
                                ,concat(''{'',array_to_string(pg_blocking_pids(psa.pid),'',''),''}'') block_pids
                                ,psa.leader_pid
                                ,psa.datname,psa.usename
                                ,psa.application_name
                                ,psa.state
                                ,psa.client_addr::text client_addr
                                ,round(GREATEST(EXTRACT(EPOCH FROM (now() - psa.query_start)),0)::numeric,4) elapsed_time_seconds
                ,GREATEST(now() - psa.query_start, INTERVAL ''0 second'') AS elapsed_time
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
                                    when psa.state=''active'' then 10 
                                    when psa.state like ''idle in transaction%'' then 5
                                    when psa.state=''idle'' then 99 else 100 end)
                                    ,elapsed_time_seconds desc
                                ,(case when psa.leader_pid is not null then 1 else 0 end);', 'postgres', 1, 3000, NOW(6), NOW(6)),
('pgsql', 'pgsql_trxandlocks', 'PgSQL锁信息默认SQL', '/dbdiagnostic/ 锁信息 PgSQL 默认 SQL，包含阻塞链。', 'WITH RECURSIVE lock_edges AS (
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
        array_to_string(path, '' -> '') AS blocking_chain
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
        ''/'',
        waiting_locks.locktype,
        NULLIF(waiting_locks.relation::regclass::text, ''''),
        CASE WHEN waiting_locks.page IS NOT NULL THEN ''page='' || waiting_locks.page END,
        CASE WHEN waiting_locks.tuple IS NOT NULL THEN ''tuple='' || waiting_locks.tuple END,
        CASE WHEN waiting_locks.transactionid IS NOT NULL THEN ''xid='' || waiting_locks.transactionid END,
        CASE WHEN waiting_locks.virtualxid IS NOT NULL THEN ''vxid='' || waiting_locks.virtualxid END,
        CASE WHEN waiting_locks.classid IS NOT NULL THEN ''classid='' || waiting_locks.classid END,
        CASE WHEN waiting_locks.objid IS NOT NULL THEN ''objid='' || waiting_locks.objid END,
        CASE WHEN waiting_locks.objsubid IS NOT NULL THEN ''objsubid='' || waiting_locks.objsubid END
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
ORDER BY waiting_duration_seconds DESC, waiting_locks.pid, waiting_locks.blocking_pid;', 'postgres', 1, 3000, NOW(6), NOW(6));


INSERT IGNORE INTO dbdiagnostic_sql_template
(db_type, diagnostic_type, template_name, description, `sql`, db_name, enabled, timeout_ms, create_time, update_time)
VALUES
('pgsql', 'pgsql_pubsub', 'PgSQL发布订阅默认SQL', '/dbdiagnostic/ 发布订阅 PgSQL 默认 SQL，展示 pg_publication、pg_publication_tables、pg_subscription 和 pg_stat_subscription 信息。', 'WITH publication_rows AS (
    SELECT
        ''publication''::text AS object_type,
        publication.pubname::text AS object_name,
        ''true''::text AS enabled,
        pg_get_userbyid(publication.pubowner)::text AS owner_name,
        current_database()::text AS database_name,
        publication.pubname::text AS publication_names,
        CASE
            WHEN publication.puballtables THEN ''ALL TABLES''
            ELSE concat_ws(''.'', publication_tables.schemaname, publication_tables.tablename)
        END::text AS table_name,
        concat_ws(
            '','',
            CASE WHEN publication.pubinsert THEN ''insert'' END,
            CASE WHEN publication.pubupdate THEN ''update'' END,
            CASE WHEN publication.pubdelete THEN ''delete'' END,
            CASE WHEN publication.pubtruncate THEN ''truncate'' END
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
        ''subscription''::text AS object_type,
        subscription.subname::text AS object_name,
        subscription.subenabled::text AS enabled,
        pg_get_userbyid(subscription.subowner)::text AS owner_name,
        current_database()::text AS database_name,
        array_to_string(subscription.subpublications, '', '')::text AS publication_names,
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
        regexp_replace(subscription.subconninfo, ''password=[^ ]+'', ''password=****'', ''gi'')::text AS conninfo
    FROM pg_subscription subscription
    LEFT JOIN pg_stat_subscription subscription_stat
        ON subscription_stat.subid = subscription.oid
)
SELECT *
FROM publication_rows
UNION ALL
SELECT *
FROM subscription_rows
ORDER BY object_type, object_name, table_name NULLS FIRST;', 'postgres', 1, 3000, NOW(6), NOW(6));
