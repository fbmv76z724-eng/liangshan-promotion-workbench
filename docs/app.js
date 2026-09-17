import {
  TEAMS,
  filterAndSortDrivers,
  filterTodayDrivers,
  formatFlag,
  flagTitle,
  formatNumber,
  normalizeId,
  ordersForEmployee,
  searchDrivers,
  summarizeTransfers,
  summarizeToday,
} from "./logic.mjs?v=20260917-6";

const TAB_NAMES = new Set(["teams", "drivers", "orders", "today"]);
const LOCAL_REFRESH_URL = "http://127.0.0.1:18765";
const ORDER_FLAGS = [
  "nonOffline",
  "abnormalScan",
  "burner",
  "regularCustomer",
  "cheating",
];

const elements = {
  appContent: document.querySelector("#app-content"),
  driverQuery: document.querySelector("#driver-query"),
  driverResults: document.querySelector("#driver-results"),
  driverSearchForm: document.querySelector("#driver-search-form"),
  driverSearchStatus: document.querySelector("#driver-search-status"),
  loadState: document.querySelector("#load-state"),
  orderQuery: document.querySelector("#order-query"),
  orderResults: document.querySelector("#order-results"),
  orderSearchForm: document.querySelector("#order-search-form"),
  orderSearchStatus: document.querySelector("#order-search-status"),
  periodLabel: document.querySelector("#period-label"),
  syncLabel: document.querySelector("#sync-label"),
  teamCount: document.querySelector("#team-count"),
  teamCompletionFilter: document.querySelector("#team-completion-filter"),
  teamDrivers: document.querySelector("#team-drivers"),
  teamOptions: document.querySelector("#team-options"),
  teamSortBy: document.querySelector("#team-sort-by"),
  teamSortDirection: document.querySelector("#team-sort-direction"),
  teamTitle: document.querySelector("#team-title"),
  teamUpdated: document.querySelector("#team-updated"),
  todayDrivers: document.querySelector("#today-drivers"),
  todayOnlyCompleted: document.querySelector("#today-only-completed"),
  todayQuery: document.querySelector("#today-query"),
  todayRefresh: document.querySelector("#today-refresh"),
  todayRefreshed: document.querySelector("#today-refreshed"),
  todaySearchForm: document.querySelector("#today-search-form"),
  todaySearchStatus: document.querySelector("#today-search-status"),
  todayTeamCount: document.querySelector("#today-team-count"),
  todayTeamOptions: document.querySelector("#today-team-options"),
  todayTeamTitle: document.querySelector("#today-team-title"),
  todayUpdated: document.querySelector("#today-updated"),
};

let snapshot = null;
let todaySnapshot = null;
let selectedTeam = TEAMS[0];
let selectedTodayTeam = TEAMS[0];
let teamCompletionFilter = "all";
let teamSortBy = "realTransfers";
let teamSortDirection = "desc";
let lastTodayFetchAt = 0;
let todayOnlyCompleted = false;
let todayRefreshInProgress = false;

class LocalRefreshUnavailable extends Error {}
class LocalRefreshFailed extends Error {}

function tabFromHash() {
  const candidate = window.location.hash.replace(/^#/, "");
  return TAB_NAMES.has(candidate) ? candidate : "teams";
}

function setActiveTab(tab, updateHash = true) {
  const activeTab = TAB_NAMES.has(tab) ? tab : "teams";

  document.querySelectorAll("[data-tab]").forEach((button) => {
    const selected = button.dataset.tab === activeTab;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  });

  document.querySelectorAll("[role='tabpanel']").forEach((panel) => {
    panel.hidden = panel.id !== `panel-${activeTab}`;
  });

  if (updateHash && window.location.hash !== `#${activeTab}`) {
    window.history.pushState(null, "", `#${activeTab}`);
  }
}

function createTextElement(tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) {
    element.className = className;
  }
  element.textContent = text;
  return element;
}

function createStateMessage(title, detail) {
  const wrapper = document.createElement("div");
  wrapper.className = "empty-state";
  wrapper.append(
    createTextElement("strong", "", title),
    createTextElement("span", "", detail),
  );
  return wrapper;
}

function createMetric(label, value, tone = "") {
  const metric = document.createElement("div");
  metric.className = `metric ${tone}`.trim();
  metric.append(
    createTextElement("span", "metric-label", label),
    createTextElement("strong", "metric-value", value),
  );
  return metric;
}

function createDriverCard(driver) {
  const card = document.createElement("article");
  card.className = `driver-card ${driver.promotionCompleted ? "is-completed" : "is-unfinished"}`;

  const identity = document.createElement("div");
  identity.className = "driver-identity";
  const nameLine = document.createElement("div");
  nameLine.className = "driver-name-line";
  nameLine.append(
    createTextElement("strong", "driver-name", driver.name),
    createTextElement("span", "team-badge", driver.team),
    createTextElement(
      "span",
      `completion-badge ${driver.promotionCompleted ? "is-complete" : "is-incomplete"}`,
      driver.promotionCompleted ? "本月已完成" : "本月未完成",
    ),
  );
  identity.append(
    nameLine,
    createTextElement("span", "driver-id", `工号 ${normalizeId(driver.employeeId)}`),
  );

  const metrics = document.createElement("div");
  metrics.className = "metric-grid";
  metrics.append(
    createMetric("出车天数", formatNumber(driver.outDays)),
    createMetric("真实转单", formatNumber(driver.realTransfers), "metric-positive"),
    createMetric(
      "推广次数",
      formatNumber(driver.promotionCount),
      "metric-accent",
    ),
    createMetric(
      "推广差值",
      formatNumber(driver.promotionDelta),
      Number(driver.promotionDelta) < 0 ? "metric-negative" : "metric-accent",
    ),
  );

  card.append(identity, metrics);
  return card;
}

function createTodayDriverCard(driver) {
  const card = document.createElement("article");
  card.className = `driver-card today-driver-card ${driver.completed ? "is-completed" : "is-unfinished"}`;

  const identity = document.createElement("div");
  identity.className = "driver-identity";
  const nameLine = document.createElement("div");
  nameLine.className = "driver-name-line";
  nameLine.append(
    createTextElement("strong", "driver-name", driver.name),
    createTextElement("span", "team-badge", driver.team),
    createTextElement(
      "span",
      `completion-badge ${driver.completed ? "is-complete" : "is-incomplete"}`,
      driver.completed ? "今日已完成" : "今日未完成",
    ),
  );
  identity.append(
    nameLine,
    createTextElement("span", "driver-id", `工号 ${normalizeId(driver.employeeId)}`),
  );

  card.append(identity);
  return card;
}

function renderDriverCollection(container, drivers, emptyTitle, emptyDetail) {
  container.replaceChildren();
  if (!drivers.length) {
    container.append(createStateMessage(emptyTitle, emptyDetail));
    return;
  }
  container.append(...drivers.map(createDriverCard));
}

function renderTeamOptions() {
  elements.teamOptions.replaceChildren();
  TEAMS.forEach((team) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "team-option";
    button.textContent = team;
    button.setAttribute("aria-pressed", String(team === selectedTeam));
    button.addEventListener("click", () => {
      selectedTeam = team;
      renderTeamOptions();
      renderSelectedTeam();
    });
    elements.teamOptions.append(button);
  });
}

function renderSelectedTeam() {
  const teamDrivers = snapshot.drivers.filter(
    (driver) => driver.team === selectedTeam,
  );
  const drivers = filterAndSortDrivers(teamDrivers, {
    completion: teamCompletionFilter,
    sortBy: teamSortBy,
    direction: teamSortDirection,
  });
  elements.teamTitle.textContent = selectedTeam;
  elements.teamCount.textContent = `${drivers.length} / ${teamDrivers.length} 人`;
  renderDriverCollection(
    elements.teamDrivers,
    drivers,
    "该队伍暂无司机",
    "请检查最近一次同步数据。",
  );
}

function renderDriverSearch() {
  const query = elements.driverQuery.value.trim();
  if (!query) {
    elements.driverSearchStatus.textContent = "请输入姓名或工号。";
    elements.driverResults.replaceChildren();
    return;
  }

  const results = searchDrivers(snapshot.drivers, query);
  elements.driverSearchStatus.textContent = `找到 ${results.length} 位司机。`;
  renderDriverCollection(
    elements.driverResults,
    results,
    "没有找到对应司机",
    "请检查姓名是否正确，或改用工号精确查询。",
  );
}

function renderTodayTeamOptions() {
  elements.todayTeamOptions.replaceChildren();
  TEAMS.forEach((team) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "team-option";
    button.textContent = team;
    button.setAttribute("aria-pressed", String(team === selectedTodayTeam));
    button.addEventListener("click", () => {
      selectedTodayTeam = team;
      elements.todayQuery.value = "";
      renderTodayTeamOptions();
      renderTodayDrivers();
    });
    elements.todayTeamOptions.append(button);
  });
}

function renderTodayMeta(clientRefreshAt = "") {
  if (!todaySnapshot) {
    elements.todayUpdated.textContent = "今日数据暂不可用";
    elements.todayRefreshed.textContent = "";
    return;
  }
  elements.todayUpdated.textContent =
    `数据更新 ${formatSyncTime(todaySnapshot.meta.syncedAt)}`;
  elements.todayRefreshed.textContent = clientRefreshAt
    ? `页面刷新 ${formatSyncTime(clientRefreshAt)}`
    : "";
}

function renderTodayDrivers() {
  if (!todaySnapshot) {
    elements.todayTeamTitle.textContent = "今日推广";
    elements.todayTeamCount.textContent = "";
    elements.todaySearchStatus.textContent = "";
    elements.todayDrivers.replaceChildren(
      createStateMessage(
        "今日数据暂不可用",
        "页面会在下一次自动刷新时重试。",
      ),
    );
    return;
  }

  const query = elements.todayQuery.value.trim();
  const drivers = filterTodayDrivers(todaySnapshot.drivers, {
    team: query ? "" : selectedTodayTeam,
    query,
    onlyCompleted: todayOnlyCompleted,
  });
  const summary = summarizeToday(drivers);
  elements.todayTeamTitle.textContent = query ? "查询结果" : selectedTodayTeam;
  elements.todayTeamCount.textContent =
    `未完成 ${summary.unfinished} · 已完成 ${summary.completed}`;
  elements.todaySearchStatus.textContent = query
    ? `找到 ${summary.total} 位司机。`
    : "";
  elements.todayDrivers.replaceChildren();
  if (!drivers.length) {
    elements.todayDrivers.append(
      createStateMessage(
        query
          ? "没有找到对应司机"
          : todayOnlyCompleted
            ? "该队伍暂无已推广司机"
            : "该队伍暂无司机",
        query ? "请检查姓名或工号。" : "请检查今日同步数据。",
      ),
    );
    return;
  }
  elements.todayDrivers.append(...drivers.map(createTodayDriverCard));
}

function createOrderFlagRow(field, value) {
  const row = document.createElement("div");
  row.className = `flag-row ${Number(value) === 1 ? "is-one" : ""}`.trim();
  row.append(
    createTextElement("dt", "", flagTitle(field)),
    createTextElement("dd", "", formatFlag(field, value)),
  );
  return row;
}

function createOrderCard(order) {
  const card = document.createElement("article");
  card.className = `order-card ${order.isReal ? "is-real" : "is-not-real"}`;
  const heading = document.createElement("div");
  heading.className = "order-card-heading";
  heading.append(
    createTextElement("strong", "", order.date),
    createTextElement("span", "", `工号 ${normalizeId(order.employeeId)}`),
    createTextElement(
      "span",
      `transfer-status ${order.isReal ? "is-real" : "is-not-real"}`,
      order.isReal ? "真实推广" : "非真实推广",
    ),
  );
  const flags = document.createElement("dl");
  flags.className = "flag-list";
  ORDER_FLAGS.forEach((field) => {
    flags.append(createOrderFlagRow(field, order[field]));
  });
  card.append(heading, flags);
  return card;
}

function createOrderTable(orders) {
  const wrapper = document.createElement("div");
  wrapper.className = "table-wrap";
  const table = document.createElement("table");
  table.className = "orders-table";

  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  ["司机工号", "推广日期", ...ORDER_FLAGS.map(flagTitle)].forEach((label) => {
    headerRow.append(createTextElement("th", "", label));
  });
  thead.append(headerRow);

  const tbody = document.createElement("tbody");
  orders.forEach((order) => {
    const row = document.createElement("tr");
    row.append(
      createTextElement("td", "", normalizeId(order.employeeId)),
      createTextElement("td", "", order.date),
      ...ORDER_FLAGS.map((field) =>
        createTextElement(
          "td",
          Number(order[field]) === 1 ? "is-one" : "",
          formatFlag(field, order[field]),
        ),
      ),
    );
    tbody.append(row);
  });

  table.append(thead, tbody);
  wrapper.append(table);
  return wrapper;
}

function createTransferSummary(summary) {
  const wrapper = document.createElement("div");
  wrapper.className = "transfer-summary";
  [
    ["总计转单", summary.total, "total"],
    ["真实转单", summary.real, "real"],
    ["不真实转单", summary.notReal, "not-real"],
  ].forEach(([label, value, tone]) => {
    const item = document.createElement("div");
    item.className = `transfer-summary-item ${tone}`;
    item.append(
      createTextElement("span", "", label),
      createTextElement("strong", "", String(value)),
    );
    wrapper.append(item);
  });
  return wrapper;
}

function renderOrders() {
  const query = normalizeId(elements.orderQuery.value);
  elements.orderResults.replaceChildren();

  if (!query) {
    elements.orderSearchStatus.textContent = "请输入推荐司机工号。";
    return;
  }
  if (!/^\d+$/.test(query)) {
    elements.orderSearchStatus.textContent = "工号只能包含数字。";
    return;
  }

  const orders = ordersForEmployee(snapshot.orders, query);
  elements.orderSearchStatus.textContent = `找到 ${orders.length} 条匹配订单。`;
  if (!orders.length) {
    elements.orderResults.append(
      createStateMessage(
        "该工号暂无推广工单",
        "当前统计周期内没有匹配记录。",
      ),
    );
    return;
  }

  const mobileList = document.createElement("div");
  mobileList.className = "order-card-list";
  mobileList.append(...orders.map(createOrderCard));
  elements.orderResults.append(
    createTransferSummary(summarizeTransfers(orders)),
    createOrderTable(orders),
    mobileList,
  );
}

function formatDateRange(meta) {
  const start = new Date(`${meta.periodStart}T00:00:00`);
  const end = new Date(`${meta.periodEnd}T00:00:00`);
  const formatter = new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
  });
  return `${formatter.format(start)} 至 ${formatter.format(end)}`;
}

function formatSyncTime(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(parsed);
}

function renderMeta() {
  elements.syncLabel.textContent = `最近同步 ${formatSyncTime(snapshot.meta.syncedAt)}`;
  elements.periodLabel.textContent = `统计范围 ${formatDateRange(snapshot.meta)}`;
  elements.teamUpdated.textContent = `数据更新时间 ${formatSyncTime(snapshot.meta.syncedAt)}`;
}

function bindTabNavigation() {
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      setActiveTab(button.dataset.tab);
    });
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) {
        return;
      }
      event.preventDefault();
      const tabs = [...document.querySelectorAll("[data-tab]")].filter(
        (item) => item.closest("nav").classList.contains("desktop-tabs") ===
          button.closest("nav").classList.contains("desktop-tabs"),
      );
      const currentIndex = tabs.indexOf(button);
      const direction = event.key === "ArrowRight" ? 1 : -1;
      const nextTab = tabs[(currentIndex + direction + tabs.length) % tabs.length];
      nextTab.focus();
      setActiveTab(nextTab.dataset.tab);
    });
  });

  window.addEventListener("hashchange", () => setActiveTab(tabFromHash(), false));
  window.addEventListener("popstate", () => setActiveTab(tabFromHash(), false));
}

function bindForms() {
  elements.driverSearchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    renderDriverSearch();
  });
  elements.driverQuery.addEventListener("input", renderDriverSearch);

  elements.orderSearchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    renderOrders();
  });
}

function bindTeamControls() {
  elements.teamCompletionFilter.addEventListener("change", () => {
    teamCompletionFilter = elements.teamCompletionFilter.value;
    renderSelectedTeam();
  });
  elements.teamSortBy.addEventListener("change", () => {
    teamSortBy = elements.teamSortBy.value;
    renderSelectedTeam();
  });
  elements.teamSortDirection.addEventListener("click", () => {
    teamSortDirection = teamSortDirection === "desc" ? "asc" : "desc";
    elements.teamSortDirection.textContent =
      teamSortDirection === "desc" ? "降序" : "升序";
    elements.teamSortDirection.setAttribute(
      "aria-pressed",
      String(teamSortDirection === "asc"),
    );
    renderSelectedTeam();
  });
}

async function loadSnapshot() {
  const response = await fetch("./data/snapshot.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`快照读取失败：HTTP ${response.status}`);
  }
  const data = await response.json();
  if (!Array.isArray(data.drivers) || !Array.isArray(data.orders)) {
    throw new Error("快照格式不正确。");
  }
  return data;
}

async function loadTodaySnapshot() {
  const response = await fetch(`./data/today.json?t=${Date.now()}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`今日快照读取失败：HTTP ${response.status}`);
  }
  const data = await response.json();
  if (!data.meta || !Array.isArray(data.drivers)) {
    throw new Error("今日快照格式不正确。");
  }
  return data;
}

async function updateTodaySnapshotView() {
  todaySnapshot = await loadTodaySnapshot();
  lastTodayFetchAt = Date.now();
  renderTodayMeta(new Date(lastTodayFetchAt).toISOString());
  renderTodayDrivers();
}

async function refreshTodayData() {
  if (todayRefreshInProgress) {
    return;
  }
  todayRefreshInProgress = true;
  try {
    await updateTodaySnapshotView();
  } catch (error) {
    if (todaySnapshot) {
      elements.todayRefreshed.textContent = "本次刷新失败，继续显示上次数据";
      return;
    }
    todaySnapshot = null;
    renderTodayMeta();
    renderTodayDrivers();
  } finally {
    todayRefreshInProgress = false;
  }
}

async function startLocalRefresh() {
  let response;
  try {
    response = await fetch(`${LOCAL_REFRESH_URL}/refresh`, {
      method: "POST",
      cache: "no-store",
      headers: {
        "X-Workbench-Refresh": "1",
      },
    });
  } catch (error) {
    throw new LocalRefreshUnavailable("本机同步服务未启动", { cause: error });
  }
  if (!response.ok) {
    throw new LocalRefreshUnavailable(`本机同步服务返回 HTTP ${response.status}`);
  }
  return response.json();
}

async function waitForLocalRefresh() {
  const deadline = Date.now() + 5 * 60 * 1000;
  while (Date.now() < deadline) {
    await new Promise((resolve) => window.setTimeout(resolve, 2000));
    let response;
    try {
      response = await fetch(`${LOCAL_REFRESH_URL}/status`, {
        cache: "no-store",
      });
    } catch (error) {
      throw new LocalRefreshUnavailable("本机同步服务连接中断", { cause: error });
    }
    if (!response.ok) {
      throw new LocalRefreshUnavailable(`本机同步服务返回 HTTP ${response.status}`);
    }
    const state = await response.json();
    if (state.status === "success") {
      return state;
    }
    if (state.status === "failure") {
      throw new LocalRefreshFailed(state.message || "本机同步失败");
    }
  }
  throw new LocalRefreshFailed("本机同步超时，请稍后重试");
}

async function refreshTodayManually() {
  if (todayRefreshInProgress) {
    return;
  }
  todayRefreshInProgress = true;
  elements.todayRefresh.disabled = true;
  elements.todayRefresh.textContent = "同步中...";
  elements.todayRefreshed.textContent = "正在从钉钉同步今日数据...";
  try {
    await startLocalRefresh();
    const state = await waitForLocalRefresh();
    await updateTodaySnapshotView();
    elements.todayRefreshed.textContent =
      `手动刷新完成 ${formatSyncTime(state.finishedAt)}`;
  } catch (error) {
    if (error instanceof LocalRefreshUnavailable) {
      try {
        await updateTodaySnapshotView();
        elements.todayRefreshed.textContent =
          `${error.message}，已重新载入线上数据`;
      } catch (reloadError) {
        elements.todayRefreshed.textContent =
          `刷新失败：${reloadError instanceof Error ? reloadError.message : "未知错误"}`;
      }
    } else {
      elements.todayRefreshed.textContent =
        `同步失败：${error instanceof Error ? error.message : "未知错误"}`;
    }
  } finally {
    todayRefreshInProgress = false;
    elements.todayRefresh.disabled = false;
    elements.todayRefresh.textContent = "刷新";
  }
}

function bindTodayControls() {
  elements.todaySearchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    renderTodayDrivers();
  });
  elements.todayQuery.addEventListener("input", renderTodayDrivers);
  elements.todayOnlyCompleted.addEventListener("click", () => {
    todayOnlyCompleted = !todayOnlyCompleted;
    elements.todayOnlyCompleted.setAttribute(
      "aria-pressed",
      String(todayOnlyCompleted),
    );
    elements.todayOnlyCompleted.textContent = todayOnlyCompleted
      ? "显示全部"
      : "只看已推广";
    renderTodayDrivers();
  });
  elements.todayRefresh.addEventListener("click", () => {
    refreshTodayManually();
  });

  window.setInterval(refreshTodayData, 5 * 60 * 1000);
  document.addEventListener("visibilitychange", () => {
    if (
      document.visibilityState === "visible"
      && Date.now() - lastTodayFetchAt >= 60 * 1000
    ) {
      refreshTodayData();
    }
  });
}

async function start() {
  try {
    snapshot = await loadSnapshot();
    renderMeta();
    renderTeamOptions();
    renderSelectedTeam();
    bindTabNavigation();
    bindForms();
    bindTeamControls();
    await refreshTodayData();
    renderTodayTeamOptions();
    bindTodayControls();
    elements.loadState.hidden = true;
    elements.appContent.hidden = false;
    setActiveTab(tabFromHash(), false);
  } catch (error) {
    elements.loadState.className = "state-panel state-panel-error";
    elements.loadState.replaceChildren(
      createTextElement("strong", "", "数据载入失败"),
      createTextElement(
        "span",
        "",
        error instanceof Error ? error.message : "请稍后重试。",
      ),
    );
  }
}

start();
