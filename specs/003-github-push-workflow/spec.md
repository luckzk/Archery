# GitHub推送流程

## 背景

本项目代码来自 Archery 源项目 fork。当前开发在本机仓库 `/home/opc/node/Archery` 中进行，功能分支推送到个人 GitHub fork，再按需要从 GitHub 发起 Pull Request。

这份文档只描述 GitHub 推送流程。具体功能开发逻辑放在各自功能文档里。

## 当前仓库信息

项目目录：

```bash
cd /home/opc/node/Archery
```

当前开发分支：

```text
feature/pgsql-zabbix-metrics
```

远程仓库：

```text
origin   https://github.com/luckzk/Archery.git
upstream https://github.com/hhyo/Archery.git
```

含义：

- `origin` 是个人 fork，用来推送自己的开发分支。
- `upstream` 是源项目，不要直接推送。

## 推送原则

日常开发只推送到：

```bash
origin
```

不要推送到：

```bash
upstream
```

当前功能分支推送命令：

```bash
git push -u origin feature/pgsql-zabbix-metrics
```

已经设置 upstream 后，后续在该分支上可以直接：

```bash
git push
```

## 第一次推送完整流程

确认当前分支：

```bash
git branch --show-current
```

确认改动：

```bash
git status --short --branch
```

暂存全部改动：

```bash
git add .
```

提交：

```bash
git commit -m "feat: add realtime PostgreSQL metrics dashboard"
```

推送到个人 fork：

```bash
git push -u origin feature/pgsql-zabbix-metrics
```

推送成功后，GitHub 会提示 Pull Request 地址，类似：

```text
https://github.com/luckzk/Archery/pull/new/feature/pgsql-zabbix-metrics
```

## Token推送方式

当前远程地址是 HTTPS：

```text
https://github.com/luckzk/Archery.git
```

因此推送时使用 GitHub token 作为密码。

推送时如果提示：

```text
Username for 'https://github.com':
Password for 'https://luckzk@github.com':
```

输入：

```text
Username: luckzk
Password: GitHub token
```

注意：`Password` 不是 GitHub 登录密码，是 GitHub Personal Access Token。

## 获取GitHub Token

GitHub 页面：

```text
https://github.com/settings/tokens
```

推荐使用 Fine-grained token：

```text
Fine-grained personal access tokens -> Generate new token
```

建议配置：

- Token name：`archery-dev-push`
- Resource owner：`luckzk`
- Repository access：只选择 `luckzk/Archery`
- Repository permissions：`Contents` 设置为 `Read and write`
- Expiration：按需要选择，例如 30 天或 90 天

生成后复制 token。token 只显示一次，不要发给别人，不要提交到代码仓库。

## 凭据保存

为了避免每次 push 都输入 token，可以启用 Git 凭据保存：

```bash
git config --global credential.helper store
```

执行后，再推送一次并输入用户名和 token：

```bash
git push
```

之后 Git 会把凭据保存到：

```text
~/.git-credentials
```

后续同一个 HTTPS remote 推送不再提示 token。

安全注意：`credential.helper store` 是明文保存 token。只建议在自己可信的机器上使用。

## 已验证的推送结果

当前分支已经成功推送：

```text
feature/pgsql-zabbix-metrics -> origin/feature/pgsql-zabbix-metrics
```

成功输出示例：

```text
[new branch] feature/pgsql-zabbix-metrics -> feature/pgsql-zabbix-metrics
branch 'feature/pgsql-zabbix-metrics' set up to track 'origin/feature/pgsql-zabbix-metrics'.
Everything up-to-date
```

`Everything up-to-date` 表示本地分支和 GitHub 远程分支已经一致，没有新的提交需要推送。

## 日常继续开发后的推送

以后继续改代码时，常用流程：

```bash
cd /home/opc/node/Archery
git status --short --branch
git add .
git commit -m "你的提交说明"
git push
```

如果只是查看是否有未推送提交：

```bash
git status --short --branch
```

如果显示类似：

```text
## feature/pgsql-zabbix-metrics...origin/feature/pgsql-zabbix-metrics [ahead 1]
```

说明本地有 1 个提交还没推送，执行：

```bash
git push
```

## 查看远程地址

```bash
git remote -v
```

期望输出：

```text
origin   https://github.com/luckzk/Archery.git (fetch)
origin   https://github.com/luckzk/Archery.git (push)
upstream https://github.com/hhyo/Archery.git (fetch)
upstream https://github.com/hhyo/Archery.git (push)
```

## 如果Token过期

如果 token 过期，push 可能失败或重新提示输入密码。

处理方式：

1. 到 GitHub 重新生成 token。
2. 删除旧凭据或直接覆盖保存。
3. 再执行一次 push，输入新 token。

删除已保存凭据：

```bash
rm ~/.git-credentials
```

然后重新推送：

```bash
git push
```

按提示输入用户名和新 token。

## 可选：改用SSH推送

如果以后不想用 token，也可以改成 SSH。

生成 SSH key：

```bash
ssh-keygen -t ed25519 -C "你的GitHub邮箱"
```

查看公钥：

```bash
cat ~/.ssh/id_ed25519.pub
```

把输出内容添加到 GitHub：

```text
GitHub -> Settings -> SSH and GPG keys -> New SSH key
```

测试：

```bash
ssh -T git@github.com
```

切换 remote：

```bash
git remote set-url origin git@github.com:luckzk/Archery.git
```

推送：

```bash
git push
```

## 常见问题

### `fatal: could not read Username for 'https://github.com'`

说明当前环境无法交互式输入 GitHub 用户名，或者没有配置凭据。可以手工执行 `git push` 输入用户名和 token，或配置 SSH remote。

### `Everything up-to-date`

说明当前没有新提交需要推送，不是错误。

### 推到了哪里

只要命令是：

```bash
git push origin feature/pgsql-zabbix-metrics
```

就是推到个人 fork：

```text
https://github.com/luckzk/Archery.git
```

不会推到源项目 `hhyo/Archery`。
