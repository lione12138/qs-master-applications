export function filterRecordsToRanking(records, rankingRows) {
  const universityIds = new Set(
    rankingRows.map((row) => row.universityId).filter(Boolean),
  );
  return records.filter((record) => universityIds.has(record.universityId));
}
