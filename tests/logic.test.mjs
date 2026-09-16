import assert from "node:assert/strict";
import test from "node:test";

import {
  filterAndSortDrivers,
  formatFlag,
  normalizeId,
  ordersForEmployee,
  searchDrivers,
  summarizeTransfers,
} from "../docs/logic.mjs";

const drivers = [
  {
    employeeId: "11127615",
    name: "刘鹏",
    team: "二大队",
    outDays: 3,
    realTransfers: 1,
    promotionDelta: -1,
  },
  {
    employeeId: "11273471",
    name: "刘鹏",
    team: "三大队",
    outDays: 4,
    realTransfers: 0,
    promotionDelta: 2,
  },
  {
    employeeId: "11281385",
    name: "陈浩",
    team: "一大队",
    outDays: 12,
    realTransfers: 3,
    promotionDelta: 5,
  },
];

test("normalizes Excel-style employee ids", () => {
  assert.equal(normalizeId("11281385.0"), "11281385");
  assert.equal(normalizeId(11281385), "11281385");
});

test("searches names with a contains match and returns duplicates", () => {
  const results = searchDrivers(drivers, "刘鹏");
  assert.deepEqual(
    results.map((driver) => driver.employeeId),
    ["11127615", "11273471"],
  );
});

test("searches numeric employee ids exactly", () => {
  const results = searchDrivers(drivers, "11281385");
  assert.deepEqual(
    results.map((driver) => driver.name),
    ["陈浩"],
  );
  assert.equal(searchDrivers(drivers, "1128138").length, 0);
});

test("returns only matching orders sorted by date descending", () => {
  const orders = [
    { employeeId: "11281385", date: "2026-09-01" },
    { employeeId: "11281385", date: "2026-09-03" },
    { employeeId: "11127615", date: "2026-09-04" },
  ];
  assert.deepEqual(
    ordersForEmployee(orders, "11281385").map((order) => order.date),
    ["2026-09-03", "2026-09-01"],
  );
});

test("formats flags with text instead of color alone", () => {
  assert.equal(formatFlag("nonOffline", 1), "1 · 非线下推广");
  assert.equal(formatFlag("cheating", 0), "0 · 非作弊单");
});

test("filters completed drivers and sorts by real transfers descending", () => {
  const results = filterAndSortDrivers(
    [
      { ...drivers[0], promotionCompleted: false },
      { ...drivers[1], promotionCompleted: true },
      { ...drivers[2], promotionCompleted: true },
    ],
    { completion: "completed", sortBy: "realTransfers", direction: "desc" },
  );
  assert.deepEqual(
    results.map((driver) => driver.employeeId),
    ["11281385", "11273471"],
  );
});

test("sorts unfinished drivers by out days ascending", () => {
  const results = filterAndSortDrivers(
    [
      { ...drivers[0], promotionCompleted: false, outDays: 8 },
      { ...drivers[1], promotionCompleted: false, outDays: 3 },
      { ...drivers[2], promotionCompleted: true, outDays: 1 },
    ],
    { completion: "unfinished", sortBy: "outDays", direction: "asc" },
  );
  assert.deepEqual(
    results.map((driver) => driver.outDays),
    [3, 8],
  );
});

test("summarizes real and non-real transfers", () => {
  assert.deepEqual(
    summarizeTransfers([
      { isReal: true },
      { isReal: false },
      { isReal: true },
    ]),
    { total: 3, real: 2, notReal: 1 },
  );
});
