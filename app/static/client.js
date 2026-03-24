(function () {
  const state = {
    roomId: "doubao",
    role: "landing",
    draftSaveTimer: null,
    retryTimer: null,
    lastVersion: 0,
    lastHistoryCount: 0,
    eventSource: null,
    flashTimer: null,
    reconnectTimer: null,
    pollTimer: null,
    mobileHydrated: false,
    pendingText: null,
  };

  const roomInput = document.getElementById("room-input");
  const reconnectButton = document.getElementById("reconnect-button");
  const archiveIdleInput = document.getElementById("archive-idle-input");
  const saveSettingsButton = document.getElementById("save-settings-button");
  const settingsStatus = document.getElementById("settings-status");
  const mobilePanel = document.getElementById("mobile-panel");
  const pcPanel = document.getElementById("pc-panel");
  const mobileEditor = document.getElementById("mobile-editor");
  const clearButton = document.getElementById("clear-button");
  const autoClearToggle = document.getElementById("auto-clear-toggle");
  const saveState = document.getElementById("save-state");
  const output = document.getElementById("pc-output");
  const copyButton = document.getElementById("copy-button");
  const refreshButton = document.getElementById("refresh-button");
  const connectionStatus = document.getElementById("connection-status");
  const versionBadge = document.getElementById("version-badge");
  const updatedAt = document.getElementById("updated-at");
  const sourceLine = document.getElementById("source-line");
  const title = document.getElementById("page-title");
  const subtitle = document.getElementById("page-subtitle");
  const historyList = document.getElementById("history-list");
  const syncFlash = document.getElementById("sync-flash");
  const archiveHint = document.getElementById("archive-hint");
  const autoClearStoragePrefix = "doubao-input-sync:auto-clear:";

  function inferRoleFromPath() {
    const parts = window.location.pathname.split("/").filter(Boolean);
    if (parts[0] === "mobile") {
      state.role = "mobile";
      state.roomId = parts[1] || "doubao";
      return;
    }
    if (parts[0] === "pc") {
      state.role = "pc";
      state.roomId = parts[1] || "doubao";
      return;
    }
    state.role = "landing";
    state.roomId = "doubao";
  }

  function setRoleView() {
    if (state.role === "mobile") {
      title.textContent = "手机输入区";
      subtitle.textContent = "把手机端的文字稳定送到同一个 room。";
      mobilePanel.hidden = false;
      pcPanel.hidden = true;
      return;
    }
    if (state.role === "pc") {
      title.textContent = "PC 同步区";
      subtitle.textContent = "主路径是同步页承接，并从自动存档列表随时重复制。";
      mobilePanel.hidden = true;
      pcPanel.hidden = false;
      return;
    }
    title.textContent = "同步服务已启动";
    subtitle.textContent = "你可以打开 /mobile/<room> 和 /pc/<room> 开始同步。";
    mobilePanel.hidden = false;
    pcPanel.hidden = false;
  }

  function autoClearStorageKey() {
    return `${autoClearStoragePrefix}${state.roomId}`;
  }

  function loadLocalPreferences() {
    autoClearToggle.checked = window.localStorage.getItem(autoClearStorageKey()) === "1";
  }

  function persistLocalPreferences() {
    window.localStorage.setItem(autoClearStorageKey(), autoClearToggle.checked ? "1" : "0");
  }

  function triggerFlash(message) {
    if (!syncFlash) {
      return;
    }
    syncFlash.textContent = message;
    syncFlash.classList.remove("is-active");
    void syncFlash.offsetWidth;
    syncFlash.classList.add("is-active");
    if (state.flashTimer) {
      window.clearTimeout(state.flashTimer);
    }
    state.flashTimer = window.setTimeout(function () {
      syncFlash.classList.remove("is-active");
    }, 1500);
  }

  function renderRoomState(payload) {
    const previousVersion = state.lastVersion;
    const previousHistoryCount = state.lastHistoryCount;
    const nextHistoryCount = (payload.history || []).length;

    state.lastVersion = payload.version;
    state.lastHistoryCount = nextHistoryCount;
    versionBadge.textContent = `version ${payload.version}`;
    updatedAt.textContent = payload.updated_at ? `updated at: ${payload.updated_at}` : "尚未收到内容";
    sourceLine.textContent = `source: ${payload.source || "-"}`;
    if (payload.settings && payload.settings.archive_idle_seconds) {
      archiveIdleInput.value = payload.settings.archive_idle_seconds;
      archiveHint.textContent = `输入停顿约 ${payload.settings.archive_idle_seconds} 秒后自动入档`;
    }
    if (state.role !== "mobile") {
      output.textContent = payload.text || "等待手机端输入…";
    }
    if (state.role === "mobile" && !state.mobileHydrated && document.activeElement !== mobileEditor) {
      mobileEditor.value = payload.text || "";
      state.mobileHydrated = true;
    }
    renderHistory(payload.history || []);

    if (nextHistoryCount > previousHistoryCount) {
      saveState.textContent = autoClearToggle.checked ? "已捕捉并同步，已自动清空" : "已捕捉并同步";
      triggerFlash("已捕捉并同步一批文字");
      if (state.role === "mobile" && autoClearToggle.checked) {
        mobileEditor.value = "";
      }
      return;
    }

    if (payload.version > previousVersion && previousVersion !== 0) {
      saveState.textContent = "已同步，等待稳定归档";
    }
  }

  function renderHistory(historyItems) {
    if (!historyItems.length) {
      historyList.innerHTML = '<div class="history-empty">还没有归档内容。</div>';
      return;
    }

    historyList.innerHTML = "";
    historyItems
      .slice()
      .reverse()
      .forEach(function (item) {
        const wrapper = document.createElement("article");
        wrapper.className = "history-card";

        const header = document.createElement("div");
        header.className = "history-header";
        header.innerHTML = `
          <strong>#${item.archive_id}</strong>
          <span>${item.archived_at}</span>
          <span>${item.chars} chars</span>
        `;

        const body = document.createElement("div");
        body.className = "history-text";
        body.textContent = item.text;

        const actions = document.createElement("div");
        actions.className = "inline-row actions";

        const copyItemButton = document.createElement("button");
        copyItemButton.type = "button";
        copyItemButton.textContent = "复制这一条";
        copyItemButton.addEventListener("click", async function () {
          await navigator.clipboard.writeText(item.text);
          connectionStatus.textContent = `已复制存档 #${item.archive_id}`;
          window.setTimeout(function () {
            connectionStatus.textContent = "已连接";
          }, 1200);
        });

        actions.appendChild(copyItemButton);
        wrapper.appendChild(header);
        wrapper.appendChild(body);
        wrapper.appendChild(actions);
        historyList.appendChild(wrapper);
      });
  }

  async function fetchState() {
    const response = await fetch(`/api/state?room_id=${encodeURIComponent(state.roomId)}`);
    const payload = await response.json();
    renderRoomState(payload);
  }

  async function fetchServerInfo() {
    const response = await fetch("/api/server-info");
    const payload = await response.json();
    if (payload.archive_idle_seconds) {
      archiveHint.textContent = `输入停顿约 ${payload.archive_idle_seconds} 秒后自动入档`;
      archiveIdleInput.value = payload.archive_idle_seconds;
    }
  }

  async function pushDraft(text) {
    saveState.textContent = "同步中…";
    state.pendingText = text;
    try {
      const response = await fetch("/api/update", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          room_id: state.roomId,
          text,
          source: "mobile-web",
        }),
      });
      const payload = await response.json();
      renderRoomState(payload);
      state.pendingText = null;
      saveState.textContent = "已同步";
    } catch (error) {
      saveState.textContent = "网络中断，自动重试中…";
      scheduleDraftRetry();
    }
  }

  function scheduleDraftRetry() {
    if (state.retryTimer || state.pendingText === null) {
      return;
    }
    state.retryTimer = window.setTimeout(function () {
      state.retryTimer = null;
      if (state.pendingText !== null) {
        pushDraft(state.pendingText);
      }
    }, 1200);
  }

  async function saveSettings() {
    settingsStatus.textContent = "保存中…";
    try {
      const response = await fetch("/api/settings", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          room_id: state.roomId,
          archive_idle_seconds: archiveIdleInput.value,
        }),
      });
      const payload = await response.json();
      renderRoomState(payload);
      settingsStatus.textContent = "已保存";
    } catch (error) {
      settingsStatus.textContent = "保存失败，请重试";
    }
  }

  function scheduleReconnect() {
    if (state.reconnectTimer) {
      return;
    }
    state.reconnectTimer = window.setTimeout(function () {
      state.reconnectTimer = null;
      connectStream();
    }, 1800);
  }

  function ensurePolling() {
    if (state.pollTimer) {
      return;
    }
    state.pollTimer = window.setInterval(function () {
      fetchState().catch(function () {
        connectionStatus.textContent = "已断开，轮询重试中";
      });
    }, 3000);
  }

  function stopPolling() {
    if (!state.pollTimer) {
      return;
    }
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }

  function connectStream() {
    if (state.eventSource) {
      state.eventSource.close();
    }

    connectionStatus.textContent = "连接中";
    const eventSource = new EventSource(`/api/stream?room_id=${encodeURIComponent(state.roomId)}`);
    state.eventSource = eventSource;

    eventSource.addEventListener("open", function () {
      connectionStatus.textContent = "已连接";
      stopPolling();
    });

    eventSource.addEventListener("error", function () {
      connectionStatus.textContent = "已断开，自动重连中";
      if (state.eventSource) {
        state.eventSource.close();
        state.eventSource = null;
      }
      ensurePolling();
      scheduleReconnect();
    });

    eventSource.addEventListener("room_state", function (event) {
      const payload = JSON.parse(event.data);
      renderRoomState(payload);
    });
  }

  function rebuildPath() {
    const nextRoom = roomInput.value.trim() || "doubao";
    const prefix = state.role === "pc" ? "/pc/" : "/mobile/";
    persistLocalPreferences();
    if (state.role === "landing") {
      window.location.href = `/pc/${encodeURIComponent(nextRoom)}`;
      return;
    }
    window.location.href = `${prefix}${encodeURIComponent(nextRoom)}`;
  }

  function bindEvents() {
    reconnectButton.addEventListener("click", rebuildPath);
    refreshButton.addEventListener("click", fetchState);
    saveSettingsButton.addEventListener("click", saveSettings);
    autoClearToggle.addEventListener("change", persistLocalPreferences);

    copyButton.addEventListener("click", async function () {
      const value = output.textContent === "等待手机端输入…" ? "" : output.textContent;
      await navigator.clipboard.writeText(value);
      connectionStatus.textContent = "已复制";
      window.setTimeout(function () {
        connectionStatus.textContent = "已连接";
      }, 1200);
    });

    clearButton.addEventListener("click", function () {
      mobileEditor.value = "";
      pushDraft("");
    });

    mobileEditor.addEventListener("input", function () {
      saveState.textContent = "输入中，自动同步中…";
      if (state.draftSaveTimer) {
        window.clearTimeout(state.draftSaveTimer);
      }
      state.draftSaveTimer = window.setTimeout(function () {
        pushDraft(mobileEditor.value);
      }, 180);
    });
  }

  inferRoleFromPath();
  setRoleView();
  roomInput.value = state.roomId;
  loadLocalPreferences();
  bindEvents();
  fetchState();
  fetchServerInfo();
  connectStream();
})();
