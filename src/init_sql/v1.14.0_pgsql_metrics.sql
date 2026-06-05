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
