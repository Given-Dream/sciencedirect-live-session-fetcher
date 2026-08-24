# ScienceDirect 实时会话抓取器

[English](./README.md)

这是一套可复用脚本和 Codex skill，用于在“用户已经合法完成授权”的浏览器会话中，串行下载论文 PDF。

这个仓库最初的主线是 Windows 下的 Edge DevTools 路线，用来处理 ScienceDirect / Elsevier 的实时会话下载。现在仓库仍然保留这条原始主线，并在同一个 Chromium 抓取器中加入 Wiley / AGU、Canadian Science Publishing、AIP Publishing 和 IEEE Xplore 的显式实时会话适配器，同时继续保留 macOS Chrome 与 Firefox 混合出版商路线。

## 适用场景

这套流程适合下面几类情况：

- 你已经拥有个人账号、机构账号或校园网等合法访问权限
- 直接用 `requests`、`curl` 或普通 HTTP 下载会被登录页、验证码、挑战页或浏览器专属流程拦住
- 你可以手动完成登录、机构认证或验证码，并保持浏览器窗口打开

## 支持路线

- `Windows Edge DevTools 路线`
  这是仓库原来的核心路线，适合 Windows 下的 ScienceDirect 和 Elsevier。
  抓取器会复用真实 Edge 会话，读取文章页中的 `pdfDownload` 元数据，定位短时签名的 ScienceDirect PDF 链接，并优先在当前授权页面上下文中抓取 PDF。

- `macOS Chrome DevTools 路线`
  这是在原有 DevTools 流程上补充出来的 macOS 路线。
  它同样适合 ScienceDirect 和 Elsevier，并共享 Windows 路线中的 Wiley / AGU、Canadian Science Publishing、AIP 和 IEEE 显式适配器，也能 fallback 到通用 PDF 元数据、链接、iframe、embed、object 入口。

- `Firefox 混合出版商路线`
  适合页面本身已经暴露正常 PDF 入口的出版商。
  这一路线已经在下列出版商或站点类型上实践过：
  `MDPI`、`Springer Nature`、`Frontiers`、`AIP`、`ASCE`、`SSRN`、`ICE / Géotechnique`

  同时也把下列主流出版商视为通用 fallback 目标：
  `Wiley`、`Taylor & Francis`、`IEEE`、`ACM`、`ACS`、`Nature Portfolio`、`Oxford University Press`、`Cambridge University Press`、`Sage`

  前提是页面结构确实暴露了标准 PDF 目标，而不是完全被站内脚本或挑战页包裹。

脚本会通过 DevTools 远程调试端口连接到真实浏览器会话，逐篇打开文章，寻找出版社授权的 PDF 路由，再通过页面上下文、带当前会话凭据的 DevTools 资源加载、导航响应、浏览器下载事件或内置 PDF viewer 保存文件。所有文件必须通过 `%PDF-` 文件头校验，出版社专用候选地址还必须匹配当前 DOI 或 IEEE 文献号。

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

- `scripts/run_devtools_sciencedirect_fetch.ps1`
  原始 Windows Edge 路线对应的 PowerShell 包装器。

- `scripts/launch_chrome_clone_remote_debug_macos.sh`
  在 macOS 上启动一个独立 Chrome 会话，并打开远程调试端口。
  支持：
  `--direct-connection`、`--disable-extensions`、`--one-shot-profile`

- `scripts/run_devtools_sciencedirect_fetch_macos.sh`
  macOS 下的 Chrome DevTools Python 下载器包装脚本。

- `scripts/attach_sciencedirect_remote_debug.py`
  可选 probe，用来检查当前 Chrome 或 Edge 会话是否已经能看到文章元数据与出版社 PDF 信号。

- `scripts/devtools_sciencedirect_serial_fetch.py`
  Chrome / Edge 共用的 DevTools 串行下载器。
  保留了原来稳定的 ScienceDirect 签名 PDF 路径，并增加 Wiley / AGU、Canadian Science Publishing、AIP 和 IEEE 的显式路由及 DOI / 文献号身份过滤。

- `scripts/firefox_sciencedirect_serial_fetch.py`
  可见 Firefox 串行下载器。
  面向混合出版商页面，优先尝试：
  `citation_pdf_url`、普通 PDF 链接、`Download PDF` 等入口。

- `examples/input-template.csv`
  最小输入模板。

- `codex-skill/`
  一份可直接放进 `~/.codex/skills` 的 skill 副本。

## 依赖

- Python 3.10+
- `requirements.txt` 中的 Python 包
- Windows + Microsoft Edge，用于原始 DevTools 路线
- macOS + Google Chrome，用于新增的 macOS 路线

安装依赖：

```bash
python -m pip install -r requirements.txt
```

## 快速开始

### Windows Edge 快速开始

1. 启动推荐的干净 Edge 会话

对于 ScienceDirect / Elsevier，推荐从这条命令开始：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_edge_clone_remote_debug.ps1 `
  -DirectConnection `
  -DisableExtensions `
  -OneShotProfile `
  -RemoteDebuggingPort 9222 `
  -Url "https://doi.org/10.1016/j.measurement.2025.118930"
```

2. 在打开的浏览器里手动完成授权

需要做的事：

1. 登录 ScienceDirect 或机构入口
2. 手动通过验证码或 challenge
3. 打开任意一篇目标文章
4. 点击一次 `View PDF`
5. 保持该浏览器窗口打开

3. 可选：先做 probe

```powershell
python .\scripts\attach_sciencedirect_remote_debug.py `
  --browser edge `
  --debugger-address 127.0.0.1:9222
```

4. 运行 Edge DevTools 批量下载

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_devtools_sciencedirect_fetch.ps1 `
  -InputCsv .\examples\input-template.csv `
  -OutDir .\out\run-001 `
  -InterItemSleepSeconds 6
```

### macOS Chrome 快速开始

1. 启动推荐的干净 Chrome 会话

对于 ScienceDirect / Elsevier，推荐从这条命令开始：

```bash
bash ./scripts/launch_chrome_clone_remote_debug_macos.sh \
  --direct-connection \
  --disable-extensions \
  --one-shot-profile \
  --remote-debugging-port 9222 \
  --url "https://doi.org/10.1016/j.measurement.2025.118930"
```

2. 在打开的浏览器里手动完成授权

需要做的事：

1. 登录 ScienceDirect 或机构入口
2. 手动通过验证码或 challenge
3. 打开任意一篇目标文章
4. 点击一次 `View PDF`
5. 保持该浏览器窗口打开

如果是校外访问 IEEE，请先在这个 Chrome 窗口里完成 IEEE / 机构账号登录。后续批量应从论文详情页走，不建议直接把 `stamp.jsp` 当作入口，否则 IEEE 可能把请求识别成个人会话下的 PDF 访问，显示并不准确的 “This Content is Not Included in Your Subscription”。

3. 可选：先做 probe

```bash
python3 ./scripts/attach_sciencedirect_remote_debug.py \
  --browser chrome \
  --debugger-address 127.0.0.1:9222
```

4. 运行 Chrome DevTools 批量下载

```bash
bash ./scripts/run_devtools_sciencedirect_fetch_macos.sh \
  --input-csv ./examples/input-template.csv \
  --out-dir ./out/run-001 \
  --inter-item-sleep-seconds 6
```

5. 混合出版商时使用 Firefox 路线

```bash
python3 ./scripts/firefox_sciencedirect_serial_fetch.py \
  --input-csv ./examples/input-template.csv \
  --out-dir ./out/firefox-run-001 \
  --manual-ready-timeout 300 \
  --page-wait-seconds 10 \
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

- DevTools 路线优先使用 `doi.org` 与 `sciencedirect.com`
- 对 IEEE，优先在 `note` 里放 IEEE 文章页，例如 `https://ieeexplore.ieee.org/document/<arnumber>`；如果输入里已有 `stamp.jsp` 或 `stampPDF/getPDF.jsp`，脚本会先规整回论文详情页再找 PDF。
- Firefox 混合路线也可以利用出版商落地页 URL

## 输出内容

每次运行会生成：

- `pdfs/`
- `devtools_results.csv`
- `devtools_missing.csv`
- `downloaded_doi.txt`
- `missing_doi.txt`
- `summary.txt`

## 真实运行经验

- 对 ScienceDirect / Elsevier，在 Windows 上原来的可靠默认起点仍然是：
  `Edge DevTools + DirectConnection + DisableExtensions + OneShotProfile`

- macOS Chrome 路线沿用了同一套 DevTools 核心流程，是当前新增的 macOS 对应方案。

- 如果是校外 IEEE 访问，先在 Chrome 或 Edge 窗口里完成机构授权，再从论文详情页进入 PDF。直接把 `stamp.jsp` 当作入口，更容易落到误导性的订阅提示页。

- ScienceDirect 的 `pdf.sciencedirectassets.com` 链接通常是短时签名链接。
  它们看起来像普通 URL，但经常会：
  - 很快过期
  - 只能在当前授权浏览器上下文中使用
  - 在外部 HTTP 客户端中返回 `403 Forbidden`

- 如果 Chrome 或 Edge 打开的是：
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

## 多来源文献 Skill

仓库同时提供可直接安装的 [literature-live-session-pipeline](./literature-live-session-pipeline/) Skill。它保留原有出版商路线，并新增知网 PDF-only 实时会话流程：精确题名结果、文献详情页、精确可见文本 `PDF下载`。该路线会忽略隐藏休眠的验证 DOM，遇到真实可见验证则停止；拒绝 CAJ 内容，并允许“带权限加密标记但无需密码可正常读取”的 PDF 通过严格题名与页数核验。

浏览器用户目录、登录会话、已下载论文和运行输出均明确排除在 Git 之外。
