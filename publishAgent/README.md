# publishAgent 使用說明

這個資料夾提供一套由 01 到 05 的 Python 腳本，協助你用較容易理解的方式完成 Agent 365 的本機測試、設定、藍圖建立與 manifest 封裝。

這份文件的目標是：
- 用最少的步驟理解整體流程
- 知道每支腳本負責什麼工作
- 依照順序執行，減少出錯機會

## 專案結構

```text
publishAgent/
├── _common.py
├── 01_build-run-agent.py
├── 02_setup-a365-config.py
├── 03_setup-agent-blueprint.py
├── 04_deploy.py
├── 05_publish-to-admin-center.py
└── README.md
```

## 建議使用順序

建議依照下面順序執行：

1. `01_build-run-agent.py`
2. `02_setup-a365-config.py`
3. `03_setup-agent-blueprint.py`
4. `04_deploy.py`
5. `05_publish-to-admin-center.py`

如果你只想重新產生新版 `manifest.zip`，通常只需要直接執行第 5 步。

## Mermaid 步驟圖

下面這張 Mermaid 圖對應附件中的 6 步驟流程，並且把第 1 到第 5 步直接對應到 `publishAgent` 內的 Python 腳本：

```mermaid
flowchart LR
	s1["1<br/>Build and Run<br/>Agent Step<br/><br/>`01_build-run`<br/>`-agent.py`<br/>前置: uv / .env<br/>輸出: Host URL"]
	s2["2<br/>Setup A365<br/>Config Step<br/><br/>`02_setup-a365`<br/>`-config.py`<br/>前置: Azure 登入<br/>輸出: a365.json"]
	s3["3<br/>Setup Agent<br/>Blueprint<br/><br/>`03_setup-agent`<br/>`-blueprint.py`<br/>前置: a365.json<br/>輸出: generated json"]
	s4["4<br/>Deploy<br/>Environment<br/><br/>`04_deploy.py`<br/>前置: blueprint id<br/>執行: 模擬部署<br/>輸出: deploy check"]
	s5["5<br/>Publish Admin<br/>Package Step<br/><br/>`05_publish-to`<br/>`-admin-center.py`<br/>前置: generated json<br/>輸出: manifest.zip"]
	s6["6<br/>Create Agent<br/>Instance Step<br/><br/>Admin Center<br/>手動建立流程<br/>前置: manifest.zip<br/>輸出: agent instance"]

	s1 --> s2 --> s3 --> s4 --> s5 --> s6

	classDef step1 fill:#16b6c8,stroke:#16b6c8,color:#ffffff,stroke-width:2px;
	classDef step2 fill:#157fd6,stroke:#157fd6,color:#ffffff,stroke-width:2px;
	classDef step3 fill:#1683de,stroke:#1683de,color:#ffffff,stroke-width:2px;
	classDef step4 fill:#6b69b8,stroke:#6b69b8,color:#ffffff,stroke-width:2px;
	classDef step5 fill:#138a10,stroke:#138a10,color:#ffffff,stroke-width:2px;
	classDef step6 fill:#ffba08,stroke:#ffba08,color:#ffffff,stroke-width:2px;

	class s1 step1;
	class s2 step2;
	class s3 step3;
	class s4 step4;
	class s5 step5;
	class s6 step6;
```

補充說明：
- 第 1 到第 5 步是這個資料夾中的腳本流程
- 第 6 步不是 Python 腳本，而是在 Agent 365 Admin Center 內完成的手動操作
- Mermaid 圖中的 `前置` 代表執行該步驟前通常要先備妥的條件
- Mermaid 圖中的 `輸出` 代表該步驟完成後最重要的產物或結果

## 執行前準備

開始前，請先確認：

1. 已安裝 `uv`
2. 已登入 Azure CLI
3. 專案根目錄的 `.env` 已填好必要設定
4. 專案根目錄已有 `a365.config.json`，或準備在第 2 步建立它

常用指令：

```bash
az login
uv run python publishAgent/02_setup-a365-config.py
```

## 每個檔案的簡易說明

### `_common.py`

這是共用工具檔，不需要單獨執行。

主要功能：
- 取得路徑
- 載入 `.env`
- 讀寫 JSON
- 執行命令
- 輸出統一格式的訊息
- 做基本驗證

你可以把它理解成：其他 01 到 05 腳本都會共用的工具箱。

### `01_build-run-agent.py`

用途：
- 啟動本機 Agent Host
- 視需要啟動 Microsoft 365 Agents Playground
- 幫你確認本機端點是否正常

適合什麼時候用：
- 想先確認 agent 本機能不能跑起來
- 想在發佈前先做本機測試

基本用法：

```bash
uv run python publishAgent/01_build-run-agent.py
```

只啟動 agent、不啟動 Playground：

```bash
uv run python publishAgent/01_build-run-agent.py --skip-playground
```

你會看到的結果：
- 本機 agent 啟動
- 顯示健康檢查網址
- 如果有開 Playground，也會顯示 UI 網址

### `02_setup-a365-config.py`

用途：
- 建立或更新 `a365.config.json`
- 把 Agent 365 後續步驟需要的設定整理好

適合什麼時候用：
- 第一次設定專案
- Azure 資源名稱、租戶、訂閱、endpoint 變更時

基本用法：

```bash
uv run python publishAgent/02_setup-a365-config.py
```

你會需要準備的資訊通常包含：
- Tenant ID
- Subscription ID
- Azure location
- Resource group
- Web App 名稱
- Agent 顯示名稱
- Manager email
- Messaging endpoint

你可以把這一步理解成：先把後續流程要用的設定檔準備好。

### `03_setup-agent-blueprint.py`

用途：
- 呼叫 `a365` 與 `az` CLI，建立或接續使用 Agent Blueprint
- 產生 `a365.generated.config.json`

適合什麼時候用：
- 第 2 步完成後
- 想讓後面的 publish 流程知道要綁定哪個 blueprint

基本用法：

```bash
uv run python publishAgent/03_setup-agent-blueprint.py
```

如果你只想看會跑什麼命令：

```bash
uv run python publishAgent/03_setup-agent-blueprint.py --dry-run
```

這一步成功後，通常會得到：
- `a365.generated.config.json`
- 可用來封裝 manifest 的 blueprint 資訊

### `04_deploy.py`

用途：
- 模擬部署流程
- 讓教學步驟保持完整

適合什麼時候用：
- 想照完整 01 到 05 順序走一次
- 想保留教學節奏，但目前不真的部署 Azure 資源

基本用法：

```bash
uv run python publishAgent/04_deploy.py
```

注意：
- 這支腳本目前是示範用
- 它不會真的把程式部署到 Azure

### `05_publish-to-admin-center.py`

用途：
- 產生最新的 `manifest.json`
- 自動提升 manifest 版本號
- 自動產生新的 package/title ID
- 統一使用 `boy.png` 作為 icon
- 在 headless Linux 直接封裝 `manifest.zip`

適合什麼時候用：
- 想把最新 manifest 打包上傳到 Agent 365 Admin Center
- 前一次上傳後，想再產生新版 package

基本用法：

```bash
uv run python publishAgent/05_publish-to-admin-center.py
```

如果你只想先預覽，不真的寫檔：

```bash
uv run python publishAgent/05_publish-to-admin-center.py --dry-run
```

這一步會自動完成：
- 更新 `manifest/manifest.json`
- 更新 `manifest/agenticUserTemplateManifest.json`
- 更新 `manifest-template.json`
- 產生 `manifest/manifest.zip`

特別注意：
- 每次執行都會自動產生新的版本號
- 每次執行都會自動產生新的 package/title ID
- 這是為了降低 Admin Center 出現舊版本或已部署 title 衝突的機率

## 最常用的完整流程

如果你是第一次執行，建議用下面順序：

```bash
uv run python publishAgent/01_build-run-agent.py
uv run python publishAgent/02_setup-a365-config.py
uv run python publishAgent/03_setup-agent-blueprint.py
uv run python publishAgent/04_deploy.py
uv run python publishAgent/05_publish-to-admin-center.py
```

如果你只是要重新產生新的上傳包，直接執行：

```bash
uv run python publishAgent/05_publish-to-admin-center.py
```

## 常見問題

### 1. 什麼時候只跑第 5 步就好？

當下面條件都已經成立時，通常只跑第 5 步即可：
- `a365.config.json` 已存在
- `a365.generated.config.json` 已存在
- 你只是想重新產生新版 `manifest.zip`

### 2. 如果 `03_setup-agent-blueprint.py` 失敗怎麼辦？

先檢查：
- 是否已 `az login`
- `.env` 與 `a365.config.json` 的值是否正確
- 是否已有可重用的 `AGENT_BLUEPRINT_ID`

### 3. 上傳到 Admin Center 時遇到版本或已部署錯誤怎麼辦？

先重新執行：

```bash
uv run python publishAgent/05_publish-to-admin-center.py
```

這支腳本已經會自動：
- 產生較新的版本號
- 產生新的 package/title ID

通常重新封裝後再上傳即可。

## 最後產物在哪裡

完成第 5 步後，最重要的檔案通常在專案根目錄下的 `manifest/`：

- `manifest/manifest.json`
- `manifest/agenticUserTemplateManifest.json`
- `manifest/manifest.zip`

其中真正要上傳到 Agent 365 Admin Center 的通常是：

- `manifest/manifest.zip`
