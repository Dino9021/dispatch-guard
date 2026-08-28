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
