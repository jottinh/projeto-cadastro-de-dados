const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
const state = { user: null, chats: [], activeId: null, lastMessageId: 0, pendingPhone: "", pollTimer: null, polling: false };
const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const method = options.method || "GET";
  const headers = { Accept: "application/json" };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    headers["X-CSRFToken"] = csrfToken;
  }
  const response = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  let data = {};
  try { data = await response.json(); } catch (_) { data = {}; }
  if (!response.ok) {
    const error = new Error(data.error || "Não foi possível concluir a solicitação.");
    error.status = response.status;
    throw error;
  }
  return data;
}

function showNotice(selector, message, success = false) {
  const notice = $(selector);
  notice.textContent = message;
  notice.classList.toggle("success", success);
  notice.hidden = false;
}

function clearNotices() {
  document.querySelectorAll(".form-notice").forEach((notice) => {
    notice.hidden = true;
    notice.textContent = "";
    notice.classList.remove("success");
  });
}

function setAuthMode(mode) {
  clearNotices();
  $("#login-tab").classList.toggle("active", mode === "login");
  $("#register-tab").classList.toggle("active", mode === "register");
  $("#login-tab").setAttribute("aria-selected", String(mode === "login"));
  $("#register-tab").setAttribute("aria-selected", String(mode === "register"));
  $("#login-form").hidden = mode !== "login";
  $("#register-form").hidden = mode !== "register";
  $("#verify-form").hidden = mode !== "verify";
  $(".auth-tabs").hidden = mode === "verify";
  if (mode === "login") {
    $("#form-kicker").textContent = "BEM-VINDO DE VOLTA";
    $("#form-title").textContent = "Entre na sua conta";
    $("#form-description").textContent = "Use seu telefone e senha para continuar.";
  } else if (mode === "register") {
    $("#form-kicker").textContent = "UM NOVO COMEÇO";
    $("#form-title").textContent = "Crie sua conta";
    $("#form-description").textContent = "Cadastre seu telefone para encontrar pessoas.";
  } else {
    $("#form-kicker").textContent = "CONFIRME SEU TELEFONE";
    $("#form-title").textContent = "Só falta um passo";
    $("#form-description").textContent = `Confirme o número ${state.pendingPhone}.`;
  }
}

function showAuth(mode = "login") {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
  state.user = null;
  state.activeId = null;
  $("#chat-app").hidden = true;
  $("#auth-screen").hidden = false;
  setAuthMode(mode);
}

async function showApp(user) {
  state.user = user;
  state.activeId = null;
  state.lastMessageId = 0;
  $("#auth-screen").hidden = true;
  $("#chat-app").hidden = false;
  $("#chat-sidebar").classList.remove("mobile-hidden");
  $("#chat-main").classList.remove("mobile-hidden");
  $("#account-name").textContent = user.name;
  $("#account-phone").textContent = user.phone;
  $("#account-avatar").textContent = initials(user.name);
  await refreshChats();
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(poll, 2200);
}

function initials(name) {
  return String(name || "?").trim().split(/\s+/).slice(0, 2).map((part) => part[0] || "").join("").toUpperCase();
}

function setMobileView(showChat) {
  const mobile = window.matchMedia("(max-width: 680px)").matches;
  $("#chat-sidebar").classList.toggle("mobile-hidden", mobile && showChat);
  $("#chat-main").classList.toggle("mobile-hidden", mobile && !showChat);
}

function renderChats() {
  const list = $("#chat-list");
  const search = $("#chat-search").value.trim().toLocaleLowerCase("pt-BR");
  const chats = state.chats.filter((chat) => `${chat.name} ${chat.phone} ${chat.last_message}`.toLocaleLowerCase("pt-BR").includes(search));
  list.replaceChildren();
  if (!chats.length) {
    const empty = document.createElement("div");
    empty.className = "list-empty";
    empty.textContent = search ? "Nenhuma conversa encontrada." : "Ainda não há conversas. Adicione alguém pelo telefone.";
    list.append(empty);
    return;
  }
  chats.forEach((chat, index) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `chat-row${chat.id === state.activeId ? " selected" : ""}`;
    row.style.animationDelay = `${Math.min(index * 20, 120)}ms`;
    row.setAttribute("aria-label", `Abrir conversa com ${chat.name}`);
    const avatar = document.createElement("span");
    avatar.className = "row-avatar";
    avatar.textContent = initials(chat.name);
    const copy = document.createElement("span");
    copy.className = "row-copy";
    const top = document.createElement("span");
    top.className = "row-top";
    const name = document.createElement("span");
    name.className = "row-name";
    name.textContent = chat.name;
    const time = document.createElement("span");
    time.className = "row-time";
    time.textContent = chat.time || "";
    top.append(name, time);
    const bottom = document.createElement("span");
    bottom.className = "row-bottom";
    const preview = document.createElement("span");
    preview.className = "row-preview";
    preview.textContent = chat.last_message;
    bottom.append(preview);
    if (chat.unread > 0) {
      const badge = document.createElement("span");
      badge.className = "unread-count";
      badge.textContent = String(chat.unread);
      bottom.append(badge);
    }
    copy.append(top, bottom);
    row.append(avatar, copy);
    row.addEventListener("click", () => selectChat(chat.id));
    list.append(row);
  });
}

function appendMessage(message) {
  const line = document.createElement("div");
  line.className = `message-line${message.mine ? " mine" : ""}`;
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  const text = document.createElement("div");
  text.className = "message-text";
  text.textContent = message.text;
  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = message.time;
  bubble.append(text, meta);
  line.append(bubble);
  $("#messages").append(line);
}

async function loadMessages(reset = false) {
  if (!state.activeId) return;
  const chatId = state.activeId;
  if (reset) {
    state.lastMessageId = 0;
    const messages = $("#messages");
    messages.replaceChildren();
    const divider = document.createElement("div");
    divider.className = "day-divider";
    divider.textContent = "MENSAGENS";
    messages.append(divider);
  }
  const data = await api(`/api/chats/${chatId}/messages?after=${state.lastMessageId}`);
  if (chatId !== state.activeId) return;
  for (const message of data) {
    appendMessage(message);
    state.lastMessageId = Math.max(state.lastMessageId, message.id);
  }
  const area = $("#messages");
  area.scrollTop = area.scrollHeight;
  if (state.lastMessageId > 0) {
    await api(`/api/chats/${chatId}/read`, { method: "POST", body: { last_id: state.lastMessageId } });
  }
}

async function selectChat(chatId) {
  const chat = state.chats.find((item) => item.id === chatId);
  if (!chat) return;
  state.activeId = chatId;
  state.lastMessageId = 0;
  $("#welcome-state").hidden = true;
  $("#active-chat").hidden = false;
  $("#active-chat").style.display = "flex";
  $("#contact-name").textContent = chat.name;
  $("#contact-phone").textContent = chat.phone;
  $("#contact-avatar").textContent = initials(chat.name);
  setMobileView(true);
  renderChats();
  try {
    await loadMessages(true);
    await refreshChats(false);
    $("#message-input").focus();
  } catch (error) {
    handleApiError(error);
  }
}

async function refreshChats(selectFirst = false) {
  try {
    state.chats = await api("/api/chats");
    renderChats();
    if (selectFirst && state.chats.length) await selectChat(state.chats[0].id);
    if (!state.activeId || !state.chats.some((chat) => chat.id === state.activeId)) {
      state.activeId = null;
      $("#active-chat").hidden = true;
      $("#welcome-state").hidden = false;
      setMobileView(false);
    }
    if (state.activeId) {
      const active = state.chats.find((chat) => chat.id === state.activeId);
      $("#contact-name").textContent = active.name;
      $("#contact-phone").textContent = active.phone;
    }
    renderChats();
  } catch (error) {
    handleApiError(error);
  }
}

async function poll() {
  if (state.polling || !state.user) return;
  state.polling = true;
  try {
    state.chats = await api("/api/chats");
    renderChats();
    if (state.activeId && state.chats.some((chat) => chat.id === state.activeId)) {
      await loadMessages(false);
      await refreshChats(false);
    }
  } catch (error) {
    handleApiError(error);
  } finally {
    state.polling = false;
  }
}

function handleApiError(error) {
  if (error.status === 401) {
    showAuth("login");
    showNotice("#login-notice", "Sua sessão terminou. Entre novamente.");
    return;
  }
  showToast(error.message || "Não foi possível conectar ao servidor.");
}

let toastTimer;
function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, 3000);
}

function openContactModal() {
  $("#contact-modal").hidden = false;
  $("#contact-notice").hidden = true;
  $("#contact-phone-input").value = "";
  $("#contact-phone-input").focus();
}
function closeContactModal() {
  $("#contact-modal").hidden = true;
}

$("#login-tab").addEventListener("click", () => setAuthMode("login"));
$("#show-login-top").addEventListener("click", () => setAuthMode("login"));
$("#register-tab").addEventListener("click", () => setAuthMode("register"));
$("#back-to-register").addEventListener("click", () => setAuthMode("register"));

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearNotices();
  const form = event.currentTarget;
  const button = form.querySelector("[type=submit]");
  button.disabled = true;
  const values = new FormData(form);
  try {
    await api("/api/login", { method: "POST", body: { phone: values.get("phone"), password: values.get("password") } });
    window.location.reload();
  } catch (error) {
    showNotice("#login-notice", error.message);
  } finally { button.disabled = false; }
});

$("#register-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearNotices();
  const form = event.currentTarget;
  const button = form.querySelector("[type=submit]");
  button.disabled = true;
  const values = new FormData(form);
  state.pendingPhone = String(values.get("phone")).trim();
  try {
    const result = await api("/api/register", { method: "POST", body: {
      name: values.get("name"), phone: values.get("phone"), password: values.get("password"),
    } });
    showNotice("#verify-notice", result.message, true);
    setAuthMode("verify");
    $("#verify-code").focus();
  } catch (error) {
    showNotice("#register-notice", error.message);
  } finally { button.disabled = false; }
});

$("#verify-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearNotices();
  const button = event.currentTarget.querySelector("[type=submit]");
  button.disabled = true;
  try {
    await api("/api/verify", { method: "POST", body: { phone: state.pendingPhone, code: $("#verify-code").value } });
    window.location.reload();
  } catch (error) {
    showNotice("#verify-notice", error.message);
  } finally { button.disabled = false; }
});

$("#open-contact").addEventListener("click", openContactModal);
$("#welcome-contact").addEventListener("click", openContactModal);
$("#close-contact").addEventListener("click", closeContactModal);
$("#cancel-contact").addEventListener("click", closeContactModal);
$("#contact-modal").addEventListener("click", (event) => { if (event.target === event.currentTarget) closeContactModal(); });
$("#contact-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("[type=submit]");
  button.disabled = true;
  $("#contact-notice").hidden = true;
  try {
    const chat = await api("/api/contacts", { method: "POST", body: { phone: $("#contact-phone-input").value } });
    closeContactModal();
    await refreshChats();
    await selectChat(chat.id);
  } catch (error) {
    showNotice("#contact-notice", error.message);
  } finally { button.disabled = false; }
});

$("#message-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("#message-input");
  const text = input.value.trim();
  if (!text || !state.activeId) return;
  const button = event.currentTarget.querySelector("[type=submit]");
  button.disabled = true;
  try {
    const message = await api(`/api/chats/${state.activeId}/messages`, { method: "POST", body: { text } });
    appendMessage(message);
    state.lastMessageId = Math.max(state.lastMessageId, message.id);
    input.value = "";
    await refreshChats();
    input.focus();
    $("#messages").scrollTop = $("#messages").scrollHeight;
  } catch (error) {
    showToast(error.message);
  } finally { button.disabled = false; }
});

$("#chat-search").addEventListener("input", renderChats);
$("#mobile-back").addEventListener("click", () => setMobileView(false));
$("#logout-button").addEventListener("click", async () => {
  try { await api("/api/logout", { method: "POST", body: {} }); }
  catch (error) { showToast(error.message); }
  showAuth("login");
});

(async function start() {
  try {
    await showApp(await api("/api/me"));
  } catch (_) {
    showAuth("login");
  }
})();
