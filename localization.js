const COUNTRY_ZH = {
  Argentina: "阿根廷", Australia: "澳大利亚", Austria: "奥地利",
  Belgium: "比利时", Brazil: "巴西", Canada: "加拿大", Chile: "智利",
  "China (Mainland)": "中国大陆", Denmark: "丹麦", Finland: "芬兰",
  France: "法国", Germany: "德国", "Hong Kong SAR, China": "中国香港",
  India: "印度", Indonesia: "印度尼西亚", Ireland: "爱尔兰",
  Italy: "意大利", Japan: "日本", Kazakhstan: "哈萨克斯坦",
  Malaysia: "马来西亚", Mexico: "墨西哥", Netherlands: "荷兰",
  "New Zealand": "新西兰", Norway: "挪威", Qatar: "卡塔尔",
  "Republic of Korea": "韩国", "Russian Federation": "俄罗斯",
  "Saudi Arabia": "沙特阿拉伯", Singapore: "新加坡",
  "South Africa": "南非", Spain: "西班牙", Sweden: "瑞典",
  Switzerland: "瑞士", Taiwan: "中国台湾",
  "United Arab Emirates": "阿联酋", "United Kingdom": "英国",
  "United States of America": "美国",
};

const REGION_ZH = {
  Africa: "非洲", Americas: "美洲", Asia: "亚洲",
  Europe: "欧洲", Oceania: "大洋洲",
};

const PROGRAMME_ZH = {
  "brown-computer-science-scm": "计算机科学理学硕士",
  "cambridge-advanced-chemical-engineering-mphil": "高级化学工程哲学硕士",
  "cambridge-advanced-computer-science-mphil": "高级计算机科学哲学硕士",
  "cmu-scs-graduate-programmes": "卡内基梅隆大学计算机科学学院研究生项目",
  "cuhk-computer-science-msc": "计算机科学理学硕士",
  "eth-zurich-swiss-federal-institute-of-technology": "学校级硕士申请窗口",
  "fudan-english-taught-international-postgraduate": "复旦大学英文授课国际研究生项目",
  "ip-paris-computer-science-masters": "巴黎理工学院计算机科学硕士项目",
  "korea-university-general-graduate-admissions": "高丽大学一般研究生院招生",
  "kyoto-informatics-masters": "京都大学信息学研究科硕士项目",
  "ntu-applied-artificial-intelligence-mcomp": "应用人工智能计算机硕士",
  "ntu-international-degree-admissions": "台湾大学国际学位生招生",
  "penn-engineering-masters": "宾夕法尼亚大学工程学院硕士项目",
  "pku-international-standard-graduate-admissions": "北京大学国际研究生常规招生",
  "polyu-information-technology-msc": "信息技术理学硕士",
  "snu-international-graduate-admissions": "首尔大学国际研究生招生",
  "tsinghua-advanced-computing-master": "高级计算硕士项目",
  "ucl-advanced-materials-science-msc": "高级材料科学理学硕士",
  "ucsd-cse-graduate-admissions": "加州大学圣迭戈分校计算机系研究生招生",
  "um-coursework-postgraduate": "马来亚大学授课型研究生项目",
  "utokyo-computer-science-master": "计算机科学硕士项目",
  "yonsei-international-graduate-admissions": "延世大学国际研究生招生",
};

const ROUND_ZH = {
  "August entrance examination": "8 月入学考试",
  "Coursework and mixed mode": "授课型及混合模式",
  "Extended deadline": "延期截止", "Extended round": "延长轮次",
  "Final deadline": "最终截止",
  "International applications round 1": "国际申请第一轮",
  "International applications round 2": "国际申请第二轮",
  "International Bachelor's window": "境外本科申请窗口",
  "International graduate admissions": "国际研究生招生",
  "International student track": "国际学生通道",
  "IP Paris portal session 1": "巴黎理工学院第一轮",
  "IP Paris portal session 2": "巴黎理工学院第二轮",
  "Main application period": "主要申请期",
  "Non-visa applicants": "无需学生签证申请人",
  "Online application": "在线申请", "Phase One": "第一阶段",
  "Phase Two": "第二阶段", "Regular admissions": "常规招生",
  "Regular deadline": "常规截止", "Second application round": "第二轮申请",
  "Standard international application period": "国际申请常规批次",
  "Summer entrance examination": "夏季入学考试",
  "Swiss Bachelor's window": "瑞士本科申请窗口",
  "Visa applicants": "需要学生签证申请人",
};

export function countryLabel(country, language = "en") {
  return language === "zh" ? COUNTRY_ZH[country] || country : country;
}

export function regionLabel(region, language = "en") {
  return language === "zh" ? REGION_ZH[region] || region : region;
}

export function schoolLabels(university, language = "en") {
  const english = university.school || "";
  const chinese = university.schoolZh || "";
  return language === "zh"
    ? { primary: chinese || english, secondary: chinese ? english : "" }
    : { primary: english, secondary: chinese };
}

export function programmeLabel(scopeId, fallback, language = "en") {
  return language === "zh" ? PROGRAMME_ZH[scopeId] || fallback : fallback;
}

export function roundLabel(round, language = "en") {
  if (!round || language !== "zh") return round || "";
  return ROUND_ZH[round] || round;
}
