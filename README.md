# 🚀 Agent Framework 範例 Agent — Python

這個 repo 示範如何在 Python 中，搭配 [Microsoft Agent 365 SDK](https://github.com/microsoft/Agent365-python) 使用 Agent Framework 建構一個可實際運作的 agent。

整體而言，這個 repo 會協助您：

- 以 **Agent Framework** 搭配 `AzureOpenAIChatClient` 建立一個會話式 agent，並用 Microsoft 365 Agents SDK 進行 hosting。
- 在 agent 中整合 **observability（tracing/caching/監控）**、**notifications（通知）** 與 **MCP tools（工具）**。
- 在本機以 Agents Playground 進行測試，並驗證身分辨識、安裝事件與多則訊息等行為。

> 本 repo 已預先接好 `start_with_generic_host.py` 作為本機進入點。完整的概念與指引請參閱 [Microsoft Agent 365 開發者文件](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/)。

## 📑 目錄

- [✨ 這個範例示範什麼?](#features)
- [⚠️ 執行前的重要須知](#important-notes)
- [🗂️ 專案結構](#project-structure)
- [🧭 執行順序](#execution-order)
- [📚 官方參考與支援](#references)

<a id="features"></a>

## ✨ 這個範例示範什麼?

| 主題 | 說明 |
|---|---|
| **Observability（可觀測性）** | 為 agent 應用程式提供端對端 tracing、caching 與監控 |
| **Notifications（通知）** | 用於管理使用者通知的服務與模型 |
| **Tools（工具）** | 透過 Model Context Protocol（MCP）工具建構進階的 agent 解決方案 |
| **Hosting Patterns（託管模式）** | 使用 Microsoft 365 Agents SDK 進行 hosting |

**先決條件 Prerequisites：**

- Python 3.x
- Microsoft Agent 365 SDK
- Agent Framework（agent-framework-azure-ai）
- Azure/OpenAI API 憑證

如需 agent 程式碼與實作的逐步說明，請參閱 [Agent Code Walkthrough](AGENT-CODE-WALKTHROUGH.md)。

<a id="user-identity"></a>

## ⚠️ 執行前的重要須知

- 本 repo 使用 `AzureOpenAIChatClient`，因此要成功取得聊天回應，**必須**在 `.env` 中提供 `AZURE_OPENAI_API_KEY`、`AZURE_OPENAI_ENDPOINT`、`AZURE_OPENAI_DEPLOYMENT` 與 `AZURE_OPENAI_API_VERSION`。
- `AZURE_OPENAI_ENDPOINT` 必須設為 Azure OpenAI 資源的根路徑（例如 `https://your-resource.openai.azure.com/`），**請勿**在後面附加 `/openai/v1`。
- 進行本機開發時，**建議先以 bearer-token 方式測試**（`USE_AGENTIC_AUTH=false`、`AUTH_HANDLER_NAME=` 留空），確認基本流程可運作後再切換。
- agentic identity 在 Teams **不支援** streaming 回應；請改用 `send_activity` 送出討論結果。
- 若要改用 **agentic authentication**，需設定 `USE_AGENTIC_AUTH=true`、`AUTH_HANDLER_NAME=AGENTIC`，並從 `a365 config display -g` 填入 `CONNECTIONS__SERVICE_CONNECTION__SETTINGS__*` 的各項值。

<a id="project-structure"></a>

## 🗂️ 專案結構

```text
.
├── agent.py                     # Agent 主邏輯（建立 chat client、agent、MCP tools）
├── agent_interface.py           # Agent 介面定義
├── host_agent_server.py         # Hosting server（on_message、on_installation_update 等事件處理）
├── start_with_generic_host.py   # 本機進入點
├── local_authentication_options.py  # 本機驗證選項
├── token_cache.py               # Token 快取
├── agentsplayground             # Agents Playground 執行檔
├── .env.template                # 環境變數範本
├── pyproject.toml               # 專案與相依套件設定
├── AGENT-CODE-WALKTHROUGH.md    # Agent 程式碼逐步說明
├── manifest/                    # Agent manifest 與 blueprint metadata
├── publishAgent/                # 發布到 Admin Center 的步驟腳本
└── docs/                        # 設計文件
```

<a id="execution-order"></a>

## 🧭 執行順序

第一次使用這個 repo 時，建議按照下列步驟依序執行：

1. **Step 1：環境準備** - 安裝相依套件、建立 `.env`。
2. **Step 2：設定 Azure OpenAI** - 在 `.env` 中填入 Azure OpenAI 連線資訊。
3. **Step 3：取得 token** - 以 bearer-token 方式測試，取得 MCP tools 所需的 delegated token。
4. **Step 4：啟動 agent server** - 執行本機進入點。
5. **Step 5：啟動 Agents Playground** - 針對本機端點開啟測試介面。
6. **Step 6：驗證基本情境** - 確認 agent 回應、tools 清單與安裝事件。

> 若要設定並測試此 agent，亦可參閱官方 [Configure Agent Testing](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/testing?tabs=python) 指南。

### 🧰 Step 1：環境準備

安裝相依套件並建立本機環境檔案：

```bash
uv pip install -e .
cp .env.template .env
```

### 📝 Step 2：設定 Azure OpenAI

在 `.env` 中填入 Azure OpenAI 設定。此 repo 使用 `AzureOpenAIChatClient`，因此需要下列變數：

```bash
AZURE_OPENAI_API_KEY=<your-api-key>
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=<your-deployment-name>
AZURE_OPENAI_API_VERSION=<api-version>
```

請將 `AZURE_OPENAI_ENDPOINT` 設定為 Azure OpenAI 資源的根路徑，請勿在後面附加 `/openai/v1`。

### 🔑 Step 3：取得 token

進行本機開發時，建議先以 bearer-token 方式測試：

```bash
# keep these values for local testing
AUTH_HANDLER_NAME=
USE_AGENTIC_AUTH=false

# fetch a delegated token for MCP tools
a365 develop get-token
```

執行 `a365 develop get-token` 後，請確認 `.env` 中已包含 `BEARER_TOKEN=...`。

### 🚀 Step 4：啟動 agent server

```bash
uv run python start_with_generic_host.py
```

### 🧪 Step 5：啟動 Agents Playground

針對本機端點啟動 Agents Playground：

```bash
./agentsplayground -e "http://localhost:3978/api/messages" -c "emulator"
```

### ✅ Step 6：驗證基本情境

驗證測試指南中的基本情境：

- 傳送 `What can you do?` 以確認 agent 有回應。
- 在 `BEARER_TOKEN` 填入後，傳送 `List all tools I have access to`。
- 觸發安裝（install）事件，並確認出現歡迎訊息。

<a id="references"></a>

## 📚 官方參考與支援

- 程式碼逐步說明：[Agent Code Walkthrough](AGENT-CODE-WALKTHROUGH.md)
- Microsoft Agent 365 開發者文件：<https://learn.microsoft.com/en-us/microsoft-agent-365/developer/>
- [Microsoft Agent 365 SDK - Python repository](https://github.com/microsoft/Agent365-python)
- [Microsoft 365 Agents SDK - Python repository](https://github.com/Microsoft/Agents-for-python)
- [Agent Framework documentation](https://github.com/microsoft/Agent365-python/tree/main/packages/agent-framework)
- [Python API documentation](https://learn.microsoft.com/python/api/?view=m365-agents-sdk&preserve-view=true)

**支援 Support：**

- **Issues**：請於 [GitHub Issues](https://github.com/microsoft/Agent365-python/issues) 區段提出 issue
- **Security**：如有安全性問題，請參閱 [SECURITY.md](SECURITY.md)

## Contributing

This project welcomes contributions and suggestions. Most contributions require you to agree to a Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us the rights to use your contribution. For details, visit <https://cla.opensource.microsoft.com>.

When you submit a pull request, a CLA bot will automatically determine whether you need to provide a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/). For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

*Microsoft, Windows, Microsoft Azure and/or other Microsoft products and services referenced in the documentation may be either trademarks or registered trademarks of Microsoft in the United States and/or other countries. The licenses for this project do not grant you rights to use any Microsoft names, logos, or trademarks. Microsoft's general trademark guidelines can be found at http://go.microsoft.com/fwlink/?LinkID=254653.*

## License

Copyright (c) Microsoft Corporation. All rights reserved.

Licensed under the MIT License - see the [LICENSE](LICENSE.md) file for details.