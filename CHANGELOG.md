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

## 0.65.0

cowork：第二次跨機搬遷（一個專案從舊機搬到新機，最後共 9 個 session 參與）由觀察者角色逐筆記錄的教訓。
兩項是 **0.64.2 自己出的錯**，其餘是新規則；另附一支監看工具。

- ⛔ **〔修 0.64.2〕唯一穩定的身分是擁有者指派的「角色」。** 0.64.2 說「`[ref]`／session id 是唯一穩定的鍵」、報到檔用
  session id 命名 —— 錯了：runtime 名字幾分鐘就換且會被回收；名字旁的 `[ref]` 也會變（同一個 agent 認領時一個 session id、
  後來清單上是另一個 `[ref]`；傳訊工具自己的說明也寫「不是剛從清單或錯誤讀到的 ref 不會解析」）；接手的 session 會拿到新
  session id。⇒ 報到檔改為 `checkin/<角色>.md`，runtime 名字、`[ref]`、session id 都是持有者每次重開就重寫的欄位；要找某個
  角色：讀它的報到檔 → 在即時清單找到那個名字 → 傳給它（`coordination.md` 2.1／2.8／2.9）。交接期間同一角色兩個人
  （舊機 S3、新機 S3）改用 `S3-old`／`S3-new`，直到舊的正式退役。
- ⛔ **〔修 0.64.2〕代號不用 `@`。** 0.64.2 要代號加 `@` 前綴；但 `@` 是傳訊工具的 team 語法（`name@team`），送往 `@MIG`
  在查找之前就被拒（`to must be a bare teammate name`），錯誤樣式跟「找不到」不同，花了三次嘗試才分辨出來。代號只用英數字，
  而且**永遠不拿來當傳送地址**。
- ⭐ **等同伴不等於停下來（`cross-machine.md` 1.8、規則 13、`unattended-work` §15）。** session 回合之間什麼都不跑、也沒有東西
  會叫醒它：「我在等」寫完就睡著了。實測一方 11:45 說在等，一直睡到 13:31 主人轉達「開始」。⇒ 停下來等同伴之前先設喚醒：
  同機用傳訊工具的 `notify_when_idle`，跨機用新附的 **`skills/cowork/tools/watch-folder.ps1`**（背景執行，資料夾一有變動就結束
  並叫醒你）；板子只貼**一行**等待。採用後實測：一方做完，另一方約 50 秒自己醒來接手，中間沒有人。
  ⛔ 第二半是踩出來的：第一版寫「停下前要貼等待行」，被照字面解讀成每次醒來都貼，9 個 session 互相吵醒（每兩分鐘 4～5 行
  空轉）。⇒ **醒來沒你的事就什麼都不寫**；監看排除自己和觀察者的檔。等「主人」則照舊乾淨停下。
- **權限要在第一次複製「之前」、在目的地「根目錄」處理（`cross-machine.md` 1.6、2.3）。** 同一個缺陷兩天內出現三次，每次只修
  出事的資料夾。經管理共享建立的檔對其他帳號是唯讀的，就算對方能新建檔也一樣 —— 建立者要在建立的同一步用 SID 授權。
- **目的地防毒會在完美複製之後刪檔（2.3b）**：寫入測試 40/40、位元組全對，幾分鐘後防毒開始隔離證據檔，另有 30 個同類檔在風險中。
  搬證據／樣本前先比對排除設定；幾分鐘後再數一次檔。**目的地 agent 不要在目的地樹裡啟動（2.3c）。**
- **雙重編碼的 UTF-8 會通過控制字元掃描（4.2）**：主人原話轉到板子上變成一串帶重音的拉丁字母，沒有任何控制字元。加一道
  雙重編碼特徵檢查；轉述的原話一定讀回核對。
- **通道搬家只在新位置公告**，看舊位置的一方永遠不會醒（`coordination.md` 3.9）⇒ 在舊位置公告、持續監看到大家確認。
- 其他新節：`coordination.md` 3.14 發 WAITING 或說誰在／不在之前先重讀板子（兩小時內三次）；3.15 中途採用的規則立刻寫進
  通道常駐檔（後來加入的三個 session 都沒拿到）；3.16 主人給的規則明顯有害時，各方回報一次、照舊遵守，只有主人或寫規則的人能改；
  3.17 主人在 session 之間手動傳話＝通道少一個檔；3.18 觀察者角色：可貼「FYI」（量到、確定會卡住的阻礙），並記錄誰讀過觀察檔。
  `cross-machine.md` 1.3（只開放目標共用時的通道位置）、1.7（開頭貼一次兩邊時鐘，時間一律取自 `date`）、3.4（凍結要寫明誰顧停掉的監控）。
- 失效形狀多六列（等著等著睡著、喚醒風暴、通道搬了家、後來加入的人、到了又被刪），兩列改寫（名字被回收、名字撞名），
  「無聲的文字損壞」加上雙重編碼。中英同步。
- `watch-folder.ps1`：pwsh 7 版本守衛（5.1 會以序列化參數重新交給 pwsh 7；沒裝 pwsh 7 就拒絕並說明怎麼裝）；
  `-Ignore "a,b"` 逗號分隔；一律建議 `-WindowStyle Hidden`，避免視窗跳出被誤關。實測：觸發、被排除不觸發、5.1 路徑、資料夾不存在。
- 對抗式審查（sonnet）一次：1 個 BLOCKING（「名字被回收」那列仍是舊模型，中英皆然）已修，1 個 NON-BLOCKING 已修。

---

## 0.64.2

cowork：**名字會被回收**，以及主人提的**報到板**（改成一人一檔）。

- ⛔ **名字被回收比名字過期更危險。** 實測：同一個 runtime 名字六天前屬於一個角色、今天屬於另一個；
  有 session 8 分鐘就改名、另一個 20 分鐘改三次。過期的名字送不到、會報錯；**被回收的名字送得到 ——
  送到另一個 session，沒有任何錯誤。** 原本 2.1「去查活的清單」在這種情況下正好送錯。另外清單裡有一個
  不相干、離線的 session 名字就叫 `S4`，用裸代號找人會找到陌生人。
- ⭐ **報到檔（`coordination.md` 2.8）**：固定的共用目錄、**一人一檔、以 session id 命名**、只有本人覆寫。
  記代號、目前 runtime 名稱（僅供人看）、`[ref]`／session id（唯一穩定的鍵）、機器／repo、報到與最後確認
  時間。主人原本提的是單一可修改的報到板；改成一人一檔，是因為實測過兩個 session 幾分鐘內先後改同一份
  名冊、只靠 Edit 的寫入檢查剛好擋住 —— 一人一檔就沒有競爭，跟內容「一人一檔」同一個原則。
- ⭐ **代號由主人給，session 要回報怎麼稱呼它**：「收到，我的代號是 S4，以後請用 @S4 稱呼我」，並寫進報到檔。
  代號一律**加前綴**（`@S4`），不跟 runtime 名字撞。
- **2.9 用 id 定址**：傳訊息用 `[ref]`／session id；重要訊息送出前確認名字仍對應到對方報到檔上的 id。
- 規則 2 改寫為「先報到、只登記自己、用 id 定址」；2.4「幾小時內」改為實測的「幾分鐘內」；失效形狀多兩列
  （名字被回收、名字撞名）。中英同步。
- 未做：hook 閘門（第一次寫入前檢查本 session 有沒有報到檔）—— 記在 PENDING，等主人決定。

---

## 0.64.1

⛔ **0.64.0 的 cowork 在每個 session 裡都不存在。** 它的 description 寫著
`The trigger is the SITUATION, never the wording: use it …` —— YAML 純量值裡的「冒號＋空格」是映射符號，
整段 frontmatter 因此是無效 YAML，Claude Code 就**靜默丟掉這支 skill**：2026-09-23 量到巢狀 session 的
技能清單 127 個，有 `dispatch-protocol` 和 `unattended-work`，**沒有 `cowork`**，`plugin_warnings` 是 null。
模型甚至自己去 Grep／Glob 找 cowork 的檔 —— 它想要，但清單裡沒有。

- 修：`wording: use` → `wording. Use`。
- ⭐ **新閘門 `Tools/Debug/test_skill_frontmatter.py`（`test_all.py` 第 14 項）**：每一支 `skills/*/SKILL.md`
  都要有能被解析的 frontmatter、`name` 等於目錄名、`description` 非空。有 PyYAML 就用它，沒有就用嚴格的
  fallback（純量值含 `: ` 或 ` #`、或以指示字元開頭就拒絕）。陽性對照：0.64.0 那一行必須被拒、修正版必須
  被接受 —— 兩條路徑都驗過，且對已安裝的 0.64.0 副本實跑會紅。
- ⚠ **為什麼 0.64.0 的檢查全綠還是出事**：中英對齊、控制字元、識別碼、整套測試都過了，因為沒有一項用
  載入器讀檔的方式讀它。0.64.0 那節寫的「正例 4/5」量的是合成 skill 旁邊**舊的 0.63.2 cowork**，不是
  0.64.0 —— 那個數字對 0.64.0 不成立。

---

## 0.64.0

cowork 第一次跨機協作（舊機 ↔ 新機搬專案，2026-09-22）留下的教訓，加上主人同日的三個裁決。

- ⭐ **第 13 條規則，與新參考檔 `skills/cowork/reference/cross-machine.md`。** 這支 skill 原本沒有任何
  跨機器內容 —— UNC、SMB、「另一台機器」全文零命中，標題自己寫著「一棵工作樹」。那次協作最貴的一課：
  溝通板由舊機經管理共享建立，權限跟著建立者，新機**讀得到、寫不進去**；協定要它追加一段並改「球在誰
  那邊」，兩件都做不到；舊機每 20 秒輪詢，永遠看到沒變化，讀成「對方還沒開始」。**雙方都沒收到任何錯誤，
  雙方的行為都正確**，最後是主人手動修權限。⇒ 第 13 條：依賴一條管道之前先證明**寫得進去**、兩個方向
  分開量；跨機複製後第一個檢查是「我能不能寫」，不是雜湊 —— 一棵位元正確卻不可寫的樹會讓後面每一步各自
  失敗、讀起來像五個 bug。參考檔四部：管道、送達卻不能用、兩棵活樹、四個在搬家時說謊的儀器（遵守
  gitignore 的搜尋看不見一次性腳本、heredoc 把反斜線減半成看不見的控制字元、陽性對照在印出乾淨結果之後
  才崩、字元清單檢查量到定義它的那一行），加結尾檢查清單。失效形狀表多七列（無聲死鎖、單向管道、到了卻
  不能用、看不見被忽略的那一區、無聲的文字損壞、陽性對照沒跑到……），中英同步。
- ⛔ **兩層，不是一份板子。** 主人指出「各寫各的、不寫同一個板子」是先前另一個專案就有的原則，跨機經驗
  只能「加入」不能「取代」。對照那個專案 agent 們的原始紀錄：他們的 `CLAIMS.md` 就是**一份** append-only
  認領板（＝`coordination.md` 3.1），內容則是**一人一檔** `contrib/<Sn>-…md` —— 而且實測過：共同產物
  `SKILL.md` 遺失，`contrib/` 一字未損。cowork 只寫了認領板那層。現在 3.1 補上內容層與那次教訓；
  `cross-machine.md` 1.1／1.5／1.6／清單改成兩層 —— 板子跨機要先過寫入測試、寫不進板子就用自己的檔說話、
  讀者掃目錄；1:1／1:N／N:1／N:N 不改變本質。第一次搬家那份帶球權欄位的單一板子記為**權宜**，不是協定。
- ⭐ **description 改成「情境觸發」，不看字眼。** 主人：robocopy、交接、context 快用完是症狀，不是觸發
  用語；觸發條件＝同一個 repo 不只一個 session（同時或接續）、不只一台機器、跨 repo、跨專案、主人對多個
  session 轉述同一件事。實測（25 條正體中文查詢、合成 skill、sonnet、依序前景）：正例 4/5 載入 cowork
  —— 基線漏掉的跨機開場與複製後檢查現在會載，新增的跨 repo／跨專案兩題也會；最硬的近似負例（兩台機器設
  ssh、本機 `FETCH_HEAD` 權限錯誤、每晚鏡像腳本）**0 誤觸發**。唯一漏題「兩個 agent 同題草稿、我同時叫了
  它們」走去 `dispatch-protocol` —— 可辯護的讀法。⚠ 量測方法自己兩個坑，記在
  `Memory/tasks/20260922-212000-cowork-trigger-evals/`：巢狀 `claude -p` 載的是**已安裝的 plugin 副本**、
  不是工作樹（第一次重測因此無效）；skill-creator 的 `run_eval.py` 在 Windows 上對 pipe 做 `select()`
  一秒內炸掉並記成未觸發，且只認自己臨時建的名字、真的已安裝 skill 被載入也算未觸發。
- ⚠ **hook 章節補一句：`guard_cowork_first` 只看得到同一台機器的 peer。** 它讀的心跳是本機狀態目錄裡的
  檔，另一台機器的 session 永遠不算 peer。跨機任務**沒有任何東西會提醒你**，站在那裡的只有第 13 條。
  `PROTOCOL.md` §4 同步兩列。
- **`usage.py --selftest` 每天 23:33–00:00 會失敗。** 斷言寫「5h 括號永不帶星期，因為到不了明天」——
  19:00 之後開的視窗都在明天重設。2026-09-22 23:48 量到夾具（now＋1600 秒）渲染成 `(Wed 00:14)`，
  `test_all.py` 11/13。期望改為與渲染器同一種曆日比對，加三個**固定時間**釘住（週二 23:48 ＋26 分 →
  `(Wed 00:14)`；週三 00:20 ＋26 分 → `(00:46)`；週二 23:48 ＋5h → `(Wed 04:48)`），docstring 那句一起改。
  突變檢查在副本上強迫 `same_day=True` → 斷言會叫。渲染器沒動。
- README：cowork 段更新 —— 十三條、31 列失效形狀、六個參考檔、「一棵工作樹，或兩台機器」。

---

## 0.63.2

主人 2026-09-21 對 `Memory/PENDING.md` 五個項目的裁決，其中三個是程式碼：

- ⛔ **`SPENT in ~N min` 那一句的 ⛔ 跟著判定字走，而且年輕的視窗不印。** 到 0.63.1 為止，只要
  `burnout_min` 小於剩餘分鐘，那句就帶著 ⛔ 和「Plan for the gap」印出來 —— 在 **GO** 的那一行、
  「Headroom available」旁邊也一樣。2026-09-14 量到 sessions 在 20–27% 就照它收工；2026-09-19 重量，
  10% 在開窗 10 和 20 分鐘印 `SPENT in ~90 min`、45 和 90 分鐘不印 —— 餘裕最大的時候叫得最響。
  現在：GO 印 `ℹ … would be SPENT in ~N min … That figure only sizes the NEXT block; GO stands`；
  PACE／STOP 才印 ⛔ 和那句命令；視窗開了不到 `burn_note_min_age_min`（新鍵，預設 **30** 分鐘）什麼
  都不印。⚠ selftest 的強制釘子（把 `burnout_min` 強制成 1、47% 仍是 GO 且句子要在）維持 —— 拿掉的是
  符號和命令，不是句子。新增四個釘子：GO 沒有 ⛔、PACE 有、20 分鐘的年輕視窗沉默、鍵設 0 就印。
  ⛔ 審查 01 在初稿抓到兩個錯，都在出貨前修掉：年齡門的變數蓋掉了「資料年齡」的 `age_min`，新鮮資料
  在開了 55 分鐘的視窗印出 `[data 55 min old]`、40 分鐘舊的資料在年輕視窗反而沉默（改名
  `window_age_min`）；符號跟的是 5h 的等級而不是印出來的字，5h 55% + 7d 96% 的 **PACE** 行以
  「GO stands」結尾（句子移到 `level` 選定之後才組）。各加一根釘子，突變殺得掉。
- ⭐ **`guard_agent_report_file` 不再把 shell 範例當成要建立的報告。** 反引號裡的 `.md` 若緊接在
  `>`／`>>`／`| tee` 之後，或所在的反引號段含 `>` 或 `|`（`cat new.md | tee board.md`），就不算。
  2026-09-19 的誤報：審查提示詞裡 `(vi) \`echo x >> board.md\`` 被報成「從未建立」。對 35 份真實工作單
  量前後：58 個路徑一個都沒掉、沒有新增、誤報那一段 OLD 抓到 NEW 不抓（`scratch/B-measure/`）。
  ⛔ 初稿接受光桿的 `|`，審查 01 量到它把 markdown **表格欄**裡的真報告
  （`| write | \`adr-review-01-adversarial.md\` |`）當成管線目標丟掉；現在 `|` 後面一定要有 `tee`，
  `->` 箭頭的 `>` 也不算重導。三根新釘子。
  ⚠ 整檔量測看不到那個誤報，因為 `demanded_files` 每份提示詞最多回 8 個路徑，那份已有 8 個真報告。
- ⭐ **cowork nag 的證據行。** `guard_cowork_first` 拒絕前先記一行 `COWORK-PEERS sid=<sid8> mine=<s>
  <sid8>:alive=<s>,start=<s> …`；`peer_sessions()` 回三元組（多了 peer 的起始年齡）；`SKILL-SEEN` 行
  也帶 `sid=`。新工具 `Tools/Debug/cowork_nag_report.py`（有 `--selftest`，進 `test_all`）從 state log
  讀回每一次觸發，判 GHOST（peer 的心跳比這個 session 還舊 —— 從我開始它就沒動過）和 LOADED（**同一個
  session** 在 300 秒內載入 skill，用 sid 配對）。⛔ 初稿只靠時間配對，審查 01 量到兩個 session 相隔一秒
  觸發、一次載入算成 2/2 —— state log 是整台機器共用的一個檔。沒有 sid 的舊行退回時間配對，該列會標明。
  主人大多在別的專案工作，資料自己累積，要看就跑那支。第一筆：2026-09-21 16:44，peer 是重開前的
  自己（UNCONFIRMED），23 秒後載入。
- **`unattended-work` §11 加一行指標**指向 `skills/cowork/reference/verification.md` Part 3（另外三道
  對照、partition control、門檻校準、折行假 0）。方向：plugin 是正本，user-scope 的
  `VERIFICATION-LESSONS.md` 指進來 —— 主人問「沒裝 dev-workstation 就少三條？」，答案是不能讓 plugin
  依賴 user scope；`~/.claude/CLAUDE.md` 早已宣告 dispatch-guard 是 required dependency。
- **`PROTOCOL.md` 拿掉 `delegated` 狀態**（主人撤回「拿去別的帳號跑」那整個流程；那個狀態從來沒有
  東西會產生它）。dev-workstation 那邊的片段同日修。

---

## 0.63.1

⛔ **第四位審查者（主人核准的第四輪，`code-review-D-fourth.md`）在 0.63.0 出貨後找到一個阻擋。**
`Rename-Item board/BOARD.md -NewName old.md` 和 `Move-Item board/BOARD.md -Destination old.md` ——
這兩個 cmdlet 最常見的寫法，位置路徑加具名參數 —— 被**放行**：`_ps_path` 回「具名值**或**位置參數」，
一旦有任何參數具名，位置來源就被丟掉；而五份規格都寫這兩個 cmdlet 會拒。現在跟 `mv` 分支一樣，
每個非旗標 token 都算。

另外四個非阻擋一起修：（D2）C-c1 只修了一半 —— 錨點原始位元組只出現一次、但那一次是**前面**的一行
（檔尾那行重複了文字卻少了換行），工具會插進檔案中間；現在要求那一次出現必須在檔尾。（D3）只認第一個
`cd`，`cd board && cd .. && echo x > BOARD.md` 對 `board/BOARD.md` 誤拒；現在每個開頭的 cd 依序套用。
（D4）`CD`、`Set-Location`、`sl`、`chdir`、`pushd` 沒被認得；現在不分大小寫、都認。（D7）以 `# 註解`
開頭的 frontmatter 不再被跳過，那行註解變成「第一個標題」—— 兩個方向都錯；現在先跳過空行和註解行再找
`key:`。（D9）C-b1 的「釘住測試」用的是 `cd "board"`（沒有空格），舊正規式本來就抓得到，等於沒釘；
改成 `cd "board/board dir"`。文件：`PROTOCOL.md` §3/§4 三列改寫（D3/D5/D8/D11/D14）、SKILL.md 兩種語言
「放行的 Edit 是最後**一則**不是最後一行」（D12）、「`cd` 取代目錄」（D13）、0.63.0 條目裡殘留的「14 種」
（D15）。`case_append_only` 拒絕形狀 23 → 29，放行加三個 PowerShell 對照。

⛔ **而且 gate 自己在這一輪抓到 D 沒抓到的一個：** 修 D12 時，裝好的 0.63.0 hook **拒絕了**對
`skills/cowork/SKILL.zh-TW.md` 的 Edit —— 它把那個檔判成 append-only，因為第 3 條在前 2 KB 內用反引號
提到 `<!-- append-only -->`。一份**描述**標記的文件不是帶標記的紀錄。現在 HTML 註解要**獨佔一行**才算；
行內引用不算。這正是 ADR R1 寫的觸發條件，第一天就發生了。那兩個 zh-TW 編輯是用 Python 腳本逐位元組
取代完成的（`PROTOCOL.md` §4 記載的缺口，hook 跑的是安裝快取不是工作樹），commit 訊息講明。
⚠ D 的修正沒有第五輪。

---

## 0.63.0

⭐ **第三個 skill：`cowork`** —— 幾個 session 共用一棵工作樹、替同一個主人工作的規則。由四個
session 在 2026-09-19 一個晚上寫成，每一條規則都在寫它的那一小時裡被寫的人違反過至少一次；
整併進這個外掛的 ADR 走了兩輪對抗審查（第一輪 REJECT、四個阻擋；第二輪 ACCEPT、0 阻擋），紀錄在
`Memory/tasks/20260919-204317-cowork-skill-and-hooks/`。

- `skills/cowork/SKILL.md`（入口：十二條規則、24 列失效形狀目錄、hook 強制什麼）、`SKILL.zh-TW.md`
  （給人讀的對照）、`reference/` 五個英文檔。⛔ **一條規則只有一份正本**：已經在 `unattended-work`
  §9／§10／§11／§12 或 `dispatch-protocol` 的，cowork 只指過去、不重述；而且只指向 plugin 裡出貨的
  檔案，絕不指向只有某台機器才有的 user-scope 檔（第一輪抓到兩處指向 `~/.claude/CLAUDE.md`）。
  `test_guards.py` 新增 `case_cowork_restates_nothing`：相似度掃描（門檻 0.25，正負對照同跑）
  加**正規化標題比對** —— 因為第一版合併留下一節與 `unattended-work` §9 標題一字不差、相似度卻只有
  0.167，單靠分數看不到。兩個突變都殺掉。
- ⭐ **兩條規則變成閘門**（`hooks/cmd_guards.py`，`dispatch_gate.py` 的 `main()` 多一個檔案工具分支）：
  - **`guard_append_only`** —— 第一個標題含 `append-only`（或帶 `<!-- append-only -->`）的檔案只能
    變大。`Write` 要以現有內容開頭；`Edit` 的 `old_string` 要在檔尾、`new_string` 要以它開頭、對前面
    也出現過的錨點設 `replace_all` 會被拒；shell 的 `> path`、`sed -i`、無 `-a` 的 `tee`、`rm`、
    `truncate`、`cp`/`mv` 蓋到它、`Set-Content`、無 `-Append` 的 `Out-File`、`Clear-Content`、
    `Remove-Item` 都拒。⛔ **標記看「第一個標題」，不看正文** —— 掃過 21 979 個檔實測，寬鬆規則會
    把 skill 自己的 SKILL.md 和提出它的 ADR 都鎖成只能追加。展不開的 token（`$VAR`、萬用字元）記成
    `CMD-ALLOW(guard_append_only unresolved)` 放行 —— 命名成 CMD-ALLOW 是刻意的，terminal 隔離那個
    檢查只放行這個字首。
  - **`guard_cowork_first`** —— 同一個 repo 裡另一個 session 的 `.alive` 比 `peer_alive_min`（15
    分鐘，新鍵）新，而這個 session 沒叫過 `cowork`，第一次 `Write`／`Edit`／`git commit` 拒絕一次。
    peer 的根用 `normcase` 比 —— 118 個真實 `.start` 檔裡有 3 個磁碟代號大寫，其中兩個在同一個
    repo，不折大小寫它們彼此看不見。子 agent 帶父層 id，永遠不算 peer。六個性質與
    `guard_unattended_first` 相同：一次、有標記、關閉會記 `CMD-DISABLED` 且不花掉那一次、skill 叫過
    就安靜、沒蓋章只提醒。
  - 兩個都 fail open、每個決定進 log、各有開關。`case_append_only`（出貨時 14 種 shell 形狀拒、11 種放行；
    審查後增為 29 種，見 0.63.1、
    LF/CRLF 附加、`replace_all`、MultiEdit、fail-open、關閉、兩表都拆掉的突變）與 `case_cowork_first`
    （別的 repo／過期心跳／skill 已叫都安靜；磁碟代號反大小寫仍算 peer；commit 也觸發；拿掉 peer
    的突變）。
- ⛔ **`g_commit_branch` 的拒絕訊息少了一句。** 到 0.62.0 它結尾寫「each one needs its own
  worktree」—— 跟主人的規則（「no worktree workaround」）和旁邊出貨的 cowork（「不要給每個 session
  自己的一份」）相反。一個 plugin 兩套對的規則，正是 cowork 目錄裡那個失效形狀。刪掉那一句，
  `case_branch` 釘住。`PROTOCOL.md` §4 同一句話的另一份（「give each a worktree」）一併改掉。
- `config.example.json` 三個新鍵（雙語註解）；`PROTOCOL.md` §3 兩列、§4 四列誠實缺口；README 兩種
  語言各一節。
- ⛔ **發佈前的兩位審查者各找到一個阻擋，都在 0.63.0 出貨前修掉**（`code-review-A-guards.md`、
  `code-review-B-content.md`）。A：`_REDIRECT` 對**帶空格的引號路徑**永遠不命中 —— 引號存在的唯一
  理由就是空格，所以 `echo x > "board dir/BOARD.md"` 帶著 CMD-ALLOW 把紀錄截斷了；改成三個交替式。
  順帶修：同一條指令開頭的 `cd x &&` 也納入路徑解析；重複出現的錨點**不論有沒有** `replace_all`
  都拒（工具本來就要求唯一，所以不會多拒任何工具做得到的 Edit）；`Set-Content -Value x file`
  看得到了；`mv` 的**來源**也算移除；讀不到的檔記 `CMD-ALLOW(guard_append_only unreadable)` 而不是
  裝成沒標記；YAML frontmatter 裡的 `# 註解` 不算第一個標題。B：去重時掉了「substring match 不是
  token match」這一句 —— 它唯一的另一份在 user-scope，正是 ADR 說要留在 cowork 的情況；補回。
  順帶修：8.1 指向一個 `dispatch-protocol` 沒寫的規則（改指 `require_handoff_past_soft`）、8.2 少了
  兩項、8.5 重述了 PACE/STOP、verification.md 在指向 §9 的那句裡又重述了 §9。測試補強：拒絕的 shell
  形狀（14 → 23 種）現在連**拒絕理由**一起斷言（只斷言 `deny` 的話別的 guard 也能讓它綠），放行的形狀
  斷言 guard 真的跑過（`checked=`）。
- ⛔ **第三位審查者反駁那批修正，又找到 12 個非阻擋**（`code-review-C-refute.md`），四個發佈前修：
  `cd "board dir" &&` 的引號正規式犯了 F1 同一個錯（改成同樣三個交替式）；`cd x &&` 的目標**取代**
  cwd 而不是兩邊都試（兩邊都試會對指令沒碰到的檔誤拒）；錨點計數改算**原始**位元組（rstrip 過的
  計數會拒掉工具本身找得到一次的 Edit）；frontmatter 跳過只在第二行像 YAML key 時才做（否則第一行的
  `---` 水平線會連同下面的標題一起被吃掉，檔案變成沒標記）。加 `Move-Item`、`Rename-Item`、
  `Copy-Item`。**記下不修的**：A-F9（`"false"` 字串對九個 guard 都算 true，繼承）、B-NB-5（ADR 指定
  的措辭）、B-NB-6（規格在三處，本 plugin 慣例）；C 的其他缺口寫進 `PROTOCOL.md` §4。⚠ C 那批修正
  沒有再被第四位審過 —— 兩輪加一輪反駁是預算。
- ⚠ **沒做、寫下來的：** `~/.claude/docs/VERIFICATION-LESSONS.md` 該吸收哪九條、cowork 該留哪三條，
  是一份給主人的建議（`RECOMMENDATION-verification-lessons.md`），不是改動 —— 那是另一個 repo
  的 user-scope 檔。cowork 在那之前保留全文（先加再刪，否則就是它自己記的「省略遇上重組」）。
  `NewSkill/cowork/` 原件要不要刪是主人的一句話，在 `Memory/PENDING.md`。

---

## 0.62.0

⚠ **又一個預設門檻變了，所以又是次版號。** `soft_pct_7d` **95 → 93**（PACE，由「七天」視窗
觸發）。`hard_pct_7d` 維持 97。

**而「七天」那條長條圖終於有自己的一對顏色門檻。** 在 0.61.0 之前（含）是**一對門檻切兩條
長條圖** —— 所以七天那條是用「五小時」的門檻上色。2026-09-19 量到，在 0.61.0 的預設值下：

```
7d  86% -> 紅    而那一週自己的等級還在 PACE 以下
7d  94% -> 紅
7d  96% -> 紅    那一週的等級是 PACE
7d  98% -> 紅    那一週的等級是 STOP
```

⇒ 那條長條圖在它自己的 PACE 點之前**十四點**就已經叫到最大聲，而且**分不出 86% 和 98%**。

- **新增四個鍵。** `colour_lead_soft_pct_7d`（**3**）、`colour_lead_hard_pct_7d`（**2**），
  以及推導出來的 `colour_warn_pct_7d`（**90**）和 `colour_alarm_pct_7d`（**95**）。
  ⭐ 主人 2026-09-19 的指定：soft 減 3 轉橘、hard 減 2 轉紅。
- ⚠ **兩個提早量彼此不同，也和五小時的 5 不同，那是決定不是疏漏。** 7d 那一對本來就坐得很高
  —— 那一週通常不是限制 —— 所以單一的提早 5 會讓那條幾乎整週都綠、然後直接跳。3 和 2 留下
  一個看得見的警告帶，又不會讓它連叫好幾天。這句話寫在常數旁邊，免得有人「整理」掉它。
- **`colour_lead_pct`（5）沒有被retire。** 它一個版本前才出貨、README 有寫、它就是五小時的
  提早量。加了一個鍵、下一版就把它換掉是純粹的擾動，而 `install.py` 的 `RENAMED` 表就是因為
  那種事很痛才存在的。
- `_state()` / `_colour()` / `_window()` 多一個 `bands` 參數，帶那個窗自己的 `(warn, alarm)`；
  `None` 就是五小時那一對，所以每一個既有呼叫端行為完全不變。
  ⛔ **不是靠嗅 `window_secs` 判斷。** `_window()` 本來就收到它，從 `7 * 86400` 反推今天會對，
  但只要哪天出現第三個同樣七天長度、卻有自己門檻的窗，它就會無聲地錯。呼叫端知道自己在畫哪
  一個窗，就讓呼叫端講出來。⭐ 兩個七天窗都走這條路：`7d` 那條，和帳號有的話那條**模型範圍**
  的週限制。
- **七天那一對也是可以釘住的**：磁碟上填**數字**就優先，只釘一個而順序顛倒兩個都退回推導值，
  `config.example.json` 對兩個推導鍵都寫 `null`，而 `install.py --status` 與 `test_install.py`
  都**要求**它是 `null`。

**七個突變被預期的斷言殺掉。** ⛔ **其中最重要的那一個一開始溜過去了，而它溜過去的方式值得
記下來：** 把 renderer 那一行改回讀 `colour_warn_pct`，**整套 selftest 全綠**。因為我原本的
斷言測的是 **config**，而 config 可以完全正確、同時長條圖還是用預設那一對畫出來的。
⇒ 現在多一個檢查**驅動真正的 `_line_parts()`**，讀七天那一段自己的 escape code。
⚠ 而那個檢查的第一版**也**漏掉同一個突變：它只斷言紅色不出現，但那個突變只改了橘色那一半，
所以 86% 變成橘色 —— 不是紅色，檢查就過了。兩個顏色都要斷言。

⚠ 三個寫這個檢查時踩到的陷阱，都記在程式裡：

- `_line_parts()` **沒有** `now` 參數。第一版在 `"now" in _line_parts.__code__.co_varnames`
  時傳 `now=` —— 但那個 tuple 裝的是**所有區域變數**，不是參數，所以條件永遠成真、呼叫直接
  拋錯。
- `lstrip("\033[0-9;m")` 看起來對，其實不對：`lstrip` 吃的是一個**字元集合**，而 `7` 在裡面，
  所以它會把 `7d` 的 `7` 一起吃掉，那一段永遠找不到。改用 regex。
- `_line_parts()` 回傳的是 `(segments, extras)` **兩元素元組**，不是一個 list。

---

## 0.61.0

⚠ **預設門檻變了，所以這是次版號，不是修訂號。** 0.60.1 到 0.60.4 全都是修 bug，那會訓練讀者
把修訂號當成「沒有要決定的事」。這一版對每一個沒有自己覆寫過的人都會改變行為。

**主人調高了五小時視窗的兩個門檻。** `soft_pct_5h` **75 → 80**（PACE），
`hard_pct_5h` **85 → 90**（STOP）。

**而且顏色門檻改成「推導」，不再是手填的數字。** 問到紅色條（`colour_alarm_pct` 85）要怎麼辦
的時候，主人的裁定是：

> 故意不等於，那個決定什麼會被「拒絕」，而人會希望在任何東西開始被拒絕之前，就先看到警告
> 顏色。這反而讓我認為應該要修改上色條件，colour_warn_pct 的定義應該改成 soft_pct_5h 減 n、
> colour_alarm_pct 的定義應該改成 hard_pct_5h 減 n，而 n 預設應該是 5

⇒ 新增 `colour_lead_pct`（預設 **5**）。`colour_warn_pct` = `soft_pct_5h` − lead，
`colour_alarm_pct` = `hard_pct_5h` − lead。在新預設值下就是橘 75、紅 85 —— 跟改之前**同樣
兩個數字**，但現在是跟著門檻走，不是剛好坐在旁邊。

- ⛔ **這修掉的是一個會無聲發生的錯。** 原本那兩個顏色是手填的，門檻一調高它們就被留在後面：
  紅色於是會說「還沒有東西被拒絕」，而閘門其實已經在拒絕了。這一版之前，把 `hard_pct_5h`
  調到 90 的人，紅色還留在 85。
- ⛔ **而這個檔案裡本來有兩段註解在互相打架。** `DEFAULTS` 開頭寫「顏色刻意**對齊**門檻，
  橘色就是 PACE 開始、紅色就是 STOP 開始」；`_state()` 的 docstring 寫「刻意**不**等於
  soft_pct/hard_pct」。而實際值兩邊都不符：紅 85 = hard 85（對齊），橘 70 ≠ soft 75（早 5）。
  ⇒ 現在只有一條規則，寫在一個地方，而且由算式強制。
- **手動填的數字仍然優先。** 在自己的 `config.json` 裡給那兩個鍵一個**數字**，行為跟以前完全
  一樣 —— 調過顏色的人不會被改掉。⚠ 判斷「有沒有手動設」讀的是**磁碟**上的值，不是合併後的
  `cfg`：合併之後「刻意設成 85」和「預設就是 85」是同一個值。
- ⛔ **只釘住其中一個而導致順序顛倒，兩個都退回推導值**，並在 stderr 說出來。一個永遠到不了
  的紅色頻帶，跟一個從來沒發生過的速度看起來一模一樣。負的 `colour_lead_pct` 也會被拒絕 ——
  那會讓顏色出現在拒絕「之後」，正是這個設計要避免的唯一那件事。
- ⛔ **`config.example.json` 裡那兩個鍵現在是 `null`。** 範例是給人**整份複製**的東西：填一個
  數字進去，複製的人就把自己的顏色永久釘住，推導再也不會對他們生效。`config()` 只採納磁碟上
  的 int/float，所以 `null` 就等於「沒設」。⭐ `install.py --status` 的交叉檢查和
  `test_install.py` 現在都**要求**那兩個鍵是 `null`，所以範例沒辦法悄悄變回數字。
- **`_state()` 的兩個 fallback 改讀 `DEFAULTS`。** 那裡本來是寫死的字面值，而註解就記著它們
  曾經漂移過（一個寫 90，`DEFAULTS` 寫 85）。現在預設值是推導的，寫死的字面值下一次門檻一動
  就會再漂一次，而且是朝著最糟的方向：一個宣稱「還沒有東西被拒絕」的顏色。

⚠ **四個測試檔的 fixture 寫死了舊門檻，一起修成從門檻推導。** 這是這次唯一真正的意外，而且
它自己就是一個教訓：

- `dispatch_gate.py` 的驅動表用 **78** 代表「一個 PACE」（舊 soft 75 加一點餘裕）。在 80 之下
  那是 GO，陽性對照觸發，看起來像 hook 壞了。
- `test_guards.py` 有**四處** `usage_at(75)` —— 剛好等於舊的 `soft_pct_5h`，所以四個 case 都
  以一句沒頭沒尾的 `AssertionError: GO` 失敗在它們根本沒在測的判定上。
- `usage.py` 自己的顏色頻帶斷言寫死 **70/85**，也就是把推導值手抄一份。
- `README.md` 的範例印 `PACE at 78%`，那在新預設值下是**不可能出現**的一行。
- ⇒ 全部改成從 `DEFAULTS` 算出來，而且**落在頻帶內、不落在邊界上**：坐在邊界上的 fixture
  撐不過邊界移動一格。

---

## 0.60.4

**0.60.2 只修了五處中的一處,而漏掉的那一處是畫面上最強的那句話。** 七天窗驅動判定時，
`v["pct"]`（永遠是五小時窗的數字）還在四個地方被直接讀：`USAGE(...)` 那行 log、兩行
`DENY(...)` log，以及 ⛔ **派工被拒絕**那句 `systemMessage` —— 這個外掛做過最強的一件事，
而且 README 有引用它。所以在 5h 3% / 7d 99% 時，畫面上會出現
`sub-task dispatch REFUSED - usage STOP at 3%`。

⇒ **一個共用函式 `driving_pct(v)`，五處全部改用它**，回傳 `("7d ", 99)` 或 `("", 90)`。
五小時窗那一側完全不變。

- ⭐ **檢查釘的是根因,不是那五句話。** `selftest()` 斷言 `on_user_prompt` 和 `on_pre_agent`
  的原始碼裡**不准再出現** `v.get("pct") or 0`。一句一句去比對的檢查，得為每一句寫一次，
  而且一定會漏掉第五句 —— 這次就是這樣漏的。外加三個 `driving_pct()` 自己的單元斷言，
  包含「沒有 driver 也不能炸」。
- **五個突變被預期的斷言殺掉**，其中一個是把拒絕訊息改回讀五小時數字。
- **拒絕那一句是實際驅動出來的，不是只讀原始碼。** 原始碼釘子只證明呼叫寫對了，不證明字串
  出來是對的；`on_pre_agent` 沒有任何驅動列覆蓋。⚠ 探針第一版回報 `decision: 'allow'` ——
  **沒有蓋 `state/<sid>.start` 印記的 session，每個守衛都只是勸告**，所以拒絕分支從來沒跑到，
  而那句要讀的訊息根本不存在。陽性對照（`decision == "deny"`）就是為了這個。
- ⚠ 探針第一版還把環境變數名稱猜成 `CLAUDE_DISPATCH_GUARD_STATE`；實際是
  **`CLAUDE_DISPATCH_DIR`**。猜錯名字會安靜地退回讀**真實**狀態目錄，於是量到的是這台機器
  當下的判定，不是 fixture 的。

---

## 0.60.3

**0.60.2 那個新篩選器會把多行指令的續行誤標成污染。** 換句話說，它把它剛修掉的那個毛病
搬了個位置：⛔ **一個因為無關原因而紅的檢查，還是一個因為無關原因而紅的檢查。**

`log()` 寫的一筆記錄是「時間戳 + 訊息」，而訊息就是指令原文 —— 它是按**字元數**截斷的，
不是按第一個換行截斷。所以 heredoc 或任何多行指令，會在日誌裡留下**沒有時間戳前綴**的續行。
2026-09-18 在真實日誌量到：沒有前綴的 1383 行，對有前綴的 10145 行。⇒ 按**行**判斷的篩選器
會把每一個續行都標起來。

⚠ **0.60.2 那三次全綠沒有涵蓋這一點**，而這正是它為什麼出得去：那三次是同一個 Bash 呼叫，
它的 `CMD-ALLOW` 在視窗**打開之前**就寫好了，所以三個視窗期間都是零新行。篩選器自己的兩個
對照也沒涵蓋 —— 兩個樣本都是帶時間戳的單行。

- **改成按記錄判斷，不按行。** 沒有時間戳前綴的行，算前一筆記錄的續行，繼承前一筆的分類，
  不自己算一筆。
- ⚠ **`_new` 開頭的續行永不標記**：它屬於一筆在視窗**之前**就開始的記錄，所以它不是新的。
  所以 `live` 的初值是 True。
- ⭐ **對照補到五個，而且涵蓋多行記錄**：`CMD-ALLOW` 後面接兩行續行 → 三行都不標；
  `USAGE(...)` 後面接一行續行 → **兩行都標**（一筆可疑的記錄要把它的續行一起帶走）；
  單獨一行沒有記錄開頭的續行 → 不標。
- **五個突變被預期的斷言殺掉。** ⚠ 其中那個「退回按行判斷」的突變，第一版把 `if head:` 改成
  `if True:`，讓 `head.end()` 在 None 上炸掉 —— 紅了，但紅在崩潰而不是受測的斷言上，等於
  什麼都沒證明。突變本身也必須是合法的程式。
- ⛔ **為什麼是 0.60.3 而不是改寫 0.60.2：** 0.60.2 已經發佈出去了。用同一個版號換掉內容，
  就是對那個版號說謊，而且有人可能已經拉過它。

---

## 0.60.2

**七天視窗觸發判定時,那一行印的是五小時視窗的數字。** agent 被要求原封不動印的那一句用
`round(v["pct"] or 0)` 組出來，而 `pct` 永遠是五小時窗的。⇒ 在 5h 3% / 7d 99% 時，判定是
STOP、`v["text"]` 正確地說「這一週快用完了，五小時窗不是限制（5h 3%）」，緊接著的下一句卻
命令 agent 印 `STOP at 3% - winding down` —— 同一個畫面上，一邊說剎車踩下去了，另一邊叫你
去等一行寫著 3% 的字，讀起來像誤報。

⚠ **這是既有缺陷，不是 0.60.1 造成的** —— 同一個運算式在 `550b556` 就在了。它由 0.60.1 的
第二輪審查找到；那一輪報成印 `0%`，實際量測是印**五小時窗**的數字，只有在五小時窗完全沒動
的時候才會是 0。

- **改成印驅動窗的百分比,並且說出是哪一個窗。** 七天窗驅動時那一行變成
  `STOP at 7d 99% - winding down`；五小時窗驅動時**完全不變**，所以任何引用那個形狀的地方
  都不用改。`verdict()` 早就回傳 `driver` 和 `pct_7d`，不需要新的計算。
  ⭐ 主人 2026-09-18 在兩個版本並排之下選了標出窗名，而不是只換數字的 `STOP at 99%`：光看
  數字分不出是哪個窗，而且狀態列在同一時刻顯示的是五小時窗的數字。
- **驅動用的表格多兩列七天窗的。** 七天窗的門檻是 `soft_pct_7d` 95 和 `hard_pct_7d` 97，
  不是 75/85。⭐ 五小時窗那兩列現在多了一個職責：它們釘住五小時窗驅動時**不會**出現 `7d`。

**`test_guards.py` 那個比對日誌檔案大小的檢查,換成比對行。** `case_selftests_never_read_the_terminal`
原本比對真實狀態目錄日誌前後的 `len(f.read())`。但這台機器上每一個活著的 session，每一次
Bash 呼叫都會往那裡追加一行 `CMD-ALLOW` —— 所以只要有另一個 session 在工作，斷言就紅，而
訊息還把責任推給 selftest。

⇒ **它不只是吵而已。** 那個檢查排在散文釘子的前一行，所以它一紅就**中止整個檔案**，後面的
斷言根本沒執行 —— 用整個檔案做的突變檢查會讀成「攔下了」，而受測的斷言從來沒跑到。
2026-09-18 量到：連續三次整檔執行，前兩次都死在它上面（105 和 143 bytes），第三次才過。
修好之後連續三次全綠。

- **比對行,並忽略活 session 的工具流量**（`CMD-ALLOW`、`CMD-DENY` —— PreToolUse 每次呼叫
  就寫的那兩種）。視窗期間出現的其他新行一律算失敗，訊息直接印出那幾行。
- ⚠ **刻意接受的殘餘缺口：** 如果某個 selftest 寫的是 `CMD-ALLOW` 或 `CMD-DENY`，它會溜過
  這個篩選。替代方案是原本的大小比對，而它三次裡兩次因為別人的流量變紅，所以什麼都沒守住。
  **一個因為無關原因而紅的檢查不是更嚴格的檢查。**
- ⭐ **篩選器自己在同一次執行裡有對照**：它必須標記一行 `USAGE(...)`，而且必須**不**標記一行
  `CMD-ALLOW`。少了這個，一個什麼都不匹配的篩選器會永遠回報乾淨通過。
- **前綴比對，附集合退路**：日誌實務上只追加，但視窗期間輪替或被截斷會讓 `len(before)` 失去
  意義，每一行舊的都會被當成新的。

**四個突變被預期的斷言殺掉**，外加一個獨立探針。⛔ **那個探針的故事值得讀** ——
`scratch/06-fix-0.60.2/`：

- 「selftest 污染狀態日誌」**不能**注入 `selftest()` 裡面。把 `usage.state_dir` 導向暫存目錄的
  隔離，是在 `if "--selftest"` 那個分支裝的，也就是在那個函式跑**之前**，所以放在函式裡的寫入
  會進隔離區，突變量到的是空氣。
- 更糟的是，「確認探針那一行有寫進去」的那次 `grep`，**比對到的是它自己的指令文字** —— gate
  會把每一個 Bash 指令記進同一個檔案，所以拿字串去搜日誌，等於把那個字串放進日誌。
- ⇒ 忠實的版本把隔離區和檢查**指到同一個暫存目錄**：出貨 selftest 自己寫了 21 行，全部被
  標記，訊息是新的那一句，而且真實日誌零污染。

⚠ **產生的程式裡不要放反斜線。** 第一版探針把換行寫成轉義序列，注入的那一層把它變成真的
換行，檔案就不能解析了，`--selftest` 結束碼 1 —— 被檢查**舊的** `assert rc == 0` 攔下，對
受測的斷言什麼都沒證明。改用 `chr(10)`。

---

## 0.60.1

**hook 在 PACE 命令 agent 宣告收尾,它不該這樣。** 主人 2026-09-17 裁定：**PACE 的意思是
「不要開新的一批」，STOP 才是收尾那一個。** 技能文字一直就是這樣寫的，程式卻不是：那句要求
agent 原封不動印出的確認行是**一個** format string 餵 `v["verdict"]`，所以在 PACE 時它用大寫
命令 agent 印 `PACE at N% - winding down`，並且「用一句話說你**丟掉了什麼**」—— 每一個 prompt
都來一次。

⇒ 那等於把 PACE 當 STOP 在跑，而且它比它牴觸的技能散文大聲。2026-09-17 量到兩次：規則
已經寫在 `dispatch-protocol`、`unattended-work` §17 和機器的記憶檔裡，session 還是提早收尾。
⛔ **重述規則沒有用，要修的是那一行。**

- **兩個判定各有自己的措辭。** STOP 保留原文（`STOP at N% - winding down`、「你丟掉了什麼」、
  逃生口 `- NOT winding down`）。PACE 改成 `PACE at N% - no new batch`，並且明講「在 PACE 你
  什麼都不丟、也不交接，只是不要開新的一批或新的重工作」，逃生口是
  `- starting a new batch anyway`。⚠ 逃生口刻意不含 "winding down" 四個字：否則檢查會被一個
  仍然在畫面上說收尾的字串滿足。
- **確認行的機制留著,只換字。** 要求一行原封不動的輸出，是「它一直在工作」跟「它從來沒收到」
  唯一分得開的辦法。
- ⭐ **畫面和 transcript 由同一個變數餵。** 兩個欄位（`additionalContext` 給模型、
  `systemMessage` 給人）現在共用一個 `ack_line`，所以「畫面叫你等的那一行」不可能再和
  「transcript 被要求印的那一行」漂開。那種漂移從椅子上看不出來：人會在等一個沒有人要求的字。
- **技能的散文也在說反話,一併修好。** `unattended-work` §17 原本寫「判定說 **PACE** 或
  **STOP** 才交接」—— 和 hook 站在同一邊，兩邊一起叫 session 在 PACE 交接。兩個語言側現在都
  明講「⛔ 而 PACE 不是交接」。⚠ 這一條是審查第一輪的阻擋項：程式修好、`PENDING.md` 卻把
  這一半標成 FIXED，而技能還在說反話。
- ⭐ **散文的回歸被釘住了。** `test_guards.py` 既有的 `case_burn_figure_never_winds_down`
  多兩個 FORBIDDEN 樣式（出貨過的原文，英中各一）和一組必須出現的句子，所以技能文字退回去
  會是紅的，不是只有人讀得出來。
- **「batch」綁到「wave」。** `dispatch-protocol` 給 batch 一個較窄的技術意義（主人核可的
  **併發**群組），所以 `no new batch` 可能被讀成「我這一個循序子任務不算」。確認行後面那一句
  現在明講：新的一批指新的派工波或新的重工作，**循序的也算**。
- **檢查是驅動出來的,不是讀原始碼。** selftest 用 PACE（5h 78%）和 STOP（5h 90%）兩份 payload
  實際跑 `on_user_prompt()`，再讀它產生的兩個欄位。⛔ 原本的 `assert "winding down" in src`
  單獨留著會通過，因為新程式的 STOP 分支照樣滿足它 —— 缺陷本來就是一句服務兩個判定。
- **斷言的是整行,不是那個片語。** 比對 `` `PACE at 78% - no new batch` `` 會連判定字和百分比
  一起釘住；而在**兩個欄位**比對**同一個**字串，是唯一釘住那句標題主張的東西 —— 畫面不可能
  跑去等一行 transcript 沒有被要求印的字。
- ⛔ **收尾的指令本身也必須留在 STOP。** 確認行只是標籤：把 PACE 的尾句改成要求 handoff 和
  END THE TURN，上面每一個斷言都還是綠的，傷害卻一模一樣。所以 `END THE TURN` 和 `dropping`
  在 PACE 斷言為不存在、在 STOP 斷言為存在。
- ⛔ **而且兩列都必須真的跑過。** 驅動用的表格少掉 PACE 那一列，上面所有斷言都會通過 ——
  那是第三條安靜的路，和 `usage._relax`、`warned` 標記並列。現在比對跑過的判定集合，
  表格也補了尾逗號，所以刪掉一列不會讓元組退化成它自己那一列。
  ⚠ 重置時間太近（`usage._relax` 放行成 GO）或 `warned` 標記已經寫過，`on_user_prompt()`
  什麼都不印 —— 那不是安靜通過，是 `json.loads("")` 直接拋錯，訊息會指向 JSON 而不是措辭。
  真正守住那條路的是那個陽性對照：`usage.verdict()` 必須先讀成受測的那個判定。
- ⛔ **而畫面那個欄位要自己一行。** 那個線索檢查一開始只讀 `additionalContext`，第二輪量到把
  `seen_why` 改成在**使用者畫面上**下令交接，整套測試照樣全綠。現在兩個欄位都檢查，而且規則
  不同：線索只准出現在 STOP 的 `additionalContext`，`systemMessage` 在**任何**判定都不准有 ——
  那個欄位是給人的一行預期說明，它不下任何命令。
- **兩個散文樣式是刻意收緊的,那是修正,不是疏漏。** 第一版只要 PACE 出現在
  「hand over when the verdict」附近就命中，第二輪量到它**對正確的規則變紅** —— 用最自然的
  寫法寫出來的那一句（"You hand over when the verdict is STOP, not PACE"）。會擋住正確編輯的
  偵測器，比漏掉一個改寫更糟：刪掉那一句本來就有必要句在守，而一次誤紅會讓下一個踩到的人
  直接把檢查刪了。現在除了兩個陽性對照，還有四個**偽陽性**對照一起出貨。
- **必要句那個迴圈會數自己跑了幾次**，而 PACE 的失敗訊息也不再把原因推給燒率行。篩選條件
  一個都沒中的迴圈，什麼都沒斷言卻回報成功 —— 那正是判定集合檢查堵住的同一條安靜的路。
- `dispatch-protocol` 原本寫交接「只由那個『字』觸發」，沒說是哪一個字。現在兩個語言側都
  指名 **STOP**，並明講 PACE 不是。
- **總共八個突變，每一個都被它針對的那個斷言殺掉**，而且每一個都讀 AssertionError 的**訊息**，
  不看結束碼。其中兩個是對 `3e1ee3b` 手動跑的：把 PACE 的字改回從 `v["verdict"]` 組出來、
  把 "winding down" 塞回 PACE 的逃生口。另外六個寫成可重跑的腳本，在
  `Memory/tasks/20260918-092012-pace-says-winding-down/scratch/04-fix/mutate.py`：表格少掉
  PACE 列、把 END THE TURN 和 dropping 塞進 PACE 尾句、讓技能 §17 說回「PACE 才交接」、
  以及在兩個語言各拿掉那一句。
  ⚠ 那個腳本現在也記下兩個會讓突變**看起來像通過**的陷阱：錨點字串含 `\n` 的話，在這個
  倉庫的 CRLF 檔案裡一個都不會中，那個 case 會被跳過；而整個 `test_guards.py` 會在到達散文
  釘子之前，先中止在那個已知的 state-directory log 檔案大小比對上，所以技能的突變直接呼叫
  `case_burn_figure_never_winds_down`。不過那個釘子還是有用整個檔案證明過 —— 第三次嘗試，
  等到那個鄰居安靜的時候。
- `README.md` 兩個語言側都更新了，順手修掉同一段裡過期的門檻數字：那裡寫「PACE 預設 85%、
  STOP 預設 93%」，實際是 `soft_pct_5h` 75 和 `hard_pct_5h` 85，而且範例用的 90% 其實已經是 STOP。

⚠ **`SPENT in ~N min` 那條燒率行是另一件事,不在這個版本裡。**
見 `Memory/tasks/20260914-124312-burn-line-read-as-a-stop-signal/`。

---

## 0.60.0

**一台機器上只有一個 session 的 resume 活得下來,現在每個 session 各有一份。** 整套機制的每一個
產物都是綁在「機器」上的 —— 一個 `resume.json`、一個 OS 排程名稱、一個 auto-arm 冷卻檔、一個失敗
通知,還有「有人活著嗎」這個判斷 —— 所以第二個 session 武裝的時候,會無聲地蓋掉第一個。
**實測於 2026-09-17:** 同一個欄位在三小時內被三個不同 session 輪流搶走,其中一筆記錄同時帶著
一個 session 的任務資料夾和**另一個** session 的工作目錄 —— 那個排程醒來會在錯的專案裡跑。

- **記錄改成 `<state>/resume/<session>.json`。** ⛔ **故意不放進 `state/`**:`prune_state()` 依
  時間清那個資料夾,而 resume 可以對「七天」那個視窗武裝 —— `state_keep_days` 設小一點,記錄就會
  在 OS 排程還掛著的時候被刪掉,排程醒來只會看到 `RUN-ABORT`。
- **OS 排程改名為 `ClaudeDispatchGuardResume-<dir8>-<session>`。** `dir8` 是
  `normcase(realpath(state_dir))` 的雜湊,所以兩個狀態目錄不會撞同一個名字,同一個目錄用不同大小寫
  拼寫也不會認不得自己的排程。
- **武裝的 session id 用傳的,不是用猜的。** 之前 `do_arm` 退回去取「最新的 `state/*.alive`」,
  而那個函式自己的註解就寫著:兩個 session 同時活著的時候會猜錯 —— 正好就是這個功能存在的場景。
- **冷卻檔(spawn floor)也改成每個 session 一個。** 這是單槽問題的第二半:就算記錄和排程名稱都分開了,
  一個機器共用的 300 秒冷卻仍然會讓第二個 session 的武裝直接被擋掉。
- **醒來的判斷改成只問「武裝我的那個 session 還活著嗎」。** 舊的問法是「**任何** session 活著嗎」,
  而 `heartbeat()` 在任何分支之前就會蓋章,所以只要機器上有任何一個 session 就永遠是「有」——
  包括 resume 自己開出來的那個 `claude -p`,最長三小時。⛔ **這放棄了一項安全性:** 你在另一個
  session 工作的時候,背景 resume 可能會跑起來。這是刻意的,由擁有者核准 —— 保留它等於整個功能在
  單機上不存在。界線是武裝時螢幕上那行字、`resume.py --cancel`,以及 resume 只在自己記錄的
  任務資料夾和工作目錄裡動。
- **交接檔裡的「接手」註解可以讓排程不跑。** 接手別人任務的 session 立刻在那份 `HANDOFF.md` 寫
  `⛔ TAKEN OVER <時間戳記> by ...`;排程醒來讀到比武裝時間新的那一行就站下來。⚠ 時間戳記
  **寫在文字裡,絕不用檔案 mtime** —— `git checkout/pull/stash/merge` 會把每個檔案的 mtime 變成現在,
  用 mtime 的話一次 `git pull` 就能讓整台機器的排程全部不跑。⚠ 解析失敗、沒有時間戳記、比武裝時間舊 ——
  一律**照跑**:重做浪費一個視窗,不跑是把工作整個弄丟。
- **失敗通知改成每個 session 一份,而且會全部念出來。** 之前兩個 resume 同一晚失敗只會留下一則 ——
  第二次寫入蓋掉第一次,讀的人再刪掉。訊息現在也會說是**哪一個任務**停了。
- **清理:** 記錄的鬧鐘時間超過整個重試視窗、而且排程器已經不掛著它,就連記錄帶排程一起清掉。
  ⛔ 只用自己記錄裡的名字逐一問(每次約 115 ms),**不列舉整台機器的排程** —— 實測 489 個排程要
  3.7–6.8 秒,而 SessionStart 的 timeout 是 15 秒,**逾時的 hook 是 fail-open**,等於為了打掃把煞車關掉。
- **解除安裝改成依前綴列舉。** 之前只問一個固定名稱,改名之後會把每一個 per-session 排程留在系統裡 ——
  正是那個檔案自己標題寫的風險。
- **交接檔一律要寫「我是誰」。** resume 醒來是全新的 `claude -p`(新的 session id,**不是**
  `--resume` —— 重送對話記錄是 ~95k token/MB 且 cache 完全不命中),所以繼任者只能沿用這份檔案裡
  給的名字。`handoff_warnings()` 沒看到 session id 也沒看到角色名稱時會提醒。⚠ 是警告不是拒絕。
- **兩個先前就存在的缺陷一併修掉:** POSIX 的 `--cancel` 會執行 `atrm -a`,刪掉使用者**全部**的
  `at` 工作(包括這個外掛從沒建立過的);現在只刪記錄下來的那一個編號,`atrm -a` 移到要明講的
  `resume.py --cancel --all`。以及排程指令沒有帶 `--dir`,所以用 `$CLAUDE_DISPATCH_DIR` 的人,
  排程醒來讀的是**預設**目錄。
- **升級不會弄丟已武裝的排程:** 舊的單槽記錄會依它自己記的 session id 搬家;沒有 session id 的
  ⛔ **原地保留**並由 `--status` 回報 —— 幫別人的鬧鐘亂取名字比說「這個要你自己清」更糟。
- ADR:`Memory/tasks/20260917-132015-parallel-per-session-resume/`(兩輪對抗審查,第一輪 REJECT
  五個致命問題,第二輪判定五個都解決、另外找出四個)。九個突變殺過;一個既有檢查抓到這次改動
  自己引入的缺陷 —— 搬遷曾經放在 `main()` 最上面,害得 `resume.py --selftest` 去搬動真實目錄裡
  一筆活的記錄。

---

## 0.59.1

**state/ 目錄無限累積,現在會清。** 每個 session 在 state/ 留一組 per-session 標記檔(`.start`、
`.branch-*`、`.skill-seen-*`、`.warned*`、`.handoff-written`…),session 一結束就沒用了。
`prune_state()` 本來只清其中幾種,漏掉最大宗 —— 光 `.branch-*` 就佔 322 個檔裡的 179 個。現在改成
「除了例外全掃」:state/ 裡超過 `state_keep_days` 天的檔一律依時間清掉,只留兩個例外 —— `.alive`
改用「數量」上限、`.slot*` 完全不碰(那是活的併發狀態,有自己的分鐘級回收)。以後新增的標記種類會
自動被涵蓋,不會再漏。

- **`state_keep_days` 可在 config 設定,預設 7 天** —— 每個安裝都套用、未來持續清理。
- ⚠ 這是「安全邊際」:一個還在跑的 session 的 `.start` 是讓它煞車保持「開」的開關,所以天數必須超過
  單一 session 可能跑的最長時間。7 天就是那個邊際,不是隨便縮的旋鈕。
- ⚠ 跟 `history_keep_days` 一樣「刪除安全」:填字串、負數、0、null 都代表「全部保留」,用
  `usage._days()` 轉換,不列入 NUMERIC_KEYS。
- selftest 驗證:各種舊標記被掃、近期的留著、`.slot*` 不動、`.alive` 依數量、壞設定不刪任何東西;
  三個突變殺過(時間判斷、`.slot` 例外、刪除安全)。實測真實目錄:170 個 >7 天的會清、132 個近期的留。

---

## 0.59.0

**接近 reset 窗口、剩餘額度撐得過時,不再 PACE/STOP。** 舊規則只看固定門檻,所以一個馬上要重置、又還有餘裕的
視窗照樣被暫停 —— 資料上 89% 的暫停是白費的,接近重置（≤60 分）的暫停 100% 都撐過了。現在多一層「投影放寬」:
接近重置時,若整窗燃燒速度顯示剩餘額度撐得到重置,就把 PACE/STOP 放寬成 GO。它「只放寬、永不收緊」。

- **判斷用「整窗錨定」速度,不是短時間尾段速度**(`pct ÷ 視窗開啟至今分鐘數`)。理由是硬性的:每次工具呼叫的煞車
  走 `level()`＝`verdict(cheap=True)`,顯示走完整 `verdict()`,兩者「必須算出同一個詞」—— 尾段速度要 parse 歷史,
  cheap 路徑付不起。整窗速度不需要歷史、永不為 None、對帳戶天生安全。實測(`ab_rate.py`)它比 max(整窗,尾段) 還
  多救回一次白費暫停,危險數同為 0。這偏離了 ADR 的 max(整窗,尾段);見
  `Memory/tasks/20260916-143157-projection-stop-rule/REVISION-whole-anchored.md`。
- **兩個視窗各自的天花板與 horizon。** 5h:距重置超過 60 分不信投影;95% 以上絕不放寬。7d:沒有 horizon 常數
  (整窗速度自動縮放),99% 以上絕不放寬 —— 99 是讓「7d 剩 98%、接近重置 → GO」這個擁有者核可情況成立的最小防線。
- **STOP 被放寬時的 NET 區。** 主 session 繼續做事,但:自動設好續跑、提示每約 10 分重寫 HANDOFF.md、並「拒絕新派工
  (派子代理)」。主 session 自己把一串循序工作做完不算新派工。派子代理會燒掉放寬所仰賴的額度,而續跑不涵蓋進行中的子
  代理 —— 所以擋掉。
- **預設 `soft_pct_5h` 由 70 改為 75。** 每個安裝的 PACE 起點會跟著上移。
- 退休 `_soften_near_reset` 與 `near_reset_min`(舊的 20 分一級軟化,是這個投影的粗略特例);新增 `SEVEN_DAY_SECONDS`
  常數與 `relax_margin`(1.5)、`relax_horizon_min`(60,只限 5h)、`relax_ceiling_5h`(95)、`relax_ceiling_7d`(99)。
- `usage.py --selftest` 新增「cheap/full 同詞」的網格檢查(`level()` 的 docstring 一直承諾、實際卻不存在的那個),
  外加「投影永不收緊」不變式。五個 fail-open 守衛全部以突變殺過(天花板、horizon、survives、cheap/full 分歧、收緊)。
  gate 的 NET 守衛(續跑會設、不會被撤)另以兩個突變殺過。
- ⚠ 可證偽的重新檢討:放寬後若「撞牆」(視窗在重置前真的到頂)會記 log;有撞牆 → 收緊(調高 margin、調低天花板);
  一段時間乾淨 → 放鬆(調低 margin)。先以保守的 margin 1.5 出貨。ADR(兩輪對抗審查)在
  `Memory/tasks/20260916-143157-projection-stop-rule/`。

---

## 0.58.4

**前景長代理期間，用量會凍住,而煞車會 fail open。** 一個監督者派了「一個」跑很久的子代理然後在等,
在子代理回來之前不會觸發任何我們的 hook、也不會寫 ~/.claude.json。於是 watcher 判斷活跡的兩個來源
（`state/*.alive` 和 ~/.claude.json）都在半途過期,watcher 超過 `idle_after_min`（預設 15 分）就
「暫停撈取」—— 而那正是還在燒 token 的時候。⛔ 凍住的數字會讀成「偏低」,所以煞車剛好在它最該作用的
重載期間 fail open。

⚠ 這不是靠「拉長或縮短 API 間隔」能修的。下限 120 秒是量出來的(60 秒會 429、變瞎),而拉長間隔只會
讓數字更舊、更低。缺的不是頻率,是「還在工作」這個訊號。

- `last_heartbeat_min()` 多了「第三個來源」:一個正在進行的派工佔位（`state/*.slotN`）。gate 在派工
  「開始」時寫這個檔、在它的 PostToolUse 移除,所以一個開著的佔位就是「現在有在工作」的證據,中間不需要
  任何 hook。watcher 因此維持「正常的 120 秒節奏」—— 絕不打得更快,所以不會花掉那支端點大約五次的額度。
- ⛔ 以 `slot_ttl_min` 為上限（跟 `claim_slot()` 回收死佔位用的是同一個時鐘）。一個死在 PostToolUse
  之前的派工過了這個時間就不再算活跡,否則一個死掉的派工會讓 watcher 整晚打 API —— 正是 `idle_after_min`
  當初要防的（`Memory/tasks/20260902-082020-stale-slot-after-a-failed-dispatch/`）。
- ⚠ 回傳 0.0,不是佔位的年齡。一個開著、還沒過期的佔位代表「現在」有在工作;它的年齡是代理跑了多久,
  不是「距離上次有人工作多久」。餵年齡回去會讓一個 20 分鐘的代理讀成「閒置 20 分鐘」而照樣暫停。
- 天花板先說清楚:這只拿掉一個「假暫停」,不會讓數字變即時。長代理期間最好也是 120～150 秒的舊,不是 2 分鐘。
- ⚠ 前提:這只對「有在跑 `usage.py --watch`（VS Code 工作）或狀態列」的 session 有用 —— 那個 watcher
  就是這次被解除暫停的計時器。兩個都沒有的話,唯一的刷新路徑是 `keep_clock_running()`,它從 gate hook
  觸發,而 gate hook 在代理執行期間是靜默的,所以數字照樣凍住。修法是跑 `usage.py --watch`。
- `usage.py --selftest` 用「兩個既有來源都過期、只留佔位當變因」把新來源獨立出來測。兩個突變實測失敗
  （拿掉第三來源 → 開著的佔位讀成閒置;拿掉上限 → 死佔位永遠算活跡）。真背景派工不受影響 —— 它本來就被
  `dispatch-protocol` 第 2 條禁止,因為它逃出計帳。

---

## 0.58.3

**0.58.2 的文字叫人刪掉一段它自己的檢查要求保留的話。** `unattended-work` §17 寫著
「規則的唯一一份正本在 `dispatch-protocol`」，而 `case_burn_figure_never_winds_down`
斷言四個技能檔**全部**都要提到這個數字。照著那句話刪掉 §17 那一段，檢查就會失敗——
一條會把守衛絆倒的指示。

- 改成：完整規則和量測在 `dispatch-protocol`，§17 那一段是它的界線那一句，兩邊都要留著。
  英文與中文同時改。

---

## 0.58.2

**`SPENT in ~N min` 那一行把 agent 嚇停了，而且是在用量只用掉 20% 的時候。** owner 回報：
agent 把那個燃燒數字讀成「用量快沒了」，於是預約續跑、收工——判定明明是 GO。

⛔ **根因在提示詞，不在程式。** 剎車讀的是百分比，永遠不讀這個數字，那是 owner 在
2026-08-29 的決定（`Memory/notes/SHELVED-burn-meter.md`：「GO / PACE / STOP 派工或剎車都
不參考這個值」），`usage.py` 裡有檢查釘住它。但 0.56.2 到 0.58.1 的技能寫著
「N is your budget ... write the handover BEFORE it runs out」和「STOP for a new wave」——
**用散文去執行一條程式本身拒絕執行的規則**，而散文才是真正送到 agent 面前的那一半。

⚠ **而且那一行是在視窗剛開的時候叫，不是快結束的時候。** 燃燒速度的起點錨在視窗自己的開窗
時間，所以視窗越年輕，任何花費看起來都越陡。2026-09-14 實測：**用掉 10%、開窗 10 分鐘**
就印 `SPENT in ~90 min`；**同樣 10%、開窗 45 分鐘**，什麼都不印。⛔ 最大聲的地方，
正好是餘裕最多的地方。

- 兩個技能都改寫：**N 只回答一個問題——我接下來要開的這一塊塞得進 N 嗎？** 交接、寫
  `HANDOFF.md`、預約續跑，只由那個「字」（PACE / STOP）觸發。判定是 GO 就繼續做，不管 N 多小。
- `unattended-work` §17 把用量規則**搬出**「context 快用完時的交接」那一節——它被放在一條交接
  指示底下，光是那個位置就在做事，改字改不掉。規則的唯一一份正本現在在 `dispatch-protocol`。
- ⭐ **中文版從來沒有這條壞規則**，所以搜英文句子在半個 repo 裡看起來是乾淨的。現在兩種語言
  都帶著同一條收緊過的規則，漂移補上。
- `test_guards.py` 新增 `case_burn_figure_never_winds_down`：四個技能檔都不准出現六種已經出貨過
  的壞寫法，而且討論到這個數字的檔案必須寫出那句「GO 就繼續做」。三個突變實測都讓它失敗
  （放回英文壞句、拿掉必要句、中文版放回壞句）。
- ⚠ 沒有動 `usage.py`。那一行仍然在 GO 後面掛一個 ⛔，跟同一行的「Headroom available」互相
  矛盾——已經跟 owner 提出，未處理。

---

## 0.58.1

**0.58.0 的 Bash 判斷把「讀」當成「寫」。** 第二輪程式碼審查透過真正的 hook 行程量到：
「指令裡有 `HANDOFF.md`、也有 `>`」這條規則會把 `cat …/HANDOFF.md 2>&1`、`> /dev/null`、
grep 樣式裡的 `>`、heredoc 裡的一句話全部記成「本 session 寫過那個資料夾」—— 於是一次 PACE 的
`Stop` 又安排了一個已完成的任務（與 mtime 那個洞同一種失敗，門變窄了而已）。連本 session 自己的
`state/<sid>.handoff-written` 也被審查者報告裡的 heredoc 塞進一個假資料夾名。

- Bash 的規則改為：`>` 或 `>>`、可有空白與一個引號、**緊接著**以 `HANDOFF.md` 結尾的路徑。
  `test_guards.py` 對六種「讀 / 提及 / 變數」的形狀斷言不記錄，對引號與 heredoc 的寫入形狀斷言記錄；
  突變（放回舊規則）實測失敗於「a Bash command that does not write HANDOFF.md was recorded」。
- GO 的 prompt 取消鬧鐘時，那行「已取消」現在也送到畫面（`systemMessage`）；0.58.0 只給了模型看。
- `state/<sid>.warned` 與 `state/<sid>.handoff-written` 現在與 `.start` 一樣按時間清理；以前永遠不清。
- 文件：PROTOCOL 缺口列、ADR ⟨R2b⟩、一段過期註解。
- ⚠ 仍然看得到的殘餘：記錄的是資料夾**名稱**，另一棵樹裡同名的資料夾、`HANDOFF.md.bak`，都能
  滿足它；ADR 有點名，未關閉。

---

## 0.58.0

**續跑（resume）改由 hook 在回合結束時安排，不再靠 agent 記得。** 2026-09-02 下午，兩台開發機、
同一版外掛：一個 session 在 PACE 寫好 HANDOFF.md 之後又派了一個審查者 —— 自動 arm 掛在 Agent
派遣的 `PreToolUse` 上，所以它被排了續跑；另一個 session 照 PACE 的規則「不開新一波」，寫好
HANDOFF.md 就結束回合 —— arm 的程式碼一次都沒執行，STOP 提示要它手動跑 `resume.py --arm`，
它沒有跑，事後承認是漏掉。⛔ **一個要靠 agent 記得才會發生的步驟，等於沒有那個步驟。**
ADR：`Memory/tasks/20260902-142400-auto-arm-on-stop/ADR.md`（一輪對抗式審查，owner 已決定）。

- `hooks.json` 訂閱 `Stop`。回合結束時，判定為 PACE 或 STOP、而且 task_root 下有一份
  **這個 session 開始之後寫的** HANDOFF.md（mtime ≥ session 戳記、≥ 200 字），gate 就自己
  安排續跑，並在畫面上印一行「已為 `<資料夾>` 安排續跑，幾點喚醒，取消請跑 `resume.py --cancel`」。
  不會阻擋回合結束；沒有 arm 時什麼都不印。
- `UserPromptSubmit` 在 PACE / STOP 也跑同一段：警告之後才寫的 HANDOFF.md，下一個 prompt 就會被安排。
- ⛔ **「本 session 寫的」是記錄下來的，不是用時間推的。** 第一版用「mtime ≥ session 戳記」，
  程式碼審查實測 `git checkout` 會把每一份已追蹤的 `Memory/tasks/*/HANDOFF.md` 的 mtime 變成現在：
  一次 PACE 的 `Stop` 就安排了一個**已完成任務**的資料夾（`fresh=3`，日期最新的那個 —— 正是
  `maybe_auto_arm()` 拒絕的猜法）。時間是 pull / checkout / merge 可以動的代理證據。gate 在每一次
  `PostToolUse` 本來就看得到 Write / Edit 的 `file_path` 與 Bash 的指令，所以現在直接記下
  「本 session 寫過哪些資料夾的 HANDOFF.md」（`state/<sid>.handoff-written`），候選只有那些資料夾，
  再過 `handoff_state()`（存在、≥ 200 字、mtime ≥ 戳記）。⚠ 路徑藏在 shell 變數裡的 Bash 寫入
  看不到（file tool 是文件上的正途）；看不到就不安排並記 log，是安全的方向。
  幾份可用 → 最新的，log 記 `written=N usable=M session=`；⛔ 沒有 session 戳記 → 不安排並記
  `AUTO-ARM-STOP-SKIPPED no session stamp`（ADR 審查 B-2）；沒有記錄到寫入 → 不安排並記 log。
- ⛔ `stand_down_resume()` 的判定表改了一列：**PACE 的 prompt 現在保留鬧鐘，只有 GO 取消。**
  原本 GO 或 PACE 都取消；配上回合結束就 arm 之後，程式碼審查模擬 20 個回合的 PACE session 量到
  **20 次 arm、19 次取消、每回合三行 log、19 個 prompt 印出「已安排」**。PACE 不是「視窗提早重開」，
  它就是正在關閉的視窗；session 活著時鬧鐘是惰性的（`do_run()` 見到活的 session 就退下）。
  結果：第一次 PACE 的回合結束印一行「已安排」，之後靜默（去重），GO 到來時印一行「已取消」。
  取消成功時仍會移除 300 秒的 spawn floor 標記（GO → PACE 五分鐘內回來時需要它）。
  ⚠ 後果說清楚：在 PACE 做完工作就離開的人，會在重置後被喚醒一次去讀一份描述已完成工作的
  HANDOFF —— 與今天 STOP 的暴露相同；畫面那一行與 `resume.py --cancel` 是邊界。
- 留下的檢查（`test_guards.py::case_arm_on_stop`，用記錄器取代 `subprocess.Popen` 與
  `resume.do_cancel`，不會真的登錄或刪除 OS 排程）：mtime 很新但本 session 沒寫過的 HANDOFF.md →
  靜默、log 記「no HANDOFF.md write observed」；Write 的 PostToolUse 會記錄資料夾，Bash 重導向也會，
  不相關的 Write 不會；GO 靜默；PACE 的 `Stop` → 安排最新的**有記錄**資料夾、畫面提示、
  log 帶 `written=2 usable=2`；同一目標只一次；有記錄但過期 / 太短 → 靜默且 log 說明；沒戳記 → 靜默且 log；
  PACE 的 prompt 也安排；掃描根目錄取 session 開始時的 cwd；PACE 的 prompt 保留鬧鐘；GO 的 prompt
  取消並清 floor；下一次 PACE 回合結束能重新安排。突變檢查（五個）見 progress.md。
- ⚠ 這個改動看不到的事：`Stop` 在使用者中斷時不會發出（下一個 prompt 會補上）；兩個 session 共用
  一棵工作樹時，各自只會安排自己寫過的 HANDOFF.md（記錄是 per session 的）；`Stop` hook 是同步等待的，
  透過 `run.sh` 實測每個回合結束約 **1.0 秒**（與本外掛每一次工具呼叫的 hook 成本相同）。
- 需要 Claude Code 2.0.56 以上（既有的最低版本）；`Stop` 事件在該版執行檔中已存在（實測）。

---

## 0.57.0

**燃燒率的歷史把兩個帳號混在一起，而事後沒有任何東西能把它們分開。** 2026-09-02 實測：
兩個 Claude 帳號的五小時視窗重置時間只差 **0.081830 秒**，歷史篩選的容忍度是一秒
（而且 `stamp()` 本來就四捨五入到秒），一列歷史又沒有記帳號 —— 所以兩個帳號的列落在同一個
桶裡。當天的真實歷史已經混了：同一個五小時視窗裡的十三列，七日值出現三個不同的數字，
這在單一帳號裡不可能發生。那次運氣好，新帳號的百分比比較高，所以速率看起來合理
（畫面 0.600 %/min，切換後的列單獨算是 0.653）；反過來會變負數而安靜地變成 `--`，
高很多則會顯示一個大而假的速率，沒有任何提示。

- **每一列歷史現在多一個欄位 `acct`**：`~/.claude.json` 的 `cachedUsageUtilization.accountUuid`
  —— 它就放在 Claude Code 自己快取的數字旁邊，所以不必問「現在是誰登入」。⚠ 只拿它當標籤，
  永遠不拿它的數字（實測那個區塊的 `fetchedAtMs` 落後二十一分鐘）。讀不到就是 `null`，
  不猜。⛔ `userID` 不是帳號 —— 同一台機器兩個帳號實測 `userID` 相同、`accountUuid` 不同，
  它跟的是機器。
- **`_burn_rate()` 拒絕混算**：一列只有在它的 `acct` 已知、目前帳號已知、而且兩者相等時才保留。
  任一邊未知就丟掉。舊的列沒有 `acct`，所以會被丟掉 —— 這是正確的，不是退化。
  ⚠ **接受空白**：切換帳號後，儀表最多 `burn_window_min`（預設 10 分鐘）顯示 `--`。
  那是誠實的答案，比一個錯的數字好。不要拿沒標籤的列來墊 —— 那個墊法就是這個 bug。
- **切換說一次**：`token_usage.json` 也記 `acct`；前後兩次抓取的帳號都已知且不同時，
  在 state 目錄那份 `dispatch_gate.log` 寫一行 `ACCOUNT-SWITCH <前 8 碼>.. -> <前 8 碼>..`。
  未知→已知不算切換，同一次切換不會寫兩次。否則空白的儀表跟壞掉的儀表在畫面上長得一樣。
- 留下的檢查（`usage.py --selftest`）：那次碰撞本身做成 fixture —— 兩個帳號、重置差 0.08 秒、
  兩邊的列在同一個檔案裡，速率必須只從 A 的列算出（A 單獨 1.000 %/min；混算會是 3.500，
  是一個錯的數字而不是空白，所以突變檢查看得到）；沒標籤的列被丟掉；什麼都不剩時給空白而不是
  錯數；每一列新寫入的都帶標籤；切換只記一次。拆掉帳號過濾後實測失敗於
  `rows from two accounts were mixed into one rate: got 3.500 %/min, expected 1.000`；
  拆掉寫 `acct` 那一行後實測失敗於「每一列新寫入的都帶標籤」那一項。
- 「燒錄數字不進 GO / PACE / STOP」那條釘住的檢查照舊通過。
- ⚠ 「最多空白 `burn_window_min` 分鐘」只對預設的**尾端基線**成立。`burn_window_min` 設 0
  時（或任何視窗的前 `burn_window_min` 分鐘內），基線是視窗自己的起點 `(opened, 0)`，
  不看任何一列，所以切換後照樣有數字 —— 對現在登入的帳號而言那是正確的，但不會空白。
- ⚠ 這個修正看不到的東西：標籤只跟 Claude Code 自己寫入 `cachedUsageUtilization` 的時間一樣新
  —— 在那次寫入之前抓到的數字會被貼上**前一個**帳號的標籤，而且會被保留、拉動前一個帳號的速率，
  最多 `burn_window_min`（審查實測：一列這樣的資料把 B 的速率從 0.249 拉到 0.555 %/min）。
  `$ANTHROPIC_TOKEN` 設定時，數字屬於 token 的主人而 profile 不認識他，所以標籤一律「未知」、
  儀表在尾端基線上空白（與 `_account_ids()` 同一個決定；審查第一輪找到的阻斷項，本版已修）。
  `CLAUDE_CONFIG_DIR` 設定時，標籤跟著它走而憑證檔路徑寫死在 `~/.claude/`，兩者可能來自不同
  profile（既有問題，本版只點名）。舊的歷史列永遠不會有 `acct`，不會被修補（owner 決定）；
  Fable / scoped-window 的邏輯完全沒動（owner 於 2026-09-02 接受目前行為）。
- README（兩種語言）的歷史列範例多了 `acct`。

---

## 0.56.2

**0.56.1 那段「指名佔位者」的拒絕訊息，本身可以讓拒絕消失。** 0.56.1 的審查
（`Memory/tasks/20260902-082020-stale-slot-after-a-failed-dispatch/agent-01-adversarial-review.md`）
量到：`slot_ttl_min` 設得夠大時，`held_slots_note()` 裡的 `time.localtime(started + ttl * 60)`
拋出 `OSError(22)`，而那個呼叫就寫在 `deny()` 的參數列裡 —— `main()` 最外層的處理器吞掉例外、
以 0 結束、stdout 什麼都沒有。⛔ **一個什麼都不印的 hook 等於批准。** log 寫著
`DENY(slots-full)`，派工照樣過。為了讓拒絕更安全而加的那幾行字，正是讓拒絕消失的那幾行。

- 那個 note 現在走 `safe_held_slots_note()`：任何例外都換成空字串，並在 gate log 寫一行
  `HELD-NOTE-FAILED <exception>`。拒絕一定會印出來；note 是選配。note 空白時，拒絕訊息改說
  「佔位者列不出來，gate log 有 HELD-NOTE-FAILED 說明原因；位子仍在 N 分鐘後自行清除」，
  而不是「見上方時間」配三行空白。
- ⛔ **同一類的第二個洞，審查在本版找到、本版修掉：`slot_ttl_min` 填錯型別也會放行。**
  `"abc"`、`null`、`"30"`、`[30]` 都讓 `claim_slot()` 在 `cfg["slot_ttl_min"] * 60` 拋
  `TypeError` —— 比 note 更早、在拒絕之前 —— 行程什麼都不印，派工被放行；`false` 或負數則
  每一次派工都回收所有位子，等於併發上限關掉。`gate_config()` 現在對三個數字鍵
  （`slot_ttl_min`、`approval_ttl_min`、`max_slots`）做型別檢查：
  能解析的字串保留、其他一律回到預設值，並在 gate log 寫 `CONFIG-IGNORED(<key>=<value>)`。
  ⚠ `max_model_price` 刻意不在內：它自己有解析規則（接受模型名稱、`null` 等於關閉、
  打錯字時 fail-open 並記 `MODEL-PRICE-LIMIT-UNKNOWN`），`test_guards.py` 釘住這三件事。
  ⛔ 第二輪審查再量到一個：`max_slots` 是 `1.5` 這種正數但非整數時，`range(1.5)` 在佔位與
  釋放兩條路都拋 `TypeError` —— 有併發核准時派工被放行，而且之後再也沒有位子被釋放。
  `max_slots` 現在必須是整數，否則回預設值並記 log；lifecycle 檢查在 `max_slots: 1.5` 下
  透過真正的行程走一次 `PostToolUseFailure`，位子必須被放掉。
- ⭐ `dispatch-protocol` skill 多一段：`--verdict` 那一行同時說「照目前速度，視窗在 N 分鐘後
  用盡，比重置早 M 分鐘」。N 就是預算 —— 把剩下的工作塞進去，在它用完之前寫好交接；
  不要自己算，照那一行印出來的數字行動。（owner 於 2026-09-02 要求，因為這個判斷在本版的
  開發過程中真的救了一次。）
  `test_slot_lifecycle.py` 用六個壞值逐一透過真正的 hook 行程派工，判定都必須是 `deny`，
  而且活著的位子不能被回收。拆掉型別檢查後實測失敗於 `FAIL-OPEN: ... slot_ttl_min='abc'`。
- `--selftest` 多一項：`slot_ttl_min = 1000000000` 時裸的 `held_slots_note()` 必須拋
  `OSError`（否則這項檢查就沒在注入任何失敗），包過的版本必須回空字串並留下那行 log。
  拆掉 `try` 後實測失敗，失敗訊息是 `OSError: [Errno 22] Invalid argument`，不是 `AssertionError`。
- `Tools/Debug/test_slot_lifecycle.py` 多一段：slot0 被佔住時，把
  `{"slot_ttl_min": 1000000000}` 寫進沙盒的 `config.json`，再透過**真正的 hook 行程**派工一次，
  判定必須仍然是 `deny`，而且 log 裡必須有 `HELD-NOTE-FAILED`。⚠ 這裡 `None` 就是 fail-open，
  所以在讀判定之前先以那個名字斷言它。拆掉 `try` 後實測失敗於
  `FAIL-OPEN: the gate printed nothing with slot_ttl_min huge - the dispatch is allowed`。
- ⛔ **最低 Claude Code 版本：2.0.56。** 那是第一個認識 `PostToolUseFailure` 的版本；
  更舊的版本遇到一個不認識的事件名稱，會把該外掛的**每一個** hook 安靜關掉（審查以
  2.0.30 / 2.0.55 / 2.0.56 做最小對照實測）。寫進 `README.md`（兩種語言）與
  `plugin.json` 的 `description`。`install.py --status`（`/dispatch-guard:status` 跑的就是它）
  現在讀 `claude --version`：低於 2.0.56 印 ⛔ 並把 OVERALL 判成 not live；讀不到或看不懂
  一律「unknown」，不會當機、也不會假裝 OK。`test_install.py` 留下比較的檢查：
  2.0.55 → OLD、2.0.56 → OK、2.1.258 → OK、垃圾 / 空字串 / 找不到 `claude` → UNKNOWN。
- `PROTOCOL.md` 第 95 行那一列改成和第 42 行一致：gate 現在有註冊 `PostToolUseFailure`，
  但那個分支只釋放位子並在 `progress.md` 記 `FAILED:`，wind-down 在那裡仍然不會發出。
- 剩餘缺口寫寬：不只「整個 turn 死掉」—— 一個 `subagent_type` 無效的 `Agent` 呼叫，
  兩個終止事件都不會發出，而 turn 照樣繼續。兩種情況都要等完 `slot_ttl_min`。
- 已知但沒修（另開任務）：`test_resume_cancel.py` 寫 703 bytes 進真正的 state log，
  落在 `test_guards` 的視窗裡，所以 `test_all.py` **第一次**跑可能 11/12、之後乾淨。
  記在 `Memory/tasks/20260902-103321-slot-fail-open-and-account-mixing/progress.md`。

---

## 0.56.1

**「已經有 1 個 sub-task 在跑」現在會說出那是誰、跑多久了、幾點自動放掉。**
2026-09-02 在另一台開發機量到：第一次派工被 API 529 打死，`PostToolUse` 沒發生，
那個位子沒被釋放；之後每一次派工都被拒絕；`ListAgents` 顯示零個 agent 活著；
那個 session 判斷紀錄是假的 —— 判斷正確 —— 然後**手動刪掉本外掛自己的強制狀態檔**。

那個位子本來 30 分鐘後（`slot_ttl_min`）會自己被回收，但拒絕訊息從來沒說過這件事。
⇒ **一個看不到盡頭的等待，讀起來就是一個壞掉的 gate。**

- 拒絕訊息現在逐行列出每一個被佔用的位子：desc、派出去的時間、已經過幾分鐘、
  以及「幾點會自動回收」的實際時鐘時間。
- 訊息明講：如果那個派工已經死了，這裡不是卡住，等到那一分鐘再派一次就好；
  ⛔ **不要為了繞過這個拒絕去刪 slot 檔** —— 刪到一個還活著的，同一個位子會被發兩次。
- ⭐ **而且根因不只是訊息：失敗的工具呼叫發的是 `PostToolUseFailure`，不是 `PostToolUse`。**
  外掛以前只訂閱後者，所以**每一個失敗的派工**都會佔著位子直到 30 分鐘 TTL 到期 ——
  不只是被回報的那個 529。2026-09-02 對 Claude Code 2.1.251 實測：一個會失敗的 Bash 呼叫
  只發出 `PreToolUse` 與 `PostToolUseFailure`，兩者帶同一個 `tool_use_id`，
  `PostToolUse` 完全沒有出現。
  ⇒ `hooks.json` 現在訂閱 `PostToolUseFailure`，gate 在那個事件上釋放位子，
  並在 `progress.md` 記一行 `FAILED: <錯誤訊息>`。
- ⚠ 剩下的缺口寫清楚：如果整個 turn 死掉（API 錯誤打死的是父 session，不是那個工具呼叫），
  沒有任何事件會發出來，那個位子仍然要等 `slot_ttl_min`。這正是上面那段拒絕訊息在講的情況。
  ⚠ **（0.56.2 補充）不只這一種。** 一個 `subagent_type` 無效的 `Agent` 呼叫，**兩個**終止事件
  都不會發出，而 turn 照樣繼續（2026-09-02 實測）。兩種情況都要等完 `slot_ttl_min`。
- 新增檢查 `Tools/Debug/test_slot_lifecycle.py`（進 `test_all.py`，現在 12 項）：
  用真正的子行程跑一遍 allow → 被佔用 → 拒絕時指名 → 失敗時釋放 → 再次 allow。
- 回收機制、TTL、原子佔位都和以前一樣。

---

## 0.56.0

**三輪審查通過的那份 ADR，進實作了。** 中心判斷：提醒是建議，模型可以忽略，
所以對抗用量上限的保證必須是 gate 自己做的事 —— arm 一個 resume ——
而那個 arm 不可以先依賴模型做了什麼。

- ⭐ **提醒現在從「每一次工具呼叫」那條路發出。** 2026-08-31 實測：183 次 Read、
  172 次 Write、36 次 Bash、**Agent 零次**，燃燒期間沒有任何使用者輸入 ——
  而舊的兩個觸發點正好是「派工」和「使用者打字」。gate 收到了那些呼叫的每一個，
  然後提早離開。這台機器上所有 gate log 裡，`USAGE(` 出現零次。
- ⛔ **它是「組合」進去的，不是插在前面。** 一次 hook 只能印一個物件，而上面那些分支
  各自 `return` 自己的 —— 插在前面會跳過 `cmd_guards.after_command`（分支紀錄）
  和 `note_skill`（skill 標記），而那兩個正是別的守衛拒絕派工的依據。
- ⚠ **每個等級、每個 agent 只講一次，而且金鑰是 `agent_id`。** 子 agent 的 payload
  帶的是父層的 `session_id`（`transcript_path` 也是）—— 兩者都分不出來。
  ⭐ harness 自己提供 `agent_id` 就是為了這件事。
- ⭐ **沒有派工也能 arm：gate 自己寫一份 handoff**，寫到
  `<state>/handoffs/<session>/`。⛔ **寫進外掛自己的狀態目錄，不是你的 repo** ——
  沒有 marker 的專案裡 `repo_root()` 會跟著 `cd` 跑，所以「一個檔案」會變成
  N 個目錄裡的 N 個檔案。⚠ 它帶一行橫幅說明「這不是 agent 寫的」：實測過，
  一個 390 位元組的毘背檔會通過所有機械檢查，**那行橫幅是唯一分得出來的東西**。
- ⛔ **round 3 的 blocker：`os.chdir` 以前會把整個 resume 靜悄悄弄不見。**
  它在 `resume.py:610`，而所有失敗處理在 `:687`–`:697` —— 目標不在了就拋
  `FileNotFoundError` 從中間逃走：沒有 `resume_failed.json`、沒有重試、沒有取消。
  ⇒ 現在有護欄，依序退到 session 的 cwd、任務資料夾、handoff 自己的目錄，並且記一行。
- ⭐ **`--arm` 現在記錄 SessionStart 的 cwd，不是 STOP 當下的。** payload 的 cwd 會跟著
  Bash 的 `cd` 跑，拿錯的那個會把工作在錯的樹裡叫醒，而且是靜悄悄地。
  ⭐ `<sdir>/state/<sid>.start` 本來就存在、本來就會被清，而它的內容從來沒有人讀。
- ⭐ **arm 的觸發條件抽成一個函式 `arm_trigger()`** —— 下一個判斷（NO-DATA）如果改它，
  只要改那一個地方。
- ⚠ **誠實的缺口，寫進 PROTOCOL.md**：`PostToolUse` 對「失敗的」工具呼叫不觸發
  （提醒放在 `PreToolUse` 就是為了這個）；而 `<state>/handoffs/` 目前沒有任何東西會清。

---

## 0.55.0

- ⭐ **圓點後面補一個空格,前面維持貼齊。** emoji 佔「兩格」,終端機會把它畫進第二格 ——
  所以 `16:31:41🟢5h` 讓圖示壓在 `5` 上面。⚠ 前面補空格會抵消「貼齊」的用意;
  後面補一格只花一欄就解決碰撞。
- ⛔ **`_bar_col()` 以前數的是「字元」不是「欄」**,所以 head 只要帶了 emoji,它回報的位置
  就比眼睛看到的少一欄 —— 而 `_second_row_indent()` 拿它去跟「數欄」的 `_visible_len()` 比。
  ⇒ 兩者剛好差圖示那一格,所以對齊檢查會對一列**其實對齊**的畫面說「沒對齊」。已改成數欄。
- ⭐ **`SLEEP` 這個「字」換成 💤**,和判定圓點同寬。⭐ 這是**拿掉一個特例**而不是加一個:
  一個「字」需要左右各一個空格才讀得出來,一個兩格寬的圖示就坐在每個判定圖示坐的位置。
  ⚠ 字型疑慮是真的,而且是**用量的解決的**:這個 repo 記錄過 emoji 可能畫不出來
  (`7️⃣` 完全沒東西、`🔥` 變成彩色方塊),所以判定狀態才用幾何符號。
  ⇒ 擁有者把 🟢 ⚪ ⚫ 💤 🌙 並排印在那台要畫它的終端機上,五個都正常。
  ⭐ 那是唯一能了結字型問題的測試,而且它勝過推論。⚫ 留作幾何後備。
- ⭐ **新增 `usage.level()`:只回判定的「字」,而且便宜。** 實測同一台機器:
  `verdict()` **28.99 ms**,`level()` **0.471 ms** —— **便宜 62 倍**,而且回同一個字。
  ⛔ 它是一個**參數,不是第二份實作** —— 門檻、重置算術和 7d 規則夠微妙,兩份就是兩次走鐘的機會。
  ⚠ 第一次改的時候我把整個區塊都關掉了,連門檻計算也一起,那會讓它永遠回 GO;
  只能關那兩個貴的呼叫,而且**要一起關**,因為兩個都會重跑 `_burn_rate`。

---

## 0.54.1

- ⛔ **`resume.py` 的紀錄寫在沒有人找得到的地方。** 0.52.1 給 gate 的 logger 加了第二個
  「不會移動」的目的地,但漏掉了 resume.py 自己那個 —— 而它寫的是 `os.getcwd()`,
  也就是「排程器剛好從哪裡啟動」。⇒ 每一行 `ARMED` 和 `RESUME` 都落在其他紀錄不在的地方。
  由審查發現。
- ⛔ **而且它寫「第一個成功的」,不是「兩個都寫」。** 那個迴圈成功之後就 `return`,
  所以第二個目的地是「備援」而不是「副本」—— ⚠ 而 docstring 寫著「and to a fallback」,
  那個 tuple 卻只有一個元素,所以連備援都沒有。**只在另一個壞掉時才出現的副本不是稽核紀錄。**
- ⚠ **檢查的失敗訊息本身也修了。** 第一版直接 open 檔案,所以變異被抓到的時候丟的是
  `FileNotFoundError` 的堆疊,不是一句話 —— 而我自己用 grep 找 `AssertionError` 就漏看了。
  ⭐ 一個失敗訊息需要解碼的檢查,是一個會被誤讀的檢查。

---

## 0.54.0

三個由擁有者當場發現的量測缺陷,全部是「不知道」和「量出來是零」被混為一談。

- ⛔ **Burn 在安靜的時候變瞎,而那正是它該說話的時候。** `_burn_rate()` 的最後一行是
  `if rate <= 0: return None`。2026-09-01 12:48 實測:基準列(12:37,32%)就在那裡,
  live 值也是 32%,差值 0 ⇒「算不出來」⇒ 畫成虛線。
  ⭐ **零是量出來的結果,不是量不出來。** 現在只有「下降」才回 `None` —— 那才是真的
  未知(視窗在量測中間翻頁,或拿過期讀數比對現值)。安靜的時段畫成**滿格 + `.00%`**,
  而滿格的意思本來就是「視窗會比你的額度先重置」。
- ⚠ **`burn_triple()` 和 `_burn_part()` 各自又把 0 和 None 併回去一次**(`if rate else 0`、
  `if rate:`)。⇒ 兩處都改成 `is not None`,否則修好的區分會在下一個函式被抹掉。
- ⭐ **歷史紀錄多了「心跳列」。** 以前只有「數字有動」才寫一行,所以安靜的時段什麼都不寫,
  而一個空隙有兩個時間戳分不出來的原因:**沒有花掉**,或**沒有人在看**(機器關了、
  客戶端關了)—— 而配額是整個帳號共用的,別的座位可能在那段空隙裡花掉了。
  ⛔ 第二種會**低估**速率,那是危險的方向。⇒ 至少每 `burn_window_min` 寫一行,
  空隙就變成「由時間流逝記錄下來的證據」,而不是「要有人抓到的事件」。
  ⚠ 成本有上限:最壞每 10 分鐘一列,而 `history_keep_days` 本來就會整檔按天數清掉。
  ⭐ 這個修法**是程式碼自己的註解在它存在之前就寫好的**,結尾寫著「Not built」。
- ⛔ **視窗剛重置就轉黃。** WARN 那一層是 `pct > time_pct`,沒有任何餘裕 ——
  剛重置完 `time_pct` 趨近 0,所以**花掉第一個百分點就一定黃**。實測 7d 重置後幾分鐘:
  1% 對上 0.48%。而 7d 的時鐘每分鐘只走 0.0099%,所以 1% 會黃上約一百分鐘。
  ⇒ 新的 `colour_warn_margin_pct`(預設 **5** 個百分點)。⚠ 用「百分點」不用「比例」,
  因為對著趨近 0 的基準算比例正是壞掉的原因。上面兩層門檻負責「單純很高」的情況;
  這一層只負責視窗的前中段。
- ⭐ 三個都做了變異檢查,而且三個都有各自的失敗訊息:`AssertionError(None)`、
  `the heartbeat is not firing`、`4 points ahead is inside the deadband`。

---

## 0.53.2

- ⛔ **裸檔名那條規則誤報了,而且是在擁有者的畫面上。** 一份審查提示詞裡有這句散文:
  「write a `HANDOFF.md` into the owner's repository, unasked」—— 那是在**描述**建檔,
  不是在**指示**建檔,而守衛據此警告子 agent 弄丟了報告。⚠ 誤報花掉的正是這個守衛
  唯一的預算:信任。
- ⭐ **修法是排除清單,不是砍掉整條規則,而這是量出來的:** 拿這個 repo 自己的工作單測,
  裸檔名那條找到 **5 個真的報告檔**（`agent-01-implement.md` 之類）,對上這 1 個誤報。
  砍掉整條規則是拿 5 換 1。
- ⚠ **排除只作用在「裸檔名」那條分支。** `Create Memory/tasks/x/HANDOFF.md` 寫了路徑,
  那是真的指示,照樣算數;一個句子裡的裸 `HANDOFF.md` 沒有任何東西可以消歧義。
  清單:`HANDOFF.md`、`PROTOCOL.md`、`README.md`、`CHANGELOG.md`、`CLAUDE.md`、`AGENTS.md`
  —— 都是這個 repo 一天到晚在散文裡提到的文件,永遠不會是某個子任務的報告。

---

## 0.53.1

- ⛔ **0.52.1 造成的回歸，由擁有者發現：檢查會把資料寫進「真的」狀態目錄。**
  0.52.1 之後 gate 的紀錄同時寫到 `usage.state_dir()`，而 `dispatch_gate.py --selftest`
  跑的是真正的決策路徑 —— 所以**每跑一次測試套件，就有 45 行 `DENY(ultracode)`
  進到擁有者自己的紀錄檔**。擁有者問的是「這個 session 沒有開 ultracode 啊?」——
  他是對的，那些行不是他的 session 產生的。
- ⚠ **一個會污染自己要保護的證據的檢查，比沒有檢查更糟。** `--selftest` 現在在進入點
  把狀態目錄導到一個隔離的暫存目錄。
- ⛔ **導向放在「進入點」，不是放在 `selftest()` 裡面**，而這一點是量出來才知道的：
  那個函式有一半是在它自己的 `try/finally` **之後**才跑的 —— 包含產生那些行的 ultracode
  區段。只包住 try 的導向剛好會漏掉它們。
- ⭐ 新增的檢查會在子行程裡解析「真的」狀態目錄，因為 `load_gate()` 會在模組上換掉
  `usage.state_dir` —— 那正是其他案例需要的，也正是會把這個污染藏起來的東西。
  變異檢查：把隔離拿掉，檢查就以「a shipped --selftest wrote into the REAL state
  directory: 108 bytes」失敗。

---

## 0.53.0

- ⛔ **這個外掛印過最有自信的一句錯話刪掉了：「`7d 89% but it resets before this 5h window
  ends - IGNORE, not a constraint`」。** 它叫擁有者忽略當下唯一擋得住工作的那個視窗。
- ⚠ **那條規則問錯了問題。** 它問「這個視窗會不會比我早重置」，⭐ 該問的是
  「**它的剩餘額度撐不撐得到那個時候**」。2026-09-01 在擁有者自己的帳號上實測：
  7d 89%、剩 11%、距離重置 71 分鐘、每分鐘燒 0.30% —— **37 分鐘就燒完**。
- ⛔ **而且舊規則是另一個既有機制的粗糙翻版。** 「這個數字馬上要被清掉，所以可以原諒」
  正是 `_soften_near_reset()` 在做的事，而且它是按「離重置多近」逐視窗判斷。
  ⇒ 舊規則**刪掉**，不是修：只要還沒翻頁就算約束，高不高由門檻決定，
  快重置了原不原諒由 softening 決定。
- ⭐ **resume 的等待目標也跟著修好了，而且這一項有時間可以量：** 5h 0%、7d 99%、
  7d 三十分鐘後重置的情況，舊行為會把 resume 排在**兩小時後**的 5h 重置 ——
  比真正解除封鎖的時刻晚了 **90 分鐘**。現在排在 7d 重置。
- ⚠ **留下來的邊界，寫出來而不是藏起來：** softening 是一個「時間」門檻
  （`near_reset_min`，20 分鐘），不是算術。所以一個在 20 分鐘內、但還是會先燒完的視窗，
  會被放寬一級。⭐ 舊規則是「整個忽略」，新規則最多「差一級」。
- ⚠ 5h 自己的算術**一個地方都沒有改**。擁有者提出「5h 應該以 7d 的重置時間為準」之後
  自己推翻了它 —— 實測六次 5h 重置，7d 一次都沒有跟著動，兩個視窗互相獨立，
  所以 5h 的投影和標記必須用 5h 自己的時間。

---

## 0.52.1

- ⛔ **gate 的紀錄現在寫兩份，而該讀的是第二份。** `repo_root()` 從 payload 的 `cwd` 往上找
  `CLAUDE.md`、`AGENTS.md` 或 `.git`；三個都沒有的專案會直接落回 cwd 本身 ——
  而 Bash 的工作目錄會被 `cd` 帶著跑。⚠ 2026-09-01 實測：一個 session 的紀錄變成
  **四個資料夾裡的四份殘骸**，每一份旁邊還多一個 `.claude/`，而真正出事的那一小時，
  在所有人會去看的那個位置看起來是空的。
  ⇒ 每一行同時寫進 `<state>/dispatch_gate.log`，那個位置不會動。
- ⭐ **這是後面每一步的前提。** 沒有一份不會移動的紀錄，「守衛沒響」和「守衛響了但寫到別的
  地方」在畫面上一模一樣 —— 而這正是這個外掛存在要防的那種失敗。
- ⚠ 兩個目的地互相獨立：一個寫失敗不會讓另一個也不寫。⭐ 每個 repo 自己那一份留著，
  因為那是人第一個會看的地方。
- ⚠ `usage.state_dir()` 可能什麼都回不出來，而 `os.path.join(None, ...)` 會從 logger 內部
  拋 TypeError —— 那會炸掉這個模組每一條失敗路徑都依賴的呼叫。已經擋掉，模組自己的
  `--selftest` 就走到過那個狀況。
- ⭐ 檢查做了變異：把 state 那個目的地拿掉，檢查就以「the state copy missed the line」失敗；
  另外還斷言「root 跑掉的時候，那份固定的副本照樣收得到」。

---

## 0.52.0

- ⭐ **這一列的五項修改，全部是擁有者指定的（2026-09-01）：**
  1. **圓點移到時間戳記和 `5h` 中間，貼齊、兩邊都不留空格**，取代原本那兩個空格。
     ⚠ 但**閒置時那裡是 `SLEEP` 這個「字」不是一個符號** —— `07:26:12SLEEP5h` 讀不出來，
     所以是字的時候兩邊各留一個空格。這是指令沒有涵蓋、但照做會壞掉的情況。
  2. **每個視窗的重置時間，放在它自己的剩餘時間後面加括號**：`21% 4h11m(16:29)`。
     ⚠ 以前只有一個時間掛在整列最後面 —— 看到兩個剩餘時間、一個時鐘時間，
     讀的人分不出那個時鐘時間屬於哪一個視窗。
  3. **7d 只有在「不是今天重置」的時候才標星期**：今天是 `(13:29)`，明天是 `(Wed 14:11)`。
     ⚠ 5h 永遠不標 —— 它到不了明天。
  4. **Burn 的 `/m` 拿掉**，只顯示 `.30%`。⚠ **單位是「每分鐘」，現在只寫在說明文件裡。**
  5. **結尾那兩個空格保留。** ⛔ 它們不是留白，是擋游標方塊用的，檢查斷言的是位元組。
- ⚠ **順帶說明一件量出來的事：畫面上的重置時間沒有錯。** 擁有者提到 5h 應該顯示 1h12m，
  但 API 自己回的就是兩個不同的時間（5h → 15:59:59，7d → 12:59:59）。
  ⛔ **不過「煞車時機會算錯」是對的** —— 錯的是 7d 那條 `IGNORE` 規則，不是顯示。
  那條規則另外處理。

---

## 0.51.5

- ⭐ **`Ctx` 改名成 `CT`，兩個字母，這樣就結束了。** 擁有者的決定，而且它比前面兩版都對：
  `CT ` 在圖表前面佔 3 欄，和 `5h `、`7d ` 完全一樣，所以這個段落**不管在第幾行**都落在第 3 欄。
  ⇒ 空格永遠留著，不用看行數，也不用算任何東西。
- ⛔ **`_tighten_extras()` 和它的正規表示式整段刪掉。** 0.51.4 那套「有第二行才拿掉空格」
  的邏輯不需要存在了 —— ⚠ **四欄沒有辦法對齊到三欄**，這才是真正的問題，前面兩版都是在
  繞過它，而不是解決它。
- ⚠ **失敗的兩次都留在紀錄裡**（0.51.2 補第一行 → 被 harness 剪掉；0.51.3 一律不留空格 →
  一行的時候標籤黏在自己的圖表上），而且檢查裡也留了斷言，所以不會再走回去。
- ⭐ **狀態列和 VS Code 監看工作是同一段程式**（`_line_parts`），所以兩邊一起改到，
  兩邊都實測過：狀態列兩行都在第 3 欄，監看工作兩行都在第 13 欄（它的時間戳記佔前面）。
- ⚠ README 的兩種語言、範例行、表格欄名都跟著改。`longCtxCost` 沒有動 ——
  那是 harness 自己的識別字，不是這個標籤。

---

## 0.51.4

- ⭐ **`Ctx` 後面那個空格，只在「有第二行」的時候才拿掉。** 0.51.3 一律不留空格，
  結果在「全部塞得進一行」的時候變成 `Burn ... Ctx░░░░` —— 標籤和自己的圖表黏成一團。
  ⚠ 那個空格在一行的情況下是有用的：`Ctx` 在行中間，空格是唯一把標籤和圖表分開的東西。
  ⇒ 現在一行保留、兩行才拿掉，因為只有第二行需要用那一欄去換對齊。
- ⭐ **判斷是純算術的，沒有寫死任何段落名稱**：「這個圖表是不是剛好比上面那個右一欄，
  而且前面有一個空格可以讓？」新的第二行段落不用在這裡加任何東西。
- ⚠ **空格是在「組行」的時候拿掉的，不是在「做段落」的時候** —— 做段落的地方還不知道
  會有幾行。而且拿掉之後才量縮排，因為縮排要從「真的會被畫出來的那個字串」算。
- ⚠ **拿掉之後如果圖表還是對不齊，就不拿掉。** 讓出分隔符卻換不到對齊，是白讓的。
- ⭐ 兩個方向都做了變異檢查：永遠不拿掉 → 兩行那個檢查以欄位 3 和 4 失敗；
  永遠拿掉 → 一行那個檢查以「the one-row form lost the space」失敗。

---

## 0.51.3

- ⛔ **0.51.2 的做法「到不了畫面上」。** 那一版在第一行前面補了一個空格；
  ⚠ **外掛真的有印出來**（安裝的 0.51.2 自己的輸出裡 `lead=1`），但 **Claude Code
  在畫之前把行首空白剪掉了**。「量過的修正」和「有效的修正」是兩件事。
- ⛔ **也沒有任何字元可以替代。** 每一個 Unicode 空白都是 Zs 分類，JavaScript 的
  `trim()` 會全部剪掉；零寬字元不佔欄。⇒ 行首永遠對不了齊。
- ⭐ **所以改成第二行自己變窄：`Ctx` 和它的圖表之間不留空格。**
  `5h ` 的圖表在第 3 欄，`Ctx` 直接接圖表也在第 3 欄 —— 兩行對齊，而且**兩行都不以空格開頭**，
  外掛的剪裁碰不到它。
- ⚠ **watcher 沒變。** 它的時間戳記本來就把第一行的圖表推到 `Ctx` 右邊，所以那裡照舊補第二行
  （實測兩行都在第 13 欄）。
- ⛔ **`_second_row_indent` 恢復成只補第二行，而且註解裡寫明為什麼不能補第一行。**
  留著一個「補第一行」的分支比沒有更糟：它會安靜地被丟掉，卻讓人以為對齊有在處理。
- ⭐ 檢查現在同時斷言「兩行圖表同一欄」和「兩行都不以空格開頭」。變異檢查：把 `Ctx`
  後面的空格放回去，檢查就以欄位 3 和 4 失敗。

---

## 0.51.2

- ⭐ **第二行的 `Ctx` 圖表和第一行對齊了** —— 擁有者指定的做法：`5h` 前面加一個空格。
  ⛔ **留白只能往右推。** `Ctx ` 的圖表前面要 4 欄，`5h ` 只要 3 欄，所以「只補第二行」
  永遠對不齊 —— 那個補的量會是負一，然後被夾成 0。實測 CLI：第一行圖表在第 3 欄、
  第二行在第 4 欄，差一欄。⇒ 現在是「哪一邊的圖表比較左，就補那一邊」。
- ⚠ **第一行的留白從它自己的寬度預算裡扣。** 如果補完才算寬度，那一行會比終端機寬一欄，
  而多一欄就會折行 —— 折行正是這一整塊程式存在要防的唯一一件事。
- ⚠ **只有一行的時候不會多出那個空格**，它沒有東西要對齊；watcher 那邊也沒變 ——
  時間戳記讓第一行的圖表本來就在 `Ctx` 右邊，所以那裡照舊補第二行。
- ⛔ **順手修掉一個真的陷阱：`selftest()` 裡有兩個區域變數叫 `_rows`**，把同名的模組函式
  整個遮住了 —— 新的檢查一呼叫 `_rows(...)` 就是 `TypeError: 'list' object is not callable`。
  改名了。

---

## 0.51.1

- ⛔ **`tools:` 寫成 YAML 條列式的時候，會給出「錯的答案」，不是沉默。**
  `.claude/agents/<name>.md` 裡的 `tools:` 有兩種合法寫法。同一行的
  `tools: Read, Write` 一直都對；但換行之後縮排 `- Write` 的那一種，舊的樣式
  會跨過換行、只抓到 `- Read` —— 於是一個「有 Write」的 agent 被判成「寫不了」，
  對一次完全正常的派工發出**誤報**。⚠ 沉默是可以接受的；錯的答案不行。
  實測：`tools:` → `'- read'` → `False`；修好之後 → `'read, write'` → `True`。
- ⚠ **`tools:` 底下什麼都沒有 → `None`（沉默），不是空字串。** 空字串會被讀成
  「一個什麼工具都沒有的清單」，也就是「寫不了」，然後警告；但那其實是「沒有宣告」。

---

## 0.51.0

- ⭐ **0.49.0 那條寫下來的規則變成 hook 了。** 新開關 `guard_agent_report_file`（預設開），
  兩半、⛔ **兩半都不會拒絕**：
  - **PostToolUse —— 真正守得住的那一半。** 提示詞叫子 agent「建立」的檔案，在派工前就算好、
    存進它的 slot，agent 回來時 stat 一次。少了就對模型送一段說明、並在畫面上印一行。
    ⭐ 它不需要知道任何 agent 的工具清單，所以不會過期；而且它抓得到 PreToolUse 那半永遠
    抓不到的情況 —— **有能力寫、但就是沒有寫**。
  - **PreToolUse —— 便宜的提前警告。** 唯讀的 `subagent_type` 配上一份叫它建立檔案的提示詞
    就警告。⭐ **不認識的型別什麼都不說**：對未知型別而言沉默才是對的答案，猜不是。
- ⛔ **唯讀型別是用「名字表」判斷的，不是從工具清單推出來的，而這是這裡最關鍵的一個選擇。**
  `Explore` 宣告成「除了 Agent、Artifact、ExitPlanMode、Edit、Write、NotebookEdit 以外的全部
  工具」—— 也就是說**它有 `Bash`**。所以「看工具清單」的規則會判定 Explore 寫得了檔案，
  然後**剛好漏掉這個 guard 存在要抓的那一次事故**。那個型別是「被指示成唯讀」的，
  而指示不會出現在工具清單裡。⚠ `codex:codex-rescue` 只有 `Bash`，刻意不在表裡 ——
  它透過 shell 寫檔，標記它就是誤報。
- ⚠ **`Edit` 不算「能建立檔案」。** Edit 改的是已經存在的檔案，變不出一個新的 ——
  而「把 `<path>` 建起來當作你的第一個動作」正是它做不到的那一句。
  這也是 `statusline-setup`（Read, Edit）被列進唯讀表的原因。
- ⭐ **`.claude/agents/<name>.md` 的 `tools:` 勝過內建快照**，因為那是那個 repo 裡的現況，
  快照只是另一天的猜測。
- ⛔ **第一版讀提示詞的方式讀不到它自己那次事故 —— 對抗性審查用它自己的例子把它打掉。**
  它是「一行一行」掃的，而那份事故工作單是 `**Your FIRST action:** create` 在一行、
  路徑在「下一行」。拿這個 repo 自己的 18 份工作單實測：舊版只看得到 2 份。
  ⇒ 改成「動詞往後 200 字元的視窗，跨行」，並且在「句子結束」或「跨過一個換行」兩者
  先到的地方停 —— 那個停止點才是讓跨行不變成誤報機器的東西。另外，只寫檔名不寫路徑的
  （`Create agent-01-implement.md`）會用這次派工自己的任務資料夾去解。
  ⭐ **重新實測：抓到 19 個路徑，每一個都是真正的報告檔，零誤報**，18 份裡有 17 份被看到。
- ⚠ **動詞改成「完整字」比對。** `creat`/`writ`/`append` 當字根也會命中 `creative`、
  `rewritten`、`appendix`，然後把那句話剛好提到的 `.md` 當成「agent 遺失的報告」。
- ⚠ **另外兩個實測出來的錯路徑：** 工作單會把長前綴省略成 `.../Memory/tasks/...`，
  接到 repo 根目錄上會變成一個永遠不存在的路徑 —— 「寫好的報告」於是讀成「不見了」；
  而一個沒有名字的 `.md` 會產生 `<資料夾>\.md`，那個路徑永遠不會存在。兩個都修了，
  而且都有各自的檢查案例。
- ⭐ **沉默是「被斷言」的，不是被假設的。** 檢查裡有四個「不該叫」的案例：只叫它「讀」的
  唯讀型別、只有 Bash 的型別、未知型別、任務資料夾以外的路徑。⚠ 一個什麼都叫的 guard
  沒有人會讀。兩半都做過變異檢查：拿掉 `os.path.exists` 那個判斷，「檔案存在時要安靜」
  那條就失敗；拿掉 PreToolUse 的警告條件，Explore 那個案例就失敗。

---

## 0.50.0

- ⛔ **`fetch_seconds` 的下限改回 120，實驗結束。** 0.44.0 把下限調到 60，是為了實測
  「每個 token 大約五次」那個引用數字。⭐ **它照自己寫好的停止條件結束了** ——
  2026-08-31、`fetch_seconds` 設 60、擁有者回報：十分鐘內三次 HTTP 429
  （08:42:59、08:47:30、08:52:01）。⇒ 下限改回 120，小於 120 的設定會被**往上拉回 120**，
  而且會在 stderr 印一行說明。
- ⭐ **兩次實測合起來才是答案，任何一次單獨看都會誤導。** 120 秒間隔：100 分鐘內至少 26 次
  成功呼叫、沒有任何 429。60 秒間隔：幾分鐘內就 429。⇒ 那個「五次」的數字確實差了一個
  數量級，但上限**不是不存在** —— 它落在這兩個間隔之間，目前仍然不知道是多少。
  ⛔ 不要把「26 次成功」讀成「可以再快一點」，那正是這次實測推翻掉的讀法。
- ⚠ **自我檢查現在把 120 寫成字面值，不是寫 `FETCH_FLOOR_SECONDS`。** 兩邊都寫常數的話，
  這個檢查會同意任何人打進去的下限（包括收到三次 429 的那個 60）—— 它會在它存在要抓的那個
  退步裡保持綠燈。新增的案例：30、60、119 都必須變成 120，而 120 原樣通過。
- ⭐ 下限的夾限做過**變異檢查**：拿掉那一行賦值，檢查就以 `AssertionError((30, 30))` 失敗。
  ⚠ 那行 stderr 警告照樣會印 —— 所以「有看到警告」不是證據，斷言才是。

---

## 0.49.0

- ⛔ **每一份提示詞多了第 4 條：寫出 `subagent_type`，而且寫出這份提示詞需要它具備的能力。**
  2026-08-31 實測的事故：一次 ADR 第二輪審查被派成 `Explore` —— 一個唯讀型別 ——
  它建不出提示詞第一行就要求的報告檔，於是把整份審查當成最後一則訊息回傳，
  而**驗證表格和其中五項發現永久遺失**，因為那些內容在派工端從來沒收到的中間回合裡。
- ⭐ **「邊做邊寫」這條規則，對一個寫不了檔的 agent 從第一個動作就是無效的**，
  而且從派工端看是**無聲**的：摘要照樣回來，而且看起來完全正常。
  ⇒ 那次派工只寫了模型、完全沒寫型別，所以這個不匹配沒有任何地方可以現形；
  「需要 Write」那句話，不先去查那個型別的工具清單就寫不出來。
- ⭐ **agent 回來之後 `ls` 一次它的提示詞指名的檔案** —— 真正守得住的是這一步。
  出問題的那個 agent *有*在第一行說了它寫不了檔，還是被漏掉，因為摘要看起來很正常；
  檔案不存在看起來不正常。
- ⚠ **這裡刻意不寫死唯讀型別的清單** —— 和價格表同一個理由。agent 型別由使用者和 plugin
  自行定義（`.claude/agents/*.md`、SDK `agents`），寫進 skill 的快照會過期然後開始說謊。
- ⛔ **這一版是「寫下來的規則」，不是 hook。** gate 既不讀 `subagent_type`，
  也不檢查提示詞要求的檔案有沒有出現 —— 這一條進了 PROTOCOL.md 的「沒有強制」那張表。

---

## 0.48.0

- ⭐ **watcher 那一行的結尾照擁有者指定的樣子重排：** 圓點前面**一個**空格（原本兩個），
  圓點後面隔一個空格接上 **7d 的重置時間**，最後補**兩個**空格。

  ```
  ... Burn ▓▓▓▓▓▓▓░░░ .55%/m 2h16m 🟢 Tue 13:00␣␣
  ```
- ⭐ **時間不寫欄位名稱。** 讀的人看過一次就知道 `Tue 13:00` 是週視窗的重置，
  而多一個 `7d ` 標籤要花三欄 —— 這一行是從右邊往回丟東西的。
- ⛔ **結尾那兩個空格不是留白，不要「順手清掉」。** 終端機會把游標停在最後一欄並畫一個方塊，
  蓋在圓點或時間上就看不清楚了。⇒ 檢查斷言的是**位元組**不是意圖，因為一個把行尾空白清掉的
  整理動作會弄壞顯示，而且不會有任何東西告訴你。
- ⚠ **沒有 7d 視窗就不顯示時間，畫面上不會出現 `None`** —— 而那兩個結尾空格照樣留著，
  因為它們保護的是游標，不是那個時間。
- ⚠ 時間不上色，也刻意排在顏色重設之後：它是事實，不是狀態，上色只會跟旁邊的圓點吵架。
  ⭐ `%a` 在這裡走的是 C locale（Python 啟動時不會呼叫 setlocale），所以是 `Tue` 不是本地化的
  星期 —— 這是量出來的，不是猜的。

---

## 0.47.0

- ⛔ **watcher 不會再把「我們的 hook 死掉」讀成「你回家了」。** 實測 2026-08-30：`.alive`
  卡在 1225 分鐘、機器一直在用、watcher 睡了 20 小時，而 `install.py --status` 全程說
  「everything is live」。原因是 `installed_plugins.json` 指著一個被刪掉的安裝目錄，
  Claude Code 展開 `${CLAUDE_PLUGIN_ROOT}` 之後每個 hook 都靜靜失效。
- ⭐ **「有沒有人在工作」現在看兩個來源，取比較新的**：gate 自己的 `state/*.alive`，
  以及 `~/.claude.json` 的修改時間 —— 後者是 Claude Code 自己寫的，跟我們的 hook 無關。
  ⭐ **記錄器剛好錄到那次失效**：hook 被修好之前那 22 分鐘裡（`.alive` 已經超過 1000 分鐘、
  確定是死的），`~/.claude.json` 被寫了九次，年齡從沒超過 **3.71 分鐘**。
- ⭐ **兩個來源不一致時，時鐘旁邊會出現 `HOOK?`。** ⛔ 放在 `head` 不是放在判定圓點旁邊，
  這是量出來的：`_cut()` 從右邊裁，而圓點是整行最右邊的東西 —— 25 和 30 欄時它會被丟掉，
  而且整行回傳得比終端機還短，沒有任何痕跡說東西被拿掉了。`head` 裡的東西每個寬度都活著。
- ⛔ **`resume.py` 也修了，而且它的失效方向相反、後果更嚴重。** 訊號死掉時 watcher 只是
  安靜下來；排程 resume 會判定「沒人在」然後**照樣跑**，跑在正在打字的人底下。只接到
  stand-down 那個呼叫點（它不帶 session_id），而且**只可能讓它更容易退場，不會更不容易**。
- ⛔ **兩個被否決的候選訊號，理由都只有量測才給得出來：**
  - `projects/*/*.jsonl`（逐字稿）是「一個 turn 寫一次」，所以一個二十分鐘的 turn 有二十分鐘
    什麼都不寫，而 `idle_after_min` 是 15 —— 同一個 bug 換一件衣服。
  - `~/.claude/backups` 是「五個檔案的輪替、會被裁剪」：活下來最新的那個檔案本身可能就是舊的，
    所以它的年齡不等於最後一次寫入的年齡。一個「清理程式跑過就換意思」的訊號不是訊號。
- ⭐ **`$CLAUDE_USER_CONFIG` / `$CLAUDE_CONFIG_DIR` 可以指定第二個來源的位置。**
  ⛔ 用環境變數不是偏好：`test_usage_watch.py` 用 `subprocess.Popen` 起 watcher，
  monkeypatch 一個模組常數過不了行程邊界。**實測**：在這個接縫存在之前，對著一個空的暫存
  狀態目錄 `last_heartbeat_min()` 回傳 0.68 分鐘（真實 `~/.claude.json` 的年齡），
  於是**沒有任何 fixture 能表達「一台閒置的機器」**，四個測試變成寫不出來或走錯分支。
- ⭐ 新增一個測試：`case_dead_gate_beside_live_person`。它讓兩個來源「不一致」，所以只有新的
  那個能產生結果 —— ⚠ 而原本的對照組 `case_active_keeps_drawing` 把兩個來源都設成 0，
  分不出是誰讓 watcher 醒著（實測：它在第二個來源什麼都沒做的版本上照樣通過）。
  ⭐ 這個新測試自己就抓到一個真的顯示問題：`DRAW` 那個正規表示式只認時鐘開頭，
  所以帶 `HOOK?` 的一行「不算一次繪製」，報成「畫了 0 次」。
- ⭐ 三輪對抗式審查，全部 REJECT，七個 blocking 全部修掉。`Tools/Debug/test_all.py` 11/11，
  六個變異全部被殺。ADR 和三份報告在
  `Memory/tasks/20260830-163713-heartbeat-second-signal/`。

---

## 0.46.0

- ⭐ **Burn 錶的「格數」和「顏色」拆成兩個獨立訊號。** 以前兩個都是同一個 `ratio` 算出來的
  —— 兩個視覺通道講同一件事，其中一個是浪費，而且會出現「滿格但黃色」這種難以解讀的組合。
  - **格數**（不變）：這個額度撐不撐得到重置。
  - **顏色**（新）：現在燒得多快，單位是「時鐘速度」的倍數（100 ÷ 視窗分鐘數 =
    0.333 %/min，也就是「剛好在重置那一刻用完」的速度）。
- ⭐ **預設分段 1.00× / 1.75× / 2.25×，是「算出來的，不是挑的」。** 擁有者要求
  紅 10% / 橘 15% / 黃 25% / 綠 50% 的時間佔比並要我回推倍數；用真實歷史（兩個五小時視窗、
  298 個有速率的分鐘）實測是 **49 / 29 / 14 / 7**，而且在四分之一倍數的搜尋裡是最佳解。
- ⭐ **三個分段可以自己改**：`burn_x_yellow` / `burn_x_orange` / `burn_x_red`。
  ⛔ 三個「獨立數字」而不是一個陣列，這是被既有程式碼逼的：`config()` 只在值是
  `int`／`float` 時才從磁碟複製，陣列會被「安靜忽略」，使用者會拿到預設值卻以為改到了。
  ⚠ 必須遞增，不遞增就印一行並且「三個一起」退回預設 —— 半套是誰都沒選過的校準。
- ⛔ **零格一律紅色，不管速度多少。** 零格是 `ratio < 0.05`：實測 remain=119 分時涵蓋
  burnout 0～5 分，要回到滿格需要減速 **24～119 倍**，或根本不可能。⇒ 任何做得到的減速都
  改變不了結果，所以「要不要降速」沒有有用的答案；而在「空 = 危險」的欄位裡，空長條配綠色
  說的是跟事實相反的話。
- ⚠ **代價，擁有者明確接受了：光看顏色不能下判斷，兩個訊號都要讀。** 滿格配紅 = 燒很兇但
  視窗剛開，不用降速；短格配綠 = 已經龜速但撐不到，降速也救不了。
- ⛔ **`burn_window_min` 和分段是綁在一起的。** 實測：15 以上紅色「永遠不會出現」，5 則有
  15～16% 的時間根本算不出速率。所以校準用 10。改了這個值，`install.py --status` 會提醒你。
- ⭐ 新增 `Tools/Debug/burn_band_fit.py`：讀「你目前設定的」分段，用你自己的歷史算出各色
  佔比並給判定。⚠ 它放在這裡而不是任務資料夾，因為 ADR 的「什麼情況要重新檢討」需要一個
  「跑得起來」的指令 —— 任務資料夾是整包封存的。
- ⭐ 兩輪對抗式審查，兩輪都 REJECT，五個 blocking 全部修掉：空長條變綠色、「不用接新東西」
  是錯的、F5「只有 10 會出四色」是錯的（5 也會）、B1 的理由對六個狀態裡的五個不成立、
  以及漏掉發版機制。ADR 和兩份報告在
  `Memory/tasks/20260829-133237-burn-two-signals/`。
- ⭐ 七個變異全部被殺，對照組通過。⚠ 那四條舊斷言是「改寫」不是刪掉 —— 實測拆開之後
  **只有第一條會失敗**，另外三條會「因為新的理由而繼續通過」，整套測試變綠但一條都沒在守。
  `Tools/Debug/test_all.py` 11/11。

---

## 0.45.0

- ⭐ **多了一個 WARN 狀態，而且它只有顏色。** 只要五小時長條圖的填滿「超過它自己的 ┃」
  —— 也就是你花得比時鐘快 —— 圓點和長條圖一起轉黃。
  🟢 GO、🟡 WARN、🟠 PACE、🔴 STOP、⚪ 還沒有資料。
  ```
  13:20:00  5h ▓▓▓▓▓┃░░░░ 51% 2h29m 7d ▓▓▓▓░┃░░░░ 40% 2d23h Burn ────────── --  🟡
  ```
- ⛔ **WARN 進不到 `verdict()`，這是刻意的。** `dispatch_gate.py` 有「四個地方」拿判定字
  去比字面 tuple（`not in ("GO", "PACE")`、`not in ("PACE", "STOP")`），多一個字會
  **安靜地改變煞車的行為**。擁有者的話是「只變色不做任何處理」，所以 WARN 在
  `_state()` / `display_state()` 這一層產生，跟 `SLEEP` 走同一條路。
  ⚠ 它只把綠變黃，永遠不會把真正的 PACE 或 STOP 變軟。
- ⭐ **長條圖和圓點現在共用同一組配色**，所以看哪一個都是同一個答案。
  上面兩層仍然讀 `colour_warn_pct` / `colour_alarm_pct`（預設 70 / 85，跟判定一致），
  WARN 沒有自己的門檻設定值 —— 那個 ┃ 標記本身就是條件。
- ⭐ **時間格式不再印出 0。** `0h32m` 現在是 `32m`，`3h0m` 是 `3h`，`4d0h` 是 `4d`。
  ⚠ 消失的永遠是「小的那個單位」：把 `3h0m` 的 `3h` 拿掉會被讀成三分鐘。
- ⭐ **API 撈取的強制下限從 120 秒降到 60 秒，預設值仍然是 120。** 下限和預設是兩個不同的
  數字了。⛔ 這不是調校，是為了讓「每個 token 大約只能打五次」那個說法「可以被實測」——
  它一直完全建立在別人的文件上。實測 2026-08-29、120 秒間隔：100 分鐘內至少 26 次成功
  呼叫，`fetch.log` 從來沒被建立過，整個狀態目錄裡找不到 429。⇒ 那個數字大概差了一個
  數量級。⚠ 停止條件寫在 `FETCH_FLOOR_SECONDS` 上面：一小時內出現 429 就改回 120。
  ADR 和一輪對抗式審查在 `Memory/tasks/20260829-124223-fetch-floor-60s/`。
- ⭐ **`burn_window_min` 預設從 30 改成 10。** 讀數是「整數百分比」，所以 10 分鐘基線一階
  是 0.1%/m（30 分鐘是 0.033），錶會靈敏三倍，安靜的時候直接顯示 `--`。
  ⚠ 安全只有一個理由，跟 `_burn_rate()` 本來就寫著的一樣：**任何燃燒率數字都到不了
  GO/PACE/STOP。**
- ⭐ 六個變異全部被殺（`_state()` 的 WARN 層、`>` 變 `>=`、`display_state()` 蓋掉
  PACE/STOP、圓點改用百分比上色、`duration()` 的去零、`verdict()` 吐出 WARN），
  對照組通過。⚠ 其中「圓點顏色」那個第一次是**活下來的** —— 因為旁邊的長條圖剛好也是
  黃的，斷言分不出來；現在改成斷言跳脫碼「緊貼在圖示前面」。
  `Tools/Debug/test_all.py` 11/11。

---

## 0.44.1

- ⛔ **段落標籤的圖示收回來了 —— 在擁有者的終端機上，它們畫不出來。** 螢幕截圖:
  那個 `7️⃣` **什麼都沒有**，`🔥` 變成一個彩色圓點。⇒ 四段裡有兩段直接失去標籤，
  而寬度計算還在替它們各留兩欄。**一個字型可能沒有的字不是節省，是空白。**
  ```
  12:02:02  5h ▓▓▓░░░┃░░░ 34% 1h52m 7d ▓▓▓▓┃▓░░░░ 54% 3d22h Fable ▓▓▓░┃░░░░░ 31% 3d22h Burn ▓▓▓▓▓▓▓▓▓▓ .17%/m 6h36m  🟢
  ```
- ⭐ **只留最後那個判定圓點。** 那四個是幾何符號，字型覆蓋率比表情符號高得多，
  而且截圖裡它們畫得好好的。PACE 照擁有者說的用 🟠。
- ⭐ **這一版沒有把 0.44.0 全部退掉。** 一格間隔、短時間格式（`3d22h`）、
  燒盡尾巴（`.17%/m 6h36m`）都留著 —— 那些是**文字**，不靠字型有沒有某個字。
  整行 119 欄（圖示版 109，原本 141）。
- ⭐ **`_cols()` 那個寬度計算也留著。** 行尾那個圓點就是兩欄寬的字元，還是要算對；
  而且它現在也把 CJK 算對了，那是這個檔案原本就知道自己不會的事。

---

## 0.44.0

- ⭐ **整行改用圖示，擁有者一項一項指定的。**
  ```
  11:23:40  🕒▓▓▓░░┃░░░░ 33% 2h6m 7️⃣▓▓▓▓┃▓░░░░ 54% 3d23h 🚀▓▓▓░┃░░░░░ 31% 3d23h 🔥▓▓▓▓▓▓▓▓▓▓ .30%/m 3h43m  🟢
  ```
  🕒 五小時、7️⃣ 七天、🚀 模型視窗、🔥 燒盡速度；判定字換成 🟢 GO、🟠 PACE、🔴 STOP、⚪ 沒資料。
  段落間隔從兩格改一格，圖示緊貼自己的 bar，燒盡尾巴縮成 `.30%/m 3h43m`
  （開頭的 0 只在它是 0 時省掉 —— `1.20%/m` 那個 1 是有意義的）。
  **整行從 141 欄降到 109 欄。**
- ⛔ **判定圖示只在畫面上。** gate 拿到的還是 `GO`/`PACE`/`STOP` 那個**字** —— 換掉的話，
  派工邏輯會收到一個它不認識的值。轉換發生在組裝那一行的地方，別的地方都沒有，
  跟 `SLEEP` 早就遵守的規則一樣。
- ⛔ **寬度計算重寫了，而這是整批改動裡唯一危險的部分。** 以前是「數碼位」，
  那只有在每個字都一欄寬時才對 —— `BAR_FULL` 的註解本來就寫著「CJK 會歪掉」。
  一個表情符號是**兩欄**，`7️⃣` 更是**三個碼位假裝成一個字**（數字 + 變體選擇符 + 圍框記號）。
  ⇒ `_cols()` 現在分三種：W/F 兩欄、變體選擇符和組合記號零欄、圍框記號一欄。
  ⚠ **`_cut()` 也一起改成照「欄」切**，不然 25 欄的預算會切出 26 欄的行 —— 實測過。
  **算錯一欄就會換行，而換行正是這個 watcher 唯一修不好的事。**
- ⛔ **順手修掉一個會過期的檢查（跟這批改動無關）。** `test_guards.py` 有一句
  「回填 25 小時的本地表要輸給比較新的種子」，而那個種子是 repo 裡的檔案、時間固定 ——
  於是它在種子滿 24 小時的那一刻開始失敗，而且不是因為程式壞了。實測 2026-08-29：
  種子 24.09 小時，整套測試變紅。⇒ 現在那一句的時間點是**從種子本身算出來的**。
  ⚠ 第一次改的時候我直接動 `now`，結果連累下面量 24 小時間隔的兩句 —— 改成只影響那一句。

---

## 0.43.0

- ⛔ **watcher 改回「一行」，而這是終端機決定的。** 擁有者的最後一張截圖是決定性的：
  加了「每次重畫前清整個畫面」之後，VS Code 面板**把三次完整的兩列重畫疊在一起**，
  一份都沒被清掉。⇒ 那個面板**連 `\033[2J` 都不理**。
  對照：在加第二列之前，那一行一直好好地原地更新。

  | 指令 | 那個面板 |
  |---|---|
  | `\r` + `\033[K` | ✅ 有效 |
  | `\033[1A`、`\033[H`、`\033[2J` | ⛔ 全部無效 |

  ⇒ 只有「不用垂直移動」的那一組有效，而那一組只能重畫一行。**兩列在那裡做不到。**
- ⭐ **擁有者選了「回到一行，把時間寫短讓 Burn 塞得下」。** `duration()` 從
  `4d-0h-16m` 變成 `4d0h`（超過一天就不印分鐘 —— 四天後的一分鐘是雜訊，三小時後的不是）。
  整行含 `Burn` 從 **141 欄降到 129 欄**。
- ⭐ **`_redraw()` 現在只送 `\r` + 那一行 + `\033[K`，而且拿到第二列會 assert 失敗。**
  安靜地只畫一半，是「改主意的呼叫者」最容易溜過去的方式。改完後**重新錄一次位元組**確認：
  整條 stream 裡沒有換行、沒有任何 `\033[` 移動指令。
- ⚠ **`Burn` 還是會被丟掉，如果面板窄於 129 欄** —— 一行就是這樣，塞不下就從右邊丟。
- ⛔ **順手修掉我自己弄壞的東西：這個檔案裡有 22 個「真的 ESC 控制字元」。** 前面幾版的編輯
  把 `\033` 這四個字寫成了那個位元組本身，於是 CHANGELOG 變成一個帶控制字元的檔案，
  在畫面上看起來只是少了幾個字。⚠ 這正是「產生完要回頭讀真正被吃下去的成品」那條規則在講的事。

---

## 0.42.1

- ⛔ **`\033[H` 也不夠,而這次是把位元組錄下來才知道的。** 擁有者確認跑的是 `0.42.0`
  (PID 31008),畫面照樣卡一行。⇒ 把 watcher 寫到 stdout 的**每一個位元組**攔下來看:
  ```
  <ESC>[2J<ESC>[H<ESC>[?7l              ← 開場
  <ESC>[H<CR>第一列<ESC>[K<LF><CR>第二列<ESC>[K<ESC>[J   ← 每次重畫
  ```
  **沒有雜訊、沒有任何相對移動、順序完全正確。** ⇒ 程式送出去的是對的,
  是那個終端機把 `\033[H` 放在跟這個行程認知不同的地方。
- ⭐ **所以不再依賴「原點在哪裡」:每一次重畫之前,整個畫面清掉。** 清過的畫面上只剩這一次
  畫的東西,**沒有東西可以被卡住** —— 不管終端機怎麼想。
  ⚠ 代價是每 `--every` 秒整頁重畫一次;兩列、三十秒一次,沒有人看得出來。
  要是哪天 watcher 變成很多列又畫很快,那個小心翼翼的版本才需要回來。
- ⚠ **我仍然不知道那個終端機為什麼不把 `\033[H` 當成第 1 列。** 這一版不是回答那個問題,
  是讓那個問題不再重要 —— 連猜四次之後,這比再猜第五次有用。
  突變殺過:把每次的清畫面拿掉 → `AssertionError('\033[H
a<K>')`。

---

## 0.42.0

- ⛔ **不再「往上爬」。第四次,而且這次是拿到證據才動手的。** 擁有者的截圖配上行程清單:
  跑的是 `0.41.5`(PID 3224,起始 `11:01:18`),而畫面上卡住的那一行**就是 `11:01:18`** ——
  **第一次畫的那一行**。之後每一次重畫都乾乾淨淨。
  ⇒ 在第二次畫之前,游標就已經比算式以為的低一列了。**修算式永遠碰不到這個。**
- ⭐ **改成絕對定位:每次都 `\033[H` 回到左上角重畫整個畫面。** `\033[1A` 是「從**現在**的位置
  往上一列」,只有在沒有別人動過游標時才對 —— 而在 VS Code 面板裡,那不是這個行程管得到的
  (截圖左邊那個 `⊙` 就是它自己加的裝飾)。`\033[H` 是「螢幕的第 1 列第 1 欄」,不是位移,
  所以誰動過游標、行有多寬、上次畫幾列,全部都不影響。
- ⭐ **合法的原因是 watcher 啟動時已經清過畫面,整個畫面是它的。** 跟別人共用終端機的程式
  絕對不可以這樣做 —— 這一點寫在函式的註解裡。
- ⭐ **結尾的 `\033[J` 讓「變少」也不用數。** 從游標清到畫面底部,所以列數變少不可能留下舊的;
  舊的做法是用空白列去補,而那要知道上次有幾列。
- ⛔ **舊的 `_rewrite()` 整個刪掉了**,連同它追蹤的 `rows` 變數 —— 留著一個沒人呼叫的相對移動,
  下次就會有人把它接回去。突變殺過:把 `\033[1A` 放回去 → `AssertionError('\033[1A
a<K>')`。
- ⚠ **前三次(0.41.3 清畫面、0.41.4 固定列數、0.41.5 關折行)都留著,而且都不是白做** ——
  每一個都真的修掉一種殘影,只是都不是擁有者遇到的那一種。

---

## 0.41.5

- ⛔ **殘影撐過了清畫面(0.41.3)也撐過了固定列數(0.41.4)。第三個原因:終端機自己折行。**
  一列跟面板一樣寬、或比它寬,終端機會把它折成**兩個視覺列** —— 這時 `\033[1A` 往上爬的是
  **一個視覺列**,不是一個邏輯列,`
` 就回到錯的那一列的開頭,被折斷的上半永遠留在畫面上。
  ⭐ 這正是 `_watch_line()` 開頭那段註解一直在講的原始缺陷,只是它假設「把行寬修好就不會發生」。
- ⭐ **修法:重繪期間把終端機的自動折行關掉(DECAWM `?7l`)。** 關掉之後,太長的行由**終端機**
  在右邊界截斷,游標**留在原來那一列** —— 於是不管寬度量得對不對,爬幾列都不會錯。
  ⚠ **這是「量寬度」永遠治不好的**:寬度可能量完就被使用者拉過(resize),也可能根本量不到
  (`COLUMNS` 沒設、又拿不到 tty 尺寸)。關掉折行是把這一整類問題移除,不是再猜一次寬度。
- ⛔ **離開時要還回去(`?7h`)。** 折行是**終端機的模式**,不是這個行程的;留著不還,
  下一個在那個終端機跑的東西就會在右邊界被吃掉。用 `atexit` 註冊,正常結束、Ctrl-C、
  沒接到的例外三種出口都會還。
- ⚠ **這是第三次修同一個症狀,而且我沒有證明就是這個原因** —— 我沒辦法從這裡量到你面板的寬度。
  ⭐ 五秒的驗證法:**先不要更新,直接把面板拉寬一大截**。如果殘影立刻不見了,那就是折行;
  如果照樣有,那就是第四個原因,這次的修改也白做。

---

## 0.41.4

- ⛔ **殘影的真正原因:watcher 的「列數會變」。** 0.41.3 清了畫面,擁有者的第二張截圖還是有 ——
  這次看得很清楚:`10:30:24` 畫 **1 列**(那時候還沒有 burn 速率),`10:30:54` 畫 **2 列**,
  中間那一次 1→2 的成長就把舊的那列留在畫面上了。
- ⭐ **修法是「把這個轉換拿掉」,不是把游標算式修對。** 成長時的游標算式本來就是對的,
  而且釘住了 —— 但它假設「中間沒有別人動過游標」,而在 VS Code 面板裡那不是這個行程管得到的事。
  ⇒ 沒有速率的時候就畫 `Burn ────────── --`(狀態列本來就是這樣畫「還不知道」的),
  **列數永遠是 2**,沒有轉換就沒有東西會出錯。
- ⭐ **順帶一個好處:gauge 不會再用「整列消失」來表示沒資料。** 要嘛是速率、要嘛是虛線,
  兩種都看得見。
- ⚠ **推翻了一條舊規則,而且理由已經不成立。** 舊的檢查寫著「塞得下就只畫一列,不然每個
  watcher 都會多長出一列空白」—— 現在第二列永遠有 gauge,不可能空白。
- ⚠ **第二列的順序是 gauge 先、note 後。** gauge 是**有 bar 的**那一段,而第二列就是靠 bar
  對齊的;note 排在前面會讓兩列又看起來不相干。⇒ 窄到塞不下時被丟掉的是 note,
  跟這裡其他每一列的「由右往左丟」是同一條規則。
  突變殺過:沒有 burn 時走回舊的單列路徑 → 檢查立刻失敗。

---

## 0.41.3

- ⭐ **watcher 啟動時清一次畫面,舊行程留下的殘影不再卡在上面。** 擁有者的截圖:一列的舊版
  draw 卡在兩列的新版 draw 上面,看起來像「兩列壞掉」。⛔ **那不是重繪的 bug** ——
  1 列→2 列的成長本來就是原地覆蓋(`
a<K>

b<K>`,而且早就釘住了)。
  問題是那一行是**上一個行程**留下的:會重繪的 watcher 只搆得到自己起始的那一列,
  上面那列一輩子搆不到。
- ⭐ **清畫面只發生在「會重繪」的模式。** 一個一直覆蓋自己那一列的畫面,scrollback 本來就沒意義;
  要保留歷史的人用 `--scroll`,那條路徑**一個位元組都不輸出**。
  ⚠ 代價是連工作的 `Executing task` 標頭也一起清掉 —— 所以它綁在「會重繪」而不是無條件執行。
  突變殺過:讓它回傳空字串 → `AssertionError('')`。

---

## 0.41.2

- ⭐ **兩列的 bar 對齊了。** 擁有者:「可以將圖表對齊嗎?」以前第二列是照**時間戳寬度**縮排的,
  而那對不齊任何東西 —— `5h` 兩個字、`Burn` 四個字,bar 就差兩欄,兩列看起來像不相干的兩行。
  現在縮排是**從字串量出來的**(找第一個 bar 字元在第幾欄),所以以後多一個新標籤也不用改這裡。
- ⭐ **`Burn` 的 bar 也加寬一格,變成 `BAR_WIDTH + 1`** —— 跟 `Ctx` 一樣。另外三條帶著 `┃`
  標記,那個標記卡在格子中間,害它們多佔一欄;窄一格的 bar 不管怎麼縮排都對不齊。
  ⚠ **只比對齊欄位抓不到這個** —— 兩條 bar 起點一樣、終點不一樣。所以是分開釘的。
  兩個都突變殺過:縮排改回照時間戳 → `not in one column: 13 vs 15`;寬度改回 `BAR_WIDTH` →
  `AssertionError((9, 'Burn ...'))`。
- ⛔ **收回一個我在 0.41.0 寫錯的說法。** 那一版的註解、CHANGELOG 和 README 都說
  「CLI 狀態列只有一列,第二列會被丟掉」—— **那是錯的。** 同一個檔案裡的 `line_rows()`
  早就從出貨的 binary 量過:Claude Code 會把輸出照換行切開來數,狀態列**可以**兩列。
  正確的理由是**擁有者要求 CLI 那邊不要動**,不是平台做不到。三處都改了。

---

## 0.41.1

- ⛔ **`--status` 現在會說「你的 watcher 在跑舊版」。** 擁有者更新了外掛,畫面卻還是舊的那一行。
  原因:`claude plugin update` 會把**舊資料夾留在原地**,而 shim 記的是一個確切路徑,
  只有在那個路徑**不見了**才會自己找新的 —— 於是它永遠不會換。
  ⚠ **當時每一項檢查都是綠的**:工作是最新的(它的指令裡沒有版本號)、狀態列是最新的、
  shim 記的路徑確實存在。沒有人問的那一個問題是「它是不是**最新的那一份**」。
- ⭐ **修法是「開一個新的 Claude session」,不是重開 VS Code,也不是重裝。** gate 在 session
  開始時就會把 shim 指回來。⚠ 然後要**重開 watcher 終端機**,跑著的行程不會自己換程式碼。
  這兩句話現在就印在那一行警告底下 —— 沒有動作可做的警告等於沒有警告。
- ⭐ **它只報告,不修。** `--status` 是唯讀指令,在裡面順手修好會讓下一次執行跟這一次不一樣,
  而讀的人看不出為什麼。
- ⚠ **從開發 checkout 跑 `--status` 不會誤報** —— 比對的對象是**已安裝的那一份**,不是這支腳本
  所在的資料夾。那是既有 VS Code 工作檢查早就踩過的同一個坑。
  突變殺過:把那個比對改成永遠相等 → `an older shim was not reported`。

---

## 0.41.0

- ⭐ **`outlasts reset` 改成一律顯示時間。** 擁有者的指示:「文字敘述佔欄寬又不容易理解」。
  現在永遠是 `11h-52m left` —— 照現在速度撞到 100% 還要多久。
  ⚠ **這個時間可以比視窗剩餘時間還長,而那是正確的**:剩 `4h-24m` 就重置、燒完要 `11h-52m`,
  就代表你花不完。「重置先到」這件事**那條滿的 bar 本來就在講**,不需要再用字說一次。
- ⭐ **watcher 現在顯示完最後一條用量條就換行,`Burn` 自己佔一列。** 也是擁有者的指示,
  而且它順便補掉 0.40.7 量到的洞:面板窄於 141 欄時 `Burn` 會被無聲丟掉,於是「沒有 Burn」
  同時代表「沒資料」和「你面板太窄」,畫面上分不出來。給它一列之後,它永遠都在。
  ```
  09:35:01  5h ░┃░░░░░░░░ 5% 4h-24m  7d ▓▓▓▓┃▓░░░░ 51% 4d-1h-24m  Fable ▓▓▓░┃░░░░░ 31% 4d-1h-24m  GO
            Burn ▓▓▓▓▓▓▓▓▓ 0.13%/m · 11h-52m left
  ```
- ⛔ **CLI 狀態列完全沒動,這是擁有者指定的。** Claude Code 只給狀態列一列,第二列會被丟掉。
  換行是 `_watch_line()` 傳 `always_split` 進去的,`_line()` 不傳 —— 檢查兩邊都釘住了。
- ⚠ **原地重繪兩列是本來就支援的。** `_rewrite()` 按**上一次畫了幾列**往上爬(不是這一次),
  那個方向性早就是量出來並且釘住的。實跑 `--watch --every 3` 確認過,兩列穩定更新。
- ⭐ **只在「真的有 Burn 可以搬」的時候才強制換行。** 無條件換行會把 note 和模型名也推到
  第二列,那沒人要求過,而且既有檢查釘住了。突變殺過:把 `always_split=split` 改成 `False`
  → 檢查立刻失敗,錯誤訊息就是那條擠在一起的單列。

---

## 0.40.8

- ⭐ **`outlasts reset` 現在有解釋了。** README 之前把這句話印在範例裡,卻從來沒說它是什麼意思 ——
  擁有者只好開口問,那就是這份文件缺了一塊的量測結果。
  ⇒ 它在**比兩個時鐘誰先到**:「照現在速度燒到 100% 還要多久」對上「這個 5 小時視窗還多久歸零」。
  `outlasts reset` = 重置先到,你花不完;`1h-20m left` = 燒完先到。
- ⭐ **那條 bar 是那個比值,不是存量。** 所以它會**往上跑** —— 慢下來 bar 就變長。
  顏色也是反的:滿是綠、短是紅,跟其他段落的「數字越高越糟」相反。
- ⚠ 順手把 `%/m` 說清楚:那是**最近 30 分鐘**的每分鐘燒掉幾 %,不是整個視窗的平均。

---

## 0.40.7

- ⭐ **「Burn 不見了」有答案了,而且是量出來的:終端機不夠寬。** 擁有者的 watcher 上完全
  沒有 `Burn` 這一段。⛔ 資料是好的 —— 同一時刻 `burn_triple()` 回
  `(579, 282, 0.167)`,`_line_parts()` 也確實把 `Burn ▓▓▓▓▓▓▓▓▓ 0.17%/m · outlasts reset`
  放進第一列。把寬度從 100 掃到 190:**141 欄以下就不畫**。那一行有 Burn 是 141 欄,
  沒有是 100 欄,VS Code 下方面板常常只有 110～130。
- ⚠ **這是刻意的行為,不是 bug。** `Burn` 是四段裡的最後一段,終端機不夠寬時第一個被丟掉,
  丟掉的永遠不會是用量條 —— 煞車看的是那些。selftest 早就釘住這件事了。
  ⛔ **但它被丟掉的時候畫面什麼都不說**,而「沒有 Burn」有兩種完全不同的意思:
  `Burn ───────── --` 是「還沒有資料」,整段不見是「終端機太窄」。README 現在把這兩種
  並排寫出來,因為看畫面分不出來。
- ⭐ **沒有改任何程式碼。** 版面規則是刻意的而且有測試釘著;缺的是一句話,不是一個功能。

---

## 0.40.6

- ⭐ **安裝那一節重寫成兩條路,而且都只有步驟。** 擁有者的指示:最上面先給一段
  「複製貼上就全部做完」的指令,再給介面選單的做法,兩邊都不要解釋,想看的人自己往下翻。
  ⇒ `## 安裝` 現在是 **A. 一段貼完** 和 **B. 用介面選單一步一步做**,底下原本那些長篇
  說明整段保留,改名成 `## 說明區 —— 上面每一步在做什麼`。
- ⭐ **A 那一段包含 `task.allowAutomaticTasks`,而且結尾就是驗收。** 從
  `claude plugin marketplace add` 一路到 `install.py --status`,四件事一次做完:
  外掛、CLI 狀態列、VS Code 工作、自動工作的權限。
  ⛔ 開頭第一行寫的是「**在開 VS Code 之前跑完**」—— 這樣就贏了 0.40.4 量到的那場賽跑。
- ⭐ **貼的那幾行是照著跑過才寫進去的**,不是照抄舊段落:實際執行到
  `resolved installPath = ...0.40.0` 和 `OVERALL : everything is live`。
- ⚠ **B 那一段誠實說「只有第 1 步沒有選單」** —— 外掛只能從 CLI 裝。把它寫出來,
  比讓人在選單裡找一個不存在的東西好。

---

## 0.40.5

- ⭐ **兩台機器的快照都到齊了,「賽跑」這個結論被證實,而且同步和信任兩個嫌疑都排除了。**
  ⛔ 關鍵是**起點一模一樣**:第一次開啟之前,`tasks.json` 在**兩台**都是 `(no such file)`。
  ⇒ 「那台好的是靠 Settings Sync 早就拿到檔案」是錯的 —— 它也沒有。

  | | 視窗開啟 | hook 寫出工作檔 | 差 | 結果 |
  |---|---|---|---|---|
  | 好的那台 | `08:59:19` | `08:59:41` | **22 秒** | ✅ 自己起來(`watch.alive` 08:59:56) |
  | 壞的那台 | `08:43:20` | `08:43:55` | **35 秒** | ⛔ 什麼都沒有 |

  ⇒ 差 **13 秒**。同一個機制、同一個起點,只有 session 啟動快慢不同。
- ⚠ **README 裡那個「8 秒 vs 35 秒」是舉例,不是量出來的,已經換成上面這組真數字。**
  一個看起來像測量值的舉例,就是這個 repo 到處在拒絕的東西。
- ⛔ **`.gitignore` 的快照規則太窄。** 原本只擋 `vscode-snapshots/`,而第二台機器的快照
  是用**自己的名字**進來的(`-working`)—— 第一次比對就會把別人的機器 commit 出去。
  改成 `Tools/Debug/vscode-snapshots*/`,並用 `git check-ignore -v` 驗過。

---

## 0.40.4

- ⛔ **0.40.3 講得太滿,這一版推翻它。** 那一版說「寫出這個工作的那一次開啟,永遠跑不到它」——
  **「永遠」是錯的。** 實驗 D:乾淨的 VS Code,啟動時**故意不放** `tasks.json`,
  等 log 印出 `RunAutomaticTasks: Trying to run tasks.` **之後**才把檔案丟進去:
  ```
  08:58:04.671  Trying to run tasks.
  08:58:04.682  taskNames=[]                                   ← 找不到
  08:58:05.444  updated taskNames=["Claude Usage Watcher"]     ← 跑了
  ```
  ⇒ VS Code 找不到自動工作時會**再等 10 秒**,檔案在那 10 秒內出現就**會**跑。
  ⭐ 正確的說法是「一場**賽跑**」,不是「不可能」。
- ⭐ **這也解釋了為什麼有的機器裝完開起來就好,有的不會** —— 差別只是那個 session
  在視窗開啟後幾秒才啟動。實測一台:視窗 `08:43:20` 開,hook 在 `08:43:55` 才寫檔,
  **35 秒,輸了 25 秒**。另一台贏了,就「沒問題」。
- ⭐ **要必贏,就在開 VS Code 之前先在終端機跑一次安裝腳本。** 檔案先在,就沒有賽跑。
  README 和 `--status` 兩邊的說法都改掉了。

---

## 0.40.3

- ⛔ **真正的原因找到了,而且不是 0.40.2 說的那個。** 擁有者拍了三份快照,差異只有一個:
  **第一次開啟的時候,`tasks.json` 根本還不存在**(`(no such file)`),第一次開完才有它。
  而第一次和第二次之間,那個檔案**一個位元都沒變** —— 差別只是「它已經在了」。
  ⇒ 使用者層級的工作檔一樣是 session 寫出來的,而 session 在視窗開起來**之後**才啟動,
  所以**寫出這個工作的那一次開啟,永遠跑不到它**。第二次就正常,之後每個專案都正常。
- ⚠ **0.40.2 講的 workspace trust 是真的機制,但不是這次的原因。** 那三個隔離實驗沒有錯 ——
  信任關掉的資料夾確實會安靜地不跑 —— 只是擁有者的機器上,擋住的是「檔案還不存在」。
  兩個都留著:`--status` 現在**先講**這個常見的,trace log 那一套留給「不是這個」的時候。
- ⭐ **README 的說法改正了。** 它本來說使用者層級的檔案解決了「第一次開啟」的問題。
  它解決的是**第二個以後的每一個專案**;安裝完的那一次它救不了,原因跟舊版一模一樣。
  現在寫清楚了,並且給了涵蓋那一次的方法:**開 VS Code 之前**先在終端機跑一次安裝腳本。

---

## 0.40.2

- ⭐ **量出來了:擋住自動啟動的是 WORKSPACE TRUST。** 三次隔離實驗,每次只動一個變因,
  用 `--user-data-dir` 開乾淨的 VS Code,`--log trace` 讀它自己的判斷:
  | 實驗 | 信任 | 擴充套件 | log 裡的結果 |
  |---|---|---|---|
  | A | 關閉 | 無 | `taskNames=["Claude Usage Watcher"]` ✔ 跑了 |
  | B | 關閉 | **全部真的擴充套件** | `taskNames=["Claude Usage Watcher"]` ✔ 跑了 |
  | C | **預設(開啟)** | 無 | ⛔ **一行 `RunAutomaticTasks` 都沒有** |
  ⇒ 擴充套件拖慢啟動**不是**原因(B 推翻了它);資料夾沒被信任才是,而且它在
  `RunAutomaticTasks` 印出第一行 trace **之前**就 return,所以連 log 都是空的。
- ⛔ **上一版教的看 log 方法是錯的,改掉了。** `Developer: Set Log Level...` 是**來不及的** ——
  自動工作的判斷發生在視窗啟動當中,事後調等級,log 一樣是空的(實測:`renderer.log` 全是
  `[info]`)。正確作法:**關掉所有 VS Code 視窗**,再用 `code --log trace <資料夾>` 開。
- ⭐ **新工具 `Tools/Debug/vscode_snapshot.py`。** 擁有者問的正是對的問題 ——
  「第一次開不會、第二次開會」是一個**差異**,單看一次讀數答不出來。它把決定這件事的
  五個地方(含三個沒人能用編輯器打開的 SQLite)倒成純文字,`--diff` 比兩份快照。
  ⚠ 快照要在 **VS Code 關掉**的時候拍。⛔ 快照內容是那台機器開過的每一個資料夾路徑,
  所以進了 `.gitignore`,不會被 commit 出去。
- ⭐ **它自己有 selftest,而且進了 `test_all.py`(11/11)。** 因為一個壞掉的比對會印
  `no difference` —— 那也正好是「機器沒變」的正確答案,看不出來。selftest 種一個已知的
  改動,沒被報出來就失敗。

---

## 0.40.1

- ⛔ **`--status` 把「舊名字的工作」報成「沒有工作」。** 改名落地那個小時就發生了:
  畫面上寫 `⛔ NOT in tasks.json / No usage terminal will open`,而那個工作就在那裡,
  一樣是 `runOn: folderOpen`,一樣會開終端機。現在它有自己的一句話 ——
  「在,但是舊名字」,而且說清楚那不是「不會開」,是「移除工作的程式碼搆不到它」。
  ⭐ 突變殺過:把那個分支關掉 → `an old-label task did not report as an old-label task`。
- ⭐ **自動啟動失敗的時候,現在說得出「怎麼看到原因」。** 從 VS Code 1.135.0 出貨的
  workbench bundle 讀出來的:`RunAutomaticTasks` 在**找工作之前**就把自己的
  `_hasRunTasks` 立起來,找不到就等 `onDidChangeTaskConfig` **10 秒**,等不到就
  **整個視窗放棄**;資料夾還沒被信任時則是**安靜地 return**(而 `Tasks: Run Task`
  是會跳信任視窗的)。⛔ 兩種放棄都只寫在 **Trace** 等級的 log 裡,別的地方一個字都沒有 ——
  所以 `--status` 現在直接給那一串:`Developer: Set Log Level...` → Trace → 重開 →
  `window1/renderer.log` 搜 `RunAutomaticTasks`。
- ⚠ **這個版本沒有讓自動啟動變得比較會成功。** 那是 VS Code 那一邊的競態,外掛動不了。
  它只是把「什麼都沒發生」變成「看得到是哪一條分支」。

---

## 0.40.0

- ⭐ **工作改名為 `Claude Usage Watcher`。** 擁有者的指示。VS Code 的 Run Task 清單、
  專用終端機的分頁名稱、通知裡引的那一句,全部跟著改。
- ⛔ **舊名字沒有被忘掉,而這才是重點。** 只教寫入端新名字的改名,會把舊的
  `Claude usage watch` 工作原封不動留在 `tasks.json` 裡 —— 它一樣是 `runOn: folderOpen`,
  於是每次開資料夾就開**兩個** watcher 終端機,而且移除工作的程式碼再也搆不到它。
  `install.py` 的 `LEGACY_TASK_LABELS` 記著每一個用過的名字,寫入、判斷「是不是最新」、
  移除、`Tools/clean-dispatch-guard.ps1` 全部認兩個名字。
- ⭐ **檢查用突變殺過。** 把 `LEGACY_TASK_LABELS` 從 `ours()` 拿掉 →
  `AssertionError: ['Claude usage watch', 'Claude Usage Watcher']`,也就是那兩個終端機。
- ⚠ **已經開著的那個舊終端機不會自己改名,也不會自己關。** 它是上一次開資料夾留下來的;
  重新開啟資料夾,或手動關掉它。

---

## 0.39.2

- ⛔ **「已過期」那一句也拿掉了。** 擁有者的指示:「『已過期』也不顯示」。
  `token_note()` 整個刪除,兩個顯示端 —— CLI 狀態列和 watcher —— 都不再回報 OAuth token。
- ⭐ **到期時間還是會讀,那一半不能跟著刪。** `fetch()` 靠它拒絕在一個「從檔案上就看得出
  已經死掉」的 token 上,花掉端點只允許的五次呼叫其中一次。
- ⚠ **仍然有一句 OAuth 到得了畫面,而且是刻意留的。** 那是 `fetch()` 的失敗理由,走一般的
  失敗回報路徑,而且**只有在存下來的數字也過期之後**才出現 —— 那一刻畫面上的數字就是錯的,
  這時候安靜下來,正好就是這個外掛到處在拒絕的「有自信的錯答案」。要連這一句也不要,說一聲。
- ⭐ **檢查用突變殺過。** 把 `token_note()` 放回去 →
  `token_note() is back - the bar must not report an OAuth token`。
  ⚠ 釘的是「符號」而不是「畫出來的那一行」:狀態列和 watcher 各自組自己的 note,
  對其中一行做文字斷言,看不到另一行。

---

## 0.39.1

- ⛔ **OAuth 倒數那一行不再顯示。** 擁有者的指示:「OAuth 那行不要顯示」。
  它原本在 token 壽命剩下十分鐘時開始警告,而那個警告**會自己好** —— 哪一個 Claude
  用戶端在跑,就會在到期前大約五分鐘換掉 token。所以常態是:一行出現、被讀到、
  什麼都不用做、然後自己消失。一則學會被忽略的訊息,會連旁邊那些訊息的可信度一起賠掉。
- ⭐ **「已過期」那一句留著。** token 死了就不再撈資料,整條線的數字全變成 `--`,
  而那一句是螢幕上唯一說明原因的東西。把它也拿掉,只會剩下一條什麼都不解釋的空長條。
- ⭐ **檢查用突變殺過。** 把倒數放回去 → `a live token warned: the countdown is back`。
  ⚠ 它用「剩 60 秒的**活** token」去測,那在舊警告的每一個門檻之內,所以倒數不管
  從哪條路回來都會被抓到,不會靠一個剛好的門檻矇混過去。
- ⭐ **watcher 現在先講「不用 reload 的那條路」。** F1 → `Tasks: Run Task` →
  `Claude usage watch`,在你人已經在的那個視窗直接開起來。
  ⚠ 自動啟動仍然要等資料夾開啟,而且**外面的程式做不到**:VS Code 1.135.0 的 CLI
  沒有任何選項可以叫一個「已經在跑的視窗」執行工作(實測整份 `code --help`)。
  ⇒ 這個缺口一台機器只會遇到一次 —— 使用者層級的 `tasks.json` 寫過一次之後,
  以後每一次開啟資料夾都自己來。
- ⛔ **`/dispatch-guard:status` 不再被回報成「Shell command failed」。** `--status` 只要
  有東西沒活著就回傳 1,而一個 `!` 指令回傳非零,harness 就會印出失敗、並把整份報告
  丟到 stderr —— 一份完全照設計運作的報告,在人正要靠它除錯的那一刻,看起來像壞掉的
  指令。⚠ 現在後面接一個 `echo`:真正的退出碼原封不動印出來,什麼都沒有被消音。

---

## 0.39.0

- ⭐ **計量條改看最近 30 分鐘，而不是整個 5 小時視窗。** 新參數 **`burn_window_min`**（預設 30）
  讓你自己調。⚠ **0 = 整個視窗**（穩，但要一個多小時才會發現速度變了）。
  ⛔ 小於 5 會被抬到 5 **並且在畫面上說出來** —— 更短的基準線量不出速度，設 2 不會讓計量條變靈敏，
  是會**把它永久關掉**。
- ⛔ **修掉一個 bug：`_burn_rate` 收下 `now` 卻一次都沒讀。** 它的終點是「最後一筆有紀錄的資料」，
  而歷史**只在數字有變化時才寫入** —— ⇒ 閒置時分子和分母**兩端一起凍結**，那個數字根本沒有在重算，
  只是同一個值被重畫。⚠ 實測（真實視窗）：閒置 84 分鐘後速度高報 **39%**、見底時間早報 **78 分鐘**。
  現在終點是 `now` 和當下的 `pct`。
- ⭐ **起點是「`burn_window_min` 分鐘前用掉多少」。** 一筆紀錄的值會一直有效到下一筆為止
  （沒變化就不會寫），所以「切點之前最新的那一筆」可以直接當成「切點當時的值」。
  ⇒ 基準線是**真正的 30 分鐘**，不是「上一筆剛好在多久以前」。
- ⭐ **視窗開頭的錨點留著，在它有效的範圍內。** 視窗開始後的前 30 分鐘，切點會落到視窗開頭以前，
  而視窗開始必定是 0% —— 這時候一筆紀錄都不需要。
- ⛔ **這個數字現在是刻意會抖的。** 端點只給整數百分比，30 分鐘基準線上一階就是 **0.033 %/分**，
  安靜的視窗上這個量化階梯就是訊號的大部分。實測真實歷史：25 分鐘基準線在半小時內
  **0.407 → 0.040 %/分**，而同一段時間整段視窗的數字只從 0.150 動到 0.137。
  ⇒ 之所以可以接受抖，只有一個理由：**沒有任何燃燒數字會進到 GO / PACE / STOP**，這件事有檢查釘住。
- ⚠ **實測本機的差別**：同一刻，最近 30 分鐘 **0.23 %/分**，整段視窗 **0.053 %/分** —— 差 4.4 倍。
- ⚠ **有一個前提寫在程式碼註解裡**：紀錄的空白有兩種原因，時間戳分不出來 —— 沒有花費（讀數正確），
  或**沒有人在記錄**（Claude Code 關了、機器關機）。而額度是**整個帳號共用**的。
  ⇒ 第二種情況會低報速度，方向偏危險。⛔ 「進入睡眠」標記解決不了：真正麻煩的關機正是那個
  **來不及寫任何東西**的關機。解法是**心跳紀錄**，還沒做。

---

## 0.38.2

- ⛔ **`--status` 把自己剛授予的權限報成「沒設定」。** VS Code 的使用者 `settings.json`
  是 JSONC —— 註解和多餘的逗號都合法，`json.load` 兩個都不收。`--status` 用 `load()` 讀它，
  所以整個檔案讀回來是空的，裡面每一個設定都變成「沒設定」。
  ⚠ 這不是邊角情況：`allow_automatic_tasks()` **授予權限的時候就寫了一行 `//` 註解**，
  所以一台被這個外掛授權過的機器，從那一刻起永遠回報「⛔ not set」。
  實測 2026-08-29（另一台開發機）：任務在使用者層級、正確、就位，`--status` 說權限沒開，
  而人直接讀檔案看到的是 `"on"`。⇒ 終端機沒開的時候，那一行是唯一能問的東西。
- ⭐ **改讀原始文字，而且讀的是「值」不是「鍵」。** `automatic_tasks_value()` 用一個行首
  錨定的樣式把值取出來。⛔ 不能用 `allow_automatic_tasks()` 的子字串測試：那個測試在
  「授予」那邊是對的（它的偏誤是絕不覆蓋別人已經選的值），在「回報」這邊會把 `"off"`
  講成允許，也會把一行**被註解掉的**設定算成有設定 —— 而註解掉正是人表達「我不要」的方式。
- ⭐ **檢查用突變殺過。** 換回 `json.load` → `JSONC read as unset`；換成子字串 →
  `off read as allowed`。兩個都在 `dispatch_gate.py --selftest` 裡。
- ⚠ **授予的政策沒有動。** 權限仍然只在「這次呼叫真的安裝了任務」時才寫進使用者設定。
  一個 hook 每個 session 偷改別人的編輯器設定，正是這個外掛到處在避免的驚嚇。

---

## 0.38.1

- ⛔ **煞車不讀燃燒速度，而且這件事現在被釘住了。** 擁有者的指示：
  「GO / PACE / STOP 派工或剎車都不參考這個值，先只畫圖顯示最近的燃燒速度就好。」
  ⚠ 舊的 pin 只守住「推估」，而 `burnout_min` 是**第二條進得去的路** —— 它在 `verdict()` 裡
  算、被回傳、還會寫一句話進文字。多一個 `if` 就會讓它變成煞車。
- ⭐ **這個檢查是用「強迫」做的，不是用「讀」的。** 兩個數字都被推到最壞
  （「1 分鐘後燒完」、「推估 999%」），而百分比離 `soft_pct_5h` 還有二十三點。
  判定必須維持 **GO**。⚠ 檢查也斷言強迫**有到達**那兩個數字，否則它會因為根本沒跑到那條路
  而假通過。
- ⭐ **警告照樣發出**，這正是設計本身：一句話，不是一個決定。
- ⚠ **整個燃燒計量條的研究擱置**，寫進 `Memory/notes/SHELVED-burn-meter.md`：
  量到了什麼、哪兩個先前給出去的數字**被推翻**、哪些想法**已經否決不要再提**、
  還有為什麼「先收 log 再決定」是划算的（歷史存的是原始讀數，換估算法不會讓資料失效）。

---

## 0.38.0

- ⭐ **燃燒速度改從「視窗自己的開頭」算起。** 視窗開始的那一刻必定是 0%，
  所以 `(reset − 5 小時, 0%)` 是一個**不需要任何人紀錄**的資料點。
- ⛔ **不補的話，忙碌的後半段會代表整個視窗。** 紀錄不是從視窗開頭開始的 ——
  重裝、第一次執行、機器關著都會少一段。實測（另一台機器，2026-08-28）：
  視窗 **14:10** 開始，第一筆紀錄是 **16:49，當時已經用掉 35%**。
  只讀有紀錄的部分算出 **0.48 %/分**，而整個視窗的真實平均是 **0.22 %/分**。
- ⚠ **錯的方向也跟著換了，這是要知道的部分。** 以前紀錄開始得晚會**高估**速度（偏安全）；
  補上錨點之後，一個「先閒置很久、然後爆發」的視窗會**低估**速度（偏危險）。
  ⇒ 接受這個代價只有一個理由：**這個數字現在不影響 GO / PACE / STOP**，它只是給人看的儀表。
  如果哪天推估要重新納入判定，這個錨點必須跟著重新檢討。
- ⭐ **只有一筆紀錄也能算了**，因為第二個點是視窗的開頭。以前這種情況回傳「無法得知」。
- ⚠ **實測這不是「一律變寬鬆」**：同一台機器 21:14 那一筆，
  補上前段之後是 **149 分鐘見底**，只看有紀錄的部分是 154 分鐘 ——
  沒紀錄的 11.7 分鐘裡燒掉 7%，比後面有紀錄的那段還快。

---

## 0.37.0

- ⛔ **推估暫時不再影響 GO / PACE / STOP，改成純顯示。** 程式碼是**註解掉的，沒有刪**，
  重新啟用只是把一行的註解拿掉。
  ⚠ 原因是實測的：用另一台機器的真實歷史重播，判定在**十二分鐘內翻了三次**
  （GO→PACE→GO→PACE→GO），而百分比一路平順從 **40% 爬到 52%**，
  從頭到尾離 `soft_pct_5h` 70 還有二十幾個百分點。
  ⇒ 臨界值是 `(100 − pct) ÷ 剩餘分鐘`，所以在 47%、剩 114 分的時候，
  速度差**百分之一**就會跨過去 —— 而一波派工造成的速度變化遠大於此。
- ⛔ **而且 0.35.0 之後 PACE 是有代價的**：它讓「當前的 HANDOFF.md」變成派工的前提。
  ⇒ 一次因為抖動而閃現的 PACE，會擋掉一次本來該放行的派工，
  而這個外掛自己的規則「看那個字，不要看百分比」，被一個**自己在抖的字**架空了。
- ⭐ **重新啟用之前要補的兩件事，寫在程式碼註解裡**：
  ⑴ **遲滯** —— 進 PACE 用 ≥100%，回 GO 要 <90%；單一門檻碰上會抖的輸入只會顫振。
  ⑵ **最少歷史** —— 紀錄不是從視窗開頭開始的。那台機器視窗 14:10 開始、紀錄 16:49 才有，
  當時已經用掉 35%。⇒ 忽略沒紀錄的前段，等於拿「比較忙的後半段」代表整個視窗：
  **0.48 %/分 對上全視窗平均 0.22 %/分**。
- ⭐ **燃燒計量條照常顯示**，會依情況變色 —— 這正是要觀察的東西。
- ⛔ **重置時刻收斂到最近的整分。** 實測：同一個視窗的歷史裡同時有 `19:10:00` 和 `19:09:59`。
  ⚠ 取「最近」而不是「一律進位」：`19:10:00.2` 進位會變成 19:11，整整差一分鐘，
  而且是往「視窗看起來比較長」的方向錯。
- ⭐ **閒置那一行只留需要動手的訊息。** `2 min old` 和 `idle 15m` 都在重複 `SLEEP`
  已經說完的事；⚠ 只有 OAuth 快到期留下來 —— 那是唯一一個「你不在的時候會壞掉」的東西，
  而你不在正是沒有人盯著它的時候。
- ⚠ `/Debug/` 進入 gitignore：那是為了診斷從**別台機器**抓來的真實用量資料，
  不該進入公開儲存庫，也不是這個儲存庫的狀態。

---

## 0.36.0

- ⭐ **燃燒計量條，常駐在用量長條後面**：`Burn ▓▓▓░░░░░░ 1.20%/m · 44m left`。
  ⇒ 它回答一個往前看的問題：**我還可以繼續燒嗎**。長條量的是「預算還能撐多久」相對於
  「這個視窗還剩多久」—— **滿格 = 這個視窗會在你燒乾之前先重置**。
  ⚠ 它是比值不是存量：慢下來會「回升」，因為它量的是兩個時鐘會不會交叉。
- ⛔ **這一段的顏色是反的**，而且**不能**用 `colour_warn_pct` / `colour_alarm_pct`：
  其他地方百分比高是壞事，這裡滿格是好事，共用門檻會把「安全」畫成紅色。
- ⛔ **「算不出來」絕不畫成空長條或 0。** 在一個「空 = 危險」的欄位裡，
  把「沒資料」畫成空的，說的是跟事實相反的話。它顯示 `───────── --`。
- ⚠ **第一版設計是 sparkline，砍掉了**，因為它答錯問題：歷史只在「數字真的動了」才寫一行 ⇒
  安靜一小時**不會**畫成低格，它**根本不會出現**。那個橫軸看起來像時間，其實不是。
- ⚠ 成本實測 **2.47 毫秒**／次渲染，狀態列每 `refresh_seconds` 才畫一次。

---

## 0.35.0

- ⛔ **handoff 從「STOP 時要做的事」變成「派工的前提」。** 舊設計假設 agent 撞到 STOP 時
  還有一個回合可以寫 —— ⚠ 而真正的強制中斷（伺服器直接拒絕）**不給那個回合**，
  於是 resume 醒來時硬碟上沒有任何東西說明剛才在做什麼。
  ⇒ 用量讀到 PACE 或 STOP 之後，任務資料夾裡沒有「當前的」HANDOFF.md 就**拒絕派工**。
- ⭐ **「過期」是獨立的一種狀態，而且是長度檢查看不到的那一種。**
  三個視窗以前寫的 handoff 檔案存在、長度也夠，但描述的是已經不存在的工作 ——
  而一個照著錯誤指示動作的 resume，比一個「知道自己在重建」的還糟。
  ⇒ 三種狀態分開回報（沒有／只是佔位／過期），因為補救方式不同。
- ⭐ **`require_handoff_past_soft`，預設 true。** 兩種失敗並不對稱：拒絕是「大聲的」、
  代價是一次檔案寫入；不拒絕是「安靜的」、代價是一整個視窗。
  ⚠ 它只擋「派工」，而且 soft 門檻以下永遠不觸發。
- ⭐ **設成 false 會改變兩件事**（設定檔註解裡兩件都寫了）：派工放行，而且 `--arm`
  不再因為沒有 handoff 而拒絕 —— resume 改用一份**重建提示詞**醒來。
  ⛔ 那份提示詞把來源**按成本排序**並附**絕對路徑**（progress.md → git → 任務資料夾），
  「禁止」讀 session 逐字稿，「禁止」重做已經 commit 的工作，
  並且把寫 handoff 當成**第一個動作**，這樣下一次中斷才不會一模一樣。
- ⭐ **`auto_arm_resume`，預設 true。** arm 是唯一一個「漏掉就救不回來」的步驟。
  它 arm 給「這次派工的那個資料夾」，排在「正在擋住你的那個視窗」的重置；
  ⛔ 而且**只 arm 一次** —— 除非重置目標移動了（煞車從 5h 翻成 7d），那時候會重新 arm。
- ⚠ `HANDOFF.md` 和 200 字元底線現在只有**一份定義**，在 gate 裡（resume.py 本來就 import 它）。
  兩份門檻就是兩次「gate 拒絕、resume 卻接受」的機會。

---

## 0.34.0

⛔ **從舊版更新請先跑 `Tools/clean-dispatch-guard.ps1` 再重裝**，或者手動把 config 裡的
`soft_pct` / `hard_pct` / `seven_day_binding_pct` 改成下面四個新鍵 —— 舊名一律**不再讀取**。

- ⛔ **煞車以前完全不看七天視窗。** 它只讀五小時的百分比，七天的數字只產生一句**文字**、
  從來不影響判定。⇒ **7d 99% 配 5h 0% 會被判成 `GO`**，然後一直派工到「伺服器」拒絕為止。
  兩個數字都是真的，答案是錯的 —— 這是 owner 回報的。
- ⭐ **一個視窗一對門檻，共四個：**

  | 鍵 | 預設 |
  |---|---|
  | `soft_pct_5h` | 70 |
  | `hard_pct_5h` | 85 |
  | `soft_pct_7d` | 95 |
  | `hard_pct_7d` | 97 |

  ⚠ 7d 那一對故意設得高：那個視窗通常不是限制，在 70% 就 PACE 會白白拖慢一整週的工作。
- ⭐ **兩個視窗取比較嚴的那個，而且判定會講出是哪一個在管。** 看到 `5h 0%` 旁邊寫著 STOP
  又沒被告知原因的人，會認為煞車壞了 —— 而一個被認為壞掉的守衛就是一個會被關掉的守衛。
  ⚠ 平手時算五小時的，因為那是比較近、比較可行動的那一個。
- ⛔ **七天的 STOP 和五小時的 STOP 不是同一個指令。** 續跑要排在「七天」的重置之後，
  那可能是好幾天以後，判定文字會直接這樣寫。
- ⚠ **軟化是「逐視窗」判斷的。** 距離重置很近時門檻會軟化一級 —— 五小時視窗還剩 12 分鐘的
  STOP 值得軟化，七天視窗還剩三天的不值得，而共用一個判斷會把兩個一起軟化。
- ⛔ **順手修掉一個會把整週丟掉的早退。** 五小時視窗「已經重置」時，程式以前會**當場回 GO** ——
  所以一個週額度已經燒光的帳號，在五小時視窗一翻頁的瞬間就被告知 GO。
- ⚠ `seven_day_binding_pct` 移除，那句「BINDING」現在用 `soft_pct_7d` 判斷。一個東西一個名字。

---

## 0.33.0

- ⛔ **`--watch` 的整行比終端機寬，所以每一次重繪都留下一列殘骸。**
  ⚠ 成因不是看起來那樣：`_line()` **本來就會**裁到寬度 —— 是 `watch()` 又在前面加了時間、
  後面加了判定字，**16 欄沒有人扣掉**。實測寬度 150：中間那段 149 字元，送到終端機的是 **165**。
  ⇒ 換行了，而 `\r` 只回到**最後一個視覺列**、`\033[K` 只清那一列，
  所以每次重繪都把自己的第一列永遠留在畫面上。
- ⭐ **閒置時只畫一次，然後停止重繪。** 這一條把缺陷從根上移除，而不是緩解：
  **沒有東西在重繪的行，不管多寬都不可能留下殘骸**，閒置的機器也不會整夜捲出一堆一樣的行。
  ⚠ 醒來之後會重置，所以下一段安靜期一樣會標記自己。
- ⭐ **閒置那一次的內容不變 —— 數字保留、不上色、判定字變成 `SLEEP`。**
  （owner 的規則：凍住的數字在「抓取失敗」時才危險，**沒有人在工作就沒有人在花**。
  風險只在恢復工作那一刻，而 `should_fetch()` 同一刻就恢復抓取。）
  ⚠ `SLEEP` 只在畫面上，**永遠不會進到 `verdict()`** —— gate 讀那個函式判 GO/PACE/STOP。
- ⭐ **資訊太多的時候改用兩列，而不是把東西丟掉。**
  用量長條和判定字留在第一列，Context 長條、模型、說明移到第二列，**兩列各自裁到寬度**
  （兩列各自會換行，就是原本那個缺陷發生兩次）。就地重繪會把游標移回上一列；
  列數只增不減，所以不再使用的那一列會被**清掉**，而不是留著一行沒人會覆蓋的舊字。
- ⭐ **模型限定視窗的圖表**（這個帳號有在跑的話）。⛔ 回應裡**沒有**「能不能用」的欄位，
  這是實測不是假設：兩個帳號的擷取裡那一列**都在**，`is_active` **兩邊都是 false**
  （19% 時也沒翻），而 `nimbus_quill` 在那一列讀 19% 時仍然是 0.0 —— 那是**反對**它是
  Fable 對應欄位的證據。⇒ 所以這一條回答資料回答得了的問題：**有沒有一個限定視窗正在跑**
  （`percent > 0` 或 `resets_at` 有值）。⚠ 有權限但這週沒用過的帳號會看不到，直到第一次使用。
  ⭐ 模型名稱不寫死 —— 那一列自己會報名字。
- ⭐ **這個五小時視窗會在幾分鐘後燒光。** 「照這個速度到重置時是 175%」講了會用完，
  沒講**什麼時候**，而「什麼時候」才決定還有沒有空間再派一波。
  ⛔ 它和推估**共用同一次取樣**：兩次取樣會在邊界不一致，於是同一行上會出現
  「projected 175%」旁邊寫著「重置後才會用完」。
  ⚠ `None` 的意思是**算不出來**，永遠不是「安全」—— 沒有歷史、只有一列、跨度不到五分鐘、
  速率平的或在下降，四種都回 None，而且每一種都有檢查。
- ⚠ 那段 110 字元的說明也縮短了：OAuth 警告拿掉「open a Claude session to refresh it」，
  閒置說明從「no session active for 7h-35m; not fetching」變成「idle 7h-35m」。

---

## 0.32.0

⛔ **從舊版更新請先跑 `Tools/clean-dispatch-guard.ps1` 再重裝。**
這一版把每一個名字統一了，而且**不保留任何舊名相容**。

- ⭐ **一個東西一個名字。** 起因是 owner 發現自己在 config 裡寫的鍵名和文件寫的不一樣，
  於是那個開關一直沒有生效 —— 而**沒有任何東西會說**。

  | 舊 | 新 |
  |---|---|
  | `debug.token_usage_history` | `debug.token_usage` |
  | `limits.json` | `token_usage.json` |
  | 設定鍵 `limits_file` | `token_usage_file` |
  | `token_usage_history-<戳記>.jsonl` | `token_usage_history_<戳記>.jsonl` |
  | `usage-response-<戳記>.jsonl` | `API_response_usage_<戳記>.jsonl` |
  | `model_prices.spawn` | `model_pricing.spawn` |
  | `dispatch-gate.log` | `dispatch_gate.log` |
  | `dispatch-gate-error.log` | `dispatch_gate_error.log` |
  | `resume-failed.json` | `resume_failed.json` |
  | `asked-vscode-task` | `asked_vscode_task` |

- ⭐ **規則寫下來了**：這個外掛自己的東西一律 snake_case，連字號只出現在時戳裡；
  副檔名說明「格式」（`.json` 一份文件、`.jsonl` 一行一筆、`.log` 純文字）；
  標記檔一律 `<主題>.<種類>`。⚠ 唯一的例外是 `API_response_usage_*`，
  它跟設定開關 `debug.API_response_usage` 完全同名，那比規則一致更有用。
- ⛔ **`.jsonl` 沒有改成 `.json`，這是刻意的。** 那兩個檔是一行一個 JSON，
  改副檔名會讓 `json.load()` 直接爆掉、編輯器從第 2 行開始整份標紅。
- ⛔ **舊名一律不再被讀。** `keep_history`、`token_usage_history`、`limits_file` 都不再有效；
  舊檔名的 log 也不再被讀取或清理。⚠ 所以一份還寫著舊名字的 config 拿到的是**預設值**。
- ⭐ **`install.py --status` 會把 config 裡每一個已廢棄的鍵點名並標成 `⛔ IGNORED`。**
  一個「被忽略的設定」天生就是安靜的 —— 這份報告是它唯一會現身的地方，
  所以它是這次拿掉相容性之後的補償控制。

- ⛔ **執行路徑裡不再有版本號。** 外掛裝在
  `~/.claude/plugins/cache/dispatch-guard/dispatch-guard/<版本>/`。hook 不受影響
  （`hooks.json` 用 `${CLAUDE_PLUGIN_ROOT}`），⛔ 但狀態列指令、VS Code 工作、
  以及 gate 給模型的每一個指令，存的都是寫死的絕對路徑。
  `update` 會搬走目錄卻**留著舊的**，所以舊路徑照樣跑得動、跑的是舊程式，而且看起來一切正常。
- ⭐ **改成指向一個永不改變的檔案**：`~/.claude/dispatch-guard/run.sh`（Windows 工作用 `run.cmd`），
  它會轉發到目前這一份外掛。gate 在每個 session 開始時把它對準正在跑的那一份；
  ⛔ 而且**它自己也會找** —— 存的路徑不在了就去找最新安裝的那一份。
  那段「更新之後、下一個 session 之前」的空窗，正是舊的靜默失敗住的地方。
- ⚠ **第一版的檢查是瞎的，這件事值得寫下來。** 它去搜尋 `/<數>.<數>.<數>/`，
  結果**把 bug 放回去也照樣通過** —— 因為在開發用的 checkout 裡，外掛住在
  `C:/WorkSpace/dispatch-guard`，那裡本來就沒有版本號。⇒ 改成斷言「正向性質」：
  每一條對外路徑都必須走 shim。這個版本的突變測試會被殺掉。

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

## 0.30.1

- ⛔ **鏡像會刪掉那個「讓工作紀錄保持私密」的檔案。** 為了不覆蓋 public 的
  `.gitignore`，我把它從鏡像的「來源側」拿掉 —— 而鏡像會刪除「目標有、來源沒有」的東西。
  ⇒ 下一次發佈就會把 public 的 `.gitignore` 刪掉，也就是唯一讓 `Memory/` 不外流的那個檔案。
  是 owner 指出來的（`3acb0fb`）。
- ⛔ **發佈前先確認目標能不能 commit。** 舊版是先複製、先 staged 三十個檔案，
  然後才發現那個儲存庫沒有 git 身分（`44bc4c5`）。
- ⚠ 移除用 `--ignore-unmatch` staged，因為大部分檔案本來就沒被追蹤（`745bb30`）；
  ignore 清單改成涵蓋「一個被整包複製的資料夾實際會帶來的東西」（`aaa6a88`）。
- ⭐ **`Tools/PUBLISHING.md`**：「更新 public repo」變成一行指令，而且寫下來了 ——
  每一條規則都附上「產生它的那一次失敗」（`7d5c8aa`）。
- ⭐ **`history_keep_days`，預設 30。** `history_dir` 裡最後修改時間超過這個天數的檔案會被
  整個刪掉。⛔ 只刪整個檔案，永遠不裁切 —— 裁切會留下一份「看起來完整、其實不是」的紀錄
  （`f24f12f`）。
- ⛔ **「狀態目錄下的 logs/ 資料夾」不是任何人指得出來的地方。** 現在寫出絕對路徑
  `~/.claude/dispatch-guard/logs/`。⚠ 而且 `state_dir()` 自己的 docstring 是錯的 ——
  它寫 `~/.claude/`，實際回傳 `~/.claude/dispatch-guard`（`d018d97`）。
- ⭐ **`config.json` 一個位元組都不寫。** 這是第三種設計，也是第一種沒有陷阱的：
  整個複製 `config.example.json` 會「釘住」每一個值，之後移動的預設值永遠到不了那台機器
  —— 那花了兩次重裝才找出來（`dcae793`）。
- ⚠ **`Tools/Debug/scratch/` 留著的理由被拆成兩半**：它作為「唯一出口」不是選配的
  （「跑完 `git status` 必須乾淨」正是靠它才是真的檢查），但那些留下來的檔案
  只對「已經知道它們存在的人」有用 —— 所以失敗報告現在會指出那個資料夾（`ab563b5`）。

---

## 0.30.0

- ⭐ **一行指令發佈 public 快照**：`python Tools/publish-public.py --push`。
- ⛔ **「差異」會安靜地漏掉刪除。** 「複製 0.24.0 之後改過的檔案」會帶走新增和修改，
  卻讓一個在私有端刪掉的檔案永遠活在 public，而且沒有任何東西會發現。
  ⇒ 腳本改成**鏡像**整棵樹：來源沒有的，目標就移除。
- ⚠ 它第一次跑的時候拒絕了自己 —— 那是設計，不是意外。

---

## 0.29.0

- ⭐ **安裝可以在「沒有模型」的情況下說出它做了什麼。**
  owner 定的前提：假設使用者安裝的時候**已經沒有用量了**，而安裝仍然必須完成。
- ⛔ **沒有預算就沒有模型輪次** —— 所以每一個以「⭐ TELL THE USER:」開頭的 SessionStart 備註，
  都是在對一個不會執行的東西下指令。其中三個描述的是「已經寫進某人設定檔或儲存庫」的改動。
- ⛔ **gate 的 SessionStart 根本沒有通往「人」的管道。** 它印純文字，而那個事件上的純 stdout
  只會變成模型的 context。
- ⇒ `maybe_install_vscode_task`、`maybe_repoint_statusline`、`maybe_adopt_statusline`
  現在回傳 `(context, screen)`：context 那一半給模型（如果有的話），
  screen 那一半用 `systemMessage` 直接到人的螢幕上。

---

## 0.28.0

- ⭐ **watcher 現在會證明自己在跑，不再只是「有被定義」。**
  `--watch` 會去 touch 狀態目錄裡的 `watch.alive`，`--status` 讀它的年齡：
  `usage watcher : RUNNING - last drew 0 min ago`。
- ⛔ **那是兩個不同的問題。** 在提出這件事的那台機器上，工作**一直都在而且正確**，
  終端機還是沒出現。⇒ 一個定義證明的是意圖，不是行程。

---

## 0.27.0

- ⛔ **`--status` 回答不了它自己被造出來要回答的那個問題。**
  它報告狀態列，對 VS Code 的 watcher 工作**一個字都沒說**。
  在提出這件事的那台機器上，工作從頭到尾都在而且正確，而報告講不出這件事 ——
  於是「沒有用量終端機」變成一場四個指令的搜捕，而不是一行答案。
- ⭐ 現在**逐一 VS Code 使用者目錄**回報那個工作在不在、對不對。

---

## 0.26.1

- ⭐ **找不到東西可清的時候，也要告訴人怎麼安裝。**
  跑清理程式然後被告知「這裡什麼都沒有」的人，通常離安裝只差一步 ——
  舊版卻在那個「下一個指令最明顯」的時刻停在死路上。
- ⚠ 兩個結尾都從**同一份定義**取得那段指令；兩份指令會在其中一份改動時分岔，
  而一個印出過期安裝指令的清理程式，就是一個人最後讀到的那句小謊。
- ⛔ 空的那個情況也會講出它**沒辦法告訴你的事**：「資料夾找錯，看起來就跟一台乾淨的機器一模一樣」。
- ⭐ **`debug.API_response_usage`，預設 false。** 打開之後，usage 端點回傳的每一個回應都會被
  **整個** append 到 `<history_dir>/usage-response-<戳記>.jsonl`，一行一個 JSON 陣列。
  ⚠ 理由：解析器只留 `five_hour` 和 `seven_day`，其他全丟。2026-08-27 有一個關於五小時視窗
  邊界的問題能被回答，純粹是因為 `resets_at` 剛好是留下來的兩個欄位之一 —— **是運氣，不是設計**。
  ⛔ 呼叫點在 `if not five: return` **之前**，因為那個提早返回正好發生在
  「解析器看不懂的回應」上，而那正是診斷最需要的形狀。（這一個 feat 沒有自己的版本號，
  它跟著 0.26.1 一起出貨。）

---

## 0.26.0

- ⛔ **清理程式在「還沒有東西可以同意」的時候就要求同意。**
  回報：它印出 `target : C:\Users\...\.claude`，後面接「things will be deleted」——
  合理的讀法就是「它要刪掉整個 Claude Code 目錄」。它從來沒有那樣做（那個路徑是它「看」的地方），
  但在一個破壞性動作的確認提示上，文字說的是另一回事。
- ⛔ **而那個確認把事情弄得更糟**：它要求把路徑的最後一段打回來，也就是 `.claude` ——
  於是讀起來變成「輸入 .claude 以確認刪除 .claude」，正好強化了標題造成的誤讀。
- ⇒ 照 owner 定的形狀重寫：**不用任何參數**，先列出要刪除／要編輯的每一項，
  然後才要求輸入 `confirm`（不分大小寫），預設什麼都不做。

---

## 0.25.0

- ⭐ **`Tools/clean-dispatch-guard.ps1`** —— 清掉舊安裝的每一個痕跡：哪些資料夾、哪些檔案、
  哪些設定檔裡的哪些值。
- ⛔ **外掛會自癒，為什麼還需要清理程式。** 過期的狀態列和過期的 VS Code 工作從 0.13.0 起
  都會自己修好，所以多數升級不用做任何事。**永遠不會自癒的**是每一個「曾經叫這個外掛記住」的東西：
  0.11.0 之前寫下的 `config.json` **釘住了每一個值**，之後的預設值永遠到不了那台機器；
  被改名的鍵是**被忽略、不會警告**的。
- ⛔ **而它在安全之前，先解除安裝了一個正在運作的外掛。**
  一個測試沒有在子 PowerShell 裡改掉 `$HOME`，`-Apply` 就對著真正的 `~/.claude` 跑了。
  ⇒ 四項修正：先印出目標並要求打字確認、路徑改成注入（`-ClaudeHome`）、
  用原始文字偵測 JSONC、每個檔案每次執行只備份一次。

---

## 0.24.1

- ⭐ **安裝步驟前面多了「步驟 0」**：先設定 VS Code 的 **Allow Automatic Tasks**，
  那個通知就不會出現。⚠ 舊的順序有一個「只能靠**錯過**才會遇到」的步驟：
  那個通知會自己淡掉，而拒絕它（或根本沒看到）會讓 watcher 工作**被寫進去、在 Run Task 看得到、
  但開資料夾時永遠不啟動**，任何地方都沒有錯誤訊息。
- ⛔ **而 README 裡那個指令名稱根本不存在。** 它寫 `Tasks: Allow Automatic Tasks`。
  沒有那個指令 —— 對著出貨的 VS Code 1.135.0 實測過。

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

## 0.18.0

- ⭐ gate 注入到**每一層**子任務提示詞的那段規則加了第 7 條：暫存檔案放在
  `<task_root>/<task>/scratch/<你的子任務>/`，而且**不要刪**。
  0.17.0 把這件事寫進兩支 skill，但 skill 只約束讀過的 agent；
  這段規則連三層之下、兩支 skill 都沒載入的 agent 也約束得到。
  ⚠ 這是**指令，不是強制**：gate 檔得住工具呼叫，檔不住所有形式的刪除。
- ⛔ `test_resume_cancel.py` 原本斷言 `.claude/dispatch-gate.log`【不存在】，
  但要問的是【這次測試有沒有寫】—— 真的 session 在這個 repo 工作時，
  plugin 本來就會寫進那個檔。現在比對前後大小。

---

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

---

## 0.16.2

- ⭐ 三支檢查程式搬到 `Tools/Debug/`，而且**產生的每一個檔案都關在 `Tools/Debug/scratch/`**
  （相對路徑、已 gitignore、跑完不刪，所以檢查失敗時它寫了什麼還在那裡）。
  ⛔ 跑完之後 `git status` 必須乾淨 —— 那本身就是「測試沒寫到外面」的檢查，
  而這件事有兩次前科：一次寫進工作樹，一次寫進 `~/.claude`。
- ⚠ 每個子行程原本都會清空 scratch，把前一支的證據刪掉。改成由 `test_all.py` 準備一次，
  並依檢查名稱分開命名目錄。

---

## 0.16.1

- ⛔ `test_resume_cancel.py` 用**這個 repo 當工作目錄**呼叫 `do_cancel()`，
  而 `log_line()` 會寫 `<cwd>/.claude/dispatch-gate.log` —— 於是每跑一次測試就在工作樹裡
  留下外掛自己的 log。⚠ 那跟「開發複本正在被執行」長得一模一樣，
  是一個正在確認安裝的人最不能看到的東西。
- ⚠ PROTOCOL.md 瘦身之後，README 兩處還說「規範本身寫在 PROTOCOL.md」，而那個檔案自己說
  規則在 `skills/dispatch-protocol/SKILL.md`。兩處都改成描述這個分工。

---

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

---

## 0.15.0

- ⭐ **預設值改成 `soft_pct` 70 / `hard_pct` 90**，跟 `colour_warn_pct` 70、`colour_alarm_pct` 90 對齊。
  橘色 = PACE 開始，紅色 = STOP 開始。⚠ 仍然是四個獨立設定值，沒有合併。
- ⛔ 這讓兩句已經寫下的說明變成錯的，兩句都改了：「顏色門檻故意設在拒絕門檻之前」（現在是相等），
  以及今天稍早寫的「90% 落在中間所以是 PACE」（現在 90% 就是 STOP）。
- ⭐ README 寫清楚那則畫面訊息的觸發方式：`UserPromptSubmit` 事件、依 `limits.json` 的百分比、
  每個 session 每個等級**只送一次**（記錄在 `state/<session-id>.warned`），等級改變才重新武裝。

---

## 0.14.0

- ⭐ **煞車現在會說給「人」聽。** hook 的 `systemMessage` 直接顯示在使用者畫面上（出自執行檔的參考文件：
  「Display a message to the user (all hooks)」）。PACE / STOP 各一則，派工被拒絕時也有一則。
  ⛔ 在這之前所有訊息都只進到**模型的 context** —— 於是「它繼續工作」和「它根本沒收到」長得一模一樣。
- ⭐ 進入 PACE / STOP 時，agent 被要求原封不動印出一行 `PACE at 90% - winding down`。
  ⚠ 那不證明它照做（提示詞證明不了任何事），但它分開了「收到卻繼續」和「從來沒收到」。
- ⚠ 文件講明：**90% 預設不是煞車**。`soft_pct` 85 是 PACE，`hard_pct` 93 才是 STOP。

---

## 0.13.2

- ⭐ README 兩半新增：安裝後重開 VS Code 會跳出的 **Allow** 通知（原文照引），以及找回它的三種方法。
  ⚠ 那個通知會自己淡掉，而錯過它的後果是「工作在、Run Task 看得到、但永遠不自動跑」。
- ⭐ 也寫進去：`claude plugin update` 之後那個絕對路徑會自己修好，不用重跑任何東西。實測並加了檢查。

---

## 0.13.1

- ⛔ 「允許自動工作」那個授權沒跟著搬。VS Code 用**通知**問這件事，而通知會自己淡掉 ——
  於是工作寫好了、Run Task 看得到、但永遠不會自動跑。授權現在跟著寫入一起做。
- ⛔ 使用者層級的指令被縮寫成 `${workspaceFolder}/…`。使用者層級的工作**沒有自己的 workspace**，
  那個變數會對著「當下開的專案」解析 —— 在每個專案都是錯的，包括寫出它的那一個。改成永遠用絕對路徑。

---

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

---

## 0.12.0

- ⛔ **種子 config.json 會「釘住」每一個值，所以 0.11.0 的新預設到不了任何已安裝的機器。**
  0.9.0 起 `seed_config()` 照抄範例檔，包含所有值；明確寫下的值永遠贏過程式預設值。
  ⇒ 現在只種**說明**，不種值：每個 `_` 開頭的解釋都留著，真正的 key 一個都不寫。
  ⭐ 加一個 key 變成刻意的決定，不再是「你剛好哪一天安裝」的意外。
- ⭐ `--status` 新增 `pinned settings`：列出你 config.json 裡跟預設值不同的每一個 key。
  ⛔ 在這之前，從外面完全看不出「更新了、預設變了、卻什麼都沒發生」是為什麼。
- ⚠ **已經安裝過的機器不會被改寫**（種子檔從不覆蓋）。跑 `--status` 看自己釘住了什麼。

---

## 0.11.0

- ⭐ `auto_vscode_task` **預設改成開**。⛔ 關著的時候這個功能是找不到的：hook 唯一的管道是
  SessionStart 訊息，而那是進到**模型的 context**、不是你的螢幕 —— 兩次全新安裝實測，工作都沒出現。
  ⇒ 保護改放在**衝突判定**（被 git 追蹤、解析不了）上，不是放在一個把功能藏起來的預設值。
  「問一次」那整套連同它的標記檔一起刪掉了：關掉它是一個決定，不是每個 session 重問一次的問題。
- ⛔ `test_all.py` 印失敗內容時會自己崩潰（cp950）。報告工具在報告時死掉，比沒有報告更糟。

---

## 0.10.0

- ⭐ 多帶一個 skill：`unattended-work` —— 沒人看著的時候怎麼工作。
- ⭐ 新的 `userConfig` 選項 `announce_unattended_work`（預設開）。⛔ 它關不掉 hook —— 外掛的 hook
  一定會觸發 —— 關掉的是那個 hook **印什麼**。⚠ 看不懂的值當作「開」：安靜消失的提醒比多餘的提醒糟。

---

## 0.9.4

- ⛔ 移除會**建立**檔案：從一個本來就沒有 `tasks.json` 的專案移除工作，會寫出一個空的。
  清空一台機器時，每個碰過的 repo 都被留下一個 `.vscode/` 目錄。

---

## 0.9.3

- ⛔ `auto_vscode_task` 的詢問**只問一次就永久消失**，即使沒有人看到那一次。標記是在回答**之前**寫的，
  而那句話是進到模型的 context、不是進到螢幕；session 結束或 agent 沒照做，這個功能就再也發現不了。
  改成記「問過幾次」，最多三次；⭐ 真的回答了（`--enable-auto-task` / `--disable-auto-task`）就立刻停止。

---

## 0.9.2

- `Memory/tasks/` 不再進 git，那裡曾經夾帶 80 KB 的審閱報告出貨。
- 新增 `test_all.py`：一個指令跑完四項檢查。

---

## 0.9.1

- 新增 CHANGELOG.md。README 和 PROTOCOL 不再記錄版本歷史。
- ⛔ 修好 README.md 裡兩個 NUL 位元組，git 原本已經把它當二進位檔。

---

## 0.9.0

- `~/.claude/dispatch-guard/config.json` 會自動建立，內容是 `config.example.json`。已存在絕不覆蓋。
- `config.example.json` 原本把 `dispatch.task_root` 釘成一個路徑，程式預設是 `null`（自動挑）。已改回 `null`。
- README、PROTOCOL 全面對照程式碼校正，包含上面那則公告的版本範圍。

---

## 0.8.0

- `--watch` 在沒有任何 session 活動超過 `idle_after_min`（預設 15 分）之後**停止呼叫 API**，但**繼續重畫**那一行。
- `Ctx` 從 session 第一秒就顯示，讀 0%。payload 裡沒有那個欄位時畫 `--`，永遠不是 `0%`。
- 三段長條共用一個 `BAR_WIDTH`，從 6 加寬到 9。狀態列因此從約 75 欄變成約 87 欄。
- README 的範例行拆成 `--statusline` 和 `--watch` 兩個，加上每一段的來源對照表。

---

## 0.7.2

- 取消預約的 resume 現在分得出三種結果：沒有註冊、刪除成功、排程拒絕。之前後兩種被混在一起。

---

## 0.7.1

- `statusline_install()` 也不再覆蓋一個讀不出來的 `settings.json`。
- `--uninstall` 之後 gate 不再宣稱「不會有東西醒來重做」，除非排程真的答應了。

---

## 0.7.0

- ⛔ 修好上面那則公告的 `NameError`。自我檢查改成呼叫真正的函式。
- 讀不出來的 JSON 檔案（帶註解的 `tasks.json`、多一個逗號的 `settings.json`）不再被覆蓋。
- 狀態列的擁有權判定收緊：要同時有 `usage.py` 和 `--statusline` 才算我們的。
- 移除會把 `auto_statusline` 一起關掉，否則下一個 session 就把狀態列裝回去。

---

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

---

## 0.3.0

- 完整的移除流程，`/dispatch-guard:uninstall`。

## 0.2.2 / 0.2.1 / 0.2.0

- 斜線指令 `/dispatch-guard:install` 和 `/dispatch-guard:status`。
- 重跑安裝會修好指向舊版本的狀態列路徑。
- 安裝步驟改成一段自己找路徑的腳本。

---

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

## 0.65.0

cowork: what an observer role recorded, entry by entry, during a second cross-machine move (one project from an
old machine to a new one, nine sessions by the end). Two items are **0.64.2's own mistakes**; the rest are new rules;
plus a watcher tool.

- ⛔ **[fixes 0.64.2] The only stable identity is the ROLE the owner assigned.** 0.64.2 said "`[ref]` / session id is
  the only stable key" and named check-in files by session id - wrong: runtime names change within minutes and are
  recycled; the `[ref]` beside a name changes too (one agent claimed with one session id and was later listed under a
  different `[ref]`; the messaging tool's own description says a ref "you did not just read from a listing or an error
  will not resolve"); a resumed session gets a new session id. ⇒ check-in files are `checkin/<role>.md`; runtime name,
  `[ref]` and session id are fields the holder rewrites on every restart; to reach a role: read its check-in file, find
  that name in the live list, send to it (`coordination.md` 2.1/2.8/2.9). Two holders of one role during a handover get
  `S3-old` / `S3-new` until the old one is retired.
- ⛔ **[fixes 0.64.2] No `@` in code names.** `@` is the messaging tool's team syntax (`name@team`): a send to `@MIG` was
  refused before any lookup ("to must be a bare teammate name"), an error shape unlike "not found", which took three
  attempts to tell apart. Code names are plain alphanumerics and are **never used as a send address**.
- ⭐ **Waiting for a peer is not stopping (`cross-machine.md` 1.8, rule 13, `unattended-work` §15).** Between turns a
  session runs nothing and nothing wakes it: "I am waiting" = asleep. Measured: one side said "waiting" at 11:45 and slept
  until the owner relayed "go" at 13:31. ⇒ Before ending a turn to wait on a peer, arm a wake-up: `notify_when_idle` on
  one machine; the new **`skills/cowork/tools/watch-folder.ps1`** across machines (run in the background; it exits, and
  so wakes you, when the channel folder changes); post ONE waiting line. After adoption: one side finished and the other
  acted ~50 s later with no human in between. ⛔ The second half was learnt the hard way: the first wording ("post a
  waiting line before you stop") was read as "on every wake", and nine sessions woke each other in a storm (4-5 empty
  lines every two minutes). ⇒ **A wake with nothing for you writes nothing**; watchers ignore their own and the
  observer's files. Waiting on the OWNER still stops cleanly.
- **Permissions before the first copy, at the destination ROOT (`cross-machine.md` 1.6, 2.3).** The same defect struck
  three times in two days, repaired per folder each time. A file created over an admin share is read-only to other
  accounts even when they can create files - the creator grants the other side by SID in the same step.
- **The destination's antivirus removes files after a perfect copy (2.3b)**: write-test 40/40, bytes all equal, then
  evidence files quarantined minutes later with 30 more at risk. Set exclusions before copying evidence or samples;
  re-count later. **The destination agent does not start inside the destination tree (2.3c).**
- **Double-encoded UTF-8 passes the control-character scan (4.2)**: the owner's words reached a board as a run of accented
  Latin letters, with no control character at all. Added a double-encoding signature check; read back every owner quote.
- **A channel move announced only in the new place** never wakes whoever watches the old one (`coordination.md` 3.9) ⇒
  announce in the old place and keep watching it until everyone acknowledges.
- New sections: `coordination.md` 3.14 re-read the board before posting WAITING or saying who is (not) present (three times
  in two hours); 3.15 rules adopted mid-run go into the channel's standing file at once (three late joiners never got
  them); 3.16 an owner-given rule that is visibly harmful is reported once by each party and still followed - only the
  owner or the rule's author changes it; 3.17 the owner carrying findings by hand means a missing file; 3.18 an observer
  role: an FYI category for measured, certain blockers, and a record of who read the observer's file.
  `cross-machine.md` 1.3 (where the channel goes when only the target share is reachable), 1.7 (post both clocks once;
  every stamp from `date`), 3.4 (a freeze names who covers stopped monitoring).
- Failure shapes: six rows added (asleep while waiting, wake storm, moved channel, late joiner, removed after arrival), two
  rewritten (recycled name, name collision), "silent text corruption" extended to double encoding. Both languages.
- `watch-folder.ps1`: pwsh 7 guard (5.1 re-executes under pwsh 7 with serialised arguments; no pwsh 7 = refuse and say how
  to install); `-Ignore "a,b"` comma-separated; always recommended with `-WindowStyle Hidden` so no console window pops up
  to be closed by accident. Measured: fires, ignored-only does not fire, 5.1 path, missing folder.
- One adversarial review (sonnet): 1 BLOCKING (the "recycled name" row still stated the old model, both languages) fixed;
  1 NON-BLOCKING fixed.

---

## 0.64.2

cowork: **names are recycled**, and the owner's **check-in board** (made one file per session).

- ⛔ **A recycled name is worse than an expired one.** Measured: one runtime name belonged to one
  role six days ago and to a different role today; one session was renamed after 8 minutes,
  another three times in 20. An expired name fails loudly; **a recycled name is delivered — to a
  different session, with no error.** The old 2.1 advice "query the live list" sends it straight
  to the wrong place. And the session list held an unrelated, offline session literally named
  `S4`, so a bare code name reached a stranger.
- ⭐ **Check-in files (`coordination.md` 2.8)**: one fixed shared directory, **one file per
  session, named by its session id**, rewritten only by that session — code name, current runtime
  name (for people only), `[ref]` / session id (the only stable key), machine / repo, checked-in
  and last-confirmed times. The owner proposed one editable check-in board; it became one file per
  session because two sessions were measured editing one roster minutes apart, stopped only by a
  lucky stale-write check. With a file each there is no race — the same rule as content.
- ⭐ **The code name is the owner's, and the session confirms it back**: "received — my code name
  is S4; address me as @S4 from now on", and writes it into its check-in file. Code names are
  always **prefixed** (`@S4`) so they cannot collide with runtime names.
- **2.9, address by id**: send by `[ref]` / session id; before a consequential message, check the
  name still maps to the id on the recipient's check-in file.
- Rule 2 rewritten as "check in first, register only yourself, address by id"; 2.4 "within
  hours" corrected to the measured "within minutes"; two failure-shape rows (recycled name, name
  collision). Both languages.
- Not done: a hook gate (refuse the first write until this session has a check-in file) — in
  PENDING for the owner.

---

## 0.64.1

⛔ **In 0.64.0, cowork did not exist in any session.** Its description read
`The trigger is the SITUATION, never the wording: use it …` — a colon followed by a space inside
an unquoted YAML scalar is a mapping indicator, so the frontmatter was invalid YAML and Claude
Code **dropped the skill silently**: measured 2026-09-23, a nested session listed 127 skills,
with `dispatch-protocol` and `unattended-work` and **no `cowork`**, and `plugin_warnings` was
null. The model went looking for cowork's files with Grep and Glob — it wanted the skill; the
list did not have it.

- Fix: `wording: use` → `wording. Use`.
- ⭐ **New gate `Tools/Debug/test_skill_frontmatter.py` (item 14 of `test_all.py`)**: every
  `skills/*/SKILL.md` must have parseable frontmatter, a `name` equal to its directory, and a
  non-empty `description`. PyYAML when present; otherwise a strict fallback that refuses a plain
  scalar containing `: ` or ` #` or starting with an indicator. Positive control: the 0.64.0 line
  must be rejected and its fixed form accepted — verified on both paths, and it goes red against
  the installed 0.64.0 copy.
- ⚠ **Why 0.64.0 passed every check and still broke**: zh/en counts, control characters,
  identifiers and the whole suite all passed, because none of them read the file the way the
  loader does. The "positives 4/5" in the 0.64.0 section measured the OLD 0.63.2 cowork sitting
  beside the synthetic skill, not 0.64.0 — that number does not hold for 0.64.0.

---

## 0.64.0

What cowork's first cross-machine job (moving a project from an old workstation to a new one,
2026-09-22) taught, plus three owner rulings from the same day.

- ⭐ **Rule 13, and a new reference file `skills/cowork/reference/cross-machine.md`.** The skill
  had no cross-machine content at all — UNC, SMB, "another machine": zero hits, and its own title
  said "one working tree". The costliest lesson of that job: the coordination board was created
  by the source machine over an administrative share, so its permissions followed that account;
  the destination could **read it and not write it**. The protocol told that side to append and
  flip a "whose turn" field; it could do neither. The source polled every 20 s, saw no change,
  and read it as "they have not started". **Neither side got an error; both behaved correctly**;
  the owner fixed the permissions by hand. ⇒ Rule 13: prove you can WRITE to a channel before
  depending on it, and measure each direction separately; after a cross-machine copy the first
  check is "can I write here", not the hash — a bit-perfect unwritable tree fails every later
  step with a different error and reads as five bugs. Four parts: the channel; what arrives but
  cannot be used; two live trees; four instruments that lied during the migration (an
  ignore-respecting search blind to the one-off scripts; a heredoc halving backslashes into
  invisible control characters; a positive control that crashed AFTER printing a clean result; a
  marker-list check measuring the line that defines the list); and a closing checklist. Seven
  new failure-shape rows, in both languages.
- ⛔ **Two layers, not one board.** The owner: "write your own file, not one shared board" was
  already the rule from an earlier project, and cross-machine experience ADDS to it, never
  replaces it. Against those agents' original records: their `CLAIMS.md` IS one append-only
  claims board (= `coordination.md` 3.1) and their content is one author-named file each
  (`contrib/<Sn>-…md`) — tested live when the shared `SKILL.md` was lost and `contrib/` lost
  nothing. cowork had written down only the board layer. 3.1 now states the content layer and
  that lesson; `cross-machine.md` 1.1 / 1.5 / 1.6 and its checklist are rewritten to the two
  layers — the board is usable across machines only after both sides pass the write-test, a side
  that cannot write it speaks through its own file, readers scan the directory; 1:1, 1:N, N:1
  and N:N change nothing. The single board with a turn field from the first migration is
  recorded as the **workaround**, not the protocol.
- ⭐ **The description now triggers on the SITUATION, never the wording.** The owner: robocopy,
  handover, "context running out" are symptoms, not triggers. The trigger is more than one
  session on the same repository (concurrent or one after another), more than one machine, work
  spanning repositories or projects, or an owner relaying one thing to several sessions.
  Measured (25 Traditional-Chinese queries, synthetic skill, sonnet, sequential foreground):
  positives 4/5 load cowork — the cross-machine opening and the post-copy check that missed at
  baseline now load, and the two new cross-repo / cross-project cases do too; the hardest
  near-miss negatives (ssh between two machines, a local `FETCH_HEAD` permission error, a nightly
  mirror script) **0 false fires**. The one remaining miss ("two agents produced the same
  section — I called both at once") goes to `dispatch-protocol`, a defensible reading. ⚠ Two
  traps in the measurement itself, recorded in `Memory/tasks/20260922-212000-cowork-trigger-evals/`:
  a nested `claude -p` loads the **installed plugin copy**, never the working tree (the first
  re-measurement was invalid for that reason); and skill-creator's `run_eval.py` `select()`s on a
  pipe — `WinError 10038` within a second, scored as a miss — and counts only its own temporary
  command name, so a correct load of the real installed skill also scores as a miss.
- ⚠ **The hook section gains one sentence: `guard_cowork_first` sees only same-machine peers.**
  Its heartbeat is a file in this machine's state directory; a session on another machine is
  never a peer. On a cross-machine job **nothing prompts you at all** — rule 13 is what stands
  there. `PROTOCOL.md` §4 updated in two rows.
- **`usage.py --selftest` failed every day from 23:33 to 00:00.** It asserted the five-hour reset
  bracket never carries a weekday "because it cannot reach tomorrow" — false for any window
  opened after 19:00. Measured 2026-09-22 23:48: the fixture (now + 1600 s) rendered
  `(Wed 00:14)`, `test_all.py` 11/13. The expectation is now computed the way the renderer
  computes it, with three FROZEN-time pins (Tue 23:48 + 26 min → `(Wed 00:14)`; Wed 00:20 +
  26 min → `(00:46)`; Tue 23:48 + 5 h → `(Wed 04:48)`), and the docstring sentence is corrected.
  Mutation check on a copy (force `same_day = True`) → the pins fail. Renderer unchanged.
- README: the cowork section updated — thirteen rules, 31 failure shapes, six reference files,
  "one working tree, or two machines".

---

## 0.63.2

The owner's rulings of 2026-09-21 on five `Memory/PENDING.md` items; three are code:

- ⛔ **The `SPENT in ~N min` sentence's ⛔ now follows the WORD, and a young window prints
  nothing.** Through 0.63.1 the sentence carried a ⛔ and "Plan for the gap" whenever
  `burnout_min` was under the minutes remaining — on a **GO** line, beside "Headroom available".
  Measured 2026-09-14: sessions wound down on it at 20–27%. Re-measured 2026-09-19: 10% used
  prints `SPENT in ~90 min` at 10 and 20 minutes into the window and nothing at 45 and 90 — loudest
  where the headroom is largest. Now: at GO the line reads `ℹ … would be SPENT in ~N min … That
  figure only sizes the NEXT block; GO stands`; ⛔ and the imperative appear only at PACE/STOP;
  and while the window is younger than `burn_note_min_age_min` (new key, default **30** minutes)
  nothing is printed. ⚠ The selftest's forcing pin (burnout_min forced to 1 at 47% stays GO and
  the sentence is present) is unchanged — the glyph and the imperative go, the sentence stays.
  Four new pins: no ⛔ at GO, ⛔ at PACE, a 20-minute-old window silent, the key at 0 prints.
  ⛔ Review 01 caught two defects in the first draft, both fixed before shipping: the age gate's
  variable shadowed the DATA-age `age_min`, so fresh data in a 55-minute-old window printed
  `[data 55 min old]` and 40-minute-old data in a young window printed nothing (renamed
  `window_age_min`); and the glyph followed the 5h level, not the printed word, so 5h 55% + 7d 96%
  gave a **PACE** line ending "GO stands" (the sentence is now built after `level` is chosen). One
  pin each; a mutation of either kills its pin.
- ⭐ **`guard_agent_report_file` no longer reads a shell example as a demanded report.** A `.md`
  in backticks right after `>` / `>>` / `| tee`, or inside a backtick span that contains `>` or
  `|` (`cat new.md | tee board.md`), does not count. The 2026-09-19 false alarm — a review prompt's
  `(vi) \`echo x >> board.md\`` reported "never created" — reproduces on its paragraph with the old
  code and not with the new. Measured over all 35 real work orders: 58 paths kept, none dropped,
  none invented (`scratch/B-measure/`). ⚠ The whole-file pass cannot show the removal because
  `demanded_files` caps at 8 paths per prompt and that prompt already yields 8 genuine reports.
  ⛔ The first draft accepted a bare `|`, and review 01 measured it dropping a genuine report
  written in a markdown **table cell** (`| write | \`adr-review-01-adversarial.md\` |`) as a pipe
  target; `tee` is now mandatory after `|`, and the `>` of a `->` arrow is not a redirect. Three
  new pins.
- ⭐ **Evidence for the cowork nag.** `guard_cowork_first` logs `COWORK-PEERS sid=<sid8> mine=<s>
  <sid8>:alive=<s>,start=<s> …` right before its refusal; `peer_sessions()` returns 3-tuples (the
  peer's start age is new); the `SKILL-SEEN` line carries `sid=` too. `Tools/Debug/cowork_nag_report.py`
  (new, `--selftest`, in `test_all`) reads every firing back from the state log and judges GHOST
  (the peer's heartbeat is older than this session — it has not moved since this session began)
  and LOADED (the skill invoked by the **same session** within 300 s, paired by sid). ⛔ The first
  draft paired by time alone, and review 01 measured two sessions firing a second apart with one
  load read as 2/2 — the state log is one file for the whole machine. Pre-0.63.2 lines without a
  sid fall back to the time window, and the row says so. The owner works in other projects most days; the data accrues by itself
  and the report is one command. First data point: 2026-09-21 16:44, the peer was most likely
  this session's own pre-restart self (UNCONFIRMED), skill loaded 23 s later.
- **`unattended-work` §11 gains one pointer** into `skills/cowork/reference/verification.md`
  Part 3 (the other three controls, the partition control, the calibrated threshold, the
  wrapped-line false zero). Direction settled: the plugin is the live copy and user-scope
  `VERIFICATION-LESSONS.md` points IN — the owner asked what a machine without dev-workstation
  would lose; the answer is that a plugin must not depend on user scope, and `~/.claude/CLAUDE.md`
  already names dispatch-guard the required dependency.
- **`PROTOCOL.md` drops the `delegated` status** (the owner withdrew the "run the prompts on
  another account" flow; nothing ever produced that status). The dev-workstation snippet is
  corrected the same day.

---

## 0.63.1

⛔ **A fourth reviewer (the owner approved a fourth round, `code-review-D-fourth.md`) found one
blocker after 0.63.0 shipped.** `Rename-Item board/BOARD.md -NewName old.md` and
`Move-Item board/BOARD.md -Destination old.md` — the ordinary spelling of both cmdlets, a
positional path plus a named parameter — were **allowed**: `_ps_path` returned the named values
**or** the positionals, so once any parameter was named the positional source was dropped, while
five spec copies promised both cmdlets refused. Now every non-flag token counts, exactly the `mv`
branch.

Four non-blocking items fixed with it: (D2) C-c1 was taken by half — a raw-unique anchor whose one
occurrence is an **earlier** line (the last line repeats the text but lacks the newline) let the
tool insert mid-file; the single occurrence must now be at the end. (D3) only the first `cd` was
honoured, so `cd board && cd .. && echo x > BOARD.md` falsely refused `board/BOARD.md`; every
leading cd is applied in turn. (D4) `CD`, `Set-Location`, `sl`, `chdir`, `pushd` were unseen; all
recognised, case-insensitive. (D7) frontmatter beginning with a `# comment` was no longer skipped
and its comment became the "first heading", wrong in both directions; blank and comment lines are
skipped before the `key:` test. (D9) C-b1's "pinning test" used `cd "board"` — no space — which the
old regex already refused, so it pinned nothing; now `cd "board/board dir"`. Docs: three
`PROTOCOL.md` §3/§4 rows rewritten (D3/D5/D8/D11/D14), SKILL.md in both languages says the allowed
Edit anchors on the last **entry**, not the last line (D12), and that `cd` **replaces** the
directory (D13), and the stale "14 shapes" inside the 0.63.0 entry (D15). `case_append_only`:
23 → 29 refused shapes, plus three PowerShell allowed controls.

⛔ **And the gate caught one D did not, in the same round:** while fixing D12, the installed
0.63.0 hook **refused** an Edit of `skills/cowork/SKILL.zh-TW.md` — it judged the file
append-only because rule 3 quotes `<!-- append-only -->` in backticks within the first 2 KB. A
document that DESCRIBES the marker is not a record that carries it. The HTML comment must now
stand on a line of its own; an inline mention does not count. That is exactly the trigger ADR R1
names, on day one. The two zh-TW edits were applied by a Python script doing a byte-exact
replace (the gap `PROTOCOL.md` §4 records — the hook runs the installed cache, not the working
tree), and the commit message says so. ⚠ No fifth round on D's fixes.

---

## 0.63.0

⭐ **A third skill: `cowork`** — the rules for several sessions sharing one working tree for one
owner. Written by four sessions in one evening on 2026-09-19, every rule broken at least once by
its author in the hour it was written; the ADR that merged it into this plugin went through two
adversarial review rounds (round 1 REJECT with four blockers, round 2 ACCEPT with none), recorded
in `Memory/tasks/20260919-204317-cowork-skill-and-hooks/`.

- `skills/cowork/SKILL.md` (the entry point: twelve rules, a 24-row catalogue of failure shapes,
  what the hook enforces), `SKILL.zh-TW.md` (a reading copy), five English `reference/` files.
  ⛔ **One live copy per rule**: where a rule already lives in `unattended-work` §9/§10/§11/§12
  or `dispatch-protocol`, cowork points at it and does not restate it — and it points only at
  files the plugin ships, never at a user-scope file one machine has (round 1 caught two pointers
  to `~/.claude/CLAUDE.md`). `test_guards.py` gains `case_cowork_restates_nothing`: a similarity
  scan (floor 0.25, positive and negative controls in the same run) **plus a normalised-heading
  comparison** — because the first merge left a section with a heading identical to
  `unattended-work` §9 that scored 0.167, invisible to the score alone. Both mutations killed.
- ⭐ **Two of the rules are gates now** (`hooks/cmd_guards.py`; `dispatch_gate.py`'s `main()`
  gains a file-tool branch):
  - **`guard_append_only`** — a file whose first heading contains `append-only` (or that carries
    `<!-- append-only -->`) may only grow. A `Write` must start with the current content; an
    `Edit`'s `old_string` must be the end of the file and its `new_string` start with it, and
    `replace_all` on an anchor that also occurs earlier is refused; in the shell `> path`,
    `sed -i`, `tee` without `-a`, `rm`, `truncate`, `cp`/`mv` onto it, `Set-Content`, `Out-File`
    without `-Append`, `Clear-Content`, `Remove-Item` are refused. ⛔ **The marker is the FIRST
    HEADING, not body text** — measured over 21 979 files, the loose rule locked the skill's own
    SKILL.md and the ADR that proposed it. A token the gate cannot expand (`$VAR`, a glob) is
    logged `CMD-ALLOW(guard_append_only unresolved)` and allowed — named as an ALLOW on purpose,
    because the terminal-isolation check treats only that prefix as live traffic.
  - **`guard_cowork_first`** — when another session's `.alive` in this repository is younger than
    `peer_alive_min` (15 minutes, a new key) and this session never invoked `cowork`, the first
    `Write` / `Edit` / `git commit` is refused once. Peer roots are compared under `normcase` —
    3 of 118 real `.start` files spell the drive letter upper-case, two of them in one repository,
    and without case-folding those peers cannot see each other. Sub-agents carry the parent's id
    and are never peers. The same six properties as `guard_unattended_first`: once, a mark, the
    off switch logs `CMD-DISABLED` and does not spend the mark, silent once the skill was seen,
    advisory when unstamped.
  - Both fail open, log every decision, and have their own switch. `case_append_only` (14 shell
    shapes refused and 11 allowed as shipped; 29 refused after the reviews, see 0.63.1, LF/CRLF appends, `replace_all`, MultiEdit, fail-open, the off
    switch, a mutation that removes the guard from both tables) and `case_cowork_first` (another
    repository / a stale heartbeat / the skill seen stay silent; a flipped drive-letter case still
    counts; commit triggers too; the peer-removal mutation).
- ⛔ **One sentence leaves the `g_commit_branch` refusal.** Until 0.62.0 it ended "each one needs
  its own worktree" — the opposite of the owner's rule ("no worktree workaround") and of the
  cowork skill shipped beside it ("do not give each session its own copy of the work"). One
  plugin, two right rules, is cowork's own catalogued failure shape. The sentence is gone and
  `case_branch` pins it. The same advice in `PROTOCOL.md` §4 ("give each a worktree") is
  corrected with it.
- `config.example.json`: three new keys with bilingual comments. `PROTOCOL.md`: two rows in §3,
  four honest gaps in §4. README: one section in each language.
- ⛔ **Two pre-publish reviewers each found one blocker; both fixed before 0.63.0 shipped**
  (`code-review-A-guards.md`, `code-review-B-content.md`). A: `_REDIRECT` never matched a
  **quoted path containing a space** — the one case quotes exist for — so
  `echo x > "board dir/BOARD.md"` truncated the record under CMD-ALLOW; now three alternations.
  Also from A: a leading `cd x &&` in the same command is honoured when the path is resolved; a
  repeated anchor is refused **with or without** `replace_all` (the tool requires uniqueness, so
  this never refuses an Edit the tool would perform); `Set-Content -Value x file` is seen; `mv`'s
  **source** counts as a removal; an unreadable file logs `CMD-ALLOW(guard_append_only
  unreadable)` instead of passing as unmarked; a `# comment` inside YAML frontmatter is not the
  first heading. B: the dedup dropped "a substring match is not a token match" — its only other
  copy is user-scope, exactly the case the ADR says stays in cowork; restored. Also from B: 8.1
  pointed at a rule `dispatch-protocol` does not carry (now `require_handoff_past_soft`); 8.2
  had lost two items; 8.5 restated PACE/STOP; verification.md restated §9 inside the sentence
  pointing at it. Tests hardened: the refused shell shapes (14 → 23) now assert the **refusal
  reason** (a bare `deny` can come from any guard), and the allowed shapes assert the guard ran
  (`checked=`).
- ⛔ **A third reviewer refuted the fixes and found 12 more non-blocking items**
  (`code-review-C-refute.md`); four fixed before publish: the `cd "board dir" &&` regex repeated
  F1's mistake (now the same three alternations); the `cd x &&` target **replaces** the cwd
  instead of being tried beside it (trying both refused files the command never touched); the
  anchor count is over **raw** bytes (the rstripped count refused an Edit the tool itself finds
  once); the frontmatter skip only fires when line 2 looks like a YAML key (otherwise a `---`
  horizontal rule on line 1 swallowed the marked heading and the file read as unmarked).
  `Move-Item`, `Rename-Item`, `Copy-Item` added. **Recorded, not fixed:** A-F9 (a string
  `"false"` is truthy for all nine guards - inherited), B-NB-5 (the ADR's wording), B-NB-6 (the
  spec lives in three places by this plugin's convention); C's remaining gaps are in
  `PROTOCOL.md` §4. ⚠ C's fixes were not re-reviewed by a fourth agent - two rounds plus one
  refutation is the budget.
- ⚠ **Not done, and written down:** which nine items `~/.claude/docs/VERIFICATION-LESSONS.md`
  should absorb and which three cowork keeps is a recommendation to the owner
  (`RECOMMENDATION-verification-lessons.md`), not an edit — that file is user-scope, in another
  repository. cowork keeps the full text until then (add before remove, or it is its own
  "omission meets reorganisation"). Whether to delete the `NewSkill/cowork/` original is one
  sentence from the owner, in `Memory/PENDING.md`.

---

## 0.62.0

⚠ **Another default threshold moves, so this is another MINOR release.** `soft_pct_7d`
**95 → 93** (PACE, driven by the seven-day window). `hard_pct_7d` stays 97.

**And the seven-day bar finally has its own pair of colour thresholds.** Through 0.61.0 ONE
pair banded BOTH bars — so the seven-day bar was coloured by the FIVE-HOUR thresholds. Measured
2026-09-19 at the 0.61.0 defaults:

```
7d  86% -> red    while the week's own level was still below PACE
7d  94% -> red
7d  96% -> red    the week's level is PACE
7d  98% -> red    the week's level is STOP
```

⇒ That bar was at its loudest **fourteen points** before the week's own PACE point, and it
**could not tell 86% from 98%**.

- **Four new keys.** `colour_lead_soft_pct_7d` (**3**), `colour_lead_hard_pct_7d` (**2**), and
  the derived `colour_warn_pct_7d` (**90**) and `colour_alarm_pct_7d` (**95**).
  ⭐ The owner's specification of 2026-09-19: soft minus 3 turns orange, hard minus 2 turns red.
- ⚠ **The two leads differ from each other and from the five-hour 5, and that is the decision
  rather than an oversight.** The 7d pair sits high on purpose — the week is usually not the
  constraint — so a single lead of 5 would leave that bar green for almost the whole week and
  then jump. 3 and 2 keep a visible warning band without making it shout for days. That
  sentence lives beside the constants, so nobody "tidies" the asymmetry away.
- **`colour_lead_pct` (5) is NOT retired.** It shipped one release ago, the README documents it,
  and it is the five-hour lead. Adding a key and replacing it the next version is pure churn,
  and `install.py`'s `RENAMED` table exists because that hurts.
- `_state()`, `_colour()` and `_window()` take a `bands` argument carrying that window's
  `(warn, alarm)`; `None` means the five-hour pair, so every pre-existing caller behaves exactly
  as before.
  ⛔ **NOT by sniffing `window_secs`.** `_window()` already receives it, and deriving the bands
  from `7 * 86400` would be right today and silently wrong the moment a third window appears
  with a seven-day span and thresholds of its own. The caller knows which window it is drawing,
  so the caller says so. ⭐ Both seven-day bars go through it: `7d`, and the **model-scoped**
  weekly limit when the account has one.
- **The 7d pair is pinnable too**: a NUMBER on disk wins, pinning one of the pair into the wrong
  order restores both, `config.example.json` carries `null` for both derived keys, and
  `install.py --status` and `test_install.py` both REQUIRE that null.

**Seven mutations killed by the intended assertion.** ⛔ **The most important one survived at
first, and how it survived is the part worth keeping:** repointing the renderer's line back at
`colour_warn_pct` passed the **entire selftest**. The assertions tested the CONFIG, and the
config can be perfectly right while the bar is still drawn from the default pair. ⇒ There is now
a check that **drives the real `_line_parts()`** and reads the seven-day segment's own escape
codes. ⚠ And its first version missed the same mutation **again**: it asserted only that red was
absent, while that mutation changed only the ORANGE half — so an 86% bar came out orange, which
is not red, and the check passed. Both colours are asserted now.

⚠ Three traps hit while writing that check, all recorded in the code:

- `_line_parts()` has **no** `now` parameter. A first version passed `now=` whenever `"now"`
  appeared in `_line_parts.__code__.co_varnames` — but that tuple holds every **local**, not the
  parameters, so the guard was always true and the call raised.
- `lstrip("\033[0-9;m")` looks right and is not: `lstrip` takes a **set of characters** and `7`
  is one of them, so it eats the 7 out of the `7d` label and the segment is never found. A regex
  instead.
- `_line_parts()` returns a **two-tuple** `(segments, extras)`, not a list.

---

## 0.61.0

⚠ **A default threshold moves, so this is a MINOR release and not a patch.** 0.60.1 through
0.60.4 were all fixes, which trains a reader to read a patch bump as "nothing to decide". This
one changes behaviour for everybody who never overrode the defaults.

**The owner raised both five-hour thresholds.** `soft_pct_5h` **75 → 80** (PACE),
`hard_pct_5h` **85 → 90** (STOP).

**And the colour thresholds are now DERIVED rather than hand-set.** Asked what should happen to
the red bar at `colour_alarm_pct` 85, the owner ruled:

> Deliberately not equal — that decides what gets REFUSED, and a person wants to see the
> warning colour before anything starts being refused. Which makes me think the colouring rule
> itself should change: `colour_warn_pct` should be defined as `soft_pct_5h` minus n,
> `colour_alarm_pct` as `hard_pct_5h` minus n, and n should default to 5.

⇒ New key `colour_lead_pct` (default **5**). `colour_warn_pct` is `soft_pct_5h` − lead,
`colour_alarm_pct` is `hard_pct_5h` − lead. At the new defaults that is orange 75 and red 85 —
**the same two numbers as before**, now following the thresholds instead of sitting beside them.

- ⛔ **What this fixes was silent.** The two colours were typed numbers, so raising a threshold
  left them behind: red then said "nothing is refused yet" while the gate was already refusing.
  Before this release, anybody who set `hard_pct_5h` to 90 kept a red bar at 85.
- ⛔ **And two comments in this file contradicted each other.** The head of `DEFAULTS` said the
  colours were "ALIGNED WITH THE COLOUR THRESHOLDS BELOW, ON PURPOSE... orange means exactly
  PACE has begun and red means STOP has begun"; `_state()`'s docstring said they were
  "deliberately NOT soft_pct/hard_pct". The values matched neither: red 85 equalled hard 85
  while orange 70 led soft 75 by five. ⇒ One rule now, in one place, enforced by arithmetic.
- **An explicit number still wins.** Give either key a NUMBER in your own `config.json` and it
  behaves exactly as before — somebody who tuned the colours keeps what they tuned. ⚠ "Was it
  set by hand?" is read from the DISK, not from the merged `cfg`: after the overlay, "set to 85
  on purpose" and "defaulted to 85" are the same value.
- ⛔ **Pinning only ONE of the pair into the wrong order restores BOTH**, with a line on stderr.
  A red band that can never be reached is indistinguishable from a speed that never happened. A
  negative `colour_lead_pct` is refused too: it would put the colour AFTER the refusal, which is
  the single arrangement this design exists to prevent.
- ⛔ **`config.example.json` holds `null` for those two keys now.** An example is a thing people
  copy WHOLESALE: a number there pins their colours for ever and the derivation never fires for
  them again. `config()` only takes int/float off disk, so `null` means "unset".
  ⭐ `install.py --status`'s cross-check and `test_install.py` now both REQUIRE null there, so
  the example cannot drift back into a number.
- **`_state()`'s two fallbacks read `DEFAULTS`.** They were literals, and the comment beside
  them already recorded a past drift (one said 90 while `DEFAULTS` said 85). With derived
  defaults a literal would drift again the first time a threshold moved — in the worst
  direction, a colour claiming nothing is refused yet.

⚠ **Four files had fixtures encoding the old thresholds; all are now computed from them.** That
was the only real surprise, and it is its own lesson:

- `dispatch_gate.py`'s driven table used **78** to mean "a PACE" — the old soft 75 plus a
  margin. At 80 that is a GO, the positive control fires, and the failure reads as a regression
  in the hook.
- `test_guards.py` had **four** `usage_at(75)` calls — exactly the old `soft_pct_5h` — so four
  cases failed with a bare `AssertionError: GO` on a verdict they were not testing.
- `usage.py`'s own colour-band assertions typed **70/85**, which is a derived value copied by
  hand.
- `README.md`'s examples printed `PACE at 78%`, a line that **cannot occur** at the new defaults.
- ⇒ All now read `DEFAULTS` and sit a few points **INSIDE** each band rather than on its edge: a
  fixture on a boundary cannot survive the boundary moving by one.

---

## 0.60.4

**0.60.2 fixed one site out of five, and the one it missed is the loudest thing on the screen.**
When the seven-day window drives the verdict, `v["pct"]` - always the five-hour figure - was
still read directly in four places: the `USAGE(...)` log line, both `DENY(...)` log lines, and
⛔ the **dispatch refusal's** `systemMessage`, which is the strongest thing this plugin ever
does and is quoted in the README. So at 5h 3% / 7d 99% the screen read
`sub-task dispatch REFUSED - usage STOP at 3%`.

⇒ **One helper, `driving_pct(v)`, and all five callers use it**, returning `("7d ", 99)` or
`("", 90)`. The five-hour side is unchanged.

- ⭐ **The check pins the ROOT CAUSE, not the five messages.** `selftest()` asserts that the
  source of `on_user_prompt` and `on_pre_agent` no longer contains `v.get("pct") or 0` at all.
  A per-message check has to be written once per message and will miss the fifth - which is
  exactly how this was missed. Plus three unit assertions on `driving_pct()` itself, including
  that a verdict with no driver does not crash it.
- **Five mutations killed by the intended assertion**, one of them putting the five-hour figure
  back into the refusal message.
- **The refusal line is DRIVEN, not read.** A source pin proves the call is written, not that
  the string comes out right, and no driven row exercises `on_pre_agent`. ⚠ The probe's first
  run reported `decision: 'allow'`: **without a `state/<sid>.start` stamp every guard is
  advisory by design**, so the refusal branch never ran and the message under test did not
  exist. That is what the `decision == "deny"` positive control is for.
- ⚠ The probe also guessed the environment variable as `CLAUDE_DISPATCH_GUARD_STATE`; it is
  **`CLAUDE_DISPATCH_DIR`**. A wrong name falls back silently to the REAL state directory, so
  the measurement becomes this machine's current verdict rather than the fixture's.

---

## 0.60.3

**0.60.2's new filter flagged the continuation lines of a multi-line command as pollution** -
which is the fault it had just removed, moved one step over. ⛔ **A check that is red for an
unrelated reason is still a check that is red for an unrelated reason.**

`log()` writes a record as `timestamp + message`, and the message is the command text,
truncated by CHARACTER COUNT rather than at the first newline. So a heredoc - or any
multi-line command - leaves continuation lines in the log with NO timestamp prefix. Measured
2026-09-18 in the real log: 1383 lines without a prefix against 10145 with one. ⇒ A per-LINE
filter flags every one of them.

⚠ **0.60.2's three green runs did not cover this, and that is why it shipped.** Those three
runs were one Bash call, whose `CMD-ALLOW` was logged at `PreToolUse` BEFORE the window
opened - so zero new lines appeared inside any of the three windows. The filter's own two
controls did not cover it either: both fixtures were single lines carrying timestamps.

- **Per RECORD, not per line.** A line with no timestamp prefix is a continuation of the
  previous record and inherits its classification instead of being judged on its own.
- ⚠ **A leading continuation line is never flagged**: its record began BEFORE the window, so
  it is not new. Hence `live` starts True.
- ⭐ **Five controls now, and they cover multi-line records**: a `CMD-ALLOW` followed by two
  continuation lines flags none of the three; a `USAGE(...)` followed by a continuation flags
  BOTH (a suspect record must carry its continuation lines with it); a bare continuation line
  with no record start flags nothing.
- **Five mutations killed by the intended assertion.** ⚠ The per-line regression needed two
  attempts: turning `if head:` into `if True:` made `head.end()` raise on a continuation line,
  which is red by a crash rather than by the assertion under test and proves nothing. A
  mutation has to be valid code too.
- ⛔ **Why 0.60.3 and not a rewritten 0.60.2:** 0.60.2 is already published. Swapping the
  contents under a released version number is a lie about that number, and somebody may
  already have pulled it.

---

## 0.60.2

**A seven-day driven verdict printed the five-hour window's percentage.** The line the agent
is ordered to echo was built from `round(v["pct"] or 0)`, and `pct` is always the five-hour
figure. ⇒ At 5h 3% / 7d 99% the verdict is STOP, `v["text"]` correctly says the WEEK is nearly
spent and the five-hour window is not the constraint (5h 3%), and the very next sentence orders
`STOP at 3% - winding down`. On one screen, one half says the brake is on and the other tells
you to watch for a line reading 3% - which reads as a false alarm.

⚠ **Pre-existing, not from 0.60.1**: the same expression is in `550b556`. Found by 0.60.1's
round-2 review, which reported it as printing `0%`; measured, it prints the **five-hour**
number, and 0 only when that window is untouched.

- **It prints the DRIVING window's percentage, and says which window that is.** A seven-day
  driven line becomes `STOP at 7d 99% - winding down`; a five-hour driven one is **unchanged**,
  which is why nothing that quotes the shape needed editing. `verdict()` already returned
  `driver` and `pct_7d`, so no new computation.
  ⭐ The owner chose the labelled form over a bare `STOP at 99%` on 2026-09-18, with both side
  by side: the number alone cannot be told from a five-hour one, and the statusline is showing
  the five-hour figure at that same moment.
- **Two seven-day rows in the driven table.** Its thresholds are `soft_pct_7d` 95 and
  `hard_pct_7d` 97, not 75/85. ⭐ The five-hour rows now carry a second duty: they pin that the
  `7d` marker does NOT appear when the five-hour window drives.

**`test_guards.py` stopped comparing the state log's file SIZE.**
`case_selftests_never_read_the_terminal` compared `len(f.read())` of the real state-directory
log before and after running the shipped selftests. But every live session on the machine
appends a `CMD-ALLOW` line there on every Bash call, so any concurrent session failed the
assertion - with a message blaming the selftest.

⇒ **And it was not merely noisy.** That case runs immediately BEFORE the prose pin, so a red
there ABORTED the whole file before later assertions executed: a mutation check driven through
the whole file read as "caught" while the assertion under test never ran. Measured 2026-09-18:
three consecutive whole-file runs failed twice (105 and 143 bytes) and reached the rest only on
the third. Three consecutive runs after the fix are green.

- **It compares LINES and ignores a live session's tool traffic** (`CMD-ALLOW`, `CMD-DENY` -
  the two a `PreToolUse` writes on every call). Any other new line inside the window fails, and
  the message prints those lines.
- ⚠ **The residual gap, accepted deliberately:** a selftest writing a `CMD-ALLOW` or `CMD-DENY`
  line slips past the filter. The alternative is the size comparison, which was red on somebody
  else's traffic two runs in three and therefore protected nothing. **A check that is red for
  an unrelated reason is not a stricter check.**
- ⭐ **The filter has a control in the same run**: it must flag a `USAGE(...)` line and must NOT
  flag a `CMD-ALLOW` one. Without that, a filter matching nothing reports a clean pass for ever.
- **Prefix comparison with a set fallback**: the log is append-only in practice, but a rotation
  or truncation inside the window would make `len(before)` meaningless and read every old line
  as new.

**Four mutations killed by the intended assertion**, plus one standalone probe whose story is
the part worth reading (`scratch/06-fix-0.60.2/`):

- "a shipped selftest pollutes the state log" **cannot** be injected into `selftest()`. The
  quarantine that redirects `usage.state_dir` to a temp directory is installed in the
  `if "--selftest"` branch, BEFORE that function runs, so a write placed inside it lands in the
  quarantine and the mutation measures nothing.
- Worse, the `grep` that "confirmed" the probe line had landed was matching **its own command
  text**: the gate logs every Bash command to that same file, so searching the log for a string
  puts the string in the log.
- ⇒ The faithful version points the quarantine and the check at **one** temp directory. The
  shipped selftests wrote 21 real lines, all flagged, the message is the new one, and the
  owner's log was never touched.

⚠ **Never put a backslash in generated code.** The first probe wrote its newline as an escape
sequence, the injecting layer turned it into a real line break, the file stopped parsing and
`--selftest` exited 1 - caught by the check's **older** `assert rc == 0`, proving nothing about
the assertion under test. `chr(10)` instead.

---

## 0.60.1

**At PACE the hook ordered the agent to announce a wind-down. It must not.** The owner ruled on
2026-09-17: **PACE means "start no new batch"; STOP is the one that winds down.** The skills
already said exactly that; the code did not. The acknowledgement line the agent is ordered to
print verbatim came out of **one** format string fed `v["verdict"]`, so at PACE it told the
agent, in capitals and on every prompt, to print `PACE at N% - winding down` and to say in one
sentence **what it was dropping**.

⇒ That is PACE run as STOP, and it was louder than the skill prose it contradicted. Measured
twice on 2026-09-17: the rule was already in `dispatch-protocol`, in `unattended-work` §17 and
in this machine's memory file, and sessions still stopped early. ⛔ **Restating the rule does
not work; the LINE is what needs fixing.**

- **Each verdict has its own wording.** STOP keeps today's text (`STOP at N% - winding down`,
  "what you are dropping", escape hatch `- NOT winding down`). PACE becomes
  `PACE at N% - no new batch` and says plainly that at PACE the session drops NOTHING and hands
  nothing back - it only refrains from starting a new wave or a new heavy block. Its escape
  hatch is `- starting a new batch anyway`. ⚠ That phrase deliberately avoids the words
  "winding down": otherwise the new check is satisfied by a string that still says it on screen.
- **The acknowledgement MECHANISM stays; only the words change.** Demanding one verbatim line is
  the only thing that separates "it kept working" from "it never heard".
- ⭐ **The screen and the transcript are fed by ONE variable.** Both fields
  (`additionalContext` for the model, `systemMessage` for the person) now build from a single
  `ack_line`, so the line the screen tells you to wait for cannot drift from the line the
  transcript is ordered to print. That drift is invisible from a chair: the person waits for
  words nothing demands.
- **The skill's own prose said the opposite, and is fixed with it.** `unattended-work` §17 read
  "You hand over when the verdict says **PACE** or **STOP**" - it stood on the hook's side, and
  the two of them together told a session to hand over at PACE. Both language sides now say
  "⛔ AND PACE IS NOT A HANDOVER". ⚠ This was round 1's blocking finding: the code was fixed
  while `PENDING.md` closed that half as FIXED and the skill still contradicted it.
- ⭐ **The prose regression is pinned.** `test_guards.py`'s existing
  `case_burn_figure_never_winds_down` gains two FORBIDDEN patterns - the phrasings that actually
  shipped, one per language - and one required sentence, so the skill text going back is RED and
  not merely noticeable to a careful reader.
- **"batch" is bound to "wave".** `dispatch-protocol` gives batch a narrower technical sense (an
  owner-approved CONCURRENT group), so `no new batch` could be read as not covering one more
  ordinary sequential sub-task. The sentence after the acknowledgement line now says it plainly:
  a new batch means a new dispatch wave or a new heavy block, **sequential ones included**.
- **The check is DRIVEN, not read.** The selftest runs `on_user_prompt()` with a PACE payload
  (5h 78%) and a STOP payload (5h 90%) and reads the two fields it emits. ⛔ The old
  `assert "winding down" in src` passes on its own, because the new STOP branch still satisfies
  it - the defect was one string serving two verdicts, so the check has to see the two OUTPUTS.
- **It asserts the whole LINE, not the phrase.** Matching `` `PACE at 78% - no new batch` ``
  pins the verdict word and the percentage too; and matching the SAME string in BOTH fields is
  the only thing that pins the headline claim - that the screen cannot come to expect a line the
  transcript is not ordered to print.
- ⛔ **The wind-down INSTRUCTIONS stay STOP-only as well.** The acknowledgement line is only the
  label: a PACE tail rewritten to demand a handoff and the end of the turn satisfies every
  assertion above while doing the identical damage. So `END THE TURN` and `dropping` are
  asserted ABSENT at PACE and PRESENT at STOP.
- ⛔ **And both rows must actually have run.** Drop the PACE row from the driving table and every
  assertion above passes - the third silent route, beside `usage._relax` and the `warned` mark.
  The set of verdicts driven is now checked, and the table carries a trailing comma so removing
  a row cannot degenerate the tuple into that row.
  ⚠ Correcting an earlier claim in this entry: when a reset is too close (`usage._relax` returns
  GO) or the `warned` mark is already set, `on_user_prompt()` prints nothing - that is not a
  silent pass, it is `json.loads("")` raising, with a message about JSON rather than about the
  wording. What actually guards that route is the positive control: `usage.verdict()` must first
  read the fixture as the verdict under test.
- ⛔ **AND THE SCREEN FIELD NEEDS ITS OWN ROW.** The cue check first read `additionalContext`
  alone, and round 2 measured `seen_why` rewritten to order a handover on the USER'S SCREEN
  passing the whole suite. Both fields are checked now, with different rules: a cue belongs in
  `additionalContext` at STOP and nowhere else, and in `systemMessage` at NO verdict - that
  field is the person's one-line expectation note and issues no orders at all.
- **The two prose patterns are TIGHT, and that is the fix, not an oversight.** The first
  version matched PACE anywhere near "hand over when the verdict", and round 2 measured it
  going **red on the CORRECT rule** written the obvious way ("You hand over when the verdict is
  STOP, not PACE"). A detector that blocks the right edit is worse than one that misses a
  paraphrase: the required sentence already catches removal, while a false red gets the check
  deleted by the next person who hits it. Four false-positive controls now ship beside the two
  positive ones.
- **The required-sentence loop counts its iterations**, and the failure message for a PACE
  finding no longer blames the burn figure. A loop whose filter matches nothing asserts nothing
  and reports success - the same silent route the verdict-set check closes.
- `dispatch-protocol` said handing over is "triggered by the WORD" without naming which. It
  names **STOP** now, in both languages, and says PACE is not one.
- **Eight mutations killed in total, each by the assertion it was aimed at**, every one verified
  by reading the AssertionError **message** rather than the exit code. Two were run by hand
  against `3e1ee3b` - rebuilding the PACE words from `v["verdict"]`, and putting "winding down"
  back into the PACE escape hatch. The other six are scripted and repeatable in
  `Memory/tasks/20260918-092012-pace-says-winding-down/scratch/04-fix/mutate.py`: the table
  losing its PACE row, `END THE TURN` and `dropping` in the PACE tail, skill §17 saying "hand
  over at PACE" again, and that sentence removed in each language.
  ⚠ Two traps that script now documents, both of which make a mutation look like a pass: an
  anchor containing `\n` matches nothing in this repository's CRLF files and the case is
  SKIPPED; and the whole of `test_guards.py` aborts on the known state-directory log-size
  comparison BEFORE reaching the prose pin, so the skill mutations drive
  `case_burn_figure_never_winds_down` directly. The pin was still proven through the whole
  file, on the third attempt, once that neighbour was quiet.
- `README.md` updated on both language sides, and a stale threshold in the same block fixed
  along with it: it said PACE defaults to 85% and STOP to 93%, where the real defaults are
  `soft_pct_5h` 75 and `hard_pct_5h` 85 - and its 90% example is already a STOP.

⚠ **The `SPENT in ~N min` burn line is a SEPARATE issue and is not in this release.**
See `Memory/tasks/20260914-124312-burn-line-read-as-a-stop-signal/`.

---

## 0.60.0

**Only one session's resume survived on a machine; every session now has its own.** Every
artefact of the mechanism was keyed to the MACHINE - one `resume.json`, one OS task name, one
auto-arm spawn mark, one failure marker, and the "is anybody alive?" test - so the second
session to arm silently took the first one's slot. **Measured 2026-09-17:** three different
sessions held that one slot inside three hours, and one record carried one session's task
folder together with **another** session's working directory - that alarm would have run in
the wrong repository.

- **The record is `<state>/resume/<session>.json`.** ⛔ **Deliberately NOT in `state/`:**
  `prune_state()` sweeps that folder by age, and a resume can be armed against the SEVEN-day
  window - so with `state_keep_days` set low the record dies while its OS task is still
  registered, and the alarm wakes to `RUN-ABORT`.
- **The OS task is `ClaudeDispatchGuardResume-<dir8>-<session>`.** `dir8` hashes
  `normcase(realpath(state_dir))`, so two state directories cannot collide on one name, and
  spelling the same directory two ways cannot make it fail to recognise its own tasks.
- **The arming session id is PASSED, not guessed.** `do_arm` fell back to "the newest
  `state/*.alive`", and that function's own docstring says the guess is wrong when two
  sessions are live - precisely the case this feature exists for.
- **The spawn floor is per session too.** This was the second half of the single-slot bug:
  even with a record and a task name each, a machine-wide 300 s floor still blocked a second
  session's arm outright.
- **The fire-time test asks only whether the session that ARMED it is awake.** It used to ask
  whether ANY session was, and `heartbeat()` stamps before any branch - so the answer is yes
  whenever any session exists, including the headless `claude -p` a resume itself spawns, for
  up to three hours. ⛔ **A safety property is given up:** a resume may now start while you
  work in a different session. Deliberate, and approved by the owner - keeping it costs the
  entire feature on a one-machine setup. The bounds are the screen line printed when it arms,
  `resume.py --cancel`, and the fact that a resumed run works in its OWN recorded task folder
  and cwd.
- **A takeover line in the handoff stands a resume down.** A session picking up somebody
  else's task writes `⛔ TAKEN OVER <timestamp> by ...` into that `HANDOFF.md` immediately;
  the alarm reads it and stands down if it is newer than the arm. ⚠ The timestamp is IN THE
  TEXT, never the file's mtime - `git checkout/pull/stash/merge` set mtime=now on every
  tracked file, so an mtime rule would let one `git pull` stop every armed resume on the
  machine. ⚠ Unparsable, missing or older than the arm: it RUNS. Redoing work wastes a
  window; refusing to run loses it.
- **One failure marker per session, and all of them are announced.** Two resumes failing in
  one night left ONE message: the second write overwrote the first and the reader deleted it.
  The message now also names WHICH task stopped.
- **Reaping:** a record and its task go once the alarm time is past the whole retry window AND
  the scheduler no longer holds the job. ⛔ It probes only names it already holds (~115 ms
  each) and **never enumerates the machine's tasks** - measured at 3.7-6.8 s against 489 tasks,
  under a 15 s SessionStart timeout, and **a hook that times out FAILS OPEN**: housekeeping
  would have disabled enforcement.
- **The uninstaller enumerates by prefix.** It queried one fixed name, so after the rename it
  would have left every per-session task registered - the exact hazard its own header names.
- **Every handoff must say WHO the session is.** A resume wakes a fresh `claude -p` with a new
  session id (**never** `--resume`: ~95k tokens/MB at zero cache read), so the successor can
  only keep a name this file gives it. `handoff_warnings()` says so when neither a session id
  nor a role appears. ⚠ A warning, never a refusal.
- **Two pre-existing defects fixed alongside:** a POSIX `--cancel` ran `atrm -a` and deleted
  EVERY `at` job the user had, including jobs this plugin never created - it now removes only
  the recorded job number, and `atrm -a` moved behind an explicit `resume.py --cancel --all`.
  And the scheduled command carried no `--dir`, so anyone using `$CLAUDE_DISPATCH_DIR` had an
  alarm that fired against the DEFAULT directory.
- **An upgrade does not lose an armed alarm:** a pre-0.60 record is moved under the session id
  it already records; one WITHOUT a session id is ⛔ **left alone** and reported by `--status` -
  inventing a name for somebody's armed alarm is worse than saying it is theirs to clear.
- ADR: `Memory/tasks/20260917-132015-parallel-per-session-resume/` (two adversarial review
  rounds; round 1 REJECT with five blockers, round 2 judged all five resolved and found four
  more). Nine mutations killed, and an existing check caught a defect this change introduced -
  the migration sat at the top of `main()`, so `resume.py --selftest` migrated a LIVE record in
  the real state directory.

---

## 0.59.1

**The state/ directory grew unbounded; it is now reaped.** Every session leaves a set of
per-session markers in state/ (`.start`, `.branch-*`, `.skill-seen-*`, `.warned*`,
`.handoff-written`); they are dead the moment the session ends. `prune_state()` reaped only a
few kinds and missed the bulk - `.branch-*` alone was 179 of 322 files. It now sweeps ALL of
state/ by age with only two carve-outs: `.alive` is bounded by count, and `.slot*` is never
touched (live concurrency state with its own minute-scale reclaim). A marker kind added later
is covered automatically instead of being missed the same way.

- **`state_keep_days` is configurable, default 7 days** - shipped so every install applies it
  and keeps cleaning, not just this one machine.
- ⚠ It is a SAFETY margin: a live session's `.start` is the switch that keeps its brake ON, so
  the window must exceed the longest a single session can run. 7 days is that margin.
- ⚠ DELETE-SAFE like `history_keep_days`: a string, a negative, 0 or null keeps EVERYTHING
  (coerced by `usage._days()`, not listed in NUMERIC_KEYS).
- Selftest covers the age sweep across kinds, recent-kept, `.slot*` untouched, the `.alive`
  count bound, and delete-safety; three mutations killed (age check, `.slot` exception,
  delete-safe). Dry-run on the real folder: 170 files >7d swept, 132 recent kept.

---

## 0.59.0

**Near a reset with the budget surviving, the brake no longer PACE/STOPs.** The old rule read
only the fixed thresholds, so a window about to reset with headroom to spare was paused anyway -
in the data, 89% of pauses were wasted, and near the reset (<=60 min) 100% of paused rows
survived. A projection layer now RELAXES a PACE/STOP to GO near a reset when the whole-window
burn rate says the remaining budget survives to the reset. It only ever loosens; it never adds
caution.

- **The rate is WHOLE-ANCHORED (`pct / minutes since the window opened`), not a short trailing
  rate.** The reason is hard: the per-tool-call brake runs `level()` = `verdict(cheap=True)` while
  the display runs the full `verdict()`, and the two MUST produce the same word - a trailing rate
  needs a history parse the cheap path cannot afford. Whole-anchored needs no history, is never
  None, and is account-safe by construction. Measured (`ab_rate.py`) it recovers one MORE wasted
  pause than `max(whole, trailing)` at zero added danger. This deviates from the ADR's
  `max(whole, trailing)`; see `Memory/tasks/20260916-143157-projection-stop-rule/REVISION-whole-anchored.md`.
- **Per-window ceiling and horizon.** 5h: do not trust a projection beyond 60 min from reset;
  never relax at or above 95%. 7d: NO horizon constant (the whole-window rate self-scales); never
  relax at or above 99% - 99 is the minimal backstop that lets the owner's approved case (7d 98%
  left, near reset -> GO) fire.
- **The NET zone when a STOP is relaxed.** The main session keeps working, but: a resume is armed
  automatically, the agent is asked to rewrite HANDOFF.md every ~10 min, and a NEW dispatch (a
  sub-agent) is REFUSED. The main session finishing its own sequential list is not a new dispatch.
  A sub-agent would burn the budget the relaxation counts on and is not covered by the armed
  resume, so it is blocked.
- **Default `soft_pct_5h` changes 70 -> 75.** Every install's PACE point moves up with it.
- Retires `_soften_near_reset` and `near_reset_min` (the old 20-min one-level soften, a cruder
  special case of this projection); adds a `SEVEN_DAY_SECONDS` constant and the keys `relax_margin`
  (1.5), `relax_horizon_min` (60, 5h only), `relax_ceiling_5h` (95), `relax_ceiling_7d` (99).
- `usage.py --selftest` gains a cheap/full word-AGREEMENT grid (the check `level()`'s docstring
  promised but that did not exist) plus a "the projection never TIGHTENS" invariant. All five
  fail-open guards are mutation-killed (ceiling, horizon, survives, cheap/full divergence,
  tighten). The gate's NET guards (resume arms, resume not stood down) are mutation-killed too.
- ⚠ Falsifiable reconsideration: a WALL-HIT (a relaxed window that then reached the cap before
  reset) is logged; any hit -> tighten (raise margin, lower a ceiling); a clean period -> loosen
  (lower margin). Ships at a conservative margin 1.5 first. The ADR (two adversarial review
  rounds) is in `Memory/tasks/20260916-143157-projection-stop-rule/`.

---

## 0.58.4

**Usage froze during a long FOREGROUND agent, and the brake failed open.** A supervisor that
dispatches ONE long sub-agent and waits fires no hook of ours and writes no ~/.claude.json
until the agent returns. Both of the watcher's liveness sources (`state/*.alive` and
~/.claude.json) go stale mid-run, so the watcher crosses `idle_after_min` (default 15) and
PAUSES - during exactly the stretch that is still spending tokens. ⛔ A frozen number reads
LOW, so the brake fails OPEN during the heavy run it exists to govern.

⚠ This is not fixed by lengthening or shortening the API interval. The 120 s floor is measured
(60 s drew 429s and went blind), and a longer interval only makes the number older and lower.
The missing thing is not frequency - it is a signal that says work is still happening.

- `last_heartbeat_min()` gains a THIRD source: an in-flight dispatch slot (`state/*.slotN`).
  The gate writes it when a dispatch STARTS and removes it on that dispatch's PostToolUse, so
  an open slot is proof work is happening NOW with no hook in between. The watcher keeps its
  NORMAL 120 s cadence - it never polls faster, so it cannot spend the endpoint's ~5-call budget.
- ⛔ Capped at `slot_ttl_min` - the same clock `claim_slot()` uses to reclaim a dead slot. A
  dispatch that dies before its PostToolUse stops counting past that age, or one crashed
  dispatch would keep the watcher polling all night, the failure `idle_after_min` exists to
  prevent (`Memory/tasks/20260902-082020-stale-slot-after-a-failed-dispatch/`).
- ⚠ Returns 0.0, not the slot's age. An open, non-stale slot means work is happening NOW; its
  age is how long the agent has run, not how long since anyone worked. Feeding the age back
  would make a 20-minute agent read as 20 minutes idle and pause anyway.
- Ceiling stated up front: this removes a FALSE pause, it does not make the number live. The
  best during a long agent is still 120-150 s stale, not 2 minutes.
- ⚠ PRECONDITION: it only helps a session running `usage.py --watch` (the VS Code task) or the
  statusline - that watcher IS the timer this un-pauses. With neither, the only refresh path is
  `keep_clock_running()`, which fires from the gate hook and is silent during the agent, so the
  number still freezes. `usage.py --watch` is the repair.
- `usage.py --selftest` isolates the new source (both existing sources stale, only the slot as
  variable). Two mutations were measured to fail it (source removed - an open slot reads idle;
  cap removed - a dead slot counts for ever). True BACKGROUND dispatch is unaffected: it is
  already forbidden by `dispatch-protocol` refusal #2, because it escapes accounting.

---

## 0.58.3

**0.58.2's own text told the reader to delete a paragraph its own check requires.**
`unattended-work` §17 said `dispatch-protocol` "holds the one live copy of the rule", while
`case_burn_figure_never_winds_down` asserts that **all four** skill files mention the figure.
Following that sentence and deleting §17's paragraph fails the check - an instruction that
trips the guard.

- Reworded: `dispatch-protocol` carries the full rule with its measurement, §17 carries its
  scope line, and both have to stay. Both languages.

---

## 0.58.2

**The `SPENT in ~N min` line stopped agents at 20% of the five-hour window.** The owner
reported agents reading that burn figure as "usage is nearly gone", arming a resume and
winding down - while the verdict said GO.

⛔ **The defect was in the prompts, not the code.** The brake reads the percentage and never
this figure - the owner's decision of 2026-08-29 (`Memory/notes/SHELVED-burn-meter.md`:
「GO / PACE / STOP 派工或剎車都不參考這個值」), pinned by a check in `usage.py`. But from
0.56.2 to 0.58.1 the skills said "N is your budget ... write the handover BEFORE it runs out"
and "STOP for a new wave" - **prose enforcing exactly the rule the code refuses to enforce**,
and prose is the half that actually reaches the agent.

⚠ **And the line fires at the START of a window, not the end.** The rate is anchored at the
window's own open, so a young window makes any spend look steep. Measured 2026-09-14: at
**10% used, 10 minutes in** it prints `SPENT in ~90 min`; the **same 10% at 45 minutes in**
prints nothing at all. The ⛔ is loudest exactly where the headroom is largest.

- Both skills rewritten: **N answers exactly one question - does the block I am about to START
  fit inside N?** Handing over, writing `HANDOFF.md` and arming a resume are triggered by the
  WORD (PACE / STOP) and by nothing else. At GO you keep working, however small N is.
- `unattended-work` §17 **moves** the usage rule out of "Handover when context runs short". It
  was filed under a handover instruction, and that placement was doing work no rewording could
  undo. `dispatch-protocol` now holds the one live copy.
- ⭐ **The zh-TW files never carried the bad rule**, so a grep for the English phrasing read
  clean across half the repository. Both languages now carry the same tightened rule; the drift
  is closed.
- `test_guards.py` gains `case_burn_figure_never_winds_down`: none of the four skill files may
  contain any of six phrasings that actually shipped, and a file that discusses the figure must
  state the "at GO you keep working" scope. Three mutations were measured to fail it (the
  English phrasing restored, the required sentence removed, the Chinese phrasing restored).
- ⚠ `usage.py` is untouched. The line still hangs a ⛔ off a GO verdict beside "Headroom
  available" on the same line - raised with the owner, not acted on.

---

## 0.58.1

**0.58.0's Bash rule counted a READ as a write.** The round-2 code review measured it through
the real hook process: "the command contains `HANDOFF.md` and a `>` anywhere" recorded a folder
from `cat …/HANDOFF.md 2>&1`, from `> /dev/null`, from a `>` inside a grep pattern and from a
sentence in a heredoc - and one Stop at PACE armed a finished task again (the mtime failure
through a narrower door). The live 0.58.0 gate on the reviewer's own session recorded a fake
folder name from a heredoc in its report.

- The Bash rule is now: `>` or `>>`, optional spaces and one quote, then IMMEDIATELY a path
  ending in `HANDOFF.md`. `test_guards.py` asserts six read / mention / variable shapes record
  nothing and the quoted and heredoc write shapes record; the mutation (old rule restored) fails
  at "a Bash command that does not write HANDOFF.md was recorded".
- When a GO prompt cancels the alarm, the CANCELLED line now reaches the screen
  (`systemMessage`); 0.58.0 gave it to the model only.
- `state/<sid>.warned` and `state/<sid>.handoff-written` are pruned by age like `.start`; they
  never were.
- Docs: the PROTOCOL gaps row, ADR ⟨R2b⟩, one stale comment.
- ⚠ Residual, named and not closed: the record holds a folder NAME, so a same-named folder in
  another tree or `HANDOFF.md.bak` can satisfy it.

---

## 0.58.0

**The resume is now armed by the hook when the turn ends, not by the agent remembering.**
On the afternoon of 2026-09-02, two dev machines, same plugin version: one session wrote its
HANDOFF.md at PACE and then dispatched a reviewer - the auto-arm lived on the Agent `PreToolUse`
path, so it was armed; the other obeyed PACE ("no new wave"), wrote its HANDOFF.md and ended the
turn - the arm code never ran, the STOP text asked it to run `resume.py --arm` by hand, it did
not, and it later confirmed the omission. ⛔ **A step that depends on an agent remembering is
not a step.** ADR: `Memory/tasks/20260902-142400-auto-arm-on-stop/ADR.md` (one adversarial
review round; the owner had decided).

- `hooks.json` subscribes to `Stop`. When a turn ends at PACE or STOP and the task root holds a
  HANDOFF.md **written after this session started** (mtime ≥ the session stamp, ≥ 200 chars), the
  gate arms the resume itself and puts one line on the screen: armed for `<folder>`, wakes after
  the reset, cancel with `resume.py --cancel`. It never blocks the turn; when it does not arm it
  prints nothing.
- `UserPromptSubmit` at PACE / STOP runs the same step, so a handoff written after the warning is
  armed on the next prompt.
- ⛔ **"Written this session" is RECORDED, not inferred from a clock.** The first version used
  "mtime ≥ the session stamp", and the code review measured `git checkout` handing every tracked
  `Memory/tasks/*/HANDOFF.md` mtime=now: one Stop at PACE armed a **finished** task's folder
  (`fresh=3`, the newest-dated one - exactly the guess `maybe_auto_arm()` refuses). Time is a
  proxy that pull / checkout / merge can move. The gate already sees every Write/Edit `file_path`
  and every Bash command on `PostToolUse`, so it now records which task folders' HANDOFF.md this
  session wrote (`state/<sid>.handoff-written`); the candidates are exactly those folders, then
  `handoff_state()` (present, ≥ 200 chars, mtime ≥ stamp). ⚠ A Bash write whose path hides in a
  shell variable is not seen (the file tool is the documented route); unseen means nothing armed
  and a log line - the safe direction. Several usable → the newest, logged as
  `written=N usable=M session=`; ⛔ no session stamp → nothing and `AUTO-ARM-STOP-SKIPPED no
  session stamp` (ADR review B-2); no recorded write → nothing and a log line.
- ⛔ One row of `stand_down_resume()`'s verdict table changed: **a PACE prompt now KEEPS the
  alarm; only GO cancels.** It used to cancel on GO or PACE; with the turn's end arming at PACE
  the code review simulated a 20-turn PACE session and measured **20 arms, 19 cancels, three log
  lines per turn and an "ARMED" line on 19 of 20 prompts**. PACE is not "the window reopened
  early" - it IS the closing window - and the alarm is inert while the session lives (`do_run()`
  stands down on a live session). Result: one ARMED line at the first PACE turn end, silence
  after (de-dup), one CANCELLED line when GO arrives. A successful cancel still clears the 300 s
  spawn-floor file (a GO → PACE return inside five minutes needs it). ⚠ Consequence stated: a
  person who finishes at PACE and leaves gets one wake after the reset that reads a handoff
  describing finished work - the same exposure STOP has today; the screen line and
  `resume.py --cancel` are the bound.
- Checks left behind (`test_guards.py::case_arm_on_stop`; `subprocess.Popen` and
  `resume.do_cancel` are recorders, so no real OS task is created or deleted): a HANDOFF.md fresh
  by mtime that this session never wrote → silent, logged `no HANDOFF.md write observed`; a Write
  `PostToolUse` records the folder, a Bash redirect records too, an unrelated Write does not; GO
  silent; `Stop` at PACE → the newest RECORDED folder, said on screen, logged `written=2
  usable=2`; once per target; recorded-but-stale / thin → silent and logged; no stamp → silent
  and logged; a PACE prompt arms too; the start-time cwd decides the scan root; a PACE prompt
  keeps the alarm; a GO prompt cancels it and clears the floor; the next PACE turn end re-arms.
  Five mutations in progress.md.
- ⚠ What this change cannot see: `Stop` does not fire on a user interrupt (the next prompt
  covers it); two sessions on one working tree each arm only what they themselves wrote (the
  record is per session); the `Stop` hook is awaited - measured through `run.sh` at about
  **1.0 s** per turn end, the same as every other hook call this plugin makes.
- Needs Claude Code 2.0.56 or later, the existing minimum; the `Stop` event is present in that
  build (measured).

---

## 0.57.0

**The burn-rate history mixed two accounts, and nothing afterwards could tell them apart.**
Measured 2026-09-02: two Claude accounts' five-hour windows reset **0.081830 s** apart, the
history filter's tolerance is one second (and `stamp()` rounds to the second anyway), and a
history row recorded no account - so rows from both accounts landed in one bucket. The live
history was already mixed that day: thirteen rows in one five-hour window whose seven-day value
took three different numbers, which one account cannot do. It was lucky: the new account sat
HIGHER, so the rate stayed plausible (0.600 %/min shown, 0.653 from the post-switch rows
alone); lower would have gone negative and silently blanked the gauge, much higher would have
shown a large false rate with nothing saying so.

- **Every history row now carries `acct`**: `cachedUsageUtilization.accountUuid` from
  `~/.claude.json` - it sits beside the numbers Claude Code cached itself, so nothing has to ask
  "who is signed in". ⚠ A label only, never the numbers (that block's `fetchedAtMs` measured
  twenty-one minutes stale). Unreadable is `null`, never a guess. ⛔ `userID` is NOT the
  account - same machine, two accounts: `userID` identical, `accountUuid` different. It tracks
  the machine.
- **`_burn_rate()` refuses to mix**: a row is kept only when its `acct` is known, the current
  account is known, and they are equal. Unknown on either side drops the row. Legacy rows have
  no `acct` and are dropped - correct, not a regression. ⚠ **The blank is accepted**: after a
  switch the gauge reads `--` for up to `burn_window_min` (10 minutes by default). That is the
  honest answer and it beats a wrong number. It is not softened by falling back to unlabelled
  rows - that fallback IS the bug.
- **A switch is said once**: `token_usage.json` carries `acct` too, and when two consecutive
  fetches have KNOWN, DIFFERENT ids one line `ACCOUNT-SWITCH <8>.. -> <8>..` goes to the
  state-directory `dispatch_gate.log`. Unknown → known is not a switch; one switch is one line.
  Otherwise a blank gauge and a broken gauge look the same on screen.
- Checks left behind (`usage.py --selftest`): the collision itself as a fixture - two accounts,
  resets 0.08 s apart, rows from both in one file, the rate computed from A's rows only (A alone
  1.000 %/min; mixed would be 3.500, a wrong NUMBER rather than a blank so the mutation check can
  see it); an unlabelled row is dropped; a blank rather than a wrong rate when nothing usable
  survives; every new row is labelled; a switch is logged once. Mutation-checked: with the
  account filter removed it fails at `rows from two accounts were mixed into one rate: got 3.500
  %/min, expected 1.000`; with the `acct` write removed it fails at "every new row carries the
  label".
- The pinned check "no burn figure reaches GO / PACE / STOP" still passes unchanged.
- ⚠ "`--` for up to `burn_window_min`" holds for the default **trailing baseline** only. With
  `burn_window_min` 0 (or inside the first `burn_window_min` minutes of any window) the baseline
  is the window's own start `(opened, 0)` and no row is consulted, so a switch shows a number:
  correct for the account signed in now, but not a blank.
- ⚠ What this fix cannot see: the label is only as fresh as Claude Code's own write of
  `cachedUsageUtilization` - a fetch made before that write is labelled with the PREVIOUS
  account, is kept, and can move that account's rate for up to `burn_window_min` (the review
  measured one such row moving B's rate 0.249 → 0.555 %/min). With `$ANTHROPIC_TOKEN` set the
  numbers belong to the token's owner, whom the profile does not know, so the label is
  "unknown" and the gauge blank on the trailing baseline (the same decision `_account_ids()` makes; the review's one
  BLOCKING finding, fixed in this version). Under `CLAUDE_CONFIG_DIR` the label follows it while
  the credentials path is fixed at `~/.claude/`, so the two can come from different profiles
  (pre-existing; named here, not changed). Old history rows never gain an `acct` and are not
  repaired (owner's decision); the Fable / scoped-window logic is untouched (owner accepted the
  current behaviour 2026-09-02).
- README (both languages): the example history row shows `acct`.

---

## 0.56.2

**The 0.56.1 refusal that names the slot holder could take the refusal down with it.** The
review of 0.56.1
(`Memory/tasks/20260902-082020-stale-slot-after-a-failed-dispatch/agent-01-adversarial-review.md`)
measured it: with `slot_ttl_min` large enough, `time.localtime(started + ttl * 60)` inside
`held_slots_note()` raises `OSError(22)`, and that call sat inside `deny()`'s argument list -
so `main()`'s outer handler swallowed it, the process exited 0, and stdout was empty.
⛔ **A hook that prints nothing has approved the call.** The log said `DENY(slots-full)`; the
dispatch went through. The words added to make the refusal safer were the words that made it
disappear.

- The note now goes through `safe_held_slots_note()`: any exception becomes an empty string
  plus one gate-log line `HELD-NOTE-FAILED <exception>`. The refusal always prints; the note
  is the optional part. When the note is blank the refusal says so - "the holder could not be
  listed, the gate log has a HELD-NOTE-FAILED line, the slot still clears itself N minutes
  after it was claimed" - instead of "at the time shown above" over three empty lines.
- ⛔ **A second hole of the same class, found by this version's review and closed here: a
  wrong TYPE in `slot_ttl_min` also let the dispatch through.** `"abc"`, `null`, `"30"` and
  `[30]` made `claim_slot()` raise `TypeError` at `cfg["slot_ttl_min"] * 60` - earlier than
  the note, before any refusal - so the process printed nothing and the dispatch was allowed;
  `false` or a negative number reclaimed every slot on every dispatch, which is the
  concurrency limit switched off. `gate_config()` now type-checks the three numeric keys
  (`slot_ttl_min`, `approval_ttl_min`, `max_slots`): a string that parses is kept, anything
  else falls back to the default, and the gate log gets one `CONFIG-IGNORED(<key>=<value>)`
  line per read for as long as it stays wrong. ⚠ `max_model_price` is deliberately NOT in
  that list: it has its own parsing (a model name is accepted, `null` switches the check off,
  a typo fails open with `MODEL-PRICE-LIMIT-UNKNOWN`), and `test_guards.py` pins all three.
  ⛔ Round 2 of the review measured one more: `max_slots` = `1.5` - a positive number that is
  not whole - made `range(1.5)` raise `TypeError` on both the claim and the release path: with
  a concurrency approval in place the dispatch was ALLOWED, and no slot was ever released again.
  `max_slots` must now be a whole number, else the default plus a log line; the lifecycle check
  drives one `PostToolUseFailure` through the real process under `max_slots: 1.5` and requires
  the slot to be released.
- ⭐ The `dispatch-protocol` skill gains a paragraph: the `--verdict` line also says "at the
  current rate the window is SPENT in N min, M min BEFORE it resets". N is the budget - fit
  the remaining work into it and write the handover before it runs out; do not compute it, act
  on the number the line prints. (Asked for by the owner on 2026-09-02, because that reading
  saved this very release once.)
  `test_slot_lifecycle.py` fires six bad values through the real hook process; each must be
  `deny` and the live slot must survive. Mutation-checked: with the type check removed it fails
  at `FAIL-OPEN: ... slot_ttl_min='abc'`.
- `--selftest` gains a case: with `slot_ttl_min = 1000000000` the bare `held_slots_note()`
  must raise `OSError` (or the check injects nothing), and the wrapped one must return blank
  and leave that log line. Mutation-checked: with the `try` removed it fails, and the failure
  text is `OSError: [Errno 22] Invalid argument`, not an `AssertionError`.
- `Tools/Debug/test_slot_lifecycle.py` gains a step: while slot0 is held, write
  `{"slot_ttl_min": 1000000000}` into the sandbox `config.json`, fire one more dispatch
  through the **real hook process**, and require the decision to still be `deny` and the log to
  hold `HELD-NOTE-FAILED`. ⚠ `None` from the process IS the fail-open, so it is asserted by
  that name before the decision is read. Mutation-checked: with the `try` removed it fails at
  `FAIL-OPEN: the gate printed nothing with slot_ttl_min huge - the dispatch is allowed`.
- ⛔ **Minimum Claude Code version: 2.0.56** - the first build that knows
  `PostToolUseFailure`. An earlier build meeting one unknown event name silences **every**
  hook of that plugin (the review measured it with a minimal pair on 2.0.30 / 2.0.55 /
  2.0.56). Declared in `README.md` (both languages) and in `plugin.json`'s `description`.
  `install.py --status` (which is what `/dispatch-guard:status` runs) now reads
  `claude --version`: below 2.0.56 it prints ⛔ and OVERALL reads not live; unreadable or
  missing is "unknown" - never a crash, never a false OK. `test_install.py` keeps the
  comparison honest: 2.0.55 → OLD, 2.0.56 → OK, 2.1.258 → OK, garbage / empty / no `claude`
  on PATH → UNKNOWN.
- `PROTOCOL.md` line 95 now agrees with line 42: the gate does register
  `PostToolUseFailure`, but that branch only releases the slot and records `FAILED:` in
  `progress.md`; the wind-down still does not fire there.
- The residual gap is stated wider: not only "the whole turn dies" - an `Agent` call with an
  invalid `subagent_type` fires **neither** terminal event while the turn carries on. Both
  cases wait out `slot_ttl_min`.
- Known and NOT fixed here (recorded as its own task in
  `Memory/tasks/20260902-103321-slot-fail-open-and-account-mixing/progress.md`):
  `test_resume_cancel.py` writes 703 bytes into the real state log, which lands in
  `test_guards`' window, so the **first** `test_all.py` run can show 11/12 and later runs are
  clean.

---

## 0.56.1

**"1 sub-task is already in flight" now says which one, how old it is, and when it clears.**
Measured 2026-09-02 on another machine: the first dispatch died to an API 529, its
`PostToolUse` never ran, so its slot was never released; every later dispatch was refused;
`ListAgents` showed ZERO agents alive; and the session - reading the record as stale, which
it was - **deleted this plugin's own enforcement state by hand.**

That slot would have been reclaimed on its own after 30 minutes (`slot_ttl_min`), but the
refusal never said so. ⇒ **A wait with no visible end reads as a broken gate.**

- The refusal now lists every held slot: its description, the time it was dispatched, its age
  in minutes, and the wall-clock minute the gate reclaims it.
- It says plainly that a dead dispatch is not stuck - wait for that minute and dispatch again
  - and ⛔ **never delete a slot file to get past the refusal**: deleting a live one hands the
  same slot to two dispatches.
- ⭐ **And the root cause was not only the wording: a FAILED tool call fires
  `PostToolUseFailure`, not `PostToolUse`.** The plugin subscribed only to the latter, so
  **every failed dispatch** held its slot for the full 30-minute TTL - not just the reported
  529. Measured 2026-09-02 against Claude Code 2.1.251 with a probe hook: one failing Bash
  call produced `PreToolUse` and `PostToolUseFailure` carrying the SAME `tool_use_id`, and no
  `PostToolUse` at all.
  ⇒ `hooks.json` now subscribes to `PostToolUseFailure`; the gate releases the slot on it and
  writes one `FAILED: <error>` row to `progress.md`.
- ⚠ The remaining gap, stated: if the whole turn dies (the API error kills the parent session
  rather than the tool call), no event fires and the slot waits out `slot_ttl_min`. That is
  the case the refusal text above is for.
  ⚠ **(Added in 0.56.2) It is not the only such case.** An `Agent` call with an invalid
  `subagent_type` fires **neither** terminal event while the turn carries on (measured
  2026-09-02). Both cases wait out `slot_ttl_min`.
- New check `Tools/Debug/test_slot_lifecycle.py`, wired into `test_all.py` (now 12): it drives
  the gate as real subprocesses through allow → held → refused BY NAME → released on failure →
  allowed again.
- The reclaim, the TTL and the atomic claim are unchanged.

---

## 0.56.0

**The ADR that passed three rounds is implemented.** Its central judgement: a warning is
advice a model can ignore, so the plugin's guarantee against a usage limit must be an action
the gate takes itself - arming a resume - and that arming must never depend on the model
having done something first.

- ⭐ **The wind-down now fires from the path EVERY tool call crosses.** Measured 2026-08-31:
  183 Read, 172 Write, 36 Bash, **zero Agent calls**, and no user prompt in the burn window -
  while the two places it used to fire from were a dispatch and a user prompt. The gate
  received every one of those calls and returned early. `USAGE(` appears **zero** times in
  every gate log on that machine.
- ⛔ **It is COMPOSED with the branches that were already there, not inserted in front.** A
  hook prints ONE object and each branch returns its own, so going first would have skipped
  `cmd_guards.after_command` (which records the branch `guard_commit_branch` enforces
  against) and `note_skill` (which writes the marker `require_skills` refuses dispatches on).
- ⚠ **Once per level per AGENT, keyed by `agent_id`.** A sub-agent's payload carries the
  parent's `session_id` - and so does its `transcript_path`, so neither tells them apart.
  ⭐ The harness supplies `agent_id` for exactly this purpose and says so.
- ⭐ **A resume is armed even with no dispatch: the gate writes its own handoff** into
  `<state>/handoffs/<session>/`. ⛔ **Into the plugin's state directory, never the owner's
  repository** - `repo_root()` follows the shell's `cd` in a marker-less tree, so "one file"
  would have been N files in N directories, none pruned. ⚠ It carries a banner saying no
  agent wrote it, and that banner is load-bearing: measured, a 390-byte stub passes every
  mechanical check, so **nothing else distinguishes a stub from a real handoff**.
- ⛔ **Round 3's blocker: `os.chdir` could lose the whole resume, silently.** It sits at
  `resume.py:610` and every failure handler is at `:687`-`:697`, so a target that no longer
  exists raised `FileNotFoundError` straight past them - no `resume_failed.json`, no retry,
  no cancellation, and the one mechanism whose purpose is to say "it failed at 03:40" never
  ran. ⇒ Guarded, falling back in order to the session's cwd, the task folder, and the
  handoff's own directory, logging which it used.
- ⭐ **`--arm` records the SessionStart cwd, not the one at STOP.** The payload's cwd follows
  the Bash tool's `cd`; the wrong one wakes the work in the wrong tree, silently.
  ⭐ `<sdir>/state/<sid>.start` already existed and is already pruned, and nothing had ever
  read its content.
- ⭐ **The arming trigger is one function, `arm_trigger()`** - so the next judgement (the
  NO-DATA problem) changes one place and nothing else.
- ⚠ **Honest gaps, written into PROTOCOL.md**: `PostToolUse` does not fire for a FAILED tool
  call, which is why the note is on `PreToolUse`; and nothing prunes `<state>/handoffs/`.

---

## 0.55.0

- ⭐ **One space after the verdict icon; the timestamp side stays flush.** An emoji occupies
  TWO cells and the terminal draws it into the second, so `16:31:41🟢5h` put the glyph over
  the `5`. ⚠ A space *before* it would undo what the flush icon was for; a space after costs
  one column and fixes the collision.
- ⛔ **`_bar_col()` counted CHARACTERS, not columns**, so a head carrying the icon reported a
  position one to the left of where the eye sees the bar - while `_second_row_indent()`
  compares it against `_visible_len()`, which counts columns. ⇒ They disagreed by exactly the
  icon's extra cell, and the alignment check said "not aligned" about a row that was.
- ⭐ **The word `SLEEP` becomes 💤**, the same width as the verdict dots. ⭐ That REMOVES a
  special case rather than adding one: a word needed a space on each side to stay readable; a
  two-cell glyph sits exactly where every verdict icon sits.
  ⚠ The font worry was real and is settled by MEASUREMENT. This repository had recorded that
  an emoji can simply fail to draw - `7️⃣` rendered as nothing and `🔥` as a coloured blob -
  which is why the verdict states are geometric. ⇒ The owner printed 🟢 ⚪ ⚫ 💤 🌙 side by
  side in the terminal that has to draw them and all five rendered. That test beats the
  inference; ⚫ stays the geometric fallback.
- ⭐ **New `usage.level()`: the verdict WORD only, and cheap.** Measured on one machine:
  `verdict()` **28.99 ms** against `level()` **0.471 ms** - **62x cheaper**, same word.
  ⛔ It is a PARAMETER, not a second implementation: the thresholds, the reset arithmetic and
  the seven-day rule are subtle enough that two copies would be two chances to disagree.
  ⚠ The first attempt gated the whole block and so skipped the threshold computation too,
  which made it return GO for every input. Only the two expensive calls are skipped, and
  **both together**, because both re-parse the history through `_burn_rate`.

---

## 0.54.1

- ⛔ **`resume.py`'s log landed where nobody could find it.** 0.52.1 gave the gate's logger a
  second, unmovable destination and missed resume.py's own - which writes to `os.getcwd()`,
  meaning wherever the scheduler happened to start it. ⇒ Every `ARMED` and `RESUME` line went
  somewhere the rest of the record is not. Found by review.
- ⛔ **And it wrote to the FIRST destination that worked, not to both.** The loop returned on
  success, so the second destination was a fallback rather than a copy - ⚠ and the docstring
  said "and to a fallback" while the tuple held one element, so there was no fallback either.
  **A copy that only appears when the other fails is not an audit trail.**
- ⚠ **The check's own failure message was fixed too.** The first version opened the file
  directly, so the mutation it caught produced a `FileNotFoundError` traceback rather than a
  sentence - and grepping for `AssertionError` missed it, which is exactly how a caught
  mutation gets recorded as an uncaught one. ⭐ A check whose failure has to be decoded is a
  check somebody misreads.

---

## 0.54.0

Three measurement defects, all found by the owner watching the row, and all the same
mistake: **"I cannot tell" and "I measured zero" were the same answer.**

- ⛔ **The burn gauge went blind during a quiet stretch - exactly when it had something to
  say.** `_burn_rate()` ended with `if rate <= 0: return None`. Measured 2026-09-01 12:48:
  the baseline row (12:37, 32%) was right there, the live value was 32%, the delta was 0 ⇒
  "unknowable" ⇒ dashes. ⭐ **Zero is a measurement, not an absence.** Only a FALLING
  percentage returns `None` now - that is genuinely unknowable (a window turned over inside
  the baseline, or a stale reading compared against a live one). A quiet stretch draws a
  **full bar and `.00%`**, and a full bar already means "the window resets before you run
  dry".
- ⚠ **`burn_triple()` and `_burn_part()` each collapsed 0 and None back together** (`if rate
  else 0`, `if rate:`). ⇒ Both now test `is not None`, or the distinction would be undone one
  function away from where it was made.
- ⭐ **History gains a heartbeat row.** A row used to be written only when a number MOVED, so
  a quiet stretch wrote nothing - and a gap has two causes the timestamps cannot tell apart:
  nothing was spent, or **nothing was watching** (machine off, client closed). The quota is
  account-wide, so another seat may have spent through the gap. ⛔ That case **under-states**
  the rate, which is the dangerous direction. ⇒ A row at least every `burn_window_min`, so a
  gap becomes evidence recorded by the passage of time rather than by an event somebody had
  to catch. ⚠ Bounded: at worst one row per ten minutes, and `history_keep_days` already
  prunes whole files. ⭐ This fix was argued for **by the code's own comment before it
  existed**, which ended "Not built".
- ⛔ **A freshly reset window turned yellow.** The WARN tier was `pct > time_pct` with no
  deadband - and just after a reset `time_pct` is near zero, so the **first percent spent**
  turns the bar and the dot yellow. Measured minutes after the seven-day reset: 1% against
  0.48%, and a seven-day clock advances 0.0099%/min, so one percent stays yellow for about a
  hundred minutes. ⇒ New `colour_warn_margin_pct`, default **5** points. ⚠ Points rather than
  a ratio, because a ratio against a near-zero baseline is what broke. The two tiers above it
  catch a window that is simply high; this one exists only for the early and middle stretch.
- ⭐ All three mutation-checked, each with its own failure message: `AssertionError(None)`,
  `the heartbeat is not firing`, `4 points ahead is inside the deadband`.

---

## 0.53.2

- ⛔ **The bare-filename rule produced a false alarm, on the owner's screen.** A review
  prompt contained the sentence "write a `HANDOFF.md` into the owner's repository, unasked" -
  prose **about** creating a file, not an instruction to create one - and the guard warned
  that the sub-agent had lost its report. ⚠ A false alarm spends the only budget this guard
  has: trust.
- ⭐ **The fix is an exclusion list, not deleting the rule, and that is measured:** across
  this repository's own work orders the bare-filename branch finds **five genuine reports**
  (`agent-01-implement.md` and friends) against this one false positive. Deleting it would
  trade five for one.
- ⚠ **The exclusion applies only to the BARE-filename branch.** `Create
  Memory/tasks/x/HANDOFF.md` names a path and is a real instruction, so it still counts; a
  bare `HANDOFF.md` in a sentence has nothing to disambiguate it. The list is `HANDOFF.md`,
  `PROTOCOL.md`, `README.md`, `CHANGELOG.md`, `CLAUDE.md`, `AGENTS.md` - documents this
  repository talks about constantly, and never a per-sub-task report.

---

## 0.53.1

- ⛔ **A regression from 0.52.1, found by the owner: the checks wrote into the REAL state
  directory.** Since 0.52.1 the gate log also goes to `usage.state_dir()`, and
  `dispatch_gate.py --selftest` runs the real decision paths - so **every suite run filed 45
  `DENY(ultracode)` lines into the owner's own log**. The owner asked "but this session does
  not have ultracode on?" and was right: those lines were never theirs.
- ⚠ **A check that pollutes the evidence it exists to protect is worse than no check.**
  `--selftest` now redirects the state directory to a quarantined temporary one.
- ⛔ **The redirection goes at the ENTRY POINT, not inside `selftest()`**, and that is
  measured rather than assumed: half of that function runs **after** its own `try/finally` -
  including the ultracode block that produced the lines. A redirection scoped to the `try`
  would have missed exactly them.
- ⭐ The new check resolves the real state directory in a SUBPROCESS, because `load_gate()`
  replaces `usage.state_dir` on the imported module - which is what every other case needs,
  and what would have hidden this. Mutation-checked: remove the quarantine and it fails with
  "a shipped --selftest wrote into the REAL state directory: 108 bytes".

---

## 0.53.0

- ⛔ **The most confidently wrong sentence this plugin printed is gone**: `7d 89% but it
  resets before this 5h window ends - IGNORE, not a constraint`. It told the owner to ignore
  the only window that could stop the work.
- ⚠ **That rule asked the wrong question.** It asked whether the window would still be there;
  ⭐ the question is whether its **headroom** would last. Measured 2026-09-01 on the owner's
  own account: 7d at **89%**, 11% left, **71 minutes** to its reset, burning 0.30%/min - so
  the headroom was gone in **37** minutes.
- ⛔ **And the old rule was a cruder copy of something that already existed.** "This number
  is about to be wiped, so forgive it" is exactly `_soften_near_reset()`, which weighs the
  same idea per window and by how close the reset really is. ⇒ Deleted rather than repaired:
  the window binds whenever it has not turned over, the thresholds decide whether it is high
  enough to matter, and softening decides whether an imminent reset forgives it.
- ⭐ **The resume's target is fixed with it, and that half can be measured in minutes:** with
  5h at 0%, 7d at 99% and the 7d resetting in thirty minutes, the old behaviour armed the
  resume for the five-hour reset **two hours** out - **90 minutes** after the thing actually
  blocking the work had cleared. It now waits for the 7d reset.
- ⚠ **The residual edge, stated rather than hidden:** softening is a threshold on TIME
  (`near_reset_min`, 20) and not arithmetic, so a window inside that window which would still
  be exhausted first is softened by one level. ⭐ The old rule erred by ignoring the window
  entirely; this one errs by one level.
- ⚠ **Nothing in the five-hour window's own arithmetic changed.** The owner proposed that 5h
  should adopt the 7d's reset time, then withdrew it on their own reasoning - and the data
  agrees: across **six** measured 5h resets the 7d never moved, so the two windows are
  independent and 5h's projection and marker must use 5h's own reset.

---

## 0.52.1

- ⛔ **The gate log is written twice now, and the second copy is the one to read.**
  `repo_root()` walks up from the payload's `cwd` for `CLAUDE.md`, `AGENTS.md` or `.git`; a
  project carrying none of the three falls through to the cwd itself - which the Bash tool's
  `cd` moves between calls. ⚠ Measured 2026-09-01: one session's log arrived as **four
  fragments in four directories**, each with a stray `.claude/` beside it, and the hour that
  mattered looked empty in the one place anybody would look.
  ⇒ Every line also goes to `<state>/dispatch_gate.log`, which never moves.
- ⭐ **This is the precondition for everything that comes next.** Without one log that cannot
  move, "the guard never fired" and "the guard fired somewhere else" are the same picture -
  and that is precisely the failure this plugin exists to prevent.
- ⚠ The two destinations are independent: one failing does not silence the other. ⭐ The
  per-repository copy stays, because it is where a person looks first.
- ⚠ `usage.state_dir()` can return nothing, and `os.path.join(None, ...)` raises TypeError
  from inside the logger - which would take out the one call every failure path in this
  module relies on. Guarded; the module's own `--selftest` reached that state.
- ⭐ Mutation-checked: drop the state destination and the check fails with "the state copy
  missed the line". It also asserts that a **moved root** does not cost the fixed copy.

---

## 0.52.0

- ⭐ **Five changes to the row, all owner-specified (2026-09-01):**
  1. **The verdict icon moves between the timestamp and `5h`, flush, with no space on either
     side**, replacing the two spaces that used to separate them. ⚠ But **while idle that
     position carries the WORD `SLEEP`, not a glyph** - `07:26:12SLEEP5h` is unreadable, so a
     word keeps one space either side. The instruction did not cover that case and following
     it literally would have broken the idle row.
  2. **Each window's reset time now sits in brackets after its own remaining time**:
     `21% 4h11m(16:29)`. ⚠ There used to be one time at the end of the whole row - two
     remaining times and one clock time, with nothing saying which window it belonged to.
  3. **The seven-day window carries a weekday only when it does not reset today**: `(13:29)`
     today, `(Wed 14:11)` tomorrow. ⚠ The five-hour window never carries one - it cannot
     reach tomorrow.
  4. **The burn rate drops its `/m`** and reads `.30%`. ⚠ **The unit is per minute and now
     lives only in the documentation.**
  5. **The two trailing spaces stay.** ⛔ They are not padding - they keep the terminal's
     cursor block off anything worth reading, and the check asserts the bytes.
- ⚠ **One measured aside: the reset times on screen were never wrong.** The owner expected
  the five-hour window to read 1h12m like the seven-day one; the API itself returns two
  different times (5h → 15:59:59, 7d → 12:59:59). ⛔ **The owner's other point stands** -
  the brake does fire at the wrong time - but the fault is the seven-day `IGNORE` rule, not
  the display. That is handled separately.

---

## 0.51.5

- ⭐ **`Ctx` becomes `CT` - two letters - and that ends it.** The owner's decision, and it is
  better than either of the previous two versions: `CT ` occupies three columns before its
  bar, exactly like `5h ` and `7d `, so the segment lands in column 3 **whichever row it is
  on**. ⇒ The space stays, always, with no row count and no arithmetic.
- ⛔ **`_tighten_extras()` and its regex are deleted.** 0.51.4's "give up the space only on a
  second row" logic no longer needs to exist. ⚠ **Four columns cannot be aligned to three** -
  that was the actual problem, and both earlier versions worked around it instead of solving
  it.
- ⚠ **Both failures stay in the record** (0.51.2 padded the first row and the harness trimmed
  it; 0.51.3 dropped the space and the label touched its own bar on one row) and both are
  still asserted in the checks, so neither can come back.
- ⭐ **The statusline and the VS Code watcher task are the same code** (`_line_parts`), so this
  reaches both, and both were measured: the statusline puts both bars in column 3, the
  watcher both in column 13 (its timestamp owns the columns before that).
- ⚠ README follows in both languages - the example rows and the table's column name.
  `longCtxCost` is untouched: that is a harness identifier, not this label.

---

## 0.51.4

- ⭐ **The space after `Ctx` is given up only when there IS a second row.** 0.51.3 removed it
  unconditionally, so on a terminal wide enough for one row it read `Burn ... Ctx░░░░` - the
  label running into its own bar. ⚠ Mid-line that space is doing real work: it is the only
  thing separating the label from the bar. ⇒ Kept on one row, given up on two, because only
  a second row needs that column to buy alignment.
- ⭐ **The test is arithmetic and names no segment**: "is this bar exactly one column right of
  the one above it, and is there a space to give up?" A new second-row segment needs nothing
  added.
- ⚠ **The space is removed at ROW-ASSEMBLY time, not when the segment is built** - the builder
  does not yet know how many rows there will be. And the indent is measured AFTER tightening,
  because it must be computed from the string that will actually be drawn.
- ⚠ **If removing the space does not land the bar in the column above, it is not removed.** A
  segment that gives up its separator for nothing is worse than one that keeps it.
- ⭐ Mutation-checked in both directions: never tighten and the two-row check fails with
  columns 3 and 4; always tighten and the one-row check fails with "the one-row form lost the
  space".

---

## 0.51.3

- ⛔ **0.51.2's fix never reached the screen.** That version padded the first row by one
  column. ⚠ **The plugin really did emit it** - `lead=1` in the installed 0.51.2's own
  output - and **Claude Code trims leading whitespace off a statusline row before drawing
  it**. A measured fix and a working fix are not the same thing.
- ⛔ **No character can stand in, either.** Every Unicode space is category Zs and a
  JavaScript `trim()` removes all of them; a zero-width character occupies no column.
  ⇒ Nothing leading can ever align anything here.
- ⭐ **So the second row is made narrower instead: no space between `Ctx` and its bar.**
  `5h ` puts its bar in column 3, and `Ctx` running straight into its bar lands in column 3
  too - aligned, and with **neither row starting with a space**, so the trim cannot touch it.
- ⚠ **The watcher is unchanged.** Its timestamp already pushes the first row's bar right of
  `Ctx`, so the pad stays on the second row there (measured: both bars in column 13).
- ⛔ **`_second_row_indent` is back to padding only the second row, with the reason the first
  row cannot be padded written into it.** Keeping that branch would be worse than not having
  it: it is silently discarded while reading as though alignment were handled.
- ⭐ The check now asserts both that the two bars share a column and that neither row starts
  with a space. Mutation-checked: put the space back after `Ctx` and it fails with columns
  3 and 4.

---

## 0.51.2

- ⭐ **The second row's `Ctx` bar lines up with the first row's** — done the way the owner
  specified: one space in front of `5h`. ⛔ **Padding can only push RIGHT.** `Ctx ` needs
  four columns before its bar and `5h ` needs three, so padding only the second row can
  never align them - the pad would have to be minus one, and it was clamped to zero.
  Measured in the CLI: the first row's bar sat at column 3 and the second row's at column 4.
  ⇒ Whichever bar sits further left is now the one that moves.
- ⚠ **The first row's pad comes out of its own width budget.** Added after the fit, it would
  make the row one column wider than the terminal - and one column too many wraps, which is
  the single thing this whole area exists to prevent.
- ⚠ **A one-row line never gains that space** - it has nothing to line up with - and the
  watcher is unchanged: its timestamp already pushes the first row's bar right of `Ctx`, so
  the pad stays on the second row there.
- ⛔ **A real trap fixed on the way past: `selftest()` had two locals named `_rows`**, which
  shadowed the module function of the same name for the whole function - so the new check's
  call raised `TypeError: 'list' object is not callable`. Renamed.

---

## 0.51.1

- ⛔ **A YAML block-list `tools:` produced a WRONG ANSWER, not silence.** `tools:` in
  `.claude/agents/<name>.md` has two legal spellings. The inline `tools: Read, Write` was
  always read correctly; the block list - `tools:` then indented `- Write` lines - was not:
  the old pattern skipped the newline and captured only `- Read`, so an agent **holding
  Write** was reported unable to write, warning about a perfectly good dispatch. ⚠ Silence
  would have been acceptable here; a wrong answer is not. Measured: `tools:` gave `'- read'`
  and `False`; it now gives `'read, write'` and `True`.
- ⚠ **A bare `tools:` with nothing under it returns `None` (silent), not an empty string.**
  An empty string reads as a tool list containing nothing - so, cannot write, so warn - but
  it declares nothing at all, which is unknown.

---

## 0.51.0

- ⭐ **0.49.0's written rule is a hook now.** New switch `guard_agent_report_file` (default
  on), two halves, ⛔ **neither of which ever refuses**:
  - **`PostToolUse` — the load-bearing half.** The files a prompt tells its sub-agent to
    CREATE are resolved before the dispatch and stashed in its slot, then `stat`ed when the
    agent returns. A missing one produces a note to the model and a line on the screen.
    ⭐ It needs no knowledge of any agent's tool list, so it cannot go stale — and it catches
    what the `PreToolUse` half never can: an agent that **could** write and simply did not.
  - **`PreToolUse` — a cheap early warning** when a read-only `subagent_type` is paired with
    a prompt telling it to create a file. ⭐ **An unknown type says nothing at all**: silence
    is the right answer for a type nobody here has seen, and a guess is not.
- ⛔ **Read-only types are matched by NAME, not by a rule derived from tool lists, and that is
  the load-bearing choice.** `Explore` is declared as "all tools except Agent, Artifact,
  ExitPlanMode, Edit, Write, NotebookEdit" — which leaves it holding **`Bash`**. A tool-list
  rule would therefore call Explore able to write and would have **missed the exact incident
  this guard exists for**. The type is read-only by *instruction*, and an instruction is not
  visible in a tool list. ⚠ `codex:codex-rescue` holds only `Bash` and is deliberately absent
  from the table: it writes through the shell, so flagging it would be a false alarm.
- ⚠ **`Edit` does not count as being able to create a file.** Edit changes a file that already
  exists; "create `<path>` as your FIRST action" is precisely the instruction it cannot obey.
  That is why `statusline-setup` (Read, Edit) is in the read-only snapshot.
- ⭐ **A project's `.claude/agents/<name>.md` `tools:` line beats the built-in snapshot**,
  because it is the live truth for that name in that repository and the snapshot is a guess
  from another day.
- ⛔ **The first version's prompt-reading could not see its own incident — the adversarial
  review knocked it down with its own example.** It scanned line by line, and that incident's
  work order writes `**Your FIRST action:** create` on one line with the path on the NEXT.
  Measured against this repository's 18 real work orders, the old rule saw **two**. ⇒ The
  verb now carries forward 200 characters **across a line break**, stopping at the end of the
  sentence or after one line break, whichever comes first — and that stop is what keeps the
  extra reach from becoming a false-alarm machine. A bare filename (`Create agent-01-implement.md`) resolves against the dispatch's own task folder.
  ⭐ **Re-measured: 19 paths, every one a genuine report file, no false positives**, and 17
  of the 18 work orders are now seen.
- ⚠ **Verbs are matched as WHOLE WORDS.** The stems `creat`/`writ`/`append` also fire inside
  `creative`, `rewritten` and `appendix`, and then name whatever `.md` the sentence happened
  to mention as the agent's lost report.
- ⚠ **Two more wrong paths, both measured:** work orders elide a long prefix as
  `.../Memory/tasks/...`, and joining that onto the repository root produced a path that can
  never exist — so a report that WAS written read as missing; and a bare `.md` with no stem
  produced `<task folder>\.md`, which can never exist either. Both fixed, each with its own
  check.
- ⭐ **Silence is asserted, not assumed.** Four no-alarm cases: a read-only type asked only to
  READ, a Bash-only type, an unknown type, and a path outside the task root. ⚠ A guard that
  fires on everything is a guard nobody reads. Both halves are mutation-checked — drop the
  `os.path.exists` test and the "file present stays silent" case fails; drop the `PreToolUse`
  condition and the Explore case fails.

---

## 0.50.0

- ⛔ **The `fetch_seconds` floor is back to 120 — the experiment is over.** 0.44.0 lowered it
  to 60 to measure the cited "~5 requests per token" figure. ⭐ **It ended the way its own
  stop rule said it must:** measured 2026-08-31 at `fetch_seconds` 60, owner-reported — three
  HTTP 429s in ten minutes (08:42:59, 08:47:30, 08:52:01). ⇒ The floor is 120 again, anything
  smaller in a config is clamped **up** to 120, and the clamp says so on stderr.
- ⭐ **The two measurements together are the answer; either one alone misleads.** At 120 s: at
  least 26 successful calls in 100 minutes, no 429 anywhere. At 60 s: a 429 within minutes.
  ⇒ The "five calls" figure really is out by roughly an order of magnitude, but the limit is
  **not absent** — it sits between those two intervals and is still unknown. ⛔ Do not read
  the 26 successful calls as permission to go faster; that is the reading this run refuted.
- ⚠ **The self-check now asserts 120 as a LITERAL, not as `FETCH_FLOOR_SECONDS`.** With the
  constant on both sides the check agrees with whatever floor somebody types in — including
  the 60 that drew the 429s — so it would have stayed green straight through the regression it
  exists to catch. New cases: 30, 60 and 119 must all become 120, and 120 passes through.
- ⭐ The clamp is **mutation-checked**: delete the assignment and the check fails with
  `AssertionError((30, 30))`. ⚠ The stderr warning still prints during that mutation — so
  seeing the warning is not evidence; the assertion is.

---

## 0.49.0

- ⛔ **Every prompt gains a fourth rule: state the `subagent_type`, and the capability that
  prompt needs from it.** Measured 2026-08-31: a round-2 ADR review was dispatched as
  `Explore`, a read-only type. It could not create the report its own first line demanded, so
  it returned the whole review as its final message — and **its verification table and five
  of its findings were permanently lost**, because they sat in an intermediate turn the
  dispatcher never received.
- ⭐ **The write-as-you-go rule is void from the first action for an agent that cannot write**,
  and the failure is **silent** from the dispatcher's side: the summary still arrives and
  still looks normal. ⇒ That dispatch named the model and never the type, so the mismatch had
  nowhere to become visible. The words "needs Write" cannot be written without first reading
  that type's tool list.
- ⭐ **`ls` the file the prompt named when the agent returns** — this is the step that actually
  holds. The failing agent *did* say in its first line that it could not write, and it was
  still missed, because the summary looked normal. A file's absence does not.
- ⚠ **No list of read-only types is written into the skill** — the same reason the prices are
  not. Agent types are user- and plugin-defined (`.claude/agents/*.md`, SDK `agents`), so a
  snapshot shipped in a skill rots and then lies.
- ⛔ **This release is a written rule, not a hook.** The gate reads neither `subagent_type` nor
  whether the demanded file appeared, and PROTOCOL.md's "NOT enforced" table now says so.

---

## 0.48.0

- ⭐ **The end of the watcher row is rearranged as the owner specified:** **one** space before
  the dot (it was two), then a space and the **seven-day reset time**, then **two** spaces.

  ```
  ... Burn ▓▓▓▓▓▓▓░░░ .55%/m 2h16m 🟢 Tue 13:00␣␣
  ```
- ⭐ **No field name on the time.** A reader learns once that `Tue 13:00` is the weekly reset,
  and a `7d ` label would cost three columns on a row that drops parts from the right.
- ⛔ **The two trailing spaces are not padding - do not tidy them away.** The terminal parks
  its cursor on the last column and draws a block there; over the dot or over the time that
  block is unreadable. ⇒ The check asserts the BYTES rather than the intent, because a
  trailing-whitespace cleanup would break the display and nothing else would say so.
- ⚠ **No seven-day window means no time, never the word `None` on screen** - and the two
  trailing spaces survive, because what they protect is the cursor, not the time.
- ⚠ The time is uncoloured and sits outside the colour reset on purpose: it is a fact, not a
  state, and colouring it would make it argue with the dot beside it. ⭐ `%a` runs in the C
  locale here (Python does not call setlocale at startup), so it reads `Tue` rather than a
  localised weekday - measured, not assumed.

---

## 0.47.0

- ⛔ **The watcher no longer reads "our hooks are dead" as "you went home".** Measured
  2026-08-30: `.alive` frozen at 1225 minutes on a machine in continuous use, the watcher
  asleep for 20 hours, and `install.py --status` printing `OVERALL : everything is live`
  throughout. The cause was `installed_plugins.json` pointing at a deleted install directory,
  so `${CLAUDE_PLUGIN_ROOT}` expanded to nothing and every hook silently failed to fire.
- ⭐ **"Is anybody working?" now reads two sources, whichever is newer**: the gate's own
  `state/*.alive`, and the mtime of `~/.claude.json`, which Claude Code writes whether or not
  any hook of ours is wired. ⭐ **The recorder happened to capture the failure itself**: across
  the 22 minutes before the hooks were repaired — `.alive` over 1000 minutes old, so provably
  dead — `~/.claude.json` was written nine times and never got older than **3.71 minutes**.
- ⭐ **When the two disagree, `HOOK?` appears beside the clock.** ⛔ In `head`, not beside the
  verdict dot, and that was measured: `_cut()` trims from the right and the dot is the
  rightmost thing on the line — at 25 and 30 columns it is DROPPED and the row comes back
  shorter than the terminal with nothing saying anything was suppressed. Anything in `head`
  survives every width.
- ⛔ **`resume.py` is fixed too, and its failure direction is the opposite and worse.** When
  the signal dies the watcher merely goes quiet; the scheduled resume decides nobody is
  present and **runs the work anyway**, underneath somebody who is typing. Wired only into the
  stand-down call site (which passes no `session_id`), and it can **only ever make the resume
  MORE likely to stand down, never less**.
- ⛔ **Two candidate signals rejected, both for reasons only measurement could give:**
  - `projects/*/*.jsonl` (the transcript) is written at TURN boundaries, so a twenty-minute
    turn writes nothing for twenty minutes against an `idle_after_min` of 15 — the same defect
    in a new coat.
  - `~/.claude/backups` is a **rotating, pruned ring of five files**: the newest survivor can
    itself be old, so its age is not the age of the last write. A signal whose meaning changes
    when a cleaner runs is not a signal.
- ⭐ **`$CLAUDE_USER_CONFIG` and `$CLAUDE_CONFIG_DIR` point the second source elsewhere.**
  ⛔ An environment variable rather than a constant is not a preference: `test_usage_watch.py`
  starts the watcher through `subprocess.Popen`, where a monkeypatched module constant does
  not cross the process boundary. **Measured** before the seam existed: against an empty
  temporary state directory `last_heartbeat_min()` returned 0.68 minutes — the age of the real
  `~/.claude.json` — so **no fixture could express "an idle machine"** and four assertions
  became unwritable or passed through the wrong branch.
- ⭐ New check `case_dead_gate_beside_live_person`, in which the two sources **disagree**, so
  only the new one can produce the result. ⚠ The existing control `case_active_keeps_drawing`
  ages both sources to zero and therefore cannot tell which kept the watcher awake — measured,
  it passed against a build whose second source did nothing at all. ⭐ The new check
  immediately caught a real display defect of its own: the `DRAW` pattern anchored on the
  clock, so a row carrying `HOOK?` counted as **no draw at all** and reported "drew 0 times".
- ⭐ Three adversarial review rounds, all REJECT, seven blocking findings all fixed.
  `Tools/Debug/test_all.py` 11/11; six mutations, all killed. ADR and all three reports in
  `Memory/tasks/20260830-163713-heartbeat-second-signal/`.

---

## 0.46.0

- ⭐ **The Burn gauge's CELLS and its COLOUR are now two independent signals.** Both used to
  be computed from the same `ratio` — two visual channels carrying one number, one of them
  wasted, and it produced the unreadable "full bar, yellow" combination.
  - **Cells** (unchanged): will the budget outlast this reset?
  - **Colour** (new): how fast am I burning, as a multiple of **clock speed** (100 ÷ window
    minutes = 0.333 %/min, the pace that finishes the window exactly as it resets).
- ⭐ **The default bands 1.00× / 1.75× / 2.25× were FITTED, not picked.** The owner asked for
  red 10% / orange 15% / yellow 25% / green 50% of the time and for the multiples that produce
  it. Measured over real history (two five-hour windows, 298 minutes with a rate) they give
  **49 / 29 / 14 / 7**, and they are the best set a quarter-multiple search finds.
- ⭐ **All three edges are configurable**: `burn_x_yellow` / `burn_x_orange` / `burn_x_red`.
  ⛔ Three separate scalars rather than one list, and that is forced by existing code:
  `config()` copies a value from disk only when it is an `int` or `float`, so a list under a
  known key would be **silently ignored** and the reader would get the defaults while
  believing otherwise. ⚠ They must ascend; a set that does not prints a line and **all three**
  fall back — a half-honoured set is a calibration nobody chose.
- ⛔ **Zero cells is forced to red whatever the rate says.** Zero cells is `ratio < 0.05`:
  measured at remain=119 min it covers burnout 0-5 minutes, and returning to a full bar from
  there needs a **24× to 119×** slowdown, or is impossible. ⇒ No achievable change of pace
  alters the outcome, so "should I slow down?" has no answer that helps — and in a column
  where empty already means DANGER, an empty bar wearing green says the opposite of the truth.
- ⚠ **The price, accepted explicitly by the owner: a glance at the colour alone no longer
  decides anything.** Full bar + red is "burning hard, but the window just opened — no action
  needed"; short bar + green is "already crawling, and slowing further will not save it".
- ⛔ **The bands are coupled to `burn_window_min`.** Measured: at 15 and above red **never**
  fires; at 5, 15-16% of the time has no rate at all. Hence 10. Change that dial and
  `install.py --status` tells you what it cost.
- ⭐ New `Tools/Debug/burn_band_fit.py` reads the **configured** edges and reports their
  achieved shares against your own history, with a verdict. ⚠ It ships here rather than in the
  task folder because the ADR's reconsideration criterion needs a command that can actually be
  run — a task folder is archived as a unit.
- ⭐ Two adversarial review rounds, both REJECT, five blocking findings all fixed: an empty bar
  painted green, a false "no new wiring" claim, F5's false "only 10 produces all four colours"
  (5 does too), B1's reason being untrue for five of six states, and the omitted release
  mechanics. ADR and both reports in `Memory/tasks/20260829-133237-burn-two-signals/`.
- ⭐ Seven mutations, all killed, control passing. ⚠ The four old assertions were **rewritten,
  not deleted** — measured, only the FIRST of them fails after the split; the other three go on
  **passing for a new reason**, so the suite would have gone green while guarding nothing.
  `Tools/Debug/test_all.py` 11/11.

---

## 0.45.0

- ⭐ **A WARN state, and it is colour only.** The dot and the bar turn yellow as soon as the
  five-hour bar's fill passes **its own ┃** — you are spending faster than the clock.
  🟢 GO, 🟡 WARN, 🟠 PACE, 🔴 STOP, ⚪ no data yet.
  ```
  13:20:00  5h ▓▓▓▓▓┃░░░░ 51% 2h29m 7d ▓▓▓▓░┃░░░░ 40% 2d23h Burn ────────── --  🟡
  ```
- ⛔ **WARN never reaches `verdict()`, deliberately.** `dispatch_gate.py` tests the verdict
  word against literal tuples in **four** places (`not in ("GO", "PACE")`, `not in ("PACE",
  "STOP")`), so a fifth word would **silently change what the brake does**. The owner's
  instruction was 只變色不做任何處理 — colour only, no handling — so WARN is derived at the
  display layer by `_state()` / `display_state()`, the same route `SLEEP` already takes.
  ⚠ It can only turn a green dot yellow; it never softens a real PACE or STOP.
- ⭐ **The bars and the dot now share one palette**, so either one answers the same question.
  The two upper tiers still read `colour_warn_pct` / `colour_alarm_pct` (70 / 85 by default,
  matching the verdict); WARN has no threshold key because the ┃ marker IS the condition.
- ⭐ **A zero unit is no longer printed.** `0h32m` is `32m`, `3h0m` is `3h`, `4d0h` is `4d`.
  ⚠ It is always the SMALLER unit that vanishes: dropping the `3h` from `3h0m` would read as
  three minutes.
- ⭐ **The enforced fetch floor drops from 120 s to 60 s; the default is still 120 s.** The
  floor and the default are now different numbers. ⛔ Not a tuning change — it exists so the
  "~5 calls per access token" claim can be MEASURED, having rested entirely on somebody else's
  documentation. Measured 2026-08-29 at a 120 s interval: at least 26 successful calls in 100
  minutes, `fetch.log` never created at all, and no 429 anywhere in the state tree. ⇒ The
  figure is out by roughly an order of magnitude. ⚠ The stop rule sits above
  `FETCH_FLOOR_SECONDS`: a 429 inside the first hour puts it back to 120. The ADR and its
  adversarial review round are in `Memory/tasks/20260829-124223-fetch-floor-60s/`.
- ⭐ **`burn_window_min` default 30 → 10.** Readings arrive in WHOLE percent, so one step over
  a 10-minute baseline is 0.1 %/min against 0.033 at 30 — three times twitchier, and `--` on a
  quiet stretch. ⚠ Safe for one reason only, the same one `_burn_rate()` already states: **no
  burn figure reaches GO/PACE/STOP.**
- ⭐ Six mutations, all killed (the WARN tier in `_state()`, `>` to `>=`, `display_state()`
  overwriting PACE/STOP, the dot coloured by percentage, the `duration()` zero-trim, and
  `verdict()` emitting WARN), with a passing control. ⚠ The dot-colour one **survived the
  first attempt** — the bar beside it happened to be yellow too, so the assertion could not
  tell them apart; it now asserts the escape sits immediately before the icon.
  `Tools/Debug/test_all.py` 11/11.

---

## 0.44.1

- ⛔ **The segment-label icons are withdrawn - they do not draw on the owner's terminal.**
  From the screenshot: the keycap seven rendered as **nothing at all** and the fire came out
  as a coloured dot. ⇒ Two of the four segments lost their label while the width counter went
  on reserving two columns for each. **A glyph a font may not have is not a saving, it is a
  blank.**
  ```
  12:02:02  5h ▓▓▓░░░┃░░░ 34% 1h52m 7d ▓▓▓▓┃▓░░░░ 54% 3d22h Fable ▓▓▓░┃░░░░░ 31% 3d22h Burn ▓▓▓▓▓▓▓▓▓▓ .17%/m 6h36m  🟢
  ```
- ⭐ **Only the verdict dot stays.** Those four are geometric shapes with far wider font
  coverage than an emoji, and the screenshot shows them drawing correctly. PACE keeps 🟠, as
  the owner asked.
- ⭐ **0.44.0 is not withdrawn wholesale.** The one-space separator, the short durations
  (`3d22h`) and the trimmed burn tail (`.17%/m 6h36m`) all stay - those are TEXT, and depend
  on no font having any particular glyph. The row is 119 columns (109 with icons, 141 before).
- ⭐ **`_cols()` stays too.** The dot at the end of the row is itself a two-column character
  and still has to be measured - and it now gets CJK right as well, which this file always
  knew it did not.

---

## 0.44.0

- ⭐ **The whole row is icons now, each one the owner's choice.**
  ```
  11:23:40  🕒▓▓▓░░┃░░░░ 33% 2h6m 7️⃣▓▓▓▓┃▓░░░░ 54% 3d23h 🚀▓▓▓░┃░░░░░ 31% 3d23h 🔥▓▓▓▓▓▓▓▓▓▓ .30%/m 3h43m  🟢
  ```
  🕒 five hours, 7️⃣ seven days, 🚀 the model window, 🔥 the burn rate; the verdict becomes
  🟢 GO, 🟠 PACE, 🔴 STOP, ⚪ no data. The separator goes from two spaces to one, each icon
  sits against its own bar, and the burn tail shrinks to `.30%/m 3h43m` - the leading zero
  dropped only when it IS a zero, since the `1` in `1.20%/m` carries magnitude.
  **The row falls from 141 columns to 109.**
- ⛔ **The verdict icon is display only.** The gate still receives the WORD `GO`/`PACE`/`STOP`;
  a symbol reaching that side would be a value the dispatch logic does not know. The
  substitution happens where the row is assembled and nowhere else - the rule `SLEEP` has
  followed all along.
- ⛔ **The width counter is rewritten, and that is the only dangerous part of this.** It
  counted CODEPOINTS, which is right only while everything is one column wide - `BAR_FULL`'s
  own comment says the blocks were chosen because "CJK would misalign". An emoji is TWO
  columns, and `7️⃣` is three codepoints pretending to be one character (digit + variation
  selector + enclosing keycap). ⇒ `_cols()` now answers three cases: W/F is two, a variation
  selector or combining mark is zero, the keycap mark is one. ⚠ **`_cut()` had to learn
  columns too**, or a 25-column budget produced a 26-column row - measured the moment the
  labels changed. **One column of miscounting wraps the row, and a wrapped row is the one
  thing this watcher cannot repair.**
- ⛔ **And an expiring check is repaired in passing, unrelated to the rest.**
  `test_guards.py` asserted that "a back-dated live table loses to a NEWER seed" - but the
  seed is a file in this repository with a fixed timestamp, so the premise expired 24 hours
  after that capture and the suite then went red on the clock rather than on a defect.
  Measured 2026-08-29: the seed turned 24.09 h old and the suite failed. ⇒ The instant is now
  derived FROM the seed. ⚠ The first attempt moved `now` itself and broke the two assertions
  below it that measure the 24 h interval from it; it is scoped to the one line that needs it.

---

## 0.43.0

- ⛔ **The watcher is back to ONE row, and the terminal decided that.** The owner's last
  screenshot is conclusive: with a full clear before every draw, the VS Code panel **stacked
  three complete two-row draws**, none of them cleared. ⇒ That panel **ignores `\033[2J`
  too**. Against that: before a second row existed, the single line updated in place perfectly.

  | sequence | that panel |
  |---|---|
  | `\r` + `\033[K` | ✅ honoured |
  | `\033[1A`, `\033[H`, `\033[2J` | ⛔ all ignored |

  ⇒ Only the pair that needs no vertical movement works, and that pair rewrites one row.
  **Two rows are not achievable there.**
- ⭐ **The owner chose "one row, with the times shortened so Burn fits".** `duration()` goes
  from `4d-0h-16m` to `4d0h` - past a day the minutes are dropped, because four days out a
  minute is noise and three hours out it is not. The whole line with `Burn` falls from **141
  columns to 129**.
- ⭐ **`_redraw()` now emits `\r` + the row + `\033[K` and nothing else, and asserts on a
  second row** rather than silently drawing half of what it was handed. The byte stream was
  re-captured after the change: no newline and no `\033[` movement anywhere in it.
- ⚠ **`Burn` is still dropped on a panel narrower than 129 columns** - one row means whatever
  does not fit goes from the right.
- ⛔ **And a defect of my own making is repaired: this file held 22 real ESC control bytes.**
  Earlier edits wrote the byte itself where the text meant the four characters `\033`, so
  the CHANGELOG became a file with control characters in it, looking on screen merely like a
  few missing letters. ⚠ Exactly what the rule about reading back the artefact that is
  actually consumed exists to catch.

---

## 0.42.1

- ⛔ **`\033[H` was not enough either, and this time the bytes were CAPTURED to find out.**
  The owner confirmed `0.42.0` was running (PID 31008) and the panel still stranded a row.
  ⇒ Every byte the watcher writes to stdout was recorded:
  ```
  <ESC>[2J<ESC>[H<ESC>[?7l                              opening
  <ESC>[H<CR>row1<ESC>[K<LF><CR>row2<ESC>[K<ESC>[J      each draw
  ```
  **No stray output, no relative move anywhere, order exactly right.** ⇒ What this process
  sends is correct; where that terminal puts `\033[H` is not what it believes.
- ⭐ **So it stops depending on where home is: the screen is cleared before EVERY draw.** A
  cleared screen holds only what this draw put there, so there is nothing left to strand,
  whatever the terminal thinks. ⚠ It costs a full repaint every `--every` seconds - two rows
  on a thirty-second interval, which nobody can see. A watcher redrawing many rows at speed
  would need the careful version back.
- ⚠ **Why that terminal does not treat `\033[H` as row 1 is still unknown.** This release does
  not answer that question; it makes the answer stop mattering - which after four guesses is
  worth more than a fifth. Mutation-checked: drop the per-draw clear and
  `AssertionError('\033[H
a<K>')` fires.

---

## 0.42.0

- ⛔ **No more climbing. Fourth attempt, and the first one made from evidence.** The owner's
  screenshot beside the process list: the running copy is `0.41.5` (PID 3224, started
  `11:01:18`) and the stranded row **is `11:01:18`** — the FIRST draw. Every later redraw is
  clean. ⇒ The cursor was already a row lower than the arithmetic believed before the second
  draw ever ran, and **fixing the arithmetic can never reach that**.
- ⭐ **Absolute positioning instead: `\033[H` and redraw the whole screen, every time.**
  `\033[1A` means "up one row from WHEREVER THE CURSOR IS", which is correct only while
  nothing else has moved it - and inside a VS Code panel that is not this process's to control
  (the `⊙` at the left of the owner's screenshot is the terminal's own decoration). `\033[H`
  is row 1 column 1 of the screen, not a displacement, so it does not matter what moved the
  cursor, how wide the rows were, or how many were drawn last time.
- ⭐ **It is legitimate only because the watcher cleared the screen at startup and owns it.**
  A program sharing a terminal must never do this, and the function says so.
- ⭐ **`\033[J` at the end makes shrinking safe without counting.** It erases from the cursor
  to the bottom of the screen; the old code padded with blank rows, and the padding had to
  know the previous height.
- ⛔ **`_rewrite()` is deleted outright**, along with the `rows` counter it needed. Leaving an
  uncalled relative move in the file is how it comes back. Mutation-checked: put `\033[1A`
  back and `AssertionError('\033[1A
a<K>')` fires.
- ⚠ **The three earlier fixes stay, and none was wasted** — the startup clear (0.41.3), the
  fixed row count (0.41.4) and wrapping off (0.41.5) each remove a real way to strand a row.
  None of them was the owner's.

---

## 0.41.5

- ⛔ **The residue survived the clear (0.41.3) and the fixed row count (0.41.4). Third cause:
  the terminal's own line wrapping.** A row as wide as the panel - or wider - is wrapped by the
  TERMINAL onto two visual rows, and `\033[1A` then climbs one VISUAL row rather than one
  logical one: `
` returns to the start of the wrong row and the top half stays on screen for
  ever. ⭐ This is the original defect the comment at the head of `_watch_line()` describes; it
  simply assumed fitting the row was enough to prevent it.
- ⭐ **The fix: turn the terminal's auto-wrap off (DECAWM `?7l`) while rewriting.** With it off
  an over-long row is truncated by the TERMINAL at the margin and the cursor stays on the row it
  was on - so the climb cannot be wrong however the width measurement turned out.
  ⚠ **Measuring the width can never fix this**: the width can be stale (a resize between
  measuring and writing) or unknowable (`COLUMNS` unset and no tty size). Turning wrapping off
  removes the class instead of guessing better.
- ⛔ **Handed back on exit (`?7h`).** Auto-wrap is the TERMINAL's mode, not this process's; left
  off, the next thing to run there loses its own wrapping. Registered with `atexit`, so a clean
  return, a Ctrl-C and an unhandled error all restore it.
- ⚠ **This is the third attempt at one symptom, and the cause is NOT proved** - the panel's
  width cannot be measured from here. ⭐ A five-second check that settles it: **before updating,
  drag the panel much wider.** If the residue stops, it was wrapping. If it does not, there is a
  fourth cause and this change was wasted.

---

## 0.41.4

- ⛔ **The real cause of the stranded line: the watcher's ROW COUNT changed.** 0.41.3 cleared
  the terminal and the owner's second screenshot still showed it - and showed it clearly:
  `10:30:24` drew **one** row (no burn rate yet), `10:30:54` drew **two**, and that single
  1-to-2 growth left the older row on screen.
- ⭐ **The cure is to remove the transition, not to get the cursor arithmetic right.** That
  arithmetic was already correct and pinned - but it assumes nothing else moved the cursor in
  between, and inside a VS Code panel that is not something this process controls. ⇒ With no
  rate, the gauge is drawn as `Burn ────────── --`, exactly how the statusline already draws
  "not known yet", so there are **always two rows** and no transition to get wrong.
- ⭐ **A second benefit: the gauge no longer says "no data" by vanishing.** It is either a rate
  or dashes; both are visible.
- ⚠ **An old rule is overturned and its reason is gone.** The check used to say a line that
  fits must stay on one row "or every watcher grows a blank second one". Row two is never
  blank now - it always carries the gauge.
- ⚠ **Row two is gauge first, note second.** The gauge is the segment with a BAR, and the bar
  is what row two is aligned by; a note in front of it would leave the rows looking unrelated
  again. ⇒ Too narrow for both and the note is what goes - the same right-to-left rule every
  other row here follows. Mutation-checked: fall back to the old single-row path when there is
  no burn and the check fails at once.

---

## 0.41.3

- ⭐ **The watcher clears the terminal once at startup, so the previous run's line is not
  stranded above the new one.** From the owner's screenshot: a one-row draw from the old
  version sitting above a two-row draw from the new one, which reads as the two-row layout
  being broken. ⛔ **It is not a rewrite bug** — 1-to-2 growth overwrites row one in place
  (`
a<K>

b<K>`, pinned long before this). The stranded line belonged to a DIFFERENT
  PROCESS: a rewriting watcher can only reach the row it starts on, and that line is above it.
- ⭐ **The clear happens only in rewriting mode.** A surface that overwrites its own row has no
  scrollback worth keeping; anyone who wants the history passes `--scroll`, and that path emits
  nothing at all from here. ⚠ The cost is that it takes the task's `Executing task` header with
  it, which is why it is tied to rewriting rather than done unconditionally.
  Mutation-checked: return an empty string and `AssertionError('')` fires.

---

## 0.41.2

- ⭐ **The two rows' bars now sit in one column.** The owner asked for the charts to line up.
  The second row used to be indented by the TIMESTAMP's width, which aligns nothing: `5h` is
  two characters and `Burn` is four, so the bars landed two columns apart and the rows read as
  two unrelated lines. The indent is now MEASURED from the strings (where the first bar glyph
  falls), so a new label needs nothing added here.
- ⭐ **The burn bar is drawn `BAR_WIDTH + 1` wide**, like `Ctx`. The other three carry the `┃`
  marker, which sits between cells and costs them a column; a bar one narrower cannot line up
  beneath them however the row is indented. ⚠ **Column equality does not catch this** — both
  bars start in the same place and end in different ones — so it is pinned separately. Both
  mutation-checked: indent back to the timestamp → `not in one column: 13 vs 15`; width back to
  `BAR_WIDTH` → `AssertionError((9, 'Burn ...'))`.
- ⛔ **A claim from 0.41.0 is withdrawn.** Its comments, CHANGELOG and README all said the CLI
  statusline gets one row and a second would be thrown away. **That is wrong.** `line_rows()`,
  in the same file, had already measured out of the shipped binary that Claude Code splits the
  command's output on newlines and counts them — a statusline MAY be two rows. The real reason
  the statusline does not split is the owner's instruction to leave the CLI side alone. Fixed
  in all three places.

---

## 0.41.1

- ⛔ **`--status` can now say "your watcher is running an older copy".** The owner updated the
  plugin and the display kept drawing the previous version's line. Cause: `claude plugin update`
  **leaves the old directory in place**, and the shim records an exact path and only falls back
  to the newest copy when the recorded one is GONE — so it never falls back.
  ⚠ **Every check was green while that was true**: the task is current (its command carries no
  version), the statusline is current, the recorded path exists. The question nobody asked is
  whether it is the NEWEST one.
- ⭐ **The repair is a NEW Claude session** — not a VS Code restart and not a reinstall. The gate
  repoints the shim at session start. ⚠ Then restart the watcher terminal, because a running
  process does not reload its code. Both sentences are printed under the warning: a warning with
  no move to make is not a warning.
- ⭐ **It reports and never repairs.** `--status` is read-only, and fixing something from inside
  it would make the next run disagree with this one for reasons the reader cannot see.
- ⚠ **Running `--status` from a development checkout does not false-alarm** — the comparison is
  against the INSTALLED copy, not the directory this script sits in. That is the same trap the
  VS Code task check already learned. Mutation-checked: make the comparison always equal and
  `an older shim was not reported` fires.

---

## 0.41.0

- ⭐ **`outlasts reset` is replaced by a time, always.** The owner's instruction: the words cost
  columns and made the reader translate a phrase into a number anyway. It now always reads
  `11h-52m left` — when the burn-out lands at the current rate.
  ⚠ **That time can exceed what the window has left, and that is correct**: resets in `4h-24m`,
  burns out in `11h-52m` means you cannot spend it all. "The reset arrives first" is what the
  full bar was already saying; it did not need saying twice.
- ⭐ **The watcher now breaks after the last usage window and gives `Burn` a row of its own.**
  Also the owner's instruction, and it closes the hole measured in 0.40.7: under 141 columns the
  gauge was silently dropped, so "no Burn" meant either "no data" or "your panel is narrow" with
  nothing on screen to tell them apart. With a row of its own it is always there.
  ```
  09:35:01  5h ░┃░░░░░░░░ 5% 4h-24m  7d ▓▓▓▓┃▓░░░░ 51% 4d-1h-24m  Fable ▓▓▓░┃░░░░░ 31% 4d-1h-24m  GO
            Burn ▓▓▓▓▓▓▓▓▓ 0.13%/m · 11h-52m left
  ```
- ⛔ **The CLI statusline is untouched, as the owner specified.** Claude Code renders one row and
  a second would be thrown away. The break is `always_split`, passed by `_watch_line()` and not
  by `_line()` — both sides are pinned by checks.
- ⚠ **Redrawing two rows in place was already supported.** `_rewrite()` climbs by what the
  PREVIOUS draw put on screen, not by what this one will, and that direction was measured and
  pinned long before this. Confirmed by running `--watch --every 3`: two rows update cleanly.
- ⭐ **The split is forced only when there is a Burn segment to move.** Forcing it always would
  push the note and the model onto a second row on a wide terminal, which nobody asked for and
  which the existing checks pin. Mutation-checked: change `always_split=split` to `False` and the
  new check fails, printing the crammed single row it is there to prevent.

---

## 0.40.8

- ⭐ **`outlasts reset` is explained now.** The README printed those words in an example and
  never said what they meant — the owner had to ask, which is the measurement of a hole in the
  documentation. ⇒ It **races two clocks**: "how long until 100% at this rate" against "how long
  until this five-hour window goes back to zero". `outlasts reset` = the reset arrives first and
  you cannot spend it all; `1h-20m left` = burn-out arrives first.
- ⭐ **The bar is that ratio, not a stock.** Which is why it goes back **up** — slow down and it
  grows. Its colour is inverted too: full is green, short is red, the opposite of every other
  segment where a high number is bad.
- ⚠ And `%/m` is spelled out: percent burned per minute over the **last 30 minutes**, not an
  average of the whole window.

---

## 0.40.7

- ⭐ **"The Burn segment is missing" has an answer, and it was measured: the terminal is too
  narrow.** The owner's watcher showed no `Burn` at all. ⛔ The data was fine — at that same
  moment `burn_triple()` returned `(579, 282, 0.167)` and `_line_parts()` did put
  `Burn ▓▓▓▓▓▓▓▓▓ 0.17%/m · outlasts reset` on the first row. Sweeping the width from 100 to
  190: **below 141 columns it is not drawn.** That line is 141 columns with Burn and 100
  without, and VS Code's bottom panel is often 110–130.
- ⚠ **This is deliberate, not a bug.** `Burn` is the last of the four segments and the first
  sacrificed on a narrow terminal — never a usage bar, because the bars are what the brake acts
  on. The selftest already pins that. ⛔ **But nothing says it was dropped**, and "no Burn" has
  two entirely different meanings: `Burn ───────── --` is "no data yet", an absent segment is
  "too narrow". The README now puts the two side by side, because the screen cannot tell them
  apart.
- ⭐ **No code changed.** The layout rule is deliberate and pinned by a test; what was missing
  was a sentence, not a feature.

---

## 0.40.6

- ⭐ **The install section is rewritten as two routes, both steps only.** The owner's
  instruction: lead with one paste that does everything, then the menu route, and explain
  neither — point at the prose below and let whoever wants it go and read it. ⇒ `## Install`
  is now **A. One paste** and **B. Through the menus**, and every long passage that was there
  is kept below, renamed to `## Reference — what each of those steps does`.
- ⭐ **Route A includes `task.allowAutomaticTasks`, and ends on its own check.** From
  `claude plugin marketplace add` through to `install.py --status`: the plugin, the CLI
  statusline, the VS Code task and the automatic-task permission, in one paste.
  ⛔ Its first line is **run it before opening VS Code** — which wins the race 0.40.4 measured.
- ⭐ **Those lines were RUN before being written down**, not copied from the old section:
  `resolved installPath = ...0.40.0` and `OVERALL : everything is live`.
- ⚠ **Route B says plainly that only step 1 has no menu** — the plugin installs from the CLI.
  Saying so beats sending somebody hunting through menus for something that is not there.

---

## 0.40.5

- ⭐ **Snapshots from BOTH machines confirm the race, and clear Settings Sync and workspace
  trust at the same time.** ⛔ What settles it is the identical starting state: before the
  first open, `tasks.json` read `(no such file)` on **both**. ⇒ "the good machine already had
  the file from sync" is false — it did not have it either.

  | | window opened | hook wrote the task file | gap | outcome |
  |---|---|---|---|---|
  | the one that works | `08:59:19` | `08:59:41` | **22 s** | ✅ started (`watch.alive` 08:59:56) |
  | the one that does not | `08:43:20` | `08:43:55` | **35 s** | ⛔ nothing |

  ⇒ Thirteen seconds. Same mechanism, same starting state, only session-start latency differs.
- ⚠ **The "8 seconds versus 35" in the README was an illustration, not a measurement, and is
  replaced by the pair above.** An illustration that reads as a measurement is exactly what
  this repository refuses everywhere else.
- ⛔ **The `.gitignore` snapshot rule was too narrow.** It matched only `vscode-snapshots/`,
  while a second machine's snapshots arrive under a name of their own (`-working`) — the
  first comparison would have committed somebody else's machine. Now
  `Tools/Debug/vscode-snapshots*/`, verified with `git check-ignore -v`.

---

## 0.40.4

- ⛔ **0.40.3 overstated it, and this release refutes it.** It said the open that creates the
  task "can never run it" — **never is wrong.** Probe D: a clean VS Code launched with
  **no** `tasks.json`, the file dropped in only **after** the log printed
  `RunAutomaticTasks: Trying to run tasks.`:
  ```
  08:58:04.671  Trying to run tasks.
  08:58:04.682  taskNames=[]                                   <- nothing found
  08:58:05.444  updated taskNames=["Claude Usage Watcher"]     <- it ran
  ```
  ⇒ Finding no automatic task, VS Code waits a further **10 seconds**, and a file that
  appears inside them **does** run. ⭐ The honest word is **race**, not impossible.
- ⭐ **That also explains why one machine just works after installing and another does not** —
  the only difference is how many seconds after the window the session starts. Measured on
  one: window at `08:43:20`, the hook wrote at `08:43:55` — **35 seconds, losing by 25**.
  A machine that starts its session in eight wins, and reports no problem at all.
- ⭐ **To win it every time, run the install script from a terminal before opening VS Code.**
  With the file already there no race is run. Both the README and `--status` now say this.

---

## 0.40.3

- ⛔ **The actual cause, and it is not what 0.40.2 said.** The owner took three snapshots and
  the difference is one thing: **on the first open `tasks.json` did not exist yet**
  (`(no such file)`); it is there after that open. And between the first and second open
  **that file does not change at all** — the only difference is that it is already there.
  ⇒ The user-level task file is written by a session too, and a session starts *after* the
  window is up, so **the open that creates the task can never run it**. The second works, and
  every project after that works.
- ⚠ **The workspace-trust finding in 0.40.2 is a real mechanism but not this cause.** Those
  three isolated runs were not wrong — an untrusted folder does silently skip the task — it
  simply was not what bit here. Both are kept: `--status` now leads with the common case and
  keeps the trace-log recipe for when it is *not* that.
- ⭐ **The README claim is corrected.** It said the user-level file solved the FIRST open. It
  solves every project from the second one onward; the launch right after installing it
  cannot cover, for exactly the reason the per-project file could not. That is now stated,
  along with the way to cover it: run the install script from a terminal **before** opening
  VS Code.

---

## 0.40.2

- ⭐ **Measured: what blocks the automatic start is WORKSPACE TRUST.** Three isolated runs,
  one variable each, a clean VS Code via `--user-data-dir` and `--log trace` to read its own
  decision:
  | run | trust | extensions | what the log said |
  |---|---|---|---|
  | A | disabled | none | `taskNames=["Claude Usage Watcher"]` — it ran |
  | B | disabled | **the real extension set** | `taskNames=["Claude Usage Watcher"]` — it ran |
  | C | **default (on)** | none | ⛔ **not one `RunAutomaticTasks` line** |
  ⇒ Extensions slowing startup is **not** the cause — B refutes it. An untrusted folder is,
  and it returns **before** `RunAutomaticTasks` prints its first trace, which is why even
  the log is empty.
- ⛔ **The log recipe shipped in 0.40.1 was wrong and is corrected.** `Developer: Set Log
  Level...` is **too late**: the automatic-task decision is taken while the window starts, so
  raising the level afterwards leaves the log empty (measured — `renderer.log` held nothing
  but `[info]`). The right form is: close EVERY window, then `code --log trace <folder>`.
- ⭐ **New tool, `Tools/Debug/vscode_snapshot.py`.** The owner asked the right question:
  "first open does nothing, second one works" is a claim about a DIFFERENCE, and no single
  reading answers it. It dumps the five places that decide this — three of them SQLite
  databases no editor opens — as plain text, and `--diff` compares two snapshots. ⚠ Take
  them with VS Code CLOSED. ⛔ A snapshot lists every folder that machine has ever opened, so
  it is in `.gitignore` and never committed.
- ⭐ **It carries its own selftest, wired into `test_all.py` (11/11).** A broken comparison
  prints `no difference` — which is also the honest answer on an unchanged machine, and the
  two cannot be told apart by looking. The selftest plants a known change and fails if it is
  not reported.

---

## 0.40.1

- ⛔ **`--status` reported a task under an OLD NAME as no task at all.** It happened the
  hour the rename landed: the screen said `⛔ NOT in tasks.json / No usage terminal will
  open` about a task sitting right there, still `runOn: folderOpen`, still opening a
  terminal. It now gets its own sentence — present, but under the old name — and says what
  is actually wrong with that: nothing which removes tasks by the current name can reach it.
  ⭐ Mutation-checked: disable the branch → `an old-label task did not report as an
  old-label task`.
- ⭐ **When the automatic start fails, it can now say how to SEE why.** Read from VS Code
  1.135.0's shipped workbench bundle: `RunAutomaticTasks` sets its own `_hasRunTasks` flag
  **before** it looks for tasks; finding none it waits **10 seconds** for
  `onDidChangeTaskConfig` and then gives up **for that whole window**; and when the folder
  is not yet trusted it returns **in silence** — while `Tasks: Run Task` asks for trust
  instead. ⛔ Both give-ups are logged at **Trace** and nowhere else, so `--status` now
  hands over the recipe: `Developer: Set Log Level...` → Trace → restart →
  `window1/renderer.log`, search `RunAutomaticTasks`.
- ⚠ **This release does not make the automatic start more likely to work.** That race lives
  inside VS Code and no plugin can reach it. It only turns "nothing happened" into "here is
  the branch it took".

---

## 0.40.0

- ⭐ **The task is now called `Claude Usage Watcher`.** The owner's instruction. VS Code's
  Run Task list, the dedicated terminal's tab, and the quoted notification all follow.
- ⛔ **The old name is not forgotten, and that is the point.** A rename that teaches only the
  writer the new name leaves the old `Claude usage watch` task sitting in `tasks.json` —
  still `runOn: folderOpen`, so every folder open starts **two** watcher terminals, and
  nothing that removes tasks by label can reach the old one again. `LEGACY_TASK_LABELS` in
  `install.py` remembers every name ever written; writing, the is-it-current check, removal
  and `Tools/clean-dispatch-guard.ps1` all match both.
- ⭐ **Mutation-checked.** Drop `LEGACY_TASK_LABELS` from `ours()` →
  `AssertionError: ['Claude usage watch', 'Claude Usage Watcher']` — those two terminals.
- ⚠ **An already-open old terminal does not rename or close itself.** It belongs to the
  previous folder open; reopen the folder, or close it by hand.

---

## 0.39.2

- ⛔ **The EXPIRED sentence is gone too.** The owner's instruction: *"「已過期」也不顯示"*.
  `token_note()` is deleted, so neither display — the CLI statusline nor the watcher —
  reports an OAuth token any more.
- ⭐ **The expiry is still read, and that half must not go with it.** `fetch()` uses it to
  refuse to spend one of the endpoint's five calls on a token the credentials file already
  shows is dead.
- ⚠ **One OAuth sentence can still reach the display, deliberately.** It is `fetch()`'s
  failure reason, arriving by the ordinary failure-reporting route, and **only once the
  stored number has also gone stale** — the moment the figures on screen are wrong. Going
  quiet there is exactly the confident wrong answer this plugin refuses everywhere else.
  Say so if you want that one gone as well.
- ⭐ **The check is mutation-killed.** Put `token_note()` back →
  `token_note() is back - the bar must not report an OAuth token`. ⚠ Pinned by the SYMBOL
  rather than by a rendered line: the statusline and the watcher build their notes
  separately, so a text assertion on one cannot see the other.

---

## 0.39.1

- ⛔ **The OAuth countdown line is gone.** The owner's instruction: *"OAuth 那行不要顯示"*.
  It warned for the last ten minutes of the token's life, and that warning **fixes itself** —
  whichever Claude client is running rotates the token about five minutes before it expires.
  So the ordinary case was a line that appeared, was read, needed nothing, and vanished on its
  own. A note people learn to ignore costs the notes beside it their credibility.
- ⭐ **EXPIRED stays.** A dead token stops the fetch, so every figure on the line reads `--`,
  and that sentence is the only thing on screen that says why. Removing it as well would leave
  an empty bar explaining nothing.
- ⭐ **The check is mutation-killed.** Put the countdown back → `a live token warned: the
  countdown is back`. ⚠ It tests a **live** token with 60 seconds left, which is inside every
  threshold the old warning used, so a countdown returning by any route fails here rather than
  passing on a lucky threshold.
- ⭐ **The watcher names the no-reload route first.** F1 → `Tasks: Run Task` →
  `Claude usage watch` opens it in the window you are already in. ⚠ The automatic start still
  needs a folder open, and **no outside program can trigger it**: the VS Code 1.135.0 CLI has
  no option that runs a task in a window already running (measured against the whole of
  `code --help`). ⇒ The gap is once per MACHINE — after the user-level `tasks.json` is
  written, every later folder open starts it by itself.
- ⛔ **`/dispatch-guard:status` is no longer reported as "Shell command failed".** `--status`
  exits 1 whenever anything is not live, and a `!` command that exits non-zero makes the
  harness print a failure and route the whole report to stderr — a report working exactly as
  designed, reading as a broken command, at the one moment somebody is using it to debug.
  ⚠ An `echo` now follows it: the real exit code is printed and nothing is silenced.

---

## 0.39.0

- ⭐ **The gauge reads the last 30 minutes, not the whole five-hour window.** New key
  **`burn_window_min`** (default 30) sets it. ⚠ **0 = the whole window** - steady, but over an
  hour to notice that the rate changed. ⛔ Below 5 it is raised to 5 **and says so**: a shorter
  baseline cannot resolve a rate from whole-percent readings, so a well-meant `2` would not
  make the gauge twitchy, it would **switch it off for ever**.
- ⛔ **A bug fixed: `_burn_rate` accepted `now` and never read it.** Its end point was the last
  *logged* row, and history rows are written only when a number MOVES - ⇒ an idle stretch froze
  **both** ends and the figure was not being recomputed at all, just redrawn. ⚠ Measured on a
  real window: after 84 quiet minutes the rate read **39% high** and the burn-out time **78
  minutes too soon**. The end point is now `now` and the live `pct`.
- ⭐ **The start point is what was spent `burn_window_min` minutes ago.** A row's value stands
  until the next row (nothing changed, or a row would have been written), so the newest row at
  or before the cut IS the value at the cut. ⇒ The baseline is a true 30 minutes, not "however
  long ago the last row happens to sit".
- ⭐ **The window's own start survives as the anchor where it is valid.** Inside the first
  `burn_window_min` minutes the cut reaches back past the open, and a window opens at 0% by
  definition - so no logged row is needed at all.
- ⛔ **The number is now deliberately twitchy.** `used_percentage` is reported in whole
  percent, so one step over a 30-minute baseline is **0.033 %/min**, and on a quiet window that
  quantum is most of the signal. Measured on real history, a 25-minute baseline swung
  **0.407 → 0.040 %/min** across half an hour in which the whole-window figure moved
  0.150 → 0.137. ⇒ It is safe to be twitchy for exactly one reason: **no burn figure reaches
  GO / PACE / STOP**, and a check pins that.
- ⚠ **Measured live on this machine**: at one instant the last 30 minutes read **0.23 %/min**
  against the whole window's **0.053** - a factor of 4.4.
- ⚠ **One assumption is recorded at the rule itself**: a gap in the history has two causes the
  timestamps cannot separate - nothing was spent (the reading is right), or nothing was
  WATCHING (Claude Code closed, the machine off), and the quota is account-wide. ⇒ The second
  under-states the rate, the dangerous direction. ⛔ A "went to sleep" marker does not fix it:
  the shutdown that matters is the one that does not get to write anything. A **heartbeat row**
  does. Not built.

---

## 0.38.2

- ⛔ **`--status` reported the permission it had just granted as "not set".** A VS Code user
  `settings.json` is JSONC — comments and trailing commas are legal there and `json.load`
  rejects both — and `--status` read it with `load()`, so the whole file came back empty and
  every setting in it read as unset. ⚠ Not a corner case: `allow_automatic_tasks()` **writes
  a `//` comment as it grants**, so from the moment this plugin allowed automatic tasks on a
  machine, that machine reported "⛔ not set" for ever. Measured 2026-08-29 on a second
  development machine: the task was present, current and at user level, `--status` called the
  permission missing, and the file itself said `"on"`. ⇒ That line is the one thing there is
  to consult when the terminal did not open.
- ⭐ **It reads the raw text now, and reads the VALUE rather than the key.**
  `automatic_tasks_value()` extracts it with a line-anchored pattern. ⛔ Not the substring
  test `allow_automatic_tasks()` uses: that test is right THERE — its bias is to never
  overwrite a value somebody already chose — and here it would call `"off"` allowed, and
  would count a commented-OUT line as set, which is exactly how a person says they withheld
  it.
- ⭐ **The check is mutation-killed.** Put back `json.load` → `JSONC read as unset`;
  substitute the substring test → `off read as allowed`. Both live in
  `dispatch_gate.py --selftest`.
- ⚠ **The grant policy is unchanged.** The permission is still written only when that call is
  the one that installed the task. A hook quietly editing somebody's editor settings every
  session is the surprise this plugin avoids everywhere else.

---

## 0.38.1

- ⛔ **The brake does not read the burn rate, and that is now pinned.** The owner's
  instruction: *"GO / PACE / STOP 派工或剎車都不參考這個值, 先只畫圖顯示最近的燃燒速度就好."*
  ⚠ The existing pin guarded the projection only, and `burnout_min` is a **second way in** — it
  is computed inside `verdict()`, returned, and writes a sentence into the text. One `if` would
  silently make it a brake.
- ⭐ **The check FORCES rather than reads.** Both figures are driven to their worst - "spent in
  one minute" and "projected 999%" - at a percentage twenty-three points under `soft_pct_5h`,
  and the verdict must stay **GO**. ⚠ It also asserts the forcing REACHED both figures, or it
  would pass by never running the path at all.
- ⭐ **It still warns**, which is the whole design: a sentence, never a decision.
- ⚠ **The burn-meter work is SHELVED**, written up in `Memory/notes/SHELVED-burn-meter.md`:
  what was measured, which two figures given to the owner are **refuted**, which ideas are
  **rejected and should not be re-proposed**, and why collecting logs first is the good trade
  (history rows are raw readings, so changing the estimator invalidates none of them).

---

## 0.38.0

- ⭐ **The burn rate is measured from the window's OWN START.** A window opens at 0% by
  definition, so `(reset − 5 hours, 0%)` is a reading **nobody had to record**.
- ⛔ **Without it the busy tail stood for the whole window.** Logging does not begin when the
  window does - a reinstall, a first run, a machine that was off. MEASURED on a second
  machine, 2026-08-28: the window opened at **14:10** and the first row is **16:49, with 35%
  already spent**. The logged rows alone gave **0.48 %/min** for a window whose true average
  was **0.22 %/min**.
- ⚠ **The direction of error changes, and that is the part to know.** Before, a late start
  OVER-stated the rate - the safe direction. Anchored, a window that sat idle for hours and
  then burst UNDER-states it. ⇒ That is accepted for one reason: **this figure no longer
  drives GO / PACE / STOP**, it is a gauge to read. If the projection is ever re-enabled as a
  verdict input, the anchor has to be revisited with it.
- ⭐ **One logged row is now enough**, because the window's start is the second point. That
  case used to return "cannot be known".
- ⚠ **Measured: it is not uniformly softer.** On the same machine's 21:14 reading, anchoring
  gives **149 minutes to empty** against 154 from the logged rows alone - 7% went in the 11.7
  unlogged minutes, faster than the logged stretch that followed.

---

## 0.37.0

- ⛔ **The projection no longer sets GO / PACE / STOP - display only, for now.** The code is
  **commented out, not deleted**; re-enabling it is uncommenting one line.
  ⚠ The reason is measured: replaying another machine's real history, the verdict flipped
  **three times in twelve minutes** (GO→PACE→GO→PACE→GO) while the percentage climbed
  smoothly from **40% to 52%**, never within twenty points of `soft_pct_5h`.
  ⇒ The boundary is `(100 − pct) / minutes_left`, so at 47% with 114 minutes left a swing of
  **one hundredth** of a percent per minute crosses it - and a dispatch wave moves the rate
  far more than that.
- ⛔ **And since 0.35.0 a PACE costs something**: it makes a current `HANDOFF.md` a
  precondition of dispatching. ⇒ One flickering sample blocked a dispatch that should have
  gone through, and this plugin's own rule - act on the WORD, never on raw percentages - was
  undermined by a word that was itself twitching.
- ⭐ **Two things to add before re-enabling, recorded in the code**: ⑴ **hysteresis** - enter
  at ≥100%, leave only below 90%; a single threshold on a noisy input can only chatter.
  ⑵ **a minimum history** - logging does not start when the window does. On that machine the
  window opened at 14:10 and the first row is 16:49 with 35% already spent, so ignoring the
  unlogged head made the busier logged stretch stand for the whole window: **0.48 %/min
  against a whole-window average of 0.22**.
- ⭐ **The burn gauge still renders and still changes colour** - that is the thing to watch.
- ⛔ **Reset instants snap to the nearest whole minute.** Measured: one window's history holds
  both `19:10:00` and `19:09:59`. ⚠ Nearest, not always up: rounding `19:10:00.2` up gives
  19:11 - a whole minute wrong, in the direction that makes the window look longer.
- ⭐ **The idle line keeps only what needs acting on.** `2 min old` and `idle 15m` both
  restate what `SLEEP` already says; ⚠ only the OAuth warning survives - it is the one thing
  that breaks while you are away, and being away is when nobody is watching for it.
- ⚠ `/Debug/` is gitignored: real usage figures pulled off ANOTHER machine to diagnose
  something here belong in neither a published repository nor this repo's state.

---

## 0.36.0

- ⭐ **A burn gauge, permanently after the usage bars**: `Burn ▓▓▓░░░░░░ 1.20%/m · 44m left`.
  ⇒ It answers one forward-looking question: **can I keep spending?** The bar measures the
  budget's life against the TIME LEFT IN THE WINDOW — **a full bar means this window resets
  before you run dry**. ⚠ It is a ratio, not a stock: unlike a health bar it goes back UP
  when the burn slows, because what it measures is whether the two clocks cross.
- ⛔ **Colour is inverted here** and must NOT use `colour_warn_pct` / `colour_alarm_pct`:
  everywhere else a high percentage is bad, here a full bar is good, and the shared
  thresholds would paint safety red.
- ⛔ **Unknowable is never drawn as an empty bar or a zero.** In a column where empty means
  DANGER, drawing "no data" as empty says the opposite of the truth. It renders
  `───────── --`.
- ⚠ **The first design was a sparkline and it was cut**, because it answered the wrong
  question: history rows are written only when a number MOVES, so a quiet hour does not draw
  a low bar — it draws nothing at all. The axis looked like time and was not.
- ⚠ Cost, measured: **2.47 ms** per render on real history, against a statusline that draws
  once per `refresh_seconds`.

---

## 0.35.0

- ⛔ **The handoff becomes a PRECONDITION of dispatching, not an action at STOP.** The old
  design assumes the agent still gets a turn when it hits STOP — ⚠ and a real cut-off, the
  server refusing, **gives no turn at all**, so the resume wakes with nothing on disk saying
  what was being done. ⇒ Once usage reads PACE or STOP, a dispatch is REFUSED unless the task
  folder holds a current `HANDOFF.md`.
- ⭐ **"Stale" is a state of its own, and the one a size check cannot see.** A handoff from
  three windows ago passes existence and length while describing work that no longer exists —
  and a resume acting on wrong instructions is worse than one that knows it is
  reconstructing. ⇒ Three states, reported separately (missing / placeholder / stale),
  because the remedies differ.
- ⭐ **`require_handoff_past_soft`, default true.** The two failures are not symmetric:
  refusing is LOUD and costs one file write, while not refusing is SILENT and costs a whole
  window. ⚠ It gates DISPATCH only, and below the soft threshold it never fires.
- ⭐ **Setting it false changes two things** (the config comment says both): the dispatch is
  allowed, and `--arm` stops refusing without a handoff — the resume then wakes with a
  **reconstruction prompt**. ⛔ That prompt names the sources cheapest-first with ABSOLUTE
  paths (progress.md → git → the task folder), forbids the session transcript outright,
  forbids redoing work that is already committed, and makes writing the handoff the FIRST
  action so the next cut-off is not identical.
- ⭐ **`auto_arm_resume`, default true.** Arming is the one step whose omission cannot be
  recovered from. It arms for THIS dispatch's folder, against the reset of the window that is
  BLOCKING; ⛔ and it arms ONCE — unless the target moves (the brake flipping from the
  five-hour window to the seven-day one), which re-arms.
- ⚠ `HANDOFF.md` and the 200-character floor have ONE definition now, in the gate, which
  resume.py already imports. Two copies of that threshold are two chances for the gate to
  refuse what the resume would accept.

---

## 0.34.0

⛔ **Updating: run `Tools/clean-dispatch-guard.ps1` and reinstall**, or replace `soft_pct` /
`hard_pct` / `seven_day_binding_pct` in your config with the four keys below — the old names
are **not read any more**.

- ⛔ **The brake ignored the seven-day window entirely.** It read the five-hour percentage and
  nothing else; the seven-day figure produced a **note** and never a level. ⇒ **7d 99% beside
  5h 0% read as `GO`**, and kept dispatching until the SERVER refused. Both numbers true, the
  answer wrong. Reported by the owner.
- ⭐ **One pair of thresholds per window, four in all:**

  | key | default |
  |---|---|
  | `soft_pct_5h` | 70 |
  | `hard_pct_5h` | 85 |
  | `soft_pct_7d` | 95 |
  | `hard_pct_7d` | 97 |

  ⚠ The 7d pair sits high on purpose: that window is usually not the constraint, and pacing
  on it at 70% would throttle a week of work for nothing.
- ⭐ **The stricter of the two wins, and the verdict says which one is driving it.** A reader
  who sees `5h 0%` beside STOP and is not told why concludes the brake is broken — and a
  guard believed broken is a guard that gets switched off. ⚠ Ties go to the five-hour window,
  the nearer and more actionable one.
- ⛔ **A seven-day STOP is not the same instruction as a five-hour one.** The resume must be
  scheduled after the SEVEN-DAY reset, which can be days away, and the text says so.
- ⚠ **Near-reset softening is per window.** A 5h STOP twelve minutes from its reset is worth
  softening; a 7d STOP three days out is not, and one shared test would have softened both.
- ⛔ **An early return that threw the whole week away, fixed on the way past.** A five-hour
  window that had already turned over returned GO **on the spot** — so an account whose week
  was spent was told GO the moment its five-hour window rolled over.
- ⚠ `seven_day_binding_pct` is gone; the "BINDING" wording reads `soft_pct_7d`. One name per
  thing.

---

## 0.33.0

- ⛔ **The `--watch` line was wider than the terminal, so every render stranded a row.**
  ⚠ The cause is not what it looks like: `_line()` **does** fit itself to the width — and
  `watch()` then prepended a timestamp and appended the verdict word, **sixteen columns
  nobody had subtracted**. Measured at width 150: the body came back 149 characters and the
  line that reached the terminal was **165**. ⇒ It wrapped, and `\r` returns to the start of
  the LAST VISUAL ROW while `\033[K` clears only that row.
- ⭐ **Idle draws once and then stops redrawing.** That removes the defect at its source
  rather than mitigating it: **a row nothing is rewriting cannot be stranded, whatever its
  width**, and an idle machine stops scrolling a terminal full of identical lines all night.
  ⚠ It resets on waking, so the next quiet spell marks itself too.
- ⭐ **That one render keeps its content** — the figures stay, the colour goes, and the
  verdict word becomes `SLEEP`. (The owner's rule: a frozen figure is dangerous when a FETCH
  is failing, but while nobody is working nobody is spending. The exposure is the moment work
  resumes, and `should_fetch()` starts fetching at that same moment.) ⚠ `SLEEP` is
  display-only and **never reaches `verdict()`**, which the gate reads for GO/PACE/STOP.
- ⭐ **Two rows when one will not hold everything, instead of throwing information away.**
  The usage bars and the verdict stay on the first row; the context bar, the model and the
  note move to the second, and **each row is fitted separately** (two rows that can each wrap
  is the original defect twice over). Rewriting moves the cursor back up, and the row count
  never shrinks — so a row that is no longer used is CLEARED rather than left holding an old
  line nothing will overwrite.
- ⭐ **A bar for the model-scoped window**, when the account has one running. ⛔ The response
  carries **no entitlement field**, and that is measured: across two captured accounts the
  scoped row exists on BOTH, `is_active` is false on both — it stayed false at 19% used — and
  `nimbus_quill` read 0.0 while the scoped row read 19%, which is evidence AGAINST that
  codename being Fable's counterpart. ⇒ So the bar answers what the data can answer — **is a
  scoped window RUNNING** (`percent > 0` or a non-null `resets_at`). ⚠ An entitled account
  that spent nothing this week sees nothing until its first use. ⭐ The model is not
  hard-coded: the row names itself.
- ⭐ **When the five-hour window runs out, not only whether.** "Projected 175% by reset" says
  it will be exhausted and leaves the reader to work out whether there is room for another
  wave. ⛔ It shares ONE sampling with the projection: two samplings would disagree at the
  edges and put "projected 175%" beside "runs out after the reset" on one line. ⚠ `None`
  means **unknowable, never safe** — no history, one row, under five minutes of span, or a
  flat-or-falling rate; all four return None and all four are checked.
- ⚠ The 110-character note is shorter too: the OAuth warning drops "open a Claude session to
  refresh it", and "no session active for 7h-35m; not fetching" becomes "idle 7h-35m".

---

## 0.32.0

⛔ **Updating from an older version: run `Tools/clean-dispatch-guard.ps1`, then reinstall.**
This release unifies every name and keeps **no compatibility path** for the old ones.

- ⭐ **One name per thing.** It started with the owner finding that the key they had written
  in their config was not the key the code reads, so the switch had never done anything -
  and **nothing anywhere said so**.

  | old | new |
  |---|---|
  | `debug.token_usage_history` | `debug.token_usage` |
  | `limits.json` | `token_usage.json` |
  | config key `limits_file` | `token_usage_file` |
  | `token_usage_history-<stamp>.jsonl` | `token_usage_history_<stamp>.jsonl` |
  | `usage-response-<stamp>.jsonl` | `API_response_usage_<stamp>.jsonl` |
  | `model_prices.spawn` | `model_pricing.spawn` |
  | `dispatch-gate.log` | `dispatch_gate.log` |
  | `dispatch-gate-error.log` | `dispatch_gate_error.log` |
  | `resume-failed.json` | `resume_failed.json` |
  | `asked-vscode-task` | `asked_vscode_task` |

- ⭐ **The rule is written down now**: snake_case for everything this plugin owns, hyphens
  only inside a timestamp; the extension states the FORMAT (`.json` one document, `.jsonl`
  one value per line, `.log` text); marker files are `<subject>.<kind>`. ⚠ The single
  exception is `API_response_usage_*`, which matches its config switch
  `debug.API_response_usage` exactly - more useful than being consistent with the rule.
- ⛔ **`.jsonl` was NOT changed to `.json`, deliberately.** Both files are one JSON value per
  line; the other extension would make `json.load()` raise and mark the whole file as a
  syntax error from line 2 in every editor.
- ⛔ **No retired name is read any more.** `keep_history`, `token_usage_history` and
  `limits_file` do nothing; logs under the older names are neither read nor pruned. ⚠ So a
  config still carrying one gets the DEFAULT rather than the value somebody wrote.
- ⭐ **`install.py --status` names every retired key it finds and marks it `⛔ IGNORED`.** An
  ignored setting is silent by construction, and that report is the only place it ever shows
  up - so it is the compensating control for dropping compatibility.

- ⛔ **No execution path carries a version number any more.** The plugin installs to
  `~/.claude/plugins/cache/dispatch-guard/dispatch-guard/<VERSION>/`. Hooks are immune
  (`hooks.json` uses `${CLAUDE_PLUGIN_ROOT}`), ⛔ but the statusline command, the VS Code
  task and every command the gate hands to the model all held a literal absolute path.
  `update` moves the directory and **leaves the old one behind**, so a stale path keeps
  working and keeps running old code while everything reports healthy.
- ⭐ **They all point at one file that never changes** — `~/.claude/dispatch-guard/run.sh`
  (`run.cmd` for the VS Code task) — which forwards into whichever copy is current. The gate
  aims it at the running copy at every session start; ⛔ and **it also finds one itself** if
  the recorded path is gone. That window, between an update and the next session, is exactly
  where the silent failure used to live.
- ⚠ **The first version of the check was blind, and that is worth recording.** It searched
  the wired paths for `/<n>.<n>.<n>/` and **passed with the bug put back** — in a development
  checkout the plugin lives at `C:/WorkSpace/dispatch-guard`, which has no version in it
  either. ⇒ It asserts the positive property now: every wired path goes through the shim.
  That version is mutation-killed.

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

## 0.30.1

- ⛔ **The mirror would have deleted the one file keeping the work log private.** To avoid
  overwriting the public `.gitignore` I had dropped it from the mirror's SOURCE side — and a
  mirror deletes whatever is in the target and absent from the source. ⇒ The next publish
  would have removed the public `.gitignore`, the single file keeping `Memory/` out of a
  public repository. Caught by the owner (`3acb0fb`).
- ⛔ **Check the target can commit BEFORE mutating it.** The first version copied and staged
  thirty files, then discovered that repository had no git identity (`44bc4c5`).
- ⚠ Removals are staged with `--ignore-unmatch`, because most were never tracked
  (`745bb30`); the ensured ignore set now covers what a copied folder actually brings
  (`aaa6a88`).
- ⭐ **`Tools/PUBLISHING.md`**: "update the public repo" is one command now, and written
  down — each rule beside the failure that produced it (`7d5c8aa`).
- ⭐ **`history_keep_days`, default 30.** A file in `history_dir` whose last-modified time is
  older than that is removed WHOLE. ⛔ Never trimmed: trimming leaves a record that looks
  complete and is not (`f24f12f`).
- ⛔ **"A logs/ folder under the state directory" is not a place anyone can go and look.**
  The absolute path `~/.claude/dispatch-guard/logs/` is written out now. ⚠ And
  `state_dir()`'s own docstring was wrong — it said `~/.claude/` where the function returns
  `~/.claude/dispatch-guard` (`d018d97`).
- ⭐ **No `config.json` is written, not one byte.** Third design, first with no hazard in it:
  copying `config.example.json` whole PINNED every value, so a machine set up before a
  default moved kept the old one silently — two reinstalls to find (`dcae793`).
- ⚠ **`Tools/Debug/scratch/` earns its place in two halves.** As the single outlet it is not
  optional — it is what makes "after a run, `git status` must be clean" a real test — but the
  kept files were only useful to whoever already knew they existed, so the failure report now
  names the folder (`ab563b5`).

---

## 0.30.0

- ⭐ **One command to publish the public snapshot**: `python Tools/publish-public.py --push`.
- ⛔ **A delta silently misses deletions.** "Copy what changed since 0.24.0" carries additions
  and edits and leaves a privately-deleted file alive in public for ever, with nothing to
  notice it. ⇒ The script MIRRORS the tree instead: what is not in the source is removed from
  the target.
- ⚠ It refused its own first run, by design.

---

## 0.29.0

- ⭐ **The install can now say what it did without a model to say it.** The owner's
  constraint: assume the person has NO USAGE LEFT when they install, and the install must
  still complete.
- ⛔ **With no budget there is no model turn** — so every SessionStart note beginning
  "⭐ TELL THE USER:" was an instruction to something that will not run. Three of them
  described changes written into somebody's settings or repository.
- ⛔ **The gate's SessionStart had no channel to the person at all.** It printed plain text,
  and plain stdout on that event can only ever become model context.
- ⇒ `maybe_install_vscode_task`, `maybe_repoint_statusline` and `maybe_adopt_statusline`
  return `(context, screen)` now: the context half for the model when there is one, the
  screen half straight to the person through `systemMessage`.

---

## 0.28.0

- ⭐ **The watcher now proves it is running, instead of only being defined.** `--watch`
  touches `watch.alive` in the state directory and `--status` reads its age:
  `usage watcher : RUNNING - last drew 0 min ago`.
- ⛔ **They are not the same question.** On the machine this came from, the task was present
  and correct the whole time and the terminal still did not appear. ⇒ A definition proves
  intent; it does not prove a process.

---

## 0.27.0

- ⛔ **`--status` could not answer the question it was built for.** It reported the
  statusline and said NOTHING about the VS Code watcher task. On the machine where this came
  up the task was present and correct the whole time, and the report could not say so — so
  "no usage terminal" became a hunt through four commands instead of one line.
- ⭐ It now reports the task, per VS Code user directory.

---

## 0.26.1

- ⭐ **Finding nothing to clean answered the question asked, not the one they have.**
  Somebody who runs a cleaner and is told "nothing here" is usually one step from installing
  — so the run ended on a dead end at exactly the moment the next command was obvious.
- ⚠ Both endings get the install command from ONE definition. Two copies drift the first time
  one changes, and a cleaner printing a stale install command is a small lie in the last thing
  a person reads.
- ⛔ The empty case also says what it CANNOT tell you: "a wrong folder looks exactly like a
  clean machine".
- ⭐ **`debug.API_response_usage`, default false.** With it on, every response the usage
  endpoint returns is appended WHOLE to `<history_dir>/usage-response-<stamp>.jsonl`, one JSON
  array per line. ⚠ Why: the parser keeps `five_hour` and `seven_day` and discards the rest. A
  question about the five-hour window's boundary was answered on 2026-08-27 only because
  `resets_at` happens to be one of the two fields already stored — **luck, not design**.
  ⛔ The call site is BEFORE `if not five: return`, because that early return fires on exactly
  the response the parser cannot use, which is the shape a diagnostic most needs. (That
  feature shipped under 0.26.1 without a version of its own.)

---

## 0.26.0

- ⛔ **The cleaner asked for consent before it had anything to consent to.** Reported:
  it printed `target : C:\Users\...\.claude` followed by "things will be deleted", and the
  reasonable reading is that it deletes the whole Claude Code directory. It never did — that
  path is where it LOOKS — but the words said otherwise, on a confirmation prompt for a
  destructive action.
- ⛔ **And the confirmation made it worse.** It asked for the last path segment typed back,
  which is `.claude` — so it read as "type .claude to confirm deleting .claude", reinforcing
  the exact misreading the header had created.
- ⇒ Rebuilt to the owner's shape: **no parameters at all**, every item to be deleted or
  edited listed first, and only then a typed `confirm` (case-insensitive), defaulting to
  doing nothing.

---

## 0.25.0

- ⭐ **`Tools/clean-dispatch-guard.ps1`** — removes every trace of an older install: which
  folders, which files, which settings values inside which files.
- ⛔ **Why a cleaner is needed when the plugin self-heals.** A stale statusline and a stale VS
  Code task both repair themselves from 0.13.0 onward, so most upgrades need nothing. What
  never self-heals is everything the plugin was once told to REMEMBER: a `config.json` written
  before 0.11.0 PINNED every value, so a later default never reaches that machine; and renamed
  keys are IGNORED, not warned about.
- ⛔ **And it uninstalled a live plugin before it was safe.** A fixture test failed to
  redirect `$HOME` in a child PowerShell, so `-Apply` ran against the real `~/.claude`.
  ⇒ Four fixes: the target is printed first and confirmation is typed, paths are injected
  (`-ClaudeHome`), JSONC is detected in the raw text, and each file is backed up once per
  run.

---

## 0.24.1

- ⭐ **A step 0 ahead of the install**: set VS Code's **Allow Automatic Tasks** first, so
  the notification never appears. ⚠ The old order had a step you could only meet by MISSING
  it: the notification fades on its own, and declining it — or never seeing it — leaves the
  watcher task written, visible under Run Task, and never starting on folder open, with no
  error anywhere.
- ⛔ **And the command name in the README did not exist.** It said
  `Tasks: Allow Automatic Tasks`. There is no such command — measured against the shipped VS
  Code 1.135.0.

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

## 0.16.2

- ⭐ The three check scripts moved to `Tools/Debug/`, and **every file they produce is
  confined to `Tools/Debug/scratch/`** — relative paths, gitignored, and kept after the run so
  a failing check's output is still there. ⛔ A run must leave `git status` clean; that is
  itself the check that the tests stayed in their sandbox, and it has two precedents: once
  into the working tree, once into `~/.claude`.
- ⚠ Each child process used to wipe the scratch directory and take the previous child's
  evidence with it. `test_all.py` prepares it once now, and directories are namespaced by
  check.

---

## 0.16.1

- ⛔ `test_resume_cancel.py` called `do_cancel()` with the REPOSITORY as its working
  directory, and `log_line()` appends to `<cwd>/.claude/dispatch-gate.log` — so every run left
  the plugin's own log in the working tree. ⚠ That is indistinguishable from the development
  copy being executed, which is the one thing somebody checking their install must be able to
  rule out.
- ⚠ After PROTOCOL.md was slimmed down, both README halves still said "the rules themselves
  are in PROTOCOL.md", which that file now contradicts. Both describe the split now.

---

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

---

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

---

## 0.14.0

- ⭐ **The brake speaks to the PERSON now.** A hook's `systemMessage` is displayed on the
  user's screen (quoted from the shipped reference: "Display a message to the user (all
  hooks)"). One at PACE, one at STOP, one when a dispatch is refused. ⛔ Everything used to go
  only into the MODEL's context, where "it carried on" and "it never heard" look identical.
- ⭐ Entering PACE or STOP demands one exact line from the agent:
  `PACE at 90% - winding down`. ⚠ Not proof of obedience - nothing in a prompt is - but it
  separates "heard it and continued" from "never received it".
- ⚠ Documented: **90% is not the brake by default.** soft_pct 85 is PACE; hard_pct 93 is STOP.

---

## 0.13.2

- ⭐ Both README halves gained the **Allow** notification VS Code shows after an install,
  quoted verbatim, plus three ways to get it back. ⚠ It fades, and missing it leaves the task
  installed and listed while never starting on folder open.
- ⭐ Documented too: `claude plugin update` repairs the stored absolute path by itself, with
  nothing to re-run. Measured, and pinned by a selftest case.

---

## 0.13.1

- ⛔ The automatic-tasks permission did not travel with the task. VS Code asks for it with a
  NOTIFICATION, which fades - so the task was written, Run Task listed it, and it never ran.
  The grant now happens on the write.
- ⛔ The user-level command was shortened to `${workspaceFolder}/…`. A user-level task has NO
  workspace of its own, so that resolves against whatever project is open - wrong in every
  project, including the one it was written from. Absolute paths always, now.

---

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

---

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

---

## 0.11.0

- ⭐ `auto_vscode_task` now defaults to **on**. ⛔ Off, the feature was undiscoverable: the
  hook's only channel was a SessionStart message, which reaches a MODEL's context rather than
  your screen — measured on two clean installs where the task never appeared and nothing said
  why. ⇒ The protection moved to the CONFLICT tests (tracked by git, unparseable) instead of a
  default that hid the feature. The ask-once machinery and its marker file are gone: switching
  it off is a decision, not a question to re-open every session.
- ⛔ `test_all.py` crashed while PRINTING a failure on a cp950 console. A reporter that dies
  while reporting is worse than none: the exit code says "failed" and the reason is gone.

---

## 0.10.0

- ⭐ A second skill ships with the plugin: `unattended-work`, how to work with nobody watching.
- ⭐ New `userConfig` option `announce_unattended_work` (default on). ⛔ It cannot disable the
  hook — a plugin's hooks always fire — so what it switches off is what the hook PRINTS.
  ⚠ An unrecognised value counts as ON: a reminder that silently stops is worse than a
  redundant one.

---

## 0.9.4

- ⛔ An uninstall CREATED a file: removing the task from a project that never had a
  `tasks.json` wrote a new empty one, so clearing a machine down left a `.vscode/` directory
  in every repository it touched.

---

## 0.9.3

- ⛔ The `auto_vscode_task` offer was spent by a single unseen message. The mark was written
  BEFORE the answer, and the message reaches a model's context rather than a screen — so a
  session that ended, or an agent that did not act on it, retired the feature for good. It
  counts misses now, up to three; ⭐ an actual answer (`--enable-auto-task` /
  `--disable-auto-task`) retires it immediately.

---

## 0.9.2

- `Memory/tasks/` is no longer tracked; it had shipped 80 KB of review reports.
- `test_all.py` runs all four checks with one command.

---

## 0.9.1

- CHANGELOG.md added. README and PROTOCOL no longer carry version history.
- ⛔ Two NUL bytes repaired in README.md; git had begun treating it as a binary file.

---

## 0.9.0

- `~/.claude/dispatch-guard/config.json` is created for you, from `config.example.json`. An
  existing file is never overwritten.
- `config.example.json` pinned `dispatch.task_root` to a path while the code default is
  `null`, meaning "choose automatically". Shipped as `null` now.
- README and PROTOCOL audited against the code, including the version range above.

---

## 0.8.0

- `--watch` **stops calling the API** after `idle_after_min` (default 15) with no session
  activity, and **keeps redrawing** the line.
- `Ctx` is drawn from the first second of a session, reading 0%. A payload with no such field
  draws `--`, never `0%`.
- All three bars share one `BAR_WIDTH`, widened from 6 to 9. The statusline goes from about
  75 to about 87 columns.
- The README example line became two, one per interface, plus a table of where each segment
  comes from.

---

## 0.7.2

- Cancelling an armed resume distinguishes three outcomes: not registered, deleted, and
  refused by the scheduler. The last two used to be merged.

---

## 0.7.1

- `statusline_install()` no longer overwrites a `settings.json` it cannot read either.
- After `--uninstall` the gate no longer claims nothing will wake later unless the scheduler
  actually agreed.

---

## 0.7.0

- ⛔ Fixes the `NameError` in the advisory above. The self-check now calls the real function.
- JSON files that cannot be read — a commented `tasks.json`, a `settings.json` with a
  trailing comma — are no longer overwritten.
- Statusline ownership tightened: it must contain both `usage.py` and `--statusline`.
- Uninstalling also switches `auto_statusline` off, or the next session put the line back.

---

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

---

## 0.3.0

- A complete uninstall, and `/dispatch-guard:uninstall`.

## 0.2.2 / 0.2.1 / 0.2.0

- The slash commands `/dispatch-guard:install` and `/dispatch-guard:status`.
- Re-running the installer repairs a statusline path left pointing at an older version.
- The install step became a script that finds its own path.

---

## 0.1.0

- First release.
