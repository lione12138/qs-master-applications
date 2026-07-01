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
