# Changelog

本项目所有值得注意的变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.4.0] - 2026-09-20

按全哥指定的两个方向推进：**17K 站点** + **fontdecode 优先按 glyph 名解码**。

### Added

- **正版站点规则：17K小说网**（`17k.com`）。实测一本 586 章全免费书；
  20 章 46 058 字，校对 PASS。站点用阿里云 WAF → 浏览器路由。
- **`fontdecode` 途径一：按 glyph 名解码**（**优先**，秒级，**不需要 17MB 参考字体**）。
  覆盖三类写法：英文单词（`zero`/`period`，起点老版反爬的形态）、
  码位十六进制（`uni98CE`/`u5929`/`CJK UNIFIED IDEOGRAPH-98CE`）、单字符名；
  并**明确拒绝** `gid58646`/`cid44285` 这类索引名（那是索引不是字符，别瞎猜）。
  覆盖率 ≥60% 即走这条路，否则自动退回轮廓匹配。
  → 这条路子源自 `_ref/2.txt`（知乎 58209887）记录的起点老版解法，已记入借鉴记账。
- **站点级 VIP 特征 `chapter.vip_markers`** + `freeguard.check_page_markers()`：
  有些站点的付费信号**不在正文里**，而在整页层面（17K 用
  `chapter_free.css` vs `chapter_vip.css` 区分免费/付费章）。
- **`catalog.browser_wait_selector`**：目录页专用浏览器等待条件
  （此前只有顶层与章节页两处）。
- **`chapter.content_selectors`**：正文容器候选列表（同一站不同请求可能给
  `id="readAreaBox"` 或 `class="readAreaBox content"`）。

### Fixed

- 实测：**浏览器路由不配 `wait_selector` 会时快时慢地取到空 DOM** ——
  17K 目录页只等 1.5s 就拿到 **0 章**，页面其实要 3-5s 才渲染出 586 章。
  三者（书籍/目录/章节）都要配各自的等待条件。
- 17K 正文容器内的 `h1`（章节标题）与 `.chapter_update_time`（书名+作者+字数）
  会混进正文首段，需一并剔除。

### 实测订正

- 起点老版字体反爬（`_ref/1.txt`/`2.txt`、QidianScrapy）确实是「数字 → 英文单词
  glyph 名」的简单映射；**但现在已换成腾讯云 Chaos VM**，
  有说法"起点反爬很业余"已过时。
- 两份新参考（QidianScrapy / QidianCrawler）**都没有 LICENSE 文件** →
  按著作权法默认「保留全部权利」，比 GPL/AGPL 更严 →
  本项目只取**事实性信息**（选择器、映射规律）并记账，**未复制任何代码**。
  QidianCrawler 的 README 亦明示「下载 VIP 章节需在弹出的浏览器中登录后重新执行」，
  该凭据流程完全不采用。

### 验证

- 130 用例全绿（约 2s）；新增 `char_from_glyph_name` 的 8 组用例
  （含"必须拒绝索引名"的反向用例）。
- 17K E2E：586 章目录 → 抓 20 章 46 058 字；校对 PASS。
- 番茄回归：`gid` 索引名 → 自动退回轮廓匹配 → **362/362 码位、100% 覆盖**，
  正文仍为「寒风呼啸，漫天飞雪。」（证明两途径切换无回归）。
- 免费约束自检 PASS；仓库卫生门禁 PASS。

---

## [0.3.0] - 2026-09-20

按投入产出继续补站点能力，补上「**JSON 接口目录**」这一整类来源。

### Added

- **正版站点规则：七猫免费小说**（`qimao.com`，字节/百度系「免费阅读 + 广告」平台）。
  708 章 = 20 章 web 可读 + 688 章 **APP 独占**（不是付费墙）。
- **`catalog.mode = "json_api"`** —— 目录来自 JSON 接口而非 HTML：
  `items_path` / `cid_field` / `title_field` / **`vip_field`** / `vip_truthy` / `url_template`。
  这类接口常带**逐章 VIP 字段**（七猫 `is_vip`、起点 `vip`），比 HTML class 标记更可靠，
  第 3 层据此判定、连请求都不发。参考项目（backupqidian 的 `ajax/book/category`、
  `_ref` 里的 Scrapy 爬虫）走的都是这条路。
- **APP 墙识别**（第 4 层新增一类特征词）：不少中文小说站是「APP 优先」，
  web 端只放前若干章。实测七猫第21章的"正文"是 2 段 78 字的
  「下载【七猫免费小说APP】，继续在APP内免费畅读全本内容」——
  **78 > 最小字数阈值 50**，不显式拦截就会被当成正常正文保存。
  已补 `APP内免费畅读` / `请在APP` / `下载【` / `扫码下载` 等标记。
- **`book.title` 支持 `@title` 伪选择器 + `book.title_pattern` 正则清洗**：
  SPA 站点（七猫）书名只在文档 `<title>` 里且带站点后缀，
  用 `^(.*?)(?:免费阅读|...)` 即可拿到干净书名。
- **`chapter.browser_wait_selector`**：章节页专用等待条件（与书籍页解耦）。

### Fixed

- **浏览器路由不能复用同一个 page**：实测七猫（Nuxt SPA）连续 `goto` 时，
  上一次的客户端路由会中断新的文档级导航 → `net::ERR_ABORTED`，**20 章全 failed**。
  改为每次导航用独立页面（同 context，WAF cookie 保留）。
- **浏览器路由不能走线程池**：Playwright 同步对象绑定创建它的线程，
  `ThreadPoolExecutor` 会新建线程 → `Cannot switch to a different thread`。
  browser 模式改为主线程顺序抓。
- **browser 路由取 JSON 不能用 `page.goto`**：Chrome 会把 JSON 包成 `<pre>` 的 HTML
  文档，破坏解析。改用页面内 `fetch()` 取原始响应体（同源请求自动带上 WAF cookie）。
- **校对误报乱序**：`catalog.sort=document_order` 的站点（雪花 ID：番茄/七猫）
  章节号本来就不单调，检查它只会误报。`Book.catalog_sort` 现在会传给校对层并跳过该检查。
- **规则校验放宽**：`item_selector` 仅在非 json_api 模式下必需。

### 实测订正

- 起点：WAF 是**腾讯云 Chaos VM**（95KB 虚拟机式 JS 挑战），不是 2019 年那篇博客
  说的"很业余"。无头 Chromium 等 42s 不放行、`navigator.webdriver=true` 被识别。
  **`_ref` 里的 QidianCrawler（DrissionPage）选择器 `#bookName`/`.chapter-name`/
  `.content-text` 已记录备用**；其 README 亦写明只有 VIP 章才需要用户手动登录。
- 七猫接口必须带 `Accept: application/json`：只带 `Referer` 仍被回 23670 字节的 SPA 外壳。

### 验证

- 121 用例全绿（约 2s）；新增 JSON 接口目录、书名清洗、APP 墙拦截的测试。
- 七猫 E2E：708 章 → 抓 20 / locked 688；43 065 字；校对 PASS；
  `verify_artifacts` 证明 **locked 章零请求、零泄漏、无 APP 墙残留**。
- 免费约束自检 PASS；仓库卫生门禁 PASS。

---

## [0.2.0] - 2026-09-20

承接 0.1.0 的拦截粒度修正，继续把「过度防御」的残留清掉，并补齐两个能力缺口。

### Changed — 两处拦截粒度修正（重要）

- **第 5 层导出终检：查「泄漏」而非「存在」**。原实现是「存在受保护章节就拒绝导出」，
  导致任何含 VIP 的正版站**永远导不出来**（纵横那本 705 章里 650 章 VIP）。
  现在只检查「受保护章节**携带正文**」——那才是拦截失效的信号。
  受保护章节存在但正文为空是**正常状态**。见 [docs/FREE_ONLY.md](docs/FREE_ONLY.md) 第 5 层。
- **不再用「含 VIP」当作站点不支持的隐含理由**。参见 0.1.0 的第 1 层修正；
  本轮把纵横从「技术障碍」复核为「**服务端渲染、纯 HTTP 可取**」，正式启用。

### Added

- **正版站点规则：纵横中文网**（`zongheng.com`）——705 章里 50 章免费 / 650 章 VIP。
  VIP 章在目录层带 `class="vip col-4"` → 标记 locked、**零请求**（已机械验证）。
  实测要点：站点跨三个子域且只有 `huayu.zongheng.com/showchapter/{bid}.html` 有完整目录；
  VIP 标记在 `<li>` 而非 `<a>`（第 3 层查父元素 class 才能命中）；
  正文在 `div.reader-content div.content`（非直接子级）。
- **浏览器路由**（`noveldown/browser.py` + `fetch_mode: browser`）——补上此前的能力缺口：
  参考项目 FictionDown 用 Chromedp/PhantomJS 处理 JS 渲染页，本项目此前只有 HTTP 路由。
  可选依赖 playwright；browser 模式自动降为单线程（同步 API 不能跨线程共享）。
  **不做任何凭据相关的事**：不注入 Cookie、不登录；若站点要求人机验证，本路由同样失败。
- **`tools/verify_artifacts.py`**：产物终检 —— 机械验证
  「受保护章节零请求（无缓存痕迹）」「零泄漏（正文区无受保护章节标题）」
  「无付费墙字样」「无 PUA 乱码残留」「章节数自洽」。
  四本实测产物（纵横/番茄/bqgbe/shuquge）全部 PASS。
- 规则新增 `fetch_mode` / `browser`（`wait_selector` / `wait_ms` / `click_selectors` / `scroll`）。

### Fixed

- 实测发现：**「JS 站就得用浏览器」是错的**。纵横的 showchapter 页用无头浏览器打开
  只看到 2 个章节链接，而纯 HTTP 取到的静态 HTML 里有完整 700 章。
  已在 docs/RULES.md 写明「先用实测证据决定路由，不要默认」。
- `tools/verify_artifacts.py` 首版对 EPUB 有假阳性：EPUB 里 `intro.xhtml` 的物理顺序
  在章节之后，用「锚点之后」切正文区会把书籍简介算进来，而简介里合法地含有
  「最新章节：第699章 后会无期（大结局）」。已改为 EPUB 只扫章节文件。

### 验证

- 113 用例全绿（约 2s）；新增回归测试锚定「含 VIP 的正版站规则必须启用」
  「受保护章节正文为空时导出必须成功」。
- 纵横 E2E：700 章 → 50 章抓取 / 650 章 locked；产物 163 576 字；
  `verify_artifacts` 证明 **locked 章节零缓存痕迹、零泄漏、无付费墙字样**。
- 番茄 E2E：966 章目录；字体反爬 362/362 还原；产物 PUA 残留 0。
- 免费约束自检 PASS；仓库卫生门禁 PASS。

---

## [0.1.0] - 2026-09-20

首个可用版本。四个站点规则经端到端实测，四格式导出产物通过结构校验。

### Changed — 拦截层语义修正（重要）

- **站点层不再因「含 VIP 内容」而拒绝整站**。原设计把起点/纵横/17K/晋江/刺猬猫/飞卢
  列入黑名单，那是**粒度放错层级**：一本小说通常前几十章免费，站点含 VIP 不等于
  该章需要付费。后果是可用规则里只剩盗版站，而正版免费平台反被拒之门外。
  现在：站点层只保留「项目明确声明不支持」的政策旋钮（`POLICY_DENYLIST`，**默认空**），
  拦截职责下沉到章节级（目录 VIP 标记 → 不请求；正文付费墙 → 丢弃）。
  见 [docs/FREE_ONLY.md](docs/FREE_ONLY.md) 第 1 层。
- 停用规则改为**调研记录存根**（只需写 `disabled_reason`，不必写全选择器）；
  `find_rule()` 命中停用规则时**报出停用原因**，而不是含糊的「没有规则」。
- `VIP_ITEM_CLASS_MARKERS` 扩充 `pay` / `price` / `coin` / `charge` / `subscribe`
  —— 实测纵横用 `class="pay fr"` / `user_pay` 标注付费章，原表的裸 `paid` 匹配不到。

### Added

- **正版站点规则：番茄小说**（`fanqienovel.com`，字节旗下「免费阅读 + 广告」平台，
  全站无 VIP 章节）。这是本项目第一个正版来源，也是对上述设计错误的反证。
- **字体反爬解码**（`noveldown/fontdecode.py`）：还原被替换成私用区码位（PUA）的正文。
  番茄把 54% 的字符换成 PUA 码位再用自定义字体渲染，DOM 里是 `'寒\ue516呼啸'`。
  子集字体里没有可用线索（cmap 全是 PUA、glyph 名是来源字体序号、charstring 被重打包），
  故用**字形轮廓匹配**同版本参考字体还原：实测 **363/363 全部命中**，
  端到端 362/362 码位、覆盖率 100%。
- **`catalog.sort = document_order` + `catalog.dedupe = keep_last`**：番茄的章节 ID 是
  雪花 ID，且「最近更新：第N章」回显在列表**头部**；cid 升序会把回显的脏标题排到最后。
- **`tools/build_fontmap.py`**：一次性下载参考字体（SourceHanSansSC-Normal 2.002，
  OFL-1.1，约 16MB）并生成轮廓索引（44 260 条，压缩后 1.2MB，缓存在 `output/fontcache/`）。
  脚本校验 sha256；参考字体与索引**都不入仓**（理由见 docs/REFERENCE.md 第四节）。
- **停用规则存根 4 条**：起点（WAF）/ 纵横（目录靠 JS）/ 17K（靠 JS）/ 七猫（靠 JS），
  逐条记录技术障碍与实测证据。
- 规则引擎：`Rule.disabled_reason`、`site_overview()`；`sites` 命令输出启用/停用分组与原因。

### Added（首版核心）

- **规则驱动引擎**：`noveldown/rules/*.json` 一站点一文件，加站不改代码。
  首版内置 3 条实测规则：`shuquge.com`（1582 章）、`bqgbe.cc`（169 章）、`biqu520.net`（2653 章）；
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
- **109 个离线单元测试**：含真实页面 fixtures 回归，全套约 3 秒跑完。
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
- **字体反爬不报错、只缺字**：番茄第 1 章 1409 字里 764 个 PUA（54%），
  文本能取到、结构正常、字数也对，只是乱码（"寒呼啸，漫飞雪。"）。
  这类问题只能靠"产物必须 0 PUA 残留"的校验发现——已加进端到端检查。
- 轮廓匹配的**取号陷阱**：同一字形对应多个码位（「风」U+98CE 与康熙部首「⻛」U+2EDB），
  不做区块优先级时 `U+E516` 反查成 `⻛`。已加 `_cp_priority()` 并补测试。
- 参考字体**版本必须严格对上**：2.002R 命中 363/363，`@release`(2.005) 只有 7/363。
  脚本已加 sha256 校验，不符即报错并提示风险。
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

- 无 JS 引擎：目录或正文由 JS 动态渲染的站点暂不支持（规则可标 `requires_js: true`）。
  起点 / 纵横 / 17K / 七猫 因此停用，逐条原因写在各自规则文件的 `disabled_reason`。
- 目录归一化默认依赖「章节 ID 与阅读顺序同向」；ID 无序的站点需用
  `sort: document_order`（番茄小说即此例）。
- 字体反爬解码依赖**同版本**参考字体；上游改版会导致失配（脚本会校验 sha256 并报错）。
