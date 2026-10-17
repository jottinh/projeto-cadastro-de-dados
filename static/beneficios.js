const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
const state = { setupRequired: false, records: [] };
const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const headers = { Accept: "application/json" };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    headers["X-CSRFToken"] = csrfToken;
  }
  const response = await fetch(path, {
    method: options.method || "GET",
    credentials: "same-origin",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  let result = {};
  try { result = await response.json(); } catch (_) { result = {}; }
  if (!response.ok) {
    const error = new Error(result.error || "Não foi possível concluir a solicitação.");
    error.status = response.status;
    throw error;
  }
  return result;
}

function notice(selector, message, success = false) {
  const element = $(selector);
  element.textContent = message;
  element.classList.toggle("success", success);
  element.hidden = false;
}

function clearNotices() {
  document.querySelectorAll(".notice").forEach((element) => {
    element.hidden = true;
    element.textContent = "";
    element.classList.remove("success");
  });
}

function showAuth(setupRequired, message = "") {
  state.setupRequired = setupRequired;
  $("#dashboard").hidden = true;
  $("#auth-screen").hidden = false;
  $("#setup-form").hidden = !setupRequired;
  $("#login-form").hidden = setupRequired;
  $("#auth-kicker").textContent = setupRequired ? "PRIMEIRO ACESSO" : "ACESSO ADMINISTRATIVO";
  $("#auth-title").textContent = setupRequired ? "Configure a administração" : "Entre no painel";
  $("#auth-description").textContent = setupRequired
    ? "Crie o acesso administrativo para este computador."
    : "Informe suas credenciais para continuar.";
  clearNotices();
  if (message) notice(setupRequired ? "#setup-notice" : "#login-notice", message);
}

function moneyLabel(value) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(value));
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { toast.hidden = true; }, 3000);
}

async function showDashboard(username) {
  $("#auth-screen").hidden = true;
  $("#dashboard").hidden = false;
  $("#admin-label").textContent = username;
  await loadRecords();
}

function renderRecords() {
  const body = $("#records-body");
  const query = $("#search-input").value.trim().toLocaleLowerCase("pt-BR");
  const records = state.records.filter((record) => `${record.name} ${record.reference}`.toLocaleLowerCase("pt-BR").includes(query));
  body.replaceChildren();
  $("#empty-state").hidden = state.records.length > 0;
  $("#records-count").textContent = `${state.records.length} ${state.records.length === 1 ? "registro" : "registros"}`;
  if (!state.records.length) return;

  for (const record of records) {
    const row = document.createElement("tr");
    const nameCell = document.createElement("td");
    nameCell.className = "name-cell";
    nameCell.textContent = record.name;
    const reference = document.createElement("span");
    reference.className = "reference";
    reference.textContent = record.reference;
    nameCell.append(reference);

    const household = document.createElement("td");
    household.textContent = `${record.household_size} ${record.household_size === 1 ? "pessoa" : "pessoas"}`;
    const category = document.createElement("td");
    category.textContent = record.benefit_type;
    const monthly = document.createElement("td");
    monthly.className = "monthly-cell";
    monthly.textContent = moneyLabel(record.monthly_value);
    const balance = document.createElement("td");
    balance.className = "balance-cell";
    balance.textContent = moneyLabel(record.balance);
    const statusCell = document.createElement("td");
    const status = document.createElement("span");
    status.className = `status-pill status-${record.status.toLocaleLowerCase("pt-BR")}`;
    status.textContent = record.status;
    statusCell.append(status);

    const actions = document.createElement("td");
    const actionGroup = document.createElement("div");
    actionGroup.className = "row-actions";
    const adjust = document.createElement("button");
    adjust.className = "action-button";
    adjust.type = "button";
    adjust.title = "Ajustar saldo";
    adjust.textContent = "Saldo";
    adjust.addEventListener("click", () => openBalance(record));
    const history = document.createElement("button");
    history.className = "action-button";
    history.type = "button";
    history.title = "Ver histórico do saldo";
    history.textContent = "Histórico";
    history.addEventListener("click", () => openHistory(record));
    actionGroup.append(adjust, history);
    actions.append(actionGroup);

    row.append(nameCell, household, category, monthly, balance, statusCell, actions);
    body.append(row);
  }
  if (!records.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 7;
    cell.className = "list-empty";
    cell.textContent = "Nenhum cadastro encontrado com esse filtro.";
    row.append(cell);
    body.append(row);
  }
}

async function loadRecords() {
  try {
    const result = await api("/api/beneficiaries");
    state.records = result.entries;
    $("#stat-count").textContent = result.stats.count;
    $("#stat-active").textContent = result.stats.active;
    $("#stat-balance").textContent = moneyLabel(result.stats.balance);
    renderRecords();
  } catch (error) {
    if (error.status === 401) {
      const status = await api("/api/session");
      showAuth(status.setup_required, "Sua sessão terminou. Entre novamente.");
    } else {
      showToast(error.message);
    }
  }
}

function openModal(id) {
  $(id).hidden = false;
  const firstInput = $(id).querySelector("input, textarea, select");
  if (firstInput) firstInput.focus();
}

function closeModal(id) {
  $(id).hidden = true;
}

function openBalance(record) {
  $("#balance-form").dataset.recordId = record.id;
  $("#balance-record-name").textContent = record.name;
  $("#new-balance").value = Number(record.balance).toFixed(2).replace(".", ",");
  $("#balance-reason").value = "";
  $("#balance-notice").hidden = true;
  openModal("#balance-modal");
}

async function openHistory(record) {
  $("#history-record-name").textContent = `${record.name} · ${record.reference}`;
  const list = $("#history-list");
  list.replaceChildren();
  openModal("#history-modal");
  try {
    const entries = await api(`/api/beneficiaries/${record.id}/history`);
    if (!entries.length) {
      const empty = document.createElement("div");
      empty.className = "history-empty";
      empty.textContent = "Ainda não há movimentações.";
      list.append(empty);
      return;
    }
    for (const entry of entries) {
      const item = document.createElement("article");
      item.className = "history-entry";
      const top = document.createElement("div");
      top.className = "history-top";
      const change = document.createElement("span");
      change.textContent = `${moneyLabel(entry.old_balance)} → ${moneyLabel(entry.new_balance)}`;
      const date = document.createElement("time");
      date.textContent = entry.date;
      top.append(change, date);
      const reason = document.createElement("p");
      reason.textContent = entry.reason;
      const admin = document.createElement("small");
      admin.textContent = `Registrado por ${entry.admin}`;
      item.append(top, reason, admin);
      list.append(item);
    }
  } catch (error) {
    closeModal("#history-modal");
    showToast(error.message);
  }
}

$("#setup-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("[type=submit]");
  button.disabled = true;
  const values = new FormData(form);
  try {
    await api("/api/setup", { method: "POST", body: { username: values.get("username"), password: values.get("password") } });
    window.location.reload();
  } catch (error) {
    notice("#setup-notice", error.message);
  } finally { button.disabled = false; }
});

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("[type=submit]");
  button.disabled = true;
  const values = new FormData(form);
  try {
    await api("/api/login", { method: "POST", body: { username: values.get("username"), password: values.get("password") } });
    window.location.reload();
  } catch (error) {
    notice("#login-notice", error.message);
  } finally { button.disabled = false; }
});

$("#new-record").addEventListener("click", () => {
  $("#record-form").reset();
  $("#record-notice").hidden = true;
  openModal("#record-modal");
});
$("#empty-new-record").addEventListener("click", () => $("#new-record").click());

$("#record-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("[type=submit]");
  const values = new FormData(form);
  button.disabled = true;
  try {
    const result = await api("/api/beneficiaries", { method: "POST", body: {
      name: values.get("name"), household_size: values.get("household_size"),
      benefit_type: values.get("benefit_type"), monthly_value: values.get("monthly_value"),
      balance: values.get("balance"), status: values.get("status"),
    } });
    closeModal("#record-modal");
    await loadRecords();
    showToast(`Cadastro ${result.reference} criado.`);
  } catch (error) {
    notice("#record-notice", error.message);
  } finally { button.disabled = false; }
});

$("#balance-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("[type=submit]");
  button.disabled = true;
  try {
    await api(`/api/beneficiaries/${form.dataset.recordId}/balance`, { method: "POST", body: {
      balance: $("#new-balance").value, reason: $("#balance-reason").value,
    } });
    closeModal("#balance-modal");
    await loadRecords();
    showToast("Saldo de demonstração atualizado e registrado no histórico.");
  } catch (error) {
    notice("#balance-notice", error.message);
  } finally { button.disabled = false; }
});

$("#search-input").addEventListener("input", renderRecords);
$("#logout-button").addEventListener("click", async () => {
  try {
    await api("/api/logout", { method: "POST", body: {} });
    window.location.reload();
  } catch (error) { showToast(error.message); }
});

document.querySelectorAll("[data-close]").forEach((button) => {
  button.addEventListener("click", () => closeModal(`#${button.dataset.close}`));
});
document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) closeModal(`#${backdrop.id}`);
  });
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") document.querySelectorAll(".modal-backdrop:not([hidden])").forEach((modal) => closeModal(`#${modal.id}`));
});

(async function start() {
  try {
    const status = await api("/api/session");
    if (!status.authenticated) {
      showAuth(status.setup_required);
      return;
    }
    await showDashboard(status.username);
  } catch (error) {
    showAuth(true, error.message);
  }
})();
