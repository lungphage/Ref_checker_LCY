#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import copy
import csv
import difflib
import html
import json
import re
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "参考文献真实性自动核验工具 v5"
DEFAULT_EMAIL = "your_email@example.com"
REQUEST_TIMEOUT = 25
REQUEST_RETRIES = 3
REQUEST_PAUSE = 0.2
RESULT_COLUMNS = [
    "编号",
    "状态",
    "相似度",
    "数据源",
    "输入参考文献",
    "提取标题",
    "匹配标题",
    "匹配作者",
    "期刊",
    "输入年份",
    "匹配年份",
    "DOI",
    "链接",
    "建议",
    "谷歌学术搜索",
]
TREE_COLUMNS = ["编号", "状态", "相似度", "数据源", "匹配标题", "期刊", "匹配年份", "DOI", "建议"]
STATUS_PRIORITY = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NOT_FOUND": 3}
TEXT_FALLBACK_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030", "gbk", "big5")
FILTER_OPTIONS = ["全部", "HIGH", "MEDIUM", "LOW", "NOT_FOUND", "重复条目", "疑似网络失败"]
SORT_OPTIONS = ["综合优先级", "相似度降序", "相似度升序", "编号升序", "编号降序"]

HTTP_CACHE = {}


def log_error(msg):
    with open("debug_log.txt", "a", encoding="utf-8") as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
        f.write(str(msg) + "\n")


def clean_text(text):
    if not text:
        return ""
    text = str(text).lower()
    text = re.sub(r"\[[a-z]\]", " ", text)
    text = re.sub(r"doi\s*[:：]?\s*\S+", " ", text, flags=re.I)
    text = re.sub(r"https?://\S+", " ", text, flags=re.I)
    text = re.sub(r"[\u3000]+", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def token_similarity(a, b):
    a = clean_text(a)
    b = clean_text(b)
    if not a or not b:
        return 0.0

    ratio = difflib.SequenceMatcher(None, a, b).ratio() * 100
    set_a = set(a.split())
    set_b = set(b.split())
    jaccard = (len(set_a & set_b) / len(set_a | set_b) * 100) if set_a and set_b else 0
    cover = (len(set_a & set_b) / len(set_a) * 100) if set_a else 0
    return round(max(ratio, jaccard * 1.1, cover * 0.95), 1)


def extract_ref_no(ref):
    match = re.match(r"\s*\[(\d+)\]", ref)
    return match.group(1) if match else ""


def extract_year(ref):
    years = re.findall(r"\b(19\d{2}|20\d{2})\b", ref)
    return years[-1] if years else ""


def normalize_doi(doi):
    if not doi:
        return ""
    doi = doi.strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi\s*[:：]?\s*", "", doi, flags=re.I)
    doi = doi.rstrip(".,;)]} ")
    return doi


def extract_doi(ref):
    match = re.search(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", ref, flags=re.I)
    return normalize_doi(match.group(1)) if match else ""


def extract_title(ref):
    text = re.sub(r"^\s*\[\d+\]\s*", "", ref).strip()
    text = re.sub(r"\s*doi\s*[:：]?\s*\S+\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    patterns = [
        r"(?:et al\.|等\.)\s*(.+?)\s*\[[A-Za-z]\]",
        r"\.\s*([^\.]{8,320}?)\s*\[[A-Za-z]\]",
        r"[。．.]\s*([^。．.]{8,320}?)\s*\[[A-Za-z]\]",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            title = match.group(1).strip(" .;，,")
            if len(clean_text(title)) >= 5:
                return title

    parts = [p.strip() for p in re.split(r"[。．.]", text) if p.strip()]
    if len(parts) >= 2:
        candidate = parts[1].strip(" ;，,")
        if len(clean_text(candidate)) >= 5:
            return candidate

    return text[:250]


def extract_authors(ref):
    text = re.sub(r"^\s*\[\d+\]\s*", "", ref).strip()
    text = re.sub(r"\s+", " ", text)
    match = re.match(r"(.+?)(?:\.\s+|[。．])", text)
    if not match:
        return []

    author_part = match.group(1)
    author_part = re.sub(r"\bet al\b\.?", "", author_part, flags=re.I)
    author_part = author_part.replace("，", ",").replace("；", ";")
    parts = re.split(r"[,;]| and ", author_part, flags=re.I)
    authors = []
    for part in parts:
        name = clean_text(part)
        if len(name) >= 2:
            authors.append(name)
    return authors[:8]


def parse_reference_context(ref):
    return {
        "ref_no": extract_ref_no(ref),
        "title": extract_title(ref),
        "year": extract_year(ref),
        "doi": extract_doi(ref),
        "authors": extract_authors(ref),
    }


def get_scholar_url(query):
    return "https://scholar.google.com/scholar?q=" + urllib.parse.quote(query)


def clone_result_row(row, ref, ref_no):
    new_row = copy.deepcopy(row)
    new_row["编号"] = ref_no
    new_row["输入参考文献"] = ref
    new_row["谷歌学术搜索"] = get_scholar_url(new_row.get("提取标题") or ref)
    new_row["_is_duplicate"] = True
    base_note = new_row.get("建议", "")
    duplicate_note = "该条与前面参考文献内容重复，已直接复用前一次核验结果。"
    new_row["建议"] = duplicate_note if not base_note else duplicate_note + " " + base_note
    return new_row


def ref_cache_key(ref, parsed_ref=None):
    parsed_ref = parsed_ref or parse_reference_context(ref)
    title = clean_text(parsed_ref["title"])
    doi = normalize_doi(parsed_ref["doi"]).lower()
    year = parsed_ref["year"]
    if doi:
        return "doi:" + doi
    if title:
        return "title:" + title + "|year:" + year
    return "raw:" + clean_text(ref)


def http_get_json(url, params=None, timeout=REQUEST_TIMEOUT):
    query = urllib.parse.urlencode(params or {})
    full_url = url + ("?" + query if query else "")
    if full_url in HTTP_CACHE:
        return HTTP_CACHE[full_url]

    headers = {
        "User-Agent": "ReferenceChecker-v5.2 (mailto:%s)" % DEFAULT_EMAIL,
        "Accept": "application/json",
    }
    last_error = None
    for attempt in range(REQUEST_RETRIES):
        try:
            req = urllib.request.Request(full_url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(data)
            HTTP_CACHE[full_url] = parsed
            return parsed
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            retryable = not isinstance(exc, urllib.error.HTTPError) or exc.code in (408, 409, 425, 429, 500, 502, 503, 504)
            if attempt >= REQUEST_RETRIES - 1 or not retryable:
                break
            time.sleep(0.8 * (attempt + 1))
    raise last_error


def remember_error(error_list, source, message):
    error_list.append(f"{source}: {message}")


def crossref_by_doi(doi, error_list=None):
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    try:
        data = http_get_json(url)
        item = data.get("message", {})
        return [parse_crossref_item(item)]
    except Exception as exc:
        log_error("Crossref DOI search failed: %s\n%s" % (doi, traceback.format_exc()))
        if error_list is not None:
            remember_error(error_list, "Crossref DOI", str(exc))
        return []


def crossref_search(query, error_list=None):
    params = {
        "query.bibliographic": query,
        "rows": 6,
        "mailto": DEFAULT_EMAIL,
    }
    try:
        data = http_get_json("https://api.crossref.org/works", params=params)
        items = data.get("message", {}).get("items", [])
        return [parse_crossref_item(item) for item in items]
    except Exception as exc:
        log_error("Crossref search failed:\n%s\n%s" % (query, traceback.format_exc()))
        if error_list is not None:
            remember_error(error_list, "Crossref Search", str(exc))
        return []


def get_crossref_year(item):
    for key in ("published-print", "published-online", "published", "issued"):
        if key in item:
            parts = item.get(key, {}).get("date-parts", [])
            if parts and parts[0]:
                return str(parts[0][0])
    return ""


def parse_crossref_item(item):
    title = item.get("title", [""])
    journal = item.get("container-title", [""])
    authors = []
    for author in item.get("author", [])[:8]:
        name = " ".join([author.get("given", ""), author.get("family", "")]).strip()
        if name:
            authors.append(name)
    return {
        "source": "Crossref",
        "title": title[0] if title else "",
        "year": get_crossref_year(item),
        "journal": journal[0] if journal else "",
        "doi": normalize_doi(item.get("DOI", "")),
        "url": item.get("URL", ""),
        "authors": "; ".join(authors),
    }


def openalex_search(query, error_list=None):
    params = {
        "search": query,
        "per-page": 6,
        "mailto": DEFAULT_EMAIL,
    }
    try:
        data = http_get_json("https://api.openalex.org/works", params=params)
        items = data.get("results", [])
        return [parse_openalex_item(item) for item in items]
    except Exception as exc:
        log_error("OpenAlex search failed:\n%s\n%s" % (query, traceback.format_exc()))
        if error_list is not None:
            remember_error(error_list, "OpenAlex", str(exc))
        return []


def parse_openalex_item(item):
    title = item.get("title", "") or ""
    year = str(item.get("publication_year", "") or "")
    location = item.get("primary_location") or {}
    source = location.get("source") or {}
    doi = normalize_doi(item.get("doi", "") or "")
    authors = []
    for authorship in item.get("authorships", [])[:8]:
        author = authorship.get("author") or {}
        if author.get("display_name"):
            authors.append(author.get("display_name"))
    return {
        "source": "OpenAlex",
        "title": title,
        "year": year,
        "journal": source.get("display_name", "") or "",
        "doi": doi,
        "url": item.get("doi") or item.get("id") or "",
        "authors": "; ".join(authors),
    }


def dedupe_candidates(candidates):
    seen = set()
    unique = []
    for candidate in candidates:
        key = (
            normalize_doi(candidate.get("doi", "")).lower(),
            clean_text(candidate.get("title", "")),
            clean_text(candidate.get("journal", "")),
            candidate.get("year", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def judge(ref, candidate, parsed_ref=None):
    parsed_ref = parsed_ref or parse_reference_context(ref)
    input_title = parsed_ref["title"]
    ref_year = parsed_ref["year"]
    ref_doi = parsed_ref["doi"]
    ref_authors = parsed_ref["authors"]

    title = candidate.get("title", "")
    sim_title = token_similarity(input_title, title)
    sim_ref = token_similarity(ref, title)
    sim = max(sim_title, sim_ref)

    candidate_year = candidate.get("year", "")
    year_match = not (ref_year and candidate_year) or ref_year == candidate_year

    ref_author_text = " ".join(ref_authors)
    candidate_author_text = candidate.get("authors", "")
    author_sim = token_similarity(ref_author_text, candidate_author_text) if ref_author_text and candidate_author_text else 0

    candidate_doi = normalize_doi(candidate.get("doi", ""))
    doi_match = bool(ref_doi and candidate_doi and ref_doi.lower() == candidate_doi.lower())
    if doi_match:
        sim = max(sim, 99.0)

    if author_sim >= 65:
        sim = min(100.0, sim + 3)
    elif ref_authors and candidate_author_text and author_sim < 30:
        sim = max(0.0, sim - 4)

    if ref_year and candidate_year and not year_match:
        sim = max(0.0, sim - 8)

    sim = round(min(100.0, max(0.0, sim)), 1)

    if doi_match or (sim >= 90 and year_match):
        status = "HIGH"
        note = "标题高度一致，且年份或 DOI 可以互相印证，基本可确认真实存在。"
    elif sim >= 80 and year_match:
        status = "MEDIUM"
        note = "标题较为一致，建议再人工核对作者、期刊和卷期信息。"
    elif sim >= 72:
        status = "MEDIUM"
        note = "找到较相近结果，但年份或作者存在偏差，建议人工复核。"
    elif sim >= 56:
        status = "LOW"
        note = "只找到相似文献，不建议直接引用当前匹配结果。"
    else:
        status = "NOT_FOUND"
        note = "未找到可靠匹配，建议使用标题或作者到谷歌学术继续检索。"
    return status, sim, note


def pick_crossref_queries(ref, parsed_ref):
    queries = []
    if parsed_ref["title"]:
        queries.append(parsed_ref["title"])
    queries.append(ref)
    if parsed_ref["authors"] and parsed_ref["title"]:
        queries.append(parsed_ref["authors"][0] + " " + parsed_ref["title"])

    unique = []
    seen = set()
    for query in queries:
        cleaned = clean_text(query)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique.append(query)
    return unique


def build_result_row(ref, parsed_ref, candidate, status, sim, note, network_notes=None):
    search_query = parsed_ref["title"] or ref
    if network_notes:
        note = note + " 检索过程中部分接口请求失败，结果可能不完整。"
    return {
        "编号": parsed_ref["ref_no"],
        "状态": status,
        "相似度": sim,
        "数据源": candidate.get("source", ""),
        "输入参考文献": ref,
        "提取标题": parsed_ref["title"],
        "匹配标题": candidate.get("title", ""),
        "匹配作者": candidate.get("authors", ""),
        "期刊": candidate.get("journal", ""),
        "输入年份": parsed_ref["year"],
        "匹配年份": candidate.get("year", ""),
        "DOI": candidate.get("doi", ""),
        "链接": candidate.get("url", ""),
        "建议": note,
        "谷歌学术搜索": get_scholar_url(search_query),
        "_network_error": bool(network_notes),
        "_network_notes": " | ".join(network_notes or []),
        "_is_duplicate": False,
    }


def check_one_reference(ref):
    ref = ref.strip()
    parsed_ref = parse_reference_context(ref)
    candidates = []
    network_errors = []

    if parsed_ref["doi"]:
        candidates.extend(crossref_by_doi(parsed_ref["doi"], network_errors))

    for query in pick_crossref_queries(ref, parsed_ref):
        candidates.extend(crossref_search(query, network_errors))
        if candidates:
            current_best = max((judge(ref, candidate, parsed_ref)[1] for candidate in candidates), default=0)
            if current_best >= 92:
                break

    candidates = dedupe_candidates(candidates)
    current_best = max((judge(ref, candidate, parsed_ref)[1] for candidate in candidates), default=0)
    if current_best < 80:
        candidates.extend(openalex_search(parsed_ref["title"] or ref, network_errors))
        candidates = dedupe_candidates(candidates)

    best = None
    for candidate in candidates:
        status, sim, note = judge(ref, candidate, parsed_ref)
        row = build_result_row(ref, parsed_ref, candidate, status, sim, note, network_errors)
        if best is None or row["相似度"] > best["相似度"]:
            best = row

    if best is None:
        note = "Crossref 和 OpenAlex 均未返回可靠结果，建议改用标题、作者和年份到谷歌学术继续检索。"
        if network_errors:
            note = "接口请求失败，可能受网络或限流影响。建议稍后重试，或使用谷歌学术人工核对。"
        best = {
            "编号": parsed_ref["ref_no"],
            "状态": "NOT_FOUND",
            "相似度": 0,
            "数据源": "",
            "输入参考文献": ref,
            "提取标题": parsed_ref["title"],
            "匹配标题": "",
            "匹配作者": "",
            "期刊": "",
            "输入年份": parsed_ref["year"],
            "匹配年份": "",
            "DOI": parsed_ref["doi"],
            "链接": "",
            "建议": note,
            "谷歌学术搜索": get_scholar_url(parsed_ref["title"] or ref),
            "_network_error": bool(network_errors),
            "_network_notes": " | ".join(network_errors),
            "_is_duplicate": False,
        }
    return best


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows([{col: row.get(col, "") for col in RESULT_COLUMNS} for row in rows])


def col_letter(n):
    text = ""
    while n:
        n, r = divmod(n - 1, 26)
        text = chr(65 + r) + text
    return text


def write_minimal_xlsx(path, rows):
    if not rows:
        return
    data = [RESULT_COLUMNS] + [[row.get(col, "") for col in RESULT_COLUMNS] for row in rows]

    def cell_xml(r, c, value):
        ref = f"{col_letter(c)}{r}"
        value = "" if value is None else str(value)
        return f'<c r="{ref}" t="inlineStr"><is><t>{html.escape(value)}</t></is></c>'

    sheet_rows = []
    for row_index, row in enumerate(data, start=1):
        cells = "".join(cell_xml(row_index, col_index, value) for col_index, value in enumerate(row, start=1))
        sheet_rows.append(f'<row r="{row_index}">{cells}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>" + "".join(sheet_rows) + "</sheetData></worksheet>"
    )

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="reference_check" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""

    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

    styles = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="1"><fill><patternFill patternType="none"/></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>"""

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        zf.writestr("xl/styles.xml", styles)


def read_text_file(path):
    for encoding in TEXT_FALLBACK_ENCODINGS:
        try:
            with open(path, "r", encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


class ReferenceCheckerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1420x860")
        self.root.minsize(1220, 760)
        self.rows = []
        self.running = False
        self.cancel_requested = False
        self.processed_cache = {}
        self.stats = {"duplicates_reused": 0, "network_warnings": 0, "total_input": 0}
        self.summary_var = tk.StringVar(value="结果统计：尚未开始")
        self.status_var = tk.StringVar(value="准备就绪")
        self.filter_var = tk.StringVar(value="全部")
        self.sort_var = tk.StringVar(value="综合优先级")
        self.author_var = tk.StringVar(value="原作者：李晨宇 | 优化：刘梓峰")
        self.stat_vars = {
            "HIGH": tk.StringVar(value="0"),
            "MEDIUM": tk.StringVar(value="0"),
            "LOW": tk.StringVar(value="0"),
            "NOT_FOUND": tk.StringVar(value="0"),
            "META": tk.StringVar(value="重复 0 | 网络 0"),
        }
        self.configure_styles()
        self.build_ui()

    def configure_styles(self):
        self.palette = {
            "bg": "#F4F7FB",
            "panel": "#FFFFFF",
            "panel_alt": "#EEF3FF",
            "ink": "#132238",
            "muted": "#63758B",
            "line": "#D7E0EA",
            "accent": "#1F6FEB",
            "accent_soft": "#DCEBFF",
            "success": "#1F8F5F",
            "success_soft": "#E5F7ED",
            "warn": "#C48315",
            "warn_soft": "#FFF3D8",
            "danger": "#C84646",
            "danger_soft": "#FFE3E3",
            "shadow": "#E9EEF5",
        }
        self.root.configure(bg=self.palette["bg"])
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("App.TFrame", background=self.palette["bg"])
        style.configure("Card.TFrame", background=self.palette["panel"], relief="flat")
        style.configure("SoftCard.TFrame", background=self.palette["panel_alt"], relief="flat")
        style.configure("TLabel", background=self.palette["bg"], foreground=self.palette["ink"])
        style.configure("Card.TLabel", background=self.palette["panel"], foreground=self.palette["ink"])
        style.configure("Muted.TLabel", background=self.palette["bg"], foreground=self.palette["muted"])
        style.configure("HeroTitle.TLabel", background=self.palette["bg"], foreground=self.palette["ink"], font=("Microsoft YaHei UI", 22, "bold"))
        style.configure("HeroSub.TLabel", background=self.palette["bg"], foreground=self.palette["muted"], font=("Microsoft YaHei UI", 10))
        style.configure("Section.TLabel", background=self.palette["bg"], foreground=self.palette["ink"], font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("CardTitle.TLabel", background=self.palette["panel"], foreground=self.palette["ink"], font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("CardValue.TLabel", background=self.palette["panel"], foreground=self.palette["ink"], font=("Segoe UI Semibold", 20, "bold"))
        style.configure("Meta.TLabel", background=self.palette["panel"], foreground=self.palette["muted"], font=("Microsoft YaHei UI", 9))
        style.configure("Author.TLabel", background=self.palette["panel_alt"], foreground=self.palette["ink"], font=("Microsoft YaHei UI", 9, "bold"))

        style.configure("Primary.TButton", background=self.palette["accent"], foreground="#FFFFFF", borderwidth=0, focusthickness=0, padding=(16, 10))
        style.map("Primary.TButton", background=[("active", "#165DCC")], foreground=[("disabled", "#DDE6F6")])
        style.configure("Secondary.TButton", background=self.palette["panel"], foreground=self.palette["ink"], bordercolor=self.palette["line"], borderwidth=1, padding=(14, 9))
        style.map("Secondary.TButton", background=[("active", "#F8FBFF")])
        style.configure("Danger.TButton", background="#FDECEC", foreground=self.palette["danger"], borderwidth=0, padding=(14, 9))
        style.map("Danger.TButton", background=[("active", "#FBDADA")])

        style.configure(
            "Modern.Horizontal.TProgressbar",
            troughcolor="#E6EDF7",
            bordercolor="#E6EDF7",
            lightcolor=self.palette["accent"],
            darkcolor=self.palette["accent"],
            background=self.palette["accent"],
            thickness=12,
        )
        style.configure("Modern.TCombobox", fieldbackground=self.palette["panel"], background=self.palette["panel"], foreground=self.palette["ink"], bordercolor=self.palette["line"], arrowsize=16, padding=6)
        style.configure("Modern.Treeview", background=self.palette["panel"], fieldbackground=self.palette["panel"], foreground=self.palette["ink"], rowheight=34, bordercolor=self.palette["line"], lightcolor=self.palette["line"], darkcolor=self.palette["line"])
        style.map("Modern.Treeview", background=[("selected", "#D7E8FF")], foreground=[("selected", self.palette["ink"])])
        style.configure("Modern.Treeview.Heading", background="#EDF4FF", foreground=self.palette["ink"], relief="flat", font=("Microsoft YaHei UI", 9, "bold"), padding=(8, 8))

    def build_ui(self):
        shell = ttk.Frame(self.root, style="App.TFrame", padding=20)
        shell.pack(fill=tk.BOTH, expand=True)

        hero = tk.Frame(shell, bg=self.palette["bg"])
        hero.pack(fill=tk.X, pady=(0, 14))

        title_wrap = tk.Frame(hero, bg=self.palette["bg"])
        title_wrap.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(title_wrap, text="参考文献真实性智能核验台", style="HeroTitle.TLabel").pack(anchor="w")
        ttk.Label(
            title_wrap,
            text="适配单文件启动器的现代化桌面界面。支持批量去重、Crossref/OpenAlex 联查、筛选排序与单文件发布流程。",
            style="HeroSub.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        top_actions = ttk.Frame(hero, style="App.TFrame")
        top_actions.pack(side=tk.RIGHT, anchor="n")
        ttk.Button(top_actions, text="导入 TXT", command=self.load_txt, style="Secondary.TButton").pack(side=tk.LEFT, padx=4)
        ttk.Button(top_actions, text="清空", command=self.clear_all, style="Secondary.TButton").pack(side=tk.LEFT, padx=4)
        ttk.Button(top_actions, text="开始核验", command=self.start_check, style="Primary.TButton").pack(side=tk.LEFT, padx=4)
        ttk.Button(top_actions, text="停止任务", command=self.cancel_check, style="Danger.TButton").pack(side=tk.LEFT, padx=4)

        credit = ttk.Frame(shell, style="SoftCard.TFrame", padding=(16, 12))
        credit.pack(fill=tk.X, pady=(0, 14))
        ttk.Label(credit, textvariable=self.author_var, style="Author.TLabel").pack(side=tk.LEFT)
        ttk.Label(
            credit,
            text="单文件版首次运行会自动解压到本地缓存目录，再启动主程序。",
            style="Meta.TLabel",
        ).pack(side=tk.RIGHT)

        stats_row = ttk.Frame(shell, style="App.TFrame")
        stats_row.pack(fill=tk.X, pady=(0, 14))
        self.create_stat_card(stats_row, "HIGH", "高可信匹配", self.stat_vars["HIGH"], self.palette["success_soft"], self.palette["success"]).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.create_stat_card(stats_row, "MEDIUM", "建议复核", self.stat_vars["MEDIUM"], self.palette["accent_soft"], self.palette["accent"]).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.create_stat_card(stats_row, "LOW", "低置信度", self.stat_vars["LOW"], self.palette["warn_soft"], self.palette["warn"]).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.create_stat_card(stats_row, "NOT_FOUND", "未找到", self.stat_vars["NOT_FOUND"], self.palette["danger_soft"], self.palette["danger"]).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.create_stat_card(stats_row, "META", "批量状态", self.stat_vars["META"], "#EEF4F8", self.palette["ink"]).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

        body = ttk.Panedwindow(shell, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        left_panel = ttk.Frame(body, style="Card.TFrame", padding=16)
        right_panel = ttk.Frame(body, style="Card.TFrame", padding=16)
        body.add(left_panel, weight=3)
        body.add(right_panel, weight=5)

        ttk.Label(left_panel, text="输入参考文献", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            left_panel,
            text="每行一条最佳；如果是连续段落，只要保留 [1] [2] [3] 这类编号，工具也会自动拆分。",
            style="Meta.TLabel",
        ).pack(anchor="w", pady=(4, 10))

        self.text = tk.Text(
            left_panel,
            height=20,
            wrap=tk.WORD,
            bg="#FBFCFE",
            fg=self.palette["ink"],
            insertbackground=self.palette["accent"],
            relief="flat",
            padx=14,
            pady=14,
            bd=0,
            highlightthickness=1,
            highlightbackground=self.palette["line"],
            highlightcolor=self.palette["accent"],
            font=("Consolas", 10),
        )
        self.text.pack(fill=tk.BOTH, expand=True)
        example = (
            "[1] Huo K, Li X, Hu W, Song X, Zhang D, Zhang X, et al. "
            "RFRP-3, the mammalian ortholog of GnIH, is a novel modulator involved in "
            "food intake and glucose homeostasis[J]. Frontiers in Endocrinology, 2020, 11:194.\n"
            "[2] Huo K, Li X, Hu W, Song X, Zhang D, Zhang X, et al. "
            "RFRP-3, the mammalian ortholog of GnIH, is a novel modulator involved in "
            "food intake and glucose homeostasis[J]. Frontiers in Endocrinology, 2020, 11:194."
        )
        self.text.insert("1.0", example)

        helper = ttk.Frame(left_panel, style="Card.TFrame")
        helper.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(helper, text="导出 CSV", command=self.export_csv, style="Secondary.TButton").pack(side=tk.LEFT)
        ttk.Button(helper, text="导出 Excel", command=self.export_xlsx, style="Secondary.TButton").pack(side=tk.LEFT, padx=8)
        ttk.Label(
            helper,
            text="提示：结果表格双击可直接打开匹配链接或谷歌学术。",
            style="Meta.TLabel",
        ).pack(side=tk.RIGHT)

        topbar = ttk.Frame(right_panel, style="Card.TFrame")
        topbar.pack(fill=tk.X)
        ttk.Label(topbar, text="核验结果中心", style="CardTitle.TLabel").pack(side=tk.LEFT)
        ttk.Label(topbar, textvariable=self.status_var, style="Meta.TLabel").pack(side=tk.RIGHT)

        prog = ttk.Frame(right_panel, style="Card.TFrame")
        prog.pack(fill=tk.X, pady=(10, 12))
        self.progress = ttk.Progressbar(prog, mode="determinate", style="Modern.Horizontal.TProgressbar")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(prog, text="进度", style="Meta.TLabel").pack(side=tk.RIGHT, padx=(12, 0))

        control = ttk.Frame(right_panel, style="Card.TFrame")
        control.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(control, text="筛选", style="Meta.TLabel").pack(side=tk.LEFT)
        filter_box = ttk.Combobox(control, textvariable=self.filter_var, values=FILTER_OPTIONS, width=14, state="readonly", style="Modern.TCombobox")
        filter_box.pack(side=tk.LEFT, padx=(8, 16))
        filter_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh_tree())
        ttk.Label(control, text="排序", style="Meta.TLabel").pack(side=tk.LEFT)
        sort_box = ttk.Combobox(control, textvariable=self.sort_var, values=SORT_OPTIONS, width=16, state="readonly", style="Modern.TCombobox")
        sort_box.pack(side=tk.LEFT, padx=(8, 16))
        sort_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh_tree())
        ttk.Button(control, text="导出当前筛选", command=self.export_filtered_dialog, style="Secondary.TButton").pack(side=tk.RIGHT)

        summary = ttk.Frame(right_panel, style="SoftCard.TFrame", padding=(14, 12))
        summary.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(summary, textvariable=self.summary_var, style="Meta.TLabel").pack(side=tk.LEFT)

        self.tree = ttk.Treeview(right_panel, columns=TREE_COLUMNS, show="headings", style="Modern.Treeview")
        for col in TREE_COLUMNS:
            self.tree.heading(col, text=col)
            if col == "匹配标题":
                self.tree.column(col, width=420)
            elif col == "建议":
                self.tree.column(col, width=420)
            elif col == "DOI":
                self.tree.column(col, width=180)
            else:
                self.tree.column(col, width=100)
        self.tree.tag_configure("HIGH", background="#ECF9F1")
        self.tree.tag_configure("MEDIUM", background="#EEF5FF")
        self.tree.tag_configure("LOW", background="#FFF6E5")
        self.tree.tag_configure("NOT_FOUND", background="#FFF0F0")
        self.tree.tag_configure("DUPLICATE", background="#F1F4FA")
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", self.open_selected_link)

        bottom = ttk.Frame(shell, style="App.TFrame", padding=(4, 12, 4, 0))
        bottom.pack(fill=tk.X)
        ttk.Label(
            bottom,
            text="说明：HIGH 基本可用；MEDIUM 建议人工复核；LOW/NOT_FOUND 不建议直接引用。单文件版由启动器负责解压与拉起主程序。",
            style="Muted.TLabel",
        ).pack(side=tk.LEFT)
        ttk.Label(bottom, text="原作者：李晨宇  |  优化：刘梓峰", style="Muted.TLabel").pack(side=tk.RIGHT)

    def create_stat_card(self, parent, title, subtitle, value_var, bg_color, value_color):
        card = tk.Frame(parent, bg=bg_color, bd=0, highlightthickness=0, padx=16, pady=14)
        tk.Label(card, text=title, bg=bg_color, fg=self.palette["muted"], font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w")
        tk.Label(card, textvariable=value_var, bg=bg_color, fg=value_color, font=("Segoe UI Semibold", 21, "bold")).pack(anchor="w", pady=(6, 2))
        tk.Label(card, text=subtitle, bg=bg_color, fg=self.palette["muted"], font=("Microsoft YaHei UI", 9)).pack(anchor="w")
        return card

    def load_txt(self):
        path = filedialog.askopenfilename(
            title="选择参考文献 txt 文件",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        content = read_text_file(path)
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", content)
        self.status_var.set("已导入文件")

    def clear_all(self):
        if self.running:
            messagebox.showinfo("正在运行", "请先停止当前任务，再执行清空。")
            return
        self.text.delete("1.0", tk.END)
        self.rows = []
        self.processed_cache = {}
        self.stats = {"duplicates_reused": 0, "network_warnings": 0, "total_input": 0}
        self.clear_tree()
        self.progress["value"] = 0
        self.progress["maximum"] = 0
        self.summary_var.set("结果统计：尚未开始")
        self.status_var.set("已清空")

    def clear_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def parse_refs(self):
        content = self.text.get("1.0", tk.END).strip()
        if not content:
            return []
        if re.search(r"\[\d+\]", content):
            refs = re.split(r"(?=\[\d+\]\s*)", content)
            lines = [item.strip() for item in refs if item.strip()]
            if len(lines) > 1:
                return lines
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        merged = []
        for line in lines:
            if merged and not re.match(r"^\[\d+\]", line):
                merged[-1] += " " + line
            else:
                merged.append(line)
        return merged

    def start_check(self):
        if self.running:
            messagebox.showinfo("正在运行", "当前核验尚未结束，请稍候。")
            return
        refs = self.parse_refs()
        if not refs:
            messagebox.showwarning("没有参考文献", "请先粘贴或导入参考文献。")
            return
        self.rows = []
        self.processed_cache = {}
        self.stats = {"duplicates_reused": 0, "network_warnings": 0, "total_input": len(refs)}
        self.cancel_requested = False
        self.clear_tree()
        self.progress["maximum"] = len(refs)
        self.progress["value"] = 0
        self.summary_var.set("结果统计：处理中")
        self.running = True
        self.status_var.set("准备开始")
        threading.Thread(target=self.worker, args=(refs,), daemon=True).start()

    def cancel_check(self):
        if self.running:
            self.cancel_requested = True
            self.status_var.set("正在停止...")

    def worker(self, refs):
        try:
            for index, ref in enumerate(refs, start=1):
                if self.cancel_requested:
                    self.root.after(0, self.status_var.set, "任务已停止")
                    break
                parsed_ref = parse_reference_context(ref)
                cache_key = ref_cache_key(ref, parsed_ref)
                self.root.after(0, self.status_var.set, f"正在核验 {index}/{len(refs)}")
                if cache_key in self.processed_cache:
                    row = clone_result_row(self.processed_cache[cache_key], ref, parsed_ref["ref_no"])
                    self.stats["duplicates_reused"] += 1
                else:
                    row = check_one_reference(ref)
                    self.processed_cache[cache_key] = copy.deepcopy(row)
                if row.get("_network_error"):
                    self.stats["network_warnings"] += 1
                self.rows.append(row)
                self.root.after(0, self.progress.configure, {"value": index})
                self.root.after(0, self.update_summary)
                self.root.after(0, self.refresh_tree)
                time.sleep(REQUEST_PAUSE)

            if not self.cancel_requested:
                status_text = f"完成：共核验 {len(self.rows)} 条，复用重复结果 {self.stats['duplicates_reused']} 条"
                self.root.after(0, self.status_var.set, status_text)
                self.root.after(0, self.finish_notice)
        except Exception:
            log_error(traceback.format_exc())
            self.root.after(0, messagebox.showerror, "程序错误", "程序运行出错，已写入 debug_log.txt。")
        finally:
            self.running = False
            self.cancel_requested = False
            self.root.after(0, self.update_summary)
            self.root.after(0, self.refresh_tree)

    def finish_notice(self):
        message = (
            f"核验完成。\n"
            f"总条目：{len(self.rows)}\n"
            f"重复复用：{self.stats['duplicates_reused']}\n"
            f"网络提示：{self.stats['network_warnings']}\n\n"
            f"可使用上方筛选和排序后再导出。"
        )
        messagebox.showinfo("完成", message)

    def get_filtered_rows(self):
        rows = list(self.rows)
        current_filter = self.filter_var.get()
        if current_filter == "全部":
            filtered = rows
        elif current_filter == "重复条目":
            filtered = [row for row in rows if row.get("_is_duplicate")]
        elif current_filter == "疑似网络失败":
            filtered = [row for row in rows if row.get("_network_error")]
        else:
            filtered = [row for row in rows if row.get("状态") == current_filter]
        return self.sort_rows(filtered)

    def sort_rows(self, rows):
        mode = self.sort_var.get()
        if mode == "相似度降序":
            return sorted(rows, key=lambda row: row.get("相似度", 0), reverse=True)
        if mode == "相似度升序":
            return sorted(rows, key=lambda row: row.get("相似度", 0))
        if mode == "编号升序":
            return sorted(rows, key=self.ref_no_sort_key)
        if mode == "编号降序":
            return sorted(rows, key=self.ref_no_sort_key, reverse=True)
        return sorted(rows, key=self.combined_sort_key)

    def ref_no_sort_key(self, row):
        ref_no = row.get("编号", "")
        return (0, int(ref_no)) if str(ref_no).isdigit() else (1, str(ref_no))

    def combined_sort_key(self, row):
        return (
            STATUS_PRIORITY.get(row.get("状态", "NOT_FOUND"), 99),
            -float(row.get("相似度", 0) or 0),
            self.ref_no_sort_key(row),
        )

    def refresh_tree(self):
        self.clear_tree()
        for row in self.get_filtered_rows():
            values = [row.get(col, "") for col in TREE_COLUMNS]
            tags = []
            if row.get("_is_duplicate"):
                tags.append("DUPLICATE")
            tags.append(row.get("状态", "NOT_FOUND"))
            self.tree.insert("", tk.END, values=values, tags=tuple(tags))

    def update_summary(self):
        counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "NOT_FOUND": 0}
        for row in self.rows:
            status = row.get("状态", "")
            if status in counts:
                counts[status] += 1
        visible = len(self.get_filtered_rows()) if self.rows else 0
        self.stat_vars["HIGH"].set(str(counts["HIGH"]))
        self.stat_vars["MEDIUM"].set(str(counts["MEDIUM"]))
        self.stat_vars["LOW"].set(str(counts["LOW"]))
        self.stat_vars["NOT_FOUND"].set(str(counts["NOT_FOUND"]))
        self.stat_vars["META"].set("重复 {dupes} | 网络 {net}".format(
            dupes=self.stats["duplicates_reused"],
            net=self.stats["network_warnings"],
        ))
        self.summary_var.set(
            "结果统计：HIGH {high} | MEDIUM {medium} | LOW {low} | NOT_FOUND {not_found} | 重复复用 {dupes} | 网络提示 {net} | 当前显示 {visible} | 总计 {total}".format(
                high=counts["HIGH"],
                medium=counts["MEDIUM"],
                low=counts["LOW"],
                not_found=counts["NOT_FOUND"],
                dupes=self.stats["duplicates_reused"],
                net=self.stats["network_warnings"],
                visible=visible,
                total=len(self.rows),
            )
        )

    def get_selected_row(self):
        selection = self.tree.selection()
        if not selection:
            return None
        values = self.tree.item(selection[0], "values")
        if not values:
            return None
        ref_no = values[0]
        title = values[4]
        for row in self.get_filtered_rows():
            if row.get("编号", "") == ref_no and row.get("匹配标题", "") == title:
                return row
        return None

    def open_selected_link(self, _event=None):
        row = self.get_selected_row()
        if not row:
            return
        url = row.get("链接") or row.get("谷歌学术搜索")
        if not url:
            messagebox.showinfo("无可打开链接", "该条结果没有可打开的链接。")
            return
        webbrowser.open(url)

    def export_csv(self):
        self.export_rows("csv", self.rows, "保存全部结果 CSV")

    def export_xlsx(self):
        self.export_rows("xlsx", self.rows, "保存全部结果 Excel")

    def export_filtered_dialog(self):
        rows = self.get_filtered_rows()
        if not rows:
            messagebox.showwarning("没有可导出的结果", "当前筛选条件下没有可导出的结果。")
            return
        answer = messagebox.askyesnocancel("按当前筛选导出", "选择“是”导出 CSV，选择“否”导出 Excel。")
        if answer is None:
            return
        self.export_rows("csv" if answer else "xlsx", rows, "保存当前筛选结果")

    def export_rows(self, kind, rows, title):
        if not rows:
            messagebox.showwarning("没有结果", "请先完成核验。")
            return
        if kind == "csv":
            path = filedialog.asksaveasfilename(
                title=title,
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")],
            )
        else:
            path = filedialog.asksaveasfilename(
                title=title,
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx")],
            )
        if not path:
            return
        if kind == "csv":
            write_csv(path, rows)
        else:
            write_minimal_xlsx(path, rows)
        messagebox.showinfo("已导出", f"共导出 {len(rows)} 条结果到：\n{path}")


def main():
    try:
        root = tk.Tk()
        ReferenceCheckerGUI(root)
        root.mainloop()
    except Exception:
        log_error(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
