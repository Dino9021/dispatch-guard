<!-- One file, two languages: Traditional Chinese first, English second.
     Two separate files drifted out of step, and a translation nobody can see beside its
     original is a translation nobody updates. -->

> 🇹🇼 **正體中文（本節）** ｜ 🇬🇧 **[English](#dispatch-guard-english)**
> — 同一個檔案，中文在前半段，英文在後半段。

# dispatch-guard

一個 Claude Code 外掛，把子代理派遣的規範從**「建議」變成「強制」**，
並在用量快用完時**拒絕**再派子代理。

**只用 Python 標準函式庫。** 不用 `pip install`、不用 `npm install`、沒有任何要一起帶的相依套件 —
裡面唯一一個非標準函式庫的 import，是它自己的另一個檔。

複製到哪都能用。唯一帶有專案色彩的是任務資料夾放哪裡：
⭐ 它宣告為專案工作路徑底下的 **`Memory/tasks`**，而且 gate 會在 session 開始時**自己建立**它，
所以 agent 永遠不用挑位置。要改就用 `task_root` 這個設定。

---

## 為什麼用 hook，而不是 skill

skill 是模型看了描述之後**自己決定**要不要用；文件是模型**自己決定**要不要讀。
**兩者都只是建議。** 實測過：子代理**讀得到** `CLAUDE.md`、也**叫得動** skill，
所以這從來不是「做不做得到」的問題 — 問題是**沒有任何東西把選擇權拿掉**。

⭐ **hook 把選擇權拿掉了。** 它在每一次工具呼叫、每一個 session、每一層深度都會觸發 —
子代理自己再派子代理，一樣會撞到同一個 hook — 而且它可以**直接拒絕**這次呼叫。

⭐ **而且煞車踩在「派遣」這個動作上，不是塞一段話進去。**
派一個子代理是代理做的事情裡最貴的：子代理要自己重讀一次 context，
它的報告又要被讀回主控。塞一句「請節制一點」只是建議，模型會拿它跟任務權衡。
**但被拒絕的工具呼叫沒得權衡。**

---

## 它會做什麼

| | |
|---|---|
| ⛔ 拒絕**第二個同時進行**的子任務 | 除非 owner 已核准一個數量 |
| ⛔ 拒絕**背景**派遣 | 它會完全繞過計數 — 見下方「做不到的事」 |
| ⛔ 拒絕**計畫還沒寫到硬碟**就派遣 | 計畫與每一個子任務提示詞要先落地 |
| ⛔ 拒絕**一次大量生成**的工具呼叫 | 沒有核准管道 |
| ⭐ 用量到達**硬門檻**就拒絕派遣 | 到軟門檻則對子任務發出警告 |
| ⭐ **自動把規範加在每個子任務提示詞前面** | 每一層都加，派遣的人什麼都不用做 |
| ⭐ **每次派遣的結果自動寫進 `progress.md`** | 之後的 session 才分得出「真的做完」跟「看起來做完」 |
| ⭐ **附帶 `unattended-work` skill** | 沒人看著時怎麼工作。開場提醒可以關掉 |
| ⭐ **可預約用量重置後的一次性續跑** | 關掉終端機、關掉編輯器、session 死掉都還在。⚠ 但**登出不算** — 見下方 |

⭐ **第二組：擋「安靜失敗」的指令** —— 做錯跟做對在螢幕上長得一模一樣的那種。
每一條都有自己的開關，預設全開。

| | |
|---|---|
| ⛔ 拒絕在**這個 session 沒選過的分支**上 `git commit` | 表示另一個 session 把共用工作目錄切走了 |
| ⛔ 拒絕 `git add -A` / `.` / `--all` | 按名字加你改的那幾個檔案 |
| ⛔ 拒絕 `git commit -m` | 訊息寫成檔案，用 `-F <路徑>` |
| ⛔ 拒絕**把錯誤訊息吞掉**的搜尋 | `2>/dev/null`、`2>$null`、`--no-messages`、grep 的 `-s` |
| ⛔ **沒載入 `dispatch-protocol` 就拒絕派工** | 每一次都拒絕，直到它被叫過。`require_dispatch_protocol` |
| ⭐ 沒載入 `unattended-work` 就派工，**拒絕一次** | 只是提醒。要變成閘門就開 `require_unattended_work` |
| ⚠ `cd <相對路徑> && …` 出警告 | `cd` 失敗時，後面整串安靜地不執行 |
| ⚠ 有更舊的 commit 沒推，會提醒 | 只提醒，不拒絕 |
| ⚠ 子 agent 回來了，但**它的提示詞要求的檔案沒有出現** | `guard_agent_report_file`。摘要照樣回來、而且看起來很正常；檔案不存在看起來不正常 |
| ⚠ **唯讀的 `subagent_type`** 配上一份叫它建立檔案的提示詞 | 同一個開關，派工前就警告。⭐ 不認識的型別什麼都不說 |
| ⛔ 拒絕**模型太貴**的子代理派工 | `max_model_price`，預設 **5**（每百萬輸入 token 美元） |

⭐ **價格從 Anthropic 官方定價頁抓，不是手打的。**
`hooks/model_pricing.py` 把
[官方定價頁](https://platform.claude.com/docs/en/about-claude/pricing.md)
的 markdown 解析成 `model_pricing.json`，裡面同時記錄 epoch 與 `YYYY-MM-DD HH:MM:SS` 兩種時間。
超過 `model_price_hours`（預設 24）就在**背景**更新 —— ⚠ 它永遠不會卡住任何一次工具呼叫，
發現過期的那個 session 繼續用手上的表，新數字給下一個 session 用。

⛔ **這是這個外掛唯一一次對外連線。** 在此之前它從不連網。
不想連就在 config 設 `"model_price_update": false` —— 上限照樣執行，
用的是隨儲存庫出貨的種子表（切版本那天從官方頁抓下來的真資料），只是數字不再變動。
⭐ **上限在派工「之前」就會告訴 agent**：session 開場的 context
會寫出可以派哪些家族、不可以派哪些，以及目前的價格。hook 是後備，不是通知管道。

⛔ **這一組全部是「規則已經寫下來、也被讀過、然後照樣被違反」才存在的。**
2026-08-27 一個 session 裡違反了四條，其中兩條的違反者就是那天早上寫下它們的那個 agent。
最刺的一條：規則寫「每次 commit 前先確認在哪個分支」，agent **真的跑了那個指令** ——
寫成 `git rev-parse --abbrev-ref HEAD && git add -A && git commit …`。
⛔ `&&` 只問前一個指令有沒有**成功**，從來不問它的**答案能不能接受**。
分支名稱印出來、滑過去了，commit 落在另一個 session 的分支上。

⭐ **規則本身只有一份活的：[skills/dispatch-protocol/SKILL.md](skills/dispatch-protocol/SKILL.md)**
（中文對照在 [SKILL.zh-TW.md](skills/dispatch-protocol/SKILL.zh-TW.md)）。
**[PROTOCOL.md](PROTOCOL.md)** 放的是規則周邊的機制：檔案慣例、hook 到底強制了什麼、
誠實列出的缺口、以及續跑怎麼運作。
⭐ **這份文件只描述現在的行為。** 什麼時候變的、為什麼變，在 **[CHANGELOG.md](CHANGELOG.md)**。

⭐ **要驗證這份 repo：`python Tools/Debug/test_all.py`。** 它跑完十一項檢查並回傳一個結束碼。
⚠ 每一項都只針對「已經真的發生過、而且是安靜的」那種 bug —— 不是為了覆蓋率。
它們不碰 `~/.claude`、不花 API 額度、也不會建立排程工作。
⭐ **產生的每一個檔案都關在 `Tools/Debug/scratch/`**（已 gitignore，而且跑完不刪 ——
檢查失敗時它寫了什麼還在那裡）。⛔ 跑完之後 `git status` 必須是乾淨的，
那本身就是「測試沒有寫到外面」的檢查。

⭐ **`python Tools/Debug/burn_band_fit.py` —— 檢查 Burn 錶的顏色分段還準不準。**
它讀「你目前設定的」`burn_x_yellow` / `burn_x_orange` / `burn_x_red`，用你自己的歷史
算出四個顏色各佔多少時間，然後直接給判定：紅色掉到 0% 或超過約 15% 就該重新校準。
⚠ 它只讀歷史檔的複本，不打 API、不動你的資料。⛔ 它放在這裡而不是任務資料夾，
是因為「什麼情況要重新檢討這組門檻」必須是一個「跑得起來」的指令 ——
任務資料夾是整包封存的。`--dir` 可以指到別的狀態目錄。

---

## 安裝

⭐ **兩條路，挑一條，兩條都是完整的。** 這一節只給步驟；每一步為什麼長那樣，
下面的**說明區**都有 —— 想看再看。

### ⚡ A. 一段貼完（最快，什麼都不用想）

⛔ **在開 VS Code 之前跑完。** 理由見說明區的「**⚠ 安裝後重開 VS Code，它會問你一次**」。

**Windows（PowerShell）**

```powershell
claude plugin marketplace add Dino9021/dispatch-guard
claude plugin install dispatch-guard@dispatch-guard
$p = (Get-Content "$env:USERPROFILE\.claude\plugins\installed_plugins.json" -Raw | ConvertFrom-Json).plugins.'dispatch-guard@dispatch-guard'[0].installPath
if (-not $p) { throw "dispatch-guard is not installed" }
& "$p\hooks\run.cmd" "$p\install.py" --all
& "$p\hooks\run.cmd" "$p\install.py" --status
```

**macOS / Linux**

```bash
claude plugin marketplace add Dino9021/dispatch-guard
claude plugin install dispatch-guard@dispatch-guard
for c in python3 python py; do command -v "$c" >/dev/null && PY="$c" && break; done
p=$("$PY" -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))['plugins']['dispatch-guard@dispatch-guard'][0]['installPath'])")
[ -n "$p" ] || { echo "dispatch-guard is not installed"; exit 1; }
sh "$p/hooks/run.sh" "$p/install.py" --all
sh "$p/hooks/run.sh" "$p/install.py" --status
```

⭐ **這一段把四件事都做完**：外掛、CLI 狀態列、VS Code 的 `Claude Usage Watcher` 工作，
以及 VS Code 的 `task.allowAutomaticTasks`（那個「你來不及按」的通知就不會出現了）。
最後一行 `--status` 是驗收 —— `OVERALL` 那行說 live 就是好了。

⚠ 然後**開一個新的 Claude session**（hook 在 session 開始才載入），**再開 VS Code**。

> 細節在說明區：**1. 外掛本體**、**2.（選配）狀態列和 watcher**、**4. 確認裝好了**。

### 🖱 B. 用介面選單一步一步做

⚠ **只有第 1 步沒有選單** —— 外掛只能從 CLI 裝。之後全部是點的。

| # | 在哪裡 | 做什麼 |
|---|---|---|
| 1 | 終端機 | `claude plugin marketplace add Dino9021/dispatch-guard` 然後 `claude plugin install dispatch-guard@dispatch-guard` |
| 2 | Claude（新 session） | 打 `/dispatch-guard:install` —— ⭐ 先給你看 dry run，問過才動手 |
| 3 | Claude | 打 `/dispatch-guard:status` 驗收 |
| 4 | VS Code | `Ctrl+Shift+P` → `Tasks: Manage Automatic Tasks` → `Allow Automatic Tasks`（第 2 步通常已經設好了，這是保險）|
| 5 | VS Code | 重開資料夾。沒出現的話：`Terminal` → `Run Task` → `Claude Usage Watcher` |

> 細節在說明區：**0.（用 VS Code 的人先做這一步）**、**1. 外掛本體**、
> **2.（選配）狀態列和 watcher**、**⚠ 安裝後重開 VS Code，它會問你一次**、**4. 確認裝好了**。

---

## 說明區 —— 上面每一步在做什麼

### 0.（用 VS Code 的人先做這一步，整個安裝會順很多）

⭐ **一台機器做一次，涵蓋所有專案。** 先把它設好，安裝過程就不會被一個「你來不及按」的
通知打斷 —— 那個通知會自己淡掉，而錯過它的後果是：工作寫好了、`Run Task` 也看得到，
但開資料夾時**永遠不會自動跑**，⛔ 而且不會有任何錯誤訊息。

| 做法 | 怎麼做 |
|---|---|
| ⭐ 指令面板 | `Ctrl+Shift+P` → **`Tasks: Manage Automatic Tasks`** → 選 **`Allow Automatic Tasks`** |
| 改設定檔 | `Ctrl+Shift+P` → `Preferences: Open User Settings (JSON)`，加入 `"task.allowAutomaticTasks": "on"` |

```jsonc
// %APPDATA%\Code\User\settings.json
// macOS: ~/Library/Application Support/Code/User/settings.json
// Linux: ~/.config/Code/User/settings.json
{
  "task.allowAutomaticTasks": "on"
}
```

⚠ **VS Code 的預設值是 `"off"`**，所以在你或安裝腳本改掉它之前，自動工作一律不跑。
那個鍵只接受 `"on"` 和 `"off"`。
⚠ **這是「使用者層級」的設定**，不是每個專案一份 —— 一次就涵蓋所有專案。
⚠ 它也不是這個外掛專用的：你其他專案的自動工作也會跟著被允許。
⛔ **而且工作在「不受信任的工作區」裡不會跑**，不管這個設定是什麼 ——
那是 VS Code 自己的說明原文。要一起按「信任這個資料夾」。

⭐ **不做也可以。** 第 2 步的腳本本來就會幫你設成 `on`；先手動做只是讓你連通知都看不到。
沒設好的話，重開 VS Code 時會看到那個通知 —— 見下面「⚠ 安裝後重開 VS Code，它會問你一次」。

### 1. 外掛本體 — hook 和 skill

```bash
claude plugin marketplace add Dino9021/dispatch-guard
claude plugin install dispatch-guard@dispatch-guard
```

⭐ **這個 repository 同時是市集、也是它自己列出來的那個外掛**，所以上面兩行就是全部。
⚠ `marketplace.json` **必須**放在 repo 根目錄 —— `marketplace add` 只在那裡找它。

不經 GitHub、裝本機的一份就給路徑；開發中請用 `--plugin-dir`，它不複製：

```bash
claude plugin marketplace add C:/WorkSpace/dispatch-guard   # 本機目錄也可以當市集
claude --plugin-dir C:/WorkSpace/dispatch-guard             # 開發用，只影響這一個 session
```

⚠ **外掛的 hook 是在 SESSION 開始時載入的。** 裝完請開一個新的 session 再看效果。

⛔ **需要 Claude Code 2.0.56 以上。** 更舊的版本不認識 `PostToolUseFailure` 這個事件，
而一個外掛只要有一個 hook 掛在該版本不認識的事件上，那個外掛的**每一個** hook 都會被安靜地
關掉 —— 什麼都不強制，也沒有任何訊息（2026-09-02 以 2.0.30 / 2.0.55 / 2.0.56 實測）。
`python install.py --status`（也就是 `/dispatch-guard:status`）會讀 `claude --version`，
版本太舊時警告；找不到 `claude` 時寫「unknown」，不會假裝是 OK。

> ⛔ **裝的是舊版本？先看 [CHANGELOG.md](CHANGELOG.md) 最上面那則安全公告。**
> 有幾個版本因為一個 hook 例外而完全沒有在強制任何規則，而且是安靜的。

### 2.（選配）狀態列和 watcher — 複製貼上，它自己找路徑

⭐ **煞車不需要這一步。** gate 自己 fork 刷新，所以第 1 步做完煞車就活了。
這一步是讓**你**在螢幕上看到那一行用量。

⭐ **沒有路徑要填，也不需要任何人幫你跑。** 下面兩段都自己去讀
`~/.claude/plugins/installed_plugins.json` 裡的 `installPath`，所以版本號不用你管。
⛔ **在你的專案目錄裡執行它** —— `.vscode/tasks.json` 是每個專案一份的檔案，
所以腳本寫進哪個專案，取決於你在哪裡執行它。

**Windows（PowerShell）**

```powershell
$p = (Get-Content "$env:USERPROFILE\.claude\plugins\installed_plugins.json" -Raw | ConvertFrom-Json).plugins.'dispatch-guard@dispatch-guard'[0].installPath
if (-not $p) { throw "dispatch-guard is not installed - run: claude plugin install dispatch-guard@dispatch-guard" }
& "$p\hooks\run.cmd" "$p\install.py" --all
```

**macOS / Linux**

```bash
for c in python3 python py; do command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys" >/dev/null 2>&1 && PY="$c" && break; done
p=$("$PY" -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))['plugins']['dispatch-guard@dispatch-guard'][0]['installPath'])")
[ -n "$p" ] || { echo "dispatch-guard is not installed - run: claude plugin install dispatch-guard@dispatch-guard"; exit 1; }
sh "$p/hooks/run.sh" "$p/install.py" --all
```

⭐ **它同時做完兩件事，因為兩種環境看用量的地方不一樣：**

| | 這個腳本裝什麼 | 裝在哪裡 |
|---|---|---|
| CLI | 狀態列 | `~/.claude/settings.json`，⭐ 每個帳號一次 |
| VS Code 擴充套件 | `Claude Usage Watcher` 工作 | ⭐ VS Code 的**使用者層級** `tasks.json`，一次涵蓋**每個專案** |

⛔ **不會往你的 repo 寫任何東西。** 舊版本是每個專案一份 `.vscode/tasks.json`，
那在「第一次開啟」永遠不會成立 —— 檔案由 session 寫出，而 session 在資料夾開啟**之後**才啟動，
所以**每一個新專案**的第一次開啟都看不到它。

⚠ **安裝完的「第一次開啟」是一場賽跑，而且你會贏或會輸。** 使用者層級的檔案是 session
寫出來的，而 session 在視窗開起來**之後**才啟動。VS Code 找不到自動工作時，會再等
**10 秒**（`onDidChangeTaskConfig`）；⭐ **檔案在那 10 秒內寫進去，它就會跑** ——
實測 2026-08-29，log 依序寫著 `taskNames=[]` 然後 `updated taskNames=["Claude Usage Watcher"]`。
⛔ **超過就整個視窗放棄，而且不會有任何訊息。**

⇒ 所以有的機器「裝完開起來就好」，有的不會。⭐ **兩台都量過了,起點一模一樣** ——
第一次開啟之前 `tasks.json` 兩台都是 `(no such file)`,所以跟同步、跟信任都沒有關係:

| | 視窗開啟 | hook 寫出工作檔 | 差 | 結果 |
|---|---|---|---|---|
| 贏的那台 | `08:59:19` | `08:59:41` | **22 秒** | ✅ 自己起來了 |
| 輸的那台 | `08:43:20` | `08:43:55` | **35 秒** | ⛔ 沒起來 |

⇒ 差別就是 **13 秒**的 session 啟動時間。⚠ 這個數字不是「10 秒」那個門檻本身 ——
VS Code 的 10 秒是從它自己**開始找工作**那一刻起算,而那一刻本身也會被擴充套件拖慢。

⭐ **要讓它必贏，就在開 VS Code 之前，先在終端機跑一次安裝腳本**（下面第 2 步，
或 Claude 裡的 `/dispatch-guard:install`）。檔案先在，就沒有賽跑。
⚠ 第一次之後檔案就一直在了，**從此每個專案、每次開啟都不再有這個問題。**

### ⚠ 安裝後重開 VS Code，它會問你一次

⭐ **這是唯一需要你點的一下，而且只有一次。** 重開資料夾之後，VS Code 右下角會跳出：

> **Notifications**
> This workspace has tasks (Claude Usage Watcher) defined () that can launch processes
> automatically when you open this workspace. Do you want to allow automatic tasks to run in
> all trusted workspaces?
>
> **[ Allow ]** [ Disallow ] [ Open Files ]

⇒ **按 `Allow`。** 那是 VS Code 自己的安全機制：⛔ 沒有它，工作寫好了、Run Task 也看得到，
但開資料夾時**永遠不會自動跑** —— 而且不會有任何錯誤訊息。

⚠ **那個通知會自己淡掉。** 來不及按也沒關係，三種方法都可以：

| 方法 | 怎麼做 |
|---|---|
| 找回通知 | 狀態列右下角的**鈴鐺圖示**，或 `Notifications: Show Notifications` |
| 直接執行那個決定 | `Ctrl+Shift+P` → `Tasks: Manage Automatic Tasks` → 選 `Allow Automatic Tasks` |
| 看它寫到哪裡 | `%APPDATA%\Code\User\settings.json` 的 `"task.allowAutomaticTasks": "on"` |

⭐ **安裝腳本本來就會把那個值設成 `on`**，所以多數情況下你連通知都不會看到。
⚠ 但如果那個檔案在安裝時讀不到（例如帶了 VS Code 不介意、JSON 解析器介意的東西），
它會拒絕改寫並告訴你 —— 那時候就會看到上面那個通知。

### ⭐ 0.32.0 起：路徑裡根本不再有版本號

外掛裝在 `~/.claude/plugins/cache/dispatch-guard/dispatch-guard/**<版本>**/`。
hook 不受影響（`hooks.json` 用 `${CLAUDE_PLUGIN_ROOT}`，每個 session 重新展開），
⛔ 但**狀態列指令、VS Code 工作、以及 gate 給模型的每一個指令**存的都是**寫死的絕對路徑**。
`update` 會搬走目錄卻**留著舊的**，所以舊路徑照樣跑得動、跑的是舊程式 —— ⚠ 而且一切看起來都正常。

⇒ 所以外掛外面的東西**一律不再寫版本化路徑**，全部改成指向這一個永不改變的檔案：

```
~/.claude/dispatch-guard/run.sh      （Windows 的工作用 run.cmd）
```

⭐ 它會轉發到「目前這一份」外掛。兩件事讓它保持正確：
gate 在每個 session 開始時，發現裡面存的路徑不是正在跑的那一份就改寫；
⛔ 而且**它自己也會找**——萬一存的路徑不在了（更新之後、下一個 session 之前那段空窗），
它會去找最新安裝的那一份。那段空窗正是舊的靜默失敗住的地方。

⚠ 舊版本接上去的狀態列還是帶著版本化路徑；`repoint_statusline()` 會把它改成 shim，一次就好。

⇒ **不用重跑任何東西。** ⚠ 這一項實測過：把儲存的路徑改成一個假的舊版本，
下一次就被改回來。

⭐ 細節和實測數字在下面〈在 VS Code 擴充套件裡〉那一節。

⚠ **要重新開啟資料夾**那個 watcher 工作才會起來（`runOn: folderOpen`）。
⛔ 它會在**使用者**設定裡開 `task.allowAutomaticTasks`（那個權限只有使用者範圍有效，
這是安全設計），並先備份成 `.bak-dispatch-guard`。

只要狀態列、不要 VS Code 工作，就把 `--all` 拿掉。
⭐ `--check` 對兩半都有效，所以 `--all --check` 什麼都不會寫，你可以先看再決定。

⛔ **Windows 走 `run.cmd`，Unix 走 `run.sh`，而那個 for 迴圈會「執行」每個候選。**
兩件事都不是多餘的。Windows PATH 上的 `python3` 是微軟商店的假殼：`command -v` 會成功，
執行卻回 49。`bash` 通常也是 WSL 的啟動殼。只查「找不找得到」會得到一個很有自信的錯答案。

<details>
<summary>⭐ 已經在 Claude session 裡？有斜線指令，同一件事</summary>

| 斜線指令 | 做什麼 |
|---|---|
| `/dispatch-guard:install` | 上面那件事。先給你看 dry run，問過才動手 |
| `/dispatch-guard:status` | 現在到底有沒有在動？唯讀，什麼都不改。⭐ 也印出 `install path` |
| `/dispatch-guard:uninstall` | 反過來做。也先給你看 dry run，問過才動手 |

⭐ 它裡面寫的是 `${CLAUDE_PLUGIN_ROOT}`，由 Claude Code 展開，而且每個 session 重新展開一次。
⚠ 斜線指令跟 hook 一樣是 session 開始時載入的，所以裝好之後要開一個新的 session。
打不出來就是版本太舊：先 `claude plugin update`。

</details>

### 狀態列現在是選配 —— 以及它為什麼曾經不是

```bash
python install.py --check    # 只看它會做什麼，不會動任何東西
```

⭐ **`usage.py` 自己去撈數字** — `GET https://api.anthropic.com/api/oauth/usage`，
用的是本來就在硬碟上的 OAuth token。所以狀態列從來就不是**資料來源**。

⭐ **那個時鐘是 gate，不是狀態列。** 數字過期時，gate 會自己 fork 一個背景刷新 ——
而那是它本來就會跑的 hook 事件。

⛔ **而且它不是「在 hook 裡同步撈」那個被否決的做法。** 同步 HTTP 會讓每一次跨過間隔邊界的
派工卡住。它是 fork 完就回來，數字留給**下一次**呼叫去讀。派工永遠不等網路。

⇒ **所以狀態列和 `--watch` 現在是「顯示」，不是「命脈」。** 裝它們是為了讓**人**看得到那一行。

⚠ **API 最多每 `fetch_seconds` 秒問一次（預設 120），
再加上隨機 `fetch_seconds_jitter` 秒的抖動（預設 30，設 0 就關掉）。**
兩個都可以在 config 改。預設下實際等待是 120～150 秒。
抖動永遠是**加上去、不會減** — 設負數會被拒絕並印一行告訴你 —
所以絕不會低於下限。
會加抖動是因為：多個 session 的狀態列都是同一個 60 秒節拍，
不加抖動它們會慢慢對齊、同時撞到同一個間隔邊界 —
那正是把呼叫額度一次燒掉的情況。

⛔ **下限是程式強制的，不是建議** — 設更小會被拉回來，而且會印一行告訴你。
⚠ **下限是 120 秒，和預設值同一個數字** —— 設小於 120 的值會被「往上拉回 120」。
下限在 2026-08-29 調低到 60，只為了讓下面這個說法「可以被實測」；
⛔ **2026-08-31 實測結束：60 秒的間隔十分鐘內收到三次 `429`（08:42:59、08:47:30、08:52:01），
所以改回 120。** 兩次實測合起來才是答案：120 秒下 100 分鐘至少 26 次成功、沒有任何 429，
60 秒下幾分鐘就 429 —— 上限不是「五次」，但也不是「沒有」，它落在兩個間隔之間而且還不知道。
這支端點每個 access token 大概只能打 **五次**
（[onWatch](https://github.com/onllm-dev/onwatch)，它自己監控十家供應商，預設也是 120 秒），
打完會拿到一直不退的 `429`
（[issue #31021](https://github.com/anthropics/claude-code/issues/31021)，已被標為不修），
而煞車會剛好在它最該作用的重載期間變瞎。

⛔ **`--verdict` 永遠不撈數字。** 它是每次派工都會跑的 hook，在那裡做同步 HTTP 會讓派工卡住。
會去撈的是 `--statusline`、`--watch`，以及 gate 在數字過期時 fork 出去的 `--fetch-now`。

⭐ **所以「沒有狀態列、也沒有 `--watch`」不代表煞車瞎掉。** gate 自己 fork 刷新 ——
見上面〈狀態列現在是選配〉。那兩樣是給**人**看的，不是維持數字新鮮的東西。

⭐ **token 是「事先看到」而不是「壞了才知道」。**
`usage.py` 會去讀憑證檔裡的 `expiresAt`，在**到期前 10 分鐘**就提醒你；
已經過期的 token 它連問都不問 — 因為那一定拿到 `401`，
只是白白花掉五次額度裡的一次，去換一個檔案早就寫著的答案。
它永遠不會去寫、也不會去更新那個 token。

⚠ **提醒自己消失掉是正常的，不是壞掉。**
access token 大約撐 8 小時，而只要有 Claude 在跑，
它會在到期前約 5 分鐘自己換掉。
⭐ **提醒一直不消失才是真的訊號** — 代表沒有任何東西會去換它。
長時間跑的 `--watch` 不需要重開，因為每次撈資料都會重新讀那個檔案。

安裝程式會：

- **絕不覆蓋你原本的狀態列。** 那個位置只放得下一個指令，安靜地佔走等於刪掉你自己放的東西。
  要佔走請用 `install.py --take-statusline`，它會先備份原本的指令。
- 回報 hook 實際會用哪一個 Python — ⚠ **是真的去執行每個候選**，
  因為在 Windows 上 `python3` 會指到微軟商店的假殼，看起來裝好了，執行卻回 49。
- 設定 `statusLine.refreshInterval`，讓數字在對話空檔也會動，不是只有你按下 Enter 才動。

### ⭐ 更新外掛之後，它自己會修好

更新外掛的指令：

```bash
claude plugin marketplace update dispatch-guard          # 先把市集拉到最新
claude plugin update dispatch-guard@dispatch-guard       # 再更新外掛本身
```

⚠ **擴充套件那邊要自己去按更新。** ⚠ 更新完要開一個新 session，外掛在 session 開始時載入。

⭐ **除了上面這兩行，更新之後不用再敲任何指令。** 這一節描述的陷阱會自己修掉。
下一個 session 開始時，gate 會把指向舊版本的狀態列重新指向正在跑的那一份，並告訴你它做了。
打開 `auto_vscode_task` 的話，那個 VS Code 工作也一樣。
⚠ 沒打開的話，工作那一半還是要你重跑一次安裝腳本。

⛔ **但下面這個陷阱本身沒有消失，只是被自動修掉了。** 知道它為什麼存在，才看得懂
`--status` 為什麼要比對兩個路徑：

⛔ **安裝是「複製」，不是「參照」。** 檔案被複製到
`~/.claude/plugins/cache/<市集>/<外掛>/<版本>/`，執行的是**那一份**。
⇒ 改你的工作資料夾**不會有任何效果**，要 `claude plugin update`。
⚠ 而 `update` 是看版本號的，所以改了內容沒改版號它可能偵測不到 —
**開發請用 `claude --plugin-dir <資料夾>`**，那會直接讀你的資料夾、不複製，而且只影響那一個 session。

⚠ **`plugins` 底下有兩個長得很像的目錄，只有一個會被執行。**

| 目錄 | 是什麼 | 有 `.git` | 會被執行 |
|---|---|---|---|
| `~/.claude/plugins/marketplaces/dispatch-guard/` | 市集的 git clone，也就是**來源** | 有 | ⛔ 不會 |
| `~/.claude/plugins/cache/dispatch-guard/dispatch-guard/<版本>/` | 安裝出來的**複本** | 沒有 | ⭐ 會 |

⛔ **所以路徑不要指到 `marketplaces/`。** 它沒有版本號，看起來像個「固定路徑」，很誘人 ——
但 hook 跑的是 `cache/` 那一份。指錯了，狀態列和 hook 就各跑一個不同的版本，
而且沒有任何東西會講。
⭐ **權威的答案在 `~/.claude/plugins/installed_plugins.json` 的 `installPath`**，
而那個檔案自己的路徑是固定的。`/dispatch-guard:status` 的 `install path` 那一行就是讀它比出來的。

⛔ **那個路徑帶著版本號，而 `update` 不會刪掉舊目錄。**
hook 不受影響（`${CLAUDE_PLUGIN_ROOT}` 每個 session 重新展開），
但**狀態列指令**和 **`.vscode/tasks.json`** 存的是字面上的絕對路徑，兩個都拿不到那個變數。
⇒ 更新之後它們會繼續指向**舊版本**，⛔ **而且因為舊目錄還在，它們照樣「能跑」——
只是跑的是舊程式。** 那比壞掉更糟，因為壞掉抓得到。

⭐ **所以 `install.py --status` 會去比對「接上的路徑」和「目前安裝的路徑」**，
不只查存在。更新之後實際印出來長這樣：

```
wired paths         : ⛔ WRONG - and this fails SILENTLY
                      statusline runs a STALE COPY - the path exists, so nothing
                      complains, but it is not the installed version:
                        wired  : …/dispatch-guard/<old version>/hooks/usage.py
                        current: …/dispatch-guard/<installed version>
OVERALL             : ⛔ NOT fully live - see the lines above
```

⇒ **狀態列那一半不用你修** —— 下一個 session 開始時 gate 就把它指回來了。
打開 `auto_vscode_task` 的話，工作那一半也一樣。
⇒ 要手動修就一個斜線指令：`/dispatch-guard:install`。⭐ 不用去找新版本的路徑。

### 3. 裝完之後，還要敲什麼？什麼都不用

⭐ **上面兩行指令是唯一要敲的東西。** 開一個新 session，剩下的自己會發生：

| 事情 | 誰做 | 什麼時候 |
|---|---|---|
| 煞車開始運作 | ⭐ hook | 第一個 session |
| CLI 狀態列出現 | ⭐ hook，只在那個位置**沒人佔**的時候 | 第一個 session |
| `Memory/tasks` 建好 | ⭐ hook | 每個專案第一次 |
| VS Code 工作寫進新專案 | ⭐ hook，⚠ 你答應過一次之後 | 打開專案時 |
| 更新後狀態列指回新版本 | ⭐ hook | 更新後第一個 session |
| 更新後 VS Code 工作指回新版本 | ⭐ hook，⚠ **不需要你答應** | 更新後第一個 session |

⛔ **那個「答應一次」是唯一一次互動，而且它會自己開口問。** 你在 VS Code 裡開一個還沒有
watcher 工作的專案時，開場那一行會叫 Claude 問你要不要以後自動處理。按同意，就結束了 ——
**一台機器問一次，答案是「不要」也一樣不再問**。你不用讀這份文件才知道有這個選項。

⛔ **「修好已經存在的工作」不需要你答應，「建立新的工作」才需要。** 差別在於前者不會往你的
repository 放進任何新東西 —— 那個檔案本來就在，只是指著 `plugin update` 已經走過的版本。
拒絕去修它，只是讓一個已經存在的檔案繼續跑舊程式。

⭐ **狀態列只裝進空的位置。** 已經有人佔著就絕對不碰，不管是誰。要搶還是只能 `--take-statusline`。

⚠ **一個還沒自動化的角落，講明白：** 已經預約的 resume 是一個 OS 排程工作，裡面存著這個版本的
絕對路徑。在它等待的期間更新外掛，它醒來時跑的是舊版的 `resume.py`。舊目錄還在，所以它會跑起來，
只是跑舊程式。⭐ 影響很小（那是一次性的工作），但它是最後一個還會過期的路徑。

### 4. 確認裝好了 — 只有一種方法有效

```
/dispatch-guard:status
```

⛔ **你在畫面上不會看到任何東西，這不是壞掉。**
外掛的「我還活著」訊息來自 `SessionStart` hook，而 hook 的 stdout 是進到 **Claude 的 context**，
不會進到你的終端機。所以「我沒看到」在「完全正常」跟「根本沒跑」兩種情況下長得一模一樣。
`--status` 印的每一行都是一次實際量測：

```
plugin installed    : dispatch-guard@dispatch-guard
plugin enabled      : True
install path        : ...\plugins\cache\dispatch-guard\dispatch-guard\<version>
SessionStart hook   : RAN - 2 session(s) stamped, newest 3 min ago
statusline refresh  : every 60s
usage data file     : ...\.claude\dispatch-guard\token_usage.json
                      last written 1 min ago
usage verdict       : GO - 5h at 43%, 168 min left (resets 14:00)
resume armed        : no (nothing pending, which is the normal state)
OVERALL             : everything is live
```

---

### 5. VS Code + Claude Code 擴充套件的完整流程

⛔ **擴充套件沒辦法顯示狀態列。** 但**這不影響煞車** —— gate 自己 fork 刷新。
⇒ **第 1 步做完就結束了。** 下面第 4 到第 7 步只有在你想**看到**那一行時才需要。

1. 在 VS Code 裡打開你的專案。
2. 開整合終端機（`` Ctrl+` ``），跑第 1 步那兩行外掛安裝指令。⚠ 需要 `claude` CLI 在 PATH 上。
3. **重新載入視窗**，或開一個新的 Claude session。⚠ hook 和斜線指令都在 session 開始時載入。
   ⭐ **到這裡煞車就活了。** 第一次判定會說「還沒有數字」，因為那一刻 fetch 才剛送出去；
   幾秒後就有了。

以下是選配 —— 你想在螢幕上看到用量才做：

4. 在專案目錄裡跑第 2 步那段腳本。已經在 Claude 裡的話，`/dispatch-guard:install` 是同一件事。
5. ⚠ **重新開啟資料夾。** 工作是 `runOn: folderOpen`，所以現在不會起來。
6. ⚠ VS Code 會問 **Allow Automatic Tasks**。**要按同意。**
   ⭐ 先做過第 0 步的話，這一步不會出現 —— 那就是它存在的理由。
7. 一個叫 `Claude Usage Watcher` 的專用終端機會出現，裡面就是那一行用量。

⛔ **第 6 步沒同意，看起來跟「工作寫壞了」一模一樣** —— 兩種情況都是什麼都沒出現、也沒有錯誤訊息。
要分開它們：Terminal → Run Task → `Claude Usage Watcher`。
手動跑得起來，就表示工作本身沒問題，只有自動觸發沒動作。

⭐ **那個 watcher 是「你的」時鐘，不是煞車的。** 狀態列那一半在擴充套件裡永遠不會顯示。
它還是值得裝 —— 只要你也用 CLI，兩邊共用同一個 `token_usage.json`（那是**每個帳號**一份的，
不是每個專案一份）。

---

## 移除

⭐ **兩件事要拆開：** `install.py` 接上去的東西（狀態列、VS Code 工作），和外掛本身（hook、skill）。
前者用 `--uninstall`，後者用 `claude plugin uninstall`。

⭐ 在 Claude session 裡的話，`/dispatch-guard:uninstall` 把下面第 1 步做完，並把剩下的列給你。

### 1. 拆掉 install.py 接上去的兩半

在**每一個**裝過的專案目錄裡跑一次。⭐ 加 `--check` 可以先看，它什麼都不會動。

**Windows（PowerShell）**

```powershell
$p = (Get-Content "$env:USERPROFILE\.claude\plugins\installed_plugins.json" -Raw | ConvertFrom-Json).plugins.'dispatch-guard@dispatch-guard'[0].installPath
& "$p\hooks\run.cmd" "$p\install.py" --all --uninstall
```

**macOS / Linux**

```bash
for c in python3 python py; do command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys" >/dev/null 2>&1 && PY="$c" && break; done
p=$("$PY" -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))['plugins']['dispatch-guard@dispatch-guard'][0]['installPath'])")
sh "$p/hooks/run.sh" "$p/install.py" --all --uninstall
```

它做四件事：

- 移掉 `settings.json` 裡的 `statusLine`（`refreshInterval` 跟著一起走）
- ⭐ 把 `auto_statusline` 和 `auto_vscode_task` 設成 false
- 移掉**這個專案** `.vscode/tasks.json` 裡的 `Claude Usage Watcher`
- ⭐ 取消已經預約的 resume

⛔ **第二項不是多餘的，少了它移除會自己失效。** `auto_statusline` 預設是 true，
所以下一個 session 開始時 hook 會看到空的位置，然後把那一行**裝回去** ——
你還沒讀完移除的輸出，它就回來了。

⚠ **只有你執行它的那個專案會被清掉。** `auto_vscode_task` 打開期間，
每個你用 VS Code 開過的專案都可能有那個工作，而沒有任何地方記著是哪些。
關掉旗標會止血，已經寫出去的檔案要一個一個清。

⛔ **最後那一項不能只寫在文件裡。** 其他殘留只是躺在硬碟上；那一個是會**自己醒來**的
OS 排程工作，而它醒來要跑的腳本可能已經被你刪掉了。一個會自己執行的殘留，
跟一個等著被刪的殘留不是同一件事。

⚠ **`.vscode/tasks.json` 是每個專案一份的**，所以裝過幾個專案就要跑幾次。

### 2. 移除外掛本體

```bash
claude plugin uninstall dispatch-guard@dispatch-guard
claude plugin marketplace remove dispatch-guard
```

⚠ **順序是先第 1 步再第 2 步。** 反過來的話，`--uninstall` 需要的那些檔案已經沒了。

### 3. 它不會替你刪的東西

| 東西 | 在哪裡 | 為什麼留著 |
|---|---|---|
| 用量歷史、設定、session 戳記 | `~/.claude/dispatch-guard/` | 是你的資料。要刪：`Remove-Item -Recurse` 或 `rm -rf` |
| `Memory/tasks/` | 每個專案裡 | 是你的工作紀錄。這支腳本從來不碰它 |
| `task.allowAutomaticTasks` | VS Code **使用者**設定 | 現在可能有別的工作靠它 |
| `.bak-dispatch-guard` | 那個設定檔旁邊 | 那是你原本設定的備份 |
| `statusline-backup.json` | `~/.claude/` 裡 | 只有用過 `--take-statusline` 才會有 |

⚠ **已經開著的那個 `Claude Usage Watcher` 終端機不會自己關。** 重新開啟資料夾，或手動關掉。

---

## 另一個 skill：`unattended-work`

⭐ **這個外掛帶兩個 skill。** `dispatch-protocol` 是**派工的規範**；
`unattended-work` 是**沒有人看著的時候怎麼工作** —— 審查輪次、卡住判定、
什麼時候可以不問就繼續、以及交回工作之前的門檻。

⚠ **兩件事是分開的，故意的。** 一個管「怎麼派」，一個管「怎麼做」。
只想要其中一個也可以：skill 是模型自己決定要不要讀的，不讀就不生效。

### 不想每次 session 都被提醒？

⛔ **外掛的 hook 一定會觸發，這不是設定問題。** 官方文件寫得很明確：
「All declared hooks always fire. Hooks cannot be conditionally enabled/disabled based on
user config.」⇒ 所以能關掉的不是 hook，是它**印什麼**。

安裝時或之後都可以設：

```bash
claude plugin install dispatch-guard@dispatch-guard --config announce_unattended_work=false
```

或直接改 `~/.claude/settings.json` 裡 `pluginConfigs` 底下那個外掛的
`options.announce_unattended_work`。

| 值 | 結果 |
|---|---|
| 沒設、`true`、或任何看不懂的值 | ⭐ 每個 session 開場提醒你載入這個 skill |
| `false`、`0`、`no`、`off` | ⛔ 那個 hook 什麼都不印。skill 還在，你自己叫 |

⛔ **看不懂的值當作「開」，這個方向是刻意的。** 預設是開；一個**安靜消失**的提醒比一個
多餘的提醒糟得多 —— 你會以為規則生效了，實際上根本沒有東西去載入它。

⚠ 關掉之後 `Skill(unattended-work)` 照樣叫得動，只是不會有人提醒你。


## 怎麼看那些數字

⛔ **兩個介面印的不是同一行，所以這裡有兩個例子。**
之前這裡只有一行，而那一行**沒有任何介面印得出來** —— 它同時有 CTx（只有狀態列畫得出來）
和沒有判定字（只有 `--watch` 會印）。

**CLI 狀態列（`--statusline`）**

```
5h ▓▓▓▓┃░░░░░ 43% 2h-47m  7d ▓▓▓▓┃▓▓░░░ 64% 4d-3h-59m  CT ▓▓▓▓░░░░░  41%  Opus 5·high
```

⭐ 有 CT、模型和 effort，因為那三樣來自 Claude Code 餵給狀態列指令的 payload。
⚠ **沒有判定字**（GO/PACE/STOP）：session 開場那一行已經報告過「Usage braking is active (GO)」，
而且判定真正的讀者是 hook，不是眼睛。

**watcher（`--watch`，擴充套件看的就是這個）**

```
12:02:02🟢5h ▓▓▓░░░┃░░░ 34% 1h52m(13:54) 7d ▓▓▓▓┃▓░░░░ 54% 3d22h(Fri 10:00) Fable ▓▓▓░┃░░░░░ 31% 3d22h(Fri 10:00) Burn ▓▓▓▓▓▓▓▓▓▓ .17% 6h36m
```

⭐ **判定字換成圓點，而且它就貼在時間戳記後面、`5h` 前面**（擁有者指定，2026-09-01）：🟢 GO、🟡 WARN、🟠 PACE、🔴 STOP、⚪ 還沒有資料。

⭐ **WARN 是第四個狀態，而且它只有顏色。** 只要五小時長條圖的填滿「超過它自己的 ┃」
—— 也就是你花得比時鐘快 —— 圓點就轉黃，長條圖也轉黃。⛔ **它不會進到 `verdict()`**：
閘門讀的是那個「字」，多一個字會安靜地改變煞車的行為，所以 WARN 只活在畫面這一層。
⚠ 它只會把綠色變黃，永遠不會把真正的 PACE 或 STOP 變軟。
⚠ **那只在畫面上** —— gate 拿到的還是 `GO`/`PACE`/`STOP` 那個字，換掉的話派工邏輯會收到
一個它不認識的值。

⛔ **段落標籤試過改成圖示（🕒 7️⃣ 🚀 🔥），失敗了，所以是文字。**
在擁有者的終端機上，那個 `7️⃣` **什麼都沒畫出來**，`🔥` 變成一個彩色圓點 ——
四段裡有兩段直接失去標籤，而寬度計算還在替它們各留兩欄。
⇒ 一個字型可能沒有的字不是節省，是空白。圓點留著，因為那是幾何符號，字型覆蓋率高得多。

⭐ 有判定字，因為對擴充套件使用者來說**這是唯一看得到用量的地方**，旁邊沒有開場那一行。
⛔ 它畫不出 CT、模型和 effort —— 它只是終端機裡的一個迴圈，沒有任何東西餵 payload 給它。

### `Burn` 那一段：`11h-52m left` 是什麼意思

`Burn` 回答一個問題：**照現在這個速度，我還有多久會撞到 100%。**

```
12:02:02🟢5h ▓▓▓░░░┃░░░ 34% 1h52m(13:54) 7d ▓▓▓▓┃▓░░░░ 54% 3d22h(Fri 10:00) Fable ▓▓▓░┃░░░░░ 31% 3d22h(Fri 10:00) Burn ▓▓▓▓▓▓▓▓▓▓ .17% 6h36m
```

⭐ **The verdict is a coloured dot, and it sits flush between the timestamp and `5h`** (owner-specified, 2026-09-01): 🟢 GO, 🟡 WARN, 🟠 PACE, 🔴 STOP, ⚪ no data yet.

⭐ **WARN is a fourth state and it is colour only.** The dot and the bar turn yellow as soon as
the five-hour bar's fill passes **its own ┃** — you are spending faster than the clock.
⛔ **It never reaches `verdict()`**: the gate acts on the WORD, and a fifth word would silently
change what the brake does, so WARN lives on the display side alone. ⚠ It can only turn a green
dot yellow; it never softens a real PACE or STOP.
⚠ **Display only** — the gate still receives the word `GO`/`PACE`/`STOP`; a symbol reaching
that side would be a value the dispatch logic does not know.

⛔ **Icons were tried for the segment labels (🕒 7️⃣ 🚀 🔥) and failed, which is why they are
text.** On the owner's terminal the keycap seven drew **nothing at all** and the fire came out
as a coloured dot — two of the four segments lost their label while the width counter went on
reserving two columns for each. ⇒ A glyph a font may not have is not a saving, it is a blank.
The dots stay: geometric shapes have far wider font coverage than an emoji.

⛔ **watcher 是「一行」，而那是終端機決定的，不是喜好問題。** 第二行只能靠「把游標往上移」
才有辦法重畫，而 VS Code 的終端機面板**完全不理會任何垂直移動** —— 量了四個版本才確定，
最後把 watcher 寫出去的每一個位元組錄下來:程式送的完全正確,那個面板照樣把三次重畫疊起來。
⇒ 只有 `\r`（回到行首）加 `\033[K`（清掉這一行）是有效的,而那一組只能重畫**一行**。

⚠ **所以時間寫得比較短**（`3d23h`，不是 `3d-23h-16m`）—— 一行上每一欄都在決定
`Burn` 畫不畫得下。整行含 `Burn` 是 **129 欄**。面板窄於這個數字,`Burn` 就會被丟掉。

**怎麼讀：**

| 看到 | 意思 |
|---|---|
| `.13%` | ⚠ **單位是「每分鐘」，不顯示在畫面上。** 最近 **10 分鐘**（`burn_window_min`，預設 10）每分鐘燒掉 0.13% —— 不是整個視窗的平均 |
| `11h-52m left` | 照這個速度，**11 小時 52 分後**會撞到 100% |

⚠ **這個時間可以比「視窗還剩多久」還長，那是正常的。** 上面那行剩 `4h-24m` 就重置，
但燒完要 `11h-52m` ⇒ **你根本花不完，重置會先到。** 這時候 bar 是滿的。

**那條 bar 是「燒完 ÷ 重置」的比值**，⛔ 不是油量：

| 格數 | 意思 |
|---|---|
| `▓▓▓▓▓▓▓▓▓` 滿 | 撐得過重置 —— 額度夠用，不必降速 |
| 一半 | 只撐得到剩餘時間的一半 |
| 很短 | ⛔ 快撞到上限了，要降速或停 |
| 零格 | 額度會在剩餘時間的 5% 內用完 —— 顏色一律紅色 |

⭐ **顏色是「另一個」訊號，跟格數無關**：它講「現在燒得多快」，單位是**時鐘速度的倍數**
（時鐘速度 = 100 ÷ 視窗分鐘數 = 0.333 %/min，也就是「剛好在重置那一刻用完」的速度）。

| 速度 | 顏色 |
|---|---|
| < 1× | 🟢 綠 |
| 1× ~ 1.75× | 🟡 黃 |
| 1.75× ~ 2.25× | 🟠 橘 |
| ≥ 2.25× | 🔴 紅 |

⚠ **兩個訊號會不一致，而且兩個都要讀。** 滿格配紅色 = 燒很兇但視窗才剛開，還有本錢；
短格配綠色 = 已經在龜速了，但還是撐不到。分段可以在 config 用
`burn_x_yellow` / `burn_x_orange` / `burn_x_red` 自己改，
改之前先跑 **`python Tools/Debug/burn_band_fit.py`** 看你自己的歷史算出來是什麼。

⚠ **兩個反直覺的地方：**
- **bar 會往上跑。** 你慢下來它就變長 —— 它量的是「兩個時鐘會不會交叉」，不是還剩多少油。
- **格數滿 = 好，顏色是另一回事。** 這一段的「格數」滿=好；「顏色」則跟旁邊那三條一樣，
  越高越糟 —— 因為它量的是速度，不是餘裕。

⚠ **`🔥────────── --` 代表「還沒有資料」** —— 同一個 5 小時視窗裡至少要兩筆紀錄才算得出速度。
剛裝好、或剛過重置點就是這樣，等幾分鐘就有了。

### ⭐ 沒人在工作的時候，watcher 會停止呼叫 API

⛔ **那個 VS Code 工作綁的是「資料夾有沒有開著」，不是「有沒有 session 活著」。**
所以它以前會整晚打一個大約每 token 只允許**五次**呼叫的端點。

| 情況 | watcher 做什麼 |
|---|---|
| 有 session 在動 | 正常撈，最快每 `fetch_seconds` 一次 |
| 超過 `idle_after_min`（預設 15 分）「沒有任何人在工作的跡象」 | ⭐ **停止撈**，而且從 0.33.0 起**停止重畫** |

⭐ **0.47.0 起「有沒有人在工作」看兩個來源，取比較新的：** gate 自己的 `state/*.alive`，
以及 `~/.claude.json` 的修改時間 —— 後者是 Claude Code 自己寫的，跟我們的 hook 有沒有掛上無關。
⚠ **為什麼**：hook 沒掛上的時候（安裝目錄被刪、更新中斷），第一個訊號會在你還在工作時變平，
watcher 就把它讀成「人走了」。實測 2026-08-30：`.alive` 卡在 1225 分鐘、機器一直在用、
watcher 睡了 20 小時，而 `install.py --status` 全程說一切正常。
⭐ 兩個來源**不一致**時，watcher 會在時鐘旁邊顯示 `HOOK?` —— 有人在工作但我們的 hook 沒在跑。
修法是 `/plugin update` 或重裝，**然後重開**。
| 心跳回來 | ⭐ 立刻恢復，而且只花**一次**呼叫，不補打一串 |

⭐ **0.33.0 起：閒置時只畫一次，然後安靜。** 那一次會把判定字換成 **`SLEEP`**、
**把顏色全部拿掉**，數字**照樣留著**。之後就不再輸出任何東西，直到有人開始工作。

⛔ **為什麼「不重畫」比「繼續重畫」對。** 舊行為每一格都重畫，而那一行有時候比終端機寬 ——
`\r` 只回到**最後一個視覺列**、`\033[K` 只清那一列，於是每一次重繪都把自己的第一列
永遠留在畫面上。整晚下來就是一整面半截的行。⇒ **沒有東西在重繪的行，不可能留下殘骸。**

⚠ **數字為什麼可以留著。** 凍住的數字在「抓取失敗」的時候危險 ——
但**沒有人在工作就沒有人在花**，所以它不會漂移。風險只在恢復工作的那一刻，
而那一刻 watcher 同時就恢復抓取。⭐ `SLEEP` 和「沒有顏色」就是在說這一行不是即時的。

⭐ **資訊太多的時候改用兩列，而不是把東西丟掉。** 用量長條和判定字留在第一列，
Context 長條、模型、說明移到第二列，**兩列各自裁到寬度**。

⭐ **訊號本來就在硬碟上：** gate 每次 hook 事件都會寫 `state/<session-id>.alive`。
⚠ 而 `prune_state()` 是**按數量**留最新的 20 個，不是按年齡刪，所以活著的那個 session
自己的檔案永遠不會被清掉、也就不會被誤判成閒置。

⛔ **`--statusline` 不受這個限制。** 它會被呼叫，本來就是因為有 session 正在互動 ——
在那裡加一個閒置檢查，只會在最該刷新的時候把刷新擋掉。

### 每一段從哪裡來

| 段 | 來源 | 範圍 | `--statusline` | `--watch` |
|---|---|---|---|---|
| `5h` / `7d` | `token_usage.json`（API 撈的） | ⭐ 每個**帳號** | ✅ | ✅ |
| `CT` | payload 的 `context_window` | ⚠ 每個 **session** | ✅ | ⛔ |
| 模型 · effort | payload 的 `model` / `effort` | 每個 session | ✅ | ⛔ |
| 判定字 | 由 `token_usage.json` 算出 | 每個帳號 | ⛔（開場那一行報過） | ✅ |

⭐ **這一條界線解釋了其他每件事：** 為什麼 CT 是每個 session、
為什麼 5h/7d 是每個帳號（所以一台機器跑一個 watcher 就夠），
以及為什麼擴充套件那一行講不出你在用哪個模型。

⭐ **CT 從第一秒就在，讀 0%。** 它以前是開始工作之後才「跳出來」，
那會讓整行寬度變動，而且分不出「這個介面沒有這個東西」跟「這個 session 還沒開始」。
⛔ 但 payload 裡**沒有那個欄位**的時候畫的是 `--`，永遠不是 `0%` ——
把「讀不到」畫成 0% 是一個有自信的錯答案，而且錯在低的那一邊。

⭐ **那個 `┃` 是「時鐘走到哪裡」** — 不是缺一格。
填滿的部分**超過**它，表示你燒得比時間過得快；**落後**它，表示還有餘裕。
單看百分比說不出這件事。
⚠ 它插在兩格**之間**，不是佔掉一格；佔掉一格會讓填滿的比例少一格，
變成長條圖跟數字互相矛盾。

顏色只是提醒，不是政策：綠色 → `colour_warn_pct` 以上轉橘 → `colour_alarm_pct` 以上轉紅。
⭐ **這兩個門檻跟「會拒絕東西」的門檻是對齊的：** 橘色 = `soft_pct_5h` 開始 PACE，
紅色 = `hard_pct_5h` 開始 STOP。所以你瞄一眼的顏色，和 gate 做的決定，不會各說各話。
⚠ **但它們仍然是四個獨立的設定值。** 顏色是給人看的，門檻是拿來拒絕工具呼叫的；
想要顏色比減速更早出現、或乾脆不要顏色的人，不該為此放棄煞車。

### 在 VS Code 擴充套件裡

**擴充套件一樣看得到用量，只是不走狀態列。** 兩邊顯示的地方不同：

| | 用量那一行顯示在哪裡 |
|---|---|
| CLI | ⭐ 狀態列 |
| 擴充套件 | ⭐ 一個終端機 —— `Claude Usage Watcher` 這個工作，或你自己跑的 `usage.py --watch` |

⛔ **擴充套件畫不出狀態列**，這是能力限制，不是設定問題。2.1.246 版實測：
`statusLine` 在擴充套件的 webview bundle 裡出現 **0 次**，
而 `hooks`、`permissions`、`plugins`、`subagent` 都找得到；CLI 執行檔則提到 34 次。
⇒ 所以擴充套件改用終端機顯示，而那個終端機就是那個工作打開的。

⭐ **那個工作怎麼裝，在上面〈2.（選配）狀態列和 watcher〉那一步**，
兩半（狀態列給 CLI、工作給擴充套件）是同一個腳本一起做完的。
打開 `auto_vscode_task` 之後，新專案的那個工作連裝都不用裝 —— 見〈設定〉。

⭐ **煞車兩邊都會動，而且不需要上面任何一樣東西。** gate 自己 fork 刷新。
⇒ 下面這個指令是給**你**看的，不是給煞車用的：

```bash
python hooks/usage.py --watch          # 就一行，原地重寫；--every N 可改頻率
```

⭐ 或讓它自己開：`/dispatch-guard:install`（手動是 `install.py --vscode-task`）會寫一個工作，
在資料夾開啟時自動起一個專用終端機，並順便把需要的權限打開。

⛔ **那個權限一定要放在「使用者」設定裡，這是安全設計，不是怪毛病。**
如果一個 repository 能在自己的 `.vscode/settings.json` 裡設 `task.allowAutomaticTasks`，
那你 clone 任何 repository、一打開資料夾就會幫它執行指令。
⚠ Windows 上這個工作跑的是 `run.cmd`，**不是** `bash run.sh` —
Windows PATH 上的 `bash` 通常指到 WSL 的啟動殼，會回你「沒有安裝任何發行版」。
而且工作型態是 `type: "process"`，**不是** `"shell"`：
在 PowerShell 裡，一行開頭加了引號的路徑會被當成**字串**，不是指令。

---

### 那個 VS Code 工作，可以不用每個專案手動做

⛔ **`.vscode/tasks.json` 是 VS Code 的專案檔，這件事改不了。** `runOn: folderOpen` 只吃工作區範圍，
使用者層級的工作只能是 `shell` 或 `process`，而且文件沒有承諾它會在開資料夾時自動跑。

⇒ 所以有三條路，先看你要的是什麼：

| 你要什麼 | 怎麼做 | 每個專案一次？ |
|---|---|---|
| 煞車會動 | 什麼都不用做 | ⭐ 不用。gate 自己 fork 刷新 |
| 任何一個終端機看得到 | 跑一次 `usage.py --watch` | ⭐ 不用。一台機器一個就夠 |
| 每個 VS Code 視窗自動出現 | 那個工作 | ⭐ 打開 `auto_vscode_task` 之後就不用 |

⭐ **預設就是開的，什麼都不用做。** 在 VS Code 裡打開一個還沒有那個工作的專案，
下一個 session 開始時 hook 就把它寫進去，並在開場那一行說它做了什麼。

⛔ **不問，是因為問過的那條路走不通。** 那句詢問只能進到**模型的 context**，不是印到你的螢幕；
兩次全新安裝實測，工作都沒出現，而且沒有任何東西說明原因。
⇒ 保護改放在**衝突判定**上，不是放在一個把功能藏起來的預設值。

不想要就關掉：

```bash
install.py --enable-auto-task      # 安全地合併寫入，不會動到你其他設定
install.py --disable-auto-task     # 關掉
```

或直接改 `~/.claude/dispatch-guard/config.json`（那個檔案會自動幫你建好）：

```json
{ "dispatch": { "auto_vscode_task": true } }
```

打開之後，SessionStart hook 會在這個專案缺那個工作、或那個工作指向舊版本時，自己寫進去。
⭐ **一台機器設定一次，之後每個專案都自動。**

⭐ **預設是開的。** ⛔ 但它只在**沒有衝突**的時候寫。**建立**一個新的 tasks.json 要這四項全過：

1. `auto_vscode_task` 是 true。
2. **真的在 VS Code 擴充套件裡跑**（看 `CLAUDE_CODE_ENTRYPOINT` 或 `VSCODE_PID`）。
   ⚠ 沒有這一關，一個純 CLI session 就會在從來不用 VS Code 打開的專案裡留下一個 `.vscode/`。
3. 專案目錄真的存在。
4. ⛔ **`.vscode/tasks.json` 沒有被 git 追蹤。** 那個檔案裡是這台機器的絕對路徑，還帶著版本號 ——
   改一個被追蹤的檔案會弄髒工作區，而且那個路徑很可能就這樣被 commit 進去，
   交給下一個人一個指向他沒有的目錄的工作。被追蹤的話它**不寫**，並告訴你原因。

⚠ **但「修好已經存在的那個工作」不受第 1、2 關限制**，這是刻意的。那個檔案本來就在，
而且本來就是我們的，只是指著舊版本；不修它只是讓一個已經存在的檔案繼續跑舊程式，
所以設定關著、也不在 VS Code 裡的時候，一樣會修。
⛔ **第 4 關（git 追蹤）兩種情況都適用。**
⭐ 而且修的時候**不會**去動 VS Code 的 `task.allowAutomaticTasks` —— 那個權限當初給了或沒給，
不該由一次修補悄悄改掉。

⭐ **而且它每次都會講。** 它動了你的專案，卻不說，那是錯的那種貼心 —— 檔案再小都一樣。
⚠ 已經是對的就不會重寫，所以不會每個 session 都動那個檔案。

---

## ⛔ 煞車踩下去的時候，你怎麼知道？

⚠ **這是最容易被含糊帶過的問題。** 一個「勸告」是模型可以跟任務權衡的東西，
而「它繼續工作」跟「它根本沒收到」在螢幕上長得一模一樣。

⇒ 所以有**三個**訊號，強度不同：

| 訊號 | 誰保證 | 證明了什麼 |
|---|---|---|
| ⭐ **`systemMessage`** —— 直接顯示在你的畫面上 | Claude Code | **hook 真的跑了，而且判定是什麼**。模型吞不掉它 |
| ⛔ **工具呼叫被拒絕** | hook | **那次派工沒有發生**。這是唯一「強制」的東西 |
| ⚠ **agent 回覆的確認行** | 模型自己 | 它**收到了**。⛔ 不證明它照做 |

### 你會看到的東西

到達 PACE（預設 85%）或 STOP（預設 93%）時，畫面上會出現：

```
dispatch-guard: usage PACE at 90%. Dispatch is still allowed; scope should shrink.
Expect the agent to acknowledge with `PACE at 90% - winding down`;
if that line does not appear, it did not act on it.
```

⇒ **然後看 agent 的下一則訊息第一行**。它被要求原封不動印出：

```
PACE at 90% - winding down
```

⚠ **沒有那一行 = 它沒有處理這件事。** 那時候你可以直接接手，不用猜。
⭐ 它也可以印 `- NOT winding down` 並說明理由 —— 那是**不同的**故障，處理方式也不同：
「收到但選擇繼續」跟「從來沒收到」要修的地方不一樣。

派工在 STOP 被拒絕時，畫面上會出現：

```
dispatch-guard: sub-task dispatch REFUSED - usage STOP at 95%.
Nothing was dispatched. The agent has been told to save the current step and arm a resume.
```

⭐ **這一句是硬證據。** 那次工具呼叫真的沒有發生 —— 不是模型「決定不派」。

### 那則訊息什麼時候出現，會不會一直重複

| | |
|---|---|
| **哪個事件** | `UserPromptSubmit` —— ⭐ **你送出訊息的那一刻**。不是背景計時器 |
| **依據什麼** | `token_usage.json` 裡的百分比，由 `verdict()` 換算成 GO / PACE / STOP |
| **會重複嗎** | ⛔ **不會。** 每個 session、每個等級只送一次 |

⭐ **不重複的做法是把「已經送過哪一級」寫到硬碟上**：
`~/.claude/dispatch-guard/state/<session-id>.warned` 裡面就是 `PACE` 或 `STOP` 那個字。
下一次送出訊息時，如果算出來的等級跟檔案裡一樣，hook 就直接結束，什麼都不印。

⇒ 所以一次長時間的執行會聽到**最多兩次**：跨過 `soft_pct_5h` 一次，跨過 `hard_pct_5h`t` 再一次。

⚠ **等級變了就會重新武裝**，包括往回走。用量視窗重置之後回到 GO，之後再爬到 PACE，
你會再收到一次 —— 因為那是新的一輪，不是同一輪的重複。

⛔ **這個記錄是「每個 session」的。** 開一個新 session，同樣的等級會再說一次 ——
刻意如此：新 session 的模型沒有前一個 session 的 context，沒被告知過。

⚠ 那個計時器只在**你送出訊息**時走。⭐ 但**派工被拒絕**不受這個限制：
那是 `PreToolUse`，每一次派工都判定，而且每一次都會拒絕。

### ⚠ 兩個門檻，分別在哪裡

| 門檻 | 預設 | 行為 | 長條顏色 |
|---|---|---|---|
| `soft_pct_5h` | **70** | **PACE** —— 縮小範圍，派工**仍然允許** | 橘（`colour_warn_pct` 70） |
| `hard_pct_5h` | **85** | **STOP** —— 派工**被拒絕** | 紅（`colour_alarm_pct` 85） |
| `soft_pct_7d` | **95** | **PACE**，由「七天」視窗觸發 | —— |
| `hard_pct_7d` | **97** | **STOP**，由「七天」視窗觸發 | —— |

⛔ **0.34.0 以前煞車完全不看 7d。** 它只讀五小時的百分比，所以 **7d 99% 配 5h 0% 會被判成 GO**，
然後一直派工到「伺服器」拒絕為止 —— 兩個數字都是真的，答案是錯的。
⇒ 現在**兩個視窗取比較嚴的那個**，而且判定會講出是哪一個在管。
⚠ 7d 那一對故意設得高：那個視窗通常不是限制，在 70% 就 PACE 會白白拖慢一整週。
⚠ 而且如果 7d 在「目前這個 5h 視窗結束之前」就會重置，它會被**完全忽略** ——
它的百分比馬上就要歸零。

⇒ **85% 就是 STOP，派工會被拒絕。** ⚠ 這個值從 90 降下來，是因為 90 還在派工，結果撞到 session limit 被強制終止。想更早或更晚，改
`~/.claude/dispatch-guard/config.json`：

```json
{ "soft_pct_5h": 60, "hard_pct_5h": 85 }
```

⚠ 只寫你要改的那幾個。⛔ 寫進去的值會被**釘住**，以後版本改了預設值也到不了你這裡 ——
`install.py --status` 的 `pinned settings` 那一行會告訴你自己釘了什麼。

⚠ 也可以查 `.claude/dispatch_gate.log`，`USAGE(PACE) pct=90` 和 `DENY(usage-stop pct=95)`
都留在那裡 —— ⛔ 但那證明的是 **gate 說了什麼**，不是 agent 做了什麼。

---

## ⛔ 不要開 ultracode

⚠ **ultracode 跟這個外掛正面衝突，而且是每一輪都在浪費 token。**

`/effort` 對 ultracode 的說明是：**xhigh effort ＋ 動態 workflow 編排**。
而一個 workflow 就其構造而言會**一次生出很多 agent** —— ⛔ 這個 gate **直接拒絕 Workflow**，
也拒絕第二個同時進行的子任務。

⇒ 所以每一輪都是這樣：ultracode 先叫 agent 規劃一個 workflow，agent 讀完、想完、去呼叫，
然後**被拒絕**。那些規劃的 token 完全白花，而且是每一輪。

| effort | 跟這個外掛 |
|---|---|
| `max` | ⭐ **建議** —— 一樣深的推理，沒有 workflow 編排 |
| `ultracode` | ⛔ 每一輪都在為一個一定會被拒絕的東西做規劃 |

### ⛔ 開著就「每一個」工具呼叫都被拒絕

⚠ **不是提醒一次而已 —— 是完全停下來。** `max` 或更低才能繼續。

⭐ effort 出現在 `PreToolUse` 的 payload 裡（執行檔裡的 schema 寫的：tool-use context 的
hook 拿得到，session 生命週期的 hook 拿不到），而 `PreToolUse` 也正好是唯一能拒絕呼叫的地方。
所以 gate 在**每一次**工具呼叫上都看得見、也都拒絕：Read、Bash、Edit、Agent，全部。

⛔ **agent 這邊沒有任何繞路** —— 拒絕的理由直接告訴它：不要換一個工具試，
把這件事講出來然後結束這一輪。⭐ **只有人能跑 `/effort`。**

第一次拒絕時，你的畫面上會出現：

```
dispatch-guard: ultracode is ON and it fights this plugin. It asks for dynamic
workflows, which the gate refuses outright - so the planning is wasted every turn.
Run /effort and pick `max` instead: same depth, no workflow orchestration.
```

⚠ **拒絕會一直重複，畫面訊息只出現一次。** 拒絕每一次都送到**模型**那裡 ——
那才是「規則」而不是「建議」；而每一次都跳一則畫面訊息會把螢幕淹掉，所以人只被告知一次。

⭐ **為什麼從「警告一次」升級成「一律拒絕」：** ultracode 不是「建議」一個 workflow，
它**每一輪都重新下達那個指令**。所以只警告一次的 session，會在剩下的時間裡持續為一個
一定會被拒絕的東西燒規劃 token。⇒ `max` 或以下可以繼續，ultracode 不行。

---

## 從腳本裡查用量

```bash
python hooks/usage.py --verdict          # GO / PACE / STOP / NO-DATA
python hooks/usage.py --verdict --json   # 給程式讀的格式
```

離開碼就是結論 — `0 GO`、`1 PACE`、`2 STOP`、`3 NO-DATA` — 腳本不用剖析文字就能分支。

⛔ **請依「那個字」行動，不要依百分比。**
在重置前 `near_reset_min` 分鐘內，門檻會**故意**放寬，
因為在那個時間點撞到上限的代價只是等幾分鐘，不是把做到一半的工作賠掉。
結論還處理了三件單看數字會判斷錯的事：重置時間的計算、週用量的假警報、以及燒完速度的推估。

---

## 用量重置後自動續跑

```bash
python hooks/resume.py --arm --task <task 資料夾>   # --dry-run 只看不做
python hooks/resume.py --status
python hooks/resume.py --cancel
```

有兩條路，拒絕派遣的時候兩條都會告訴你：

- ⭐ **叫醒還活著的 session** — 只要它還活著就選這個，因為 context 都還在，工作直接接下去。
  ⭐ **兩種 harness 都實測過**（2026-08-26）：一次性的 CronCreate 工作在 VS Code 擴充套件裡
  隔 **32 分鐘**觸發、在 CLI 裡隔 **33 分鐘**觸發，兩邊醒來都還講得出之前在做什麼。
  ⇒ 那個 **10 分鐘上限是「指令」的上限，管不到這條路** — 所以不要用背景 `sleep` 代替。
  ⚠ **但那個工作跟 session 同生共死**：它只在記憶體裡、不寫硬碟。所以「session 沒活下來」
  不是讓這條路失敗，是讓它**不存在**，而且不會留下任何痕跡讓你發現。兩條都預約就是為了這個。
  ⚠ **而它不是比較省的那條**，這是最容易誤讀的地方。留住 session 留不住 token：
  需要 resume 的等待一定比 prompt cache 活得久，所以醒來後的第一個請求會把整段對話
  重送一次、全額計費（實測 `cache_read` 是 **0**）。它買到的是**正確性**，不是比較少的帳單。
- **作業系統的一次性排程**（`schtasks` / `at`） — 這是 session **沒活下來**時唯一有效的路，
  ⚠ **而讓 session 死掉的，常常正是你在等的那個上限。**
  不需要系統管理員權限：在非提權帳號實測過，`schtasks` 建立、列出、刪除都沒跳任何提示。
  ⛔ **但它撐不過登出。** 2026-08-26 實測：`schtasks /Create` 沒帶 `/RU` / `/IT` 建出來的工作，
  Logon Mode 是 **`Interactive only`** — 只在使用者互動登入時執行。
  關終端機、關編輯器沒問題；**登出或切換使用者就不會觸發**。

⭐ **兩條同時預約是安全的。** hook 會替每個 session 蓋一個心跳戳記，
排程醒來時若發現 30 分鐘內有任何 session 活動過就自己退場，所以工作不會做兩次。

### ⭐ 提前恢復作業時，鬧鐘會自己被殺掉

⛔ **排定的時間隨時可能失去意義，而換帳號只是其中一個成因。**
重置本身就可能提前，於是開發人員在鬧鐘預定時間的**好幾個小時前**就拿回額度、
自己把工作接下去做完、然後離開。
那個鬧鐘完全不知道這件事。它會在舊的時間醒來、發現沒有人在活動（因為人做完就走了）、
然後**重做一份已經做完的工作** — 花掉一份新的額度換到一個複製品。

⭐ **所以取消的時機是「工作恢復的那一刻」，不是「鬧鐘響的那一刻」。**
gate 在 `SessionStart` 和 `UserPromptSubmit` 檢查：如果有一個**還沒到期**的鬧鐘、
而且判定顯示視窗已經有額度了 → **直接把它殺掉**，並且把這件事講給 session 聽。

⛔ **判定表就是整個安全論證：**

| 判定 | 動作 | 為什麼 |
|---|---|---|
| **STOP** | **保留** | 等待還在進行中，鬧鐘正是為此存在。⭐ 這也是為什麼剛預約完不會馬上被取消 —— STOP 時派工會被拒絕，所以預約的那一刻 STOP 必然還是真的 |
| **NO-DATA** | **保留** | 我們**不知道**視窗有沒有重開。⛔ 絕不能因為「不知道」就丟掉備援 |
| **GO / PACE** | **取消** | 有**量到的**餘裕，工作現在就能在這個 session 帶著 context 繼續。鬧鐘沒有事情可做了 |

⭐ **route A 的喚醒也會走到這裡** — cron 喚醒是以 `UserPromptSubmit` 抵達的 —
所以偏好的那條路一旦真的生效，備援就會在那一刻退場，而不是等到自己響。

⚠ **取消失敗也會講出來**，並且叫使用者自己跑 `--cancel`：一個安靜失敗的取消，
等於留著一個會重做工作的鬧鐘。

### ⚠ 等待期間換了帳號會發生什麼事

⭐ **煞車會自己好，不用做任何事。** `usage.py` 每一次都重讀憑證檔，
所以下一次撈資料就是新帳號的數字，`token_usage.json` 被覆寫，gate 立刻不再拒絕 — 有額度就是 GO。

⭐ **而且活著的 session 直接繼續就好。** 換帳號是人的動作，所以人就在鍵盤前，
不需要等任何鬧鐘。

⛔ **唯一過期的東西是作業系統那個鬧鐘的「時間」。** 它是照**舊帳號**的重置時刻排的，
而那個時刻對新帳號沒有任何意義。

⛔ **所以換帳號之後自己把工作接下去，請跑 `resume.py --cancel`。**
不取消的話會撞到這個情況：鬧鐘在舊帳號的重置時刻觸發、發現 30 分鐘內沒有 session 活動
（因為你做完就走了）、去問新帳號的判定得到 GO，
然後 **headless 重做一份你已經做完的工作**。
這個限制本來就存在（它分不出「活著在做這件事」和「活著在做別的事」），
但換帳號會讓它從罕見變成很可能。

⭐ **`--status` 會告訴你鬧鐘過期了：**

```
reset     : ⛔ STALE - armed for 22:18 but the stored reset is now 00:18,
            and the armed one has NOT passed yet.
            The usual cause is a DIFFERENT ACCOUNT signed in during the wait.
```

⚠ **這個判斷只在「排定的重置時刻還沒到」的時候做。** 過了之後那個值本來就會合法地往前走
（狀態列每 120～150 秒撈一次），那時候比對會在一切正常的時候發警報。

⛔ **沒有辦法直接認出帳號。** 2026-08-26 實測：`~/.claude/.credentials.json` 和用量端點
**兩邊都不帶任何帳號識別資訊** — 只有 token、`scopes`、方案類型和數字。
所以這裡刻意不做帳號指紋：唯一的候選是雜湊 refresh token，那是雜湊一個秘密；
而 `subscriptionType` + `rateLimitTier` 擋得住「換方案」、擋不住「同方案換帳號」，
一個半套的偵測比沒有更危險。**「重置時刻在它該到之前就變了」是唯一站得住的訊號。**

⛔ **它會拒絕內容太空的交接檔** — 少於約 200 個字元的實質內容就退回，
因為醒來卻沒東西可讀的續跑，只是花掉一份額度換到零產出。

⛔ **它不會因為「醒過來了」就把自己刪掉。**
用量可能其實還沒重置，執行也可能因為網路、憑證或 `PATH` 而失敗。
它會先驗證、再執行，**只有乾淨結束才**移除排程；
其他情況會一路重試到 `retry_window_min` 用完，然後徹底停手，
並留下一個標記**讓下一個 Claude session 主動唸出來**。

---

## 設定

⛔ **`config.json` 不會被建立，一個字都不會寫。** 安裝腳本不建，hook 也不建。
沒有這個檔案，就表示每一個設定都跟隨外掛的預設值 —— 包括以後版本改掉的新預設值。

⭐ **要改哪一個，就自己建 `~/.claude/dispatch-guard/config.json`，裡面只寫那一個 key。**
其他設定繼續跟隨預設。想知道有哪些 key、預設值是什麼，看外掛裡的 `config.example.json` ——
每一個 key 都在，而且旁邊有中英文說明。路徑不確定就跑 `python install.py --status`，
它會印出狀態目錄。

⛔ **為什麼不幫你建。** 寫在那個檔案裡的值會被**釘住**：以後版本改了預設值，你收不到。
⚠ **這不是理論，是實測到的。** 0.9.0 到 0.11.0 之間種子檔照抄範例（含所有值），於是
`auto_vscode_task` 改預設之後，所有先前安裝的機器都還是舊的 —— 更新了、預設變了、什麼都沒發生，
花了兩次重裝才找出原因。後來改成「只種說明、不種值」，釘住的問題解決了，卻留下一個 55 KB、
解釋了每一個設定卻一個值都看不到的檔案。**不建立**兩個問題都沒有。

⛔ **已經存在的 `config.json` 絕對不會被覆蓋。** 它從存在的那一刻起就是你的。
⭐ **想看自己釘住了什麼、以及哪些已經跟不上新預設值：`install.py --status` 的
`pinned settings` 那一行** —— 它會逐一列出跟目前預設值不一樣的鍵，包括被改名的舊鍵。

想換掉整個狀態目錄，用 `--dir <路徑>` 或環境變數 `$CLAUDE_DISPATCH_DIR`。
專案也可以自己帶一份 `<repo>/.claude/dispatch-guard.json`，它對 `dispatch.*` 那組設定有最終決定權。

⭐ **不確定檔案在哪，就跑 `python install.py --status`，看 `log files` 那一行** —— 它會印出解析後的絕對路徑、資料夾建了沒、裡面幾個檔案多大、保留幾天，並且在 `$CLAUDE_DISPATCH_DIR` 把 hooks 移到別處時警告你（`install.py` 不認那個變數，hooks 認）。

**保留幾天**（`history_keep_days`，預設 **30**）。`history_dir` 裡超過這個天數的檔案會被整個刪掉。
⭐ **設 0 就永久保留** —— 那是這個鍵存在之前的行為。
⚠ **`null` 不是「永久」** —— `null` 的意思是「用預設值」，跟 `history_dir` 的 `null` 一樣，所以它跟
不寫這個鍵一樣會在 30 天時刪。要永久保留只有 `0`。
⛔ **只刪整個檔案，而且只刪這個外掛「目前會寫」的那兩個名字** —— `token_usage_history_*.jsonl` 和
`API_response_usage_*.jsonl`。單一檔案永遠不會被砍掉前半段，因為那會留下一份「看起來完整、其實不是」的
紀錄。`history_dir` 可以指到放著別人檔案的資料夾，所以全面清掃是不做的。
⚠ 讀不成正數的值（一個詞、空字串、`true`、負數）一律當成「全部保留」，不會退回 30 天然後開始刪。
清理最多每個 process 一天一次，就在新的一天要開檔案的那一刻。

**保留每一次 API 回應**（`debug.API_response_usage`，預設關閉）。打開之後，usage 端點每一次的
回應都會**完整**存進 `history_dir`，檔名 `API_response_usage_<YYYYMMDD-HHMMSS>.jsonl`，一行一筆，
每個本地日一個檔：

```json
["<organizationUuid>", "<accountUuid>", "2026-08-27T09:45:00+00:00", { "…整個回應…": true }]
```

⭐ **它存在的理由是「現在用不到的欄位，就是以後那個問題要的欄位」。** 目前的解析只取兩個百分比，
其餘全部丟掉；`nimbus_quill` 和 `seven_day_opus` 看起來毫無價值，直到它們變成證據。

⚠ **最多約每天 1.2–1.4 MB。** 實測：一行 2006 位元組（回應本體 1887）；`fetch_seconds` 為 120、
`fetch_seconds_jitter` 為 30 時平均間隔 135 秒，一天約 640 次，而 720 次是完全沒有 jitter 的上限。
持續工作一整天才會到這個量，閒置時 `idle_after_min` 會讓 watcher 停止要數字。這是診斷開關 —— 問完
你要問的問題就關回 `false`。
⛔ **位置 1 是 `null` 代表這一列無法歸屬到任何座位**，做統計時必須**排除**，不能當一般資料平均進去。
⚠ 條件不只一兩種，所以記規則而不是清單：**座位確認不了就寫 null** —— `~/.claude.json` 讀不到、裡面
沒有 `oauthAccount` 或 `accountUuid`、它的組織 ID 和憑證檔不一致（換帳號之後兩個檔案不同步），或
token 來自 `$ANTHROPIC_TOKEN`。位置 0 是 `null` 則代表憑證檔裡沒有 `organizationUuid`，而那時候位置
1 也一定是 null：沒有東西可以拿來對照。
⚠ `organizationUuid` 認的是**組織**，不是座位。同一個組織裡的多個座位共用同一個值。
⚠ **並行寫入會掉行。** 實測：四個 process 同時 append，240 行裡掉了 14 到 26 行（約 6–11%）；兩個
process 同時寫也會掉。沒有例外、沒有損壞、沒有任何跡象。token-usage 歷史檔是同樣的機制。
⛔ 「只開一個 session 就不會掉」是錯的 —— `dispatch_gate.py` 自己會另外跑 `usage.py`，所以一個
session 也可能同時有兩個寫入者。要保證一行都不漏，這個檔案格式目前做不到。
⭐ 陣列寫法也接受：`"debug": ["API_response_usage"]` 等同 `{"API_response_usage": true}`。
⚠ `"debug": true` 不會打開任何開關 —— 它會關掉全部，並在 stderr 說明原因。

**Token 用量歷史**（`debug.token_usage`，⭐ **預設開啟**）會寫到 `history_dir` —
預設是 **`~/.claude/dispatch-guard/logs/`**（狀態目錄下的 `logs/` 資料夾）— 檔名是
`token_usage_history_<YYYYMMDD-HHMMSS>.jsonl`，每個本地日一個檔，**單一檔案永遠不會被裁切**：
⛔ **只有一個名字，沒有別的。** 這個開關曾經叫 `keep_history`、也曾經叫 `token_usage_history`；
兩個都**不再被讀**，舊檔名的檔案也不再被讀取或清理。⚠ 所以一份還寫著舊名字的 config 拿到的是
**預設值**，不是他寫的那個值 —— `install.py --status` 會把每一個已廢棄的鍵點名出來，
那是**被忽略的設定**唯一會現身的地方。⭐ 從舊版更新的人請跑 `Tools/clean-dispatch-guard.ps1` 再重裝。
⭐ **為什麼改成預設開**：燃燒率推估需要同一個視窗的兩個樣本，所以在此之前，PACE 裡「照這個速度到重置前會用完」那一半，對沒有手動開啟的人從來沒有運作過。**實測：一行 132 位元組、一天大約 640 次讀數，所以大約一天 82 KB**，`history_keep_days` 保留的 30 天合計 2.4 MB —— 而且那是上限，因為只有數字真的動了才會寫一行。

```json
{"at": "2026-08-26 13:29:31", "pct": 74.0, "resets_at": "2026-08-26 14:09:31",
 "sd_pct": 68.0, "sd_resets": "2026-08-30 17:29:31", "model": "Opus 5", "session": "oooooooo",
 "acct": "aaaaaaaa-0000-4000-8000-00000000000a"}
```

---

## 檔案與行程 — 哪一支程式做什麼，以及為什麼還需要檔案

⭐ **這一節是對照著實際問到的問題寫的**：哪一支去打 API、哪一支是 `--watch`、
能不能全部走記憶體、`state/` 和 `fetch.claim` 是幹什麼的。

### 只有一支程式，幾個入口

| 做什麼 | 檔案 | 函式 |
|---|---|---|
| 打 API 拿用量 | `hooks/usage.py` | `fetch()` |
| `--watch` 持續顯示 | **同一支** `hooks/usage.py` | `watch()` |
| `--statusline` 渲染一行 | 同上 | `collect()` |
| 判定 GO / PACE / STOP | 同上 | `verdict()` |

所以 `usage.py --watch` 是**一個行程**同時負責去撈和顯示。它們之間本來就在記憶體裡。

### ⛔ 跨行程那一段不能用記憶體，這是架構不是偷懶

**真正需要那個數字的是 hook，而 hook 每次都是新生的行程。**
`hooks/hooks.json` 把它宣告成 `"type": "command"`，`PreToolUse` 的 matcher 是 `*` —
也就是 Claude Code **每一次工具呼叫都重新開一個行程**跑 `dispatch_gate.py`，毫秒後就死。

```
usage.py --watch        ← 長期活著
      ↓ 寫 token_usage.json
dispatch_gate.py        ← 每次工具呼叫都是新行程，跟上面沒有共用記憶體
      ↓ 讀 token_usage.json
```

⚠ **而且讀者不只一個**：好幾個 watcher、狀態列、每次派工的 gate，
全都靠那一個檔案協調「誰該去打 API」和「這個數字多舊了」。記憶體做不到。

### ⭐ 行程內部已經改成記憶體傳遞

`ensure_fresh()` 會**直接回傳資料**，呼叫的人不用再去讀一次剛剛讀過的檔案。實測每個 tick：

| | 改前 | 改後 |
|---|---|---|
| 耗時 | 6.5 ms | **2.3 ms** |
| 開檔案 | 5 次 | **3 次** |
| └ `token_usage.json` | 3 次 | **1 次** |

剩下兩次是真的每次都要的：歷史檔（算燃燒速率）、憑證檔（查 token 到期）。

⚠ `verdict()` 有一個選用的 `data` 參數，**只給這個檔案裡面的呼叫者用**。
外面的呼叫者一定要省略它 — 這個函式的重點就是它自己去讀存好的紀錄，
讓外人餵資料進來等於讓外人餵**錯的**資料進來。`dispatch_gate.py` 刻意不傳。

### `fetch.claim` — 兩個工作，第二個更重要

1. **防止同時重複打 API。** 好幾個行程共用 `token_usage.json`，
   兩個 watcher 同時撞到「該刷新了」的邊界會**兩個都去打**，
   五次額度裡一口氣花掉兩次。這個檔案在**發出請求之前**先蓋章，晚到的看到就放棄。
2. ⭐ **它是唯一的退避機制。** 走到這個檢查，代表 `token_usage.json` 不新鮮 —
   也就是最近那次嘗試**失敗了**。所以失敗後**故意不清掉**它，
   讓後面一個間隔內沒人重試。拿到 429 一直重打只會更慘。

⚠ 它是 mtime 時鐘，不是真的互斥鎖。兩個行程撞到同一瞬間還是會打兩次；
代價是浪費一次呼叫，有上限而且很少見。真正的鎖要處理死掉的持有者和崩潰時釋放，
為了偶爾省一次請求不值得。`fetch.log` 出現成對的 429 才需要升級。

### `state/` — 裡面是什麼，以及為什麼兩種檔案的清理規則不一樣

| 檔名 | 內容 | 幹什麼 |
|---|---|---|
| `<session>.start` | 一個時間戳 | ⛔ **決定這個 session 要不要被強制執行** |
| `<session>.alive` | 一個時間戳 | 證明 hook 真的在跑；排程續跑用它判斷「有沒有 session 還活著」。⭐ `--watch` 也讀它來決定要不要暫停撈資料 |
| `<session>.slotN` | 派工佔位 | 控制同時幾個 sub-task。**有自己的分鐘級回收規則** |

⛔ **它以前從來不清，會無限長大** — 一天普通的工作就 63 個檔案。現在會清，
**但兩種規則不一樣，而那個不對稱正是重點**：

- ⭐ **`.alive` 按「數量」清，留最新的 20 個。其實 1 個就夠。**
  它只被讀「最新那一個」，其他的只是 `install.py --status` 上面的一個計數。
- ⛔ **`.start` 只按「時間」清，永遠不按數量。** 它不是資料，是**開關**。
  `session_start()` 回傳 `None` 會讓 gate 走進「只警告不阻止」那條路 —
  所以刪掉一個**還在跑**的 session 的 `.start`，等於**安靜地把它的煞車關掉**。
  ⚠ 而且沒辦法判斷它是不是還活著：一個開著但**閒置**的 session 不會觸發任何 hook，
  所以它什麼都不會更新，看起來跟死掉的一模一樣。
  ⇒ 所以那七天是**安全邊際，不是有用期限**。檔案在 session 結束的那一刻就沒用了，
  邊際存在的原因是我們不知道那一刻是什麼時候。
  **如果哪天真的要縮短，該改的是那個 fail-open，不是邊際。**
- ⚠ **`.slotN` 完全不動。** 那是活的狀態，誤刪一個還被持有的位子會讓它發兩次。

### ⭐ 為什麼不改成「一個 session 一個資料夾」

會問這個很合理，答案是三點：

1. **沒有衝突可以避免。** 檔名裡本來就是 session id
   （`state_path()` 只保留英數、`-`、`_`，UUID 完全不會被改動），所以兩個 session 撞不到。
2. **改成資料夾不會變少。** 一個 session 一個資料夾，就是把幾千個小檔案換成幾千個空資料夾，
   在 Windows 上還更貴。要處理的是清理規則，不是排列方式。
3. ⚠ **兩個檔案不能合成一個。** `.start` 的 mtime **就是** session 的開始時間，
   絕對不能被重寫；`.alive` 則是每個 hook 都要蓋一次。
   它們的寫入時機正好相反 — 這就是為什麼是兩個檔案，不是疏忽。

### ⛔ 那 `~/.claude/session-env/<session-id>/` 呢？答案是不要，理由跟「誰來清」無關

**這個想法很合理，而且它的核心論點是對的** — 這些檔案的壽命**就是** session 的壽命，
所以把它們放在一起才符合語意。它也**真的可以寫**
（Claude Code 自己就在裡面放 `sessionstart-hook-*.sh`），所以權限不是問題。

⚠ **有一個常被拿出來反對的理由，但它站不住腳，先把它排除掉：**
「那個目錄自己也不清」 — 2026-08-26 實測，763 個資料夾，最舊的是一個月前。
這是事實，但它**不是**反對的理由：把兩個小檔案加進一個本來就會存在的目錄，
並沒有讓情況變糟。

⭐ **真正的理由是另外兩個，而且第一個是：那個問題已經修好了。**
`.alive` 按數量清、`.start` 按時間清 — 這個目錄現在是**有界的**。
所以「搬過去可以解決成長問題」已經不是好處了，因為沒有東西還需要被解決。
搬過去剩下的唯一收益是**語意上的整齊**。

⛔ **而它的代價是：去依賴「某一個客戶端、某一個版本的、未公開的內部目錄結構」，
而且是用猜的方式拼出那個路徑 — 為了那個「不見了就會安靜關掉煞車」的檔案。**

⭐ **這一包外掛即將被發佈給陌生人安裝，所以有一個問題可以直接分出勝負：**
在一台 `~/.claude/session-env/` **不存在**、或結構不一樣的機器上，gate 會怎麼做？
雲端 session、`--bare` 模式、未來某一版把它改名、或者完全不是 Claude Code 的環境。

⇒ 唯一的答案是「退回去用 `state/`」。而那就代表**同一個 fail-open 開關有兩個位置**，
每一次讀取都必須兩個地方都查 —
否則一個 session 在兩次執行之間「換了位置」，就會被讀成「沒有標記」而退成只警告。

⇒ ⛔ **所以搬過去並沒有消掉清理問題，而是在「唯一不能不見的那個檔案」上，
多出第二個要去找的地方。** 這是把一個有界的問題，換成一個更難推理的問題。

⭐ **如果哪天 Claude Code 開始清理那個目錄，並且在 hook 的 payload 裡把路徑交給我們，
這就變成正確答案** — 那時候它就不是猜的，而且退路也不必存在。
在那之前，`state/` 是我們自己的、有界的、而且沒有第二個地方要找。

⚠ **真的要搬的話，有一個附帶條件不能省：把那個 fail-open 變吵。**
現在 `.start` 不見只會在沒人看的 log 裡留下一行 `ADVISORY(no-session-stamp)`。
一旦那個檔案住在我們不擁有的目錄裡，這條路徑就變得更可能發生，
那一行就必須變成 session 會**講出來**的話。

## ⛔ 它做不到的事

信任它之前請先讀這段。以下每一條，都是「它看起來在運作、其實沒有」的一種方式。

- ⛔ **核准檔不是一道牆。** 代理隨時可以自己寫一個 `PARALLEL-APPROVED`，而且真的發生過 —
  它被拒絕兩次之後，自己寫了一個檔案、引用 owner 的原話當作核准，然後就過了。
  這個檔案買到的是：這個動作是**刻意**的、它**會過期**、而且用了會留下**一行紀錄**，
  上面有它的年齡跟內容。
- ⛔ **背景派遣沒辦法計數，只能拒絕。**
  `PostToolUse` 是在工具呼叫**回傳**時觸發，而背景派遣是一啟動就回傳，
  而且它真正結束時沒有任何 hook 會觸發。
  ⇒ 已核准的並行是**一批 N 個**跑完再下一批，不是滑動視窗。
- ⛔ **它壞掉時是「放行」。** 一個因為自己當掉就拒絕所有東西的守門員，比它要守的規則更糟。
  ⚠ 代價是：**沒有出現拒絕，不等於它有在跑。**
  請看 `<repo>/.claude/dispatch_gate.log` —
  整份都是 `ADVISORY(no-session-stamp)` 表示它**什麼都沒在管**，
  而這跟「大家都乖乖守規矩」的紀錄長得一模一樣。
- ⚠ **只用擴充套件，煞車照樣有數據。**
  擴充套件確實從不呼叫狀態列，但 gate 會自己 fork 一個背景刷新，所以 `hard_pct_5h`ct` 有數字可以比。
  ⚠ 第一次判定仍然可能是「還沒有數字」—— 那一刻 fetch 才剛送出去。⛔ 但如果**每個** session
  都這樣說，那就是 fetch 一直失敗，不是還沒回來：跑 `usage.py --fetch-now` 看原因。
- ⛔ **只有「還可能是真的」的百分比才會顯示。**
  沒資料、資料比 `stale_min` 還舊、以及視窗其實已經翻頁了，三種情況都顯示 `--`。
  往低估的方向錯是危險的那一邊：一個凍住的低數字，會在最該踩煞車的時候把煞車鬆開。
- ⛔ **檔案很新，不代表數字很新。** 每個 session 都有自己的用量快取，
  所以可能一個回報 97%、另一個連續半小時回報 74%。
  存進去的時間戳只在數字有變的時候才更新，所以檔案的年齡就是「這個數字多舊」的意思 —
  但這裡沒有任何東西能讓 Claude Code 自己的那份值變得更新。
- ⛔ **skill 要求真的可能鎖死一個 session。** 如果 skill 註冊本身壞了，
  那個 session 就完全不能派工。⭐ 這就是 `require_dispatch_protocol: false` 的用途，
  而它屬於**你**：
  拒絕訊息刻意**不會**告訴 agent 那個鍵，因為一條會講出自己關閉開關的規則，
  就是一條會被關掉的規則。⚠ 正常情況下它鎖不死任何東西 ——
  叫一支 skill 就是一次 agent 做得到的工具呼叫，而開場那一行會先指名這兩支。
- ⚠ **gate 分不出「叫過」和「照做了」。** 它記錄的是 `Skill` 這個工具呼叫。
  agent 之後有沒有真的遵守那支 skill，從 hook 是看不出來的 ——
  `unattended-work` 自己那行 `ACTIVE` 才是答案的另外一半。
- ⚠ **模型上限只看得到「明寫在 `tool_input.model` 裡」的那個值。**
  寫在 agent 定義檔 frontmatter 裡的 model、或某個 `subagent_type` 的預設 model，
  hook 看不到。`subagent_type: "fork"` 永遠繼承主控的模型，上限拉不下來。
- ⚠ **沒有寫 model 的派工會繼承「這個 session 的模型」，那是什麼就是什麼。**
  這是刻意的 —— 那是你自己選的模型。⛔ 但這也表示：你把 session 開在 Fable 上，
  子代理就會繼承 Fable，而上限管不到。要它有效，就把 session 本身開在上限以下。
- ⭐ **上限會被 Claude Code 自己的 `availableModels` 允許清單收窄。**
  一個只能用 sonnet 的帳號，它的 `opus` 上限就是 sonnet 上限，
  而拒絕訊息會直接這樣寫、並且從「真的選得到」的那些模型裡面挑一個建議給你。
  ⛔ 但「不在允許清單裡」本身不會被拒絕：那種情況 Claude Code 是**安靜地替換**
  （換成同家族裡最新的、或是直接繼承主控的），而每一種替換都是成本往**下**走 ——
  成本守衛在那裡沒有東西要保護，硬要拒絕只會誤殺合法的派工。
- ⭐ **規則寫在 skill 裡，不是只在派工那一刻才擋。**
  `dispatch-protocol` 帶著那張價格表和 `max_model_price`，所以 agent 在「選擇之前」就讀到 ——
  ⛔ 一條 agent 只在被拒絕時才遇到的規則，就是一條它會想辦法繞過的規則。
  gate 注入到每一層子任務提示詞的區塊裡也有同一條（第 7 條）。
  ⚠ 兩份表可能分岔，所以有一項檢查會斷言 skill 那四列跟程式的判斷函式一致。
- ⭐ **那些數字是已公布的資料，不是我編的。** 它是出貨的模型目錄裡每一筆的
  `pricing` 欄位：`tier_<輸入>_<輸出>`，每百萬 token 美元。
  ⛔ **是「每個模型」計價，不是「每個家族」**，因為一個家族不是一個價格：
  `claude-opus-4-0` 是 $15、`claude-opus-5` 是 $5，同一個家族差三倍。
  ⛔ 而「認不出來的模型」是拒絕不是放行。⚠ 家族認得、版本沒見過的（例如
  `claude-opus-6`）會用家族計價，而那個假設會記一行 `MODEL-PRICE-ASSUMED`。
- ⚠ **`[1m]` 後綴被去掉，沒有另外計價。** 目錄一個模型只公布一個 `pricing`，
  沒有為長 context 變體公布第二個；harness 自己的帳也只是把「長 context 的那次請求」
  丟進另一個桶子（`longCtxCost`），沒有把價格乘上任何倍數。
  ⇒ 沒有可用的公布數字，所以這裡不編一個出來。
- ⛔ **指令守衛讀的是一個字串，不是一個真正解析過的 shell。** 引號裡的運算子、
  heredoc 內文裡出現的 `git commit` 字樣，都可能誤判。⭐ 誤判會在
  `.claude/dispatch_gate.log` 裡留下它拒絕了哪一行，而且每一條守衛都可以單獨關掉。
- ⚠ **`git commit -a` / `-am` 也會把所有已追蹤的修改掃進去，但 add-all 那條守衛看不到。**
  `-am` 會被 `-m` 那條擋下；單獨的 `-a` 完全沒擋。
- ⚠ **分支守衛比的是「payload 的 cwd 解析出來的那一個 checkout」。**
  `git -C <另一個 repo> commit` 會拿這個 repo 的分支去比。
- ⚠ **分支守衛可以靠「切換共用工作目錄」滿足。** 這是刻意的 ——
  這個 session 自己選的分支就是合法的，而每一次切換都會記一行 `BRANCH-RECORDED`。
- ⚠ **相對路徑的 `cd` 只警告，永遠不拒絕。**
  shell 的工作目錄在兩次工具呼叫之間會延續，而 hook payload 不帶那個值，
  所以 gate 沒辦法知道那個相對路徑會被解析到哪裡去。⛔ 不知道就不該拒絕。
- **計畫檢查看的是時間戳，不是內容。** 它擋得住「忘記寫」，擋不住「故意騙」。
- **它是以 session 為單位的。** 同一個工作目錄下的兩個 session 不會互相擋 —
  請給每個 session 自己的 `git worktree`。
- ⛔ **喚醒原本的 session 那條路，永遠只能「提醒」，不可能強制。**
  `CronCreate` 是 agent 的工具，Python hook 叫不到它 — 所以 `resume.py --arm` 只能在成功之後
  印一行叫你去設它。⚠ **只設了作業系統那個鬧鐘**、又有人在 30 分鐘內碰過 session，
  鬧鐘會以為另一條在處理而自己退場 — **兩個都不會響。**
- ⛔ **「提前恢復就殺掉鬧鐘」只掛在 `SessionStart` 和 `UserPromptSubmit`。**
  一個只被 `PreToolUse` 喚醒的 session 不會觸發那個檢查，鬧鐘會留到下一次使用者輸入才被殺。
- ⛔ **`NO-DATA` 會保留鬧鐘。** 不知道視窗有沒有重開，就不能丟掉備援 —
  所以沒有用量資料的機器永遠不會自動取消。用 `usage.py --fetch-now` 確認，或把狀態列裝起來。
- ⚠ **完整的鏈路從來沒有被一次跑完過。** 每一段都單獨量過，端到端也跑過個別 hook；
  但「真的撞到 STOP → 兩條都預約 → 視窗重開 → 鬧鐘被取消 → 工作繼續」
  需要把額度真的燒到 `hard_pct_5h`，所以沒有被刻意製造過一次。
- **外掛啟用之前就開始的 session 只有建議效力。**
  這是刻意的：去管它等於為了一個它根本無從得知需要存在的計畫檔而拒絕派遣。

---

## 致謝

用量的那一半改寫自 **[claude-pacer](https://github.com/drpwchen/claude-pacer)** —
它的重置時間計算、週用量假警報規則、燒完速度推估、接近重置的豁免、
等比長條圖與時間標記，全部用 Python 重寫，
好讓這個外掛不需要 Node 相依。
它的響應式分層、寬度偵測與主題顯示則刻意沒有搬過來：
那是那個專案比較大的一半，而其中沒有任何一項會影響「要不要派遣」這個決定。

⭐ 那個專案的一個陷阱，這裡是**堵住**而不是照抄：
它的狀態列只要不是 `--demo` 呼叫就會寫入永久檔，
所以餵它假資料會把真資料蓋掉。
這裡如果送進來的內容不含用量，就什麼都不寫，而且會明講。

## 授權

MIT。


---

<!-- ================= ENGLISH VERSION BELOW / 以下為英文版 ================= -->

> 🇹🇼 **正體中文版在本檔案的上半段** — 往上捲即可。
> 🇬🇧 **English version follows.** The Traditional Chinese version is the first half of this
> same file; scroll up for it.

# dispatch-guard (English)

A Claude Code plugin that makes sub-agent dispatch discipline **binding instead of advisory**,
and refuses to dispatch once the usage window is nearly spent.

**Standard-library Python only.** No `pip install`, no `npm install`, nothing to vendor — the
only non-stdlib import in it is one of its own files.

Copy it anywhere. The one project-shaped thing inside is where task folders go: ⭐ it is
declared as **`Memory/tasks`** under the project's working directory, and the gate **creates it
at session start**, so an agent never has to choose a location. That is the `task_root` setting.

---

## Why a hook and not a skill

A skill is selected by the model from its description; a document is read at the model's
discretion. **Both are advice.** Measured: a sub-agent *can* read `CLAUDE.md` and *can* invoke a
skill, so this was never a capability problem — it is that nothing removed the choice.

⭐ **A hook removes the choice.** It fires on every tool call, in every session, at every depth —
a sub-agent's own dispatches hit the same hook — and it can refuse the call outright.

⭐ **And the brake sits on the DISPATCH, not on an injected message.** Dispatching a sub-agent is
the most expensive thing an agent does: the sub-agent reads its own context, and its report is
read back into the parent. An injected *"please wind down"* is advice the model weighs against
its task. **A refused tool call is not.**

---

## What it does

| | |
|---|---|
| ⛔ refuses a **second concurrent** sub-task | unless the owner approved a count |
| ⛔ refuses a **background** dispatch | it escapes the accounting entirely — see the gaps below |
| ⛔ refuses a dispatch made **before the plan is on disk** | the plan and every sub-task prompt land first |
| ⛔ refuses a **mass-spawn** tool call | no approval path |
| ⭐ refuses a dispatch once usage reaches the **hard threshold** | and warns the sub-task at the soft one |
| ⭐ **prepends the protocol to every sub-task prompt** | at every depth, without the dispatcher doing anything |
| ⭐ **appends every dispatch's outcome to `progress.md`** | so a later session can tell finished work from work that only looks finished |
| ⭐ **ships the `unattended-work` skill** | how to work with nobody watching. Its reminder can be switched off |
| ⭐ **arms a one-shot resume** for after the window reopens | survives closing the terminal, the editor and the session. ⚠ NOT a logoff — see below |

⭐ **A second family: commands that fail SILENTLY** — where the wrong outcome and the right
one are byte-identical on screen. Each has its own switch; all default to on.

| | |
|---|---|
| ⛔ refuses a `git commit` on a **branch this session did not select** | it means another session moved the shared working tree under you |
| ⛔ refuses `git add -A` / `.` / `--all` | stage the paths you changed, by name |
| ⛔ refuses `git commit -m` | write the message to a file and use `-F <path>` |
| ⛔ refuses a search with **its errors silenced** | `2>/dev/null`, `2>$null`, `--no-messages`, and `-s` for grep |
| ⛔ **refuses every dispatch until `dispatch-protocol` has been invoked** | `require_dispatch_protocol` — that skill is what the gate enforces |
| ⭐ refuses the **first** dispatch when `unattended-work` was never invoked | a nag, not a gate. `require_unattended_work` makes it a gate |
| ⚠ warns on `cd <relative> && …` | when the `cd` fails, everything after it silently does not run |
| ⚠ reports unpushed commits older than the one just made | advisory, never a refusal |
| ⚠ a sub-agent returned, but **the file its prompt demanded never appeared** | `guard_agent_report_file`. The summary still comes back and still looks normal; a missing file does not |
| ⚠ a **read-only `subagent_type`** paired with a prompt that tells it to create a file | same switch, warned before it runs. ⭐ An unknown type says nothing at all |
| ⛔ refuses a sub-agent whose model **costs too much** | `max_model_price`, default **5** ($/M input tokens) |

⛔ **Every one of these exists because the rule was already written down, read, and broken
anyway.** Four were broken in ONE session on 2026-08-27, two of them by the agent that had
WRITTEN them that morning. The sharpest: the rule said "check which branch you are on before
every commit", and the agent DID run the command — chained as `git rev-parse --abbrev-ref HEAD
&& git add -A && git commit …`. ⛔ `&&` asks only whether the previous command **succeeded**,
never whether its answer was **acceptable**. The branch name printed, scrolled past, and the
commit landed on another session's branch.

⭐ **There is one live copy of the rules:
[skills/dispatch-protocol/SKILL.md](skills/dispatch-protocol/SKILL.md)** (with a Chinese
reading copy beside it). **[PROTOCOL.md](PROTOCOL.md)** holds the mechanics around them: file
conventions, what the hook actually enforces, the honest gaps, and how resume works.
⭐ **This document describes the present only.** When something changed, and why, is in
**[CHANGELOG.md](CHANGELOG.md)**.

⭐ **To verify the repository: `python Tools/Debug/test_all.py`.** It runs all eleven checks
and returns one exit code. ⚠ Each exists for a bug that actually happened AND was silent — none is
there for coverage. They touch no `~/.claude`, spend no API call, and schedule no task.
⭐ **Every file they produce goes under `Tools/Debug/scratch/`** — gitignored, and kept after
the run so a failing check's output is still there. ⛔ A run must leave `git status` clean;
that is itself the check that the tests stayed inside their sandbox.

⭐ **`python Tools/Debug/burn_band_fit.py` — is the Burn gauge's colour still calibrated?**
It reads the `burn_x_yellow` / `burn_x_orange` / `burn_x_red` edges **you are actually
running**, replays your own history through the product's own rate calculation, and reports
what share of live time each colour holds, with a verdict: red falling to 0% or rising past
about 15% means the bands need re-fitting. ⚠ It reads a copy of the history, spends no API
call, and changes nothing. ⛔ It ships here rather than in the task folder that chose the
bands because "when should this be reconsidered?" has to be a command somebody can run, and
a task folder is archived as a unit. `--dir` points it at another state directory.

---

## Install

⭐ **Two routes, pick one, both are complete.** This section is steps only; why each step looks
the way it does is in the **reference** below — read it if you want it.

### ⚡ A. One paste (fastest, nothing to think about)

⛔ **Run it BEFORE opening VS Code.** Why is in the reference, under "**⚠ Reopen VS Code after
installing, and it asks you once**".

**Windows (PowerShell)**

```powershell
claude plugin marketplace add Dino9021/dispatch-guard
claude plugin install dispatch-guard@dispatch-guard
$p = (Get-Content "$env:USERPROFILE\.claude\plugins\installed_plugins.json" -Raw | ConvertFrom-Json).plugins.'dispatch-guard@dispatch-guard'[0].installPath
if (-not $p) { throw "dispatch-guard is not installed" }
& "$p\hooks\run.cmd" "$p\install.py" --all
& "$p\hooks\run.cmd" "$p\install.py" --status
```

**macOS / Linux**

```bash
claude plugin marketplace add Dino9021/dispatch-guard
claude plugin install dispatch-guard@dispatch-guard
for c in python3 python py; do command -v "$c" >/dev/null && PY="$c" && break; done
p=$("$PY" -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))['plugins']['dispatch-guard@dispatch-guard'][0]['installPath'])")
[ -n "$p" ] || { echo "dispatch-guard is not installed"; exit 1; }
sh "$p/hooks/run.sh" "$p/install.py" --all
sh "$p/hooks/run.sh" "$p/install.py" --status
```

⭐ **That does all four things**: the plugin, the CLI statusline, VS Code's
`Claude Usage Watcher` task, and VS Code's `task.allowAutomaticTasks` — so the notification you
have to catch never appears. The last line is the check: `OVERALL` says live and you are done.

⚠ Then **open a NEW Claude session** (a plugin's hooks load at session start), **then** VS Code.

> Detail in the reference: **1. The plugin — hooks and the skill**, **2. (Optional) The statusline
> and the watcher**, **4. Check it took**.

### 🖱 B. Through the menus, step by step

⚠ **Only step 1 has no menu** — the plugin installs from the CLI. Everything after it is clicks.

| # | Where | What |
|---|---|---|
| 1 | a terminal | `claude plugin marketplace add Dino9021/dispatch-guard`, then `claude plugin install dispatch-guard@dispatch-guard` |
| 2 | Claude (new session) | type `/dispatch-guard:install` — ⭐ it shows a dry run and asks before touching anything |
| 3 | Claude | type `/dispatch-guard:status` to check |
| 4 | VS Code | `Ctrl+Shift+P` → `Tasks: Manage Automatic Tasks` → `Allow Automatic Tasks` (step 2 usually set it already; this is the belt) |
| 5 | VS Code | reopen the folder. Nothing there? `Terminal` → `Run Task` → `Claude Usage Watcher` |

> Detail in the reference: **0. If you use VS Code, do this first**, **1. The plugin — hooks and
> the skill**, **2. (Optional) The statusline and the watcher**, **⚠ Reopen VS Code after
> installing, and it asks you once**, **4. Check it took**.

---

## Reference — what each of those steps does

### 0. If you use VS Code, do this first — the rest goes much smoother

⭐ **Once per machine, covering every project.** Setting it up front means the install is never
interrupted by a notification you have to catch: it fades on its own, and missing it leaves the
task written and visible under `Run Task` but **never starting when you open a folder** — ⛔ with
no error message anywhere.

| route | how |
|---|---|
| ⭐ command palette | `Ctrl+Shift+P` → **`Tasks: Manage Automatic Tasks`** → pick **`Allow Automatic Tasks`** |
| edit the setting | `Ctrl+Shift+P` → `Preferences: Open User Settings (JSON)`, then add `"task.allowAutomaticTasks": "on"` |

```jsonc
// %APPDATA%\Code\User\settings.json
// macOS: ~/Library/Application Support/Code/User/settings.json
// Linux: ~/.config/Code/User/settings.json
{
  "task.allowAutomaticTasks": "on"
}
```

⚠ **VS Code ships with `"off"`**, so no automatic task runs until you or the install script
changes it. The key takes `"on"` and `"off"` and nothing else.
⚠ **It is a USER-level setting**, not one per project — once covers everything.
⚠ It is not specific to this plugin either: other projects' automatic tasks become allowed too.
⛔ **And tasks do not run in an untrusted workspace** whatever this is set to — that is VS Code's
own wording. Trust the folder as well.

⭐ **Skipping it is fine.** Step 2's script sets it to `on` anyway; doing it first only means you
never see the notification. Leave it and you will meet the prompt on the next VS Code restart —
see "⚠ Reopen VS Code after installing and it asks you once", below.

### 1. The plugin — hooks and the skill

```bash
claude plugin marketplace add Dino9021/dispatch-guard
claude plugin install dispatch-guard@dispatch-guard
```

⭐ **This repository is both the marketplace and the plugin it lists**, so those two lines are
the whole of it. ⚠ `marketplace.json` **must** sit at the repository root — that is the only
place `marketplace add` looks.

A local directory works as a marketplace too, and `--plugin-dir` skips the copy entirely:

```bash
claude plugin marketplace add /path/to/dispatch-guard   # no GitHub needed
claude --plugin-dir /path/to/dispatch-guard             # development; this session only
```

⚠ **A plugin's hooks load at SESSION START.** Open a new session before expecting anything.

⛔ **Needs Claude Code 2.0.56 or later.** Earlier builds do not know the `PostToolUseFailure`
event, and one hook on an event a build does not know silences **every** hook of that plugin —
nothing is enforced, and nothing says so (measured 2026-09-02 on 2.0.30 / 2.0.55 / 2.0.56).
`python install.py --status` (which is what `/dispatch-guard:status` runs) reads
`claude --version` and warns when it is older; with no `claude` on PATH it says "unknown"
rather than pretending OK.

> ⛔ **On an older version? Read the advisory at the top of
> [CHANGELOG.md](CHANGELOG.md) first.** Several releases enforced nothing at all, silently,
> because of one hook exception.

### 2. (Optional) The statusline and the watcher — paste it, it finds its own path

⭐ **The brake does not need this step.** The gate forks its own refresh, so the
brake is live once step 1 is done. This step puts the usage line on YOUR screen.

⭐ **No path to fill in, and nothing has to run it for you.** Both scripts below read
`installPath` out of `~/.claude/plugins/installed_plugins.json`, so the version number is not
your problem. ⛔ **Run it from your project directory** — `.vscode/tasks.json` is a per-project file, so
where you run the script from is which project gets the watcher.

**Windows (PowerShell)**

```powershell
$p = (Get-Content "$env:USERPROFILE\.claude\plugins\installed_plugins.json" -Raw | ConvertFrom-Json).plugins.'dispatch-guard@dispatch-guard'[0].installPath
if (-not $p) { throw "dispatch-guard is not installed - run: claude plugin install dispatch-guard@dispatch-guard" }
& "$p\hooks\run.cmd" "$p\install.py" --all
```

**macOS / Linux**

```bash
for c in python3 python py; do command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys" >/dev/null 2>&1 && PY="$c" && break; done
p=$("$PY" -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))['plugins']['dispatch-guard@dispatch-guard'][0]['installPath'])")
[ -n "$p" ] || { echo "dispatch-guard is not installed - run: claude plugin install dispatch-guard@dispatch-guard"; exit 1; }
sh "$p/hooks/run.sh" "$p/install.py" --all
```

⭐ **It does both halves, because the two environments show usage in different places:**

| | What this script installs | Where it goes |
|---|---|---|
| CLI | the statusline | `~/.claude/settings.json` — ⭐ once per account |
| VS Code extension | the `Claude Usage Watcher` task | ⭐ VS Code's **user-level** `tasks.json` — once, covering **every** project |

⛔ **Nothing is written into your repository.** Earlier versions used a per-project
`.vscode/tasks.json`, which can never work on a FIRST open: the file is created by a session,
and a session starts after the folder is already open — so the first open of every NEW project
missed it.

⚠ **The first open after installing is a race, and it can be won or lost.** The user-level
file is written by a session, and a session starts *after* the window is up. When VS Code
finds no automatic task it waits a further **10 seconds** for `onDidChangeTaskConfig` —
⭐ **a file written inside those 10 seconds does run.** Measured 2026-08-29: the log reads
`taskNames=[]` and then `updated taskNames=["Claude Usage Watcher"]`.
⛔ **Past that it gives up for the whole window, and says nothing.**

⇒ That is why one machine "just works after installing" and another does not. ⭐ **Both were
measured, from an identical starting state** — `tasks.json` read `(no such file)` before the
first open on BOTH, which rules out Settings Sync and workspace trust alike:

| | window opened | hook wrote the task file | gap | outcome |
|---|---|---|---|---|
| the one that works | `08:59:19` | `08:59:41` | **22 s** | ✅ started by itself |
| the one that does not | `08:43:20` | `08:43:55` | **35 s** | ⛔ nothing |

⇒ Thirteen seconds of session-start time is the whole difference. ⚠ That gap is not the 10s
threshold itself — VS Code counts its 10 seconds from the moment *it* starts looking for
tasks, and extensions delay that moment too.

⭐ **To win it every time, run the install script from a terminal BEFORE opening VS Code**
(step 2 below, or `/dispatch-guard:install` from inside Claude). With the file already there
no race is run. ⚠ After that first time the file stays, so **no project and no later open
ever meets this again.**

### ⚠ Reopen VS Code after installing, and it asks you once

⭐ **This is the one click, and it happens once.** After you reopen the folder, VS Code shows
this in the bottom right:

> **Notifications**
> This workspace has tasks (Claude Usage Watcher) defined () that can launch processes
> automatically when you open this workspace. Do you want to allow automatic tasks to run in
> all trusted workspaces?
>
> **[ Allow ]** [ Disallow ] [ Open Files ]

⇒ **Press `Allow`.** It is VS Code's own safety gate: ⛔ without it the task is installed and
Run Task lists it, but it NEVER starts on folder open — and nothing says why.

⚠ **That notification fades by itself.** Missing it costs nothing; any of these work:

| Route | How |
|---|---|
| get the notification back | the **bell icon** at the bottom right, or `Notifications: Show Notifications` |
| make the decision directly | `Ctrl+Shift+P` → `Tasks: Manage Automatic Tasks` → pick `Allow Automatic Tasks` |
| see where it is stored | `"task.allowAutomaticTasks": "on"` in `%APPDATA%\Code\User\settings.json` |

⭐ **The installer sets that value to `on` itself**, so most of the time the notification never
appears. ⚠ But if that settings file cannot be read at install time — something VS Code
tolerates and a JSON parser does not — it refuses to edit it and says so, and then you get the
notification above.

### ⭐ `claude plugin update` repairs the stored path by itself

The task holds an ABSOLUTE path, and the cache path carries the version number. ⛔ `update`
moves the directory and LEAVES THE OLD ONE, so a stale path keeps working and keeps running old
code.

⇒ **Nothing has to be re-run.** At the next session start the gate compares what is STORED
against what is RUNNING, rewrites it when they differ, and says so in the opening line.
⚠ Measured: a stored path pointed at a fake older version was rewritten on the next call.

⭐ The detail, with the measurement behind it, is in "In the VS Code extension" below.

⚠ **Reopen the folder** for the watcher task to start; it is `runOn: folderOpen`.
⛔ It also switches on `task.allowAutomaticTasks` in **user** settings (that permission is
honoured only at user scope — a security property, see below), backing the file up as
`.bak-dispatch-guard` first.

Want the statusline only? Drop the `--all`.
⭐ `--check` is honoured by both halves, so `--all --check` writes nothing — look before you leap.

⛔ **Windows goes through `run.cmd`, Unix through `run.sh`, and that `for` loop EXECUTES each
candidate.** Neither detail is padding. On a Windows PATH `python3` is the Microsoft Store alias
stub: `command -v` succeeds and running it exits 49. `bash` is usually the WSL launcher. Testing
only whether a command resolves buys you a confident wrong answer.

<details>
<summary>⭐ Already inside a Claude session? Two slash commands do the same thing</summary>

| Slash command | What it does |
|---|---|
| `/dispatch-guard:install` | The above. Dry run first, then it asks |
| `/dispatch-guard:status` | Is it live right now? Read-only. ⭐ Prints `install path` too |
| `/dispatch-guard:uninstall` | The reverse. Dry run first, then it asks |

⭐ They spell the path `${CLAUDE_PLUGIN_ROOT}`, which Claude Code expands, and re-expands every
session. ⚠ Slash commands load at session start, like hooks, so open a new session after
installing. If they are not there at all, the copy is too old: `claude plugin update`.

</details>

### The statusline is optional now — and why it was not

```bash
python install.py --check    # see what it would do and change nothing
```

⭐ **`usage.py` fetches its own numbers** — `GET https://api.anthropic.com/api/oauth/usage`
with the OAuth token already on disk — so the statusline was never the *source*.

⭐ **The clock is the gate, not the statusline.** When the numbers go stale the dispatch gate
forks its own refresh, on a hook event it was running anyway.

⛔ **And that is not the synchronous fetch-in-a-hook that was rejected.** A blocking HTTP call
would stall every dispatch that crossed the interval boundary. This forks and returns; the
number lands for a LATER call to read. A dispatch never waits on the network.

⇒ **So the statusline and `--watch` are display, not life support.** Install them to put the
line in front of a human.

⚠ **The API is asked at most once every `fetch_seconds` (default 120) plus a random
`fetch_seconds_jitter` (default 30, `0` disables it).** Both are config keys; the real wait is
120–150 s out of the box. The jitter is always **added, never subtracted** — a negative value is
refused with a line saying so — so the wait can never dip below the floor. It exists because several sessions' status lines all tick on the same 60 s refresh and
would otherwise drift into lockstep and hit the interval boundary together — which is exactly the
burst that spends the budget.

⛔ **The floor is enforced in code, not advisory** — a smaller value is clamped and says so.
⚠ **The floor is 120 s, the same number as the default** — a config asking for less is clamped
**up** to 120. It was lowered to 60 on 2026-08-29 only to make the following claim measurable, and
⛔ **the experiment ended on 2026-08-31: a 60 s poll drew three `429`s in ten minutes (08:42:59,
08:47:30, 08:52:01), so the floor went back to 120.** The two measurements together are the
answer: 120 s gave at least 26 successful calls in 100 minutes with no `429`; 60 s gave a `429`
within minutes. The real limit is neither "five" nor absent — it lies between those intervals and
is still unknown. The endpoint is documented as allowing about **five calls per
access token**
([onWatch](https://github.com/onllm-dev/onwatch), whose own default poll is 120 s while it watches
ten providers), and exhausting it returns a persistent `429`
([issue #31021](https://github.com/anthropics/claude-code/issues/31021), closed as not planned)
which leaves the brake blind during exactly the heavy run it exists to govern.

⛔ **`--verdict` never fetches.** It runs inside the dispatch hook on every dispatch, and a
synchronous HTTP call there would stall the dispatch whenever the interval boundary is crossed.
What does fetch: `--statusline`, `--watch`, and the `--fetch-now` the gate forks when the numbers
go stale.

⭐ **No statusline and no `--watch` running? The brake still works.** The dispatch gate forks
its own refresh when the numbers go stale — see "The statusline is optional now" above. Those two
are how a PERSON sees the line; neither is what keeps it fresh.

⭐ **The token is watched, not discovered to be dead.** `usage.py` reads `expiresAt` out of the
credentials file and warns **10 minutes before** the token expires; a token already past its expiry
is not asked about at all, because a `401` would spend one of the five calls to learn what the file
already said. It never writes or refreshes that token.

⚠ **A warning that vanishes on its own is the normal case.** An access token lasts about **8 hours**
and whichever Claude client is running rotates it roughly 5 minutes before expiry. ⭐ **A warning
that persists is the real signal** — nothing is running that will refresh it. A long-running
`--watch` survives a rotation with no restart, because the file is re-read on every fetch.

The installer:

- **never clobbers an existing statusline.** The slot holds exactly one command, so taking it
  silently would remove whatever you deliberately put there. Take it with
  `install.py --take-statusline`; the previous command is backed up first.
- reports which Python the hooks will actually use — ⚠ **by running each candidate**, because on
  Windows `python3` resolves to a Microsoft Store stub that looks installed and exits 49.
- sets `statusLine.refreshInterval`, so the numbers move between turns as well as on them.

### ⭐ After a plugin update, it repairs itself

To update the plugin:

```bash
claude plugin marketplace update dispatch-guard          # refresh the marketplace first
claude plugin update dispatch-guard@dispatch-guard       # then the plugin itself
```

⚠ **The extension updates itself through its own update button.** ⚠ Open a new session
afterwards; a plugin loads at session start.

⭐ **Beyond those two lines, an update needs nothing typed.** The trap below repairs itself. At the
next session start the gate re-points a statusline aimed at an older version at the copy that
is running, and says that it did. With `auto_vscode_task` on, the VS Code task does the same.
⚠ Without that setting, the task half still needs one run of the install script.

⛔ **The trap has not gone away, it is only repaired now.** It is worth understanding, because
it is why `--status` compares two paths rather than checking that one exists:

⛔ **Installing COPIES; it does not reference.** The files are copied to
`~/.claude/plugins/cache/<marketplace>/<plugin>/<VERSION>/`, and **that copy** is what runs. ⇒
Editing your working folder changes nothing until `claude plugin update`. ⚠ And update keys off
the version number, so a content change without a version bump may go undetected — **for
development use `claude --plugin-dir <folder>`**, which reads your folder directly, copies
nothing, and affects only that session.

⚠ **Two look-alike directories live under `plugins`, and only one of them ever runs.**

| Directory | What it is | Has `.git` | Ever runs |
|---|---|---|---|
| `~/.claude/plugins/marketplaces/dispatch-guard/` | the marketplace's git clone — the **source** | yes | ⛔ no |
| `~/.claude/plugins/cache/dispatch-guard/dispatch-guard/<version>/` | the installed **copy** | no | ⭐ yes |

⛔ **So never point a path at `marketplaces/`.** It carries no version number, which makes it
look like the fixed path everybody wants — but the hooks run the `cache/` copy. Wire the wrong
one and the statusline and the hooks run two different versions, with nothing to say so.
⭐ **The authoritative answer is `installPath` in `~/.claude/plugins/installed_plugins.json`**,
and *that* file's own path is fixed. The `install path` line from `/dispatch-guard:status` is
that record, compared against the copy actually running.

⛔ **That path carries the version, and `update` leaves the OLD directory in place.** Hooks are
immune — `${CLAUDE_PLUGIN_ROOT}` is re-expanded every session — but the **statusline command**
and **`.vscode/tasks.json`** hold literal absolute paths and neither file gets that variable. ⇒
After an update they keep pointing at the **previous version**, and ⛔ **because the old
directory is still there they keep WORKING — running old code.** That is worse than breaking,
because breaking is detectable.

⭐ **So `install.py --status` compares the wired path against the CURRENT install path**, not
merely against existence. After an update it prints:

```
wired paths         : ⛔ WRONG - and this fails SILENTLY
                      statusline runs a STALE COPY - the path exists, so nothing
                      complains, but it is not the installed version:
                        wired  : …/dispatch-guard/<old version>/hooks/usage.py
                        current: …/dispatch-guard/<installed version>
OVERALL             : ⛔ NOT fully live - see the lines above
```

⇒ **The statusline half needs no fixing from you** — the gate re-points it at the next
session start, and the task half too when `auto_vscode_task` is on.
⇒ To repair it by hand it is one slash command: `/dispatch-guard:install`. ⭐ There is no new
path to find.

### 3. What is left to type after installing? Nothing

⭐ **Those two commands are the only thing you type.** Open a new session and the rest happens
by itself:

| Thing | Who does it | When |
|---|---|---|
| the brake starts working | ⭐ the hook | first session |
| the CLI statusline appears | ⭐ the hook, only into an **empty** slot | first session |
| `Memory/tasks` is created | ⭐ the hook | first time in each project |
| the VS Code task lands in a new project | ⭐ the hook, ⚠ once you have agreed once | when you open it |
| after an update, the statusline points at the new version | ⭐ the hook | first session after |
| after an update, the VS Code task points at the new version | ⭐ the hook, ⚠ **no agreement needed** | first session after |

⛔ **That one agreement is the only interaction, and it asks for itself.** Open a project in VS
Code that has no watcher task and the opening line tells Claude to ask whether you want this
handled automatically from now on. Say yes and it is done — **asked once per machine, and "no"
is remembered just as firmly**. You do not have to read this document to find the option.

⛔ **Repairing a task that exists needs no agreement; creating one does.** The difference is
that repairing puts nothing new into your repository — the file is already there, merely aimed
at a version `plugin update` has moved past. Declining to repair it only leaves an existing
file running old code.

⭐ **The statusline is only ever adopted into an empty slot.** An occupied one is never
touched, whoever owns it. Taking it over is still `--take-statusline`.

⚠ **One corner is not automated, stated rather than glossed over:** an armed resume is an OS
scheduled task holding this version's absolute path. Update the plugin while it waits and it
wakes into the OLD `resume.py` — the old directory is still there, so it runs, and it runs old
code. ⭐ The blast radius is small, since it is one one-shot job, but it is the last path that
can still go stale.

### 4. Check it took — there is exactly one way that works

```
/dispatch-guard:status
```

⛔ **You will not see anything on screen, and that is not a symptom.** The plugin's liveness
message comes from a `SessionStart` hook, and a hook's stdout goes into **Claude's context**,
never to your terminal. *"I don't see it"* looks identical whether the plugin is working
perfectly or not running at all. Every line `--status` prints is a measurement:

```
plugin installed    : dispatch-guard@dispatch-guard
plugin enabled      : True
install path        : ...\plugins\cache\dispatch-guard\dispatch-guard\<version>
SessionStart hook   : RAN - 2 session(s) stamped, newest 3 min ago
statusline refresh  : every 60s
usage data file     : ...\.claude\dispatch-guard\token_usage.json
                      last written 1 min ago
usage verdict       : GO - 5h at 43%, 168 min left (resets 14:00)
resume armed        : no (nothing pending, which is the normal state)
OVERALL             : everything is live
```

---

### 5. The whole flow on VS Code with the Claude Code extension

⛔ **The extension cannot render a statusline.** ⭐ **That does not affect the brake** — the
gate forks its own refresh. ⇒ **Step 1 is the whole installation.** Steps 4 to 7
below matter only if you want to SEE the line.

1. Open your project in VS Code.
2. Open the integrated terminal (`` Ctrl+` ``) and run the two plugin commands from step 1.
   ⚠ This needs the `claude` CLI on PATH.
3. **Reload the window**, or start a new Claude session. ⚠ Hooks and slash commands load at
   session start. ⭐ **The brake is live from here.** The first verdict says the numbers are not
   there yet, because the fetch has only just gone out; seconds later they are.

Optional, for numbers on your screen:

4. Run the step 2 script from the project directory. Already inside Claude?
   `/dispatch-guard:install` is the same thing.
5. ⚠ **Reopen the folder.** The task is `runOn: folderOpen`, so nothing starts now.
6. ⚠ VS Code asks **Allow Automatic Tasks**. **Say yes.**
   ⭐ Do step 0 first and this never appears — which is the whole point of it.
7. A dedicated terminal named `Claude Usage Watcher` appears, carrying the usage line.

⛔ **Declining step 6 looks exactly like a broken task** — both give you nothing on screen and
no error. To tell them apart: Terminal → Run Task → `Claude Usage Watcher`. If it works by hand,
the task is fine and only the automatic trigger is not.

⭐ **That watcher is YOUR clock, not the brake's.** The statusline half never shows in the
extension. It is still worth installing if you also use the CLI: both halves share one
`token_usage.json`, which is per-ACCOUNT, not per-project.

---

## Uninstalling

⭐ **Two separate things:** what `install.py` wired up (the statusline, the VS Code task) and
the plugin itself (hooks and the skill). `--uninstall` handles the first, `claude plugin
uninstall` the second.

⭐ Inside a Claude session, `/dispatch-guard:uninstall` does step 1 and lists the rest.

### 1. Unwire the two halves install.py set up

Run it once in **every** project you installed into. ⭐ Add `--check` to see it change nothing.

**Windows (PowerShell)**

```powershell
$p = (Get-Content "$env:USERPROFILE\.claude\plugins\installed_plugins.json" -Raw | ConvertFrom-Json).plugins.'dispatch-guard@dispatch-guard'[0].installPath
& "$p\hooks\run.cmd" "$p\install.py" --all --uninstall
```

**macOS / Linux**

```bash
for c in python3 python py; do command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys" >/dev/null 2>&1 && PY="$c" && break; done
p=$("$PY" -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))['plugins']['dispatch-guard@dispatch-guard'][0]['installPath'])")
sh "$p/hooks/run.sh" "$p/install.py" --all --uninstall
```

It does four things:

- removes `statusLine` from `settings.json` (`refreshInterval` goes with it)
- ⭐ sets `auto_statusline` and `auto_vscode_task` to false
- removes `Claude Usage Watcher` from **this** project's `.vscode/tasks.json`
- ⭐ cancels an armed resume

⛔ **The second one is not housekeeping; without it the uninstall undoes itself.**
`auto_statusline` defaults to true, so the next session start finds an empty slot and puts
the line **back** — before you have finished reading the uninstall's own output.

⚠ **Only the project you run it in is cleaned.** While `auto_vscode_task` was on, every
project you opened in VS Code may carry the task, and nothing anywhere records which ones.
Turning the flag off stops the spread; files already written come out one project at a time.

⛔ **That last one cannot be left to a document.** Every other leftover merely sits on disk;
this one is an OS scheduled task that WAKES UP, and the script it means to run may be the one
you just deleted. A leftover that executes is not the same class of mess as a leftover waiting
to be removed.

⚠ **`.vscode/tasks.json` is per-project**, so run this once per project you installed into.

### 2. Remove the plugin

```bash
claude plugin uninstall dispatch-guard@dispatch-guard
claude plugin marketplace remove dispatch-guard
```

⚠ **Step 1 before step 2.** The other way round, the files `--uninstall` needs are already gone.

### 3. What it will not delete for you

| Thing | Where | Why it stays |
|---|---|---|
| usage history, config, session stamps | `~/.claude/dispatch-guard/` | your data. To drop it: `Remove-Item -Recurse` or `rm -rf` |
| `Memory/tasks/` | in each project | your work log. This script never touches it |
| `task.allowAutomaticTasks` | VS Code **user** settings | other tasks may rely on it now |
| `.bak-dispatch-guard` | beside that settings file | it is the backup of *your* settings |
| `statusline-backup.json` | in `~/.claude/` | only exists if you used `--take-statusline` |

⚠ **An already-open `Claude Usage Watcher` terminal does not close itself.** Reopen the folder,
or close it by hand.

---

## The second skill: `unattended-work`

⭐ **This plugin ships two skills.** `dispatch-protocol` is the rule for **how work is
dispatched**; `unattended-work` is how to **work with nobody watching** — review rounds, the
stall test, when you may proceed without asking, and the bar for handing work back.

⚠ **They are deliberately separate.** One governs dispatch, the other governs conduct. Taking
only one is fine: a skill is read at the model's discretion, so an unread one does nothing.

### Do not want the reminder every session?

⛔ **A plugin's hooks always fire, and that is not a setting.** The official reference is
explicit: *"All declared hooks always fire. Hooks cannot be conditionally enabled/disabled
based on user config."* ⇒ So what can be switched off is not the hook, but what it **prints**.

Set it at install time or later:

```bash
claude plugin install dispatch-guard@dispatch-guard --config announce_unattended_work=false
```

Or edit `options.announce_unattended_work` under this plugin's entry in `pluginConfigs`, in
`~/.claude/settings.json`.

| Value | Result |
|---|---|
| unset, `true`, or anything unrecognised | ⭐ every session opens by telling the agent to load the skill |
| `false`, `0`, `no`, `off` | ⛔ the hook prints nothing. The skill is still installed; invoke it yourself |

⛔ **An unrecognised value counts as ON, and that direction is deliberate.** The default is
true, and a reminder that **silently stops appearing** is far worse than a redundant one: you
would believe the rules were in force while nothing had loaded them.

⚠ With it off, `Skill(unattended-work)` still works by hand. Only the prompting stops.


## Seeing the numbers

⛔ **The two interfaces do not print the same line, so there are two examples.**
There used to be one, and no interface printed it: it carried CT (only the statusline can draw
that) and no verdict word (only `--watch` prints one).

**The CLI statusline (`--statusline`)**

```
5h ▓▓▓▓┃░░░░░ 43% 2h-47m  7d ▓▓▓▓┃▓▓░░░ 64% 4d-3h-59m  CT ▓▓▓▓░░░░░  41%  Opus 5·high
```

⭐ It has CT, the model and the effort, because those three come from the payload Claude Code
feeds the statusline command. ⚠ **It has no verdict word.** The session's opening line already
reports "Usage braking is active (GO)", and the real consumer of a verdict is the hook rather
than a pair of eyes.

**The watcher (`--watch`, which is what the extension shows)**

```
12:02:02🟢5h ▓▓▓░░░┃░░░ 34% 1h52m(13:54) 7d ▓▓▓▓┃▓░░░░ 54% 3d22h(Fri 10:00) Fable ▓▓▓░┃░░░░░ 31% 3d22h(Fri 10:00) Burn ▓▓▓▓▓▓▓▓▓▓ .17% 6h36m
```

⭐ It has the verdict word, because for an extension user **this is the only place usage appears
at all** and there is no opening line beside it. ⛔ It cannot draw CT, the model or the effort:
it is a loop in a terminal, and nothing feeds it a payload.

### The `Burn` segment: what `11h-52m left` means

`Burn` answers one question: **at this rate, how long until I hit 100%.**

```
12:02:02🟢5h ▓▓▓░░░┃░░░ 34% 1h52m(13:54) 7d ▓▓▓▓┃▓░░░░ 54% 3d22h(Fri 10:00) Fable ▓▓▓░┃░░░░░ 31% 3d22h(Fri 10:00) Burn ▓▓▓▓▓▓▓▓▓▓ .17% 6h36m
```

⛔ **The watcher is ONE row, and the terminal decided that, not a preference.** A second row can
only be redrawn by moving the cursor UP, and a VS Code terminal panel ignores every vertical
move — established across four releases and then settled by capturing every byte the watcher
writes: the program emitted exactly what it intended and that panel stacked three complete
redraws anyway. ⇒ `\r` (back to the start of the line) plus `\033[K` (clear it) is the only pair
it honours, and that pair can rewrite one row.

⚠ **Which is why the times are short** (`3d23h`, not `3d-23h-16m`) — on a single row every
column decides whether `Burn` is drawn at all. The whole line with `Burn` is **129 columns**;
a panel narrower than that drops it.

**How to read it:**

| you see | meaning |
|---|---|
| `.13%` | ⚠ **The unit is PER MINUTE and is not printed** - 0.13% of the window per minute, over the **last 10 minutes** (`burn_window_min`, default 10) — not an average of the window |
| `11h-52m left` | at that rate you hit 100% in **11 hours 52 minutes** |

⚠ **That time can exceed the time left in the window, and that is correct.** The line above
resets in `4h-24m` but burns out in `11h-52m` ⇒ **you cannot spend it all; the reset arrives
first.** That is when the bar is full.

**The bar is the ratio** (burn-out ÷ reset), ⛔ not a fuel gauge:

| cells | meaning |
|---|---|
| `▓▓▓▓▓▓▓▓▓` full | it outlasts the reset — no need to slow down |
| half | you get halfway through the time left |
| short | ⛔ you hit the ceiling soon — slow down or stop |
| zero | the budget is gone inside 5% of the time left — the colour is forced to red |

⭐ **The colour is a SECOND signal and does not follow the cells** — it reports how fast you
are burning, as a multiple of **clock speed** (`100 ÷ window minutes` = 0.333 %/min, the pace
that finishes the window exactly as it resets).

| speed | colour |
|---|---|
| under 1× | 🟢 green |
| 1× to 1.75× | 🟡 yellow |
| 1.75× to 2.25× | 🟠 orange |
| 2.25× and above | 🔴 red |

⚠ **The two can disagree, and both must be read.** A full bar in red means "burning hard, but
the window only just opened"; a short bar in green means "already crawling, and it still will
not last". Tune the edges with `burn_x_yellow` / `burn_x_orange` / `burn_x_red` — and run
**`python Tools/Debug/burn_band_fit.py`** first, to see what your own history says.

⚠ **Two things that surprise people:**
- **The bar goes back UP.** Slow down and it grows — it measures whether two clocks cross, not
  how much is left in a tank.
- **Full cells are good; the colour is a separate signal.** The CELLS answer "will the budget
  outlast this reset?" — full is good. The COLOUR answers "how fast am I burning?", as a
  multiple of **clock speed** (100 ÷ window minutes = 0.333 %/min, the pace that finishes the
  window exactly as it resets): 🟢 under 1×, 🟡 to 1.75×, 🟠 to 2.25×, 🔴 above. High is bad,
  the same direction as the three bars beside it. ⚠ **The two can disagree and both must be
  read** — a full bar in red is "burning hard, but there is room"; a short bar in green is
  "already crawling and it still will not last". At zero cells the colour is forced to red.
  Tune with `burn_x_yellow` / `burn_x_orange` / `burn_x_red`.

⚠ **`🔥────────── --` means "no data yet"** — a rate needs at least two readings inside the
same five-hour window. Right after installing, or just past a reset, that is what you get; a few
minutes fixes it.

### ⭐ The watcher stops calling the API when nobody is working

⛔ **That VS Code task is bound to the FOLDER being open, not to a session being alive.** So it
used to poll all night against an endpoint that allows about **five** calls per access token.

| Situation | What the watcher does |
|---|---|
| a session is working | fetches normally, at most once per `fetch_seconds` |
| no sign of anybody working for `idle_after_min` (default 15) | ⭐ **stops fetching**, and from 0.33.0 **stops redrawing** |

⭐ **Since 0.47.0 "is anybody working?" reads two sources, whichever is newer:** the gate's own
`state/*.alive`, and the mtime of `~/.claude.json` — which Claude Code writes whether or not any
hook of ours is wired. ⚠ **Why**: when the hooks are not wired up (a deleted install directory, an
interrupted update) the first signal goes flat while you are still working, and the watcher read
that as "gone home". Measured 2026-08-30: `.alive` frozen at 1225 minutes on a machine in
continuous use, the watcher asleep for 20 hours, and `install.py --status` reporting everything
live throughout. ⭐ When the two **disagree** the watcher shows `HOOK?` beside the clock — somebody
is working and our hooks are silent. The repair is `/plugin update` or a reinstall, **then a
restart**.
| a heartbeat comes back | ⭐ resumes at once, for **one** call — never a catch-up burst |

⭐ **From 0.33.0: idle draws once, then goes quiet.** That one render turns the verdict word
into **`SLEEP`** and **drops every colour**, and **keeps the figures**. Nothing else is printed
until somebody starts working.

⛔ **Why "stop redrawing" beats "keep redrawing".** The old behaviour redrew every tick, and the
line was sometimes wider than the terminal — `\r` returns to the start of the **last visual row**
and `\033[K` clears only that row, so each render left its first row on screen for ever.
Overnight that is a wall of half-lines. ⇒ **A row nothing is rewriting cannot be stranded.**

⚠ **Why the figures may stay.** A frozen number is dangerous when a FETCH is failing — but
**while nobody is working nobody is spending**, so it cannot drift. The exposure is the moment
work resumes, and the watcher starts fetching at that same moment. ⭐ `SLEEP` and the absence of
colour are what say the row is not live.

⭐ **Two rows when one will not hold everything, instead of dropping information.** The usage
bars and the verdict stay on the first row; the context bar, the model and the note move to the
second, and **each row is fitted separately**.

⭐ **The signal was already on disk:** the gate writes `state/<session-id>.alive` on every hook
event. ⚠ And `prune_state()` keeps those **by count, newest first**, rather than deleting by age,
so a live session's own file can never be the one dropped and mistaken for idleness.

⛔ **`--statusline` is not gated this way.** It is only ever invoked because a session is
interacting, so a test there would suppress the refresh precisely when it is due.

### Where each segment comes from

| Segment | Source | Scope | `--statusline` | `--watch` |
|---|---|---|---|---|
| `5h` / `7d` | `token_usage.json`, fetched from the API | ⭐ per **account** | ✅ | ✅ |
| `CT` | the payload's `context_window` | ⚠ per **session** | ✅ | ⛔ |
| model · effort | the payload's `model` / `effort` | per session | ✅ | ⛔ |
| verdict word | computed from `token_usage.json` | per account | ⛔ (the opening line has it) | ✅ |

⭐ **That one boundary explains the rest:** why CT is per-session, why 5h and 7d are
per-account — which is why one watcher per machine serves every project — and why the
extension's line cannot tell you which model you are on.

⭐ **CT is there from the first second, reading 0%.** It used to appear only once work had
begun, which changed the width of the whole line and left the reader unable to tell "this
interface has no such thing" from "this session has not started". ⛔ But when the payload has no
such field at all it draws `--`, never `0%`: rendering "cannot read it" as zero is a confident
wrong answer, and it errs low.

⭐ **The `┃` is where the clock is** — not a gap. Fill *ahead* of it means you are burning faster
than the window is passing; behind it means there is slack. A bare percentage cannot say that.
⚠ It sits **between** cells rather than replacing one; replacing a cell makes the filled
proportion read a cell short, so the bar and the number disagree.

Colours are attention, not policy: green, orange from `colour_warn_pct`, red from
`colour_alarm_pct`. ⭐ **Aligned with the thresholds that decide:** orange is where
`soft_pct_5h` starts PACE, red is where `hard_pct_5h` starts STOP, so the bar you glance at and the
decision the gate makes cannot disagree. ⚠ They remain four separate keys: colour is what a
person reads, the thresholds are what refuses a tool call, and wanting the warning earlier than
the slow-down must not cost you the brake.

### In the VS Code extension

**The extension shows usage too — just not in a statusline.** The two environments put the
line in different places:

| | Where the usage line appears |
|---|---|
| CLI | ⭐ the statusline |
| extension | ⭐ a terminal — the `Claude Usage Watcher` task, or your own `usage.py --watch` |

⛔ **The extension cannot draw a statusline at all**, which is a capability limit rather than a
setting. Measured on 2.1.246: `statusLine` appears **0 times** in the extension's webview bundle
while `hooks`, `permissions`, `plugins` and `subagent` all appear; the CLI binary mentions it 34
times. ⇒ So the extension shows the line in a terminal instead, and that terminal is the one the
task opens.

⭐ **Installing that task is step 2 above, "(Optional) The statusline and the watcher"** — one
script does both halves, the statusline for the CLI and the task for the extension. With
`auto_vscode_task` on, a new project gets the task without any install at all; see
Configuration.

⭐ **The brake works in both, and needs none of the above.** The gate forks its own refresh.
⇒ The command below is for **you** to look at, not for the brake:

```bash
python hooks/usage.py --watch          # one line, rewritten in place; --every N to change the interval
```

⭐ Or have it open itself: `/dispatch-guard:install` (by hand, `install.py --vscode-task`)
writes a task that starts a dedicated terminal on folder open, and grants the permission that
lets it.

⛔ **That permission must live in USER settings, and that is a security property, not a quirk.**
If a repository could set `task.allowAutomaticTasks` in its own `.vscode/settings.json`, cloning
any repository would let it run commands the moment the folder opened.
⚠ On Windows the task runs `run.cmd`, never `bash run.sh` — `bash` on a Windows PATH usually
resolves to the WSL launcher stub, which fails with *"no installed distributions"*. And the task
is `type: "process"`, never `"shell"`: in PowerShell a quoted path at the start of a line is a
*string literal*, not a command.

---

### That VS Code task, without doing it per project

⛔ **`.vscode/tasks.json` is a VS Code project file, and nothing changes that.** `runOn:
folderOpen` is workspace-scoped; user-level tasks are limited to `shell` and `process`, and the
documentation makes no promise that they auto-start on folder open.

⇒ So there are three routes. Pick by what you actually want:

| What you want | What to do | Per project? |
|---|---|---|
| the brake to work | nothing | ⭐ no. The gate forks its own refresh |
| the line in some terminal | run `usage.py --watch` once | ⭐ no. One per machine is enough |
| it to appear in every VS Code window | the task | ⭐ no, once `auto_vscode_task` is on |

⭐ **It is on by default; there is nothing to do.** Open a project in VS Code that has no
such task and the next session start writes it, saying so in the opening line.

⛔ **Nothing is asked, because asking did not work.** The question could only reach a MODEL's
context, never your screen — measured on two clean installs, where the task never appeared and
nothing said why. ⇒ The protection moved to the CONFLICT tests instead of a default that hid
the feature.

To switch it off:

```bash
install.py --enable-auto-task      # a safe merge; your other settings are untouched
install.py --disable-auto-task     # off again
```

Or edit `~/.claude/dispatch-guard/config.json`, which is created for you:

```json
{ "dispatch": { "auto_vscode_task": true } }
```

With it on, the SessionStart hook writes the task into a project that is missing it, or whose
task points at an older version. ⭐ **Set once per machine, then every project is automatic.**

⭐ **It is on by default.** ⛔ But it writes only where there is no CONFLICT. **Creating** a new
tasks.json needs all four of these:

1. `auto_vscode_task` is true.
2. It is really running **inside the VS Code extension** (`CLAUDE_CODE_ENTRYPOINT` or
   `VSCODE_PID`). ⚠ Without this test a plain CLI session would leave a `.vscode/` directory in
   repositories nobody ever opens in VS Code.
3. The project directory exists.
4. ⛔ **`.vscode/tasks.json` is not tracked by git.** That file holds an absolute path carrying
   this machine's plugin version. Rewriting a tracked file leaves the tree dirty and invites
   that path into a commit, where it hands the next person a task pointing at a directory they
   do not have. When it is tracked, it writes nothing and tells you why.

⚠ **REPAIRING a task that is already there is deliberately exempt from gates 1 and 2.** The file
exists and is already ours; it merely names a version `plugin update` moved past. Declining to
repair it only leaves an existing file running old code, so it is repaired with the setting off
and outside VS Code too. ⛔ Gate 4, the tracked-file check, applies to both.
⭐ A repair never touches VS Code's `task.allowAutomaticTasks`: that permission was granted, or
withheld, when the task went in.

⭐ **And it says so every time.** Changing somebody's repository without mentioning it is the
wrong kind of convenience, however small the file. ⚠ A project that is already correct is left
alone, so the file is not touched on every session.

---

## ⛔ When the brake fires, how do you know?

⚠ **This is the question that is easiest to wave away.** Advice is something a model weighs
against its task, and "it carried on working" looks exactly like "it never heard".

⇒ So there are **three** signals, of different strength:

| Signal | Guaranteed by | What it proves |
|---|---|---|
| ⭐ **`systemMessage`** — shown on your screen | Claude Code | **the hook ran, and what it decided.** A model cannot swallow it |
| ⛔ **the tool call is refused** | the hook | **that dispatch did not happen.** The only thing that is ENFORCED |
| ⚠ **the agent's acknowledgement line** | the model itself | it **received** it. ⛔ Not that it complied |

### What you actually see

At PACE (85 by default) or STOP (93), this appears on screen:

```
dispatch-guard: usage PACE at 90%. Dispatch is still allowed; scope should shrink.
Expect the agent to acknowledge with `PACE at 90% - winding down`;
if that line does not appear, it did not act on it.
```

⇒ **Then read the first line of the agent's next message.** It is required to print, verbatim:

```
PACE at 90% - winding down
```

⚠ **No line means it did not act on this.** You can take over at that point without guessing.
⭐ It may instead print `- NOT winding down` with a reason — a DIFFERENT fault with a
different fix: "heard it and chose to continue" is not "never received it".

When a dispatch is refused at STOP, this appears:

```
dispatch-guard: sub-task dispatch REFUSED - usage STOP at 95%.
Nothing was dispatched. The agent has been told to save the current step and arm a resume.
```

⭐ **That one is hard evidence.** The tool call genuinely did not happen — the model did not
merely decide against it.

### When that message appears, and why it does not repeat

| | |
|---|---|
| **Which event** | `UserPromptSubmit` — ⭐ **the moment you send a message**. Not a background timer |
| **Driven by** | the percentage in `token_usage.json`, turned into GO / PACE / STOP by `verdict()` |
| **Does it repeat** | ⛔ **No.** Once per level, per session |

⭐ **What stops the repeat is a file**: `~/.claude/dispatch-guard/state/<session-id>.warned`
holds the word `PACE` or `STOP`. On your next message, if the level works out the same as what
that file says, the hook returns and prints nothing.

⇒ So a long run hears it **at most twice**: once crossing `soft_pct_5h`, once crossing `hard_pct_5h`.

⚠ **A change of level re-arms it**, including downwards. After the window resets you are back
at GO, and climbing into PACE again says it again — that is a new round, not a repeat of the
old one.

⛔ **The record is per SESSION.** A new session hears the same level again, deliberately: its
model has none of the previous session's context and has not been told.

⚠ That timer only advances when YOU send a message. ⭐ A refused dispatch is not bound by it:
that is `PreToolUse`, judged on every dispatch, and refused every time.

### ⚠ The two thresholds, and where they sit

| Threshold | Default | Behaviour | Bar colour |
|---|---|---|---|
| `soft_pct_5h` | **70** | **PACE** — shrink scope, dispatch is **still allowed** | orange (`colour_warn_pct` 70) |
| `hard_pct_5h` | **85** | **STOP** — dispatch is **refused** | red (`colour_alarm_pct` 85) |
| `soft_pct_7d` | **95** | **PACE**, driven by the seven-day window | — |
| `hard_pct_7d` | **97** | **STOP**, driven by the seven-day window | — |

⛔ **Before 0.34.0 the brake ignored the 7d window entirely.** It read the five-hour
percentage and nothing else, so **7d 99% beside 5h 0% read as GO** and kept dispatching until
the SERVER refused — both numbers true, the answer wrong. ⇒ The **stricter of the two windows
wins** now, and the verdict says which one is driving it. ⚠ The 7d pair sits high on purpose:
that window is usually not the constraint, and pacing on it at 70% would throttle a week of
work for nothing. ⚠ And a 7d window that resets **before the current 5h window ends** is
ignored entirely — its percentage is about to become zero.

⇒ **85% IS the STOP, and dispatch is refused there.** ⚠ It came down from 90 after a dispatch at 90 ran into a session limit and was killed. For different points, edit
`~/.claude/dispatch-guard/config.json`:

```json
{ "soft_pct_5h": 60, "hard_pct_5h": 85 }
```

⚠ Write only the keys you want to change. ⛔ A value written there is PINNED, so a later
version's new default never reaches you — the `pinned settings` line in `install.py --status`
tells you which ones you hold.

⚠ `.claude/dispatch_gate.log` also records `USAGE(PACE) pct=90` and
`DENY(usage-stop pct=95)` — ⛔ but that proves what the GATE said, not what the agent did.

---

## ⛔ Do not turn ultracode on

⚠ **Ultracode pulls against this plugin, and the cost is paid every turn.**

`/effort` describes ultracode as **xhigh effort PLUS dynamic workflow orchestration**. A
workflow spawns many agents at once by construction — and ⛔ this gate **refuses Workflow
outright**, and refuses a second concurrent sub-task.

⇒ So every turn goes: ultracode tells the agent to plan a workflow, the agent reads, plans,
calls it — and is **denied**. Those planning tokens buy nothing, once per turn.

| effort | With this plugin |
|---|---|
| `max` | ⭐ **Recommended** — the same reasoning depth, no workflow orchestration |
| `ultracode` | ⛔ plans, every turn, for something that will be refused |

### ⛔ With it on, EVERY tool call is refused

⚠ **Not a reminder — a full stop.** `max` or lower may proceed.

⭐ `effort` is present in the `PreToolUse` payload — from the schema inside the shipped
binary: available to hooks firing in a tool-use context, absent from session-lifecycle hooks
— and `PreToolUse` is also the only place a call can be denied. So the gate sees it on
**every** tool call and refuses every one: Read, Bash, Edit, Agent, all of them.

⛔ **There is no way around it from the agent's side** — the refusal reason says so: do not
try another tool, say it and end the turn. ⭐ Only a person can run `/effort`.

On the first refusal your screen shows:

```
dispatch-guard: ultracode is ON and it fights this plugin. It asks for dynamic
workflows, which the gate refuses outright - so the planning is wasted every turn.
Run /effort and pick `max` instead: same depth, no workflow orchestration.
```

⚠ **The refusal repeats; the screen message does not.** The denial reaches the MODEL on
every call, which is what makes it a rule rather than advice, while a systemMessage on every
call would bury the screen — so the person is told once.

⭐ **Why this escalated from "warn once":** ultracode does not merely SUGGEST a workflow, it
re-states the instruction every turn. A session warned once goes on burning planning tokens
on something the gate will deny, for as long as it runs. ⇒ max or below may proceed;
ultracode may not.

---

## Checking usage from a script

```bash
python hooks/usage.py --verdict          # GO / PACE / STOP / NO-DATA
python hooks/usage.py --verdict --json   # machine-readable
```

Exit codes carry the verdict — `0 GO`, `1 PACE`, `2 STOP`, `3 NO-DATA` — so a script can branch
without parsing.

⛔ **Act on the word, never on the percentage.** Within `near_reset_min` of a reset the thresholds
deliberately soften, because hitting the cap there costs a pause of a few minutes rather than lost
work. Three things the verdict handles that a raw reading gets wrong: reset arithmetic, weekly
false alarms, and burn projection.

---

## Resuming after the window reopens

```bash
python hooks/resume.py --arm --task <task-folder>   # --dry-run to see without acting
python hooks/resume.py --status
python hooks/resume.py --cancel
```

Two routes exist, and the gate offers both when it refuses a dispatch:

- ⭐ **Wake the live session** — better whenever it survives, because the work continues with all
  its context loaded. ⭐ **Measured in both harnesses** (2026-08-26): a one-shot CronCreate
  job fired after a **32-minute** idle gap in the VS Code extension and a **33-minute** gap in
  the CLI, and both could still account for what they had been doing. ⇒ The **ten-minute cap
  is a COMMAND cap and does not bound this route** — so do not substitute a background
  `sleep`.
  ⚠ **The job dies with the session**: it lives in memory and is never written to disk, so a
  session that does not survive does not make this route fail — it makes it cease to exist,
  leaving nothing behind to notice. That is why both routes are armed.
  ⚠ **It is also not the cheaper route**, which is the natural misreading. Keeping the
  session does not keep the tokens: a wait long enough to need a resume outlives the prompt
  cache, so the first request after the wake re-sends the whole conversation at full price
  (measured `cache_read` of **zero**). It buys **correctness**, not a smaller bill.
- **A one-shot OS scheduled task** (`schtasks` / `at`) — the only one that works when the session
  does not survive, and ⚠ **the thing that ends a session is often the very limit you are waiting
  on.** ⛔ **But it does not survive a logoff.** Measured 2026-08-26: a task created by
  `schtasks /Create` without `/RU` or `/IT` has Logon Mode **`Interactive only`**, so it runs
  only while the user is logged on interactively. Closing the terminal and the editor is fine;
  logging out or switching user means it never fires.
  No elevation needed: measured on a non-elevated account, `schtasks` created, listed and
  deleted a task with no prompt.

⭐ **Arming both is safe.** The gate touches a per-session heartbeat, and the scheduled run stands
down if any session was active in the last 30 minutes, so the work never runs twice.

### ⭐ Resuming early kills the alarm by itself

⛔ **The armed time can stop meaning anything, and a changed account is only one cause.**
The reset itself can arrive early, so the developer gets their allowance back **hours**
before the alarm is due, carries the work on, finishes, and leaves. The alarm knows none of
that. It wakes at its old time, finds nobody active because they finished and left, and
**redoes work that is already done** — spending a fresh allowance to produce a duplicate.

⭐ **So the cancel happens when WORK RESUMES, not when the alarm fires.** On `SessionStart`
and `UserPromptSubmit` the gate asks: is an alarm armed for a time that has not arrived, and
does the verdict now show headroom? If so it **kills the alarm** and says so into the
session.

⛔ **The verdict table is the whole safety argument:**

| verdict | action | why |
|---|---|---|
| **STOP** | **keep** | the wait is still on; this is why the alarm exists. ⭐ It is also what stops a cancel firing seconds after the arm — a dispatch is refused at STOP, so STOP is necessarily still true when the alarm is armed |
| **NO-DATA** | **keep** | we do not know whether the window reopened. ⛔ Never discard a backup on the strength of ignorance |
| **GO / PACE** | **cancel** | there is MEASURED headroom, so the work can proceed now, in this session, with its context. The alarm has nothing left to do |

⭐ **A route (A) wake lands here too** — the cron wake arrives as a `UserPromptSubmit` — so
the backup retires the moment the preferred route actually works, rather than at its own
fire time.

⚠ **A failed cancel is also said out loud**, with an instruction to run `--cancel` by hand: a
cancel that fails silently leaves an alarm that will redo the work.

### ⚠ What happens if the account changes during the wait

⭐ **The brake heals itself, with nothing to do.** `usage.py` re-reads the credentials file
on every call, so the next fetch is the new account's numbers, `token_usage.json` is overwritten,
and the gate stops refusing — there is allowance, so the verdict is GO.

⭐ **And a live session simply carries on.** Switching accounts is a human action, so a human
is at the keyboard; no alarm has to fire at all.

⛔ **The one thing that goes stale is the OS alarm's TIME.** It was computed from the OLD
account's reset instant, which means nothing to the new one.

⛔ **So if you switch accounts and carry the work on yourself, run `resume.py --cancel`.**
Without that you hit this: the alarm fires at the old reset, finds no session active in the
last 30 minutes (you finished and walked away), asks the new account's verdict and gets GO —
and **redoes headless the work you already did**. The limitation is pre-existing (it cannot
tell "alive on this task" from "alive on something else"), but an account switch turns it
from rare into likely.

⭐ **`--status` tells you the alarm is stale:**

```
reset     : ⛔ STALE - armed for 22:18 but the stored reset is now 00:18,
            and the armed one has NOT passed yet.
            The usual cause is a DIFFERENT ACCOUNT signed in during the wait.
```

⚠ **That test only runs while the armed reset has NOT yet arrived.** Past it the stored value
advances legitimately (the statusline re-fetches every 120–150 s), so comparing then would
warn while everything was fine.

⛔ **The account cannot be identified directly.** Measured 2026-08-26: neither
`~/.claude/.credentials.json` nor the usage endpoint carries **any** account identifier —
only tokens, `scopes`, the plan type and numbers. So no fingerprint is attempted: the only
candidate is a hash of the refresh token, which is hashing a secret, while
`subscriptionType` + `rateLimitTier` would catch a change of PLAN and miss a change of
ACCOUNT on the same plan — and half a detector is worse than none. **"The reset moved before
it was due" is the only signal that holds.**

⛔ **It refuses a handoff that is only a placeholder** — under ~200 characters of real content is
rejected, because a resume that wakes with nothing to read spends an allowance to produce nothing.

⛔ **It does not delete itself just because it woke up.** The window may not actually have reset,
and the run may fail on network, credentials or `PATH`. It verifies, runs, and removes the schedule
**only on a clean exit**; anything else retries until `retry_window_min` elapses, then stops for
good and leaves a marker **the next Claude session reads out loud**.

---

## Configuration

⛔ **`config.json` is never created — not one byte.** The install script does not write it
and neither does the hook. No file means every setting follows the plugin's default, including
the defaults a later version changes.

⭐ **To change one thing, create `~/.claude/dispatch-guard/config.json` yourself with just
that key.** Everything else keeps following the default. For the list of keys and what each
one defaults to, read `config.example.json` inside the plugin — every key is there with its
value and an explanation in both languages. Not sure of the path? `python install.py --status`
prints the state directory.

⛔ **Why it is not created for you.** A value written in that file is **pinned**: a later
version's new default never reaches you.
⚠ **Measured, not theoretical.** Between 0.9.0 and 0.11.0 the seed copied the example
verbatim, values included — so when `auto_vscode_task` changed default, every machine
installed before that day kept the old one: the update landed, the default moved, nothing
happened, and it cost two reinstalls to find. Seeding only the explanations fixed the pinning
and left a 55 KB file that explained every setting while showing not one of its values.
**Creating nothing has neither problem.**

⛔ **An existing `config.json` is never overwritten.** It is yours from the moment it exists.
⭐ **To see what you have pinned, and which pins no longer match: the `pinned settings` line
in `install.py --status`** — it names every key that differs from the current default,
including keys that have since been renamed.

Override the whole state directory with `--dir <path>` or `$CLAUDE_DISPATCH_DIR`. A project may
also carry `<repo>/.claude/dispatch-guard.json`, which wins for the `dispatch.*` keys.

⭐ **Not sure where the files are? Run `python install.py --status` and read the `log files` line** — it prints the resolved absolute path, whether the folder exists yet, how many files and how large, the retention setting in force, and a warning if `$CLAUDE_DISPATCH_DIR` has moved the hooks somewhere that script does not look (the hooks read that variable; `install.py` does not).

**How long they are kept** (`history_keep_days`, default **30**). A file in `history_dir` older
than that is deleted whole.
⭐ **Use `0` to keep everything for ever** — that is what this plugin did before the key existed.
⚠ **`null` is NOT for ever.** `null` means "use the default", exactly as it does for
`history_dir`, so it deletes at 30 days just like leaving the key out. Only `0` keeps everything.
⛔ **Whole files only, and only this plugin's own** — `token_usage_history_*.jsonl` and
`API_response_usage_*.jsonl`. A single file is never trimmed, because a half-trimmed record looks
complete and is not; and `history_dir` can be pointed at a folder holding somebody else's files,
so there is no blanket sweep.
⚠ Any value that cannot be read as a positive number — a word, an empty string, `true`, a
negative — means **keep everything**, never "fall back to 30 and start deleting". The pruning
runs at most once a day per process, at the moment a new day's file is started.

**Keep every API response** (`debug.API_response_usage`, off by default). With it on, every
response from the usage endpoint is stored **complete** under `history_dir` as
`API_response_usage_<YYYYMMDD-HHMMSS>.jsonl`, one array per line, one file per local day:

```json
["<organizationUuid>", "<accountUuid>", "2026-08-27T09:45:00+00:00", { "…the whole body…": true }]
```

⭐ **It exists because the field nobody values today is the one a later question needs.** The
parser keeps two percentages and discards the rest; `nimbus_quill` and `seven_day_opus` looked
worthless right up to the moment they became evidence.

⚠ **At most about 1.2–1.4 MB a day.** Measured: 2006 bytes per line (the body alone is 1887);
with `fetch_seconds: 120` and `fetch_seconds_jitter: 30` the mean interval is 135 s, so about
640 fetches a day — 720 is the no-jitter ceiling. Reaching that needs a full day of continuous
work; while nothing is happening, `idle_after_min` stops the watcher asking. It is a
diagnostic — switch it back to `false` once it has answered your question.
⛔ **A `null` in position 1 means the row cannot be attributed to a seat**, and statistics must
**exclude** those rows rather than average them in.
⚠ There is more than one route to it, so learn the rule rather than a list: **if the seat cannot
be confirmed, it is written `null`** — `~/.claude.json` unreadable, no `oauthAccount` or
`accountUuid` in it, its organisation disagreeing with the credentials file (they are written at
different moments and diverge after an account switch), or the token coming from
`$ANTHROPIC_TOKEN`. A `null` in position 0 means the credentials file carries no
`organizationUuid` — and then position 1 is null too, because there is nothing to confirm it
against.
⚠ `organizationUuid` identifies the **organisation**, not the seat. Several seats in one
organisation share it.
⚠ **Concurrent writers lose lines.** Measured: four processes appending at once dropped 14 and
26 lines out of 240 (roughly 6–11%); two processes lose lines as well. No exception, no
corruption, no sign anywhere. The token-usage history works the same way.
⛔ "Run one session and nothing is lost" is **wrong** — `dispatch_gate.py` runs `usage.py` of
its own accord, so one session can still have two writers. This file format cannot promise a
gap-free sequence.
⭐ A list is an alias: `"debug": ["API_response_usage"]` means `{"API_response_usage": true}`.
⚠ `"debug": true` switches nothing on — it switches everything off and says why on stderr.

**Token usage history** (`debug.token_usage`, ⭐ **on by default**) is written to
`history_dir` — by default
**`~/.claude/dispatch-guard/logs/`**, the `logs/` folder under the state directory — as
`token_usage_history_<YYYYMMDD-HHMMSS>.jsonl`, one file per local day, and **no single file
is ever trimmed**:
⛔ **There is one name and no other.** This switch has been called `keep_history` and
`token_usage_history` before now; neither is read any more, and files under the old names are
neither read nor pruned. ⚠ So a config still carrying one gets the DEFAULT rather than the
value somebody wrote — `install.py --status` names every retired key it finds, and that report
is the only place an ignored setting ever shows up. ⭐ Updating from an older version: run
`Tools/clean-dispatch-guard.ps1`, then reinstall.
⭐ **Why it is on now**: the burn projection needs two samples of the same window, so the
"projected to run out before the reset" half of PACE had never fired for anyone who did not go
and switch it on. **Measured: 132 bytes a row, about 640 readings a day, so roughly 82 KB a
day** and 2.4 MB across the 30 days `history_keep_days` keeps — and that is a ceiling, since a
row is written only when a number actually moved.

```json
{"at": "2026-08-26 13:29:31", "pct": 74.0, "resets_at": "2026-08-26 14:09:31",
 "sd_pct": 68.0, "sd_resets": "2026-08-30 17:29:31", "model": "Opus 5", "session": "oooooooo",
 "acct": "aaaaaaaa-0000-4000-8000-00000000000a"}
```

---

## Files and processes — which program does what, and why a file is still needed

Every subsection here answers a question that was actually asked: which program calls the API,
which one is `--watch`, can it all be memory, and what are `state/` and `fetch.claim` for.

### There is one program, with several entry points

| what | file | function |
|---|---|---|
| calls the API for the numbers | `hooks/usage.py` | `fetch()` |
| `--watch`, the live display | **the same** `hooks/usage.py` | `watch()` |
| `--statusline`, one rendered line | same | `collect()` |
| the GO / PACE / STOP decision | same | `verdict()` |

So `usage.py --watch` is **one process** doing both the fetching and the display. Between those two
the number was never in a file to begin with.

### The cross-process hop cannot be memory, and that is architecture rather than laziness

**The consumer of the number is the hook, and the hook is a newborn process every time.**
`hooks/hooks.json` declares it as `"type": "command"` with a `PreToolUse` matcher of `*`, so Claude
Code spawns a fresh `dispatch_gate.py` on **every tool call**, and it dies milliseconds later.

```
usage.py --watch        <- long-lived
      | writes token_usage.json
dispatch_gate.py        <- a new process per tool call, sharing no memory with the above
      | reads token_usage.json
```

And there is more than one reader: several watchers, the status line, and the gate on every dispatch
all use that one file to agree on *who should fetch* and *how old the number is*. Memory cannot do
that.

### Inside a process it IS passed in memory now

`ensure_fresh()` returns the record itself, so a caller never re-reads the file it just read or
wrote. Measured per watch tick:

| | before | after |
|---|---|---|
| wall clock | 6.5 ms | **2.3 ms** |
| file opens | 5 | **3** |
| `token_usage.json` among them | 3x | **1x** |

The two that remain are genuinely needed each tick: the history file for burn projection, and the
credentials file for the token-expiry warning.

`verdict()` takes an optional `data` argument that is **for callers inside that file only**. An
outside caller must omit it - the point of the function is that it reads the stored record itself,
and letting a stranger supply one would let a stranger supply a wrong one. `dispatch_gate.py`
deliberately does not pass it.

### `fetch.claim` - two jobs, and the second one matters more

1. **It stops simultaneous duplicate requests.** Several processes share `token_usage.json`, so two
   watchers crossing the refresh boundary together would **both** fetch - two of about five calls
   per token, spent on one boundary. The claim is stamped **before** the request; whoever arrives
   second sees it and stands down.
2. **It is the only backoff there is.** Reaching that check means `token_usage.json` is *not* fresh, so
   any recent attempt recorded there must have **failed**. The claim is therefore **deliberately not
   cleared on failure**, which is what stops the next caller retrying for a whole interval. A
   persistent 429 is not something retrying cures.

It is an mtime clock, not a real mutex. Two processes hitting the same instant still get two calls;
the cost is one wasted request, bounded and rare. A real lock needs stale-owner recovery and
release-on-crash, which is a lot of machinery to save the occasional single request. Upgrade only if
`fetch.log` starts showing paired 429s.

### `state/` - what is in it, and why the two kinds are pruned by different rules

| name | content | job |
|---|---|---|
| `<session>.start` | one timestamp | **decides whether this session is ENFORCED** |
| `<session>.alive` | one timestamp | proves hooks are firing; the scheduled resume asks it whether any session is still alive. ⭐ `--watch` reads it too, to decide whether to pause fetching |
| `<session>.slotN` | a dispatch slot | concurrency control. **Has its own reclaim rule, in minutes** |

It used to grow forever - 63 files after one day of ordinary work. It is pruned now, **but by two
different rules, and the asymmetry is the whole answer**:

- **`.alive` is pruned BY COUNT, newest 20 kept - and one would do.** Only the newest is ever read;
  the rest contribute a number to `install.py --status` and nothing else.
- **`.start` is pruned BY AGE ONLY, never by count.** It is not data, it is a **switch**.
  `session_start()` returning `None` sends the gate down its advisory branch, so deleting the marker
  of a session that is **still running** silently turns its brake off. And liveness cannot be
  inferred: an open but **idle** session fires no hooks, so it refreshes nothing and looks exactly
  like a dead one.
  So the week is a **safety margin, not a useful lifetime**. The file is worthless the moment its
  session ends; the margin exists because we cannot tell when that was.
  **If it ever needs to shrink, the thing to change is the fail-open, not the margin.**
- **`.slotN` is not touched at all.** It is live state, and removing one that is still held hands
  out the same slot twice.

### Why not one directory per session

A fair question, with three parts to the answer:

1. **There is no collision to avoid.** The session id is already the filename - `state_path()` keeps
   only alphanumerics, `-` and `_`, and a UUID passes through untouched - so two sessions cannot
   land on the same name.
2. **A directory per session does not reduce anything.** It trades thousands of small files for
   thousands of empty directories, which cost more on Windows. The thing to fix was the pruning
   rule, not the layout.
3. **The two files cannot become one.** `.start`'s mtime *is* the session start time and must never
   be rewritten; `.alive` is stamped on every single hook. Their write schedules are opposites, and
   that is why there are two of them rather than an oversight.

### What about `~/.claude/session-env/<session-id>/`? No, and cleanup is not the reason

**It is a reasonable idea and its central point is correct** - these files' lifetime *is* the
session's lifetime, so co-locating them is the semantically honest layout. The directory is also
genuinely **writable** (Claude Code puts its own `sessionstart-hook-*.sh` there), so permissions are
not the obstacle.

**One common objection does not hold, and is worth clearing out of the way first:** "that directory
is not pruned either" - measured 2026-08-26, 763 subdirectories, the oldest a month old. True, but
not a reason: adding two small files to a directory that exists anyway makes nothing worse.

**The real reasons are two others, and the first is that the problem is already solved.** `.alive` is
pruned by count and `.start` by age, so this plugin's own directory is now **bounded**. "Moving it
fixes the growth" is therefore no longer a benefit, because nothing is left to fix. What remains on
the move-it side is **semantic tidiness**.

**And the cost is a dependency on the undocumented internal layout of one version of one client,
with the path assembled by guesswork - for the one file whose absence silently turns the brake off.**

**This plugin is about to be published for strangers to install, so one question settles it:** what
does the gate do on a machine where `~/.claude/session-env/` does not exist, or is laid out
differently? Cloud sessions, `--bare` mode, a future release that renames it, a harness that is not
Claude Code at all.

The only answer is "fall back to `state/`". That means **two locations for one fail-open switch**,
and every read has to consult both - otherwise a session whose directory moved between two runs
reads as "no marker" and drops to advisory.

So moving it does not remove the pruning problem. It adds a **second place to look for the one file
that must never be missing**, trading a bounded problem for a harder-to-reason-about one.

**If Claude Code ever prunes that directory and hands us the path in the hook payload, this becomes
the right answer** - at that point it is not guesswork and no fallback is needed. Until then,
`state/` is ours, bounded, and has exactly one place to look.

**If it is moved anyway, one condition is not optional: make the fail-open loud.** Today a missing
`.start` leaves one `ADVISORY(no-session-stamp)` line in a log nobody reads. Once that file lives in
a directory we do not own, that path becomes more likely, and the line has to become something the
session says out loud.

## ⛔ What it does NOT do

Read this before trusting it. Every item is a way it can look like it is working when it is not.

- ⛔ **The approval artefact is not a barrier.** An agent can always write `PARALLEL-APPROVED`
  itself, and one did — refused twice, it wrote the file quoting the owner's phrasing as the
  approval, and got through. What the artefact buys is that the act is **deliberate**, that it
  **expires**, and that its use is **one log line** carrying its age and contents.
- ⛔ **A background dispatch cannot be counted, only refused.** `PostToolUse` fires when the tool
  call *returns*, which for a background dispatch is at launch, and no hook fires when one
  finishes. ⇒ An approved concurrency runs as **batches of N**, not a rolling window.
- ⛔ **It fails OPEN.** A gate that refused everything because it crashed would be worse than the
  rule it enforces. ⚠ The price: **an absent denial is not proof it ran.** Read
  `<repo>/.claude/dispatch_gate.log` — a log full of `ADVISORY(no-session-stamp)` means it is
  enforcing **nothing**, and looks identical to a log in which nobody broke the rules.
- ⚠ **The extension alone still leaves the brake with data.** It invokes no statusline, but
  the gate forks its own refresh, so `hard_pct_5h` has a number to compare against. ⚠ The first verdict of a fresh install can still
  read "no numbers yet" — the fetch has only just gone out. ⛔ If EVERY session says it, the
  fetch is failing rather than pending: `usage.py --fetch-now` prints the reason.
- ⛔ **A percentage is shown only while it can still be true.** No data, data older than
  `stale_min`, and a window that has already turned over all render as `--`. Under-reading is the
  dangerous direction: a frozen low number holds the brake off exactly when it should fire.
- ⭐ **This class of defect is what the API fetch removed.** It used to be that each session
  cached its own usage and replayed it, so one could report 97% while another reported 74%, and
  one froze at 6% while the truth reached 22% with a correct reset time — sixteen points low, in
  the direction that keeps dispatching. A fetched number is the server's, so the file's age is
  honestly the number's age. ⚠ Historical note: the stored timestamp used to move only when a
  number
  moves, so the file's age means *"how old is this number"* — but nothing here can make Claude
  Code's own value fresher than it is.
- ⛔ **The skill requirement really can deadlock a session.** If the skill registry itself
  is broken, that session cannot dispatch at all. ⭐ That is what
  `require_dispatch_protocol: false` is for, and
  it belongs to **you**: the refusal deliberately does NOT name that key, because a rule that
  names its own off switch is a rule that gets switched off. ⚠ In the normal case it deadlocks
  nothing — invoking a skill is a tool call the agent can make, and the opening line names both
  skills before the first dispatch.
- ⚠ **The gate cannot tell an INVOKED skill from an ADOPTED one.** It records the `Skill` tool
  call; whether the agent then followed the skill is not knowable from a hook.
  `unattended-work`'s own `ACTIVE` line is the second half of that answer.
- ⚠ **The model ceiling sees only an EXPLICIT `tool_input.model`.** A model pinned in an
  agent definition's frontmatter, or a `subagent_type` default, is invisible to the hook, and
  `subagent_type: "fork"` always inherits the parent model — a ceiling cannot lower it.
- ⚠ **An omitted model inherits THIS SESSION's model, whatever it is.** Deliberate: that is
  the model you chose. ⛔ But it also means that running the session itself on Fable gives
  every sub-agent Fable and the ceiling never applies. Run the session below the ceiling.
- ⭐ **The ceiling is narrowed by Claude Code's own `availableModels` allowlist.** On an
  account restricted to sonnet, an `opus` ceiling IS a sonnet ceiling — the refusal says so,
  and the replacement it names is one the account can actually select. ⛔ But being outside
  the allowlist is not refused by itself: there Claude Code **silently substitutes** (the
  newest allowed model in the family, or the parent's model), and every substitution is a step
  DOWN in cost. Nothing for a cost guard to protect, and a refusal there would eventually kill
  legal work.
- ⭐ **The rule lives in the SKILL, not only in the refusal.** `dispatch-protocol` carries
  the price table and `max_model_price`, so an agent reads them BEFORE it chooses — ⛔ a rule
  an agent only ever meets as a refusal is a rule it tries to route around. The block the gate
  injects into every sub-task prompt carries it too (rule 7). ⚠ Two copies of a number can
  drift, so a check asserts the skill's four rows against the function that decides.
- ⭐ **The numbers are published data, not mine.** They are the `pricing` field on each entry
  of the shipped model catalog: `tier_<input>_<output>`, US dollars per million tokens.
  ⛔ **Priced per MODEL, not per family**, because a family is not one price:
  `claude-opus-4-0` is $15 and `claude-opus-5` is $5 — three times, same family. ⛔ And an
  unrecognised model is refused rather than ranked. ⚠ A known family with an unseen version
  (`claude-opus-6`) is priced through its family, and that assumption is logged as
  `MODEL-PRICE-ASSUMED`.
- ⚠ **The `[1m]` suffix is stripped and not charged for.** The catalog publishes one `pricing`
  tier per model and none for the long-context variant, and the harness's own accounting puts a
  long-context request in a separate bucket (`longCtxCost`) without multiplying its price.
  ⇒ There is no published number to use, so this gate invents none.
- ⛔ **The command guards read a shell STRING, not a parsed shell.** An operator inside
  quotes, or the words `git commit` inside a heredoc body, can produce a false positive.
  ⭐ Every refusal names the command it refused in `.claude/dispatch_gate.log`, and every
  guard has its own off switch.
- ⚠ **`git commit -a` / `-am` also stages everything tracked, and the add-all guard does not
  see it.** `-am` is caught by the `-m` guard; a bare `-a` is not caught at all.
- ⚠ **The branch guard compares ONE checkout** — the one the payload's `cwd` resolves to. A
  `git -C <other-repo> commit` is judged against this repository's branch.
- ⚠ **The branch guard can be satisfied by switching the shared tree.** Deliberate: a branch
  this session selects is legitimate, and every switch leaves a `BRANCH-RECORDED` line.
- ⚠ **The relative-`cd` guard warns and never refuses.** The shell's working directory
  persists between tool calls and the hook payload does not carry it, so the gate cannot know
  what the relative path will resolve against. ⛔ It does not refuse what it cannot test.
- **The plan check is a timestamp, not a reading.** It catches forgetting, not cheating.
- **It is per session.** Two sessions in one working tree do not block each other — give each its
  own `git worktree`.
- ⛔ **Waking the live session can only ever be REMINDED, never enforced.** `CronCreate` is
  an agent tool and no Python hook can call it, so `resume.py --arm` can only print a line
  telling you to arm it. ⚠ **Arm only the OS alarm**, and if anybody touched a session in the
  last 30 minutes it stands down expecting the wake to handle it — **and neither fires.**
- ⛔ **The "resuming early kills the alarm" check runs only on `SessionStart` and
  `UserPromptSubmit`.** A session woken only through `PreToolUse` does not reach it, so the
  alarm survives until the next user prompt.
- ⛔ **`NO-DATA` keeps the alarm.** Not knowing whether the window reopened is no reason to
  discard a backup — so a machine with no usage data never auto-cancels. Confirm with
  `usage.py --fetch-now`, or install the statusline.
- ⚠ **The whole chain has never been run end to end in one go.** Every stage is measured
  individually and individual hooks were driven end to end, but "really hit STOP → arm both →
  window reopens → alarm cancelled → work continues" needs the allowance actually burned to
  `hard_pct_5h`, so it has never been staged deliberately.
- **A session that began before the plugin was enabled is advisory only.** Deliberate: policing it
  would refuse dispatches for a plan file it had no way to know it needed.

---

## Credits

The usage half is adapted from **[claude-pacer](https://github.com/drpwchen/claude-pacer)** — its
reset arithmetic, weekly false-alarm rule, burn projection, near-reset exemption, proportional bar
and elapsed-time marker, rewritten in Python so this plugin has no Node dependency. Its responsive
tiers, width probing and topic display were deliberately not taken: they are the large half of that
project, and none of it decides whether to dispatch.

⭐ One trap from that project is closed rather than reproduced: its statusline persists on any
non-`--demo` invocation, so feeding it synthetic input overwrites the real data. Here a payload
carrying no usage writes nothing and says so.

## Licence

MIT.
