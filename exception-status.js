const MANUAL_POLICY_STATUSES = new Set([
  "official-entry-protected",
  "dynamic-listing-dates-not-captured",
  "official-route-current-dates-not-captured",
]);

export function needsManualCheck(university) {
  const nextAction = university.coverage?.nextAction;
  const discovery = university.admissionsDiscovery;
  const policyStatus = university.windowPolicy?.cycleGuidance?.status || "";

  return (
    ["locate-official-entry", "verify-window-policy"].includes(nextAction) ||
    ["low-confidence", "not-found", "pending", "error"].includes(discovery) ||
    MANUAL_POLICY_STATUSES.has(policyStatus)
  );
}
