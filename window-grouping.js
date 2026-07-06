import { canonicalIntake } from "./intake-filter.js";

export function equivalentWindowKey(record) {
  if (record.scopeType !== "programme") return null;
  if (!record.universityId || !record.opensAt || !record.closesAt) return null;

  const applicantCategories = [...(record.applicantCategories || [])]
    .sort()
    .join(",");
  return JSON.stringify([
    record.universityId,
    canonicalIntake(record).key,
    applicantCategories,
    record.opensAt,
    record.closesAt,
    record.round || "",
    record.dataStatus || "official",
  ]);
}

export function groupEquivalentWindows(records) {
  const groups = [];
  const groupsByKey = new Map();

  records.forEach((record, index) => {
    const equivalentKey = equivalentWindowKey(record);
    if (!equivalentKey) {
      groups.push({
        key: `record:${record.id || index}`,
        records: [record],
        collapsible: false,
      });
      return;
    }

    let group = groupsByKey.get(equivalentKey);
    if (!group) {
      group = { key: equivalentKey, records: [], collapsible: false };
      groupsByKey.set(equivalentKey, group);
      groups.push(group);
    }
    group.records.push(record);
    group.collapsible = group.records.length > 1;
  });

  return groups;
}

export function groupWindowGroupsByUniversity(windowGroups) {
  const groups = [];
  const groupsByKey = new Map();

  windowGroups.forEach((windowGroup, index) => {
    const representative = windowGroup.records[0] || {};
    const universityId = representative.universityId;
    if (!universityId) {
      groups.push({
        key: `window-group:${windowGroup.key || index}`,
        universityId: "",
        records: windowGroup.records,
        windowGroups: [windowGroup],
        collapsible: false,
      });
      return;
    }

    const key = `university:${universityId}`;
    let group = groupsByKey.get(key);
    if (!group) {
      group = {
        key,
        universityId,
        records: [],
        windowGroups: [],
        collapsible: false,
      };
      groupsByKey.set(key, group);
      groups.push(group);
    }
    group.records.push(...windowGroup.records);
    group.windowGroups.push(windowGroup);
    group.collapsible =
      group.windowGroups.length > 1 || group.records.length > 1;
  });

  return groups;
}
