export const TEAMS = Object.freeze([
  "一大队",
  "二大队",
  "三大队",
  "四大队",
  "五大队",
  "六大队",
  "七大队",
  "八大队",
  "九大队",
  "十大队",
  "会理大队",
  "德昌大队",
]);

const FLAG_LABELS = Object.freeze({
  nonOffline: Object.freeze({ 0: "线下推广", 1: "非线下推广" }),
  abnormalScan: Object.freeze({ 0: "正常扫码", 1: "非正常扫码" }),
  burner: Object.freeze({ 0: "非小号", 1: "小号" }),
  regularCustomer: Object.freeze({ 0: "非熟客", 1: "熟客订单" }),
  cheating: Object.freeze({ 0: "非作弊单", 1: "作弊单" }),
});

const FLAG_TITLES = Object.freeze({
  nonOffline: "是否非线下推广",
  abnormalScan: "是否非正常扫码",
  burner: "是否小号",
  regularCustomer: "是否熟客订单",
  cheating: "是否作弊单",
});

export function normalizeId(value) {
  const raw = value == null ? "" : String(value).trim();
  return /^\d+\.0+$/.test(raw) ? raw.replace(/\.0+$/, "") : raw;
}

export function compareDrivers(left, right) {
  const teamOrder = TEAMS.indexOf(left.team) - TEAMS.indexOf(right.team);
  if (teamOrder !== 0) {
    return teamOrder;
  }
  const nameOrder = left.name.localeCompare(right.name, "zh-CN");
  return nameOrder !== 0
    ? nameOrder
    : normalizeId(left.employeeId).localeCompare(normalizeId(right.employeeId));
}

const DRIVER_SORT_FIELDS = Object.freeze({
  outDays: "outDays",
  realTransfers: "realTransfers",
  promotionCount: "promotionCount",
  promotionDelta: "promotionDelta",
});

export function filterAndSortDrivers(
  drivers,
  { completion = "all", sortBy = "realTransfers", direction = "desc" } = {},
) {
  const filtered = drivers.filter((driver) => {
    if (completion === "completed") {
      return driver.promotionCompleted === true;
    }
    if (completion === "unfinished") {
      return driver.promotionCompleted !== true;
    }
    return true;
  });
  const field = DRIVER_SORT_FIELDS[sortBy] ?? "realTransfers";
  const multiplier = direction === "asc" ? 1 : -1;

  return [...filtered].sort((left, right) => {
    const difference = Number(left[field] ?? 0) - Number(right[field] ?? 0);
    if (difference !== 0) {
      return difference * multiplier;
    }
    return compareDrivers(left, right);
  });
}

export function searchDrivers(drivers, query) {
  const normalizedQuery = String(query ?? "").trim();
  if (!normalizedQuery) {
    return [];
  }

  const rows = /^\d+$/.test(normalizedQuery)
    ? drivers.filter(
        (driver) => normalizeId(driver.employeeId) === normalizedQuery,
      )
    : drivers.filter((driver) =>
        String(driver.name ?? "")
          .toLocaleLowerCase("zh-CN")
          .includes(normalizedQuery.toLocaleLowerCase("zh-CN")),
      );

  return [...rows].sort(compareDrivers);
}

export function ordersForEmployee(orders, employeeId) {
  const normalizedId = normalizeId(employeeId);
  if (!normalizedId) {
    return [];
  }

  return orders
    .filter((order) => normalizeId(order.employeeId) === normalizedId)
    .map((order) => ({ ...order }))
    .sort((left, right) => {
      const dateOrder = String(right.date).localeCompare(String(left.date));
      return dateOrder !== 0
        ? dateOrder
        : normalizeId(left.employeeId).localeCompare(
            normalizeId(right.employeeId),
          );
    });
}

export function summarizeTransfers(orders) {
  const real = orders.filter((order) => order.isReal === true).length;
  return {
    total: orders.length,
    real,
    notReal: orders.length - real,
  };
}

export function formatFlag(field, value) {
  const numericValue = Number(value);
  const label = FLAG_LABELS[field]?.[numericValue];
  if (!label) {
    return "—";
  }
  return `${numericValue} · ${label}`;
}

export function flagTitle(field) {
  return FLAG_TITLES[field] ?? field;
}

export function formatNumber(value) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? String(numericValue) : "0";
}
