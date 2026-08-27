# DeepSeek 密钥配置

Money Radar 会优先从环境变量 `DEEPSEEK_API_KEY` 读取密钥；本地没有环境变量时，才读取项目根目录的 `deepseek.env`。密钥绝不提交到 Git。

## 本地定时任务

在实际自动化代码目录中填写此文件：

```text
/Users/lizhu/Automations/money-radar/repo/deepseek.env
```

文件只有一行：

```text
DEEPSEEK_API_KEY=你的DeepSeek密钥
```

该文件与 `README.md`、`money_radar/` 同级，权限已设置为仅当前用户可读写。每日任务会在拉取代码后从这里读取密钥；它是被 Git 忽略的未跟踪文件，不会被同步到 GitHub。

如果你直接在开发目录运行，也可填写同级文件：

```text
/Volumes/T7/CCR1/money-radar/deepseek.env
```

## GitHub Actions

1. 打开仓库 Settings → Secrets and variables → Actions。
2. 新建 repository secret，名称必须是 `DEEPSEEK_API_KEY`。
3. 将 DeepSeek 密钥作为 secret 值保存。
4. 在工作流执行 Money Radar 命令的步骤中传入：

```yaml
env:
  DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
```

GitHub Actions 无法直接写入这台 Mac 的 iCloud 文件夹。云端工作流应把日报作为 artifact、提交到仓库，或发送到另一个已配置的远端目的地；本地定时任务才会写入 iCloud。

## 验证

填好本地文件后，不要在终端打印密钥。直接运行日报导出；报告中若在英文、中文原文下方出现 `**分析**：`，就表示 DeepSeek 已成功工作。
