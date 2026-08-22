# Workflow

1. 先整理 `manifest.csv`，至少包含 `number`、`title`、`source_hint` 和 `entry_url`。
2. 按来源分别启动 Edge 会话。CNKI 默认端口为 `9223`。
3. 在对应浏览器里手动登录、完成真实可见的验证，并保持窗口打开。自动化不得代替用户拖动滑块。
4. 用 `probe_live_session.py` 先探一条，再根据来源选择下载器。
5. ScienceDirect、WOS 和通用出版商使用 `run_devtools_multi_source_fetch.ps1`。
6. CNKI 使用 `run_cnki_pdf_live_fetch.ps1`，流程固定为“检索结果页 -> 精确题名链接 -> 文献详情页 -> 精确可见文本 `PDF下载`”。严禁选择 `CAJ下载`。
7. CNKI 的可信点击使用 DevTools 鼠标事件。不能按 DOM `id` 选择下载按钮，因为 CAJ 与 PDF 锚点可能同时使用 `id="cajDown"`。
8. 点击 `_blank` 后同时监视批次下载目录与系统 `Downloads`。若文件落到系统目录，只复制到批次目录，不移动或删除用户原文件。
9. 可信点击短暂等待后仍无文件时，可在临时空白页导航到同一个 `PDF下载` href，并把详情页作为 referrer；这是重放已授权的同一下载链接，不是绕过。若出现登录页或真实验证页，立即停止。
10. 只接收文件头为 `%PDF-` 的文件，并核验页数、无密码可读性和题名。`is_encrypted=true` 只表示权限标记；只要无需密码即可读取页数/文本，就不能据此拒绝。
11. 题名比较先做 Unicode NFKC，再去掉空白、标点与符号。若中文字体映射导致提取乱码，应进入人工复核，不得静默通过。
12. 人工复核至少记录：来源文件名、首页可视题名、英文封面题名/作者（如有）、页数、源文件与归档文件 SHA-256。只有证据闭环时才能做人工覆盖。
13. 每篇间隔建议 5–12 秒。失败后只用 `cnki_pdf_missing.csv` 生成失败子集重试，不要立即重跑已完成记录。
14. 最后检查 `cnki_pdf_results.csv`、`cnki_pdf_missing.csv`、`cnki_pdf_summary.json` 和 `endnote_report.json`。

## 知网真实验证判定

知网正常结果页可能保留腾讯验证组件的隐藏 DOM，甚至包含“拖动下方拼图完成验证”文字。以下任一条件才视为真实验证：

- URL 包含 `/verify/home` 或 `captchaType=`；
- 页面标题为安全验证类标题，且正文同时出现验证提示；
- 验证提示元素及其祖先均非 `display:none`、非隐藏、透明度大于 0，并且元素矩形与当前视口相交。

仅在 HTML 或 `body.innerText` 中搜索到验证文字不得判失败。

推荐把每一轮都放进单独批次目录，例如：

- `batch_20260411/manifest.csv`
- `batch_20260411/manifest.ris`
- `batch_20260411/downloads/`
- `batch_20260411/endnote_report.json`
- `batch_20260411/endnote/`
