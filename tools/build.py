# -*- coding: utf-8 -*-
"""제140회 콘텐츠 패키지 → 열람 화면 생성기.

원본 마크다운과 도면은 읽기만 한다. 도면은 바이트 그대로 복사하고 해시를 검증한다.
"""
import glob
import hashlib
import html
import json
import os
import re
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source", "140")   # 원본 패키지 해제 위치 (.gitignore 대상)
OUT = ROOT

# 큐넷 대분류 → 서비스 과목 (요구사항 R-23 · 부록 A)
SUBJECT = {
    "1. 토목구조 일반 사항": "토목구조 일반",
    "2. 철근콘크리트": "콘크리트구조",
    "3. 프리스트레스트 콘크리트": "콘크리트구조",
    "4. 구조역학": "구조역학",
    "5. 강구조": "강구조",
    "6. 교량공학": "교량공학",
}
CATEGORY_ORDER = ["구조역학", "콘크리트구조", "강구조", "교량공학", "토목구조 일반"]


SUB = {"\u2080": "0", "\u2081": "1", "\u2082": "2", "\u2083": "3", "\u2084": "4",
       "\u2085": "5", "\u2086": "6", "\u2087": "7", "\u2088": "8", "\u2089": "9"}


def inline(t, subs=False):
    t = html.escape(t, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t, flags=re.S)
    if subs:
        # R-57 — 유니코드 첨자는 지정 서체에도 대체 서체에도 없어 세 번째 서체로 떨어진다.
        t = re.sub(r"[\u2080-\u2089]+",
                   lambda m: "<sub>" + "".join(SUB[c] for c in m.group()) + "</sub>", t)
        # R-57 — 지정 서체(한글·라틴)에 없는 글자만 대체 서체로 감싼다.
        #        span의 0.67em이 size-adjust 67%와 같은 결과를 낸다.
        # 문장부호(·, —, 〈〉, 【】)와 한자는 글자 높이가 한글과 같으므로 건드리지 않는다.
        # 지정 서체가 가진 화살표(←, →)는 제외한다. 감싸면 손글씨 글리프를 버리게 된다.
        t = re.sub(r"[\u00D7\u00F7\u0370-\u03FF\u2070-\u209F\u2160-\u217F"
                   r"\u2191\u2193-\u22FF\u2460-\u24FF]+",
                   lambda m: f'<span class="sym">{m.group()}</span>', t)
    return t


def render_block(text, subs=False):
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        raw = lines[i]
        s = raw.strip()

        if not s:
            i += 1
            continue

        # 표
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            sep = 1 if len(rows) > 1 and all(set(c) <= set("-: ") and c for c in rows[1]) else None
            out.append('<div class="tablewrap"><table>')
            if sep:
                out.append("<thead><tr>" + "".join(f"<th>{inline(c, subs)}</th>" for c in rows[0]) + "</tr></thead>")
                body = rows[2:]
            else:
                body = rows
            out.append("<tbody>")
            for r in body:
                out.append("<tr>" + "".join(f"<td>{inline(c, subs)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table></div>")
            continue

        # 순서 목록
        m = re.match(r"^(\d+)\.\s+(.*)$", s)
        if m:
            items = []
            while i < len(lines):
                mm = re.match(r"^(\d+)\.\s+(.*)$", lines[i].strip())
                if not mm:
                    # 빈 줄 뒤에 같은 목록이 이어지면 계속 묶는다
                    if not lines[i].strip():
                        j = i + 1
                        while j < len(lines) and not lines[j].strip():
                            j += 1
                        if j < len(lines) and re.match(r"^\d+\.\s+", lines[j].strip()):
                            i = j
                            continue
                    break
                items.append(mm.group(2))
                i += 1
            out.append(f'<ol start="{m.group(1)}">' + "".join(f"<li>{inline(x, subs)}</li>" for x in items) + "</ol>")
            continue

        # 글머리 목록 (들여쓴 항목은 하위 목록으로)
        if s.startswith("- "):
            items = []
            while i < len(lines):
                if lines[i].strip().startswith("- "):
                    indent = len(lines[i]) - len(lines[i].lstrip())
                    items.append((indent, lines[i].strip()[2:]))
                    i += 1
                    continue
                if not lines[i].strip():
                    j = i + 1
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines) and lines[j].strip().startswith("- "):
                        i = j
                        continue
                break
            base = min(d for d, _ in items)
            out.append("<ul>")
            open_sub = False
            for d, txt in items:
                if d > base and not open_sub:
                    out.append("<ul class='sub'>")
                    open_sub = True
                elif d == base and open_sub:
                    out.append("</ul>")
                    open_sub = False
                out.append(f"<li>{inline(txt, subs)}</li>")
            if open_sub:
                out.append("</ul>")
            out.append("</ul>")
            continue

        out.append(f"<p>{inline(s, subs)}</p>")
        i += 1
    return "\n".join(out)




# ---------- 패키지 읽기 ----------

def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def pull_images(body, base_dir):
    """본문에서 이미지와 바로 아래 이탤릭 캡션을 걷어낸다."""
    found = []

    def take(m):
        found.append((m.group(1), os.path.normpath(os.path.join(base_dir, m.group(2)))))
        return "\u0000IMG\u0000"

    body = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", take, body)
    body = re.sub(r"\u0000IMG\u0000\s*\n\s*\*[^*\n]+\*\s*\n", "\n", body)
    body = body.replace("\u0000IMG\u0000", "")
    return re.sub(r"\n{3,}", "\n\n", body).strip(), found


def load_items():
    items = []
    paths = sorted(p for d in ("140-1", "140-2", "140-3", "140-4")
                   for p in glob.glob(os.path.join(SRC, d, "*.md")))
    for path in paths:
        raw = open(path, encoding="utf-8").read()
        head_txt = raw.split("## 문제")[0]

        m = re.search(r"^# 제(\d+)회.+?·\s*(\d+)교시\s*(\d+)번\s*·\s*(\d+)점", raw, re.M)
        rnd, session, no, score = (int(m.group(k)) for k in (1, 2, 3, 4))
        title = re.search(r"^## (.+)$", raw, re.M).group(1).strip()
        meta = dict(re.findall(r"^\|\s*(문항 유형|과목|출처)\s*\|\s*(.+?)\s*\|$", head_txt, re.M))

        parts = re.split(r"^## (문제|모범답안)$", raw, flags=re.M)
        body = {parts[k]: parts[k + 1] for k in range(1, len(parts), 2)}
        base = os.path.dirname(path)
        question, q_imgs = pull_images(body["문제"], base)
        answer, a_imgs = pull_images(body["모범답안"], base)

        dwgs = []
        for usage, imgs in (("문제", q_imgs), ("답안", a_imgs)):
            for alt, svg in imgs:
                png = svg[:-4] + ".png"
                d = {"drawing_id": os.path.basename(svg)[:-4], "usage": usage,
                     "drawing_type": alt, "svg": svg, "svg_sha256": sha(svg),
                     "status": "approved"}
                if os.path.exists(png):
                    d["png"] = png
                    d["png_sha256"] = sha(png)
                dwgs.append(d)

        items.append({
            "id": f"{rnd}-{session}-{no:02d}", "exam_round": rnd, "session": session,
            "question_no": no, "title": title, "type": meta["문항 유형"], "score": score,
            "category": SUBJECT[meta["과목"].split("›")[0].strip()],
            "category_detail": meta["과목"], "source": meta["출처"],
            "question": question, "model_answer": answer, "drawings": dwgs,
        })
    return items


# ---------- 화면 생성 ----------

def figure(d):
    """SVG를 인라인으로 넣는다.

    <img>로 넣으면 SVG가 격리된 문서가 되어 페이지의 웹폰트를 쓰지 못한다.
    도면 19건이 손글씨체를 지정하고 있으므로 인라인으로 넣어야 지정대로 그려진다.
    원본 파일은 drawings/ 에 그대로 두고 해시로 검증한다. 여기서는 바이트를 옮겨 담기만 한다.
    """
    svg = open(d["svg"], encoding="utf-8").read()
    svg = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", svg)
    svg = re.sub(r"^\s*<!DOCTYPE[^>]*>\s*", "", svg)
    svg = re.sub(r"<metadata>.*?</metadata>", "", svg, flags=re.S)   # c2pa 매니페스트 제거
    svg = svg.replace("<svg ", '<svg role="img" ', 1)
    cap = html.escape(d["drawing_type"])
    return f'''<figure class="dwg">
  <div class="dwg-canvas" data-cap="{html.escape(d["drawing_id"])} · {cap}" aria-label="{cap}">{svg}</div>
  <figcaption><span class="mono">{html.escape(d["drawing_id"])}</span> {cap}<button class="zoom" type="button">확대</button></figcaption>
</figure>'''


def card(it):
    q = [d for d in it["drawings"] if d["usage"] == "문제"]
    a = [d for d in it["drawings"] if d["usage"] == "답안"]
    ready = bool(it["model_answer"])
    src_label = f"제{it['exam_round']}회 {it['session']}교시 {it['question_no']}번"

    if ready:
        action = (f'<button class="btn toggle" type="button" data-t="{it["id"]}" '
                  f'aria-expanded="false" aria-controls="ans-{it["id"]}">해설보기</button>')
        dwg_html = ""
        if a:
            dwg_html = '<div class="dwgs">' + "\n".join(figure(d) for d in a) + '</div>'
        panel = ('<div class="ans-head"><span class="eyebrow">모범답안</span></div>'
                 + render_block(it["model_answer"], subs=True) + dwg_html
                 + f'<div class="ans-foot"><button class="btn ghost toggle" type="button" data-t="{it["id"]}">해설 닫기</button></div>')
    else:
        action = '<span class="pending">해설 준비 중</span><button class="btn" type="button" disabled>해설보기</button>'
        panel = ""

    qdwg = '<div class="dwgs">' + "\n".join(figure(d) for d in q) + '</div>' if q else ""

    return f'''
<article class="item" id="item-{it["id"]}" data-cat="{html.escape(it["category"])}"
         data-session="{it["session"]}" data-ready="{"1" if ready else "0"}">
  <header class="item-head">
    <span class="no">문항 {it["question_no"]}</span>
    <span class="stamp" role="note" aria-label="출처 {src_label}">
      <span class="stamp-k">출처</span><span class="stamp-v">{src_label}</span>
    </span>
  </header>
  <div class="head-main"><h2>{html.escape(it["title"])}</h2></div>

  <div class="qbody">{render_block(it["question"])}</div>
  {qdwg}

  <div class="titleblock">
    <span class="chip chip-cat">{html.escape(it["category"])}</span>
    <span class="chip chip-exam">제{it["exam_round"]}회 {it["session"]}교시</span>
    <span class="chip">{html.escape(it["type"])}</span>
    <span class="chip">{it["score"]}점</span>
    <span class="tb-action"><button class="btn ghost report" type="button">신고</button>{action}</span>
  </div>

  <div class="ans" id="ans-{it["id"]}" hidden><div class="ans-in">{panel}</div></div>
</article>'''


def main():
    items = load_items()
    rnd = items[0]["exam_round"]
    sessions = sorted({it["session"] for it in items})

    # 도면 원본 복사 + 해시 재검증
    for sub in ("svg", "png"):
        dst_dir = os.path.join(OUT, "drawings", sub)
        os.makedirs(dst_dir, exist_ok=True)
        for f in glob.glob(os.path.join(dst_dir, "*")):
            os.remove(f)
    for it in items:
        for d in it["drawings"]:
            for key in ("svg", "png"):
                if key not in d:
                    continue
                dst = os.path.join(OUT, "drawings", key, os.path.basename(d[key]))
                shutil.copyfile(d[key], dst)
                assert sha(dst) == d[key + "_sha256"], f"해시 불일치: {dst}"

    counts = {}
    for it in items:
        counts[it["category"]] = counts.get(it["category"], 0) + 1
    catlist = "\n".join(
        f'''      <li><button type="button" data-cat-open="{c}">
        <span class="txt"><b>{c}</b></span>
        <span class="cat-count">{counts[c]}문항</span>
        <span class="arw" aria-hidden="true">›</span>
      </button></li>'''
        for c in CATEGORY_ORDER if counts.get(c))

    sess_opts = "\n".join(
        f'        <option value="{s}">{s}교시</option>' if s in sessions
        else f'        <option value="{s}" disabled>{s}교시 · 준비 중</option>'
        for s in (1, 2, 3, 4))

    admin_items = "\n".join(
        f'''      <div class="row"><div class="meta">
        <div class="rt">제{it["exam_round"]}회 {it["session"]}교시 {it["question_no"]}번 · {html.escape(it["title"])}</div>
        <div class="rs">{html.escape(it["category"])} · {html.escape(it["type"])} · {it["score"]}점 · 도면 {len(it["drawings"])}건</div>
        <div class="acts"><button class="mini sec" data-q="{it["id"]}" data-act="작성중">작성중으로 내리기</button></div>
      </div><span class="st" data-s="게시됨">게시됨</span></div>'''
        for it in items)

    tpl = open(os.path.join(ROOT, "tools", "template.html"), encoding="utf-8").read()
    out = (tpl
           .replace("{{CARDS}}", "\n".join(card(it) for it in items))
           .replace("{{CATLIST}}", catlist)
           .replace("{{SESSION_OPTIONS}}", sess_opts)
           .replace("{{ADMINITEMS}}", admin_items)
           .replace("{{ROUND}}", str(rnd))
           .replace("{{COUNT}}", str(len(items)))
           .replace("{{READY}}", str(sum(1 for it in items if it["model_answer"]))))
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(out)

    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    keys = ("id", "exam_round", "session", "question_no", "title", "type", "score",
            "category", "category_detail", "source", "question", "model_answer")
    pub = {"exam_round": rnd, "sessions": sessions, "item_count": len(items),
           "category_order": CATEGORY_ORDER,
           "items": [dict({k: it[k] for k in keys},
                          drawings=[dict(d, svg="drawings/svg/" + os.path.basename(d["svg"]),
                                         **({"png": "drawings/png/" + os.path.basename(d["png"])} if "png" in d else {}))
                                    for d in it["drawings"]])
                     for it in items]}
    with open(os.path.join(OUT, "data", str(rnd) + ".public.json"), "w", encoding="utf-8") as f:
        json.dump(pub, f, ensure_ascii=False, indent=1)

    print("문항 %d건 · 교시 %s · 도면 %d건" % (len(items), sessions, sum(len(i["drawings"]) for i in items)))
    print("과목별:", counts)
    print("bytes:", os.path.getsize(os.path.join(OUT, "index.html")))


if __name__ == "__main__":
    main()
