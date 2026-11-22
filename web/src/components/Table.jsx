import React, { useState, useMemo } from "react";

export function compareTableValues(valA, valB, isNumeric, isIdentifier, dir = "asc") {
  const isEmpty = (v) =>
    v === null ||
    v === undefined ||
    v === "" ||
    (Array.isArray(v) && v.length === 0);

  const aEmpty = isEmpty(valA);
  const bEmpty = isEmpty(valB);

  // Empty values always sorted to the end regardless of direction
  if (aEmpty && bEmpty) return 0;
  if (aEmpty) return 1;
  if (bEmpty) return -1;

  let cmp = 0;
  if (isNumeric) {
    const numA = Number(valA);
    const numB = Number(valB);
    cmp = numA - numB;
  } else {
    const strA = Array.isArray(valA) ? valA.join(", ") : String(valA);
    const strB = Array.isArray(valB) ? valB.join(", ") : String(valB);
    cmp = strA.localeCompare(strB, undefined, { numeric: !isIdentifier, sensitivity: "base" });
  }

  return dir === "desc" ? -cmp : cmp;
}

export function nextSortState(currentKey, currentDir, clickedKey) {
  if (currentKey !== clickedKey) {
    return { sortKey: clickedKey, sortDir: "asc" };
  }
  return {
    sortKey: clickedKey,
    sortDir: currentDir === "asc" ? "desc" : "asc",
  };
}

export function sortTableData(data, sortKey, sortDir, columns) {
  if (!sortKey || !data || !Array.isArray(data)) return data || [];
  const col = columns.find((c) => c.key === sortKey);
  const isNumeric = col ? Boolean(col.isNumeric) : false;
  const isIdentifier = col ? Boolean(col.isIdentifier) : false;

  // Stable sort: pair each element with its original index
  const indexed = data.map((item, index) => ({ item, index }));
  indexed.sort((a, b) => {
    const valA = a.item[sortKey];
    const valB = b.item[sortKey];
    const res = compareTableValues(valA, valB, isNumeric, isIdentifier, sortDir);
    if (res !== 0) return res;
    return a.index - b.index;
  });

  return indexed.map((entry) => entry.item);
}

export function Table({
  columns,
  data,
  keyField = "id",
  initialSortKey = null,
  initialSortDir = "asc",
  className = "dense-table",
  emptyMessage = "No records found",
}) {
  const [sortKey, setSortKey] = useState(initialSortKey);
  const [sortDir, setSortDir] = useState(initialSortDir);

  function handleHeaderClick(key, sortable) {
    if (sortable === false) return;
    const next = nextSortState(sortKey, sortDir, key);
    setSortKey(next.sortKey);
    setSortDir(next.sortDir);
  }

  const sortedData = useMemo(() => {
    return sortTableData(data, sortKey, sortDir, columns);
  }, [data, sortKey, sortDir, columns]);

  return (
    <div style={{ overflowX: "auto" }}>
      <table className={className}>
        <thead>
          <tr>
            {columns.map((col) => {
              const isSorted = sortKey === col.key;
              const ariaSort = isSorted
                ? (sortDir === "asc" ? "ascending" : "descending")
                : (col.sortable !== false ? "none" : undefined);
              const sortIndicator = isSorted ? (sortDir === "asc" ? " ▲" : " ▼") : "";

              return (
                <th
                  key={col.key}
                  style={{
                    cursor: col.sortable !== false ? "pointer" : "default",
                    userSelect: "none",
                    textAlign: col.align || "left",
                    ...col.headerStyle,
                  }}
                  tabIndex={col.sortable !== false ? 0 : undefined}
                  role={col.sortable !== false ? "columnheader" : undefined}
                  aria-sort={ariaSort}
                  onClick={() => handleHeaderClick(col.key, col.sortable)}
                  onKeyDown={(e) => {
                    if (col.sortable !== false && (e.key === "Enter" || e.key === " ")) {
                      e.preventDefault();
                      handleHeaderClick(col.key, col.sortable);
                    }
                  }}
                >
                  <span>{col.header}</span>
                  {sortIndicator && (
                    <span style={{ fontSize: "10px", marginLeft: "4px" }}>{sortIndicator}</span>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sortedData.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                style={{ textAlign: "center", color: "var(--muted)", padding: "16px" }}
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            sortedData.map((row, rowIdx) => {
              const rowKey = row[keyField] !== undefined ? row[keyField] : rowIdx;
              return (
                <tr key={rowKey}>
                  {columns.map((col) => {
                    const val = row[col.key];
                    const content = col.render
                      ? col.render(val, row)
                      : (val !== null && val !== undefined ? String(val) : "-");
                    return (
                      <td
                        key={col.key}
                        style={{ textAlign: col.align || "left" }}
                        className={col.isIdentifier ? "mono" : (col.className || "")}
                      >
                        {content}
                      </td>
                    );
                  })}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

export default Table;
