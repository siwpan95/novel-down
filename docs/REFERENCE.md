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

## 三、参照项目（本地压缩包，位于 `_ref/`）

> `_ref/` 仅为调研素材，**不参与构建、不进入版本库**（见 `.gitignore`）。

| 项目 | 许可证 | 借鉴范围 | **明确排除** |
|---|---|---|---|
| `ma6254/FictionDown`（Go） | **GPL-3.0** | ① 「章节缺失 / 顺序错乱」的**检查维度**；② 广告过滤的思路；③ **断点续爬**的设计思路；④ 保留卷结构 | ① 「起点正版信息 + 笔趣阁盗版正文互补，补齐 **VIP** 章节」的整套工作流——直接违反本项目免费约束；② 任何代码（本项目未复制其 Go 代码） |
| `404-novel-downloader`（TS/油猴） | **AGPL-3.0** | ① **规则驱动站点适配**的架构思想（一书一规则、多类目录形态）；② EPUB 章节结构参考 | ① 登录 Token / VIP 相关参数与流程；② 其 AGPL 代码（**传染性许可证，未复制任何代码**，仅借鉴架构思路） |
| `backupqidian`（Python） | 未声明 | 起点免费目录 API 的存在性与调用形态；Markdown 输出规范（标题为 1 级、段落空行分隔） | `--vip` 开关、`cookies.txt` 载入、`get_session()` 凭据注入——**全部排除** |

---

## 四、实测数据来源

本项目所有站点规则均基于**实际请求所得页面**逆向，非猜测。关键实测记录：

| 日期 | 站点 | 发现 |
|---|---|---|
| 2026-09-20 | `www.shuquge.com` | 标准笔趣阁结构；目录页 1594 项含 12 项「最新章节倒序回显」→ 归一化后 1582 章 |
| 2026-09-20 | `www.bqgbe.cc` | 正文按段 base64 编码进 `document.writeln(随机命名空间.随机函数名('…'))`；章节内部分页（`54948_1.html`）；目录用 CSS `nth-child(n){display:none}` 隐藏列表项；目录 3 页 → 169 章 |
| 2026-09-20 | `www.biqu520.net` | 与 bqgbe 同模板；目录项为 `onclick="随机函数名(id)"`（无 href）；27 页 → 2653 章，与站点自报分页完全一致 |
| 2026-09-20 | 多站 | 不可达（curl 000）：bqg70.com、b520.cc、biqiuge.com、bqgui.cc、22biqu.com、xbiquge.la、69shuba.com、bqg128.com；WAF 403：beqege.cc |

---

## 五、未采用但仍可能有用

- `requests_cache`：本项目改为按 cid 自管章节缓存（粒度更贴合断点续爬），不再依赖它。
- `trafilatura` / `readability` / `newspaper`：通用正文抽取算法对小说章节页过重且会破坏段落边界，本项目用规则化的容器选择器 + 段落切分替代。
- `curl_cffi`：已接入（`--curl-cffi`），但三个免费站均无 TLS 指纹校验，默认关闭。
