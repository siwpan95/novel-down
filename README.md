# novel-down · 读书爬虫（仅免费章节）

规则驱动的网络小说离线阅读工具：**目录发现 → 并发抓取 → 免费章节硬拦截 → 校对 → 四格式导出**。

> **本项目仅用于免费章节，不涉及任何 VIP 付费内容。**
> 这不是免责声明，而是[**六层可验证的技术约束**](./docs/FREE_ONLY.md)——
> 无登录、无 Cookie、无购买、无付费墙绕过，且可用 `selfcheck` 机械校验。

![阅读器界面](docs/screenshot.png)

*单文件 HTML 阅读器（导出产物之一）。截图内容为脚本自撰的占位文本，非任何真实作品。*

---

## 特性

- **规则驱动**：一个站点一个 JSON，加站不改代码。内置 **12 个**实测可用站点规则（+4 条停用存根）。
- **双路由取页**：纯 HTTP 为主；目录靠 JS 渲染、或站点有 WAF 的，可切**真实浏览器路由**
  （`fetch_mode: browser`，Playwright/Chromium）。**反检测模式**（`browser.anti_detect`）
  用本机**真 Chrome + headed + 关 AutomationControlled + 语言自洽**，可过腾讯云 Chaos VM。
- **两种目录来源**：HTML 选择器，或 **JSON 接口**（`catalog.mode=json_api`）——
  后者常带**逐章 VIP 字段**（七猫 `is_vip`、起点 `sS`），比 HTML class 更可靠；
  支持**卷→章嵌套展开**（`flatten_field`，起点 `data.vs[].cs[]`）。
- **反爬六件套处理**：JS 内联 base64 正文、**字体反爬（PUA 码位，两途径解码）**、
  目录倒序回显、CSS 隐藏列表项、多页目录、**APP 墙**。
- **字体解码零参考字体依赖**：优先按 glyph 名解（秒级）；否则用**随仓**轮廓索引
  （`noveldown/fontmaps/`，459 KB，**不联网、不下载 17 MB 参考字体**）。
- **章节归一化**：全收集 → 去重 → 排序编号（`cid` 升序或 `document_order`），
  统一消解各站目录反爬。
- **免费章节六层拦截**：政策名单 / 规则自证 / 目录 VIP 标记 / 正文付费墙 / 导出终检 / 代码自检。
  站点层不拦"含 VIP"的正版站——拦截在**章节级**（见 [FREE_ONLY.md](./docs/FREE_ONLY.md)）。
- **断点续爬**：章节级缓存（按 cid 索引）+ 状态文件，Ctrl-C 后重跑即续。
- **四格式导出**：TXT / Markdown / **EPUB3（纯标准库手写）** / **单文件 HTML 阅读器**。
- **校对报告**：缺失、乱序、重复、广告残留、异常短章、编码异常、受保护章节。
- **产物终检**：机械验证"受保护内容零请求、零泄漏、无乱码残留"。
- **身份池 + 连接池**：1373 条浏览器身份轮换 + 每线程连接复用（实测约 12× 提速）。
- **零 JS 依赖运行**：`python -m noveldown`，无需浏览器/Node（除非站点用浏览器路由）。

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

| 站点 | 类型 | 匹配域名 | 章节数 | 实测结果 |
|---|---|---|---|---|
| **起点中文网** | 正版·含 VIP | `qidian.com` | **1418（153 免费 / 1265 VIP）** | **反检测浏览器路由**过腾讯 Chaos VM；目录走 **JSON 接口**（`data.vs[].cs[]`，逐章 `sS`：1=免费/0=VIP），1265 章标记 locked、**零请求**；抓 17 章 56 932 字，校对 PASS |
| **17K小说网** | 正版 | `17k.com` | **586（全免费）** | 目录 `dl.Volume dd a`；正文 `div#readAreaBox`；20 章 46 058 字；**无字体反爬** |
| **七猫免费小说** | 正版·免费阅读 | `qimao.com` | **708（20 可读 / 688 APP独占）** | 目录走 **JSON 接口**，逐章带 `is_vip`；688 章标记 locked、**零请求**；20 章 43 065 字 |
| **纵横中文网** | 正版·含 VIP | `zongheng.com` | **700（50 免费 / 650 VIP）** | 650 章在**目录层**带 `class="vip col-4"` → 标记 locked、**零请求**；50 章免费正文 163 576 字 |
| **番茄小说** | 正版·免费阅读 | `fanqienovel.com` | 966 | 目录 967 链接→966 章；正文 **362/362 个字体混淆码位全部还原** |
| **塔读小说网** | 正版·免费 | `tadu.com` | **2416（全免费）** | 目录 `/book/catalogue/{bid}`；**正文来自 JSON 接口**（章节页是空壳）→ `chapter.body_api`；3 章 5501 字，校对 PASS |
| **书海小说网** | 正版·含 VIP | `shuhai.com` | **645（40 免费 / 605 VIP）** | 正版详情页 `/book/{bid}.htm`；目录 `?method=getcatalog` **裸 HTML**（无需浏览器）；605 章带 `span.vip` → locked、**零请求**；5 章 11 585 字 |
| **飞卢小说网** | 正版·含 VIP | `faloo.com` | **12188（49 免费 / 12139 VIP）** | 书籍页一次给出全目录（约 2 MB）；免费/VIP 由**分段** `div.DivVip` 判定（逐章无标记）→ 12139 章 locked、**零请求**；3 章 6087 字 |
| **次元姬** | 正版·含 VIP | `ciyuanji.com` | **673（26 免费 / 647 VIP）** | Next.js：目录在 `__NEXT_DATA__`；**无书籍页**，入口为章节页；正文服务端加密、需浏览器渲染；647 章 locked、**零请求**；3 章 10370 字 |
| 书趣阁 | 免费阅读站 | `shuquge.com` / `xshuquge.net` | 1582 | 第 1 章 106 段 / 2865 字，过滤 2 行广告 |
| 笔趣阁 bqgbe | 免费阅读站 | `bqgbe.cc` | 169 | 第 1 章 55 段 / 1352 字，base64×33 |
| 笔趣阁 biqu520 | 免费阅读站 | `biqu520.net` | 2653 | 第 1 章 45 段 / 1345 字，base64×23 |

**另有三条停用存根**（红线，均附可复核证据）：`ciweimao.com`（刺猬猫，人机验证：章节页 307 → 极验）、
`xrzww.com`（息壤，登录墙：正文接口恒 `{code:401,用户验证失败}`，真 Chrome 也 401）、
`youdubook.com`（有毒小说网，同息壤）。详见 [FREE_ONLY.md](./docs/FREE_ONLY.md)。

> **纵横这条最能说明设计取向**：那是一本 705 章的正版小说，其中 **650 章是 VIP**。
> 「站点含 VIP」不是拒绝理由——那 50 章免费内容在射程内；VIP 章由**目录层的 class 标记**
> 拦下，`fetch` 全程只发出 50 次章节请求（已用 `tools/verify_artifacts.py` 机械验证）。

> **起点是天花板级对手**：腾讯云 Chaos VM（`__TENCENT_CHAOS_VM`，95 KB 虚拟机式 JS 挑战）
> 曾判死——捆绑 Chromium + headless 的 `sec-ch-ua` 里明写 `HeadlessChrome`、`navigator.webdriver=true`，
> 202 挑战页 42s 不放行。换成**本机真 Chrome + headed + 关 AutomationControlled** 后，
> 数秒内渲染出 67~70 万字节书页，指纹 `webdriver=false / plugins=5 / languages=zh-CN,zh`。
> 免费/VIP 由目录接口逐章 `sS` 字段切分（**1=免费、0=VIP**，与直觉相反）。

> **七猫的 688 章不是付费墙，是 APP 墙**：web 端只放前 20 章，其余章正文被替换成
> 「下载【七猫免费小说APP】，继续在APP内免费畅读全本内容」。那段占位文字有 78 字，
> **高于最小字数阈值**——不拦就会被当成正常正文存下来。已把「APP 墙」补进第 4 层特征词。

`python -m noveldown sites` 会列出全部规则。

> 新增站点见 [docs/RULES.md](./docs/RULES.md)（含探针工具、五种典型形态的完整 JSON、
> 「**字体反爬**」与「**浏览器路由**」的完整解法）。

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
│   ├── fontmaps/              随仓字体轮廓索引（459 KB，零下载解密用）
│   └── constants.py           常量 + 免费约束词表
├── tools/probe_site.py        站点结构探针（编写新规则用）
├── tools/build_fontmap.py     重建字体轮廓索引（仅维护者；--shipped 写回随仓索引）
├── tools/verify_artifacts.py  产物终检（零请求 / 零泄漏 / 无乱码残留）
├── tools/verify_reader.py     真实浏览器验证 HTML 阅读器（Playwright）
├── tools/make_screenshot.py   生成 README 演示截图（用自撰文本，不含第三方正文）
├── tools/check_repo.py        仓库卫生门禁（本仓不含第三方源码 / 凭据 / 产物）
├── tests/                     168 个用例（含端到端拦截集成测试）+ fixtures
├── docs/
│   ├── REFERENCE.md           借鉴记账（来源 + 许可证 + 范围 + 排除项）
│   ├── RULES.md               规则格式与典型形态（含字体反爬 / 浏览器路由）
│   └── FREE_ONLY.md           免费章节六层约束
└── output/                    产物（不入版本库）
```

---

## 依赖

**必需依赖只有 `requests` + `beautifulsoup4`**（EPUB/HTML 导出为纯标准库实现）：

```bat
F:\Python314\python.exe -m pip install -r requirements.txt
```

| 包 | 用途 | 必需 |
|---|---|---|
| `requests` | HTTP | ✓ |
| `beautifulsoup4` | HTML 解析 | ✓ |
| `lxml` | bs4 的快速解析器（缺失自动回退 `html.parser`） | 建议 |
| `soupsieve` | CSS 选择器（随 bs4 安装） | ✓ |
| `fontTools` + `brotli` | **字体反爬解码**（番茄小说）——不装只影响该类站点；解码所需的轮廓索引已随仓，**运行时不需要参考字体、不联网** | 可选 |
| `playwright` | **浏览器路由 / 反检测模式**（目录靠 JS 渲染、或有 WAF 的站点）——不装只影响该类站点；反检测还需本机装有 Google Chrome | 可选 |
| `curl_cffi` | TLS 指纹伪装（`--curl-cffi`） | 可选 |

实测本机 `F:\Python314`（Python 3.14.7）上述依赖**全部可用**。

### 环境变量

| 变量 | 作用 |
|---|---|
| `NOVELDOWN_STEALTH_JS` | 可选：自备 stealth 脚本（如 puppeteer-extra 的 `stealth.min.js`）路径。反检测模式会在页面脚本前注入它。**本项目不随仓分发该脚本**（实测内置伪装已足够，理由见 [docs/REFERENCE.md](./docs/REFERENCE.md) 第六节） |

---

## 测试

```bat
F:\Python314\python.exe -m unittest discover -s tests -t .
```

**168 个用例，约 3 秒**（离线，不联网）。覆盖：预解码（含真实页面回归）、
目录归一化（含 `document_order`/`keep_last`）、目录页发现、正文提取、
免费六层拦截、四格式导出（含 EPUB 结构与 XML 合法性校验）、
断点续爬状态机、规则校验、校对报告、字体反爬解码（glyph 名 / 轮廓索引）、
JSON 接口目录（含 `flatten_field` 卷→章展开、**内嵌 HTML 的 SSR 数据块**）、
段落级正文选择器（含**未命中回退**、**首段即标题**的精确删除）、
反检测启动参数与语言自洽、容器式目录项（含空 `<a>` 文本）、子元素/分段 VIP 判定、
正文接口 `body_api`（含水印剔除）、作者正则、书名清洗。

另有四项**端到端**验证：

```bat
:: 1. 真实引擎 + 本地合成站点：证明「locked 章节零请求」「付费墙正文被丢弃」
::    「导出拒绝」「成品无付费字样」——随单测一起跑
F:\Python314\python.exe -m unittest tests.test_integration_guard -v

:: 2. 真实浏览器（Playwright + Chromium）操作 HTML 阅读器并断言 30 项
F:\Python314\python.exe tools\verify_reader.py "output\<书名>_<站点>\<书名>_<站点>.html"

:: 3. 产物终检：受保护内容零请求 / 零泄漏 / 无乱码残留
F:\Python314\python.exe tools\verify_artifacts.py "output\<书名>_<站点>"

:: 4. 仓库卫生门禁：不含第三方源码 / 凭据 / 产物，且借鉴记账完整
F:\Python314\python.exe tools\check_repo.py
F:\Python314\python.exe tools\check_repo.py --selfcheck   # 证明门禁本身有效
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

MIT，见 [LICENSE](./LICENSE)。

**第三方来源**：本项目在调研阶段参照过三个第三方项目（FictionDown / 404-novel-downloader /
backupqidian），**只借鉴设计思路，未复制任何代码**，其源码**不入本仓**
（其中两份是 GPL-3.0 与 AGPL-3.0-or-later，与本仓 MIT 不兼容）。
浏览器反检测所用的 `puppeteer-extra-plugin-stealth`（MIT）经评估后**未随仓分发**
（实测内置伪装已足够，仅保留可选外挂入口）。
来源链接、许可证依据、取用范围与排除项逐条记在 [docs/REFERENCE.md](./docs/REFERENCE.md)，
并由 `tools/check_repo.py` 机械校验「本仓不含第三方源码」＋「借鉴记账完整」。
