"""介護の空白地帯：介護サービス情報公表システムのオープンデータ（事業所一覧）と、
住民基本台帳の市区町村別・年齢階級別人口を組み合わせ、
75歳以上の人口あたりの介護事業所数を市区町村ごとに比べる。"""
import io
import re
from collections import defaultdict

from lib import oc

KAIGO = "https://www.mhlw.go.jp/stf/kaigo-kouhyou_opendata.html"
JUKI = "https://www.soumu.go.jp/main_sosiki/jichi_gyousei/daityo/jinkou_jinkoudoutai-setaisuu.html"

# ランキングに使うサービス（コード: 表示名）。名前はページのリンク文字から取り直す。
FOCUS = {"110": "訪問介護", "130": "訪問看護", "150": "通所介護", "510": "介護老人福祉施設（特養）",
         "520": "介護老人保健施設", "320": "認知症グループホーム", "730": "小規模多機能型居宅介護", "430": "居宅介護支援"}


def kaigo_files():
    html = oc.decode(oc.get(KAIGO))
    found = {}
    for u, text, before in oc.anchors(KAIGO, r"jigyosho_\d{3}[^/]*\.(csv|zip)$", html):
        code = re.search(r"jigyosho_(\d{3})", u).group(1)
        if code in found:
            continue          # ページの上（＝最新の時点）を優先
        m = re.search(r"%s[_＿\s]*([^\s（(]+)" % code, before + " " + text)
        found[code] = (u, m.group(1) if m else FOCUS.get(code, code))
    oc.check(len(found) >= 20, "介護オープンデータのCSVリンクが少なすぎます(%d)" % len(found))
    pm = re.search(r"(20\d\d)年(\d{1,2})月末時点", html)
    return found, (pm.group(0) if pm else "")


def kaigo_counts(files):
    cnt = defaultdict(lambda: defaultdict(int))     # 市区町村コード5桁 → サービス → 事業所数
    cap = defaultdict(lambda: defaultdict(float))   # 定員
    names = {}
    for code, (u, label) in files.items():
        b = oc.get(u, timeout=300)
        if u.endswith(".zip"):
            b = next(v for k, v in oc.unzip(b).items() if k.lower().endswith(".csv"))
        df = oc.read_csv(b)
        c_city = oc.col(df, "市区町村コード", required=False) or oc.col(df, "市町村コード")
        c_cap = oc.col(df, "定員", required=False)
        c_pn, c_cn = oc.col(df, "都道府県名", required=False), oc.col(df, "市区町村名", required=False)
        for i, cc in enumerate(df[c_city].tolist()):
            k = re.sub(r"\D", "", str(cc))[:5]
            if len(k) != 5:
                continue
            cnt[k][code] += 1
            if c_cap:
                cap[k][code] += oc.num(df[c_cap].iat[i]) or 0
            if c_pn and c_cn and k not in names:
                names[k] = df[c_pn].iat[i] + df[c_cn].iat[i]
        oc.log("kaigo", code, label, len(df))
    return cnt, cap, names


def population():
    """住基の『市区町村別 年齢階級別人口（総計）』xlsx を探して 75歳以上・65歳以上人口を返す。"""
    import openpyxl
    cands = oc.anchors(JUKI, r"\.xlsx?$")
    oc.check(cands, "住民基本台帳人口のExcelが見つかりません")
    # リンク文字で選ぶ：例「【総計】令和8住民基本台帳年齢階級別人口（市区町村別）」
    cands = [c for c in cands if "総計" in c[1] and "年齢" in c[1] and "市区町村" in c[1]] or \
            [c for c in cands if "年齢" in c[1] + c[2][-40:] and "市区町村" in c[1] + c[2][-40:]
             and "外国人" not in c[1] and "日本人" not in c[1]]
    for u, text, before in cands:
        wb = openpyxl.load_workbook(io.BytesIO(oc.get(u, timeout=300)), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
        hdr_i = next((i for i, r in enumerate(rows[:30])
                      if any(re.match(r"^75\D", str(c or "").strip()) and "歳" in str(c) for c in r)), None)
        if hdr_i is None:
            continue
        hdr = [str(c or "").replace("\n", "") for c in rows[hdr_i]]
        i_code = next(i for i, h in enumerate(hdr) if "コード" in h)
        i_sex = next((i for i, h in enumerate(hdr) if "性別" in h), None)
        def ages(start):
            return [i for i, h in enumerate(hdr) if "歳" in h and re.match(r"^(\d+)\D", h)
                    and int(re.match(r"^(\d+)", h).group(1)) >= start]
        a75, a65 = ages(75), ages(65)
        i_tot = next((i for i, h in enumerate(hdr) if h in ("総数", "計", "合計")), None)
        i_pn = next((i for i, h in enumerate(hdr) if "都道府県" in h), None)
        i_cn = next((i for i, h in enumerate(hdr) if "市区町村" in h and "コード" not in h), None)
        oc.check(a75 and a65, "年齢階級の列を読み取れません")
        pop = {}
        for r in rows[hdr_i + 1:]:
            code = re.sub(r"\D", "", str(r[i_code] or ""))
            if len(code) < 5 or code[2:5] == "000":
                continue
            if i_sex is not None and str(r[i_sex]).strip() not in ("計", "総数", "男女計"):
                continue
            def s(ix):
                return sum(oc.num(r[i]) or 0 for i in ix)
            nm = (str(r[i_pn] or "") if i_pn is not None else "") + (str(r[i_cn] or "") if i_cn is not None else "")
            pop[code[:5]] = {"p75": s(a75), "p65": s(a65), "tot": oc.num(r[i_tot]) if i_tot is not None else None,
                             "name": nm.replace("\u3000", "").replace(" ", "")}
        if len(pop) > 1500:
            m = re.search(r"令和(\d+)年?住民基本台帳", text)
            when = ("%d年1月1日" % (2018 + int(m.group(1)))) if m else ""
            return pop, u, when
    raise oc.DataError("市区町村別・年齢階級別人口（総計）の表を特定できません")


def run():
    files, when = kaigo_files()
    cnt, cap, names = kaigo_counts(files)
    pop, popurl, popwhen = population()
    oc.check(len(set(cnt) & set(pop)) > 1500, "介護データと人口データの市区町村コードが合いません")

    R = []
    method = ("介護サービス情報公表システムに登録された事業所（%s）を市区町村ごとに数え、住民基本台帳の75歳以上人口（%s）"
              "1,000人あたりに直しました。事業所の所在地で数えるため、隣の市町村の事業所を使っている地域では少なく見えます。"
              "75歳以上人口が500人未満の町村は割合がぶれやすいため除いています。" % (when or "最新時点", popwhen or "最新"))
    for code, label in FOCUS.items():
        if code not in files:
            continue
        rows = []
        for k, p in pop.items():
            if p["p75"] < 500:
                continue
            n = cnt.get(k, {}).get(code, 0)
            rows.append({"city": p.get("name") or names.get(k) or k, "pref": oc.pref_name(k), "n": n, "p75": p["p75"],
                         "per": n / p["p75"] * 1000})
        rows.sort(key=lambda x: (x["per"], -x["p75"]))
        zero = sum(1 for x in rows if x["n"] == 0)
        R.append({"id": "s" + code, "tab": label, "title": "%sが少ない市区町村" % label,
                  "desc": "75歳以上1,000人あたりの%sの事業所数が少ない順。事業所が1つもない市区町村は%d。" % (label, zero),
                  "rows": rows, "trend": oc.trend(rows, "pref", 50, "市区町村", "市区町村"), "method": method,
                  "columns": [{"key": "city", "label": "市区町村"},
                              {"key": "per", "label": "75歳以上千人あたり", "type": "num", "fmt": "2"},
                              {"key": "n", "label": "事業所数", "type": "num"},
                              {"key": "p75", "label": "75歳以上人口", "type": "num", "bar": True}],
                  "share_label": "city", "share_value": "per"})
    # 主要サービスのうち、いくつが「ゼロ」か
    zr = []
    for k, p in pop.items():
        if p["p75"] < 300:
            continue
        missing = [FOCUS[c] for c in FOCUS if c in files and cnt.get(k, {}).get(c, 0) == 0]
        if missing:
            zr.append({"city": p.get("name") or names.get(k) or k, "pref": oc.pref_name(k), "m": len(missing), "list": "、".join(missing), "p75": p["p75"]})
    zr.sort(key=lambda x: (-x["m"], -x["p75"]))
    R.insert(0, {"id": "zero", "tab": "ないサービス", "title": "町の中に事業所がない介護サービスの数",
                 "desc": "主な%dサービスのうち、市区町村内に事業所が1つもないサービスの数。" % len([c for c in FOCUS if c in files]),
                 "rows": zr, "trend": oc.trend(zr, "pref", 50, "市区町村", "市区町村"), "method": method,
                 "columns": [{"key": "city", "label": "市区町村"},
                             {"key": "m", "label": "ないサービス数", "type": "num", "bar": True},
                             {"key": "list", "label": "ないサービス"},
                             {"key": "p75", "label": "75歳以上人口", "type": "num"}],
                 "share_label": "city", "share_value": "m"})
    meta = {"data_period": when,
            "stats": [{"label": "登録されている介護事業所", "value": sum(sum(v.values()) for v in cnt.values()), "unit": "か所"},
                      {"label": "主なサービスが1つ以上ない市区町村", "value": len(zr), "unit": ""},
                      {"label": "75歳以上人口", "value": sum(p["p75"] for p in pop.values()) / 10000, "unit": "万人"}],
            "sources": [{"name": "介護サービス情報公表システム オープンデータ", "org": "厚生労働省", "url": KAIGO,
                         "license": "CC BY 4.0（介護サービス情報公表システムから抽出したデータを加工）", "retrieved": oc.today()},
                        {"name": "住民基本台帳に基づく人口、人口動態及び世帯数（市区町村別 年齢階級別人口）", "org": "総務省",
                         "url": JUKI, "license": "公共データ利用規約", "retrieved": oc.today()}]}
    oc.write(meta, R)


if __name__ == "__main__":
    oc.main(run)
