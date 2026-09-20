# 借鉴记账（REFERENCE.md）

> 遵循全哥的「创新三原则」第 1 条：**借鉴必记账 —— 来源 + 许可证 + 范围**。
> 本文件记录本项目的每一处外部参考、取用了什么、**以及明确排除了什么**。

---

## 一、本家复用（最高优先级参照）

| 项 | 内容 |
|---|---|
| 来源 | `G:\repos\webcopier`（WebCopier v5.3/5.4，全哥内部项目） |
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

> **参考价值判断**：真正与本项目最契合的是**本家 `G:\repos\webcopier`**（见第一节），
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
| 本仓取用 | **只取事实性对应关系**：由 `tools/build_fontmap.py` 生成 `{字形轮廓哈希: 字符}` 索引（44 260 条，压缩后约 1.2 MB），缓存于 `output/fontcache/` |

### 为什么不把它（和索引）放进仓库

1. **不是代码依赖，是数据工具**——本项目**没有**把字体当资产分发，而是让脚本
   按需下载并校验指纹；索引只是派生数据，可从公开字体重建。
2. **体积**：字体 16 MB、索引 1.2 MB，而两者都可一条命令重建，没有入库的理由。
3. **版本敏感性**：参考字体**换版本就会解码失配**（实测 2.005 只有 7/363 命中）。
   固定在 `2.002R` 并由脚本校验 sha256，比在仓库里存一份容易过期的副本更可靠。

> OFL-1.1 允许再分发，因此**入库在许可上是可行的**——这里是工程取舍（体积 / 可重建性），
> 不是许可限制。若将来要离线使用，把字体放到 `output/fontcache/` 并在
> `tools/build_fontmap.py` 里改用本地路径即可。
>
> 该字体是**本站点专用**能力：`font_decode` 未启用的规则完全不涉及它，
> 也不影响其它三个站点的运行。

---

## 五、实测数据来源

本项目所有站点规则均基于**实际请求所得页面**逆向，非猜测。关键实测记录：

| 日期 | 站点 | 发现 |
|---|---|---|
| 2026-09-20 | `www.shuquge.com` | 标准笔趣阁结构；目录页 1594 项含 12 项「最新章节倒序回显」→ 归一化后 1582 章 |
| 2026-09-20 | `www.bqgbe.cc` | 正文按段 base64 编码进 `document.writeln(随机命名空间.随机函数名('…'))`；章节内部分页（`54948_1.html`）；目录用 CSS `nth-child(n){display:none}` 隐藏列表项；目录 3 页 → 169 章 |
| 2026-09-20 | `www.biqu520.net` | 与 bqgbe 同模板；目录项为 `onclick="随机函数名(id)"`（无 href）；27 页 → 2653 章，与站点自报分页完全一致 |
| 2026-09-20 | 多站 | 不可达（curl 000）：bqg70.com、b520.cc、biqiuge.com、bqgui.cc、22biqu.com、xbiquge.la、69shuba.com、bqg128.com；WAF 403：beqege.cc |

---

## 六、未采用但仍可能有用

- `requests_cache`：本项目改为按 cid 自管章节缓存（粒度更贴合断点续爬），不再依赖它。
- `trafilatura` / `readability` / `newspaper`：通用正文抽取算法对小说章节页过重且会破坏段落边界，本项目用规则化的容器选择器 + 段落切分替代。
- `curl_cffi`：已接入（`--curl-cffi`），但四个可用站点均无 TLS 指纹校验，默认关闭。
- `fontTools` / `brotli`：**已采用，但仅服务字体反爬那一项功能**（见第四节）。
  非必需依赖——未安装时其它站点照常工作。
