# 本地 CTP 仿真（SimNow）

聚宽模拟是步骤 1 的官方线上账本。SimNow 属于**步骤 2**：单条聚宽模拟满 3 个月、观察合格，且你提供阿里云之后，才做自动执行。现在只保留登录/查账能力测试。门槛见 [gates.md](gates.md)。

默认 dry-run。`environment: live` 会被拒绝。步骤 2 之前不要 `--send`，也不要注册会自动发单的计划任务。

## 一次配好

1. 在 [simnow.com.cn](https://www.simnow.com.cn/) 开仿真账号，记下投资者账号和密码。入金用官网的仿真入金。
2. 本机 Python 3.12 用 `openctp-ctp`（不必装 vn.py）。Windows 若改用 vn.py，需 [VC++ 可再发行组件](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)。
3. 复制模板，填账号。路径在仓库外：

```
%USERPROFILE%\.cursor\secrets\ctp_simnow.json
```

模板：`ctp/config.example.json`。不要把填好的文件放进 git。可用环境变量 `CTP_CONFIG` 指向别的路径。

4. 可选依赖（不进主 `requirements.txt`）：

```powershell
pip install -r requirements-ctp.txt
```

Clash 的 `HTTP_PROXY=127.0.0.1:7890` 只给 `gh`/`git` 用；CTP 是 TCP，进程里会清掉 HTTP 代理。

## 步骤 2 之前本机只测登录

```powershell
python run_ctp_probe.py
python run_fq002_ctp.py
python run_fq002_ctp.py --connect
```

- 无参数：只打印计划（dry-run）。
- `--connect`：登录查账，仍不下单。
- `--send`：留给步骤 2。现在不要用计划任务自动 `--send`。

日志（gitignore）：`data/processed/fq002_ctp.log`、`fq002_ctp_heartbeat.json`。

可选 dry-run 任务（已登录才跑，不唤醒电脑）：

```powershell
powershell -File scripts\register_fq002_task.ps1
schtasks /Delete /TN FQ002-SimNow /F
```

## 步骤 2：阿里云 + SimNow 自动（资源你来开）

国内 ECS/轻量，出站 TCP 到下面前置。cron 跑 `run_fq002_ctp.py --refresh --send`。密钥只放服务器本地，禁止 GitHub。FQ-002 满 3 个月（约 2026-12-02）且观察合格后再做。

## 前置地址（以官网为准）

电信示例（看穿式握手 `counter_env` 填 **实盘**，不要填「测试」，否则常见 4097）：

- 交易 `tcp://182.254.243.31:30001`
- 行情 `tcp://182.254.243.31:30011`
- 7×24 测试改 `40001` / `40011`

`environment` 只能是 `simnow` 或 `broker_sim`。

## 不要做的事

- **账号、密码、API key、token 禁止进 git、禁止 `git push`。** 只放 `%USERPROFILE%\.cursor\secrets\` 或阿里云本地文件。
- 不要把密码写进 README 或聊天记录。
- 步骤 1 期间不要对 SimNow 自动发单。
- 不要改 `environment: live`。实盘是步骤 3，SimNow 自动跑稳后再评估。
- 聚宽 paper 盈亏进 [paper/leaderboard.md](../paper/leaderboard.md)；SimNow 仿真盈亏不进该表。
