#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

const root = path.resolve(import.meta.dirname, "..");
const dataDir = path.join(root, "data");
const universityPayload = JSON.parse(
  fs.readFileSync(path.join(dataDir, "universities.json"), "utf8"),
);

const THE_URL =
  "https://www.timeshighereducation.com/world-university-rankings/2026/world-ranking";
const ARWU_URL = "https://www.shanghairanking.com/rankings/arwu/2025";
const ARWU_PAYLOAD_URL =
  "https://www.shanghairanking.com/_nuxt/static/1779447311/rankings/arwu/2025/payload.js";
const USNEWS_URL =
  "https://www.usnews.com/education/best-global-universities/search";
const USNEWS_EDITION = "2026-2027";

const args = new Map(
  process.argv.slice(2).map((value, index, values) => [
    value,
    values[index + 1],
  ]),
);
const outputPath = args.get("--output")
  ? path.resolve(args.get("--output"))
  : path.join(dataDir, "global-rankings.json");

function normalize(value = "") {
  return String(value)
    .toLocaleLowerCase("en")
    .replace(/&/g, " and ")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\([^)]*\)/g, " ")
    .replace(/\b(the|university|universitat|universite|universidad|universita|college|of|and)\b/g, " ")
    .replace(/[^a-z0-9]+/g, "");
}

function identityKey(value = "") {
  return String(value)
    .toLocaleLowerCase("en")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "");
}

function slug(value = "") {
  return String(value)
    .toLocaleLowerCase("en")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 72);
}

function rankStart(display) {
  const match = String(display).match(/\d+/);
  return match ? Number(match[0]) : Number.POSITIVE_INFINITY;
}

function todayInBeijing() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(
    parts.filter((part) => part.type !== "literal").map((part) => [part.type, part.value]),
  );
  return `${values.year}-${values.month}-${values.day}`;
}

const countryAliases = new Map([
  ["United States of America", "United States"],
  ["United States", "United States"],
  ["United Kingdom", "United Kingdom"],
  ["Mainland China", "China"],
  ["Hong Kong SAR", "Hong Kong"],
  ["Macau SAR", "Macau"],
  ["Russian Federation", "Russia"],
  ["Republic of Korea", "South Korea"],
  ["Korea, South", "South Korea"],
  ["Taiwan, China", "Taiwan"],
  ["Türkiye", "Turkey"],
  ["Czechia", "Czech Republic"],
]);

const regionByCountry = new Map([
  ["Argentina", "Americas"], ["Australia", "Oceania"], ["Austria", "Europe"],
  ["Belgium", "Europe"], ["Brazil", "Americas"], ["Canada", "Americas"],
  ["Chile", "Americas"], ["China", "Asia"], ["Colombia", "Americas"],
  ["Czech Republic", "Europe"], ["Denmark", "Europe"], ["Egypt", "Africa"],
  ["Estonia", "Europe"], ["Finland", "Europe"], ["France", "Europe"],
  ["Germany", "Europe"], ["Greece", "Europe"], ["Hong Kong", "Asia"],
  ["Hungary", "Europe"], ["India", "Asia"], ["Indonesia", "Asia"],
  ["Iran", "Asia"], ["Ireland", "Europe"], ["Israel", "Asia"], ["Italy", "Europe"],
  ["Japan", "Asia"], ["Malaysia", "Asia"], ["Mexico", "Americas"],
  ["Netherlands", "Europe"], ["New Zealand", "Oceania"], ["Norway", "Europe"],
  ["Pakistan", "Asia"], ["Poland", "Europe"], ["Portugal", "Europe"],
  ["Russia", "Europe"], ["Saudi Arabia", "Asia"], ["Singapore", "Asia"],
  ["South Africa", "Africa"], ["South Korea", "Asia"], ["Spain", "Europe"],
  ["Sweden", "Europe"], ["Switzerland", "Europe"], ["Taiwan", "Asia"],
  ["Thailand", "Asia"], ["Turkey", "Asia"], ["United Arab Emirates", "Asia"],
  ["United Kingdom", "Europe"], ["United States", "Americas"], ["Vietnam", "Asia"],
]);

// Official publishers use different institutional names. These mappings are
// deliberately small and explicit so a ranking-only record is preferred over
// an unsafe automatic identity match.
const aliasEntries = [
  ["ludwigmaximiliansuniversitatmunchen", "ludwig-maximilians-universit-t-m-nchen"],
  ["ludwigmaximiliansuniversitymunich", "ludwig-maximilians-universit-t-m-nchen"],
  ["ecolepolytechniquefederaledelausanne", "cole-polytechnique-f-d-rale-de-lausanne"],
  ["swissfederalinstituteoftechnologylausanne", "cole-polytechnique-f-d-rale-de-lausanne"],
  ["parissciencesetlettrespslresearchuniversityparis", "psl-university"],
  ["psluniversity", "psl-university"],
  ["unswsydney", "the-university-of-new-south-wales"],
  ["purdueuniversitywestlafayette", "purdue-university"],
  ["purdueuniversitywestlafayettein", "purdue-university"],
  ["humboldtuniversityofberlin", "humboldt-universit-t-zu-berlin"],
  ["almatersstudiorumuniversitadibologna", "alma-mater-studiorum-university-of-bologna"],
  ["universityofbologna", "alma-mater-studiorum-university-of-bologna"],
  ["trinitycollegedublintheuniversityofdublin", "trinity-college-dublin-the-university-of-dublin"],
  ["trinitycollegedublin", "trinity-college-dublin-the-university-of-dublin"],
  ["technischeuniversitatdresden", "technische-universitat-dresden"],
  ["tudresden", "technische-universitat-dresden"],
  ["freeuniversityberlin", "freie-universit-t-berlin"],
  ["freeuniversityofberlin", "freie-universit-t-berlin"],
  ["parissaclayuniversity", "universite-paris-saclay"],
  ["universitycollegelondon", "ucl-university-college-london"],
  ["lmumunich", "ludwig-maximilians-universit-t-m-nchen"],
  ["universityofmunich", "ludwig-maximilians-universit-t-m-nchen"],
  ["heidelberguniversity", "heidelberg-university"],
  ["nanyangtechnologicaluniversitysingapore", "nanyang-technological-university-singapore-ntu-singapore"],
  ["nanyangtechnologicaluniversity", "nanyang-technological-university-singapore-ntu-singapore"],
  ["moscowstateuniversity", "lomonosov-moscow-state-university"],
  ["pennsylvaniastateuniversityuniversitypark", "pennsylvania-state-university"],
  ["universityofbarcelona", "university-of-barcelona"],
  ["universityofmontreal", "university-of-montreal"],
  ["universityofsaopaulo", "universidade-de-s-o-paulo-usp"],
  ["universityofsopaulo", "universidade-de-s-o-paulo-usp"],
  ["sao-paulo", "universidade-de-s-o-paulo-usp"],
  ["karolinskainstitutet", "karolinska-institutet"],
  ["universityofcalifornia,sanfrancisco", "university-of-california-san-francisco"],
  ["universityofcaliforniasanfrancisco", "university-of-california-san-francisco"],
  ["universityofcaliforniasan-diego", "university-of-california-san-diego"],
  ["universityofcaliforniasandiego", "university-of-california-san-diego"],
  ["universityofcalifornialosangeles", "university-of-california-los-angeles"],
  ["universityofcaliforniaberkeley", "university-of-california-berkeley"],
  ["universityofcaliforniadavies", "university-of-california-davis"],
  ["universityofcaliforniadavis", "university-of-california-davis"],
  ["universityofcaliforniasanta-barbara", "university-of-california-santa-barbara"],
  ["universityofcaliforniasantabarbara", "university-of-california-santa-barbara"],
  ["universityofcaliforniairvine", "university-of-california-irvine"],
  ["universityofillinoisurbanachampaign", "university-of-illinois-at-urbana-champaign"],
  ["universityofillinoisaturbanachampaign", "university-of-illinois-at-urbana-champaign"],
  ["universityofillinoisatchampaign", "university-of-illinois-at-urbana-champaign"],
  ["texasamuniversity", "texas-a-and-m-university"],
  ["texasamuniversitycollegestation", "texas-a-and-m-university"],
  ["theohiostateuniversity", "ohio-state-university"],
  ["universityofpittsburghpittsburghcampus", "university-of-pittsburgh"],
  ["universityofpittsburgh", "university-of-pittsburgh"],
  ["universityofmarylandcollegepark", "university-of-maryland-college-park"],
  ["universityofminnesotatwincities", "university-of-minnesota-twin-cities"],
  ["universityofwashingtonseattle", "university-of-washington"],
  ["universityofwisconsinmadison", "university-of-wisconsin-madison"],
  ["universityofnottinghamming", "university-of-nottingham"],
  ["universitatmunchen", "ludwig-maximilians-universit-t-m-nchen"],
  ["katholiekeuniversiteitleuven", "ku-leuven"],
  ["universityofamsterdam", "university-of-amsterdam"],
  ["universityofzurich", "university-of-zurich"],
  ["universityofgeneva", "university-of-geneva"],
  ["universityofbasel", "university-of-basel"],
  ["universityofoslo", "university-of-oslo"],
  ["universityofhelsinki", "university-of-helsinki"],
  ["universityofcopenhagen", "university-of-copenhagen"],
  ["universityofwarwick", "university-of-warwick"],
  ["universityofleeds", "university-of-leeds"],
  ["universityofsouthampton", "university-of-southampton"],
  ["universityofbirmingham", "university-of-birmingham"],
  ["universityofglasgow", "university-of-glasgow"],
  ["universityofsheffield", "university-of-sheffield"],
  ["universityofexeter", "university-of-exeter"],
  ["universityofliverpool", "university-of-liverpool"],
  ["universityofbristol", "university-of-bristol"],
  ["universityofedinburgh", "university-of-edinburgh"],
  ["universityofmanchester", "the-university-of-manchester"],
  ["koreaadvancedinstituteofscienceandtechnologykaist", "kaist"],
  ["pennstatemaincampus", "pennsylvania-state-university"],
  ["technicaluniversityofberlin", "technische-universit-t-berlin"],
  ["karlsruheinstituteoftechnology", "karlsruhe-institute-of-technology-kit"],
  ["kingfahduniversityofpetroleumandminerals", "king-fahd-university-of-petroleum-and-minerals"],
];
const aliases = new Map(
  aliasEntries.map(([name, universityId]) => [identityKey(name), universityId]),
);

const universitiesByNormalizedName = new Map(
  universityPayload.universities.map((university) => [
    normalize(university.school),
    university,
  ]),
);
const universitiesById = new Map(
  universityPayload.universities.map((university) => [university.id, university]),
);

function resolveUniversity(name) {
  const normalized = normalize(name);
  const matchedId = aliases.get(identityKey(name));
  if (matchedId && universitiesById.has(matchedId)) return universitiesById.get(matchedId);
  return universitiesByNormalizedName.get(normalized) || null;
}

async function sourceText(url, argumentName) {
  const filePath = args.get(argumentName);
  if (filePath) return fs.readFileSync(path.resolve(filePath), "utf8");
  const response = await fetch(url, {
    headers: { "User-Agent": "GradWindow ranking importer/1.0" },
  });
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return response.text();
}

async function sourceJson(url) {
  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
      "User-Agent": "GradWindow ranking importer/1.0",
    },
  });
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return response.json();
}

function usNewsRank(item) {
  const rank = (item.ranks || []).find(
    (candidate) =>
      candidate.is_ranked !== false &&
      String(candidate.label || "").includes("Best Global Universities"),
  );
  if (!rank) return null;
  const position = rankStart(rank.value);
  if (!Number.isFinite(position)) return null;
  return {
    position,
    display: rank.is_tied ? `=${position}` : String(position),
  };
}

function parseUsNews(payloads) {
  return payloads
    .flatMap((payload) => payload.items || [])
    .map((item) => ({ item, rank: usNewsRank(item) }))
    .filter(({ rank }) => rank && rank.position <= 200)
    .map(({ item, rank }) => ({
      name: item.name,
      rankDisplay: rank.display,
      country: item.country_name,
      sourceUrl: item.url || USNEWS_URL,
    }));
}

async function sourceUsNewsPages() {
  const fixturePath = args.get("--usnews-json");
  if (fixturePath) {
    const fixture = JSON.parse(fs.readFileSync(path.resolve(fixturePath), "utf8"));
    return Array.isArray(fixture) ? fixture : fixture.pages || [fixture];
  }

  const pages = [];
  let page = 1;
  let totalPages = 1;
  while (page <= totalPages) {
    const payload = await sourceJson(`${USNEWS_URL}?format=json&page=${page}`);
    pages.push(payload);
    totalPages = Number(payload.total_pages) || page;
    const positions = (payload.items || [])
      .map((item) => usNewsRank(item)?.position)
      .filter(Number.isFinite);
    // Fetch the first page wholly beyond 200 so ties at rank 200 that spill
    // onto the next page are retained.
    if (!positions.length || Math.min(...positions) > 200) break;
    page += 1;
  }
  return pages;
}

function parseThe(html) {
  const marker = '<script id="__NEXT_DATA__" type="application/json">';
  const start = html.indexOf(marker);
  const end = html.indexOf("</script>", start);
  if (start < 0 || end < 0) throw new Error("THE ranking payload was not found");
  const payload = JSON.parse(html.slice(html.indexOf(">", start) + 1, end));
  return payload.props.pageProps.page.rankingsTableConfig.rankingsData.data
    .filter((row) => rankStart(row.rank) <= 200)
    .map((row) => ({
      name: row.name,
      rankDisplay: row.rank,
      country: row.location,
      sourceUrl: `https://www.timeshighereducation.com${row.url}`,
    }));
}

function parseArwu(payloadText) {
  let captured;
  const context = {
    __NUXT_JSONP__: (route, payload) => {
      captured = { route, payload };
    },
  };
  vm.createContext(context);
  vm.runInContext(payloadText, context);
  const rows = captured?.payload?.data?.[0]?.filterList;
  if (!Array.isArray(rows)) throw new Error("ARWU ranking payload was not found");
  return rows
    .filter((row) => rankStart(row.ranking) <= 200)
    .map((row) => ({
      name: row.univNameEn,
      rankDisplay: row.ranking,
      country: row.region,
      sourceUrl: ARWU_URL,
    }));
}

function buildRows(rows, rankingId, sourceUrl) {
  const usedIds = new Map();
  return rows.map((row) => {
    const university = resolveUniversity(row.name);
    const country = countryAliases.get(row.country) || row.country;
    const baseId = university?.id || `${rankingId}-${slug(row.name)}`;
    const count = usedIds.get(baseId) || 0;
    usedIds.set(baseId, count + 1);
    return {
      id: count ? `${baseId}-${count + 1}` : baseId,
      universityId: university?.id || null,
      school: university?.school || row.name,
      schoolZh: university?.schoolZh || "",
      country: university?.country || country,
      region: university?.region || regionByCountry.get(country) || "Other",
      rankPosition: rankStart(row.rankDisplay),
      rankDisplay: row.rankDisplay,
      rankingOnly: !university,
      sourceUrl: row.sourceUrl || sourceUrl,
    };
  });
}

const [theHtml, arwuPayload, usNewsResult] = await Promise.all([
  sourceText(THE_URL, "--the-html"),
  sourceText(ARWU_PAYLOAD_URL, "--arwu-payload"),
  sourceUsNewsPages()
    .then((pages) => ({ pages }))
    .catch((error) => ({ error })),
]);
const theRows = buildRows(parseThe(theHtml), "the", THE_URL);
const arwuRows = buildRows(parseArwu(arwuPayload), "arwu", ARWU_URL);
const usNewsRows = usNewsResult.pages
  ? buildRows(parseUsNews(usNewsResult.pages), "usnews", USNEWS_URL)
  : [];

const output = {
  meta: {
    generatedAt: todayInBeijing(),
    selectionPolicy:
      "All institutions whose published rank starts at 200 or above are retained; tied and banded ranks are preserved.",
    note:
      "QS remains the admissions-monitoring core. Ranking-only institutions are not represented as monitored admissions data.",
  },
  rankings: {
    the: {
      label: "Times Higher Education World University Rankings",
      shortLabel: "THE",
      edition: "2026",
      sourceUrl: THE_URL,
      rowCount: theRows.length,
      rows: theRows,
    },
    arwu: {
      label: "Academic Ranking of World Universities",
      shortLabel: "ARWU (ShanghaiRanking)",
      edition: "2025",
      sourceUrl: ARWU_URL,
      rowCount: arwuRows.length,
      rows: arwuRows,
    },
    usnews: {
      label: "U.S. News Best Global Universities",
      shortLabel: "U.S. News",
      edition: USNEWS_EDITION,
      sourceUrl: USNEWS_URL,
      rowCount: usNewsRows.length,
      rows: usNewsRows,
      available: usNewsRows.length > 0,
      ...(usNewsRows.length
        ? {}
        : {
            unavailableReason: usNewsResult.error
              ? `Official U.S. News data could not be fetched: ${usNewsResult.error.message}`
              : "The official U.S. News response did not contain ranked rows.",
          }),
    },
  },
};

fs.writeFileSync(outputPath, `${JSON.stringify(output, null, 2)}\n`, "utf8");
console.log(`Wrote ${outputPath}`);
console.log(`THE: ${theRows.length} rows (${theRows.filter((row) => row.rankingOnly).length} ranking-only)`);
console.log(`ARWU: ${arwuRows.length} rows (${arwuRows.filter((row) => row.rankingOnly).length} ranking-only)`);
console.log(
  `U.S. News: ${usNewsRows.length} rows (${usNewsRows.filter((row) => row.rankingOnly).length} ranking-only)`,
);
