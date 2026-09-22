# novel-down 上线前全检报告（代码审查 + 安全审计 + QA 测试）

**日期**：2026-09-22
**场景**：上线前检查（Pre-launch Check）—— 代码审查 + 安全审计 + QA 测试与发布物验证
**目标仓库**：`G:\repos\novel-down` @ `97ae559`（v0.8.38，分支 main，远端 `https://gitee.com/siwpan/novel-down.git`，MIT，public）
**参与成员**：产品官（代码审查） + 安全卫士（OWASP+STRIDE 审计） + 质量门神（QA 测试与发布）
**主理人**：沽思航（Gu）· 软件工坊 CEO

---

## 📌 TL;DR（执行摘要）

- 整体结论：🟡 **有条件通过（Conditional Go）** —— 源码质量优秀、测试全绿、门禁全 PASS、免费约束被证明为真硬约束；**唯一源码级阻塞项是 1 个已复现的输出目录路径穿越**，另有 1 个发布物版本标注不一致必须处理。
- 阻塞项数量：**2**（🔴 路径穿越；🟠 dist CLI 便携版自报 v0.8.37）
- 三路独立结论高度收敛：均判 **条件 Go**，均确认「仅免费章节」六层约束**无任何旁路开关**，均确认 public 仓**零凭据泄漏**。
- 下一步：修 F-001（一行到三行改动）→ 重建 CLI 便携版并重算 SHA256SUMS/zip → 即可 **Go**。

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| **Go / No-Go** | 🟡 **条件 Go**（清掉 2 个阻塞项即可 Go） |
| **严重度分布** | 🔴 1 ／ 🟠 6 ／ 🟡 11 ／ 🟢 4（合并去重后） |
| 测试基线 | **288 passed / 0 failed / 0 error / 0 skipped**，9.94s（pytest 9.1.1，Python 3.14.7） |
| 机械门禁 | `tools/check_repo.py` **11/11 PASS**（EXIT 0）；`noveldown selfcheck` **PASS**（EXIT 0，且经反向验证为真断言） |
| 发布物状态 | GUI 版实测可起窗（0.8.38 ✓）；**CLI 便携版自报 0.8.37 ✗** |
| 总体健康分（QA 口径） | **92 / 100**（功能/测试 100，发布物 85，文档 95） |
| 关键行动项 | 4 条 P0/P1 + 6 条 P2 |
| 建议负责人 | 全哥（一人团队；建议按 P0 → P1 → P2 顺序自查自修） |

**主理人裁决说明（超然于成员结论）**：安全官判 🔴 路径穿越，代码审查员判「无 🔴」。二者不矛盾——代码审查员的审查维度未覆盖输出路径净化。主理人已**独立复现**该缺陷（见 §2.1 证据），**裁定 🔴 成立**。

---

## 1. 各成员核心结论

### 🔍 产品官（代码审查）
- **核心判断**：工程质量整体扎实，**无 🔴**；288 用例全绿、`check_repo` 11 项 PASS。README 里所有关键计数（161/146/48/113/37/23/15、392 镜像域、1373 身份、459KB 轮廓索引、288 用例）**逐个实核全部吻合**——主理人预设的"文档↔实现不一致"在这些点上**不成立**。
- **最实的一条**：GUI「停止」按钮**实际停不下来**。真实引擎 + 本地合成站实测：第 3 章点停止 → **40/40 全抓完**，且提示语「会在当前章节结束后停下」属误导。
- **关键建议**：修正 GUI 取消语义为协作式取消；`rules.validate()` 校验 `(?P<cid>…)` 命名组、`discover()` 0 章时告警；把 `packaging/` 纳入门禁扫描。

### 🛡️ 安全卫士（OWASP Top 10 + STRIDE 审计）
- **核心判断**：**条件 Go**，唯一阻塞项是已复现的 `CWE-22` 输出目录路径穿越；public 仓**无任何凭据/密钥泄漏**（全仓 + **全 git 历史**扫描 0 命中）。
- **合规核验（本仓最强一环）**：免费六层约束**无「跳过开关」**——无 `--vip`/环境变量/配置项能关闭；`selfcheck` PASS；161 条规则严格加载全通过；146 条启用规则 `free_only=true` 全为真。`state.py` 对受保护章写 `paragraphs=[]`，导出器写盘前逐一调用 `assert_no_protected` / `filter_exportable`。
- **关键建议**：`cli.py:327` / `gui.py:353` 目录名过 `safe_filename` 并加 `commonpath` 越界断言；依赖钉精确版本 + hash。

### ✅ 质量门神（QA 测试与发布）
- **核心判断**：**条件 Go**。源码可发；唯一实质缺陷是 `dist/` 里发给用户的**命令行便携版 exe 自报 v0.8.37**，与 v0.8.38 发行标注不符（产物 mtime 06:42/06:43 早于版本号提升 07:15）。
- **实跑亮点**：离线 export 从真实缓存产出 TXT/MD/EPUB/HTML 四格式且非空（EPUB3 经标准库 `zipfile` 验证为合法 zip、`mimetype` 首条 STORED）；`verify_artifacts` / `verify_reader` 全 PASS（受保护内容零请求、零泄漏、PUA=0）；GUI 打包版与源码版**均实测起窗、responding=True**。
- **关键建议**：发布前重建 CLI 便携版（onedir + onefile）并重算 `SHA256SUMS.txt`、重打两个 zip；否则必须在 release notes 明示版本串未刷新。

---

## 2. 综合审查发现（去重合并后按严重度排序）

### 2.1 🔴 阻塞项（发版前必须处理）

| # | 严重度 | 类别 | 位置 | 问题描述 | 建议 | 来源成员 |
|---|--------|------|------|---------|------|---------|
| 1 | 🔴 | 安全 / 路径穿越 (CWE-22, OWASP A03) | `noveldown/cli.py:327`、`noveldown/gui.py:353` | 输出**目录名**直接拼接远端返回的 `book.title`：`os.path.join(cfg["save_dir"], f"{book.title}_{book.site}")`。明明仓内已有 `exporters/__init__.py:35` 的 `book_slug()`（= `safe_filename(f"{title}_{site}")`），且**四个导出器都用它做文件名**，唯独目录名漏用 → `..\..\` 可逃出 `--out`；亦含 Windows 非法字符（`?`/`*`/`\|`）时直接建目录失败 | 目录名改用 `book_slug(book)`；追加 `os.path.commonpath([resolve(out_dir), abspath(save_dir)]) == abspath(save_dir)` 断言，越界即拒；补回归测试（`grep safe_filename tests/` 目前为空） | 安全卫士（**主理人独立复现**） |
| 2 | 🟠 | 发布物 / 一致性 | `dist/noveldown/noveldown.exe`、`dist/noveldown-onefile.exe`、`dist/noveldown-0.8.38-portable-win64.zip` | 发给用户的**命令行便携版自报 v0.8.37**：`--version` → `noveldown 0.8.37`，而源码 `python -m noveldown --version` = `0.8.38`。构建于版本号提升之前（06:42/06:43 < 07:15）。v0.8.38 提交仅改 GUI/packaging/docs，**CLI 核心逻辑未变**，无功能回归 | 发布前重建 onedir + onefile → 重算 `SHA256SUMS.txt` → 重打两个 zip（`python packaging/build.py --portable --zip --gui`）；否则在 release notes 明示 | 质量门神 |

**#1 主理人独立复现证据**（`F:/Python314/python.exe`，仓外临时目录，未联网，代码路径原样照抄）：

```
raw expr        : '..\\..\\PWNED_demo'
out_dir         : C:\Users\13122\AppData\Local\Temp\PWNED_demo     ← 已逃出 save_dir
escaped?        : True
leak file exists: True
--- 现有净化函数对比 ---
book_slug(book) : _.._PWNED_demo      ← 仓内已有，目录名却没用
safe_filename   : _.._PWNED_demo
--- 附：Windows 非法字符场景 ---
raw '斗破苍穹：第一章?_demo'  |  净化后 '斗破苍穹：第一章__demo'
```

> 影响面dual：既是**安全面**（恶意/被劫持镜像站可把成品写到 `--out` 之外），也是**健壮性面**（合法书名含半角 `?`、`/` 等字符时建目录/导出直接失败）——后者不需要任何攻击者就会命中。

### 2.2 🟠 高（发版前建议处理）

| # | 严重度 | 类别 | 位置 | 问题描述 | 建议 | 来源成员 |
|---|--------|------|------|---------|------|---------|
| 3 | 🟠 | 功能缺陷 | `noveldown/gui.py:331-337`（`_prog`）、`gui.py:291`；`engine.py:760-771` | GUI「停止」= 在工作线程进度回调里抛 `KeyboardInterrupt`。异常从 `as_completed` 循环抛出时，`with ThreadPoolExecutor(...)` 的 `__exit__` 会 `shutdown(wait=True)`，**等待所有已提交章节跑完**。真实引擎实测：**stop@第3章 → 40/40 全抓完**，提示语误导 | 改协作式取消：给 engine 传 `threading.Event`/stop 回调，循环内 `if stop: 取消剩余 futures`；至少立刻改文案 | 产品官 |
| 4 | 🟠 | 静默失败 | `parser.py:504-509`、`parser.py:373-395`；`rules.py::validate()`；`engine.py:303-333` | 目录项解析 `try/except Exception: pass` 吞掉一切。规则作者把 `catalog.id_from.pattern` 写成 `(\d+)`（漏命名组 `cid`）→ `m.group("cid")` 抛 IndexError 被吞 → **目录静默 0 章、不报错**；`validate()` 不校验命名组，`discover()` 不校验非空 | `validate()` 校验 `pattern` 必含 `(?P<cid>…)`；`discover()` 0 章时显式告警/抛错；被吞异常至少记日志 | 产品官 |
| 5 | 🟠 | 供应链 / 构建不可复现 | `requirements.txt:4-8` | `requests>=2.31`、`beautifulsoup4>=4.12`、`lxml>=5.0` 仅下限，无 `==`、无 hash、无 lock。public MIT + 发 exe，构建期会静默拉到未来版本（OWASP A06/A08） | `pip-compile` 钉精确版本 + hash；发版附依赖清单 | 安全卫士 |
| 6 | 🟠 | 门禁盲区 / 硬编码 | `packaging/build.py:127`（`default=r"F:/Python314/python.exe"`）；`tools/check_repo.py:64`（`SCAN_CODE_DIRS=("noveldown","tools","tests")`）；`tests/test_freeguard.py:263` | 项目**自己定的规则**「生产代码不得写死本机绝对路径」，但 `packaging/` 被排除在门禁之外，门禁却仍打印「7 生产代码无硬编码本机路径 ✓」——**门禁过度声称**；换机/换盘即失败 | `--py` 默认改 `sys.executable`；把 `packaging` 并入 `SCAN_CODE_DIRS`（同步那个测试）；`HARDCODED_PATH_RE` 已能匹配 `F:/Python314` | 安全卫士 + 产品官（**双路交叉确认**） |
| 7 | 🟠 | 测试盲区 | `tests/`（缺 `test_http_client` / `test_ratelimit` / `test_identity_manager`） | 「线程池 + 连接池 + 身份轮换 + 限速抖动」这几条**恰好 0 直接测试**：逐模块 grep 显示三者在 tests 中被引用 **0 次**。重试退避（含 403/429 分支）、连接池复用、cookie 清空、自适应降速、身份轮换、GUI 取消路径均无回归 | 补 `http_get` 退避重试与 `RateLimiter`（slowdown/recover/并发取票）单测；给 `engine.run()` 取消路径补集成测试 | 产品官 |
| 8 | 🟡 | 合规一致性 / 降级不干净 | `fontdecode.py:451-466`（`deps_available`） | brotli 的 `ImportError` 被 `pass` 吞掉、**不加进 missing**，与本模块 docstring(32-35) 及报错文案(465)「woff2 需要 brotli」**自相矛盾**。brotli 缺失时装了 fontTools 仍返回 True → woff2 站点在 `TTFont()` 深层炸，被 `engine._font_decode` 兜住后**把含 PUA 占位字符的正文当 `status=ok` 存下并导出**（半乱码数据冒充正常数据） | `deps_available` 真查 brotli；或解码后覆盖率过低（如 <0.9）时把该章降级为 empty/告警 | 产品官 |

### 2.3 🟡 加固 / 一般

| # | 严重度 | 类别 | 位置 | 问题描述 | 建议 | 来源成员 |
|---|--------|------|------|---------|------|---------|
| 9 | 🟡 | 门禁自证能力 | `tools/check_repo.py --selfcheck` | 自检**仅抽验 11 项中的 5 项**（许可文件唯一/无第三方源码/无归档/无调试残留/规划表脱节）→「门禁能抓到问题」这一性质未被完全自证。与 #6 同源：**门禁的自我证明偏弱** | 扩展到全部 11 项 | 质量门神（**主理人跨路归纳**） |
| 10 | 🟡 | 错误处理 | `cli.py:233-237`、`cli.py:424-437`；`engine.py:210-228` | 浏览器路由站点在缺 playwright 时 `_browser()` 抛 `BrowserUnavailable(RuntimeError)`；`cmd_fetch` 只捕 `KeyboardInterrupt`，`main()` 的 except 不含 RuntimeError → **用户看到原始 traceback** | `main()` 增捕 `BrowserUnavailable`，按 probe 的 `[失败]` 风格友好打印 | 产品官 |
| 11 | 🟡 | 安全加固 | `freeguard.py:68` | `host == d or host.endswith("."+d) or host.startswith(d)`。`endswith("."+d)` 已足够挡 `example.com.evil.net`（已复现 False）；`startswith(d)` **无安全增益**，反把 `example-bad.competitor.org` 当 `example-bad.com` 拦下（误拦，fail-closed 但语义错）。默认名单为空 → 影响低 | 删除 `host.startswith(d)` 分支 | 安全卫士 |
| 12 | 🟡 | 安全纵深 (SSRF) | `http_client.py:167,174`（`allow_redirects=True`） | 命中站点可 302 到内网地址而不再校验；风险被 `find_rule()`（必须先匹配某条随仓规则域名）大幅收窄，`169.254.169.254` 无规则 → 不可达。属纵深缺口 | 重定向回调校验最终 host ∈ 该规则 `match` 集合 | 安全卫士 |
| 13 | 🟡 | 记账完整性 / 门禁盲区 | `tools/check_repo.py:51-54`；`.archived/`；`docs/REFERENCE.md` §三 | `.archived/` 实有 **8 个第三方归档**（FictionDown×3、novel-downloader、backupqidian、novel-spider、**QidianCrawler、QidianScrapy**），后两者**在 REFERENCE.md 记账中完全没有**；且 `FORBIDDEN_DIR_PARTS` **不含 `.archived/`** → 一旦在此解压再 `git add -A`，第三方源码可入库而门禁第 2 项不报（**MIT 仓分发 GPL/AGPL 源码的许可风险**） | REFERENCE.md 快照表补 `.archived/` 清单与 sha256；`FORBIDDEN_DIR_PARTS` 增 `.archived/` | 产品官 |
| 14 | 🟡 | 合规一致性 | `http_client.py:163-169` vs `176-180`；`cli.py:382` | requests 路径每次请求后 `sess.cookies.clear()`（不承载凭据），但 **curl_cffi 路径不清 cookie jar**，两者不一致，与 README/FREE_ONLY「无 Cookie」表述冲突；且 `--curl-cffi` 在未安装时**静默回退** requests、无提示 | curl 路径同样清 cookie；`--curl-cffi` 不可用时明确 warn | 产品官 |
| 15 | 🟡 | 误伤风险 | `constants.py:77-82`；`freeguard.py:98-122` | `PAYWALL_MARKERS` 含泛词「打开APP」「下载【」「扫码下载」等，`check_content` 对**整章正文**做子串匹配 → 正常免费章节若出现这些词会被判 blocked 且正文丢弃（宁缺勿滥取向，但过宽） | 收紧为站点独特整句，或要求与章末位置/页面上下文共现 | 产品官 |
| 16 | 🟡 | 设计记录 | `browser.py:165-166, 251-254` | `NOVELDOWN_STEALTH_JS` / 规则 `browser.stealth_js` 是 `add_init_script(path=...)` 向浏览器注入任意 JS。**有意设计**（规则随仓可信 + 环境变量由用户设置），但规则 JSON（数据）因此可携带「浏览器内代码」 | 在 docs/REFERENCE.md 说明其代码注入语义 | 安全卫士 |

### 2.4 🟢 建议 / 信息

| # | 严重度 | 类别 | 位置 | 问题描述 | 建议 | 来源成员 |
|---|--------|------|------|---------|------|---------|
| 17 | 🟢 | 表述强度 | `README.md:386-392`；`tools/check_repo.py:112-229` | README 称「只借鉴设计思路，未复制任何代码」并称由 check_repo 机械校验。实际门禁只能证明「未跟踪第三方源码树 + 记账完整」，**无法证明「未复制代码」**（行内抄写不会被路径/文件名门禁发现） | README 明确边界（门禁保证的是「不含第三方源码树」而非「零复制」） | 产品官 |
| 18 | 🟢 | 残留 / 测试卫生 | 根 `noveldown.spec`（未跟踪）；`tests/test_parser.py:267` | 手工残留 spec 内含 `G:/repos/...` 硬编码（**非打包配置丢失**——`packaging/build.py:66-105` 用 PyInstaller CLI 参数驱动，spec 由构建现场生成，无任何代码/文档引用它）；另有 1 条 `SyntaxWarning: "\d" is an invalid escape sequence`（非 raw string，未来 Python 会升为错误） | 删除根 spec；`test_parser.py:267` 改 raw string 或 `\\d` | 产品官 + 质量门神（**双路交叉确认**） |
| 19 | 🟢 | 文档 | `README.md` §`fetch` 选项表 | 表格漏列 CLI 实有的 `--max-items` 与 `--report`（`fetch --help` 有 13 个选项，README 表仅 11） | 补齐两项 | 质量门神 |
| 20 | 🟢 | 文档精度 | `README.md` / `packaging/README.md` / `dist/release-notes-v0.8.38.md` | onefile 启动宣称「约 47 秒」，实测 **39.7s**（偏保守/夸大）；onedir 称 1.4s 实测 1.28s（吻合） | 更新为 ≈40s | 质量门神 |

> **观察记录（非缺陷）**：`dist/noveldown-gui/_internal/` 无任何 `.tcl` 数据文件，初看可疑；但打包 GUI 实测起窗、`responding=True`，判定 Tcl9 运行库已内联/DLL 自带 —— 仅作观察，不列问题。

### 2.5 已验证良好（正面结论，均附证据）

- **密钥/凭据**：全仓 + **全 git 历史**（`--diff-filter=A` + `git grep` 全 rev）扫描 AWS/GCP/GitHub/Slack/JWT/Bearer/私钥/`secret=`/`cookie=` **0 命中** → 从未提交过密钥。
- **`identities.json`（674KB）**：1373 条，字段 `{id, engine, platform, os, ua, curl_impersonate, headers}`，来源 fake-useragent v2.2.0 / Intoli，**无 PII / 无凭据**，可随 public 仓分发。
- **免费六层约束**：无 `skip|disable|bypass` 类关闭开关；`state.save_chapter` 对受保护章写 `paragraphs=[]`；`assert_no_protected` / `assert_export_shape` / `filter_exportable` 在**每个导出器写盘前**调用。**方向验证**：仓外构造 `password="hunter2"` 探针 → `ok: False` + `VIOLATION: ('probe_violation.py',1,'口令字段',...)` → **selfcheck 是真断言，非空跑**。
- **无代码注入面**：无 `eval` / `exec` / `pickle` / `yaml.load` / `os.system` / `shell=True`；`_dig` 用 dict/list 取值、无 `getattr`（不可越界读属性）；161 条规则 regex **无灾难性回溯**。
- **站点身份伪装**：`rules.py:197 matches()` host 严格匹配，`example.com.evil.net` 已复现被拒（False）。
- **导出器安全**：`safe_filename` 净化文件名；htmlreader 转义 `< > &`（无 XSS）；epub 用数字文件名。
- **打包清洁**：**无 `--add-binary` / 外部二进制**（README「ffmpeg 等不入库」属实）；`.deps/`、`*.spec`、`.sources/`、`_ref/`、`dist/`、`build/` 均 gitignore，`git ls-files` 确认 0 跟踪。
- **无调试残留**：`noveldown/` 内 `TODO/FIXME/breakpoint/print` **0 命中**。
- **README ↔ 实现一致性**：161 规则 / 146 启用 / 48 顶层（启用 33）+ 113 镜像池 / 15 停用 / 正版 37（启用 23）/ 392 镜像域名 / 1373 身份 / fontmaps 1 文件 459KB / 288 用例 —— **逐条实核全部吻合**；`check_repo.py` 第 10 项（README 关键计数==代码事实）独立复跑亦 PASS。主理人另行独立核数（48 + 113 = 161，启用 33 + 113 = 146）**同样吻合**。

---

## 3. 阻塞项清单（Go/No-Go 判据）

| # | 阻塞项 | 位置 | 判据 | 修复代价 |
|---|--------|------|------|---------|
| B-1 | 输出目录路径穿越（🔴） | `cli.py:327`、`gui.py:353` | 可把成品写出 `--out` 之外；合法书名含非法字符时直接失败。**已复现** | 极低（1-3 行：改用 `book_slug()` + `commonpath` 断言）+ 补测试 |
| B-2 | CLI 便携版版本串错误（🟠） | `dist/` 三个 CLI 产物 | 用户下载 "v0.8.38 portable" 后 `--version` 显示 0.8.37 | 中（重建 + 重算 SHA256SUMS + 重打 zip） |

**结论**：B-1 与 B-2 均非结构性问题。**修完即 Go**。

---

## ✅ 行动清单

| # | 行动 | 负责方 | 紧急度 | 期望完成 |
|---|------|--------|--------|---------|
| 1 | 修路径穿越：`cli.py:327` 与 `gui.py:353` 的目录名改用 `book_slug(book)`，并加 `os.path.commonpath` 越界断言；补 `safe_filename` / `book_slug` 回归测试（当前 **0** 覆盖） | 全哥 | **P0** | 发版前 |
| 2 | 重建 CLI 便携版（onedir + onefile）→ 重算 `dist/SHA256SUMS.txt` → 重打两个 zip；若决定不重建，在 release notes 明示「便携版 CLI 内核同 v0.8.37、仅版本串未刷新」 | 全哥 | **P0** | 发版前 |
| 3 | 修 GUI「停止」失效（`gui.py:331-337` 改协作式取消：engine 收 `threading.Event`，循环内取消剩余 futures）+ 同步修正误导文案 | 全哥 | P1 | 发版前 |
| 4 | 修目录静默 0 章：`rules.validate()` 校验 `(?P<cid>…)` 命名组；`discover()` 0 章显式告警；被吞异常记日志 | 全哥 | P1 | 发版前 |
| 5 | 把 `packaging` 纳入 `SCAN_CODE_DIRS`（含 `tests/test_freeguard.py:263` 同步），`packaging/build.py:127` 默认改 `sys.executable`；`check_repo --selfcheck` 扩展到全部 11 项 | 全哥 | P1 | 发版前 |
| 6 | 补 `http_client` / `ratelimit` / `identity_manager` 单测（退避重试含 403/429、连接池复用、cookie 清空、自适应降速、身份轮换、GUI 取消路径） | 全哥 | P1 | 发版前 |
| 7 | 依赖钉精确版本 + hash（`pip-compile` / 约束文件） | 全哥 | P2 | 紧接一版 |
| 8 | `fontdecode.deps_available()` 真查 brotli；解码覆盖率过低时把该章降级而非当 `status=ok` 导出 | 全哥 | P2 | 紧接一版 |
| 9 | `.archived/` 补入 REFERENCE.md 记账（含 QidianCrawler / QidianScrapy）+ sha256；`FORBIDDEN_DIR_PARTS` 增 `.archived/` | 全哥 | P2 | 紧接一版 |
| 10 | `freeguard.py:68` 删 `startswith(d)` 分支；`http_client` curl 路径补清 cookie；`--curl-cffi` 不可用改 warn；`main()` 捕 `BrowserUnavailable` | 全哥 | P2 | 紧接一版 |
| 11 | 文档收口：README `fetch` 表补 `--max-items`/`--report`；onefile 耗时改 ≈40s；明确「未复制代码」的门禁边界；删根 `noveldown.spec`；`test_parser.py:267` 改 raw string | 全哥 | P2 | 紧接一版 |

---

## 🔄 回滚预案

- **发布性质**：本次为源码增量发布（v0.8.37 → v0.8.38 仅加 Tkinter GUI + 打包体系 + 文档；**CLI 核心逻辑未变**）→ 风险低。
- **回滚动作**：`git reset --hard` 指向上一个 tag / `db8ddcf`（v0.8.37 收尾），回收 `dist/` 重建产物即可。
- **数据面**：**无数据迁移、无 schema 变更**；`state/`、`cache/`、`output/` 均为本地产物，回滚不需处理。
- **发布物面**：`dist/SHA256SUMS.txt` 需与重建后的产物**同步重算**，避免校验与内容错配。

---

## ⚠️ 待完善 / 已知局限

**未验证项（逐条声明，不假装通过）**

1. **MSI 安装版**：`dist/` 无 `.msi`，`packaging/README.md` 明示「MSI 受环境限制」→ **未产出/未验证**。
2. **Inno `setup.exe`**：`dist/` 无产物，需本机 `ISCC.exe` 编译 `inno.iss` → **未验证**。
3. **全量重新构建**（`packaging/build.py --portable/gui`）：**未执行**——会覆盖已核验产物且耗时高；已确认 PyInstaller 6.22.2 可用。**建议在修 B-2 时跑一次**。
4. **联网链路**（`fetch` / `probe` / `verify_mirror_rules.py`）：按用户纪律**未对真实第三方站点发起批量请求** → **未验证**；所有链路验证均走离线缓存 / fixture。
5. **真实 Ctrl-C 打断后续爬**：**未做真机打断**（避免联网）；改以 `tests/test_state.py::TestResumeDecisionLogic` + `test_done_cids_covers_state_and_orphan_cache` + `engine.run()` L697-699 代码级/用例级佐证（均 PASS）。
6. **Browser 路由（Playwright）与字体解码（fontTools/brotli）**：因非最小依赖**未实跑**，仅静态审阅 → F-005（重定向）未构造真实 PoC，标注为**理论**；#8（brotli）基于代码阅读，未构造 woff2 站点端到端复现。

**已知局限**

- 本次三路均为**离线 + 静态 + 本地构造**验证，未在真实站点上压测；规则池（146 条启用）在站点改版后是否仍然有效，不在本次范围。
- 严重度分级由主理人统一校准：安全官原列 F-006 为 P3、代码审查员原列 #1 为 🟠 —— 合并后统一为 #16(🟡) 与 #6(🟠)，以「是否阻塞发版」为准绳。
- 主理人对成员结论做了**一处否决**：不采信代码审查员的「无 🔴」，因安全官发现了其审查维度未覆盖的路径穿越，且主理人已独立复现。

---

## 📚 成员产出索引

| 成员 | 角色 | 原始产出（对话内） |
|------|------|------------------|
| gstack-product-reviewer | 产品官（代码审查） | 发现表 11 条（4🟠/5🟡/2🟢）；README↔实现一致性逐条实核；对主理人 3 个存疑点的独立澄清；实跑 `pytest -q` 288 passed、`selfcheck` PASS、`check_repo` 11 项 PASS |
| gstack-security-officer | 安全卫士（OWASP+STRIDE） | STRIDE 威胁建模表 + OWASP Top 10 检查表；发现表 6 条（1🔴/2🟠/3🟡）；密钥/git 历史 0 命中扫描；免费六层约束无旁路核验 |
| gstack-qa-lead | 质量门神（QA+发布） | 任务状态摘要表 15 项（含退出码）；Issue 清单 4 条；README 可量化宣称 vs 实测对照表 7 条；未验证项 5 类；回滚预案与发布建议 |

---

> 本报告由软件工坊 AI 协作生成，关键决策请由工程负责人复核。
