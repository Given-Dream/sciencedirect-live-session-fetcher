# 中文流程说明

## 适用场景

当用户已经在 Microsoft Edge 中合法登录 ScienceDirect 或 Elsevier，且普通 HTTP 下载被验证机器人页、登录页或浏览器会话限制拦住时，使用这套流程。

## 标准步骤

1. 启动带远程调试端口的独立 Edge 会话。
2. 让用户在该窗口中手动：
   - 登录
   - 通过验证机器人页
   - 打开一篇目标文章
   - 点击 `View PDF`
   - 保持窗口打开
3. 如有必要，用探测脚本先检查当前会话是否已经能暴露 PDF 元数据。
4. 用串行抓取脚本批量下载，条目之间保持 `5-8` 秒休眠。
5. 检查 `devtools_missing.csv`，只重试失败条目。

## 推荐命令

启动会话：

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\SoungYu\.codex\skills\sciencedirect-live-session-fetcher\scripts\launch_edge_clone_remote_debug.ps1
```

探测会话：

```powershell
python C:\Users\SoungYu\.codex\skills\sciencedirect-live-session-fetcher\scripts\attach_sciencedirect_remote_debug.py --debugger-address 127.0.0.1:9222
```

批量抓取：

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\SoungYu\.codex\skills\sciencedirect-live-session-fetcher\scripts\run_devtools_sciencedirect_fetch.ps1 `
  -InputCsv C:\path\to\input.csv `
  -OutDir C:\path\to\out-dir `
  -InterItemSleepSeconds 6
```

## 关键注意点

- 浏览器窗口必须保持打开。
- 这套流程复用的是已授权会话，不提供新的访问权限。
- 如果页面仍在验证机器人页状态，不要强跑下载，先让用户在同一窗口中手动完成验证。
- 优先重试失败条目，不要反复整批重跑。
