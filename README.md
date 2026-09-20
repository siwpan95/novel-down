# novel-down · 读书爬虫（仅免费章节）

规则驱动的网络小说离线阅读工具：**目录发现 → 并发抓取 → 免费章节硬拦截 → 校对 → 四格式导出**。

> **本项目仅用于免费章节，不涉及任何 VIP 付费内容。**
> 这不是免责声明，而是[**六层可验证的技术约束**](./docs/FREE_ONLY.md)——
> 无登录、无 Cookie、无购买、无付费墙绕过，且可用 `selfcheck` 机械校验。

![阅读器界面](docs/screenshot.png)

*单文件 HTML 阅读器（导出产物之一）。截图内容为脚本自撰的占位文本，非任何真实作品。*

---

## 特性

- **规则驱动**：一个站点一个 JSON，加站不改代码。内置 3 个实测可用站点规则。
- **反爬三件套处理**：JS 内联 base64 正文、目录倒序回显、CSS 隐藏列表项、多页目录。
- **章节归一化**：全收集 → 按 cid 去重 → 按 cid 升序编号，统一消解三类目录反爬。
- **免费章节六层拦截**：站点黑名单 / 规则自证 / 目录 VIP 标记 / 正文付费墙 / 导出终检 / 代码自检。
- **断点续爬**：章节级缓存（按 cid 索引）+ 状态文件，Ctrl-C 后重跑即续。
- **四格式导出**：TXT / Markdown / **EPUB3（纯标准库手写）** / **单文件 HTML 阅读器**。
- **校对报告**：缺失、乱序、重复、广告残留、异常短章、编码异常、受保护章节。
- **身份池 + 连接池**：1373 条浏览器身份轮换 + 每线程连接复用（实测约 12× 提速）。
- **零 JS 依赖运行**：`python -m noveldown`，无需浏览器/Node。

---

## 快速开始

```bat
cd G:\repos\novel-down

:: 看有哪些站点规则
F:\Python314\python.exe -m noveldown sites

:: 规则自检：抓目录 + 抽 1 章，确认规则可用
F:\Python314\python.exe -m noveldown probe "https://www.shuquge.com/txt/207266/index.html"

:: 抓整本并导出（先抓 20 章试水）
F:\Python314\python.exe -m noveldown fetch "https://www.bqgbe.cc/txt/445/" --limit 20

:: 继续抓完（自动从断点续，不会重抓）
F:\Python314\python.exe -m noveldown fetch "https://www.bqgbe.cc/txt/445/"

:: 已抓过的话，换格式重导（不联网）
F:\Python314\python.exe -m noveldown export "https://www.bqgbe.cc/txt/445/" --formats epub,html

:: 只看校对报告
F:\Python314\python.exe -m noveldown report "https://www.bqgbe.cc/txt/445/"

:: 免费约束机械自检
F:\Python314\python.exe -m noveldown selfcheck
```

---

## 命令一览

| 命令 | 作用 |
|---|---|
| `sites` | 列出可用站点规则 |
| `rules [--json]` | 查看规则详情 |
| `probe <url>` | **规则自检**：抓目录 + 抽 1 章，逐环节报命中数 |
| `fetch <url>` | 抓取整本（支持断点续爬）并导出 |
| `export <url>` | 仅从断点/缓存重新导出（不联网） |
| `report <url>` | 仅产出校对报告 |
| `selfcheck` | 免费章节约束的代码级机械自检 |

### `fetch` 选项

| 选项 | 默认 | 说明 |
|---|---|---|
| `--limit N` | 0（全部） | 最多抓 N 章，调试用 |
| `--force` | 关 | 忽略断点，清空缓存重抓 |
| `-o/--out DIR` | `output/` | 输出根目录 |
| `--formats` | `txt,md,epub,html` | 导出格式 |
| `--concurrency N` | 4 | 并发数 |
| `--delay S` | 1.2 | 基础请求间隔秒（另加 0-0.8s 抖动） |
| `--timeout/--retries` | 30 / 3 | 超时与重试 |
| `--proxy` | — | 代理地址 |
| `--curl-cffi` | 关 | 启用 TLS 指纹伪装 |
| `-q/--quiet` | 关 | 安静模式 |

---

## 内置站点规则（2026-09-20 实测）

| 站点 | 匹配域名 | 目录 | 章节数 | 实测结果 |
|---|---|---|---|---|
| 书趣阁 | `shuquge.com` / `xshuquge.net` | 单页 `div.listmain` | 1582 | 第 1 章 106 段 / 2865 字，过滤 2 行广告 |
| 笔趣阁 bqgbe | `bqgbe.cc` | 3 页（select + 链接） | 169 | 第 1 章 55 段 / 1352 字，base64×33 |
| 笔趣阁 biqu520 | `biqu520.net` | 27 页（select） | 2653 | 第 1 章 45 段 / 1345 字，base64×23 |

> 不可达（已排除）：bqg70.com、b520.cc、biqiuge.com、bqgui.cc、22biqu.com、
> xbiquge.la、69shuba.com、bqg128.com（curl 000）；beqege.cc（WAF 403）。
>
> 新增站点见 [docs/RULES.md](./docs/RULES.md)（含探针工具与三种典型形态的完整 JSON）。

---

## 输出结构

```
output/
├── state/<站点>_<书籍ID>.json        进度快照（书名、章节表、状态分布）
├── cache/<站点>_<书籍ID>/<cid>.json  单章缓存（按 cid 索引，重跑不重抓）
└── <书名>_<站点>/
    ├── <书名>_<站点>.txt             纯文本
    ├── <书名>_<站点>.md              Markdown（YAML front matter + 卷/章层级）
    ├── <书名>_<站点>.epub            EPUB3（纯 zipfile 手写）
    ├── <书名>_<站点>.html            单文件离线阅读器
    └── proofread.json                校对报告
```

### 单文件 HTML 阅读器

零依赖、双击即读、可直接拷进手机。带：

- 目录侧栏 + 章节搜索
- 上一章 / 下一章 + 键盘（`←` `→` `j` `k` `空格` `Home` `End`）
- 阅读进度记忆（localStorage 记住当前章与滚动位置）
- 字号 / 行距调节 + 三档主题（日间 / 米黄 / 夜间）

---

## 项目结构

```
novel-down/
├── noveldown/
│   ├── cli.py                 命令行入口
│   ├── engine.py              抓取编排：目录发现 → 并发抓取 → 断点续爬
│   ├── rules.py               规则加载 / 校验 / 匹配
│   ├── rules/*.json           站点规则（一站点一文件）
│   ├── parser.py              目录与正文解析、目录归一化
│   ├── predecode.py           通用预解码器（JS 内联 base64 还原）
│   ├── freeguard.py           免费章节六层拦截 + 代码自检
│   ├── proofread.py           校对
│   ├── state.py               断点续爬（按 cid 索引）
│   ├── models.py              Book / Chapter 模型
│   ├── exporters/             txt / md / epub / htmlreader
│   ├── http_client.py         HTTP 层（复用 webcopier + 连接池改进）
│   ├── identity_manager.py    身份池（复用 webcopier）
│   ├── ratelimit.py           限速器（复用 webcopier + 自适应降速）
│   ├── identities.json        1373 条浏览器身份
│   └── constants.py           常量 + 免费约束词表
├── tools/probe_site.py        站点结构探针（编写新规则用）
├── tools/verify_reader.py     真实浏览器验证 HTML 阅读器（Playwright）
├── tools/make_screenshot.py   生成 README 演示截图（用自撰文本，不含第三方正文）
├── tests/                     85 个用例（含端到端拦截集成测试）+ fixtures
├── docs/
│   ├── REFERENCE.md           借鉴记账（来源 + 许可证 + 范围 + 排除项）
│   ├── RULES.md               规则格式与三种典型形态
│   └── FREE_ONLY.md           免费章节六层约束
└── output/                    产物（不入版本库）
```

---

## 依赖

**运行只需 `requests` + `beautifulsoup4`**（EPUB/HTML 导出为纯标准库实现）：

```bat
F:\Python314\python.exe -m pip install -r requirements.txt
```

| 包 | 用途 | 必需 |
|---|---|---|
| `requests` | HTTP | ✓ |
| `beautifulsoup4` | HTML 解析 | ✓ |
| `lxml` | bs4 的快速解析器（缺失自动回退 `html.parser`） | 建议 |
| `soupsieve` | CSS 选择器（随 bs4 安装） | ✓ |
| `curl_cffi` | TLS 指纹伪装（`--curl-cffi`） | 可选 |

实测本机 `F:\Python314`（Python 3.14.7）上述依赖**全部可用**。

---

## 测试

```bat
F:\Python314\python.exe -m unittest discover -s tests -t .
```

**85 个用例，约 3 秒**（离线，不联网）。覆盖：预解码（含真实页面回归）、
目录归一化、目录页发现、正文提取、免费六层拦截、四格式导出
（含 EPUB 结构与 XML 合法性校验）、断点续爬状态机、规则校验、校对报告。

另有两项**端到端**验证：

```bat
:: 1. 真实引擎 + 本地合成站点：证明「locked 章节零请求」「付费墙正文被丢弃」
::    「导出拒绝」「成品无付费字样」——随单测一起跑
F:\Python314\python.exe -m unittest tests.test_integration_guard -v

:: 2. 真实浏览器（Playwright + Chromium）操作 HTML 阅读器并断言 30 项
F:\Python314\python.exe tools\verify_reader.py "output\<书名>_<站点>\<书名>_<站点>.html"
```

---

## 注意事项

- **版权**：抓下的内容版权归原作者与发布方所有，仅供个人离线阅读，不得再分发或商用。
- **礼貌抓取**：默认并发 4、间隔 1.2s±0.8s；遇 403/412/429/503 自动全局降速。
  抓一本 2653 章的书约需 1.5 小时（含限速）。
- **站点改版**：规则会失效。用 `probe` 定位是哪一环断了，或重跑 `tools/probe_site.py`。
- **本机文件系统较慢**（实测创建+写+删一个目录约 1.5s，疑似杀软实时扫描），
  单测已改为共享临时目录以避免 I/O 成为瓶颈。

## 许可

MIT，见 [LICENSE](./LICENSE)。第三方来源与许可证记账见 [docs/REFERENCE.md](./docs/REFERENCE.md)。
