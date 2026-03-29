# ScienceDirect 实时会话抓取器

这是一套可复用脚本和 Codex skill，用来在**已经合法登录并通过验证机器人页**的 Microsoft Edge 会话里，串行下载 ScienceDirect/Elsevier 的 PDF。

它适合下面这类情况：

- 你已经拥有个人账号或机构授权访问
- 直接用 `requests`、`curl` 或普通 HTTP 抓取会被验证机器人页、登录页或浏览器专属流程拦住
- 你可以手动完成登录、通过验证机器人页，并把 Edge 窗口保持打开

这套流程不会创建新的访问权限，也不会绕过付费墙。它只是复用你**已经通过授权的浏览器会话**。

## 包含内容

- `scripts/launch_edge_clone_remote_debug.ps1`
  启动一个独立的 Edge 会话，并打开远程调试端口。
- `scripts/attach_sciencedirect_remote_debug.py`
  探测当前会话是否已经能读取 ScienceDirect 页面里的 PDF 元数据。
- `scripts/devtools_sciencedirect_serial_fetch.py`
  串行抓取主程序，一次处理一篇，并在条目之间休眠几秒。
- `scripts/run_devtools_sciencedirect_fetch.ps1`
  PowerShell 包装器，方便直接批量运行。
- `examples/input-template.csv`
  最小输入模板。
- `codex-skill/`
  一份可直接放进 `~/.codex/skills` 的 skill 副本。

## 依赖

- Windows
- Microsoft Edge
- Python 3.10+
- `requirements.txt` 里的 Python 包

安装依赖：

```powershell
pip install -r requirements.txt
```

## 快速开始

### 1. 启动专用 Edge 会话

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_edge_clone_remote_debug.ps1
```

这会打开一个新的 Edge 窗口，并启用远程调试端口。

### 2. 在这个窗口里手动完成授权

需要做的事：

1. 登录 ScienceDirect 或机构访问入口
2. 手动通过验证机器人页
3. 打开一篇目标文章
4. 点一次 `View PDF`
5. 保持这个窗口不要关闭

### 3. 可选：先做会话探测

```powershell
python .\scripts\attach_sciencedirect_remote_debug.py --debugger-address 127.0.0.1:9222
```

理想状态：

- `attached: true`
- `bot_verification_page: false`
- `has_pdf_metadata: true`

### 4. 运行批量抓取

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_devtools_sciencedirect_fetch.ps1 `
  -InputCsv .\examples\input-template.csv `
  -OutDir .\out\run-001 `
  -InterItemSleepSeconds 6
```

## 输入格式

输入 CSV 建议为 UTF-8，至少包含：

- `number`
- `doi`

可选列：

- `title`
- `note`
- `year`
- `journal`
- `formatted`

如果 `note` 里有候选链接，程序会优先使用 `doi.org` 或 `sciencedirect.com` 的链接。

## 输出内容

每次运行会生成：

- `pdfs/`
- `devtools_results.csv`
- `devtools_missing.csv`
- `downloaded_doi.txt`
- `missing_doi.txt`
- `summary.txt`

## 常用建议

- `PageWaitSeconds` 建议先用 `8`
- `InterItemSleepSeconds` 建议先用 `5-8`
- 出现验证机器人页后不要立即全量重跑，先在同一个 Edge 会话里手动打开一篇文章并点击 `View PDF`
- 对失败条目优先做小批量重试，而不是整批重跑

## 更多说明

- [详细流程](./docs/workflow.md)
- [故障排查](./docs/troubleshooting.md)
