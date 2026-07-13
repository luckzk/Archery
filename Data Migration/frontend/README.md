# PostgreSQL 迁移控制台前端

前端使用 Vite + React + TypeScript + Ant Design。

## 安装

```bash
cd frontend
HTTP_PROXY=http://127.0.0.1:8001 HTTPS_PROXY=http://127.0.0.1:8001 npm install
```

依赖安装在 `frontend/node_modules`，不会和 VitePress 文档站混在一起。

## 启动

```bash
cd frontend
npm run dev
```

默认地址：

```text
http://127.0.0.1:5174
```

开发服务会把 `/api` 和 `/health` 代理到：

```text
http://127.0.0.1:8000
```

## 构建

```bash
npm run build
```
