# 出版社实时会话下载流程

## 适用场景

当用户已经在 Chrome、Edge 或 Firefox 中合法登录出版社或机构账号，且普通 HTTP 下载被验证页、登录页、动态会话或浏览器 PDF 阅读器拦住时，使用这套流程。支持 ScienceDirect/Elsevier、Wiley/AGU、Canadian Science Publishing、AIP 和 IEEE Xplore。

## 标准步骤

1. 启动带远程调试端口的独立 Chrome 会话。
2. 让用户在该窗口中手动：
   - 登录
   - 通过验证机器人页
   - 打开一篇目标文章
   - 点击 `View PDF`
   - 保持窗口打开
   Wiley/AGU 要在 DOI 实际跳转到的期刊子域名中完成一次 PDF 操作；CSP 和 AIP 如出现验证页也要在同一窗口处理。校外访问 IEEE 时先完成 IEEE / 机构登录，并从 `document/<arnumber>` 论文详情页进入。
3. 如有必要，用探测脚本先检查当前会话是否已经能暴露 PDF 元数据。
4. 用串行抓取脚本批量下载，条目之间保持 `5-8` 秒休眠。
5. 检查 `devtools_missing.csv`，只重试失败条目。

## 推荐命令

启动会话：

```bash
bash ~/.codex/skills/sciencedirect-live-session-fetcher/scripts/launch_chrome_clone_remote_debug_macos.sh \
  --direct-connection \
  --disable-extensions \
  --one-shot-profile \
  --remote-debugging-port 9222 \
  --url "https://www.sciencedirect.com/"
```

探测会话：

```bash
python3 ~/.codex/skills/sciencedirect-live-session-fetcher/scripts/attach_sciencedirect_remote_debug.py \
  --browser chrome \
  --debugger-address 127.0.0.1:9222
```

批量抓取：

```bash
bash ~/.codex/skills/sciencedirect-live-session-fetcher/scripts/run_devtools_sciencedirect_fetch_macos.sh \
  --input-csv /path/to/input.csv \
  --out-dir /path/to/out-dir \
  --download-wait-seconds 45 \
  --inter-item-sleep-seconds 6
```

## 关键注意点

- 浏览器窗口必须保持打开。
- 这套流程复用的是已授权会话，不提供新的访问权限。
- 如果页面仍在验证机器人页状态，不要强跑下载，先让用户在同一窗口中手动完成验证。
- 优先重试失败条目，不要反复整批重跑。
- `network_resource_non_pdf:200` 表示 PDF 形式的官方地址实际返回了 HTML 登录页、摘要页或验证页，不能保存成伪 PDF。
- Edge 内置 PDF 阅读器中的真实 PDF 会从其底层 iframe 目标提取；脚本仍会检查文件头必须为 `%PDF-`。
- 不导出或重放浏览器 Cookie，不自动处理验证码。
