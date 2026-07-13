const TERM_ORDER = {
  spring: 0,
  summer: 1,
  fall: 2,
  winter: 3,
  academic: 4,
  other: 5,
};

export function canonicalIntake(record) {
  const details = record.intakeDetails || {};
  const year = Number(details.cycleYear);
  const month = details.startMonth;
  let term = details.term || "other";
  const label = String(record.intake || details.label || "").toLowerCase();

  if (label.startsWith("academic year")) term = "academic";
  if (term === "michaelmas" || term === "fall") term = "fall";
  if (term === "other" && [8, 9, 10].includes(month)) term = "fall";
  if (term === "other" && details.academicYearEnd && !month) {
    term = "academic";
  }

  return {
    key: `${term}:${year}`,
    term,
    year,
    academicYearEnd: details.academicYearEnd || null,
  };
}

export function intakeLabel(intake, language = "en") {
  const labels = {
    en: {
      spring: "Spring",
      summer: "Summer",
      fall: "Fall",
      winter: "Winter",
      academic: "Academic Year",
      other: "Other",
    },
    zh: {
      spring: "春季",
      summer: "夏季",
      fall: "秋季",
      winter: "冬季",
      academic: "学年",
      other: "其他",
    },
  };
  if (intake.term === "academic" && intake.academicYearEnd) {
    const end = String(intake.academicYearEnd).slice(-2);
    return language === "zh"
      ? `${intake.year}/${end} 学年`
      : `Academic Year ${intake.year}/${end}`;
  }
  return language === "zh"
    ? `${intake.year} ${labels.zh[intake.term]}`
    : `${labels.en[intake.term]} ${intake.year}`;
}

export function compareIntakes(left, right) {
  return (
    left.year - right.year ||
    (TERM_ORDER[left.term] ?? 99) - (TERM_ORDER[right.term] ?? 99)
  );
}
