from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


QS_SCHOOL_ZH = {
    "university-of-leeds": "利兹大学",
    "adelaide-university": "阿德莱德大学",
    "the-university-of-sheffield": "谢菲尔德大学",
    "universidad-de-buenos-aires": "布宜诺斯艾利斯大学",
    "durham-university": "杜伦大学",
    "politecnico-di-milano": "米兰理工大学",
    "university-of-technology-sydney": "悉尼科技大学",
    "uppsala-university": "乌普萨拉大学",
    "nanjing-university": "南京大学",
    "university-of-copenhagen": "哥本哈根大学",
    "pennsylvania-state-university": "宾夕法尼亚州立大学",
    "university-of-washington": "华盛顿大学",
    "boston-university": "波士顿大学",
    "the-university-of-osaka": "大阪大学",
    "university-of-alberta": "阿尔伯塔大学",
    "tokyo-institute-of-technology": "东京科学大学",
    "the-university-of-nottingham": "诺丁汉大学",
    "freie-universit-t-berlin": "柏林自由大学",
    "university-of-zurich-uzh": "苏黎世大学",
    "purdue-university": "普渡大学",
    "university-college-dublin": "都柏林大学学院",
    "tohoku-university": "东北大学",
    "queen-mary-university-of-london-qmul": "伦敦玛丽女王大学",
    "rheinisch-westf-lische-technische-hochschule-aachen": "亚琛工业大学",
    "technical-university-of-denmark": "丹麦技术大学",
    "pohang-university-of-science-and-technology-postech": "浦项科技大学",
    "king-saud-university": "沙特国王大学",
    "sungkyunkwan-university": "成均馆大学",
    "qatar-university": "卡塔尔大学",
    "karlsruhe-institute-of-technology-kit": "卡尔斯鲁厄理工学院",
    "sapienza-university-of-rome": "罗马第一大学",
    "university-of-southampton": "南安普顿大学",
    "university-of-waterloo": "滑铁卢大学",
    "utrecht-university": "乌得勒支大学",
    "lomonosov-moscow-state-university": "莫斯科国立大学",
    "university-of-st-andrews": "圣安德鲁斯大学",
    "indian-institute-of-technology-delhi-iitd": "印度理工学院德里分校",
    "leiden-university": "莱顿大学",
    "pontificia-universidad-cat-lica-de-chile": "智利天主教大学",
    "rmit-university": "皇家墨尔本理工大学",
    "rice-university": "莱斯大学",
    "alma-mater-studiorum-university-of-bologna": "博洛尼亚大学",
    "university-of-helsinki": "赫尔辛基大学",
    "university-of-bath": "巴斯大学",
    "aalto-university": "阿尔托大学",
    "macquarie-university": "麦考瑞大学",
    "aarhus-university": "奥胡斯大学",
    "universiti-sains-malaysia-usm": "马来西亚理科大学",
    "universiti-kebangsaan-malaysia-ukm": "马来西亚国民大学",
    "university-of-oslo": "奥斯陆大学",
    "university-of-wisconsin-madison": "威斯康星大学麦迪逊分校",
    "universidade-de-s-o-paulo-usp": "圣保罗大学",
    "indian-institute-of-technology-bombay-iitb": "印度理工学院孟买分校",
    "university-of-science-and-technology-of-china": "中国科学技术大学",
    "university-of-exeter": "埃克塞特大学",
    "university-of-california-davis": "加州大学戴维斯分校",
    "universiti-putra-malaysia-upm": "马来西亚博特拉大学",
    "university-of-liverpool": "利物浦大学",
    "humboldt-universit-t-zu-berlin": "柏林洪堡大学",
    "university-of-vienna": "维也纳大学",
    "georgia-institute-of-technology": "佐治亚理工学院",
    "national-tsing-hua-university": "台湾清华大学",
    "western-university": "西安大略大学",
    "universidad-nacional-aut-noma-de-m-xico-unam": "墨西哥国立自治大学",
    "tongji-university": "同济大学",
    "khalifa-university-of-science-and-technology": "哈利法大学",
    "erasmus-university-rotterdam": "鹿特丹伊拉斯姆斯大学",
    "newcastle-university": "纽卡斯尔大学",
    "ghent-university": "根特大学",
    "university-of-basel": "巴塞尔大学",
    "eindhoven-university-of-technology": "埃因霍芬理工大学",
    "university-of-southern-california": "南加州大学",
    "wageningen-university-and-research": "瓦赫宁根大学",
    "hanyang-university": "汉阳大学",
    "nagoya-university": "名古屋大学",
    "university-of-groningen": "格罗宁根大学",
    "technische-universit-t-berlin": "柏林工业大学",
    "universiti-teknologi-malaysia-utm": "马来西亚理工大学",
    "university-of-north-carolina-chapel-hill": "北卡罗来纳大学教堂山分校",
    "university-of-york": "约克大学",
    "university-of-montreal": "蒙特利尔大学",
    "washington-university-in-st-louis": "圣路易斯华盛顿大学",
    "lancaster-university": "兰卡斯特大学",
    "university-of-barcelona": "巴塞罗那大学",
    "wuhan-university": "武汉大学",
    "stockholm-university": "斯德哥尔摩大学",
    "university-of-geneva": "日内瓦大学",
    "texas-a-and-m-university": "德州农工大学",
    "indian-institute-of-technology-madras-iitm": "印度理工学院马德拉斯分校",
    "kyushu-university": "九州大学",
    "arizona-state-university": "亚利桑那州立大学",
    "university-of-california-santa-barbara-ucsb": "加州大学圣巴巴拉分校",
    "chalmers-university-of-technology": "查尔姆斯理工大学",
    "mcmaster-university": "麦克马斯特大学",
    "queen-s-university-belfast": "贝尔法斯特女王大学",
    "al-farabi-kazakh-national-university": "阿里法拉比哈萨克国立大学",
    "national-yang-ming-chiao-tung-university": "阳明交通大学",
    "cardiff-university": "卡迪夫大学",
    "hokkaido-university": "北海道大学",
    "queen-s-university-ontario": "皇后大学",
    "michigan-state-university": "密歇根州立大学",
    "emory-university": "埃默里大学",
    "university-of-cape-town": "开普敦大学",
    "universidad-de-chile": "智利大学",
    "vrije-universiteit-amsterdam": "阿姆斯特丹自由大学",
    "tecnol-gico-de-monterrey-itesm": "蒙特雷科技大学",
    "curtin-university": "科廷大学",
    "vienna-university-of-technology": "维也纳工业大学",
    "universitas-indonesia": "印度尼西亚大学",
    "university-of-bern": "伯尔尼大学",
    "university-of-wollongong": "伍伦贡大学",
    "universit-catholique-de-louvain-ucl": "鲁汶天主教大学",
    "university-of-reading": "雷丁大学",
    "university-of-otago": "奥塔哥大学",
    "university-complutense-madrid": "马德里康普顿斯大学",
    "king-abdul-aziz-university-kau": "阿卜杜勒阿齐兹国王大学",
}


QS_ALIASES_ZH = {
    "massachusetts-institute-of-technology-mit": ["麻省理工", "MIT"],
    "imperial-college-london": ["帝国理工", "IC"],
    "stanford-university": ["斯坦福"],
    "university-of-oxford": ["牛津"],
    "harvard-university": ["哈佛"],
    "university-of-cambridge": ["剑桥"],
    "california-institute-of-technology-caltech": ["加州理工", "Caltech"],
    "eth-zurich-swiss-federal-institute-of-technology": ["苏黎世理工", "ETH"],
    "ucl-university-college-london": ["UCL"],
    "national-university-of-singapore-nus": ["新国立", "国大", "NUS"],
    "the-university-of-hong-kong": ["港大", "HKU"],
    "nanyang-technological-university-singapore-ntu-singapore": ["南洋理工", "NTU"],
    "peking-university": ["北大", "PKU"],
    "tsinghua-university": ["清华"],
    "university-of-pennsylvania": ["宾大", "UPenn"],
    "the-chinese-university-of-hong-kong": ["港中文", "CUHK"],
    "the-university-of-new-south-wales": ["新南威尔士", "UNSW"],
    "johns-hopkins-university": ["约翰霍普金斯", "霍普金斯", "JHU"],
    "university-of-california-berkeley-ucb": ["伯克利", "UCB"],
    "cole-polytechnique-f-d-rale-de-lausanne": ["洛桑理工", "EPFL"],
    "the-university-of-melbourne": ["墨大"],
    "university-of-chicago": ["芝大"],
    "technical-university-of-munich": ["慕工大", "TUM"],
    "australian-national-university-anu": ["澳国立", "ANU"],
    "monash-university": ["莫纳什"],
    "university-of-toronto": ["多大"],
    "the-hong-kong-university-of-science-and-technology": ["港科", "港科大", "HKUST"],
    "universit-psl": ["巴黎文理", "PSL"],
    "the-university-of-edinburgh": ["爱大"],
    "shanghai-jiao-tong-university": ["上海交大", "交大"],
    "king-s-college-london": ["伦敦国王", "国王学院", "KCL"],
    "seoul-national-university": ["首尔国立大学", "SNU"],
    "the-university-of-tokyo": ["东大"],
    "the-university-of-manchester": ["曼大"],
    "the-university-of-queensland": ["昆大"],
    "columbia-university": ["哥大"],
    "institut-polytechnique-de-paris": ["巴黎综合理工", "IP Paris"],
    "university-of-british-columbia": ["英属哥伦比亚大学", "UBC"],
    "zhejiang-university": ["浙大"],
    "university-of-california-los-angeles-ucla": ["UCLA"],
    "the-hong-kong-polytechnic-university": ["港理工", "PolyU"],
    "university-of-michigan-ann-arbor": ["密歇根安娜堡", "UMich"],
    "city-university-of-hong-kong": ["城大", "港城大", "CityU"],
    "national-taiwan-university-ntu": ["台大"],
    "carnegie-mellon-university": ["卡梅", "CMU"],
    "universiti-malaya-um": ["马大"],
    "new-york-university-nyu": ["纽大", "NYU"],
    "ludwig-maximilians-universit-t-m-nchen": ["路德维希马克西米利安大学", "LMU"],
    "the-london-school-of-economics-and-political-science-lse": ["伦敦政经", "LSE"],
    "kyoto-university": ["京大"],
    "korea-advanced-institute-of-science-and-technology-kaist": ["KAIST"],
    "university-of-auckland": ["奥大"],
    "university-of-texas-at-austin": ["德州大学奥斯汀", "UT Austin"],
    "university-of-illinois-at-urbana-champaign": ["伊利诺伊香槟", "UIUC"],
    "trinity-college-dublin-the-university-of-dublin": ["圣三一", "TCD"],
    "the-university-of-western-australia": ["UWA"],
    "university-of-leeds": ["利兹"],
    "university-of-technology-sydney": ["UTS"],
    "pennsylvania-state-university": ["宾州州立"],
    "tokyo-institute-of-technology": ["东京工业大学", "东工大"],
    "university-college-dublin": ["UCD"],
    "queen-mary-university-of-london-qmul": ["QMUL"],
    "rheinisch-westf-lische-technische-hochschule-aachen": ["RWTH亚琛", "RWTH"],
    "technical-university-of-denmark": ["丹麦科技大学", "DTU"],
    "karlsruhe-institute-of-technology-kit": ["KIT"],
    "lomonosov-moscow-state-university": ["莫大"],
    "university-of-wisconsin-madison": ["威斯康星麦迪逊"],
    "university-of-science-and-technology-of-china": ["中科大", "USTC"],
    "national-tsing-hua-university": ["新竹清华", "国立清华大学"],
    "western-university": ["韦仕敦大学", "西部大学"],
    "university-of-north-carolina-chapel-hill": ["北卡教堂山", "UNC"],
    "washington-university-in-st-louis": ["WashU"],
    "university-of-california-santa-barbara-ucsb": ["加州大学圣塔芭芭拉分校", "UCSB"],
    "national-yang-ming-chiao-tung-university": ["国立阳明交通大学", "阳交大", "NYCU"],
    "queen-s-university-ontario": ["金斯顿女王大学", "加拿大女王大学"],
    "tecnol-gico-de-monterrey-itesm": ["蒙特雷理工"],
    "universit-catholique-de-louvain-ucl": ["UCLouvain"],
}


GLOBAL_SCHOOL_ZH = {
    "Aix Marseille University": "艾克斯-马赛大学",
    "Autonomous University of Barcelona": "巴塞罗那自治大学",
    "Baylor College of Medicine": "贝勒医学院",
    "Beihang University": "北京航空航天大学",
    "Beijing Institute of Technology": "北京理工大学",
    "Beijing Normal University": "北京师范大学",
    "Case Western Reserve University": "凯斯西储大学",
    "Central South University": "中南大学",
    "Charite Universitatsmedizin Berlin": "柏林夏里特医学院",
    "China Agricultural University": "中国农业大学",
    "Chongqing University": "重庆大学",
    "Dalian University of Technology": "大连理工大学",
    "Dartmouth College": "达特茅斯学院",
    "Deakin University": "迪肯大学",
    "Eberhard Karls University, Tübingen": "图宾根大学",
    "Ecole Polytechnique Federale de Lausanne": "洛桑联邦理工学院",
    "Free University of Berlin": "柏林自由大学",
    "Goethe University Frankfurt": "法兰克福大学",
    "Huazhong University of Science and Technology": "华中科技大学",
    "Humboldt University of Berlin": "柏林洪堡大学",
    "Hunan University": "湖南大学",
    "Icahn School of Medicine at Mount Sinai": "西奈山伊坎医学院",
    "Indiana University": "印第安纳大学",
    "Indiana University, Bloomington": "印第安纳大学布卢明顿分校",
    "Jilin University": "吉林大学",
    "Karlsruhe Institute of Technology": "卡尔斯鲁厄理工学院",
    "Karolinska Institute": "卡罗林斯卡学院",
    "King Abdullah University of Science and Technology": "阿卜杜拉国王科技大学",
    "King Fahd University of Petroleum and Minerals": "法赫德国王石油与矿业大学",
    "Korea Advanced Institute of Science and Technology KAIST": "韩国科学技术院",
    "LMU Munich": "慕尼黑大学",
    "London School of Hygiene and Tropical Medicine": "伦敦卫生与热带医学院",
    "Maastricht University": "马斯特里赫特大学",
    "Mayo Clinic College of Medicine and Science, Minnesota": "梅奥诊所医学院",
    "Medical University of Vienna": "维也纳医科大学",
    "Moscow State University": "莫斯科国立大学",
    "Nankai University": "南开大学",
    "Nanyang Technological University": "南洋理工大学",
    "Northwestern Polytechnical University": "西北工业大学",
    "NTNU Norwegian University of Science and Technology": "挪威科技大学",
    "Ohio State University Main campus": "俄亥俄州立大学",
    "Ohio State University, Columbus": "俄亥俄州立大学",
    "Paris Sciences et Lettres PSL Research University Paris": "巴黎文理研究大学",
    "Peking Union Medical College": "北京协和医学院",
    "Penn State Main campus": "宾夕法尼亚州立大学",
    "Pennsylvania State University, University Park": "宾夕法尼亚州立大学",
    "Pompeu Fabra University": "庞培法布拉大学",
    "Purdue University West Lafayette": "普渡大学",
    "Purdue University, West Lafayette": "普渡大学",
    "Queensland University of Technology": "昆士兰科技大学",
    "Radboud University Nijmegen": "拉德堡德大学",
    "Rockefeller University": "洛克菲勒大学",
    "Rutgers, The State University of New Jersey New Brunswick": "罗格斯大学新布朗斯维克分校",
    "Scuola Normale Superiore di Pisa": "比萨高等师范学校",
    "Shandong University": "山东大学",
    "Shenzhen University": "深圳大学",
    "Sichuan University": "四川大学",
    "Soochow University China": "苏州大学",
    "South China University of Technology": "华南理工大学",
    "Southeast University": "东南大学",
    "Southern University of Science and Technology": "南方科技大学",
    "Southern University of Science and Technology SUSTech": "南方科技大学",
    "Sun Yat sen University": "中山大学",
    "Swinburne University of Technology": "斯威本科技大学",
    "Tel Aviv University": "特拉维夫大学",
    "Swiss Federal Institute of Technology Lausanne": "洛桑联邦理工学院",
    "Technical University of Berlin": "柏林工业大学",
    "Technion Israel Institute of Technology": "以色列理工学院",
    "The Education University of Hong Kong": "香港教育大学",
    "The Hebrew University of Jerusalem": "耶路撒冷希伯来大学",
    "The University of Calgary": "卡尔加里大学",
    "The University of Texas MD Anderson Cancer Center": "德州大学MD安德森癌症中心",
    "Tianjin University": "天津大学",
    "Trinity College Dublin": "都柏林圣三一大学",
    "TU Dresden": "德累斯顿工业大学",
    "Tufts University": "塔夫茨大学",
    "Universitat Autonoma de Barcelona UAB": "巴塞罗那自治大学",
    "Universite Grenoble Alpes": "格勒诺布尔阿尔卑斯大学",
    "Universite libre de Bruxelles ULB": "布鲁塞尔自由大学",
    "Universite Paris Cite": "巴黎西岱大学",
    "Universite de Paris": "巴黎大学",
    "University College London": "伦敦大学学院",
    "University of Antwerp": "安特卫普大学",
    "University of Arizona": "亚利桑那大学",
    "University of Alabama Birmingham": "阿拉巴马大学伯明翰分校",
    "University of Barcelona": "巴塞罗那大学",
    "University of Bologna": "博洛尼亚大学",
    "University of Bonn": "波恩大学",
    "University of Calgary": "卡尔加里大学",
    "University of California, Irvine": "加州大学尔湾分校",
    "University of California, San Francisco": "加州大学旧金山分校",
    "University of California, Santa Cruz": "加州大学圣克鲁斯分校",
    "University of Cologne": "科隆大学",
    "University of Colorado Boulder": "科罗拉多大学博尔德分校",
    "University of Colorado Anschutz Medical Campus": "科罗拉多大学安舒茨医学院",
    "University of Chinese Academy of Sciences": "中国科学院大学",
    "University of Electronic Science and Technology of China": "电子科技大学",
    "University of Florida": "佛罗里达大学",
    "University of Freiburg": "弗赖堡大学",
    "University of Goettingen": "哥廷根大学",
    "University of Gottingen": "哥廷根大学",
    "University of Gothenburg": "哥德堡大学",
    "University of Hamburg": "汉堡大学",
    "University of Illinois at Urbana Champaign": "伊利诺伊大学厄巴纳-香槟分校",
    "University of Lausanne": "洛桑大学",
    "University of Leicester": "莱斯特大学",
    "University of Macau": "澳门大学",
    "University of Mainz": "美因茨大学",
    "University of Maryland, College Park": "马里兰大学帕克分校",
    "University of Massachusetts": "马萨诸塞大学",
    "University of Massachusetts Amherst": "马萨诸塞大学阿默斯特分校",
    "University of Massachusetts Chan Medical School": "马萨诸塞大学陈医学院",
    "University of Milan": "米兰大学",
    "University of Minnesota": "明尼苏达大学",
    "University of Minnesota, Twin Cities": "明尼苏达大学双城分校",
    "University of Montpellier": "蒙彼利埃大学",
    "University of Montreal": "蒙特利尔大学",
    "University of Muenster": "明斯特大学",
    "University of Munich": "慕尼黑大学",
    "University of Munster": "明斯特大学",
    "University of Notre Dame": "圣母大学",
    "University of Ottawa": "渥太华大学",
    "University of Padua": "帕多瓦大学",
    "University of Pittsburgh": "匹兹堡大学",
    "University of Pittsburgh Pittsburgh campus": "匹兹堡大学",
    "University of Rochester": "罗切斯特大学",
    "University of Sao Paulo": "圣保罗大学",
    "University of Strasbourg": "斯特拉斯堡大学",
    "University of Texas Southwestern Medical Center": "德州大学西南医学中心",
    "University of Texas Southwestern Medical Center Dallas": "德州大学西南医学中心",
    "University of Tubingen": "图宾根大学",
    "University of Tuebingen": "图宾根大学",
    "University of Twente": "特温特大学",
    "University of Utah": "犹他大学",
    "University of Virginia Main campus": "弗吉尼亚大学",
    "University of Virginia": "弗吉尼亚大学",
    "University of Wurzburg": "维尔茨堡大学",
    "UNSW Sydney": "新南威尔士大学",
    "Vanderbilt University": "范德堡大学",
    "Weizmann Institute of Science": "魏茨曼科学研究所",
    "Xiamen University": "厦门大学",
    "Xi an Jiaotong University": "西安交通大学",
    "Zhengzhou University": "郑州大学",
}


GLOBAL_ALIASES_ZH = {
    "Nanyang Technological University": ["南洋理工", "NTU"],
    "University College London": ["UCL"],
    "UNSW Sydney": ["新南威尔士", "UNSW"],
    "Southern University of Science and Technology": ["南科大", "SUSTech"],
    "Southern University of Science and Technology SUSTech": ["南科大", "SUSTech"],
    "Huazhong University of Science and Technology": ["华科", "HUST"],
    "University of Illinois at Urbana Champaign": ["伊利诺伊香槟", "UIUC"],
    "Penn State Main campus": ["宾州州立"],
    "Pennsylvania State University, University Park": ["宾州州立"],
    "Purdue University West Lafayette": ["普渡"],
    "Purdue University, West Lafayette": ["普渡"],
    "Ohio State University Main campus": ["OSU"],
    "Ohio State University, Columbus": ["OSU"],
    "University of California, Irvine": ["UCI"],
    "University of California, San Francisco": ["UCSF"],
    "University of California, Santa Cruz": ["UCSC"],
    "University of Colorado Boulder": ["科罗拉多博尔德"],
    "University of Maryland, College Park": ["UMD"],
    "University of Minnesota, Twin Cities": ["明大双城"],
    "University of Pittsburgh": ["匹大"],
    "University of Pittsburgh Pittsburgh campus": ["匹大"],
    "Case Western Reserve University": ["凯斯西储"],
    "Rutgers, The State University of New Jersey New Brunswick": ["罗格斯"],
    "University of Electronic Science and Technology of China": ["电子科大", "UESTC"],
    "Beihang University": ["北航"],
    "Beijing Institute of Technology": ["北理工"],
    "Beijing Normal University": ["北师大"],
    "Dalian University of Technology": ["大工"],
    "Xi an Jiaotong University": ["西交大"],
    "Sun Yat sen University": ["中大"],
    "South China University of Technology": ["华工"],
    "Northwestern Polytechnical University": ["西工大"],
    "Peking Union Medical College": ["协和"],
    "Technion Israel Institute of Technology": ["Technion"],
    "Trinity College Dublin": ["圣三一", "TCD"],
    "Universite libre de Bruxelles ULB": ["ULB"],
    "Universitat Autonoma de Barcelona UAB": ["UAB"],
    "Korea Advanced Institute of Science and Technology KAIST": ["KAIST"],
    "LMU Munich": ["LMU"],
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def normalized_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = (
        value.replace("–", " ").replace("—", " ").replace("-", " ").replace("'", " ")
    )
    return re.sub(r"[^a-zA-Z0-9]+", " ", value).strip().lower()


def cleaned_aliases(primary: str, aliases: list[str]) -> list[str]:
    seen = set()
    clean = []
    for alias in aliases:
        alias = alias.strip()
        if alias and alias != primary and alias not in seen:
            seen.add(alias)
            clean.append(alias)
    return clean


def insert_after(payload: dict, after_key: str, key: str, value) -> dict:
    rebuilt = {}
    inserted = False
    for current_key, current_value in payload.items():
        rebuilt[current_key] = current_value
        if current_key == after_key:
            rebuilt[key] = value
            inserted = True
    if not inserted:
        rebuilt[key] = value
    return rebuilt


def update_universities() -> dict[str, dict]:
    path = ROOT / "data" / "universities.json"
    payload = load_json(path)
    missing = []
    by_id = {}

    for university in payload["universities"]:
        uid = university["id"]
        if uid in QS_SCHOOL_ZH and not university.get("schoolZh"):
            university["schoolZh"] = QS_SCHOOL_ZH[uid]
        if not university.get("schoolZh"):
            missing.append(uid)

        if uid in QS_ALIASES_ZH:
            aliases = cleaned_aliases(
                university.get("schoolZh", ""), QS_ALIASES_ZH[uid]
            )
            if aliases:
                university.pop("schoolAliasesZh", None)
                university.update(
                    insert_after(university, "schoolZh", "schoolAliasesZh", aliases)
                )
        else:
            university.pop("schoolAliasesZh", None)
        by_id[uid] = university

    if missing:
        raise SystemExit(f"Missing schoolZh in data/universities.json: {missing}")

    write_json(path, payload)
    return by_id


def update_global_rankings(universities_by_id: dict[str, dict]) -> None:
    path = ROOT / "data" / "global-rankings.json"
    payload = load_json(path)
    global_names = {
        normalized_key(key): value for key, value in GLOBAL_SCHOOL_ZH.items()
    }
    global_aliases = {
        normalized_key(key): value for key, value in GLOBAL_ALIASES_ZH.items()
    }
    missing = []

    for ranking in payload["rankings"].values():
        for row in ranking.get("rows", []):
            university = universities_by_id.get(
                row.get("universityId") or row.get("id")
            )
            norm = normalized_key(row.get("school", ""))

            if university and university.get("schoolZh"):
                row["schoolZh"] = university["schoolZh"]
                row.pop("schoolAliasesZh", None)
                if university.get("schoolAliasesZh"):
                    row.update(
                        insert_after(
                            row,
                            "schoolZh",
                            "schoolAliasesZh",
                            university["schoolAliasesZh"],
                        )
                    )
            elif not row.get("schoolZh") and norm in global_names:
                row["schoolZh"] = global_names[norm]

            if not university and norm in global_aliases:
                aliases = cleaned_aliases(row.get("schoolZh", ""), global_aliases[norm])
                if aliases:
                    row.pop("schoolAliasesZh", None)
                    row.update(
                        insert_after(row, "schoolZh", "schoolAliasesZh", aliases)
                    )

            if not row.get("schoolZh"):
                missing.append(row.get("school", ""))

    if missing:
        raise SystemExit(
            f"Missing schoolZh in data/global-rankings.json: {sorted(set(missing))}"
        )

    write_json(path, payload)


def main() -> None:
    universities_by_id = update_universities()
    update_global_rankings(universities_by_id)
    print("Localized school names updated.")


if __name__ == "__main__":
    main()
