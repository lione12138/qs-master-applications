export function createRankingIndex(rankingRows) {
  const rows = rankingRows || [];
  const byUniversityId = new Map();
  const universityIds = new Set();
  rows.forEach((row) => {
    if (!row.universityId) return;
    universityIds.add(row.universityId);
    byUniversityId.set(row.universityId, row);
  });
  return { rows, byUniversityId, universityIds };
}

export function filterRecordsToRanking(
  records,
  rankingRows,
  universityIds = null,
) {
  const selectedUniversityIds =
    universityIds || createRankingIndex(rankingRows).universityIds;
  return records.filter((record) =>
    selectedUniversityIds.has(record.universityId),
  );
}
