# ScienceDirect 实时会话抓取器

[English](./README.md)

这是一套可复用脚本和 Codex skill，用于在“用户已经合法完成授权”的浏览器会话中，串行下载论文 PDF。

当前仓库里最稳定的路径仍然是：

- `ScienceDirect / Elsevier` + `真实 Edge DevTools 会话`

仓库里同时也提供：

- `Firefox 混合出版商路线`

适用于页面公开暴露普通 PDF 链接、`citation_pdf_url`、`.pdf`、`/pdf`、`Download PDF` 等目标的主流出版商页面。

## 适用场景

这套流程适合下面几类情况：

- 你已经拥有个人账号、机构账号或校园网等合法访问权限
- 直接用 `requests`、`curl` 或普通 HTTP 下载会被登录页、验证码、挑战页或浏览器专属流程拦住
- 你可以手动完成登录、机构认证或验证码，并保持浏览器窗口打开

## 支持路线

- `Edge DevTools 路线`
  适合 ScienceDirect 和 Elsevier。
  抓取器会复用真实 Edge 会话，读取文章页中的 `pdfDownload` 元数据，定位短时签名的 ScienceDirect PDF 链接，并优先在当前授权页面上下文中抓取 PDF。

- `Firefox 混合出版商路线`
  适合页面本身已经暴露正常 PDF 入口的出版商。
  这一路线已经在下列出版商或站点类型上实践过：
  `MDPI`、`Springer Nature`、`Frontiers`、`AIP`、`ASCE`、`SSRN`、`ICE / Géotechnique`

  同时也把下列主流出版商视为通用 fallback 目标：
  `Wiley`、`Taylor & Francis`、`IEEE`、`ACM`、`ACS`、`Nature Portfolio`、`Oxford University Press`、`Cambridge University Press`、`Sage`

  前提是页面结构确实暴露了标准 PDF 目标，而不是完全被站内脚本或挑战页包裹。

## 法律与边界

只在你已经合法拥有的访问权限范围内使用本仓库。

这套流程不会：

- 绕过付费墙
- 绕过登录
- 绕过验证码
- 绕过机构授权
- 凭空创建访问权限

如果页面仍然停留在挑战页、验证码页或未授权页，正确做法是先人工完成处理，再复用同一浏览器会话继续。

## 仓库内容

- `scripts/launch_edge_clone_remote_debug.ps1`
  启动一个独立 Edge 会话，并打开远程调试端口。
  现在支持：
  `-DirectConnection`、`-DisableExtensions`、`-OneShotProfile`

- `scripts/attach_sciencedirect_remote_debug.py`
  可选 probe，用来检查当前 Edge 会话是否已经能看到 ScienceDirect 文章元数据与 PDF 入口。

- `scripts/devtools_sciencedirect_serial_fetch.py`
  ScienceDirect / Elsevier 串行下载器。
  当前稳定路径是：
  文章页 -> `pdfDownload` 元数据 -> `pdf.sciencedirectassets.com` 短时签名链接 -> 页面上下文抓取 PDF

- `scripts/firefox_sciencedirect_serial_fetch.py`
  可见 Firefox 串行下载器。
  面向混合出版商页面，优先尝试：
  `citation_pdf_url`、普通 PDF 链接、`Download PDF` 等入口。

- `scripts/run_devtools_sciencedirect_fetch.ps1`
  Edge DevTools Python 下载器的 PowerShell 包装器。

- `examples/input-template.csv`
  最小输入模板。

- `codex-skill/`
  一份可直接放进 `~/.codex/skills` 的 skill 副本。

## 依赖

- Windows
- Microsoft Edge
- Python 3.10+
- `requirements.txt` 中的 Python 包

安装依赖：

```powershell
pip install -r requirements.txt
```

## 快速开始

### 1. 启动推荐的干净 Edge 会话

对于 ScienceDirect / Elsevier，推荐从这条命令开始：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_edge_clone_remote_debug.ps1 `
  -DirectConnection `
  -DisableExtensions `
  -OneShotProfile `
  -RemoteDebuggingPort 9222 `
  -Url "https://doi.org/10.1016/j.measurement.2025.118930"
```

这条命令的含义：

- `-DirectConnection`
  只对本次 Edge 进程生效，不继承浏览器代理

- `-DisableExtensions`
  避免 Adobe PDF 等扩展接管 ScienceDirect PDF

- `-OneShotProfile`
  自动创建一次性 profile；关闭这个 Edge 窗口后，这次会话自然结束

### 2. 在打开的浏览器里手动完成授权

需要做的事：

1. 登录 ScienceDirect 或机构入口
2. 手动通过验证码或 challenge
3. 打开任意一篇目标文章
4. 点击一次 `View PDF`
5. 保持该浏览器窗口打开

### 3. 可选：先做 probe

```powershell
python .\scripts\attach_sciencedirect_remote_debug.py --debugger-address 127.0.0.1:9222
```

理想信号包括：

- `attached: true`
- `has_view_pdf: true`
- `has_pdf_metadata: true`
- `pdf_url` 非空

注意：

ScienceDirect 有时会出现“probe 同时显示 challenge 标记和 PDF 元数据”的混合状态。
这种情况下，不要立刻全量开跑，先用一条文献做 probe 下载。只要 probe 行成功落盘，再继续整批跑。

### 4. 运行 Edge DevTools 批量下载

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_devtools_sciencedirect_fetch.ps1 `
  -InputCsv .\examples\input-template.csv `
  -OutDir .\out\run-001 `
  -InterItemSleepSeconds 6
```

### 5. 混合出版商时使用 Firefox 路线

```powershell
python .\scripts\firefox_sciencedirect_serial_fetch.py `
  --input-csv .\examples\input-template.csv `
  --out-dir .\out\firefox-run-001 `
  --manual-ready-timeout 300 `
  --page-wait-seconds 10 `
  --inter-item-sleep-seconds 6
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

如果 `note` 里带候选链接：

- Edge / ScienceDirect 路线优先使用 `doi.org` 与 `sciencedirect.com`
- Firefox 混合路线也可以利用出版商落地页 URL

## 输出内容

每次运行会生成：

- `pdfs/`
- `devtools_results.csv` 或 `firefox_results.csv`
- `devtools_missing.csv` 或 `firefox_missing.csv`
- `downloaded_doi.txt`
- `missing_doi.txt`
- `summary.txt`

## 真实运行经验

- 对 ScienceDirect / Elsevier，最可靠的默认起点是：
  `Edge DevTools + DirectConnection + DisableExtensions + OneShotProfile`

- ScienceDirect 的 `pdf.sciencedirectassets.com` 链接通常是短时签名链接。
  它们看起来像普通 URL，但经常会：
  - 很快过期
  - 只能在当前授权浏览器上下文中使用
  - 在外部 HTTP 客户端中返回 `403 Forbidden`

- 如果 Edge 打开的是：
  `extension://.../pdfjs/web/viewer.html?file=...`
  说明 PDF 被扩展接管了。
  这时不要反复重试同一 viewer URL，应该关闭窗口，改用禁扩展的干净会话重启。

- Firefox 对混合出版商页面很有价值，但对 ScienceDirect 本身更容易遇到：
  - `please wait`
  - 签名链接失效
  - 自动化浏览器会话不稳定

## 文档

- [Workflow](./docs/workflow.md)
- [Troubleshooting](./docs/troubleshooting.md)
