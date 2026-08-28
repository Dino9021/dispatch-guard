<!-- One file, two languages: Traditional Chinese first, English second - the same rule
     README.md follows, and for the same reason: a translation nobody can see beside its
     original is a translation nobody updates. -->

> 🇹🇼 **正體中文（本節）** ｜ 🇬🇧 **[English](#changelog-english)**

# 版本紀錄

⭐ **README 和 PROTOCOL.md 只描述「現在」。** 什麼時候變的、為什麼變，寫在這裡。
完整的理由在每一個 commit 的訊息裡；`git log` 是唯一的權威。

---

## ⛔ 安全公告 — 0.4.0 到 0.6.0 什麼都沒在強制

**受影響：** 0.4.0、0.4.1、0.5.0、0.5.1、0.6.0。**修正於 0.7.0。**

那五個版本裡 `keep_clock_running()` 用到一個沒有被綁定的名字。`NameError` 從 `main()`
**所有事件分支之前**那一行往外拋，最上層處理器以 0 結束而且不印任何東西 ——
⛔ **一個什麼都不印的 hook 等於批准了那次呼叫。**

⇒ session 沒有被蓋章，gate 整段走勸告分支：用量到 STOP 也照樣派工、背景派工不擋、
計畫檢查不做。三個自我檢查全程是綠的，因為它們只測了決策函式、從來沒有呼叫真正的函式。

**怎麼確認自己中招過：** `.claude/dispatch-gate.log` 或 `%TEMP%\dispatch-gate-error.log`
裡有沒有這一行。

```
GATE-ERROR NameError("name 'now' is not defined")
```

**怎麼修：** 更新到 0.7.0 以上，然後開一個新 session。

---

## 0.31.0

- ⭐ **Model prices are read from Anthropic's published pricing page instead of being typed
  into the source.** `hooks/model_pricing.py` parses
  [the page's markdown](https://platform.claude.com/docs/en/about-claude/pricing.md) into
  `model_pricing.json`, stamped with both an epoch and a readable
  `YYYY-MM-DD HH:MM:SS` (UTC and local).
- ⛔ **The hand-typed table was already wrong, and nothing said so.** It priced Claude
  Haiku 3.5 at $1 per million input tokens; the published price is $0.80. That row was not
  copied - it was reasoned from the harness's own weight function. ⇒ A table that cannot be
  checked against its source drifts silently, and this one had.
- ⛔ **The other candidate was rejected, correctly.** An earlier attempt read the `pricing`
  field out of the installed Claude Code binary. ⚠ A machine that has not updated Claude
  Code then prices models from an old catalog - not fresher, just stale somewhere else. The
  published page is the only source that does not depend on a local install being current.
- ⛔ **`GET /v1/models` has no pricing field.** It returns `id`, `capabilities`,
  `created_at`, `display_name`, `max_input_tokens`, `max_tokens`, `type`. That is a gap in
  the API, not in the search.
- ⭐ **Refreshed in the background, never blocking.** Past `model_price_hours` (default 24)
  the gate forks a detached child; the session that noticed keeps the table it has and the
  new numbers land for the next one. ⛔ No hook ever makes a synchronous HTTP call - that
  would make every tool call wait on the network, and a slow proxy would be
  indistinguishable from a hung plugin.
- ⛔ **A failure never empties the table.** A failed fetch, or a 200 whose table changed
  shape and parsed to nothing, both keep the previous file. The attempt is recorded in
  `model_pricing.status`, so a fetch that has been failing for a month cannot look like one
  that never needed to run - the session's opening context says which.
- ⛔ **`"model_price_update": false` is the switch that stops this plugin talking to the
  internet.** Before this feature it never did. Off, it uses the seed table that ships in
  the repository; the ceiling is still enforced, the numbers simply stop moving.
- ⭐ **The ceiling reaches the agent BEFORE it dispatches.** (The owner's point: a rule an
  agent only meets as a refusal is a rule it routes around.) The session's opening context
  names the permitted families, the refused ones and their prices; rule 7 of the block
  prepended to every sub-task prompt carries the same list, so an agent that dispatches
  further is bound by it too.
- ⛔ **Every price literal is gone from the skill and the prompt template**, leaving the
  rule. ⚠ Keeping them would have moved the drift rather than ended it: the gate refusing
  at one price while the prompt promised another. A check asserts no literal has crept
  back, and that check is itself mutation-checked.
- ⚠ **An unreadable table fails OPEN and is logged** (`MODEL-PRICE-TABLE-MISSING`). With no
  table every model reads as unrecognised and would be refused - and a cost guard that
  bricks the work is a cost guard people uninstall.

---

## 0.31.0

- ⭐ **模型價格改成從 Anthropic 官方定價頁抓，不再手打在原始碼裡。**
  `hooks/model_pricing.py` 解析
  [官方定價頁的 markdown](https://platform.claude.com/docs/en/about-claude/pricing.md)
  產生 `model_pricing.json`，裡面同時有 epoch 和 `YYYY-MM-DD HH:MM:SS`（UTC 與本地各一份）。
- ⛔ **手打的那張表本來就已經錯了，而且沒有任何東西會說。**
  它把 Claude Haiku 3.5 標成每百萬輸入 token $1；公告價是 $0.80。
  那一列不是抄來的，是從 harness 的權重函式推出來的 ——
  ⇒ 這正是「一張沒辦法跟來源對照的表會安靜地飄走」的實例。
- ⛔ **另一條路被否決了，理由是對的。** 先前的做法是去讀已安裝的 Claude Code 執行檔裡的
  `pricing` 欄位。⚠ 沒更新 Claude Code 的機器就會拿到舊目錄的價格 ——
  那不是比較新，只是換一個地方過期。官方頁是唯一不依賴任何本機安裝是否夠新的來源。
- ⛔ **`GET /v1/models` 沒有價格欄位。** 它回傳 `id`、`capabilities`、`created_at`、
  `display_name`、`max_input_tokens`、`max_tokens`、`type`。這不是沒找到，是 API 就沒有。
- ⭐ **背景更新，永遠不阻塞。** 超過 `model_price_hours`（預設 24）gate 會 fork 一個
  detached 子行程；發現過期的那個 session 繼續用手上的表，新數字給下一個 session。
  ⛔ hook 裡絕不做同步 HTTP —— 那會讓每一次工具呼叫都等網路，慢的 proxy 跟當掉的外掛
  從椅子上看起來一模一樣。
- ⛔ **失敗不會清空表。** 抓不到、或抓到 200 但表格改了形狀解析不出來，都保留舊檔。
  最後一次嘗試寫進 `model_pricing.status`，所以「抓了一個月都失敗」不會看起來像
  「本來就不需要抓」—— session 開場的 context 會講。
- ⛔ **`"model_price_update": false` 是「不要連網」的開關。** 這個功能之前，這個外掛從不連網。
  關掉之後用隨儲存庫出貨的種子表，上限照樣執行，只是數字不再變動。
- ⭐ **上限在派工「之前」就告訴 agent。**（owner 的要求：只用 hook 擋，agent 只會想繞過。）
  session 開場的 context 會寫出可以派哪些家族、不可以派哪些、以及目前價格；
  每一份子任務提示詞前面那個區塊的第 7 條帶同一份清單，所以再往下派的 agent 也被綁住。
- ⛔ **skill 和提示詞樣板裡的價格數字全部移除**，只留規則。
  ⚠ 留著就是把飄移換個地方而已：gate 用一個價格拒絕、提示詞卻承諾另一個價格。
  有一項檢查斷言兩邊都沒有再出現價格字面值，而且那個檢查本身有 mutation check。
- ⚠ **讀不到價格表時 fail open 並記 log**（`MODEL-PRICE-TABLE-MISSING`）。
  沒有表的話每個模型都會被判成「不認得」而被拒絕 —— 一個把工作鎖死的成本閘門，
  就是一個會被解除安裝的成本閘門。

---

## 0.22.0

- ⛔ **兩支 skill 沒有都載入，就一律拒絕派工**（`require_skills`，預設兩支都要）。
  `dispatch-protocol` 講一波派工怎麼規劃、怎麼落到硬碟、怎麼配速；
  `unattended-work` 講它怎麼被審、什麼時候可以不問 owner、什麼時候該停。
  兩支都沒載入就派工的 agent，是在沒有規則的情況下工作。
- ⚠ **這一條每一次都拒絕，不是只拒絕一次。** 這是相對於 `guard_unattended_first`
  刻意的加嚴 —— 那一條唸一次就讓路。⭐ 站得住腳的理由：修法永遠在 agent 手上，
  叫一支 skill 就是一次它做得到的工具呼叫。
  而 SessionStart 那一行現在會先指名這兩支，所以那個拒絕不會是驚喜。
- ⛔ **殘餘風險寫出來，不藏起來：** skill 註冊本身壞掉的話，那個 session 就不能派工。
  `require_skills: []` 是逃生口，而它屬於「你」——
  拒絕訊息刻意不告訴 agent 那個鍵，因為一條會講出自己關閉開關的規則就是一條會被關掉的規則。
- ⚠ **兩個開關衝突，解掉而不是忽略：** `announce_unattended_work=false` 的意思是
  「我不要這支 skill」，所以它會把 `unattended-work` 從必要清單裡移除。
  一個開關一個意思。`dispatch-protocol` 沒有這種開關，所以照樣必要。
- ⭐ 一支 skill 不管用哪一種寫法都算載入：`unattended-work`、
  `dispatch-guard:unattended-work`、`apps/web:unattended-work`。
  否則「載入了」會變成取決於它被怎麼打出來。
## 0.24.0

- ⭐ **模型的選擇規則搬進 skill 裡，不再只是派工那一刻的拒絕。**
  owner 的理由是對的：**一條 agent 只在「被拒絕」時才遇到的規則，
  就是一條它會想辦法繞過的規則。** 規則要在它決定之前就在它手上。
  ⇒ `dispatch-protocol` 現在有一節「派工之前就選好模型」，帶價格表、
  `best` = fable 這個陷阱、以及「不寫 `model` 永遠放行」這條安全預設。
  「五種會被拒絕的情況」變成六種。
- ⭐ gate 注入到**每一層**子任務提示詞的區塊也加了同一條（第 7 條）。
  三層之下、沒讀過任何 skill 的 agent 也拿得到，而上限的數字是即時代入的。
- ⭐ **`model_ceiling`（模型名稱）換成 `max_model_price`（數字），預設 5。**
  單位是每百萬「輸入」token 的美元。
  ⛔ 為什麼是數字不是名稱：**名稱會過期，數字不會。**
  `opus` 在 2025 年的意思是 $15，現在是 $5 —— 一個用名稱寫的上限，
  會在某個家族被重新定價的時候安靜地改變它允許什麼，
  而那正是一個成本上限絕對不能做的事。
  ⚠ 模型名稱仍然會被接受並換算，因為那是手會順手打出來的東西。
- ⭐ **對照表在哪裡，現在講清楚了：** `hooks/dispatch_gate.py` 的 `MODEL_PRICES`
  （一個模型一列，抄自出貨目錄的 `pricing` 欄位），
  說明在 `config.example.json` 的 `max_model_price`，
  而 skill 裡有四列摘要。⇒ 出新模型的時候，要更新的就是那張表。
- ⛔ **兩份表會分岔，所以有檢查。** `Tools/Debug/test_guards.py` 會拿 skill 那四列
  去問 gate 真正在用的 `model_price()`，包括「每個家族標示的範圍上限要等於
  那個家族最貴的模型」。⚠ 這一項做過變異驗證：把 skill 裡 opus 的價格改成 8，
  檢查會失敗並印出兩邊的數字。這個 repo 一小時前才修過同一類的文件分岔缺陷。
- ⚠ log 的字樣跟著改：`MODEL-PRICE-LIMIT-OFF` / `-UNKNOWN` / `-CLAMPED`。

## 0.23.2

- ⛔ **0.23.1 的 commit 訊息寫了「這個性質現在有檢查了」，但那個檢查不存在。**
  它是一次一行式的腳本，跑完就消失，沒有進 repo。
  ⇒ 在這個 repo 裡這不是小事：整份 CHANGELOG 最上面那則安全公告講的就是
  「自我檢查全綠、實際上什麼都沒強制」。
  一則永久紀錄聲稱一個已經不存在的檢查，是同一個形狀的錯。
- ⭐ 所以把檢查補成真的：`Tools/Debug/test_guards.py` 的 `case_skill_copies()`。
  它斷言每個 skill 目錄裡 `SKILL.md` 有 frontmatter（`name` 要等於目錄名）、
  而 `SKILL.zh-TW.md` **沒有** frontmatter 並且還在自稱「不是 skill 本身」。
  ⛔ 理由：對照版有 frontmatter 就會在同一個名字下註冊「第二支 skill」——
  正是 0.23.1 重寫第 19 條要禁止的那個重複。
  順便也斷言沒有任何 live skill 還在指向使用者層級的複本。
- ⭐ 這個檢查本身做過變異驗證：把 frontmatter 加回對照版，檢查會失敗並指名原因。
  檢查從 13 項變成 14 項。

## 0.23.1

- ⛔ **`unattended-work` 第 19 條（安裝）講的是「外掛還沒帶這支 skill 之前」的散布方式，
  而且它教使用者去做「現在這個模式明文禁止」的那一件事。**
  2026-08-27 在一台使用中的機器上實測。
  原文要你裝在 `~/.claude/skills/unattended-work/`、
  然後「改版本控制的那一份、部署覆蓋使用者那一份」。
- ⛔ 三句話，三句都已經變成錯的或有害的：
  ⓵ 使用者層級的那一份現在是**重複品** —— 外掛自己就註冊了這支 skill
  （`dispatch-guard:unattended-work`），同一個名字下兩個檔案，
  session 到底載入哪一個從外面看不出來。實測那天兩份除了換行符號以外逐位元組相同，
  而從下一次發布開始就會安靜地分岔。
  ⓶ 「改工作區那一份再 cp 覆蓋」這條路徑**已經不存在**：唯一來源是這個 repo，
  改動透過外掛更新送達，改在任何已安裝複本上都會被安靜覆蓋。
  ⓷ 開場提醒**現在是外掛自己出的**（`hooks/unattended.py`），
  再自己加一個 settings.json hook 只會得到一則逐位元組相同的重複訊息 —— 這也實測過。
- ⭐ 第 19 條重寫：外掛本身就是安裝、禁止第二份複本、改動走上游、
  內建提醒與它的關閉開關（`CLAUDE_PLUGIN_OPTION_ANNOUNCE_UNATTENDED_WORK=false`）。
  ⚠ ACTIVE 確認行那條規則**原封不動保留** —— 沒印出來就等於沒有東西載入它，
  而 hook 有觸發不等於規則有被遵守。沒印出來時的退路也保留：
  去已安裝的外掛路徑讀這個檔案，然後照樣遵守。
- ⭐ 同一個世代的過期文字掃過一遍，而且帶正向對照 ——
  否則「grep 沒中」會被當成「沒問題」。只有這兩份 skill 有問題：
  README 與 CHANGELOG 裡的 `user-level` 講的是 VS Code 的 `tasks.json`，
  跟 skill 散布無關、是正確的，沒有動。
- ⚠ 只改文字。`hooks/*.py` 一行都沒動 —— 提醒機制本來就是對的，過期的只有散文。

## 0.23.0

⭐ **兩個修正，兩個都是 owner 指出來的。**

- ⛔ **`unattended-work` 不再是派工的必要條件。** 0.22.0 把它做成必要，owner 推翻了，
  而理由是對的：**skill 存在的目的是給 agent 一套「做事的方式」，不是用來設閘門**，
  而這個外掛的職責是派工紀律，不是無人職守。
  有人盯著螢幕派子任務的時候，他需要的是 `dispatch-protocol`，
  審查輪次、停滯測試、收尾門檻對他沒有用。
- ⭐ `require_skills` 這個清單換成兩個布林值：
  `require_dispatch_protocol`（預設 **true**）、`require_unattended_work`（預設 **false**）。
  ⇒ 兩支要不要綁在一起，變成一個開關、由你決定。
  ⚠ `require_unattended_work` 關著的時候，`guard_unattended_first` 仍然每個 session
  「唸一次」—— 那是提醒，不是閘門。
- ⛔ **模型計價改用「已公布的資料」，而且改成「每個模型」而不是「每個家族」。**
  來源是出貨的模型目錄裡每一筆的 `pricing` 欄位：`tier_<輸入>_<輸出>`，每百萬 token 美元。
  ⇒ 因為一個家族「不是」一個價格：`claude-opus-4-0` 是 tier_15_75、
  `claude-opus-5` 是 tier_5_25 —— 同一個家族，輸入價差三倍 ——
  而 `claude-sonnet-5`（tier_2_10）比 `claude-sonnet-4-6`（tier_3_15）還便宜。
  ⛔ 家族級的數字把它們當成一樣，於是 `claude-opus-4-0` 會毫無阻礙地通過 `opus` 上限。
- ⛔ **而 `mythos = 10` 那個數字是我「推」的，不是我「讀」到的 —— 這是這次修正的重點。**
  我從 `advisor_rank` 推出來，而這個檔案自己的註解就寫著不可以自己編數字。
  目錄的 `pricing` 欄位一直都在，根本不需要推論。
  ⭐ 那個數字後來證明是對的（`claude-mythos-5` 確實是 tier_10_50），
  而「值是對的」正是讓「方法是錯的」這件事更該修，而不是更可以放過。
- ⭐ 光寫家族別名的時候，用「它實際解出來的那個模型」計價：`opus` = claude-opus-5 = $5，
  來源是目錄的 `latest_per_family`。這張表沒見過的版本（例如 `claude-opus-6`）
  會用它的家族計價，⚠ 而那個假設會記一行 `MODEL-PRICE-ASSUMED`，因為它是這個檢查裡
  唯一一個「推論」而不是「讀數」的地方。
- ⚠ **`[1m]` 後綴被去掉，沒有另外計價**，而這是限制不是決定。
  `opus[1m]` 是一個真的變體（執行檔裡顯示成 "Opus 1M"），
  但目錄一個模型只公布一個 `pricing`，沒有為長 context 變體公布第二個；
  harness 自己的帳也只是把那次請求丟進另一個桶子（`longCtxCost`），沒有乘上任何倍數。
  ⇒ 沒有可用的公布數字，所以這裡不編一個。寫進「做不到的事」那一節。

## 0.22.1

- ⛔ **這條規則底下有一個「從外面測不到」的假設，所以讓它自己會報案。**
  假設是：harness 真的會為 `Skill` 這個工具觸發 PreToolUse / PostToolUse。
  出貨執行檔裡「沒有」豁免清單、「沒有」對 Skill 的特例，派送也是對工具名稱通用的
  （`preToolUseMatcherCoversTool`），而且參考文件寫 `PostToolUse` 是「成功之後」才跑 ——
  所以記在 PostToolUse 是對的，被拒絕的 Skill 呼叫不算載入。⚠ 但「沒有反證」不是證明，
  而萬一是錯的，這條規則會永遠拒絕每一次派工。⇒ 從同一個 session 的**第三次拒絕**開始，
  訊息不再假設是 agent 的錯，而是直接指出另一種可能，兩個管道都講：
  agent 被告知停下來講出來，而螢幕上那行叫你去 `.claude/dispatch-gate.log` 找 `SKILL-SEEN`，
  找不到就設 `require_skills: []`。⭐ 一個不存在的訊號，絕不可以跟「規則正常運作」長得一樣。

## 0.21.1

- ⛔ **九條守衛裡有兩條是「安靜關掉」的。** `guard_unattended_first` 原本是在「呼叫端」
  用那個鍵擋住，所以關掉它不會留下任何一行紀錄；`model_ceiling: null` 也一樣。
  ⇒ 一個不留痕跡的關閉開關，跟「守衛跑過而且什麼都沒發現」在 log 裡長得一模一樣，
  而那正是這裡每一個決定都要寫下來的理由。現在兩者都會記一行
  （`CMD-DISABLED(guard_unattended_first)`、`MODEL-CEILING-OFF`）。
- ⚠ 關掉的時候「不會」寫那個 nag 標記：在沒人在聽的時候把唯一一次拒絕用掉，
  等於之後把守衛打開也永遠不會再觸發。這一點有檢查。

- ⛔ **出貨的 `--selftest` 會把終端機掛住。** `unattended.py` 的 `main()` 會把 stdin 讀乾
  —— 這是對的，hook 的 payload 就是從那裡來，不讀完可能讓寫入端拿到 broken pipe ——
  但它的 selftest 直接呼叫 `main()`，於是 stdin 是終端機的時候，它在等一個
  「終端機永遠不會送出」的檔案結尾。實測：`Tools/Debug/test_all.py` 兩次執行卡在這裡
  超過一小時、螢幕上什麼都沒有，而手動打 `python unattended.py --selftest` 也一樣卡住 ——
  ⛔ 那正是文件教人用來診斷安裝的指令，所以這個掛住是在「出貨的產品」裡，不只在檢查裡。
- ⭐ 三道防線，不是一道：selftest 呼叫 `main()` 之前先換掉 stdin；`test_all.py` 每一個子行程
  都用 `stdin=DEVNULL`；每一項檢查加 180 秒上限，讓「掛住」變成一個看得懂的 FAIL。
  ⚠ 一個永遠不回來的檢查比一個失敗的檢查更糟：結束碼永遠不會到，所以沒有人回報任何事。
- ⭐ 新增一項檢查：每一支出貨的 `--selftest` 都在「stdin 是一個開著、永遠不關的管線」
  的情況下跑一次。那就是閒置終端機的樣子。會掛住的子行程會被殺掉，然後這項檢查 FAIL。

## 0.21.0

- ⭐ **模型上限現在會被 Claude Code 自己的 `availableModels` 允許清單收窄。**
  它是一個「設定鍵」不是 API：讀 managed settings 檔、這個 checkout 的
  settings.local.json 與 settings.json、然後使用者的 settings.json，成本是一次檔案讀取。
  出貨執行檔裡的原文：「Allowlist of models that users can select. Accepts family aliases
  ("opus" allows any opus version), version prefixes, and full model IDs.
  If undefined, all models are available」。
- ⭐ 一個被限制成只能用 sonnet 的帳號，它的 `opus` 上限**就是** sonnet 上限。
  拒絕訊息現在報「有效上限」而不是「設定值」—— 一邊說上限是 `opus`、
  一邊叫你改用 `sonnet`，讀起來像 gate 壞了，而覺得 gate 壞了的 agent 會去繞過它。
- ⛔ **但「不在允許清單裡」本身不會被拒絕。** 那種情況 Claude Code 是安靜替換
  （`Subagent model "…" is not in the availableModels allowlist; using the newest allowed
  model in its family` / `inheriting the parent model`），而每一種替換都是成本往下走：
  成本守衛在那裡沒有東西要保護，而一條建立在別名與版本前綴比對上的拒絕規則遲早會誤殺。
  ⇒ 可用性「收窄上限」，不是第二條規則。
- ⚠ 也沒有去打 `GET /api/claude_cli/bootstrap` 拿 `model_access`：那是第二個端點、
  第二套認證，而 `availableModels` 已經免費給了同一件事。

## 0.20.0

- ⛔ **子代理的模型上限**（`model_ceiling`，預設 `opus`）。gate 在 `PreToolUse` 分支讀
  `tool_input.model`，超過上限就 `permissionDecision: "deny"`，並且指名可以改用哪一個。
- ⭐ **那個排序是從出貨的執行檔裡讀出來的，不是我編的。** Claude Code 自己用
  haiku 1 / sonnet 3 / opus 5 / fable 10 這組權重換算每一筆用量記錄
  （目錄裡的 `advisor_rank` 也同意：haiku-4-5 是 1、sonnet-5 是 3、opus-5 是 4、fable-5 是 5）。
  家族用子字串比對，所以 `claude-sonnet-6` 在它存在那天就會被讀成 sonnet，不用改任何檔案。
- ⛔ **別名先解開，因為 `best` 就是 Fable。** 一個只拒絕 `"fable"` 這個字串的守衛，
  會從 `best` 那裡把 Fable 發出去。`opusplan` → opus，`[1m]` 後綴去掉。
- ⛔ **認不出來的家族是拒絕，不是放行**，而這有實測的理由：目錄裡已經有第五個家族
  `claude-mythos-5`（`advisor_rank` 5，跟 Fable 同級），而 harness 自己那個函式
  把它算成 3 —— Sonnet 的價 —— 所以它會毫無阻礙地通過 `opus` 上限。
- ⚠ **沒寫 model 永遠放行**（繼承你為 session 選的模型），所以這條規則不可能鎖死 session；
  **上限打錯字則 fail open** 並記一行 `MODEL-CEILING-UNKNOWN`。

## 0.19.0

⭐ **第二組守衛：擋「安靜失敗」的指令。** 做錯跟做對在螢幕上長得一模一樣的那種。

- ⛔ 拒絕在**這個 session 沒選過的分支**上 `git commit`（`guard_commit_branch`）。
  分支在 SessionStart 記下來，這個 session 自己 checkout/switch 的時候會重新記，
  然後**每一次 commit** 都跟 git 現在的答案比對 —— 共用工作目錄的時候，
  另一個 session 可以在你兩次 commit 之間把它切走。
  ⛔ 複合指令裡的任何位置都算，因為真實發生的那次是
  `git rev-parse --abbrev-ref HEAD && git add -A && git commit …`：
  `&&` 只問前一個指令有沒有「成功」，從來不問它的答案「能不能接受」。
- ⛔ 拒絕 `git add -A` / `.` / `--all`（`guard_add_all`）、
  `git commit -m`（`guard_commit_message_file`）、
  以及**把錯誤訊息吞掉**的搜尋（`guard_silenced_search`）。
- ⭐ 沒載入 `unattended-work` 就派工，**拒絕一次**（`guard_unattended_first`）。
  0.17.0 讓那個提醒顯示在螢幕上，但 2026-08-27 實測：提醒被整個 session 忽略，
  而且沒有任何東西注意到。⚠ 只拒絕一次 —— 載入器壞掉不可以鎖死 session。
  ⛔ `announce_unattended_work=false` 的時候完全安靜。
- ⚠ `cd <相對路徑> && …` 出警告（`guard_relative_cd`），不拒絕：
  gate 不知道 shell 現在的工作目錄，測不了那個路徑，所以不該拒絕。
- ⚠ `git commit` 之後回報還有更舊的 commit 沒推（`guard_unpushed`）。

⭐ **每一條都可以單獨關掉**，預設全開，而且**故意不合併成一個開關** ——
有人會想要派工閘門但不要 git 閘門。關掉的那條照樣會跑，
所以 log 裡看得到「這個開關讓你少擋了什麼」。
⛔ **全部 fail open**，而且每一個決定都寫進 log（`CMD-DENY` / `CMD-WARN` /
`CMD-ALLOW(checked=… off=…)` / `CMD-DISABLED` / `CMD-GUARD-ERROR`）。
⭐ 新增 `Tools/Debug/test_guards.py`：每一條守衛都是**從 `main()` 灌真實 payload 進去**驗的，
而且都做過**變異檢查** —— 把那條守衛從表裡刪掉，同一個 payload 再灌一次，
拒絕必須消失。0.4.0–0.6.0 就是「只測決策函式、沒測接線」而整段死掉的。
檢查從 5 項變成 6 項。

## 0.18.0

- ⭐ gate 注入到**每一層**子任務提示詞的那段規則加了第 7 條：暫存檔案放在
  `<task_root>/<task>/scratch/<你的子任務>/`，而且**不要刪**。
  0.17.0 把這件事寫進兩支 skill，但 skill 只約束讀過的 agent；
  這段規則連三層之下、兩支 skill 都沒載入的 agent 也約束得到。
  ⚠ 這是**指令，不是強制**：gate 檔得住工具呼叫，檔不住所有形式的刪除。
- ⛔ `test_resume_cancel.py` 原本斷言 `.claude/dispatch-gate.log`【不存在】，
  但要問的是【這次測試有沒有寫】—— 真的 session 在這個 repo 工作時，
  plugin 本來就會寫進那個檔。現在比對前後大小。

## 0.17.0

- ⭐ `dispatch-protocol` 補上**暫存檔案**規範：子任務寫的每一個中間檔案都放在
  `<task_root>/<task>/scratch/<NN-代理或用途>/`，跑完留著，路徑要寫在提示詞裡。
  ⛔ 兩個 agent 被告知「找個暫存的地方」會挑到同一個位置，第二個清掉第一個的證據 ——
  這在這個 repo 自己的檢查程式上實測到過。
- ⛔ `unattended-work` 第 2 條要求「計畫先落到硬碟」卻**沒說放哪裡**。agent 會把正確的計畫
  寫在 gate 看不到的地方，然後派工被拒絕、而拒絕訊息指的是它沒用過的路徑。現在指向
  `dispatch-protocol` 並寫明最低要求。
- ⭐ `unattended-work` 的開場提醒現在也**顯示在使用者畫面上**（`systemMessage`），
  並指名要看的那一行。⚠ 在這之前它只是純文字 stdout，只到得了模型 ——
  「skill 載入了」和「hook 沒跑」從畫面上分不出來。

## 0.16.2

- ⭐ 三支檢查程式搬到 `Tools/Debug/`，而且**產生的每一個檔案都關在 `Tools/Debug/scratch/`**
  （相對路徑、已 gitignore、跑完不刪，所以檢查失敗時它寫了什麼還在那裡）。
  ⛔ 跑完之後 `git status` 必須乾淨 —— 那本身就是「測試沒寫到外面」的檢查，
  而這件事有兩次前科：一次寫進工作樹，一次寫進 `~/.claude`。
- ⚠ 每個子行程原本都會清空 scratch，把前一支的證據刪掉。改成由 `test_all.py` 準備一次，
  並依檢查名稱分開命名目錄。

## 0.16.1

- ⛔ `test_resume_cancel.py` 用**這個 repo 當工作目錄**呼叫 `do_cancel()`，
  而 `log_line()` 會寫 `<cwd>/.claude/dispatch-gate.log` —— 於是每跑一次測試就在工作樹裡
  留下外掛自己的 log。⚠ 那跟「開發複本正在被執行」長得一模一樣，
  是一個正在確認安裝的人最不能看到的東西。
- ⚠ PROTOCOL.md 瘦身之後，README 兩處還說「規範本身寫在 PROTOCOL.md」，而那個檔案自己說
  規則在 `skills/dispatch-protocol/SKILL.md`。兩處都改成描述這個分工。

## 0.16.0

- ⛔ **effort 是 `ultracode` 時，每一個工具呼叫都被拒絕。** `max` 或更低才能繼續。
  ultracode 是「xhigh ＋ 動態 workflow 編排」，而 workflow 一次生出很多 agent —— 這個 gate
  本來就直接拒絕。⚠ 它不是「建議」一次，是**每一輪重新下達**，所以只警告一次的 session
  會持續為一個一定被拒絕的東西燒規劃 token。⭐ effort 只出現在 tool-use 的 payload 裡
  （執行檔 schema 寫的），而 `PreToolUse` 也正好是唯一能拒絕的地方。
- ⛔ `hard_pct`、`colour_alarm_pct` 90 → **85**。90 還在派工，結果撞到 session limit 被終止。
- ⭐ GO / PACE / STOP 那個字跟長條同色，而且後面補兩個空格 —— `--watch` 原地重寫時，
  游標會停在最後一個字上，把 GO 的 O 蓋成一個方框。
- ⚠ `Ctx` 的數字前面從兩個空格改成一個，跟 5h、7d 一致（兩個空格是**段落之間**的分隔）。
  多出來的那一格改由長條吸收，欄位仍然對齊。
- ⭐ 兩個 skill 都補上 `SKILL.zh-TW.md` 正體中文對照。

## 0.15.0

- ⭐ **預設值改成 `soft_pct` 70 / `hard_pct` 90**，跟 `colour_warn_pct` 70、`colour_alarm_pct` 90 對齊。
  橘色 = PACE 開始，紅色 = STOP 開始。⚠ 仍然是四個獨立設定值，沒有合併。
- ⛔ 這讓兩句已經寫下的說明變成錯的，兩句都改了：「顏色門檻故意設在拒絕門檻之前」（現在是相等），
  以及今天稍早寫的「90% 落在中間所以是 PACE」（現在 90% 就是 STOP）。
- ⭐ README 寫清楚那則畫面訊息的觸發方式：`UserPromptSubmit` 事件、依 `limits.json` 的百分比、
  每個 session 每個等級**只送一次**（記錄在 `state/<session-id>.warned`），等級改變才重新武裝。

## 0.14.0

- ⭐ **煞車現在會說給「人」聽。** hook 的 `systemMessage` 直接顯示在使用者畫面上（出自執行檔的參考文件：
  「Display a message to the user (all hooks)」）。PACE / STOP 各一則，派工被拒絕時也有一則。
  ⛔ 在這之前所有訊息都只進到**模型的 context** —— 於是「它繼續工作」和「它根本沒收到」長得一模一樣。
- ⭐ 進入 PACE / STOP 時，agent 被要求原封不動印出一行 `PACE at 90% - winding down`。
  ⚠ 那不證明它照做（提示詞證明不了任何事），但它分開了「收到卻繼續」和「從來沒收到」。
- ⚠ 文件講明：**90% 預設不是煞車**。`soft_pct` 85 是 PACE，`hard_pct` 93 才是 STOP。

## 0.13.2

- ⭐ README 兩半新增：安裝後重開 VS Code 會跳出的 **Allow** 通知（原文照引），以及找回它的三種方法。
  ⚠ 那個通知會自己淡掉，而錯過它的後果是「工作在、Run Task 看得到、但永遠不自動跑」。
- ⭐ 也寫進去：`claude plugin update` 之後那個絕對路徑會自己修好，不用重跑任何東西。實測並加了檢查。

## 0.13.1

- ⛔ 「允許自動工作」那個授權沒跟著搬。VS Code 用**通知**問這件事，而通知會自己淡掉 ——
  於是工作寫好了、Run Task 看得到、但永遠不會自動跑。授權現在跟著寫入一起做。
- ⛔ 使用者層級的指令被縮寫成 `${workspaceFolder}/…`。使用者層級的工作**沒有自己的 workspace**，
  那個變數會對著「當下開的專案」解析 —— 在每個專案都是錯的，包括寫出它的那一個。改成永遠用絕對路徑。

## 0.13.0

- ⭐ **watcher 工作搬到 VS Code 的「使用者層級」`tasks.json`：寫一次，每個專案都有，零重開循環，
  而且不再往任何人的 repo 寫檔案。**
  ⛔ 每個專案一份的做法在「第一次開」永遠不會成立：檔案是由 session 寫出的，而 session 在資料夾
  開啟**之後**才啟動 —— 所以**每一個新專案**的第一次開啟都沒有工作，不是每台機器一次。
  ⚠ 官方文件只說使用者層級的工作限於 `shell` 和 `process`，沒說 `runOn: folderOpen` 能不能用。
  ⭐ 2026-08-27 實測：可以。終端機在下一次開啟資料夾時自己跳出來，Run Task 也看得到。
- ⭐ 舊版留下的專案內工作會被移除（它是我們的，留著會開出**第二個一模一樣**的終端機）。
  ⛔ 被 git 追蹤時不動它，只告訴你。
- ⛔ selftest 曾經在「測試」時寫到真實的 `%APPDATA%/Code/User/tasks.json`。已隔離，並實測改動前後 md5 相同。

## 0.12.0

- ⛔ **種子 config.json 會「釘住」每一個值，所以 0.11.0 的新預設到不了任何已安裝的機器。**
  0.9.0 起 `seed_config()` 照抄範例檔，包含所有值；明確寫下的值永遠贏過程式預設值。
  ⇒ 現在只種**說明**，不種值：每個 `_` 開頭的解釋都留著，真正的 key 一個都不寫。
  ⭐ 加一個 key 變成刻意的決定，不再是「你剛好哪一天安裝」的意外。
- ⭐ `--status` 新增 `pinned settings`：列出你 config.json 裡跟預設值不同的每一個 key。
  ⛔ 在這之前，從外面完全看不出「更新了、預設變了、卻什麼都沒發生」是為什麼。
- ⚠ **已經安裝過的機器不會被改寫**（種子檔從不覆蓋）。跑 `--status` 看自己釘住了什麼。

## 0.11.0

- ⭐ `auto_vscode_task` **預設改成開**。⛔ 關著的時候這個功能是找不到的：hook 唯一的管道是
  SessionStart 訊息，而那是進到**模型的 context**、不是你的螢幕 —— 兩次全新安裝實測，工作都沒出現。
  ⇒ 保護改放在**衝突判定**（被 git 追蹤、解析不了）上，不是放在一個把功能藏起來的預設值。
  「問一次」那整套連同它的標記檔一起刪掉了：關掉它是一個決定，不是每個 session 重問一次的問題。
- ⛔ `test_all.py` 印失敗內容時會自己崩潰（cp950）。報告工具在報告時死掉，比沒有報告更糟。

## 0.10.0

- ⭐ 多帶一個 skill：`unattended-work` —— 沒人看著的時候怎麼工作。
- ⭐ 新的 `userConfig` 選項 `announce_unattended_work`（預設開）。⛔ 它關不掉 hook —— 外掛的 hook
  一定會觸發 —— 關掉的是那個 hook **印什麼**。⚠ 看不懂的值當作「開」：安靜消失的提醒比多餘的提醒糟。

## 0.9.4

- ⛔ 移除會**建立**檔案：從一個本來就沒有 `tasks.json` 的專案移除工作，會寫出一個空的。
  清空一台機器時，每個碰過的 repo 都被留下一個 `.vscode/` 目錄。

## 0.9.3

- ⛔ `auto_vscode_task` 的詢問**只問一次就永久消失**，即使沒有人看到那一次。標記是在回答**之前**寫的，
  而那句話是進到模型的 context、不是進到螢幕；session 結束或 agent 沒照做，這個功能就再也發現不了。
  改成記「問過幾次」，最多三次；⭐ 真的回答了（`--enable-auto-task` / `--disable-auto-task`）就立刻停止。

## 0.9.2

- `Memory/tasks/` 不再進 git，那裡曾經夾帶 80 KB 的審閱報告出貨。
- 新增 `test_all.py`：一個指令跑完四項檢查。

## 0.9.1

- 新增 CHANGELOG.md。README 和 PROTOCOL 不再記錄版本歷史。
- ⛔ 修好 README.md 裡兩個 NUL 位元組，git 原本已經把它當二進位檔。

## 0.9.0

- `~/.claude/dispatch-guard/config.json` 會自動建立，內容是 `config.example.json`。已存在絕不覆蓋。
- `config.example.json` 原本把 `dispatch.task_root` 釘成一個路徑，程式預設是 `null`（自動挑）。已改回 `null`。
- README、PROTOCOL 全面對照程式碼校正，包含上面那則公告的版本範圍。

## 0.8.0

- `--watch` 在沒有任何 session 活動超過 `idle_after_min`（預設 15 分）之後**停止呼叫 API**，但**繼續重畫**那一行。
- `Ctx` 從 session 第一秒就顯示，讀 0%。payload 裡沒有那個欄位時畫 `--`，永遠不是 `0%`。
- 三段長條共用一個 `BAR_WIDTH`，從 6 加寬到 9。狀態列因此從約 75 欄變成約 87 欄。
- README 的範例行拆成 `--statusline` 和 `--watch` 兩個，加上每一段的來源對照表。

## 0.7.2

- 取消預約的 resume 現在分得出三種結果：沒有註冊、刪除成功、排程拒絕。之前後兩種被混在一起。

## 0.7.1

- `statusline_install()` 也不再覆蓋一個讀不出來的 `settings.json`。
- `--uninstall` 之後 gate 不再宣稱「不會有東西醒來重做」，除非排程真的答應了。

## 0.7.0

- ⛔ 修好上面那則公告的 `NameError`。自我檢查改成呼叫真正的函式。
- 讀不出來的 JSON 檔案（帶註解的 `tasks.json`、多一個逗號的 `settings.json`）不再被覆蓋。
- 狀態列的擁有權判定收緊：要同時有 `usage.py` 和 `--statusline` 才算我們的。
- 移除會把 `auto_statusline` 一起關掉，否則下一個 session 就把狀態列裝回去。

## 0.6.0

- 狀態列在那個位置沒人佔的時候自動裝好。
- `auto_vscode_task` 由 hook 主動問一次，並新增 `--enable-auto-task` / `--disable-auto-task`。
- 修好一個已存在的 VS Code 工作**不需要**同意；建立新的才需要。

## 0.5.1 / 0.5.0

- 指向舊版本的狀態列會自己修回來。
- `auto_vscode_task`：hook 可以自己把 watcher 工作寫進專案，預設關閉。

## 0.4.1 / 0.4.0

- gate 自己 fork 一個背景刷新，所以煞車不再需要狀態列或 watcher。⚠ **但見上面的公告：這在 0.7.0 之前是壞的。**
- 用量低於 1% 的視窗不再被丟掉。之前 7d 整段會消失，5h 會凍在 0%。

## 0.3.0

- 完整的移除流程，`/dispatch-guard:uninstall`。

## 0.2.2 / 0.2.1 / 0.2.0

- 斜線指令 `/dispatch-guard:install` 和 `/dispatch-guard:status`。
- 重跑安裝會修好指向舊版本的狀態列路徑。
- 安裝步驟改成一段自己找路徑的腳本。

## 0.1.0

- 第一版。

---

<a id="changelog-english"></a>

> 🇬🇧 **English (this section)** ｜ 🇹🇼 **[正體中文](#版本紀錄)**

# Changelog

⭐ **README.md and PROTOCOL.md describe the present only.** When something changed, and why,
lives here. The full reasoning is in each commit message; `git log` is the authority.

---

## ⛔ Advisory — 0.4.0 through 0.6.0 enforce nothing

**Affected:** 0.4.0, 0.4.1, 0.5.0, 0.5.1, 0.6.0. **Fixed in 0.7.0.**

In those five, `keep_clock_running()` used an unbound name. The `NameError` escaped from the
line that runs BEFORE every event branch in `main()`, and the top-level handler exits 0 and
prints nothing — ⛔ **a hook that prints nothing has APPROVED the call.**

⇒ The session was never stamped, so the gate spent the rest of it on the advisory branch: a
dispatch at STOP was allowed, a background dispatch was not refused, and the plan check did
not run. All three self-checks stayed green, because they exercised the decision function and
never called the real one.

**To tell whether you were affected**, look for this line in `.claude/dispatch-gate.log` or
`%TEMP%\dispatch-gate-error.log`:

```
GATE-ERROR NameError("name 'now' is not defined")
```

**The fix:** update to 0.7.0 or later, then open a new session.

---

## 0.22.0

- ⛔ **Every dispatch is refused until BOTH skills have been invoked** (`require_skills`,
  defaulting to both). `dispatch-protocol` is how a wave is planned, laid out on disk and
  paced; `unattended-work` is how it is reviewed, when to proceed without the owner, and when
  to stop. An agent dispatching with neither loaded is working without the rules.
- ⚠ **This one refuses EVERY time, not once** - a deliberate escalation from
  `guard_unattended_first`, which nags once and stands aside. ⭐ What makes it defensible: the
  fix is always available to the agent, because invoking a skill is a tool call it can make -
  and the SessionStart line now names both skills, so the refusal is never a surprise.
- ⛔ **The residual risk is stated rather than hidden:** if the skill registry itself is
  broken, that session cannot dispatch at all. `require_skills: []` is the escape hatch and it
  belongs to the OWNER - the refusal deliberately does not name that key, because a rule that
  names its own off switch is a rule that gets switched off.
- ⚠ **A conflict between two switches, resolved rather than ignored:**
  `announce_unattended_work=false` means "I do not want this skill", so it REMOVES
  `unattended-work` from the required list. One meaning per switch. `dispatch-protocol` has no
  such switch and stays required.
- ⭐ A skill counts as loaded under any spelling - `unattended-work`,
  `dispatch-guard:unattended-work`, `apps/web:unattended-work` - because otherwise "loaded"
  would depend on how it was typed.
## 0.24.0

- ⭐ **The model-choice rule moved INTO the skill, instead of being only a refusal at dispatch
  time.** The owner's reasoning is right: **a rule an agent only ever meets as a refusal is a
  rule it tries to route around.** It has to be in the agent's hands before it decides.
  ⇒ `dispatch-protocol` now opens with "Choose the model BEFORE you dispatch", carrying the
  price table, the `best` = fable trap, and the safe default that omitting `model` is always
  allowed. "The five refusals" became six.
- ⭐ The block the gate injects into **every** sub-task prompt carries the same rule (rule 7),
  so an agent three levels down that read no skill still gets it - with the current limit
  interpolated rather than hardcoded.
- ⭐ **`model_ceiling` (a model name) became `max_model_price` (a number), default 5** - US
  dollars per million INPUT tokens. ⛔ Why a number: **a name goes stale and a number does
  not.** `opus` meant $15 in 2025 and means $5 now, so a limit written as a name silently
  changes what it permits when a family is repriced - the one thing a cost limit must never
  do. ⚠ A model name is still accepted and priced, because it is what a hand reaches for.
- ⭐ **Where the table is, said out loud:** `MODEL_PRICES` in `hooks/dispatch_gate.py` (one row
  per model, copied from the shipped catalog's `pricing` field), documented under
  `max_model_price` in `config.example.json`, with a four-row summary in the skill. ⇒ When a
  new model ships, that table is what gets updated.
- ⛔ **Two copies of a number can drift, so there is a check.** `Tools/Debug/test_guards.py`
  puts the skill's four rows through `model_price()` - the function the gate actually decides
  with - including that each family's stated range tops out at its dearest model. ⚠ It is
  mutation-verified: change opus to $8 in the skill and the check fails, printing both numbers.
  This repository fixed the same class of documentation drift an hour earlier.
- ⚠ The log lines follow: `MODEL-PRICE-LIMIT-OFF` / `-UNKNOWN` / `-CLAMPED`.

## 0.23.2

- ⛔ **0.23.1's commit message claimed "that property is now checked rather than assumed", and
  the check did not exist.** It was a one-off inline script: it ran once and evaporated,
  and never entered the repository. ⇒ In this repository that is not a nitpick - the advisory
  at the top of this file is about self-checks staying green while nothing was enforced. A
  permanent record asserting a check that is not there is the same shape.
- ⭐ So the check is now real: `case_skill_copies()` in `Tools/Debug/test_guards.py`. Per skill
  directory it asserts that `SKILL.md` carries frontmatter whose `name` matches its directory,
  and that `SKILL.zh-TW.md` carries NONE and still declares itself a reading copy.
  ⛔ Why: frontmatter in the reading copy would register a SECOND skill under the same base
  name - the exact duplicate 0.23.1 rewrote §19 to forbid. It also asserts that no live skill
  still points at a user-level copy.
- ⭐ The check is mutation-verified: put the frontmatter back into the reading copy and it
  fails, naming the reason. 13 cases became 14.

## 0.23.1

- ⛔ **`unattended-work` §19 (Install) described the pre-plugin distribution model, and
  actively instructed the one thing the current model forbids.** Measured 2026-08-27 on a
  consuming machine. It told the reader to install at `~/.claude/skills/unattended-work/` and
  to "edit the version-controlled workshop copy, then deploy it over the user copy".
- ⛔ Three sentences, all three now wrong or harmful:
  ⓵ a user-level copy is now a DUPLICATE - the plugin registers the skill itself
  (`dispatch-guard:unattended-work`), so two files compete under one name and which one a
  session loaded is invisible. The two were byte-identical apart from line endings the day
  they were compared, and would have drifted from the next release onward.
  ⓶ the workshop-copy-then-cp path NO LONGER EXISTS: the single source is this repository,
  edits arrive by plugin update, and an edit to any installed copy is silently overwritten.
  ⓷ the session-start reminder IS the plugin own hook (`hooks/unattended.py`), so a
  hand-added settings.json hook produces a byte-identical double message - also measured.
- ⭐ §19 rewritten: the plugin is the install, no second copy, edits upstream, the built-in
  reminder and its off switch (`CLAUDE_PLUGIN_OPTION_ANNOUNCE_UNATTENDED_WORK=false`).
  ⚠ The ACTIVE confirmation-line rule is kept UNCHANGED - no line printed means nothing
  loaded it, and a hook that fired is not a rule that was followed. So is the fallback: if
  the line did not print, read the file under the installed plugin path and follow it anyway.
- ⭐ Swept for the same era of stale text, with a positive control so an empty grep could not
  pass as a clean bill of health. Only the two skill copies were affected: the `user-level`
  hits in README.md and CHANGELOG.md are VS Code `tasks.json`, which is correct and
  unrelated, and were left alone.
- ⚠ Prose only. No line of `hooks/*.py` changed - the reminder mechanism was already right.

## 0.23.0

⭐ **Two corrections, both of them the owner's.**

- ⛔ **`unattended-work` is no longer a precondition for dispatching.** 0.22.0 made it one and
  the owner reversed it, for the right reason: **a skill exists to give an agent a WAY OF
  WORKING, not to gate it**, and this plugin's job is dispatch discipline rather than
  unattended operation. Somebody dispatching sub-tasks while watching the screen needs
  `dispatch-protocol` and has no use for the review rounds, the stall test or the exit bar.
- ⭐ The `require_skills` list becomes two booleans: `require_dispatch_protocol` (default
  **true**) and `require_unattended_work` (default **false**). ⇒ Whether the two must travel
  together is one switch, and it is yours. ⚠ While `require_unattended_work` is off,
  `guard_unattended_first` still asks for the skill once per session - a nag, not a gate.
- ⛔ **Model pricing now uses PUBLISHED DATA, and prices per MODEL rather than per family.**
  The source is the `pricing` field on each entry of the shipped model catalog:
  `tier_<input>_<output>`, US dollars per million tokens. ⇒ Because a family is NOT one price:
  `claude-opus-4-0` is tier_15_75 and `claude-opus-5` is tier_5_25 - same family, three times
  the input price - and `claude-sonnet-5` (tier_2_10) is cheaper than `claude-sonnet-4-6`
  (tier_3_15). ⛔ A family-level number called those equal, so `claude-opus-4-0` passed an
  `opus` ceiling untouched.
- ⛔ **And `mythos = 10` was a number I REASONED to, not one I read - which is the point of
  this correction.** I derived it from `advisor_rank`, in a file whose own comments say not to
  invent numbers. The catalog's `pricing` field was there the whole time and needed no
  reasoning at all. ⭐ The value turned out to be right (`claude-mythos-5` IS tier_10_50), and
  that is exactly what makes the METHOD the thing to fix rather than something to let pass.
- ⭐ A bare family alias is priced as the model it actually resolves to - `opus` =
  claude-opus-5 = $5 - from the catalog's `latest_per_family`. A version this table has never
  seen (`claude-opus-6`) is priced through its family, ⚠ and that assumption is logged as
  `MODEL-PRICE-ASSUMED`, because it is the one place in this check that is an inference rather
  than a reading.
- ⚠ **The `[1m]` suffix is stripped and not charged for**, and that is a limit rather than a
  decision. `opus[1m]` is a real variant - the binary displays it as "Opus 1M" - but the
  catalog publishes one `pricing` tier per model and none for the long-context variant, and
  the harness's own accounting only puts that request in a separate bucket (`longCtxCost`)
  without multiplying its price. ⇒ There is no published number to use, so this gate invents
  none. It is in the honest-gaps table.

## 0.22.1

- ⛔ **The one assumption under this rule that cannot be measured from outside now REPORTS
  ITSELF.** The assumption: that the harness fires PreToolUse/PostToolUse for the `Skill`
  tool. The shipped binary has no exemption list, no special case for Skill, and a dispatch
  generic over the tool name (`preToolUseMatcherCoversTool`) - and the reference states
  `PostToolUse` runs after a SUCCESSFUL tool, which confirms that recording on POST is right
  and that a declined Skill call correctly does not count. ⚠ But "no evidence against" is not
  proof, and if it were wrong this rule would refuse every dispatch for ever. ⇒ From the THIRD
  refusal in a session the message stops assuming the agent is at fault and names the other
  possibility, on both channels: the agent is told to stop and say so, and the screen line
  points at `.claude/dispatch-gate.log` for a `SKILL-SEEN` line and at `require_skills: []` if
  there is none. ⭐ An absent signal must never look identical to a working one.

## 0.21.1

- ⛔ **Two of the nine guards switched off SILENTLY.** `guard_unattended_first` gated the
  CALL on its key, so turning it off left no log line at all, and `model_ceiling: null` did
  the same. ⇒ An off switch that leaves no trace is indistinguishable from a guard that ran
  and found nothing, which is the whole reason every decision here is written down. Both log
  now (`CMD-DISABLED(guard_unattended_first)`, `MODEL-CEILING-OFF`).
- ⚠ And when it is off the nag mark is NOT written: spending the one refusal while nobody was
  listening would mean switching the guard back on never fires it. Checked.

- ⛔ **A shipped `--selftest` hung the terminal.** `unattended.py`'s `main()` drains stdin -
  correctly, because that is where a hook payload arrives and an unread pipe can break the
  writer - but its selftest called `main()`, so with a terminal on stdin it waited for an end
  of file a terminal never sends. Measured: two runs of `Tools/Debug/test_all.py` sat on it
  for over an hour printing nothing, and `python unattended.py --selftest` typed by hand hung
  the same way. ⛔ That is the documented way to diagnose an install, so the hang was in the
  shipped product and not only in the checks.
- ⭐ Three defences, not one: the selftest replaces stdin before calling `main()`;
  `test_all.py` gives every child `stdin=DEVNULL`; and each check gets a 180 s ceiling so a
  hang becomes a legible FAIL. ⚠ A check that never returns is worse than one that fails - the
  exit code never arrives, so nothing reports anything.
- ⭐ New check: every shipped `--selftest` runs once with an OPEN, never-closed stdin pipe,
  which is what an idle terminal looks like. A child that blocks is killed and the case fails.

## 0.21.0

- ⭐ **The model ceiling is now narrowed by Claude Code's own `availableModels` allowlist.**
  It is a SETTINGS key, not an API: the managed settings file, then this checkout's
  settings.local.json and settings.json, then the user's settings.json - one file read.
  Verbatim from the shipped binary: "Allowlist of models that users can select. Accepts family
  aliases (\"opus\" allows any opus version), version prefixes, and full model IDs. If
  undefined, all models are available".
- ⭐ On an account restricted to sonnet, an `opus` ceiling **is** a sonnet ceiling. The
  refusal now reports the EFFECTIVE ceiling rather than the configured one - naming `opus` as
  the ceiling while advising `sonnet` reads as a bug in the gate, and an agent that believes
  the gate is broken works around it instead of complying.
- ⛔ **But being outside the allowlist is not refused by itself.** There Claude Code
  substitutes silently (`Subagent model "…" is not in the availableModels allowlist; using the
  newest allowed model in its family` / `inheriting the parent model`), and every one of those
  substitutions is a step DOWN in cost - nothing for a cost guard to protect, while a refusal
  built on alias-and-version-prefix matching would eventually refuse legal work.
  ⇒ Availability tightens the ceiling; it is not a second rule.
- ⚠ `GET /api/claude_cli/bootstrap` and its `model_access` entitlement are deliberately NOT
  called: a second endpoint with its own auth, for a list `availableModels` already gives away.
- ⭐ The allowlist is read from a REAL settings file in the checks, not injected. The gate's
  own selftest passes `avail=` straight in, which tests the decision and not the wiring - and
  a decision function that is right while nothing calls it is how 0.4.0 shipped.

## 0.20.0

- ⛔ **A model ceiling for sub-agents** (`model_ceiling`, default `opus`). The gate reads
  `tool_input.model` in its `PreToolUse` branch and answers
  `permissionDecision: "deny"` above the ceiling, naming what to use instead.
- ⭐ **The ordering was read out of the shipped binary, not invented here.** Claude Code
  prices every usage record with haiku 1 / sonnet 3 / opus 5 / fable 10, and its catalog's
  capability field agrees (`advisor_rank`: 1 for haiku-4-5, 3 for sonnet-5, 4 for opus-5, 5
  for fable-5). Families match as substrings, so `claude-sonnet-6` reads as sonnet on the day
  it exists, with no file to edit.
- ⛔ **Aliases resolve first, because `best` IS Fable.** A guard that refused the literal
  string `"fable"` would hand out Fable through `best`. `opusplan` resolves to opus, and a
  `[1m]` suffix is stripped.
- ⛔ **An unrecognised family is refused rather than allowed**, and the reason is measured:
  the catalog already holds a fifth family, `claude-mythos-5` (`advisor_rank` 5, like Fable),
  and the harness's own weight function scores it 3 — Sonnet's price — so it would pass an
  `opus` ceiling untouched.
- ⚠ **An omitted model is always allowed** (it inherits the model you chose for the session),
  so this can never deadlock a session; **a mistyped ceiling fails OPEN** and logs
  `MODEL-CEILING-UNKNOWN`.

## 0.19.0

⭐ **A second family of guards: commands that fail SILENTLY** - where the wrong outcome and
the right one are byte-identical on screen.

- ⛔ A `git commit` on a **branch this session did not select** is refused
  (`guard_commit_branch`). The branch is recorded at SessionStart, re-recorded whenever this
  session itself runs checkout/switch, and compared against git's answer **on every commit** -
  in a shared working tree another session can check out between two of your commits.
  ⛔ Matched anywhere in a compound command, because the measured failure was
  `git rev-parse --abbrev-ref HEAD && git add -A && git commit …`: `&&` asks only whether the
  previous command SUCCEEDED, never whether its answer was ACCEPTABLE.
- ⛔ `git add -A` / `.` / `--all` refused (`guard_add_all`), `git commit -m` refused
  (`guard_commit_message_file`), and a search with its errors silenced refused
  (`guard_silenced_search`).
- ⭐ The **first** dispatch is refused when `unattended-work` was never invoked
  (`guard_unattended_first`). 0.17.0 put that reminder on the screen; measured 2026-08-27, the
  reminder was ignored for an entire session and nothing noticed. ⚠ Once only - a skill loader
  that breaks must not deadlock the session. ⛔ Silent when
  `announce_unattended_work=false`.
- ⚠ `cd <relative> && …` warns rather than refuses (`guard_relative_cd`): the gate does not
  know the shell's persistent working directory, so it cannot test the path - and it does not
  refuse what it cannot test.
- ⚠ Unpushed commits older than the one just made are reported after a `git commit`
  (`guard_unpushed`).

⭐ **Every guard has its own switch**, all default to on, and they are deliberately NOT one
shared switch - somebody will want the dispatch gate without the git gate. A disabled guard
still runs, so the log says what the off switch cost.
⛔ **All of them fail open**, and every decision is logged (`CMD-DENY` / `CMD-WARN` /
`CMD-ALLOW(checked=… off=…)` / `CMD-DISABLED` / `CMD-GUARD-ERROR`).
⭐ New `Tools/Debug/test_guards.py`: every guard is driven **through `main()` with real
payload bytes**, and every one is **mutation-checked** - delete it from the table, drive the
same payload again, and the refusal must disappear. 0.4.0-0.6.0 shipped dead precisely because
the checks exercised the decision functions and never the wiring. 5 checks became 6.

## 0.18.0

- ⭐ Rule 7 in the block the gate injects into **every** sub-task prompt, at every depth:
  scratch files go under `<task_root>/<task>/scratch/<your-subtask>/`, and **you do not delete
  them**. 0.17.0 put this in both skills, but a skill only binds an agent that read it; this
  block binds an agent three levels down that loaded neither. ⚠ It is an **instruction, not
  enforcement** - the gate refuses tool calls, and no practical rule refuses every form of
  deletion.
- ⛔ `test_resume_cancel.py` asserted that `.claude/dispatch-gate.log` does not EXIST, when
  the question is whether the TEST wrote it - that file is where the plugin legitimately logs
  when a real session works in this repository. It compares the size before and after now.

## 0.17.0

- ⭐ `dispatch-protocol` gained a **scratch files** rule: every intermediate file a sub-task
  writes goes under `<task_root>/<task>/scratch/<NN-agent-or-purpose>/`, stays there after the
  run, and the path belongs in the prompt. ⛔ Two agents told "somewhere temporary" pick the
  same place, and the second wipes the evidence of the first - measured on this repository's
  own check scripts.
- ⛔ `unattended-work` §2 required the plan on disk and never said WHERE. An agent writes a
  perfectly good plan somewhere the gate cannot see, the dispatch is refused, and the refusal
  names a path the agent never used. It defers to `dispatch-protocol` now and states the
  minimum.
- ⭐ The `unattended-work` opening reminder now **reaches the screen of the person**
  (`systemMessage`) and names the line to look for. ⚠ Before this it was plain stdout, which
  only reaches the model - "the skill loaded" and "the hook never ran" looked identical.

## 0.16.2

- ⭐ The three check scripts moved to `Tools/Debug/`, and **every file they produce is
  confined to `Tools/Debug/scratch/`** — relative paths, gitignored, and kept after the run so
  a failing check's output is still there. ⛔ A run must leave `git status` clean; that is
  itself the check that the tests stayed in their sandbox, and it has two precedents: once
  into the working tree, once into `~/.claude`.
- ⚠ Each child process used to wipe the scratch directory and take the previous child's
  evidence with it. `test_all.py` prepares it once now, and directories are namespaced by
  check.

## 0.16.1

- ⛔ `test_resume_cancel.py` called `do_cancel()` with the REPOSITORY as its working
  directory, and `log_line()` appends to `<cwd>/.claude/dispatch-gate.log` — so every run left
  the plugin's own log in the working tree. ⚠ That is indistinguishable from the development
  copy being executed, which is the one thing somebody checking their install must be able to
  rule out.
- ⚠ After PROTOCOL.md was slimmed down, both README halves still said "the rules themselves
  are in PROTOCOL.md", which that file now contradicts. Both describe the split now.

## 0.16.0

- ⛔ **Every tool call is refused while effort is `ultracode`.** max or lower proceeds.
  Ultracode is xhigh PLUS dynamic workflow orchestration, and a workflow spawns many agents
  at once - which this gate refuses outright. ⚠ It does not SUGGEST that once; it re-states
  it every turn, so warning once leaves a session burning planning tokens on something that
  will be denied. ⭐ `effort` appears only on the tool-use payload (per the shipped schema),
  and `PreToolUse` is also the only place a call can be denied.
- ⛔ `hard_pct` and `colour_alarm_pct` 90 → **85**, after a dispatch at 90 hit a session limit
  and was killed.
- ⭐ The GO / PACE / STOP word takes the bar's colour, and ends with two spaces: `--watch`
  rewrites in place, so the cursor sat on the last character and drew a box over the O of GO.
- ⚠ `Ctx` used two spaces before its number; two spaces is the separator BETWEEN segments, so
  it is one now, like 5h and 7d. The bar absorbs the extra cell, so the columns still align.
- ⭐ Both skills gained a `SKILL.zh-TW.md` reading copy.

## 0.15.0

- ⭐ **Defaults are now `soft_pct` 70 / `hard_pct` 90**, aligned with `colour_warn_pct` 70 and
  `colour_alarm_pct` 90: orange is where PACE begins, red is where STOP begins. ⚠ Still four
  separate keys, not merged.
- ⛔ That made two written claims false, and both are corrected: "the colour thresholds are
  deliberately before the ones that refuse anything" (they are equal now) and "90% falls
  between them, so it is PACE" (90% IS the STOP now).
- ⭐ The README now says what triggers the on-screen message: the `UserPromptSubmit` event, the
  percentage in `limits.json`, and once per level per session - recorded in
  `state/<session-id>.warned`, re-armed only when the level changes.

## 0.14.0

- ⭐ **The brake speaks to the PERSON now.** A hook's `systemMessage` is displayed on the
  user's screen (quoted from the shipped reference: "Display a message to the user (all
  hooks)"). One at PACE, one at STOP, one when a dispatch is refused. ⛔ Everything used to go
  only into the MODEL's context, where "it carried on" and "it never heard" look identical.
- ⭐ Entering PACE or STOP demands one exact line from the agent:
  `PACE at 90% - winding down`. ⚠ Not proof of obedience - nothing in a prompt is - but it
  separates "heard it and continued" from "never received it".
- ⚠ Documented: **90% is not the brake by default.** soft_pct 85 is PACE; hard_pct 93 is STOP.

## 0.13.2

- ⭐ Both README halves gained the **Allow** notification VS Code shows after an install,
  quoted verbatim, plus three ways to get it back. ⚠ It fades, and missing it leaves the task
  installed and listed while never starting on folder open.
- ⭐ Documented too: `claude plugin update` repairs the stored absolute path by itself, with
  nothing to re-run. Measured, and pinned by a selftest case.

## 0.13.1

- ⛔ The automatic-tasks permission did not travel with the task. VS Code asks for it with a
  NOTIFICATION, which fades - so the task was written, Run Task listed it, and it never ran.
  The grant now happens on the write.
- ⛔ The user-level command was shortened to `${workspaceFolder}/…`. A user-level task has NO
  workspace of its own, so that resolves against whatever project is open - wrong in every
  project, including the one it was written from. Absolute paths always, now.

## 0.13.0

- ⭐ **The watcher task moved to VS Code's USER-level `tasks.json`: written once, covers every
  project, no per-project reopen cycle, and nothing is placed in anybody's repository.**
  ⛔ The per-project file could never work on a first open: it is created by a session, and a
  session starts AFTER the folder is open - so the first open of every NEW project had no
  task, not once per machine but once per project.
  ⚠ The documentation says only that user-level tasks are limited to `shell` and `process`,
  and says nothing about `runOn: folderOpen`. ⭐ Measured 2026-08-27: it works. The terminal
  opened on the next folder open and the task appeared in Run Task.
- ⭐ A per-project task left by an earlier version is removed - it is ours, and leaving it
  would open a SECOND identical terminal. ⛔ Not when it is tracked by git; then it is only
  reported.
- ⛔ The selftest wrote to the REAL `%APPDATA%/Code/User/tasks.json` while "testing". Isolated,
  and the md5 is now verified unchanged across a run.

## 0.12.0

- ⛔ **The seeded config.json PINNED every value, so 0.11.0's new default could not reach a
  single installed machine.** Since 0.9.0 `seed_config()` copied the example verbatim, values
  included, and an explicit value always beats a code default. ⇒ It seeds the DOCUMENTATION
  only now: every `_`-prefixed explanation is kept and not one real key is written. ⭐ Adding
  a key becomes a deliberate pin rather than an accident of the day you installed.
- ⭐ `--status` gained a `pinned settings` line listing every key in your config.json that
  differs from the default. ⛔ Before it, "the update landed, the default moved, nothing
  happened" was invisible from outside.
- ⚠ Machines already seeded are NOT rewritten - the seed never overwrites. Run `--status` to
  see what you have pinned.

## 0.11.0

- ⭐ `auto_vscode_task` now defaults to **on**. ⛔ Off, the feature was undiscoverable: the
  hook's only channel was a SessionStart message, which reaches a MODEL's context rather than
  your screen — measured on two clean installs where the task never appeared and nothing said
  why. ⇒ The protection moved to the CONFLICT tests (tracked by git, unparseable) instead of a
  default that hid the feature. The ask-once machinery and its marker file are gone: switching
  it off is a decision, not a question to re-open every session.
- ⛔ `test_all.py` crashed while PRINTING a failure on a cp950 console. A reporter that dies
  while reporting is worse than none: the exit code says "failed" and the reason is gone.

## 0.10.0

- ⭐ A second skill ships with the plugin: `unattended-work`, how to work with nobody watching.
- ⭐ New `userConfig` option `announce_unattended_work` (default on). ⛔ It cannot disable the
  hook — a plugin's hooks always fire — so what it switches off is what the hook PRINTS.
  ⚠ An unrecognised value counts as ON: a reminder that silently stops is worse than a
  redundant one.

## 0.9.4

- ⛔ An uninstall CREATED a file: removing the task from a project that never had a
  `tasks.json` wrote a new empty one, so clearing a machine down left a `.vscode/` directory
  in every repository it touched.

## 0.9.3

- ⛔ The `auto_vscode_task` offer was spent by a single unseen message. The mark was written
  BEFORE the answer, and the message reaches a model's context rather than a screen — so a
  session that ended, or an agent that did not act on it, retired the feature for good. It
  counts misses now, up to three; ⭐ an actual answer (`--enable-auto-task` /
  `--disable-auto-task`) retires it immediately.

## 0.9.2

- `Memory/tasks/` is no longer tracked; it had shipped 80 KB of review reports.
- `test_all.py` runs all four checks with one command.

## 0.9.1

- CHANGELOG.md added. README and PROTOCOL no longer carry version history.
- ⛔ Two NUL bytes repaired in README.md; git had begun treating it as a binary file.

## 0.9.0

- `~/.claude/dispatch-guard/config.json` is created for you, from `config.example.json`. An
  existing file is never overwritten.
- `config.example.json` pinned `dispatch.task_root` to a path while the code default is
  `null`, meaning "choose automatically". Shipped as `null` now.
- README and PROTOCOL audited against the code, including the version range above.

## 0.8.0

- `--watch` **stops calling the API** after `idle_after_min` (default 15) with no session
  activity, and **keeps redrawing** the line.
- `Ctx` is drawn from the first second of a session, reading 0%. A payload with no such field
  draws `--`, never `0%`.
- All three bars share one `BAR_WIDTH`, widened from 6 to 9. The statusline goes from about
  75 to about 87 columns.
- The README example line became two, one per interface, plus a table of where each segment
  comes from.

## 0.7.2

- Cancelling an armed resume distinguishes three outcomes: not registered, deleted, and
  refused by the scheduler. The last two used to be merged.

## 0.7.1

- `statusline_install()` no longer overwrites a `settings.json` it cannot read either.
- After `--uninstall` the gate no longer claims nothing will wake later unless the scheduler
  actually agreed.

## 0.7.0

- ⛔ Fixes the `NameError` in the advisory above. The self-check now calls the real function.
- JSON files that cannot be read — a commented `tasks.json`, a `settings.json` with a
  trailing comma — are no longer overwritten.
- Statusline ownership tightened: it must contain both `usage.py` and `--statusline`.
- Uninstalling also switches `auto_statusline` off, or the next session put the line back.

## 0.6.0

- The statusline is adopted when nothing owns that slot.
- `auto_vscode_task` is offered by the hook, once, plus `--enable-auto-task` /
  `--disable-auto-task`.
- Repairing an existing VS Code task needs no agreement; creating one still does.

## 0.5.1 / 0.5.0

- A statusline pointing at an older version repairs itself.
- `auto_vscode_task`: the hook can write the watcher task into a project. Off by default.

## 0.4.1 / 0.4.0

- The gate forks its own background refresh, so the brake needs no statusline and no watcher.
  ⚠ **But see the advisory above: this did not work before 0.7.0.**
- A window below 1% is no longer discarded. The 7d segment used to vanish and 5h used to
  freeze at 0%.

## 0.3.0

- A complete uninstall, and `/dispatch-guard:uninstall`.

## 0.2.2 / 0.2.1 / 0.2.0

- The slash commands `/dispatch-guard:install` and `/dispatch-guard:status`.
- Re-running the installer repairs a statusline path left pointing at an older version.
- The install step became a script that finds its own path.

## 0.1.0

- First release.
