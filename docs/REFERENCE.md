# 借鉴记账（REFERENCE.md）

> 遵循全哥的「创新三原则」第 1 条：**借鉴必记账 —— 来源 + 许可证 + 范围**。
> 本文件记录本项目的每一处外部参考、取用了什么、**以及明确排除了什么**。

---

## 一、本家复用（最高优先级参照）

| 项 | 内容 |
|---|---|
| 来源 | `本家 webcopier 仓`（WebCopier v5.3/5.4，全哥内部项目） |
| 许可证 | 内部项目（全哥创建），本项目为其派生子项目 |
| 关系 | 按 webcopier `SKILL.md` 既有约定「**复制优于共享**」——把复用层落到本项目内，上游改动靠手工对照 |

### 抽取的文件与范围

| 本项目文件 | 来源 | 抽取范围 | 改造点 |
|---|---|---|---|
| `noveldown/constants.py` | `webcopier/constants.py` | `DEFAULT_HEADERS` / `ANTICRAWL_STATUS_CODES` / 版本常量 | 剔除 GUI 字体常量；新增免费约束常量 |
| `noveldown/identity_manager.py` | `webcopier/identity_manager.py` | `BrowserIdentityManager` 全文 + 单例 + 内置回退池 | **移除 `cookie_str` 参数**（免费约束） |
| `noveldown/identities.json` | `webcopier/identities.json` | 1373 条浏览器身份池，原样复制 | 无 |
| `noveldown/http_client.py` | `webcopier/http_client.py` | `parse_proxy` / `build_headers` / `auto_referer` / `http_get` + 退避重试 | ① **彻底移除 Cookie / `http_post` / 登录路径**；② 移除 `requests_cache`；③ 移除 `_curl_impersonate` 魔法键；④ **新增每线程连接池**（见下） |
| `noveldown/ratelimit.py` | `webcopier/engine.py::RateLimiter` | 限速语义与线程锁实现 | 拆为独立模块；新增 `slowdown`/`recover` 自适应降速 |

### 本项目的改进点（相对复用源）

**每线程连接池** —— webcopier 的 `http_get` 每次 `requests.get()` 都重建 TCP+TLS。
实测（2026-09-20，biqu520.net）冷启动 3.62s、热连接 0.13-0.30s，**约 12× 差距**；
抓一本 2653 章的书会因此多花数小时。改造后每次请求后清空 cookie jar，
连接复用只发生在传输层，不承载任何凭据。

---

## 二、网络参考资料

| 来源 | 许可证 | 取用 | **明确排除** |
|---|---|---|---|
| [CSDN 136774768](https://blog.csdn.net/Du_XiaoNan/article/details/136774768)《小说网站数据爬取》 | 未声明 | 基础 requests + BeautifulSoup 流程、请求头写法、`time.sleep` 限速意识 | 用 F12 断点绕过起点调试保护以取 Cookie 的做法 |
| [CSDN 139809090](https://blog.csdn.net/Du_XiaoNan/article/details/139809090)《多线程多进程的 python 爬虫脚本项目》 | 未声明 | **生产者-消费者 + 线程池**的并发结构（`Queue` + `ThreadPoolExecutor`） | 标题即「可爬起点 **VIP** 内容」，其全部 VIP 语义与 Cookie 依赖 |
| [52pojie 896364](https://www.52pojie.cn/thread-896364-1-1.html) FictionDown 发布帖 | — | 用于定位 FictionDown 项目与其设计目标（章节缺失/乱序校对） | — |
| [知乎 235616861](https://zhuanlan.zhihu.com/p/235616861)《爬取起点月票榜前100名》 | 未声明 | 请求头 + 随机 UA 的基础写法；「看 Network 原始响应而非 Elements」的调试习惯 | 只爬**书籍元信息**（书名/作者/简介），与章节无关；本项目未采用其代码 |
| [CSDN 103728095](https://blog.csdn.net/u012757419/article/details/103728095) | 未声明 | — | — |
| [知乎 58209887](https://zhuanlan.zhihu.com/p/58209887)《使用 Python 爬取起点小说网全部文章》 | 未声明 | **起点老版字体反爬的解法**：数字被映射成乱码，但 `<style>` 里的 woff 字体其 glyph 名直接是 `zero`/`one`/…/`period`，`TTFont.getBestCmap()` 即可还原 → **本项目的「按 glyph 名解码」途径即源于此**（见 `fontdecode.char_from_glyph_name`）；另记「page 参数位置会变」的小坑 | 同样只爬书籍元信息；其对起点反爬「很业余」的判断**已过时**（现为腾讯云 Chaos VM） |
| 本地 `_ref/1.txt` / `_ref/2.txt` | 同上两文正文留存 | — | — |

---

## 三、参照项目（只记来源与许可，**源码不入仓**）

### 为什么不把它们的源码放进仓库

这三份参照是调研用的第三方源码快照。本项目**刻意不把它们放进仓库**，理由有三：

1. **许可证冲突**——FictionDown 是 **GPL-3.0**、404-novel-downloader 是 **AGPL-3.0-or-later**，
   而本项目是 **MIT**。把 GPL/AGPL 源码随 MIT 仓分发会让仓库的许可状态变得含混；
   AGPL 尤其麻烦——**通过网络分发即触发源码开放义务**。
2. **本仓未复用其任何代码**——下表「本仓取用」一列全部停在**设计思路**层面，未复制一行实现。
   既然没有代码关系，就没有必要承担许可证传染风险。
3. **体积与时效**——合计约 21 MB，而三者都是公开仓库，任何人 `git clone` 即可取到最新版；
   在仓库里囤一份快照反而会过时，还会误导读者以为本仓依赖它们。

因此本仓只保留**上游链接 + 许可证说明**，并在 `.gitignore` 里挡掉 `_ref/`、`*.zip`、`*.tar.gz`。
这条约束是可机械验证的：`python tools/check_repo.py`（第 1/2/3/6 项）。

### 参照清单

| 项目 | 上游 | 许可证（依据） | 本仓取用（仅设计层面） | **明确排除** |
|---|---|---|---|---|
| **FictionDown**<br>（Go，2019） | <https://github.com/ma6254/FictionDown> | **GPL-3.0**<br>*仓库根 `LICENSE` 为 GNU GPL v3 全文；未见项目方对 "or later" 的明确声明，故按 `GPL-3.0-only` 保守对待* | ① 「章节缺失 / 顺序错乱」的**检查维度**；② 广告过滤思路；③ **断点续爬**的设计思路；④ 保留卷结构 | ① 「起点正版信息 + 笔趣阁盗版正文互补，**补齐 VIP 章节**」的整套工作流——直接违反本项目免费约束；② 其 Go 代码（**未复制一行**） |
| **404-novel-downloader**<br>（TypeScript / 油猴，v5.2.0） | <https://github.com/404-novel-project/novel-downloader><br>作者 BGME | **AGPL-3.0-or-later**<br>*依据 `package.json` 的 `"license"` 字段* | ① **规则驱动站点适配**的架构思想（一书一规则、多类目录形态）；② EPUB 章节结构参考 | ① 登录 Token / VIP 相关参数与流程；② 其 AGPL 代码（**传染性许可证，未复制一行**，仅借鉴架构思路） |
| **backupqidian**<br>（Python，2020-01 最后提交） | <https://github.com/zombie110year/backupqidian> | **未声明许可证**<br>*仓库内**无 LICENSE / COPYING 文件**；按著作权法默认「保留全部权利」对待* | 仅取一个**事实**：起点免费目录存在可用接口 `ajax/book/category`，以及 Markdown 输出规范（标题为 1 级、段落空行分隔）的思路 | `--vip` 开关、`cookies.txt` 载入、`get_session()` 凭据注入——**全部排除**。因其未声明许可，本仓**更不会**收录其源码 |

> **参考价值判断**：真正与本项目最契合的是**本家 `本家 webcopier 仓`**（见第一节），
> 上表三份只用来说明「别人是怎么做的」，以及界定**哪些做法本项目不做**。

### 本地快照（仅存在于开发机 `_ref/`，已被 `.gitignore` 忽略）

保留 sha256 是为了将来能确认"当时看的是哪一版"，也便于核对是否被人篡改。

| 快照文件 | 大小 | sha256（前 16 位） |
|---|---|---|
| `FictionDown-master.zip` | 72 KB | `a562a094b7ecd37f…` |
| `FictionDown_0.1.3_Windows_x86_64.tar.gz` | 5.2 MB | `9bff0c41ee591b27…` |
| `FictionDown_0.1.3_Windows_i386.tar.gz` | 4.9 MB | `31c1e3b7d74c13f7…` |
| `novel-downloader-master.zip` | 3.7 MB | `1e3f6dde23ab7c63…` |
| `backupqidian-master.zip` | 12 KB | `7ae5a071ce12766f…` |

> 若需重新获取：直接 `git clone --depth 1` 上表中的上游地址。
> 本地 `_ref/README.md` 记有各快照的完整来源与校验命令（该文件同样不入仓）。

---

## 四、字体反爬所用的参考字体（第三方数据）

番茄小说的正文被字体混淆（详见 [RULES.md](./RULES.md) 的「字体反爬」）。解码需要
**同版本**的参考字体做字形轮廓匹配。

| 项 | 内容 |
|---|---|
| 组件 | **Source Han Sans SC（思源黑体）** `SourceHanSansSC-Normal` **Version 2.002** |
| 上游 | <https://github.com/adobe-fonts/source-han-sans> （tag `2.002R`） |
| 下载源 | `https://cdn.jsdelivr.net/gh/adobe-fonts/source-han-sans@2.002R/OTF/SimplifiedChinese/SourceHanSansSC-Normal.otf` |
| 许可 | **SIL Open Font License 1.1**（OFL-1.1）——允许自由使用、修改、再分发 |
| 大小 / 指纹 | 约 16.1 MB；`sha256 = 69a090057ee75936…`（前 16 位，脚本会校验） |
| 本仓取用 | **只取事实性对应关系**：由 `tools/build_fontmap.py` 派生出 `{字形轮廓哈希: 字符}` 索引 |

### 字体本体不入仓，但派生索引**随仓分发**

从 v0.5.0 起，字体解码在运行时**不再依赖参考字体、也不再联网**：

| 产物 | 是否入仓 | 体积 | 说明 |
|---|---|---|---|
| 参考字体 `SourceHanSansSC-Normal.otf` | **否** | ~16.1 MB | 只有维护者重建索引时才由 `tools/build_fontmap.py` 按需下载并校验 sha256 |
| 紧凑索引 `noveldown/fontmaps/sourcehan-sc-2.002.bin` | **是** | ~459 KB | gzip 压缩的 JSON（44 260 条 `{6字节轮廓哈希: 字符}`）；运行时唯一路径，零下载 |

1. **字体本体不入仓**：16 MB 且可一条命令重建，没有入库理由；版本敏感（换版本会解码失配），
   固定在 `2.002R` 并由脚本校验 sha256 更可靠。
2. **派生索引入仓**：它是**事实性对应关系**（轮廓哈希 → 字符），不是字体数据本身；
   体积仅 459 KB，入仓即可让终端用户开箱即用、完全离线。
   OFL-1.1 允许再分发，此做法在许可上无碍。

> 该字体是**本站点专用**能力：`font_decode` 未启用的规则完全不涉及它，
> 也不影响其它站点的运行。索引缺失时只会让番茄这类站点解码失败并给出明确指引。

---

## 四之二、第二轮参考资料评阅（2026-09-20）

全哥新给的 5 篇教程/文章 + 1 个程序。**结论：全部只在「方法论/候选站」层面有参考价值，
没有一项需要改代码**（本项目的实现已超出这些教程覆盖的范围）。逐条记账：

| 来源 | 类型 / 许可 | 取用与结论 |
|---|---|---|
| <https://docs.pingcode.com/insights/ghk1gxm29zkq4cfvusxadav4> 《python 怎么爬取小说》 | 厂商博客文章（PingCode，内容为方法论；**未取任何代码**） | **价值最高**（全哥判断正确）。它把路线讲成「先判页面类型 → 目录 → 正文 → 清洗 → 保存」，并列出四类高频失败。**逐条独立印证**了本项目已有设计：① 先判静态/异步/强反爬/图片混淆 → 我们的 triage；② 目录最容易出错 → 我们的目录归一化；③ 「先结构化，后成书」→ 我们的按 cid 章节缓存 + 四格式导出；④ 断点续抓/重试/去重/日志 → 我们全有；⑤ 「返回 200 却抓不到正文」→ 我们本轮踩的寒武纪年；⑥ 正文容器用「候选区域 + 内容校验」→ 我们的 `content_selectors` + 回退。**唯一新点子**：「按文本长度/标点密度自动挑正文容器」——记为待评估（见 NEW_SITES_PLAN §10.2） |
| <https://blog.csdn.net/weixin_41943766/article/details/155093905> | CSDN 新手教程 | 无新意（requests+bs4、`#list a` 目录 / `#content` 正文、`time.sleep(1.5)`）。仅记一个候选站 `xsbiquge.com` |
| <https://cloud.tencent.com/developer/article/2576592> | 腾讯云社区文章 | 无新意（多线程、ebooklib 生成 epub、fake_useragent、代理池、selenium headless）。⚠ 其中 **pytesseract 识别验证码** 属本项目红线（不做验证码）；其 `--headless` 用法正是我们已知**会被识破**的方式（见 RULES.md 反检测一节） |
| <https://blog.csdn.net/Mr_Ohahah/article/details/107597333> | CSDN 小白篇 | 无新意（正则提取、`#pager_next` 链式翻页、docx 输出）。可借鉴的一点：用 `requests.adapters.HTTPAdapter(max_retries=3)` 做**传输层**重传（本项目是应用层重试）。候选站 `dusuu.com`（读书网，`/ml/{bid}/{cid}.html`） |
| <https://www.cnblogs.com/dcpeng/p/18344946> | 博客园文章 | 无新意（`div.book_list a` 目录 / `div#htmlContent` 正文）。候选站 `biquw.com` |
| `novel-spider-main.zip`（@LMingJian，2025） | **GPL-3.0** 程序，**不入仓**（与本项目 MIT 不兼容，处理方式同 FictionDown） | 语言 Python（Selenium 无头浏览器 + CSS 选择器书源）。**书源格式**为简化版 Yuedu 格式。内含 2 个书源候选：`sudugu.org`（速读谷，`.con` / `#list li a`）、`soushuwang.cc`（搜书网，`#chaptercontent` / `.listmain dd a`）。⚠ **红线冲突**：其 Cloudflare 方案是「**手动**在安全浏览器里取 `cf_clearance` cookie 再绕过」——属凭据流程 + 人工环节，本项目**不做**（我们走 `--curl-cffi` / 浏览器路由）。另其 README 提到书源参考 [XIU2/Yuedu](https://github.com/XIU2/Yuedu) 书源库，**那是更大的站点候选池**（本项目可当线索用，不复制其代码） |

> 以上第三方源码/程序**一律不入仓**，仅记来源、许可与结论，由 `tools/check_repo.py` 机械校验。

---

## 五、实测数据来源

本项目所有站点规则均基于**实际请求所得页面**逆向，非猜测。关键实测记录：

| 日期 | 站点 | 发现 |
|---|---|---|
| 2026-09-20 | `www.shuquge.com` | 标准笔趣阁结构；目录页 1594 项含 12 项「最新章节倒序回显」→ 归一化后 1582 章 |
| 2026-09-20 | `www.bqgbe.cc` | 正文按段 base64 编码进 `document.writeln(随机命名空间.随机函数名('…'))`；章节内部分页（`54948_1.html`）；目录用 CSS `nth-child(n){display:none}` 隐藏列表项；目录 3 页 → 169 章 |
| 2026-09-20 | `www.biqu520.net` | 与 bqgbe 同模板；目录项为 `onclick="随机函数名(id)"`（无 href）；27 页 → 2653 章，与站点自报分页完全一致 |
| 2026-09-20 | `www.qidian.com` | 腾讯 Chaos VM：捆绑 Chromium + headless → `sec-ch-ua` 含 `HeadlessChrome`、`navigator.webdriver=true`，202 挑战页 42s 不放行；本机真 Chrome + headed + 关 AutomationControlled → 数秒内渲染出 67~70 万字节书页，`#bookName`/`.chapter-name`(1418) 命中，指纹 `webdriver=false / plugins=5 / languages=zh-CN,zh / UA 不含 HeadlessChrome`。目录走 JSON 接口 `/ajax/book/category`（`data.vs[].cs[]`，逐章 `sS`：**1=免费、0=VIP**，与直觉相反） |
| 2026-09-20 | `www.qidian.com` | **A/B 对照**：带与不带 `stealth.min.js`，上述指纹与渲染结果**完全一致** → 判定 stealth 对本站点非必需（故不随仓分发，见第六节） |
| 2026-09-20 | `www.tadu.com` | 目录 `/book/catalogue/{bid}`；章节页 `#artContent` 为空、正文由 `/getPartContentByCodeTable/{bid}/{seq}` 以 JSON 下发（`{seq}` 是序号不是 cid）；每个 `<p>` 带 `data-limit`，其中等于 `base64(当前章 cid)` 的若干段是**站点自注入的推广水印**（站点自己用 CSS 隐藏），实测 7/77 → 规则按此精确剔除。**同章高频直连会被降级**（越来越多段落被标记隐藏），真人浏览器稳定 |
| 2026-09-20 | `www.shuhai.com` | 杰奇 CMS（`ajax_gets=jieqi_contents`），GBK；详情页 `/book/{bid}.htm`（不带 .htm 是榜单页）；目录 `?method=getcatalog` **不带 CALLBACK 即裸 HTML**；目录项 `<div class=chapter-item>` 内 **215/645 的 `<a>` 文本为空**（标题在 `</a>` 之后）、VIP 是同级 `<span class="vip">` |
| 2026-09-20 | `www.ciweimao.com` | 目录 817 章可读，但**任意章节页 307 → `/signup/man_machine_verify`**（标题「验证码 - 刺猬猫」，引 geetest）；**真 Chrome + headed 仍被挡** → 判为人机验证**红线**，不予支持 |
| 2026-09-20 | `www.linovelib.com` | 书籍页 `/novel/{bid}.html`；**目录在独立页** `/novel/{bid}/catalog`（38 卷 → `ul.chapter-list > li > a`，426 章）；正文 `div#TextContent` **在 HTML 里**；目录无 VIP 标记（全免费）；作者与书名揉在 `.book-author` 需 `author_pattern`；cid 跳号故排序必须 `document_order` |
| 2026-09-20 | `www.linovel.net` | **站点已关闭**（未经授权刊载大量日本轻小说译作，版权侵权）：首页/书籍页持续 `Read timed out`，`/book/{id}` 404 → 记停用存根 |
| 2026-09-20 | 多站 | 不可达（curl 000）：bqg70.com、b520.cc、biqiuge.com、bqgui.cc、22biqu.com、xbiquge.la、69shuba.com、bqg128.com；WAF 403：beqege.cc |

---

## 六、未采用但仍可能有用

- `requests_cache`：本项目改为按 cid 自管章节缓存（粒度更贴合断点续爬），不再依赖它。
- `trafilatura` / `readability` / `newspaper`：通用正文抽取算法对小说章节页过重且会破坏段落边界，本项目用规则化的容器选择器 + 段落切分替代。
- `curl_cffi`：已接入（`--curl-cffi`），但四个可用站点均无 TLS 指纹校验，默认关闭。
- `fontTools` / `brotli`：**已采用，但仅服务字体反爬那一项功能**（见第四节）。
  非必需依赖——未安装时其它站点照常工作。

### puppeteer-extra-plugin-stealth（评估后**未随仓分发**）

| 项 | 内容 |
|---|---|
| 组件 | `puppeteer-extra-plugin-stealth` 产出的 `stealth.min.js` |
| 上游 | <https://github.com/berstend/puppeteer-extra> |
| 许可 | MIT |
| 本仓取用 | **不入仓**。仅保留一个**可选外挂入口**：设环境变量 `NOVELDOWN_STEALTH_JS` 或规则里 `browser.stealth_js` 指向自备的 `stealth.min.js`，即会在页面脚本前注入 |

**为什么不分发**：① 本仓铁律「第三方源码不入仓」（与 FictionDown / novel-downloader 同一处理，
见第三节）；② **实测非必需** —— 起点的关键阻断是「捆绑 Chromium + headless 暴露
`HeadlessChrome`、`navigator.webdriver=true`」，用**本机真 Chrome + headed +
`--disable-blink-features=AutomationControlled`** 即可解掉；带/不带 stealth.min.js
的 A/B 对照结果一致（见第五节）。因此内置伪装即可，第三方脚本降级为可选增强。
（`stealth.min.js` 已在 `.gitignore` 中，即便本地放置也不会被提交。）

