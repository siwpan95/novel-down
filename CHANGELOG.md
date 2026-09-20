# Changelog

本项目所有值得注意的变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.7.1] - 2026-09-20

按「接着做轻之文库 / 哔哩轻小说」推进 + 评阅全哥新给的 5 篇参考与 1 个程序。

### Added

- **站点：哔哩轻小说**（`linovelib.com`，轻小说译作聚合站）——**纯 HTTP，零新代码**。
  - 书籍页 `/novel/{bid}.html`；**目录在独立页** `/novel/{bid}/catalog`
    （结构：`div.volume`（38 卷）→ `div.volume-info` + `ul.chapter-list > li > a`）；
    章节页 `/novel/{bid}/{cid}.html` 正文在 HTML 里、容器 `div#TextContent`。
  - **作者与书名揉在同一元素** `.book-author`（「作者 石踏一荣 、 みやま零 全文字数 398.2万 …」）
    → 用 `author_pattern` 抽；⚠ 别用 `.author`（实测命中侧栏推荐位的另一个作者名）。
  - **必须用 `document_order`**：目录按「卷 → 卷内章节」展示顺序排列，而 cid 不逐卷递增
    （实测第一卷内出现 10 / 100 / 101 / 102 这类跳号），按 cid 数值排序会打乱章序。
  - 实测《恶魔高校DxD》：**426 章全免费**（目录里没有任何 VIP 标记），3 章 6484 字，校对 + 产物终检 PASS。
  - ⚠ 法律风险已写入规则 `notes` 与 `docs/FREE_ONLY.md`（见下）。

### Known issues

- **轻之文库 `linovel.net` 已正式关闭**：因未经授权刊载大量日本轻小说译作构成版权侵权，域名已不可用。
  实测首页/书籍页持续 `Read timed out`（45s/60s），`/book/{id}` 404。
  → 不接入，改为一条**停用存根**记录此事（避免日后重复探测死站）。
- ⚠ **同类风险提醒**：本次接入的 `linovelib.com`（哔哩轻小说）与轻之文库属**同一形态**
  （聚合未授权日轻译作）。规则仅供**个人离线阅读**，请勿再分发或商用。

### Docs

- 新增参考资料评阅（5 篇教程/文章 + 1 个程序），结论记入 `docs/REFERENCE.md` 与
  `docs/NEW_SITES_PLAN.md` §10：**无一项需要改代码**，其中 pingcode 那篇方法论文章
  **独立印证**了本项目已有的全部关键设计；另记 5 个新的免费站候选与 1 条红线冲突
  （某程序用「手动取 `cf_clearance` cookie」过 Cloudflare = 凭据流程，本项目不做）。

### Tests

- 168 → **170**。新增：站点已关闭的存根必须写明「已关闭 + 原因」、哔哩轻小说规则形态
  （目录独立页 / `document_order` / `#TextContent` / 必须有 `author_pattern`）。

## [0.7.0] - 2026-09-20

按「先做寒武纪年 → 加通用能力做次元姬 → 深查米国度/飞卢」推进。结果：
**寒武纪年判为登录/付费墙（不做）**，**次元姬与飞卢接入成功**，并修掉一个**会静默丢数据的解析 bug**。

### Added

- **站点：飞卢小说网**（`faloo.com`，正版·含 VIP）——**纯 HTTP**，零新代码。
  - 书籍页 `/{bid}.html` 一次给出**全部章节**（实测 12188 章，页面约 2 MB）；
    章节 URL 是 `/{bid}_{cid}.html`（协议相对写法）。
  - 免费/VIP **不在逐章标记上，而在分段上**：`#mulu` 里 `div.DivVip`（文本含「VIP章节部分」）
    之前是免费表（49 章，单元格 `DivTd3`）、之后是 VIP 表（12139 章，单元格 `DivTd`）。
    逐章没有任何 VIP class/图标（实测目录内 vip 图标数 = 0）
    → 用 `volume_selector: "div.DivVip"` + `catalog.vip_volume_markers: ["VIP"]` 判定。
  - 实测：3 章 6087 字，**12139 章标记 locked 零请求**，校对 + 产物终检 PASS。
- **站点：次元姬**（`ciyuanji.com`，正版·Next.js）——需要下面两个新能力。
  - **该站没有书籍页**（`/book/{id}` 等 9 种形态全 404、DOM 里 0 个书籍页链接），
    入口只能是章节页 `/chapter/{bid}_{cid}.html`；`info_url` 与 `catalog.json.url` 用 `{url}`。
  - ⚠ **正文是服务端加密的**：纯 HTTP 拿到的 `chapterContent.content` 是 base64 密文
    （中文 0 字），页面用前端 JS 解密 → 本规则 `fetch_mode: browser`。
    **口径**：这不属于「破解加密」——没有逆向密钥或算法，只是用真浏览器渲染页面、
    读站点对**所有访客**展示的内容（无登录、无验证码）。
  - 实测：3 章 10370 字，**647 章标记 locked 零请求**，校对 + 产物终检 PASS。
- **通用能力 `catalog.json.json_source`**：JSON 嵌在 HTML 里时（Next.js 的
  `<script id="__NEXT_DATA__">`、Nuxt 的 `__NUXT__`），先用 CSS 选择器取出那段 JSON，
  再照常按 `items_path` 取值 → 一条 `catalog` 规则吃下整类 SSR 站。
- **通用能力 `book.*` 的 `@json:<path>`**：从 SSR 数据块按 `a.b.c` 取书名/作者
  （次元姬的作者只在 `props.pageProps.bookChapter.authorName`，页面上没有稳定选择器）。
- **通用能力 `chapter.drop_leading_title_paragraph`**：正文首段就是标题行、
  且该 `<p>` 无 class 可剔时（实测飞卢 `div.noveContent > p:first`），
  启用后**仅当首段与目录标题完全相同**时删除 —— 宁可不删，也不会吃掉真正的首段。

### Fixed

- **lxml 静默丢内容（严重）**：`make_soup` 原来无条件优先 lxml，而 lxml 对畸形 HTML
  会**悄悄截断**。实测飞卢书籍页（2 MB）：原文 `<a>` **12356** 个、章节 **12188** 章，
  lxml 只解析出 **3128** 个 `<a>`、**3058** 章，**且不报任何错**——
  目录静默缩水 75%，后续抓取全歪。
  → 新增 `_parse_looks_complete()` 完整性校验：比对原文与树里 `<a>/<div>/<p>` 的数量，
  数量级明显不符（< 60%）就退回 `html.parser` 重解析（慢一点但不丢）。

### Known issues / 本轮裁决

- **寒武纪年 `hanwujinian.com` → ⛔ 停用（登录/付费墙）**：首页 200、书籍页 200、
  完整目录 `/catalog/{bid}` 200（87 章链接）都正常，但**章节正文对未登录访客不下发**——
  章节页虽显示「字数:2623字」，页面 HTML 与真浏览器渲染后的 DOM 里都**没有正文**
  （全页汉字仅 630~697，全是导航/元信息/书评），且 `reader.js` 里**没有任何正文接口**
  （只有 comment/report）。页面含「全本购买弹窗」「付费订阅」「包月特权」模板。
  ⚠ **自我更正**：上一轮我据「首页/章节页 200 + 最大中文元素 697 字」判它「可直接做」——
  **那是错的**，697 字是元信息不是正文。教训：判断「正文是否在 HTML 里」必须拿
  **章节声明的字数**（本例 2623 字）与实际可取文本量做数量级对比，并检查有无正文接口调用。
- **米国度 `myrics.com` → 低优先**：首页 200 / 117 KB，但只解析出 2 个 `/novels/` 链接
  且指向「用户手册」；站点为繁体、含 `/payments/`（付费），疑 SPA → 暂不投入（未判死）。

### Tests

- 157 → **168**。新增：SSR JSON 取目录（`json_source`，含缺数据块的报错提示）、
  `@json:<path>` 取作者（含路径缺失时回退到选择器）、lxml 完整性守卫（检出截断 / 放过忠实解析 /
  小页面不误伤）、首段即标题的删/不删/默认关闭三种情况。

## [0.6.1] - 2026-09-20

第二轮外探（P1-gate / P1 / P2）。**本轮不新增启用站点**，产出的是三份实测裁决 + 两条存根。

### Added

- **停用存根 2 条（登录墙红线）**：`xrzww.com`（息壤中文网）、`youdubook.com`（有毒小说网）。
  实测：目录接口 `/api/directoryList?nid=` **完全开放**且逐章带付费标记
  （`chapter_isvip` 恒 0，真信号是 **`chapter_ispay`**：305 章 = 46 免费 / 259 付费），
  但正文接口 `/api/readNovelByWeb` **恒返回 `{"code":401,"message":"用户验证失败"}`** ——
  纯 HTTP 与**真 Chrome + headed + 反检测（带 cookie、`fetch(credentials:'include')`）结果一致**。
  → **目录开放 ≠ 正文可取**；属登录墙，不做。有毒小说网与息壤同款 SPA 外壳，同判。

### Fixed

- **更正上一轮的错误结论：P2 的四个站点并非「不可达」。**
  上一轮用 `curl` 得到 `000` 就判死，实为 **curl/OpenSSL 侧的 TLS 协商问题**。
  改用本项目 `http_client`（requests）复测：`linovel.net` **200 / 204 KB**、
  `linovelib.com` **200 / 64 KB**、`hanwujinian.com` **200 / 360 KB** 全部可达；
  只有 `shencou.com` 仍 `SSLError`。
  → 记入方法论：**`curl 000` 不能判死站点**，必须换 HTTP 客户端复测，并区分 DNS / TLS / 超时。
- README / FREE_ONLY 的规则计数与支持矩阵同步（13 条 = 10 启用 + 3 停用存根）。

### Known issues / 待决策

- **次元姬 `ciyuanji.com`（Next.js）**：目录在 DOM（673 个章节链接）且 `__NEXT_DATA__` 里
  同时有 `bookChapter.chapterList`（逐章 `isFee`：26 免费 / 647 付费）与
  `chapterContent.content` —— 但**正文是服务端加密的**（纯 HTTP 拿到的是 base64 密文、中文 0 字），
  页面用前端 JS 解密，**真浏览器渲染后可正常阅读**（实测 2835 字可见文本）。
  ⚠ 需先定「加密正文」的处置口径（见 `docs/NEW_SITES_PLAN.md` §5 红线第 4 条）。
  若做，需要通用能力 `catalog.json_in_html`（从 `<script id="__NEXT_DATA__">` 取 JSON 当目录源），
  Next.js/Nuxt 站普遍适用。
- **寒武纪年 `hanwujinian.com`**：可直接做 —— 服务端渲染 + 现成 `/read/{bid}/{cid}` 形态，
  章节正文由 JS 加载（需浏览器路由），**零新代码**；页内 `slider_captcha.js` 属登录弹窗，非阅读拦截。
- **米国度 `myrics.com` / 飞卢 `b.faloo.com`**：形态待深查（正文疑 JS 渲染 / URL 规则不同）。

### Tests

- 156 → **157**。新增：登录墙类存根的 `disabled_reason` 必须写明「用户验证失败」与接口名（可复核）。

## [0.6.0] - 2026-09-20

按 P0 计划接入两站（**塔读**、**书海**），并按红线把 **刺猬猫** 记成停用存根。
新增四项通用能力，都不是「为一站写死」。

### Added

- **站点：塔读小说网**（`tadu.com`，正版，免费阅读 + 打赏模式）。
  目录 `/book/catalogue/{bid}`（2416 章）；**正文不在章节页 HTML 里**——
  `#artContent` 是空壳，正文由 `read300-*.js` 调 `/getPartContentByCodeTable/{bid}/{seq}`
  取回（`{seq}` 是**章节序号**，不是 cid）。实测《仙妻如云》3 章 5501 字，校对 + 产物终检 PASS。
- **站点：书海小说网**（`shuhai.com`，正版，杰奇 CMS）。书籍详情页是 `/book/{bid}.htm`
  （**带 .htm**；不带的是另一张榜单页）；目录由 `?method=getcatalog` 下发，
  **不带 `CALLBACK` 时直接返回裸 HTML**（无需 JSONP 解包，也无需浏览器路由），
  645 章 = **40 免费 + 605 VIP**。
- **`chapter.body_api`**：正文来自 JSON 接口的通用支持
  （`url` 支持 `{origin}/{bid}/{cid}/{seq}`，`content_field` 取字段，
  `drop` 规则按 `equals_base64_of` 剔除站点水印段）。
- **`catalog.vip_volume_markers`**：目录按**分段**标注免费/VIP 的站点
  （塔读 `<h2><span>免费章节<i>/N章</i></span></h2>`），配 `volume_selector` 即可整段锁定。
- **`catalog.vip_child_selector`**：VIP 标记在目录项**子元素**上时（书海
  `<div class="chapter-item"><a …>…</a><span class="vip"></span></div>`）的显式判定。
- **目录项可以是容器**：`item_selector` 选中容器时，href/onclick 从内嵌 `<a>` 取、
  **标题取容器文本**——实测书海 645 章里 **215 章（33%）的 `<a>` 文本为空**，
  只选 `<a>` 会丢掉三分之一标题。
- **`book.author_pattern`**：作者与书名挤在同一行时按正则取作者（书海 `神农医婿 作者: 方长`）。

### Fixed

- **`tools/probe_site.py` 崩溃**：容器打分元组里 `id`/`class` 可能为 `None`，
  并列排序时比较 `str` 与 `None` → `TypeError`。实测书海书籍页直接崩在「正文容器候选」。
- **`body_api` 片段被 lxml 丢弃**：解析器优先用 lxml，而 **lxml 会丢弃 `</html>` 之后的内容**——
  片段追加在文档末尾会整块消失（症状：容器选不到、或选了却为空）。改为插到 `</body>` 之前。
- **`drop` 规则遇到已 `decompose()` 的元素**会 `AttributeError`（`attrs` 变 None）→ 加跳过守卫。
- `vip_child_selector` 的检查范围**不能用「项自身的父级」**（那是整个目录容器，
  会匹配到别的条目的 `span.vip`）→ 改为「链接元素的父级」。实测踩过：645 章全被判 protected。

### Known issues

- **塔读正文接口会对高频重复直连降级**：站点用 `base64(章节id)` 标记「本次应隐藏」的段落，
  正常的首次响应只有少量水印段（实测 7/77），但**同一章被反复直连**时被标记的段落越来越多
  → 抽取结果变短。真人浏览器访问稳定（实测始终 7 隐藏 / 70 可见 / 1532 字）。
  → 应对：**每章只取一次**（断点续爬缓存天然满足），**不要用 `--force` 反复重抓同一章**；
  引擎在隐藏段占比 > 40% 时会打 warn 提示。

### Tests

- 147 → **156** 个用例。新增：容器目录项（含空 `<a>` 文本）、`vip_child_selector` 只影响本条目、
  `vip_volume_markers` 分段锁定、`body_api` 抽取 + 按 base64(cid) 剔除水印（含坏 JSON/缺字段）、
  `author_pattern`、停用存根的理由可复核与 `find_rule()` 报出原因。
- 实测新增两站 E2E：塔读 3 章 5501 字、书海 5 章 11585 字，二者**校对 PASS + 产物终检 PASS**
  （书海 605 个 VIP 章**零请求**零泄漏）。

## [0.5.1] - 2026-09-20

修一处**浏览器等待条件的隐性缺陷**（由一次外部项目评估的实测副产物发现）。

### Fixed

- **`wait_for_selector` 是 OR 语义，会被宽松分支提前放行**（起点规则实测踩到）：
  `chapter.browser_wait_selector` 原为 `"main.content span.content-text, #reader-content p"`，
  而 `#reader-content p` 在**骨架期就存在** → 等待立即返回，但此时正文段
  `span.content-text` 数量是 **0**。**这个等待其实没起到「等正文就绪」的作用，全靠
  `wait_ms: 3500` 兜住。** 对照实验（同页、`wait_ms=0`）：

  | 等待条件 | `span.content-text` 数 | 首段 |
  |---|---|---|
  | 收紧后 `main.content span.content-text` | **69** | `痛！` |
  | 旧 OR `…, #reader-content p` | **0** | `None` |

  → 收紧为只留 `main.content span.content-text`。
- **`paragraph_selector` 未命中时会「静默变空」**：新增**回退**——段落选择器一个都没命中时，
  退回「容器整体切分」（`extract_paragraphs`），并把 `extract_note`（如
  「段落选择器「span.content-text」未命中，已回退为容器整体切分」）并入章节备注。
  回退结果同样干净：`strip_selectors` 已先剔掉段评数等附加节点。
  设计取向：**宁可留痕地降级，也不要静默丢章**。

### Tests

- 143 → **147** 个用例。新增：段落选择器未命中→回退（含 `extract_note` 留痕）、
  回退结果经 strip 后仍无段评数污染、主路径命中时不留回退痕迹、
  容器选不到时不因 `extract_note` 未初始化而 `NameError`。

### Verified

- 起点 E2E：`fetch --limit 3` → ok=17 / locked=1265 / 待抓 136，56 932 字，校对 **PASS**，
  产物终检 **PASS**（零请求 / 零泄漏 / 无 PUA 残留），**全程无「等待超时」「回退」告警**
  （证明等待条件真的生效、且走的是主抽取路径）。

## [0.5.0] - 2026-09-20

按全哥指定的两个方向推进：**起点（Qidian）浏览器指纹伪装 → 反检测打通** +
**彻底去掉 fontdecode 的参考字体依赖**。

### Added

- **起点中文网 `qidian.com` 规则启用**（此前是「停用存根」）——反检测浏览器路由过腾讯云 Chaos VM。
  - `browser.anti_detect`：本机**真 Chrome**（`channel="chrome"`）+ **headed** +
    `--disable-blink-features=AutomationControlled`。实测指纹 `navigator.webdriver=false`、
    `plugins=5`、UA 不含 `HeadlessChrome`；数秒渲染出 **67~70 万字节**书页，`#bookName`/`.chapter-name` 命中。
  - **语言自洽脚本 `CONSISTENCY_JS`**：修正 `locale="zh-CN"` 而 `navigator.languages` 仍是
    `en-US,en` 的矛盾（真人中文 Chrome 不会这样，反爬常查这个自洽性）。
  - 目录走 **JSON 接口** `/ajax/book/category`（页面内 `fetch`，带匿名 `_csrfToken`），
    `flatten_field="cs"` 展开 `data.vs[].cs[]`。逐章 `sS` 字段：**1=免费、0=VIP**
    （`vip_truthy=["0"]`，与直觉相反，已实测确认）。实测 1418 章 = 153 免费 + 1265 VIP，VIP 零请求。
  - 正文 `main.content` + `paragraph_selector="span.content-text"`，避开同 `<p>` 里的段评数节点。
  - `{cookie:NAME}` URL 占位符：从当前页**同源** `document.cookie` 取 CSRF token 填入查询参数。
- **`catalog.json.flatten_field`**：卷→章嵌套目录展平（起点 `data.vs[].cs[]`）。
- **`chapter.paragraph_selector`**：按**段落元素**逐个取文本，而非整块容器文本。
- **`BrowserFetcher.launch_kwargs()`**：启动参数构造抽成**纯函数**，反检测三件套（channel/headless/args）可单测。
- **随仓字体轮廓索引** `noveldown/fontmaps/sourcehan-sc-2.002.bin`（gzip JSON，44 260 条，459 KB）。
- `tools/build_fontmap.py --shipped`：维护者一键重建随仓索引。

### Changed

- **`fontdecode` 运行时彻底去掉参考字体依赖**：`FontDecoder` 不再有任何下载分支
  （移除 `build_if_missing` / `downloader` / `_build_index`；`REF_FONT_URL` / `REF_FONT_SHA256`
  下沉到构建工具）。运行时只读**随仓索引**——**不联网、不下载 17 MB 参考字体**。
  实测：番茄第 1 章 **362/362 码位还原、全程零下载**。
- `font_decode` 规则键由 `{mode, auto_build}` 简化为 `{enable}` 开关
  （解码途径由字体自身决定：glyph 名可用则用，否则走随仓轮廓索引）。
- `tools/build_fontmap.py`：参考字体下载逻辑收进本工具（仅维护者重建时需要）；
  `--verify` 默认校验**随仓**索引。

### Fixed

- **仓库卫生**：不再随仓分发第三方 `stealth.min.js` —— A/B 对照（带 / 不带）证明它对起点**非必需**，
  而本仓铁律是「第三方源码不入仓」。改为**可选外挂**：`NOVELDOWN_STEALTH_JS` 或规则里
  `browser.stealth_js` 指定自备脚本；`.gitignore` 兜住同名文件。
- `freeguard.selfcheck` 误报 `{cookie:NAME}` 同源占位符为「凭据代码路径」——改用负向后顾
  精确排除占位符，真实 `cookie=` 写入仍会被抓。
- 浏览器拆除期 playwright 内部任务被取消产生的 asyncio 噪音
  （进入浏览器路由时抬高 `asyncio` logger 级别；实测警告出现在 `close()` 之后，与结果无关）。
- `browser.anti_detect_available()` 中双斜杠路径写法规范化，并去掉未使用的 `glob` 导入。

### Tests

- 130 → **143** 个用例（约 3 秒，离线）。新增：反检测启动参数 / 语言自洽 / 无第三方 stealth 随仓、
  `paragraph_selector` 段落抽取、`flatten_field` 卷→章展开（含非分组条目容错）、
  起点规则启用回归、随仓索引可读性与「运行时无参考字体依赖」守门。

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
