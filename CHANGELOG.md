# Changelog

本项目所有值得注意的变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.8.11] - 2026-09-21

### ⚠ 重要更正：我上一轮的「出版三站全灭」结论是**错的**

全哥给出三个**免登录可读**的具体 URL，实测**全部成立**：

| 站点 | 全哥给的 URL | 实测 |
|---|---|---|
| 豆瓣阅读·**专栏** | `/reader/column/76273556/chapter/777669578/` | ✅ 200、**696 汉字正文**（"爆仓第三天，虞乔的求生意愿只剩下不到5%…"） |
| 磨铁系 **laikan** | `www.laikan.com/chapter/37140/639028` | ✅ 渲染后正文容器 **`div.read-box`**（506 汉字） |
| **微信读书** | `/web/reader/16d328b0…` | ✅ 渲染后正文容器 **`div.readerChapterContent`**（**2303 汉字**） |

**我错在哪**：三站我都**只试了各自的「付费/出版电子书」入口就判了整站死刑** ——
- 豆瓣：只试 `/reader/ebook/{id}/toc/`（出版电子书 → 跳登录），**没区分「专栏」**；
- 磨铁：只看了 `/detail/{n}` 详情页上的「5磨铁币/千字」，**没试 `/chapter/{bid}/{cid}` 章节页**；
- 微信读书：只看首页卡片非锚点 + 分类页「暂无书籍」，**没试 reader URL**。

**教训（已写进 skill）**：**判「整站不可做」之前，必须把站内的内容类别/入口形态逐个试过** ——
一个平台常同时存在「付费区」与「免费可读区」，用一个入口的失败去否定整站，是最容易犯的错。

### Added

- **`read.douban.com`：豆瓣阅读·专栏（原创连载·免登录可读）** —— 从存根**翻案成可用规则**
  · 作品页 `/column/{cid}/`（目录**需浏览器渲染**：纯 HTTP 只有 13 个链接、0 个章链接；
    真 Chrome 渲染后章列表在 `ul.chapter-list` 里）。
  · 章节页 `/column/{cid}/chapter/{chid}/`（会 302 到 `/reader/column/…`，两者都返回正文），
    正文容器 **`div#article-static-content`**。
  · ⚠ 两个实测细节：① **等待要给够**（`wait_ms: 4000`；给 2000 时列表没渲染完，只取到 4 章）；
    ② 章链接 `a.chapter-item` **内嵌正文预览**（`<div class="description">` 是整段正文）
    → 用**本轮新建的 `catalog.item_strip_selectors`** 剔掉 `div.description`/`div.meta`，
    标题才干净（否则标题会变成整段正文）。这一步正好用上了上一轮加的能力。
  · 实测《风吹草动》：3 章免费、正文 788 字、端到端导出 2366 字、校对 **PASS**。
  · ⚠ 只覆盖**专栏**；**出版电子书**（`/ebook/{id}/`）reader 仍需登录 → 不做（按 URL 形态区分）。
- **`catalog.item_strip_selectors` 的第二个真实用途**（第一个是掌阅的「免费」徽章）——
  说明这个能力不是为单一站点打的补丁。

### 待建规则（本轮已把正文容器定位好，证据完整）

| 站点 | 正文容器（已实测） | 还缺 |
|---|---|---|
| 磨铁系 `laikan.com` | `div.read-box`（506 字） | 目录页形态（`/detail/{bid}` 渲染后无章列表，需继续找） |
| 微信读书 `weread.qq.com` | `div.readerChapterContent`（2303 字） | 章列表（reader 页是按 hash 单章；需找 TOC 入口） |

### Notes

- 测试 192 全绿；门禁 8 项 PASS。
- **本轮未做**（下一批）：黑岩 `heiyan.com`、知乎名单 100 条初筛、已接入站做深、镜像池继续铺开。

## [0.8.10] - 2026-09-21

按全哥指示做两件事：**① 书旗新能力 ② 正版池全面复核**。
两件的结论都**与原计划不同**，如实记录。

### ① 书旗：结论更正 —— **不是「缺一个能力」，而是「要破解加密」（红线）**

上一轮我把卡点记成「缺一个能力：正文 URL 由目录项的 JSON 字段提供」。
**这次实测发现：即便补上那个能力也没用。**

- 目录侧确实可行：页面自己会发那个**带 JWT+签名**的 `chapterlist` 请求，
  用浏览器监听即可拿到完整 JSON（含 `payStatus` 与带 sign 的 `contUrlSuffix`）。
- ⚠ **但拿到带签名的正文 URL 仍然无解**：`freeContUrlPrefix + contUrlSuffix` 实测返回
  200 `application/json`，结构 `{state, message, ChapterContent}`，而
  **`ChapterContent` 是加密串** —— 长度 15000、字符集在 base64 范围内（无非法字符），
  但 **base64 解码后是二进制乱码**（11249 字节，UTF-8 只能解出 153 个碎片汉字）
  → **不是普通 base64 编码，是加密**。
- → 要读正文就得**逆向其加解密算法**，这正是项目红线「破解服务端加密正文」所列行为，**不做**
  （且这类算法随版本变，做了也维护不住）。
- → **不建那个新能力**（没有能落地的站，属投机性工程），存根已改写为**证据链完整**的版本。

### ② 正版池 11 条存根全面复核 —— **8 条确认一致 / 0 例翻案 / 2 条未能复现（如实标注）**

| 存根 | 复核结果 |
|---|---|
| `ciweimao.com` | ✅ **确认**：章节页仍 **302 → `/signup/man_machine_verify`**（验证码），命中红线 |
| `hanwujinian.com` | ✅ **确认**：抽 4 个章节页（`/read/121348/{cid}`）汉字数 687/435/687/701，**全是标题+导航+元信息**，且每页都出现「登录」「购买」→ 正文确实不向未登录访客下发 |
| `idejian.com` | ✅ **确认**：落地页（静态文本 4200 汉字全是营销文案，渲染后仍仅 18 个链接） |
| `kureader.com` | ✅ **确认**：226 汉字落地页（APP 引导） |
| `midureader.com` | ✅ **确认**：323 汉字落地页（APP 引导） |
| `motie.com` | ✅ **确认**：0 汉字 + **302 → `/wenxue`** 营销页 |
| `read.douban.com` | ✅ **确认**：书籍页可读（1058 汉字元信息）但 reader 需登录 |
| `weread.qq.com` | ✅ **确认**：128 汉字 + 「登录」入口 |
| `shuqi.com` | ✅ **证据升级**（见 ①） |
| `xrzww.com` / `youdubook.com` | ⚠ **本次未能二次复现**（如实标注）：首页真 Chrome 渲染后**仅 5 个链接、无书籍入口**；`pre-api.xrzww.com/api/directoryList` **仍开放**（`nid=1` → `code:200`）但 `/api/search` 已 **401「请登录后再访问」** → 拿不到有效书号，无法用免费章重跑内容接口。**维持停用**：原证据是「真 Chrome + headed + 反检测会话内内容接口仍恒 401」，该证据强于纯 HTTP，**比「本轮跑不了」更可信**；但已在存根里注明**这一条的依据来自上一轮实测** |

**0 例翻案** —— 说明之前的停用判断整体是稳的；**2 条没能复现的也照实写进存根**，没有假装复核过。

### Notes

- 测试 192 全绿；门禁 8 项 PASS；规则总数 145（正版 27 = 16 启用 + 11 存根 / 免费镜像 118）。
- 本轮**没有新增规则**：① 是结论更正（少走弯路），② 是复核（确认既有判断）——
  两次都把「原以为要做的」改成了「实测证明不该做」，这比硬凑功能更有价值。

## [0.8.9] - 2026-09-21

按全哥「规划优先级后依次执行」的指示推进：**P0 出版读物三站实探**（全部转存根，
验证了全哥「这三家主打出版读物」的判断）+ **P1 新工具 `tools/check_official.py`**（作家入口机械校验）。
到 P2（书旗新能力）时按优先级说明**本轮未做**，理由见下。

### P0：磨铁 / 豆瓣阅读 / 微信读书 —— 三站全部转存根，且**结论一致**

全哥提示「如果我没记错，这三个都是主打出版读物」——**实测完全印证，而且是这一类的共性**：

| 站点 | 决定性证据 |
|---|---|
| **磨铁 `motie.com`** | 书页跳到磨铁系阅读站 `m.laikan.com`，页面上明写 **「148万字 \| 5磨铁币/千字」** → **按千字计费，没有免费章节**。www 侧已退化成营销页（渲染后仅 34 个链接，多为公众号文章） |
| **豆瓣阅读 `read.douban.com`** | 书籍页 `read.douban.com/ebook/{id}/` 是**正式出版电子书**（实测《深渊》：提供方=中信出版社、约 226,000 字、**有 ISBN**）；⚠ **阅读页 `/reader/ebook/{id}/toc/` 直接重定向到 `accounts.arkread.com` 手机号登录** → **登录墙（红线）** |
| **微信读书 `weread.qq.com`** | 分类页渲染后是 **「暂无书籍」**；首页书籍卡片**非锚点**（`/web/book/` 链接 = 0）；顶部有「登录」入口 → **登录墙（红线）** |

> **可复用的类别结论**：**「主打出版读物」的平台 ≠ 可做的免费源** ——
> 它们的商业模式要么是**按字计费**、要么是**会员/登录**，免费可读篇幅极小或为零。
> 以后遇到同类站，先看这三件事：① 有没有明码计价（×币/千字）；② 阅读页要不要登录；
> ③ 书籍页是不是「出版电子书」（有 ISBN/出版社/提供方）。

### P1：新工具 `tools/check_official.py`（「作家入口」机械校验）

落实全哥提出的判据：**正版站才提供创作渠道，盗版只负责推小说**。
工具对指定池内的站点抓首页，统计是否出现
`创作 / 投稿 / 作家专区 / 成为作者 / 我要写书 / 签约 / 原创文学` 等入口。

**实测对照（这条判据确实有区分度）**：

| 池 | 命中创作入口 |
|---|---|
| **正版**（16 条启用） | **12 / 16 = 75%** |
| **免费镜像**（抽样 14 条） | **1 / 14 = 7%** |

**⚠ 刻意不做成硬门禁**（`--strict` 才非零退出）：未命中的 4 条正版站全都**不是"不正经"**，
而是**创作入口在别的子域** ——
晋江作者专区在 `my.jjwxc.net`、起点在作家助手、七猫在 `author.qimao.com`、
掌阅移动站不展示创作入口。**这条判据是"审计提示"，不是"命不中就删规则"。**

### P2（本轮未做）：书旗「正文 URL 由目录项的 JSON 字段提供」

`shuqi.com` 的目录接口（`ocean.shuqireader.com/.../book/chapterlist`）本来能把
目录 + `payStatus` + **带 sign 的逐章正文 URL** 全部白拿，卡点只有一个：
**现 `chapter.body_api` 只支持 `{origin}/{bid}/{cid}/{seq}` 这类固定模板，带不了逐章签名**。
这需要动引擎（`catalog` 项携带正文 URL → chapter 阶段取用），
是本轮工程量最大的一项 → **按优先级排在最后，本轮未启动**，形态证据已完整存进
`shuqi.com` 存根与 `docs/NEW_SITES_PLAN.md`，下次可直接开工。

### Notes

- 测试 192 全绿；门禁 8 项 PASS；规则总数 145（正版 27 = **16 启用 + 11 存根** / 免费镜像 118）。

## [0.8.8] - 2026-09-21

按「下一批建议」执行：**掌阅系两站接入成功**（书山中文网 + 掌阅小说网移动站），
豆瓣阅读留作候选，书旗查清为「署名接口 + 非锚点目录」（超出当前 schema，转存根）。
正版池 21 → **24 条**（启用 13 → 16）。

### Added

- **`shushan.zhangyue.net`：书山中文网（掌阅系·免费阅读）** —— 本批最大的一个
  · 书籍页 `/book/{bid}/`，章节页 `/book/{bid}/{cid}`，正文容器 **`div.art_con`**。
  · ⚠ **目录不在静态 HTML 里**：纯 HTTP 取书籍页只有 **39 个 `<a>`**（而该书有 821 章）。
    目录是页内锚点 `#directory`（文字「目录（821章）」），**真 Chrome 里点一下**才渲染出列表 ——
    实测渲染后 `a[href*='/book/']` = **821 条**，与「目录（821章）」完全吻合。
    → 用 `browser.click_selectors` 点锚点 + `wait_selector` 等链接出现。
  · 实测《无暗英雄》：**821 章**（第1章 → 第821章）、正文 58 段 / 3186 字、首段为正文。
- **`m.zhangyue.com`：掌阅小说网移动站（全本免费）**
  · 书籍页 `/detail/{bid}`，**目录在独立页 `/chapter/{bid}`**（书籍页只有 16 个链接），
    章节页 `/readbook/{bid}/{cid}.html`，正文容器 **`div.read_c`**。
  · 实测《重生农女之神戒空间》：50 章、正文 54 段 / 3472 字、首段为正文。
  · ⚠ 与 `www.zhangyue.com`（**企业站**「掌阅科技-悦享美好时光」）区分。
- **新能力 `catalog.item_strip_selectors`**：取目录项标题前，先剔掉**链接内部**的徽章元素。
  实测掌阅小说网移动站：`<a …><span class="type">免费</span> 第一章：重生</a>` ——
  直接取整段文本会得到「免费\n第一章：重生」，导出后标题全带个「免费」。
  这些徽章在**链接内部**，`strip_selectors`（作用于正文容器）管不到、也没有别的绕法
  → 按选择器剔（在**深拷贝**上剔，原树仍用于读 class 判 VIP）。

### 存根

- **`shuqi.com` 书旗小说（阿里）→ 停用**。已探明形态正确但**缺一个能力**：
  ① 根路径 403，但 **`t.shuqi.com` 可用**；书籍页 `/book/{bid}.html`、目录 `/catalog/{bid}/`、
    阅读页 `/reader/{bid}/?forceChapterId={cid}`。
  ② **目录接口已挖到**：`ocean.shuqireader.com/webapi/bcspub/openapi/book/chapterlist` →
    完整目录 + 逐章 **`payStatus`（0=免费）** + **`contUrlSuffix`（带 sign 的正文 URL 后缀）**
    + `freeContUrlPrefix` —— 目录与 VIP 判定都能白拿。
  ③ ⚠ 但该接口**纯 HTTP 打不开**：需 **JWT token + 每请求 sign**，直连 **401**；
     token 是查询参数（`{cookie:NAME}` 读不到）。
  ④ ⚠ 也**不能退化成渲染后读 DOM**：渲染目录页后 `a` 标签数 = **0** ——
     章节渲染成 `<li class="ellipsis line">第一章 蛋要碎了</li>`，**无 href/id/data-***。
  → 需要**新能力**「正文 URL 由目录项的 JSON 字段提供」（现 `body_api` 只支持固定模板形式）。

### 尚未拿下（留作候选）

- **豆瓣阅读 `read.douban.com`**：首页 200 / 52 KB，但**链接形态统计为空**（SPA/JS 壳），
  且平台以**试读制**为主 → 免费比例需先核实再投入。

### Notes

- 测试 192 全绿；门禁 8 项 PASS；规则总数 142（正版 24 = 16 启用 + 8 存根 / 免费镜像 118）。
- 本批方法复用：`tools/hunt_api.py`（书旗的接口、书山的目录锚点都是靠它/浏览器定位的）。

## [0.8.7] - 2026-09-21

按全哥指示推进「① 创世/话本 ② 得间」：**创世、话本接入成功**，得间查清为**落地壳页**
（结论明确、转为存根 + 指向更有价值的掌阅系）。正版池 19 → **21 条**（启用 11 → 13）。

### Added

- **`chuangshi.qq.com`：创世中文网（阅文·含 VIP）** —— 从存根**翻案成可用规则**（关键收获）
  · ⭐ **目录页的真路由是 `/chapter/{bid}`**。踩过三条错路：书籍页 `/detail/{bid}` 的
    `a.catalogueItem` = 0；`/book/{bid}/catalog` 是 **301 跳转**；真 Chrome 渲染这两处
    **依然没有**本章节链接。
  · 最后靠**浏览器监听网络请求**（新工具 `tools/hunt_api.py`）+ 点击页面上写着「查看全部」的
    `div.link-entry`，才看出它跳到 `/chapter/{bid}` —— 那才是目录页，**纯 HTTP 可取（96 KB）**。
  · 与云起书院是**同款前端组件**：`a.catalogueItem` + `span.icon-lock` + `/read/{bid}/{seq}` +
    正文 `#article`，**四项逐项一致**；差别只在「目录在哪个 URL」（云起在书籍页里、创世在独立页）。
  · 实测 52 → **38 章 / 12 章 VIP 零请求**，正文 126 段 2038 字，首段为正文。
- **`ihuaben.com`：话本小说（正版·同人/原创免费阅读）**
  · 书籍页 `/book/{bid}.html`（目录就在页内），章节页 `/book/{bid}/{cid}.html`，
    正文容器 **`div#contentsource`**（class `nbcontent`）。
  · ⭐ **目录页有两个块，必须只取正文列表**：`div.newestChapters`（顶部「最新章节」回显，倒序）
    vs `div.chapter-list`（正文完整列表）。只取后者，**一次性排除回显 + 导航项**，
    比逐条写 `item_deny_text` 干净（试过 `dedupe=keep_last`：它**不改变被保留项的位置**，
    回显仍排在头部 —— 分块选容器才是对的解法）。
  · 实测 40 章、正文 152 段 2133 字，第1章起、第40章收尾。
- **新工具 `tools/hunt_api.py`（接口猎手）**：真浏览器打开页面 + 监听
  `request`/`response`，可选先点击某选择器触发懒加载，打印 JSON 接口的 URL/方法/POST 体/响应片段。
  创世就是靠它破的局。含 `--ignore-https-errors`（实测得间证书过期时必须开）。

### 存根

- **`idejian.com` 得间免费小说 → 停用（APP 独占）**，证据链完整：
  ① **HTTPS 证书已失效**（`ERR_CERT_DATE_INVALID`）；
  ② http 首页真 Chrome 渲染后**只有 18 个链接**，无一个指向书籍/章节；
  ③ 监听全部请求 **= 0 条 XHR**（不是"接口没找到"，而是页面上根本没有目录/正文）；
  ④ `m.` / `h5.` / `wap.` / `yd.idejian.com` **全部 DNS 不解析**。
  → 结论：得间 PC 端只是**导流 APP 的落地页**，与米读/熊猫同类。
  · 顺带发现两条**活且有内容**的掌阅系线索：`shushan.zhangyue.net`（书山中文网）、
    `m.zhangyue.com`（掌阅小说网移动站）→ 已记为下一批优先目标。

### 教训（写进规则 notes 与 skill）

- ⚠ **判断「正文能否取到」要拿足够多个样本**：我最初抽到话本两本**公告类**书
  （《话本作者攻略大全》《话本小黑屋》），章节页整页只有 1400 余汉字、正文容器为空，
  **差点误判「话本正文是 JS 渲染的」**；换两本真小说（如 `12259567`）就正常了。
- ⚠ **`dedupe` 不改变「被保留项的位置」**：回显与正文列表重复时，`keep_last` 只是换了保留哪一条，
  **顺序仍是回显在前**。正确解法是**用选择器把回显块排除掉**。

### Notes

- 测试 192 全绿；门禁 8 项 PASS；规则总数 139（正版 21 = 13 启用 + 8 存根）。

## [0.8.6] - 2026-09-21

**正版继续推进**：接入**晋江文学城**（书源生态里出现最多的正版站，79+97 条书源），
按全哥给出的实测信息补 2 条 APP 独占存根并纠 3 处域名误认。正版池 16 → **19 条**。

### Added

- **`jjwxc.net`：晋江文学城（正版·含 VIP）**
  · **入口必须用桌面版** `onebook.php?novelid={bid}`：实测移动版 `m.jjwxc.net/book2/{id}`
    只给 40 条且全是 `/vip/` 链接（拿不到免费章）；桌面版 199 KB 里目录完整
    （`table a[href*=chapterid]`，13 条免费章）。故 `info_url` **写死 www 主机**，
    把 m. 的输入也归一到桌面页。
  · **VIP 是「天然隔离」**：晋江的 VIP 章**不是 `chapterid` 链接**，而是
    `<a rel="...buynovel.php...">[VIP]</a>` —— 既没 `chapterid=`、href 也不是章节页
    → **根本进不了目录**，一个请求都不会发。比「先标 locked 再跳过」更彻底。
    （代价：报告里看不到「受保护 N 章」的计数。）
  · 正文容器 `div.noveltext`；元信息从 `<title>`《书名》作者 分段取。
  · 实测《昭暮》：13 章免费、书名/作者正确、正文 196 段 / 4711 字、首段为正文。
- **新能力 `chapter.drop_leading_symbol_paragraphs`**：丢掉正文**头部**的「纯符号噪声行」。
  实测晋江正文容器顶部有一坨无 id/class 的工具栏，剔完能命名的元素后仍残留独立的
  `[` 与 `]` 两行 —— **没有可用的选择器**，但它们只由标点组成。
  只在头部丢（正文中间的「……」是合理文学用法）。配 2 个测试（含「中间不许丢」）。

### 存根（按全哥实测信息新增 2 条，正版池存根 5 → 8）

- **`midureader.com` 米读小说 → 停用（APP 独占）**：官网打开即要求下载 APP；
  `midukanshu.com` 直接 403。
  ⚠ **域名纠错**：`nsdkh.com`、`spyxb.com` 是**盗版站**，不是米读。
- **`kureader.com` 熊猫脑洞小说（原熊猫免费小说）→ 停用（APP 独占）**：
  `xm.kureader.com/home.html` 只引导下载 APP；原 `xiongmaoxy.com` 已 DNS 不解析。
  ⚠ **域名纠错**：`xmzw.net` 是**盗版站**，不是熊猫官方。

### Changed

- **付费墙标记补阅文系 APP 墙文案**：全哥实测 VIP 章显示
  「上QQ阅读APP看书，第一时间看更新」→ 已按**整句**加入 `PAYWALL_MARKERS`
  （不按「QQ阅读」这种短词收，避免误伤正文里出现的平台名）。

### Notes

- 测试 190 → **192** 全绿；门禁 8 项 PASS。
- **新增候选**：**话本小说 `ihuaben.com`**（目录在书籍页 `/book/{bid}.html` 里、48 条，
  但**章节页正文是 JS 渲染的**：整页仅 627 汉字 → 需浏览器路由或找接口）。
- **「作家入口」判据已记入计划**（全哥提出，暂记后续执行）：正版站才提供**创作/投稿入口**，
  盗版站只推小说 → 可作为「正版 vs 盗版」的机械判据之一。
- 创世中文网仍为存根：已确认其正文容器也是 `#article`（与云起同），**只差目录**
  （书籍页与 `/book/{bid}/catalog` 渲染后均无章节链接 → 目录走 XHR）。

## [0.8.5] - 2026-09-21

**正版方面开始实行**（镜像铺开按指示暂时收尾）。新增 **2 条正版族规则（覆盖 3 个域名）**
+ 1 条停用存根；正版池 13 → **16 条**（启用 9 → 11）。

### Added

- **`yuewen-hongxiu`：红袖读书 / 小说阅读网**（阅文·免费阅读线，**2 域一条规则**）
  · 书籍页 `/book/{bid}`，目录**就在书籍页里**（`a[href*='/chapter/']`，形如 `/chapter/{bid}/{cid}`）
  · 正文容器 `div.read-content`（id `j_readContent`）
  · 元信息走 `og:novel:*`（book_name / author / status）
  · 实测《重生换宗…》：**316 章全免费**、第1章「身死」起、番外「魂归」收尾、正文 2384 字，校对 PASS
  · **两域同一后端**：把红袖的书籍 ID 直接拼到 `readnovel.com/book/{bid}` 就能打开、
    章节 URL 形状也一致 → 并入同一规则（已验证两域结果完全一致）
- **`yuewen-yunqi`：云起书院**（阅文·含 VIP）
  · 书籍页 `/detail/{bid}`、目录 `a.catalogueItem`、章节 `/read/{bid}/{seq}`
  · 正文容器 `#article`（class `isTxt chapter-box`）
  · **VIP 在目录层就锁掉**：实测该书 **679 章 = 20 免费 + 659 VIP**，
    标记是目录项里的 `span.icon-lock` → `catalog.vip_child_selector`，**659 章零请求**
  · ⚠ `{seq}` 是**章节序号**（1~679），不是与顺序无关的 ID —— 故 `sort=cid_numeric_asc`

### 已知存根

- **`chuangshi.qq.com`（创世中文网）→ 停用存根**。URL 形状与云起**完全一样**
  （`/detail/{bid}` + `/read/{bid}/{seq}`），但**目录不在书籍页里**：
  实测书籍页 `a.catalogueItem`=0；`/book/{bid}/catalog` 纯 HTTP 只有 9 个链接
  （还是「最近更新」侧栏里**别的书**的）；**用真 Chrome 渲染后仍是 0**
  → 目录由 XHR 异步下发，需监听请求找接口（同 §1.17 的做法）。存根里写明了已试路径与证据。

### 教训（已写进规则 notes 与 skill）

- ⚠ **判断「两站同模板」要比对「书籍页里的目录容器」，不能只看首页链接形状**。
  我一开始按首页链接形状相同就断定创世与云起同模板、并入一条规则 —— 那是错的，
  两站只是 URL 形状一样、目录位置不同。**首页形状是线索，书籍页结构才是证据。**

### Notes

- 测试 190 全绿；门禁 8 项 PASS。
- **测试又去掉一处「写死清单」**：`test_disabled_stub_documents_why` 原本写死了停用规则 id 集合
  （起点翻案、创世新增都要改它）。改为守真正的不变量「**每条停用规则都有足够具体的
  `disabled_reason`**」+ 几个长期存根仍在。
- 下一步正版候选（按 docs/NEW_SITES_PLAN.md §12）：得间免费小说（**PC 端是 JS SPA，需浏览器+接口**）、
  逐浪、潇湘书院、掌阅、磨铁、豆瓣阅读、书旗（根路径 403）、晋江（根路径 403 但 `m.jjwxc.net` 待试）。

## [0.8.4] - 2026-09-21

**三处着力点全部推进**：镜像族规则 38 → **111 条**，覆盖域名 203 → **367 个**
（免费镜像池 45 → **118 条**）。

### ① 修掉两个「让书籍页根本找不到」的真 bug

- **`chapter_like()` 判据错了（影响最大）**：老判据是「末段是 `数字.html` 就算章节页」，
  于是把 **`/shu/91318.html`、`/book/91318.html` 这类单段数字的书籍页也跳过** ——
  438 个站因此找不到书籍页。
  新判据：**两个以上数字段**（书号+章号，如 `/book/21/451.html`）才算章节页；
  只有一个数字段时，看**末段之前那一段是不是结构词**
  （`/book/91318.html` 的 `book` 是 → 书籍页；`/txt/vpnm/1.html` 的 `vpnm` 不是 → 章节页）。
- **候选顺序把可用候选挤掉了**：`derive_book_urls`（从最新章节反推）排在前面，
  实测 `shuhuangxs.com` 反推出 32 个**全是 404** 的 URL，把试位占满 →
  真正可用的 `/shu/44312.html` 根本没被试到。
  → 改成「按链接形态找到的书籍页」优先，并把试位从 6 提到 10。

### ② 目录容器自动发现：文字判据当**护栏**，不当主判据

- 新增「链接文字像不像章标题」（`第N章` / `序章` …）。
  **为什么需要**：光看 href 分不出章节与分类 —— 实测 `/sort/1/1.html`（分类）与
  `/book/21/451.html`（章节）形态一样，但文字完全不同（「玄幻」vs「第1章 …」）。
- ⚠ **但主判据必须仍是链接数**：我第一版反过来（文字优先），
  结果 `sequge.com` 从 643 章退化成 451 章（选中外层 `div.body` 而非精确的 `ul.dirlist`）。
  最终形态：`链接数为主 + "文字像章标题的占比 ≥30%" 做护栏`。
- 顺带：**正文候选全未命中时，接受自动识别的容器**（它就是一个可用的 CSS 选择器），
  不再只当"参考"。

### ③ 782 个「有响应但被拒」的域：改试备用入口

根路径 403/404 不再直接判死，先试 4 个通用入口（`/index.html`、`/sort/`、`/top/`、`/all/`）。
实测救回 **122 个可达（20%）**。⚠ 备用入口用**单次尝试**（否则 4 入口 ×(1+retries)
会让每个域变成十几个请求，785 个域要跑一个多小时）。

### 结构：镜像池移入子目录

```
noveldown/rules/          20 条手工规则（一站点一文件）
noveldown/rules/mirrors/  111 条批量生成的镜像池规则
```
加载器改为**递归**（新增 `noveldown.rules.iter_rule_files`）。
200 条自动生成的规则与手写规则混在一层会让 `rules/` 完全没法看。

### Notes

- 漏斗：可达 1,489 → **3,257**；可用候选 970 → **2,305**；深探通过 92 → **562**；
  引擎复验两轮 200 条草稿 → 通过 **111 条**（56%），未通过的 89 条**已剔除、不留仓**。
- `verify_mirror_rules.py` 新增 **`--concurrency`**：200 条串行要 30+ 分钟，
  并发 8 后 9 分钟跑完（每条起独立 Downloader，http_client 的 session 是线程本地的）。
- 测试 190 全绿；门禁 8 项 PASS。
- **下一轮**：仍失败的 89 条里 `目录只 0 章` 占 28 条 ——
  扫描器用「章标题文字」认出了章链接，引擎却提不出 cid（已把 `id_from.pattern` 放宽到
  `.html` 可有可无，但没解决）。需要按**每域实测到的章节 URL 形态**生成 pattern。
  另有 7 个 404、若干 `目录只 10~17 章`（疑似目录分页）。
- ⚠ **族规则的验证覆盖**：目前只用 `demo_url`（簇内第一个域）复验，
  同一 `match` 里其他域未逐个复验 —— 这是已知的覆盖缺口，下轮应逐域抽验。

## [0.8.3] - 2026-09-20

**镜像池收尾**：完成「未确认域」重扫与深探补扫，族规则 30 → **38 条**，
覆盖域名 73 → **203 个**（免费镜像池 37 → **45 条**）。

### 关键改进：把「假死」的站救回来

0.8.2 里留下的 **4,115 个「未确认」域**（只是这次没连上，**不是死站**）已重扫完毕：

| 项 | 数字 |
|---|---|
| 重扫域数 | 3,120（另 995 个在首轮已覆盖） |
| **救回可达** | **1,291（41%）** |
| 全站可达 | 1,489 → **3,074** |
| 可用候选（扣掉空壳/启发式排除） | 970 → **2,162** |

> 41% 的救回率印证了 0.8.2 的判断：**单次连不上 ≠ 站点已死**。
> 若按"试一次就判死"的做法，这批源会被永久漏掉 —— 这正是「源越多越抗抽风」的反面。

### Fixed

- **深探的「环境假失败」会被误当死站**：213 个域的深探失败原因其实是
  `ProxyError` / `ConnectionError` / `SSLError`（本机环境问题），
  却被写进结果当结论。→ 新增做法：按失败**类型**区分，
  环境类失败**从结果里剔除并重扫**（`--retries 3`），而不是留成结论。
- **`tidy` 支持合并多份扫描结果**：重扫结果落在另一个文件（`live.retry.jsonl`），
  不合并的话第二轮救回的站就白扫了（报告里仍按「不可达」算）。
- **`verify_mirror_rules.py --only-failed` 的 `--from` 参数**：原来读 `--out`，
  而 `--out` 是本次要写的新文件 → 读不到上次结果、把全部规则重验一遍。
- **`gen_family_rule.py` 不再产出「注定验证不过」的规则**：
  实测有 2 组聚类**无可验证的 demo** —— 站点把书页跳到了本组域名之外的域，
  于是 `demo_url` 的主机名不在 `match` 里（报「没有匹配的站点规则」），
  回退到域根又因 `url_pattern` 匹配不上而报「无法提取书籍 ID」。
  → 这类组**直接跳过不产出**（并打印出来），留给下轮改进深探来覆盖。

### Notes

- 引擎复验：64 条草稿 → 两轮通过 **38 条**（59%）；未通过的 26 条**已剔除，不留仓**。
  仍失败的类型（留档供下轮改进）：`目录只 0/10/15 章`（目录容器选到了外层）、
  `正文疑似目录`（把章节目录当正文抓了）、`404`（站点已变）。
- 每轮重跑流程：`scan_mirrors --phase tidy` → `--phase deep` → `gen_family_rule.py`
  → `verify_mirror_rules.py` →（两轮）→ 剔除未通过 → 提交。
- 测试 190 用例全绿；门禁 8 项 PASS。

## [0.8.2] - 2026-09-20

**镜像站批量铺开**：把「手工十几个候选」变成「上万条线索 → 逐条实测 → 族规则」的流水线。
规则从 20 条增到 **50 条**（免费镜像池 7 → **37 条**，覆盖 **73 个镜像域名**）。

> 起因是全哥纠正了我的一个判断错误，见下「Changed 判断」。

### Added

- **4 个批量工具**（都可重跑、可续跑）：
  | 工具 | 作用 |
  |---|---|
  | `tools/harvest_book_sources.py` | 从书源库 API 拉**元数据**（name/url/热度），只取线索**不取规则体** |
  | `tools/scan_mirrors.py` | `live` 存活（**三态**）/ `deep` 结构（逐候选实测）/ `tidy` 去重再判 / `stats` 聚类 |
  | `tools/gen_family_rule.py` | 按「命中的目录 + 正文选择器」聚类 → 生成族规则 |
  | `tools/verify_mirror_rules.py` | **用真实引擎**逐条复验（`Downloader.run(limit=1)` + 目录数/正文字数/目录当正文检测） |
- **`catalog.item_deny_text`**（新能力）：按文本剔除**导航类伪目录项**。
  实测镜像站目录里混着「开始阅读」「在线书库」「TXT下载」——它们和真章节一样带数字 href，
  **cid 甚至与第 1 章相同**，于是 `dedupe=keep_first` 把真标题挤掉（导出里第 1 章叫「开始阅读」）。
  加这一条后，同批规则的引擎通过率从 **10/46 提到 27/46**。
- **`browser.wait_selector` 角色化 + `browser.nav_retries`**（见 0.8.1，本轮用于批量规则生成）。
- `pytest.ini`：`testpaths = tests`。

### Changed（判断修正 —— 第三次同类错误）

- **删掉「不因同模板而跳过可用源」的错误结论**。我此前把「大概率是同一套模板的又一个镜像」
  当成跳过理由、记为「先不做」。全哥纠正：
  > 「盗版尽量铺开镜像站数量，**不能因为是大概率是同一套模板的又一个镜像而跳过**。
  > 这就是**要分开建池的原因**。盗版站存在抽风通病，**源越多才能更好规避**。」

  镜像站的价值**不在模板新，而在同类源的数量**：同一份内容有多个可替换域名才算真的可用。
  → `docs/NEW_SITES_PLAN.md §11.3` 已把这条写成反面教材留档。
- **测试改成「以文件系统为准」**：不再写死规则 id 明细（批量加域后每加一个都要改测试），
  改为断言「`rules/*.json` 全部能加载」+ 关键站点守门。
- **`.gitignore` 增 `.sources/`**：线索原始清单（上万条）落仓外，仓里只留工具与结论。

### 实测发现（影响后续做法，都写进文档与 skill）

1. **⚠ 单次连不上 ≠ 站点已死**。本机所有请求都经系统代理，实测**单次请求失败率约 45%**
   （`ProxyError` / `SSLError` / `ReadTimeout` 混合），**降低并发并不改善**
   → 是环境+站点共同导致。把「已判死」的域串行重试：30 个里**救回 5 个**（假死率 ~17%）。
   → 存活判定改**三态**（可达 / **有响应但被拒** / **未确认**），
   `--retries` 默认 2（3 次尝试 ≈ 91%），并提供 `--only unknown` 重扫。
   **`HTTPError` 说明站点有响应，403 是 WAF 不是死站。**
2. **书源库数据是脏的**：`url` 字段可能是任意字符串（实测含中文的融合版书源），
   直接喂 `urlparse` 会抛 `ValueError: netloc ... NFKC`。取 hostname 前先 try + 正则校验，
   校验不过**计数丢弃**。
3. **书号未必是数字**：实测 `min-yuan.com` 用字母编码 `/txt/vpnm/1.html`。
   bid 正则放宽到 `[A-Za-z0-9_-]{2,}`，且 `url_pattern` **必须锚到路径最后一段**
   （早期不带锚点的 `([A-Za-z0-9_-]+)` 在 `https://x.com/0_8/` 上抓到 **`https`** 当书籍 ID）。
4. **目录容器要自动发现**：固定候选选择器追不上类名花样（实测 `sequge.com` 的目录是
   `ul.dirlist`，不在任何通用候选表里 → 被判「无可用目录」）。
   改为「找出含章节式链接最多的节点」，与 v0.8.0 的自动识别正文容器同一思路。

### 漏斗（每级都是实测数字）

书源库 **31,526** 条 → 采集 25,429（脏域名丢 72）→ 唯一域 **10,754**（启发式剔成人向 295 / 非小说 541）
→ 已扫 9,444 → 可达 1,489（其中**空壳/占位 498**：返回 200 但只有几百字节或 0 个链接）
→ 可用候选 **970** → 结构深探 1,468 → 通过 92 → 生成族规则 46 条 → **引擎复验两轮通过 30 条**
→ 落地 **30 条族规则 / 73 个镜像域名**（两轮均失败的 16 条已剔除，不留在仓里）。

### Notes

- 测试 188 → **190**（新增 `item_deny_text` 2 个用例）。
- ⚠ 仍有 **4,115 个「未确认」域**待重扫（见 `docs/NEW_SITES_PLAN.md §11.4`）——
  它们只是"这次没连上"，**不是死站**，里面还有可用源。

## [0.8.1] - 2026-09-20

接入免费镜像族第 7 条（速读谷），并修掉两个**等待条件**上的结构性问题
（一个是新加的能力，一个是潜伏已久的失效配置）。

### Added

- **站点：速读谷（`shudugu.org` / `sudugu.cc`，免费镜像）**。书籍页 `/{bid}/`、
  目录 `div#list`（实测 794 个 `/{bid}/{cid}.html` 链接）、正文 `div.con`（实测 1815 汉字）。
  目录是**新章在前**（相邻 cid 递减）→ 用 `cid_numeric_asc` 恢复阅读顺序。
  走 `fetch_mode: browser`（requests 侧 SSLError，真浏览器可正常打开）。
  实测：《捞尸人》790 章、抓 6 章 14957 字、导出 TXT/MD/EPUB/HTML 四格式、校对 **PASS**。
  ⚠ 两个注意事项写进规则 `notes`：书页 `h1` 是「**653.5万字 捞尸人**」（带字数前缀，
  直接用会污染书名，故书名/作者都走 `<title>` 分段正则）。
- **`browser.wait_selector` 支持按页面角色声明**（对象写法）：
  ```json
  "browser": {"wait_selector": {"book": "#bookName", "chapter": "div.con"}}
  ```
  未出现的角色 = 不等待；值写 `null` / `false` / `""` 亦为不等待。
  字符串写法仍保留（= 全角色广播，完全等价于旧行为）。
  未知角色名、非字符串/对象类型在**规则加载时**即报错（不再等抓取时才炸）。
- **导航瞬时失败的重试带退避**：`browser.nav_retries`（1~8，默认 **4**），
  重试间隔 `1.2s × 第几次`。理由：这类站抽风是「一段时间内持续 reset」，
  **紧挨着连发重试会撞进同一窗口一起失败** —— 实测速读谷 0 退避连发 3 次全
  `ERR_CONNECTION_RESET`；加退避后**首个重试即成功**。
- **`pytest.ini`**：限定 `testpaths = tests`。
  仓库根下有仅供本地调研的第三方参照源码（`_ref/`、`.archived/`，均已 gitignore），
  它们自带 `test/` 目录会被 pytest 顺着目录树捞进来，然后在 `import coloredlogs`
  之类的第三方依赖上抛出收集错误、把本项目的测试结果淹掉。

### Fixed

- **等待条件会「漏」到不该等的页面上**（结构性缺陷）。
  顶层 `browser.wait_selector` 原本是**全角色广播**，但三处页面的就绪标志天然不同：
  速读谷把**章节容器** `div.con` 写成顶层字符串后，**书籍页**也要等 `div.con`
  （不存在）→ 白等满 30 秒超时。实测目录耗时 **37.0s → 7.6s**（其余耗时是正常渲染）。
  同病的 `soushuwang.cc`（`#chaptercontent`）一并改为只作用于 `chapter`。
  ⚠ qidian 的顶层字符串是**书籍页**条件（`#bookName`），改造后必须仍在 —— 已加回归测试守住。
- **`catalog.browser_wait_selector` 从未生效**（潜伏 bug）。
  该字段写在 `catalog` 段下（文档也是这么写的），但代码读的是 `catalog.pages` 子字典
  （`cfg = rule.catalog_cfg.get("pages")`）→ **恒为 None**，于是 17K 声明的目录等待条件
  一直靠 `wait_ms: 2500` 掩盖着、从未真正启用。改为从 `catalog` 段读取。
  实测 17K 目录 586 章、13.3s、正文 114 段/2311 字，无回归。
- **`_fetch_browser` 不再自行回退顶层默认值**。改为用哨兵 `_UNSET` 区分
  「未指定」（→ 按角色解析）与「明确不等待」（→ 直接不等待）——
  `wait_selector or cfg.get("wait_selector")` 这种写法无法表达后者，正是上面漏等待的成因。

### Notes

- 新增测试 10 个（`TestWaitSelectorRoles`），全套 **188 个通过**。
- 三段 E2E 实测：速读谷（790 章 / 6 章 14957 字 / 校对 PASS）、
  搜书网（71 章 / 3 章 6000+ 字）、17K（586 章 / 13.3s）。

## [0.8.0] - 2026-09-20

落地 pingcode 那篇的新点子（自动识别正文容器），并把规则按来源**分池**；
另新增免费镜像族的第 5 条规则。

### Added

- **`guess_content_container()`：自动识别正文容器**（`chapter.auto_content`，默认开）。
  打分 = `汉字数 × 标点系数 × 段落系数 × (1 − 链接文字占比)`，再在最高分 90% 以内取**最深**的那个。
  触发时机：`content_selector(s)` 没选到容器、**或选到了却抽不出段落**（站点改版）→ 自动兜底并留痕
  （备注写「…已自动识别正文容器」）。规则里写 `"auto_content": false` 可关闭。
- **浏览器路由支持代理**（`browser.proxy`）：Chromium **不读** `HTTP_PROXY/HTTPS_PROXY`
  环境变量（requests 会读），所以「只在代理下可达」的站点走浏览器路由会报 `ERR_TIMED_OUT`。
  规则里写 `"proxy": "env"` 即沿用环境变量里的代理，也可直接给代理 URL。
- **规则分池 `pool`**：`正版` / `免费镜像` 两类，`sites` 命令按池分组展示
  （当前 19 条：正版 13 / 免费镜像 6）。
- **站点：免费镜像族（`soushuwang.cc` / `bqg142.cc` / `soduo.cc`）**
  —— 一条规则覆盖三个域（同一套模板）：书籍页 `/book/{bid}/`、目录
  `div.listmain dl dd a, ul.section-list li a`、正文 `div#chaptercontent` 或 `div#content`。
  章节页是 **JS 反爬中转页**（「加载中……」→ 种 `getsite` cookie → `/userverify` → 跳 `bqg142.cc`
  的 hash 路由），故走 `fetch_mode: browser`；**章节内自带分页**（`下一页` → `{cid}_2.html`）
  由 `next_page.continue_when=same_base_id` 处理。
  实测：搜书网 2 章 6746 字、速读小说 30 章（2 章导出）3846 字，校对 PASS。

### Fixed

- **自动识别容器的选取逻辑错了**：原实现「先按汉字数取 90% 以上、再取最深」，
  于是**忽略了自己算出的分数**。实测速读小说章节页：正文 `div#content`（749 汉字、
  无链接）旁边还有个含「推荐本书」的外层（883 汉字），结果选中了外层 →
  首段变成「推荐本书」。改为**按分数选**（并把标点系数从「绝对阈值」改成
  **候选间相对值**，正文的标点密度明显高于 wrapper），修正后正确选中 `div#content`。
- **`page.content()` 导航竞态**：站点做多跳 JS 跳转时（搜书网：中转页 → `/userverify` → 跨域 hash 路由），
  playwright 会抛 `Unable to retrieve content because the page is navigating and changing the content`。
  已加等差重试（识别该错误 → 等 `domcontentloaded` → 再取，最多 4 次），不再当成失败。

### Changed

- **撤销一条我自己加的约束**：此前文档里写着「不主动新增盗版镜像站」——**那不是全哥的要求**，
  全哥最初的意见恰恰相反（过度防御导致可用规则全是盗版站）。现改为**按池分类**（`正版` / `免费镜像`），
  不设人为限制；候选站只要实测能用就收进对应池子。

### Docs

- 记入两条环境/风险事实：
  1. **本机 requests 走系统代理**（`HTTP_PROXY/HTTPS_PROXY` 已设置、`trust_env` 默认开），
     而 **curl 不读**这些变量 —— 这才是「curl 000 但 requests 200」的**主因**（此前归因于 TLS 栈差异，不准确）。
  2. **抽风是盗版镜像站的通病**（同一 URL 时而 200 时而超时，实测搜书网/速读小说多次）——
     探测时**不要凭一次失败判死**，运行期靠重试 + 断点续爬。
- 新增参考记账：Gitee `xioo/shuyuan`（fork 自 `no-mystery/shuyuan`）与书源仓库
  `shuyuan.yiove.com` —— 那是给**阅读APP(Legado)** 用的书源配置，**格式与本项目不通用**，
  仅作**站点候选池**；⚠ 记入风险台账：**阅读APP 已因侵权违法、为免担责而删除其开源源码**。
  另：`www.shudugu.org`（速读谷）**未死** —— requests 侧 SSLError，但真浏览器可正常打开，
  属链接不稳定，已更正此前「不可达」的判断。

### Tests

- 170 → **177**。新增：自动识别容器（选中贴身正文而非含导航/推荐位的外层、无正文时返回 None、
  选择器失配时兜底留痕、`auto_content:false` 可关、**命中配置选择器时不得越权接管**）、
  池子字段与免费镜像池数量、镜像族规则形态（三域 + 分页）。

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
- **复用层**：从本家 `本家 webcopier 仓` 按「复制优于共享」抽取
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
