# Agent Framework 範例 Agent — Python

本範例示範如何在 Python 中，搭配 Microsoft Agent 365 SDK 使用 Agent Framework 來建構 agent。內容涵蓋：

- **Observability（可觀測性）**：為 agent 應用程式提供端對端 tracing、caching 與監控
- **Notifications（通知）**：用於管理使用者通知的服務與模型
- **Tools（工具）**：透過 Model Context Protocol 工具建構進階的 agent 解決方案
- **Hosting Patterns（託管模式）**：使用 Microsoft 365 Agents SDK 進行託管

本範例使用 [Microsoft Agent 365 SDK for Python](https://github.com/microsoft/Agent365-python)。

如需更完整的文件與指引，了解如何使用 Microsoft Agent 365 SDK 建構 agent（包含如何加入 tooling、observability 與 notifications），請參閱 [Microsoft Agent 365 開發者文件](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/)。

## 先決條件 Prerequisites

- Python 3.x
- Microsoft Agent 365 SDK
- Agent Framework（agent-framework-azure-ai）
- Azure/OpenAI API 憑證

## 使用使用者身分 Working with User Identity

每當有訊息傳入時，A365 平台都會在 `activity.from_property` 中填入基本的使用者資訊——這些資訊隨時可用，不需要任何 API 呼叫或取得 token：

| 欄位 | 說明 |
|---|---|
| `activity.from_property.id` | 通道專屬的使用者 ID（例如 Teams 中的 `29:1AbcXyz...`） |
| `activity.from_property.name` | 通道所認得的顯示名稱 |
| `activity.from_property.aad_object_id` | Azure AD Object ID——用於呼叫 Microsoft Graph |

本範例會在每個訊息回合（turn）開始時記錄這些欄位，並將顯示名稱注入到 LLM 的 system instructions 中，以提供個人化的回應。

## 處理 Agent 的安裝與解除安裝 Handling Agent Install and Uninstall

當使用者安裝（hire，僱用）或解除安裝（remove，移除）agent 時，A365 平台會送出一個 `InstallationUpdate` activity——也稱為 `agentInstanceCreated` 事件。本範例在 `host_agent_server.py` 的 `on_installation_update` 中處理此事件：

| 動作 | 說明 |
|---|---|
| `add` | agent 已安裝——送出歡迎訊息 |
| `remove` | agent 已解除安裝——送出道別訊息 |

```python
if action == "add":
    await context.send_activity("Thank you for hiring me! Looking forward to assisting you in your professional journey!")
elif action == "remove":
    await context.send_activity("Thank you for your time, I enjoyed working with you.")
```

若要使用 Agents Playground 進行測試，請使用 **Mock an Activity → Install application** 來送出模擬的 `installationUpdate` activity。

## 在 Teams 中傳送多則訊息 Sending Multiple Messages in Teams

Agent365 agent 可以針對 Teams 中單一使用者提示（prompt），回應多則獨立的訊息。做法是在單一回合（turn）中多次呼叫 `send_activity`。

> **重要**：agentic identity 不支援串流（streaming）回應。SDK 偵測到 agentic identity 時，會將串流緩衝（buffer）成單一訊息。請直接使用 `send_activity` 向使用者送出即時且獨立的訊息。

本範例在 `on_message`（[host_agent_server.py](host_agent_server.py)）中示範此做法：

```python
# Message 1: immediate ack — reaches the user right away
await context.send_activity("Got it — working on it…")

# Send typing indicator immediately (awaited so it arrives before the LLM call starts).
await context.send_activity(Activity(type="typing"))

# Background loop refreshes the "..." animation every ~4s (it times out after ~5s).
async def _typing_loop():
    try:
        while True:
            await asyncio.sleep(4)
            await context.send_activity(Activity(type="typing"))
    except asyncio.CancelledError:
        pass  # Expected on cancel.

typing_task = asyncio.create_task(_typing_loop())
try:
    response = await agent.process_user_message(...)
    # Message 2: the LLM response
    await context.send_activity(response)
finally:
    typing_task.cancel()
    try:
        await typing_task
    except asyncio.CancelledError:
        pass
```

每一次呼叫 `send_activity` 都會產生一則獨立的 Teams 訊息。您可以視需要多次呼叫，以送出進度更新、部分結果或最終答案。

### 輸入中指示器 Typing Indicators

- 輸入中指示器會在 Teams 顯示「...」進度動畫
- 它內建約 5 秒的視覺逾時，必須在迴圈中每約 4 秒重新整理一次
- 僅在一對一聊天與小型群組聊天中可見——在頻道（channel）中看不到

## 執行 Agent Running the Agent

若要設定並測試此 agent，請參閱 [Configure Agent Testing](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/testing?tabs=python) 指南，以取得完整說明。

### 本機測試設定 Local Testing Setup For This Repo

此範例已預先設定為使用 `start_with_generic_host.py` 作為本機進入點：

```bash
uv run python start_with_generic_host.py
```

請依照下列專屬於此 repo 的流程，以對應官方指南：

1. 安裝相依套件：

```bash
uv pip install -e .
```

1. 建立您的本機環境檔案：

```bash
cp .env.template .env
```

1. 在 `.env` 中填入 Azure OpenAI 設定。

此 repo 使用 `AzureOpenAIChatClient`，因此要成功取得聊天回應，需要 `AZURE_OPENAI_API_KEY`、`AZURE_OPENAI_ENDPOINT`、`AZURE_OPENAI_DEPLOYMENT` 與 `AZURE_OPENAI_API_VERSION`。

請將 `AZURE_OPENAI_ENDPOINT` 設定為 Azure OpenAI 資源的根路徑，例如 `https://your-resource.openai.azure.com/`。請勿在後面附加 `/openai/v1`。

1. 進行本機開發時，建議先以 bearer-token 方式測試：

```bash
# keep these values for local testing
AUTH_HANDLER_NAME=
USE_AGENTIC_AUTH=false

# fetch a delegated token for MCP tools
a365 develop get-token
```

執行 `a365 develop get-token` 後，請確認 `.env` 中已包含 `BEARER_TOKEN=...`。

1. 啟動 agent server：

```bash
uv run python start_with_generic_host.py
```

1. 針對本機端點啟動 Agents Playground：

```bash
./agentsplayground -e "http://localhost:3978/api/messages" -c "emulator"
```

1. 驗證測試指南中的基本情境：

- 傳送 `What can you do?` 以確認 agent 有回應。
- 在 `BEARER_TOKEN` 填入後，傳送 `List all tools I have access to`。
- 觸發安裝（install）事件，並確認出現歡迎訊息。

若您之後想切換為 agentic authentication，請將 `USE_AGENTIC_AUTH=true`、`AUTH_HANDLER_NAME=AGENTIC`，並從 `a365 config display -g` 填入 `CONNECTIONS__SERVICE_CONNECTION__SETTINGS__*` 的各項值。

如需 agent 程式碼與實作的詳細說明，請參閱 [Agent Code Walkthrough](AGENT-CODE-WALKTHROUGH.md)。

## 支援 Support

如有問題、疑問或意見回饋：

- **Issues**：請於 [GitHub Issues](https://github.com/microsoft/Agent365-python/issues) 區段提出 issue
- **Documentation**：請參閱 [Microsoft Agents 365 開發者文件](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/)
- **Security**：如有安全性問題，請參閱 [SECURITY.md](SECURITY.md)

## Contributing

This project welcomes contributions and suggestions. Most contributions require you to agree to a Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us the rights to use your contribution. For details, visit <https://cla.opensource.microsoft.com>.

When you submit a pull request, a CLA bot will automatically determine whether you need to provide a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/). For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## 其他資源 Additional Resources

- [Microsoft Agent 365 SDK - Python repository](https://github.com/microsoft/Agent365-python)
- [Microsoft 365 Agents SDK - Python repository](https://github.com/Microsoft/Agents-for-python)
- [Agent Framework documentation](https://github.com/microsoft/Agent365-python/tree/main/packages/agent-framework)
- [Python API documentation](https://learn.microsoft.com/python/api/?view=m365-agents-sdk&preserve-view=true)

## Trademarks

*Microsoft, Windows, Microsoft Azure and/or other Microsoft products and services referenced in the documentation may be either trademarks or registered trademarks of Microsoft in the United States and/or other countries. The licenses for this project do not grant you rights to use any Microsoft names, logos, or trademarks. Microsoft's general trademark guidelines can be found at http://go.microsoft.com/fwlink/?LinkID=254653.*

## License

Copyright (c) Microsoft Corporation. All rights reserved.

Licensed under the MIT License - see the [LICENSE](LICENSE.md) file for details.