# Changelog

本项目所有值得注意的变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-09-20

首个可用版本。三站点规则经端到端实测，四格式导出产物通过结构校验。

### Added

- **规则驱动引擎**：`noveldown/rules/*.json` 一站点一文件，加站不改代码。
  内置 3 条实测规则：`shuquge.com`（1582 章）、`bqgbe.cc`（169 章）、`biqu520.net`（2653 章）。
- **通用预解码器** `predecode.py`：还原 `document.writeln(随机命名空间.随机函数名('base64'))`
  形态的内联正文，并**拆掉 script 壳**（否则 HTML 解析器不认内部标签）。
- **目录归一化**：全收集 → 按 cid 去重 → 按 cid 升序编号。统一消解
  「最新章节倒序回显」「CSS 隐藏列表项」「多页目录拼接」三类反爬，规则无需写特例。
- **迭代式目录页发现**（`pages.mode=auto`）：书籍页无 `<select>` 时，
  靠「查看更多章节」链接逐级展开（如 bqgbe 书籍页 → ml1 → ml2）。
- **章节内部分页拼装**：`continue_when=same_base_id` 判定续页
  （屏蔽部分站点把续页链接误标为「下一章」的干扰）。
- **免费章节六层拦截** `freeguard.py`：站点黑名单 / 规则自证 / 目录 VIP 标记 /
  正文付费墙+最小字数 / 导出终检 / 代码级机械自检（`selfcheck`）。
- **断点续爬** `state.py`：章节缓存**按 cid 索引**（防目录增删导致串页）+
  状态合并（防 discover 覆盖进度）+ 扫缓存补齐（防 Ctrl-C 落在两次落盘之间）。
- **校对** `proofread.py`：缺失 / 乱序 / 标题重复 / 正文重复 / 广告残留 /
  异常短章 / 编码异常 / 受保护章节，输出 `PASS` 或 `WARN` 结论。
- **四格式导出**：TXT、Markdown（YAML front matter + 卷章层级）、
  **EPUB3（纯标准库 `zipfile` 手写，无 pandoc 依赖）**、
  **单文件 HTML 阅读器**（目录搜索 / 键盘导航 / 进度记忆 / 字号行距 / 三主题）。
- **站点结构探针** `tools/probe_site.py`：未知站点一眼看清
  select、章节链接形状、onclick 形态、正文容器候选、base64 命中、付费墙命中。
- **71 个离线单元测试**：含真实页面 fixtures 回归，全套约 3 秒跑完。
- **端到端集成测试**：起本地 HTTP 服务模拟一个带 VIP 标记的合成站点，
  用真实引擎跑完整链路，断言「locked 章节零请求」「付费墙正文被丢弃」
  「导出拒绝」「成品无付费字样」。
- **阅读器真实浏览器验证** `tools/verify_reader.py`：Playwright + Chromium
  实际操作 UI 并断言 30 项（目录/翻页/键盘/搜索/进度记忆/主题/移动端抽屉/无 JS 错误）。
- **复用层**：从本家 `G:\repos\webcopier` 按「复制优于共享」抽取
  HTTP / 身份池（1373 条）/ 限速器，并**彻底移除 Cookie 与登录路径**。

### Changed（相对复用源的改进）

- **连接池**：webcopier 每次请求重建 TCP+TLS。实测 biqu520 冷启动 3.62s /
  热连接 0.13-0.30s（约 **12×** 差距），改为每线程 Session 复用连接；
  每次请求后清空 cookie jar，不承载任何凭据。
- **限速器**新增 `slowdown` / `recover`，命中反爬状态码时全局降速。

### Fixed（开发期实测踩到并修掉的问题）

- 正文容器首位的水印 `<div id="center_tip">` 会让 `</div>` 提前闭合，
  导致只抓到水印（21 字）——改为剔水印后再取文本。
- 正文提取时误删 `div.read_btn`，导致随后找不到「下一章」链接、分页章节只抓到第 1 页——改为在深拷贝上剔除。
- `javascript:addbookcase('…ml2.html','445')` 这类书签伪链接被当成目录页去抓——过滤伪协议。
- URL 模板把「页面 URL」当成了「书籍 ID」，拼出 404 地址——修正参数传递。
- 分页章节的页标题带「（第N页）」后缀污染章节名——改为以目录标题为准。
- `filter_exportable` 只判「未受保护」，把未抓取的 pending 章节也导出——
  限流抓 30 章时 EPUB 里塞进 169 个章节文件（139 个空章）——改为判 `has_content`。
- `discover()` 用全 pending 的新状态覆盖旧进度，导致续爬失效、进度归零重抓第 1 章——改为先合并后写盘。
- VIP 标记词是小写 `vip` 而站点写 `VIP`，大小写敏感导致目录层漏检——改为不区分大小写。
- **目录层按标题文本匹配 VIP 过于激进**：集成测试发现一个正常章节「第3章 付费墙占位」
  被误锁成 `locked`。改为「class 用宽表、标题文本只认徽章形态（`（VIP）` / `VIP章节` / `会员专享` …）」，
  宽表不再用于标题匹配——避免把合法免费章节整批误锁。
- `proofread.py` 漏导入 `STATUS_PENDING`，`fetch` 在出报告时直接崩——补导入并新增校对测试。
- 单测未覆盖 `proofread`，致上述崩溃逃逸到端到端才暴露——补 10 个校对用例。
- 阅读器在「由宽变窄」时侧栏未自动收起，会盖住顶部 ☰ 按钮（Playwright 报
  `pointer events intercepted`）——改为视口变窄时自动收起抽屉，并加遮罩 + 选章节自动收起。
- 校对把「未抓取」记成「缺失」，使 `--limit` 运行必然 WARN——拆分为 `not_fetched` 与 `missing`。
- 自检的裸词匹配会误伤自身注释与测试样本——改用「代码形态」正则并跳过 `tests/`。
- 单测每个用例都建/删临时目录，本机文件系统慢（1.5-3.1s/次）致全套 90s——改为共享临时目录，降至 2.3s。

### Security

- 明确排除参考资料中所有 VIP 相关路径：登录 Token、`cookies.txt`、
  `--vip` 开关、起点调试保护绕过、正版/盗版互补补 VIP 流程。
  借鉴记账见 [docs/REFERENCE.md](docs/REFERENCE.md)，约束细则见 [docs/FREE_ONLY.md](docs/FREE_ONLY.md)。
- 受保护章节的正文**不落缓存**（防止绕过导出层泄漏）。
- **第三方源码不入仓**：调研参照的 FictionDown（GPL-3.0）、404-novel-downloader
  （AGPL-3.0-or-later）、backupqidian（未声明许可证）**只记来源与许可，不收录源码**，
  避免与本仓 MIT 产生许可含混。该约束由 `tools/check_repo.py` 机械校验
  （许可文件唯一性 / 无第三方目录 / 无归档 / 无大文件 / 无凭据 / 借鉴记账完整），
  并用注入测试证明门禁有效。

### Known Issues

- 无 JS 引擎：目录或正文由 JS 动态渲染的站点暂不支持（规则可标 `requires_js: true` 声明）。
- 目录归一化依赖「章节 ID 与阅读顺序同向」；已核验三站满足，遇例外需为该规则加自定义排序。
