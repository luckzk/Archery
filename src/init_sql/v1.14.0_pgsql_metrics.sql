-- SQL查询页用户自定义数据
CREATE TABLE IF NOT EXISTS sqlquery_knowledge (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(30) NOT NULL,
  user_display VARCHAR(50) NOT NULL DEFAULT '',
  name VARCHAR(64) NOT NULL,
  scene VARCHAR(64) NOT NULL DEFAULT '自定义',
  engines VARCHAR(255) NOT NULL DEFAULT '通用',
  `sql` LONGTEXT NOT NULL,
  instance_name VARCHAR(50) NOT NULL DEFAULT '',
  db_name VARCHAR(64) NOT NULL DEFAULT '',
  create_time DATETIME(6) NOT NULL,
  sys_time DATETIME(6) NOT NULL,
  KEY idx_sqlquery_knowledge_user_time (username, sys_time),
  KEY idx_sqlquery_knowledge_user_name (username, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 兼容早期临时存放在 query_log 的知识库记录，迁入正式表。
INSERT INTO sqlquery_knowledge
(username, user_display, name, scene, engines, `sql`, instance_name, db_name, create_time, sys_time)
SELECT
  q.username,
  q.user_display,
  COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(q.sqllog, '$.name')), ''), '未命名') AS name,
  COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(q.sqllog, '$.scene')), ''), '自定义') AS scene,
  COALESCE(NULLIF(REPLACE(REPLACE(REPLACE(JSON_UNQUOTE(JSON_EXTRACT(q.sqllog, '$.engines')), '[', ''), ']', ''), '"', ''), ''), '通用') AS engines,
  COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(q.sqllog, '$.sql')), ''), q.sqllog) AS `sql`,
  q.instance_name,
  q.db_name,
  q.create_time,
  q.sys_time
FROM query_log q
WHERE q.alias = '__sqlquery_knowledge__'
  AND JSON_VALID(q.sqllog)
  AND NOT EXISTS (
    SELECT 1
    FROM sqlquery_knowledge k
    WHERE k.username = q.username
      AND k.name = COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(q.sqllog, '$.name')), ''), '未命名')
      AND k.`sql` = COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(q.sqllog, '$.sql')), ''), q.sqllog)
	  );

CREATE TABLE IF NOT EXISTS sqlquery_favorite (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(30) NOT NULL,
  user_display VARCHAR(50) NOT NULL DEFAULT '',
  alias VARCHAR(64) NOT NULL DEFAULT '',
  `sql` LONGTEXT NOT NULL,
  instance_name VARCHAR(50) NOT NULL DEFAULT '',
  db_name VARCHAR(64) NOT NULL DEFAULT '',
  source_query_log_id INT NULL,
  create_time DATETIME(6) NOT NULL,
  sys_time DATETIME(6) NOT NULL,
  KEY idx_sqlquery_favorite_user_time (username, sys_time),
  KEY idx_sqlquery_favorite_user_alias (username, alias),
  KEY idx_sqlquery_favorite_user_source (username, source_query_log_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 兼容旧版 query_log.favorite 收藏，迁入正式收藏表。
INSERT INTO sqlquery_favorite
(username, user_display, alias, `sql`, instance_name, db_name, source_query_log_id, create_time, sys_time)
SELECT
  q.username,
  q.user_display,
  q.alias,
  q.sqllog,
  q.instance_name,
  q.db_name,
  q.id,
  q.create_time,
  q.sys_time
FROM query_log q
WHERE q.favorite = 1
  AND q.alias <> '__sqlquery_knowledge__'
  AND NOT EXISTS (
    SELECT 1
    FROM sqlquery_favorite f
    WHERE f.username = q.username
      AND f.source_query_log_id = q.id
  );

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
('pgsql', 'pgsql_trx', 'PgSQL事务信息默认SQL', '/dbdiagnostic/ 事务信息 PgSQL 默认 SQL，展示长事务和 idle in transaction 会话。', 'SELECT
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
    GREATEST(now() - psa.xact_start, INTERVAL ''0 second'') AS transaction_duration,
    psa.query_start,
    round(GREATEST(EXTRACT(EPOCH FROM (now() - psa.query_start)), 0)::numeric, 4) AS query_duration_seconds,
    GREATEST(now() - psa.query_start, INTERVAL ''0 second'') AS query_duration,
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
      psa.state LIKE ''idle in transaction%%''
      OR now() - psa.xact_start > make_interval(secs => $thread_time$)
  )
ORDER BY transaction_duration_seconds DESC, psa.pid;', 'postgres', 1, 3000, NOW(6), NOW(6)),
('pgsql', 'pgsql_tablespace', 'PgSQL Top表空间默认SQL', '/dbdiagnostic/ Top表空间 PgSQL 默认 SQL，展示表级空间占用和 vacuum/analyze 信息。', 'WITH relation_sizes AS (
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
            WHEN stat.relid IS NULL THEN ''未采集''
            WHEN COALESCE(stat.n_live_tup, 0) = 0
             AND COALESCE(stat.n_dead_tup, 0) = 0
             AND stat.last_vacuum IS NULL
             AND stat.last_autovacuum IS NULL
             AND stat.last_analyze IS NULL
             AND stat.last_autoanalyze IS NULL THEN ''统计为空''
            ELSE ''已采集''
        END AS stats_status,
        stat.last_vacuum,
        stat.last_autovacuum,
        stat.last_analyze,
        stat.last_autoanalyze
    FROM pg_class relation
    JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
    LEFT JOIN pg_stat_user_tables stat ON stat.relid = relation.oid
    WHERE relation.relkind IN (''r'', ''p'', ''m'')
      AND namespace.nspname NOT IN (''pg_catalog'', ''information_schema'')
      AND namespace.nspname NOT LIKE ''pg_toast%%''
      AND ($schema_name$ = '''' OR namespace.nspname = $schema_name$)
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
LIMIT $limit$ OFFSET $offset$', 'postgres', 1, 3000, NOW(6), NOW(6)),
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

INSERT IGNORE INTO dbdiagnostic_sql_template
(db_type, diagnostic_type, template_name, description, `sql`, db_name, enabled, timeout_ms, create_time, update_time)
VALUES
('pgsql', 'pgsql_replication', 'PgSQL复制状态默认SQL', '/dbdiagnostic/ 复制状态 PgSQL 默认 SQL，展示 pg_stat_replication 流复制状态和延迟。', 'SELECT
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
ORDER BY replication.application_name, replication.client_addr::text, replication.pid;', 'postgres', 1, 3000, NOW(6), NOW(6)),
('pgsql', 'pgsql_replication_slots', 'PgSQL复制Slot默认SQL', '/dbdiagnostic/ 复制Slot PgSQL 默认 SQL，展示 pg_replication_slots 状态和 WAL 保留风险。', 'SELECT
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
    to_jsonb(slot)->>''wal_status'' AS wal_status,
    NULLIF(to_jsonb(slot)->>''safe_wal_size'', '''')::numeric AS safe_wal_size
FROM pg_replication_slots slot
ORDER BY retained_wal_bytes DESC NULLS LAST, slot.slot_name;', 'postgres', 1, 3000, NOW(6), NOW(6));

INSERT IGNORE INTO dbdiagnostic_sql_template
(db_type, diagnostic_type, template_name, description, `sql`, db_name, enabled, timeout_ms, create_time, update_time)
VALUES
('pgsql', 'pgsql_vacuum', 'PgSQL Vacuum风险默认SQL', '/dbdiagnostic/ Vacuum风险 PgSQL 默认 SQL，展示表级 dead tuple、vacuum/analyze 时间和 xid 年龄风险。', 'WITH table_stats AS (
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
            WHEN relation.relfrozenxid::text = ''0'' THEN 0
            ELSE age(relation.relfrozenxid)
        END AS relfrozenxid_age,
        pg_total_relation_size(relation.oid) AS total_size_bytes,
        pg_size_pretty(pg_total_relation_size(relation.oid)) AS total_size
    FROM pg_class relation
    JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
    LEFT JOIN pg_stat_user_tables stat ON stat.relid = relation.oid
    WHERE relation.relkind IN (''r'', ''p'', ''m'')
      AND namespace.nspname NOT IN (''pg_catalog'', ''information_schema'')
      AND namespace.nspname NOT LIKE ''pg_toast%%''
      AND ($schema_name$ = '''' OR namespace.nspname = $schema_name$)
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
        WHEN relfrozenxid_age >= 1500000000 THEN ''xid高风险''
        WHEN dead_tuple_ratio >= 30 AND n_dead_tup >= 100000 THEN ''dead tuple高风险''
        WHEN last_autovacuum IS NULL AND last_vacuum IS NULL AND n_live_tup + n_dead_tup > 0 THEN ''未vacuum''
        WHEN dead_tuple_ratio >= 10 AND n_dead_tup >= 10000 THEN ''需要关注''
        ELSE ''正常''
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
LIMIT $limit$ OFFSET $offset$', 'postgres', 1, 3000, NOW(6), NOW(6));

INSERT IGNORE INTO dbdiagnostic_sql_template
(db_type, diagnostic_type, template_name, description, `sql`, db_name, enabled, timeout_ms, create_time, update_time)
VALUES
('pgsql', 'pgsql_progress', 'PgSQL Progress进度默认SQL', '/dbdiagnostic/ Progress进度 PgSQL 默认 SQL，展示正在运行的 vacuum、create index、analyze 等维护任务进度。', 'WITH progress_rows AS (
    SELECT
        ''vacuum''::text AS progress_type,
        progress.pid,
        progress.datname::text AS database_name,
        concat_ws(''.'', namespace.nspname, relation.relname)::text AS relation_name,
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
        ''create_index''::text AS progress_type,
        progress.pid,
        progress.datname::text AS database_name,
        concat_ws(''.'', namespace.nspname, relation.relname)::text AS relation_name,
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
        ''analyze''::text AS progress_type,
        progress.pid,
        progress.datname::text AS database_name,
        concat_ws(''.'', namespace.nspname, relation.relname)::text AS relation_name,
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
ORDER BY elapsed_time_seconds DESC NULLS LAST, progress_rows.progress_type, progress_rows.pid;', 'postgres', 1, 3000, NOW(6), NOW(6));

INSERT IGNORE INTO dbdiagnostic_sql_template
(db_type, diagnostic_type, template_name, description, `sql`, db_name, enabled, timeout_ms, create_time, update_time)
VALUES
('pgsql', 'pgsql_wait_events', 'PgSQL等待事件聚合默认SQL', '/dbdiagnostic/ 等待事件聚合 PgSQL 默认 SQL，基于 pg_stat_activity 聚合当前等待事件。', 'SELECT
    COALESCE(activity.state, ''unknown'') AS state,
    COALESCE(activity.wait_event_type, ''None'') AS wait_event_type,
    COALESCE(activity.wait_event, ''None'') AS wait_event,
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
    count(*) FILTER (WHERE activity.state = ''active'') AS active_count,
    count(*) FILTER (WHERE activity.state LIKE ''idle in transaction%%'') AS idle_in_transaction_count,
    min(activity.query_start) AS oldest_query_start,
    min(activity.state_change) AS oldest_state_change,
    string_agg(DISTINCT activity.datname, '', '' ORDER BY activity.datname) AS database_names,
    string_agg(DISTINCT activity.usename, '', '' ORDER BY activity.usename) AS user_names,
    string_agg(DISTINCT activity.application_name, '', '' ORDER BY activity.application_name) AS application_names
FROM pg_stat_activity activity
WHERE activity.pid <> pg_backend_pid()
GROUP BY
    COALESCE(activity.state, ''unknown''),
    COALESCE(activity.wait_event_type, ''None''),
    COALESCE(activity.wait_event, ''None'')
ORDER BY
    session_count DESC,
    max_wait_seconds DESC,
    max_query_seconds DESC,
    state,
    wait_event_type,
    wait_event;', 'postgres', 1, 3000, NOW(6), NOW(6));

INSERT IGNORE INTO dbdiagnostic_sql_template
(db_type, diagnostic_type, template_name, description, `sql`, db_name, enabled, timeout_ms, create_time, update_time)
VALUES
('pgsql', 'pgsql_indexes', 'PgSQL索引诊断默认SQL', '/dbdiagnostic/ 索引诊断 PgSQL 默认 SQL，展示 invalid index、未使用大索引和顺序扫描较高对象。', 'WITH index_stats AS (
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
    WHERE table_relation.relkind IN (''r'', ''p'', ''m'')
      AND namespace.nspname NOT IN (''pg_catalog'', ''information_schema'')
      AND namespace.nspname NOT LIKE ''pg_toast%%''
      AND ($schema_name$ = '''' OR namespace.nspname = $schema_name$)
),
diagnostic_rows AS (
    SELECT
        ''invalid_index''::text AS diagnostic_type,
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
        ''索引无效或未ready，需要检查并重建/删除''::text AS reason,
        1 AS priority
    FROM index_stats
    WHERE NOT is_valid OR NOT is_ready

    UNION ALL

    SELECT
        ''unused_index''::text AS diagnostic_type,
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
        ''索引扫描次数为0且占用空间较大，建议结合业务确认是否可删除''::text AS reason,
        2 AS priority
    FROM index_stats
    WHERE idx_scan = 0
      AND NOT is_primary
      AND index_size_bytes >= 1048576

    UNION ALL

    SELECT
        ''high_seq_scan''::text AS diagnostic_type,
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
        ''表顺序扫描次数较高，建议结合SQL和选择性评估索引设计''::text AS reason,
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
LIMIT $limit$ OFFSET $offset$', 'postgres', 1, 3000, NOW(6), NOW(6));

INSERT IGNORE INTO dbdiagnostic_sql_template
(db_type, diagnostic_type, template_name, description, `sql`, db_name, enabled, timeout_ms, create_time, update_time)
VALUES
('pgsql', 'pgsql_extensions', 'PgSQL插件展示默认SQL', '/dbdiagnostic/ 插件展示 PgSQL 默认 SQL，展示当前数据库可用和已安装 extension。', 'SELECT
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
    available.name;', 'postgres', 1, 3000, NOW(6), NOW(6));


-- PgSQL 手动迁移助手任务表
CREATE TABLE IF NOT EXISTS pgsql_migration_task (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  source_instance_id INT NOT NULL,
  target_instance_id INT NOT NULL,
  schemas_json LONGTEXT NOT NULL,
  tables_json LONGTEXT NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'draft',
  description LONGTEXT NOT NULL,
  user_name VARCHAR(30) NOT NULL DEFAULT '',
  user_display VARCHAR(50) NOT NULL DEFAULT '',
  create_time DATETIME(6) NOT NULL,
  update_time DATETIME(6) NOT NULL,
  KEY idx_pgsql_migration_source_instance (source_instance_id),
  KEY idx_pgsql_migration_target_instance (target_instance_id),
  KEY idx_pgsql_migration_status (status),
  CONSTRAINT fk_pgsql_migration_source_instance FOREIGN KEY (source_instance_id) REFERENCES sql_instance(id) ON DELETE CASCADE,
  CONSTRAINT fk_pgsql_migration_target_instance FOREIGN KEY (target_instance_id) REFERENCES sql_instance(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS pgsql_migration_task_log (
  id INT AUTO_INCREMENT PRIMARY KEY,
  task_id INT NOT NULL,
  operation VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  message LONGTEXT NOT NULL,
  details_json LONGTEXT NOT NULL,
  start_time DATETIME(6) NOT NULL,
  finish_time DATETIME(6) NULL,
  KEY idx_pgsql_migration_log_task (task_id),
  CONSTRAINT fk_pgsql_migration_log_task FOREIGN KEY (task_id) REFERENCES pgsql_migration_task(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS pgsql_migration_sequence_result (
  id INT AUTO_INCREMENT PRIMARY KEY,
  task_id INT NOT NULL,
  operation VARCHAR(20) NOT NULL,
  sequence_schema VARCHAR(64) NOT NULL,
  sequence_name VARCHAR(128) NOT NULL,
  table_schema VARCHAR(64) NOT NULL DEFAULT '',
  table_name VARCHAR(128) NOT NULL DEFAULT '',
  column_name VARCHAR(128) NOT NULL DEFAULT '',
  source_last_value BIGINT NULL,
  target_current_value BIGINT NULL,
  target_value BIGINT NULL,
  should_apply TINYINT(1) NOT NULL DEFAULT 0,
  reason VARCHAR(255) NOT NULL DEFAULT '',
  setval_sql LONGTEXT NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT '',
  error LONGTEXT NOT NULL,
  create_time DATETIME(6) NOT NULL,
  KEY idx_pgsql_migration_sequence_task (task_id),
  CONSTRAINT fk_pgsql_migration_sequence_task FOREIGN KEY (task_id) REFERENCES pgsql_migration_task(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS pgsql_migration_data_check_result (
  id INT AUTO_INCREMENT PRIMARY KEY,
  task_id INT NOT NULL,
  schema_name VARCHAR(64) NOT NULL,
  table_name VARCHAR(128) NOT NULL,
  status VARCHAR(20) NOT NULL,
  checks_json LONGTEXT NOT NULL,
  create_time DATETIME(6) NOT NULL,
  KEY idx_pgsql_migration_data_check_task (task_id),
  CONSTRAINT fk_pgsql_migration_data_check_task FOREIGN KEY (task_id) REFERENCES pgsql_migration_task(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- SQLQuery 用户界面偏好
CREATE TABLE IF NOT EXISTS sqlquery_preference (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(30) NOT NULL,
  user_display VARCHAR(50) NOT NULL DEFAULT '',
  theme VARCHAR(20) NOT NULL DEFAULT 'archery',
  resource_tab VARCHAR(20) NOT NULL DEFAULT 'table',
  mysql_tab VARCHAR(20) NOT NULL DEFAULT 'knowledge',
  create_time DATETIME(6) NOT NULL,
  sys_time DATETIME(6) NOT NULL,
  UNIQUE KEY uk_sqlquery_preference_username (username),
  KEY idx_sqlquery_preference_sys_time (sys_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- PgSQL 手动迁移助手权限
SET @content_type_id=(SELECT id FROM django_content_type WHERE app_label='sql' AND model='permission');
INSERT IGNORE INTO auth_permission (name, content_type_id, codename)
VALUES
  ('菜单 PgSQL迁移助手', @content_type_id, 'menu_pgsql_migration'),
  ('管理PgSQL迁移准备任务', @content_type_id, 'pgsql_migration_mgt'),
  ('执行PgSQL迁移检查和设置', @content_type_id, 'pgsql_migration_execute');
