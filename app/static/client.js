(function () {
  const state = {
    roomId: "doubao",
    role: "landing",
    draftSaveTimer: null,
    lastVersion: 0,
    eventSource: null,
  };

  const roomInput = document.getElementById("room-input");
  const reconnectButton = document.getElementById("reconnect-button");
  const mobilePanel = document.getElementById("mobile-panel");
  const pcPanel = document.getElementById("pc-panel");
  const mobileEditor = document.getElementById("mobile-editor");
  const clearButton = document.getElementById("clear-button");
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

  function renderRoomState(payload) {
    state.lastVersion = payload.version;
    versionBadge.textContent = `version ${payload.version}`;
    updatedAt.textContent = payload.updated_at ? `updated at: ${payload.updated_at}` : "尚未收到内容";
    sourceLine.textContent = `source: ${payload.source || "-"}`;
    if (state.role !== "mobile") {
      output.textContent = payload.text || "等待手机端输入…";
    }
    if (state.role === "mobile" && document.activeElement !== mobileEditor) {
      mobileEditor.value = payload.text || "";
    }
    renderHistory(payload.history || []);
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

  async function pushDraft(text) {
    saveState.textContent = "同步中…";
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
    saveState.textContent = "已同步";
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
    });

    eventSource.addEventListener("error", function () {
      connectionStatus.textContent = "已断开，自动重连中";
    });

    eventSource.addEventListener("room_state", function (event) {
      const payload = JSON.parse(event.data);
      renderRoomState(payload);
    });
  }

  function rebuildPath() {
    const nextRoom = roomInput.value.trim() || "doubao";
    const prefix = state.role === "pc" ? "/pc/" : "/mobile/";
    if (state.role === "landing") {
      window.location.href = `/pc/${encodeURIComponent(nextRoom)}`;
      return;
    }
    window.location.href = `${prefix}${encodeURIComponent(nextRoom)}`;
  }

  function bindEvents() {
    reconnectButton.addEventListener("click", rebuildPath);
    refreshButton.addEventListener("click", fetchState);

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
  bindEvents();
  fetchState();
  connectStream();
})();
