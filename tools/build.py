# -*- coding: utf-8 -*-
"""139-3 변형문제 열람 웹서비스 — 화면 프로토타입 생성기.

public_fields(question / model_answer / drawings / homage)와
README가 '선택 노출'로 표시한 title·type·difficulty_stars만 출력한다.
internal_fields는 이 스크립트가 읽지도 않는다.
"""
import base64
import hashlib
import html
import json
import os
import re
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source")   # 원본 데이터 패키지 해제 위치 (.gitignore 대상)
OUT = ROOT

CATEGORIES = {
    "139-3-A": "교량공학",
    "139-3-B": "콘크리트구조",
    "139-3-C": "건설관리",
    "139-3-D": "구조역학",
    "139-3-E": "구조역학",
    "139-3-F": "콘크리트구조",
}
CATEGORY_ORDER = ["구조역학", "콘크리트구조", "교량공학", "건설관리"]

PUBLIC_META = ("id", "title", "type", "difficulty_stars", "homage")
BANNED = ("origin", "learning_objective", "variation_design",
          "drawing_requirements", "self_review", "reference",
          "requirement_block")


# ---------- 마크다운-라이트 렌더러 (텍스트 내용은 변경하지 않음) ----------

def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t, flags=re.S)
    return t


def render_block(text, allow_tables=True):
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        raw = lines[i]
        s = raw.strip()

        if not s:
            i += 1
            continue

        # 표
        if allow_tables and s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            sep = 1 if len(rows) > 1 and all(set(c) <= set("-: ") and c for c in rows[1]) else None
            out.append('<div class="tablewrap"><table>')
            if sep:
                out.append("<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr></thead>")
                body = rows[2:]
            else:
                body = rows
            out.append("<tbody>")
            for r in body:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table></div>")
            continue

        # 순서 목록
        m = re.match(r"^(\d+)\.\s+(.*)$", s)
        if m:
            items = []
            while i < len(lines):
                mm = re.match(r"^(\d+)\.\s+(.*)$", lines[i].strip())
                if not mm:
                    break
                start = mm.group(1) if not items else None
                items.append(mm.group(2))
                i += 1
            out.append(f'<ol start="{m.group(1)}">' + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ol>")
            continue

        # 글머리 목록 (들여쓴 항목은 하위 목록으로)
        if s.startswith("- "):
            items = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                indent = len(lines[i]) - len(lines[i].lstrip())
                items.append((indent, lines[i].strip()[2:]))
                i += 1
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
                out.append(f"<li>{inline(txt)}</li>")
            if open_sub:
                out.append("</ul>")
            out.append("</ul>")
            continue

        out.append(f"<p>{inline(s)}</p>")
        i += 1
    return "\n".join(out)


# ---------- 도면 ----------

def verify(path, expect):
    """원본 파일을 그대로 배포한다. 해시만 검증하고 바이트는 건드리지 않는다."""
    b = open(os.path.join(SRC, path), "rb").read()
    got = hashlib.sha256(b).hexdigest()
    assert got == expect, f"hash mismatch: {path}"
    return path


def figure(d, idx):
    src = verify(d["svg"], d["svg_sha256"])
    return f"""<figure class="dwg">
  <img src="{src}" alt="{html.escape(d['drawing_type'])} {html.escape(d['drawing_id'])}"
       data-full="{src}" data-cap="{html.escape(d['drawing_id'])} · {html.escape(d['drawing_type'])}" loading="lazy">
  <figcaption><span class="mono">{html.escape(d['drawing_id'])}</span> {html.escape(d['drawing_type'])}<button class="zoom" type="button">확대</button></figcaption>
</figure>"""


# ---------- 문항 카드 ----------

def card(no, it, exam):
    q_dwgs = [d for d in it["drawings"] if d["usage"] == "문제"]
    a_dwgs = [d for d in it["drawings"] if d["usage"] == "답안"]
    ans = it.get("model_answer")
    ready = bool(ans)
    hom = it["homage"]["label"]
    cat = CATEGORIES[it["id"]]

    qfigs = "\n".join(figure(d, i) for i, d in enumerate(q_dwgs))

    if ready:
        panel_inner = f"""
      <div class="ans-head"><span class="eyebrow">모범답안</span></div>
      {render_block(ans)}
      {'<div class="dwgs">' + chr(10).join(figure(d, i) for i, d in enumerate(a_dwgs)) + '</div>' if a_dwgs else ''}
      <div class="ans-foot"><button class="btn ghost toggle" type="button" data-t="{it['id']}">해설 닫기</button></div>"""
        action = f'<button class="btn toggle" type="button" data-t="{it["id"]}" aria-expanded="false" aria-controls="ans-{it["id"]}">해설보기</button>'
    else:
        panel_inner = ""
        action = ('<span class="pending">해설 준비 중</span>'
                  '<button class="btn" type="button" disabled>해설보기</button>')

    return f"""
<article class="item" id="item-{it['id']}" data-cat="{html.escape(cat)}" data-ready="{'1' if ready else '0'}">
  <header class="item-head">
    <span class="no">문항 {no}</span>
    <span class="stamp" role="note" aria-label="오마주 출처 {html.escape(hom)}">
      <span class="stamp-k">오마주</span><span class="stamp-v">{html.escape(hom)}</span>
    </span>
  </header>
  <div class="head-main"><h2>{html.escape(it['title'])}</h2></div>

  <div class="qbody">{render_block(it['question'])}</div>
  {'<div class="dwgs">' + qfigs + '</div>' if qfigs else ''}

  <div class="titleblock">
    <span class="chip chip-cat">{html.escape(cat)}</span>
    <span class="chip chip-exam">제{exam}</span>
    <span class="chip">{html.escape(it['type'])}</span>
    <span class="chip">난이도 <span class="stars">{html.escape(it['difficulty_stars'])}</span></span>
    <span class="tb-action">{action}</span>
  </div>

  <div class="ans" id="ans-{it['id']}" hidden>
    <div class="ans-in">{panel_inner}</div>
  </div>
</article>"""


def main():
    data = json.load(open(os.path.join(SRC, "139-3-items.json")))
    items = data["items"]
    exam = f'{data["exam_round"]}회 {data["session"]}교시'
    cards = "\n".join(card(i + 1, it, exam) for i, it in enumerate(items))
    ready_n = sum(1 for it in items if it.get("model_answer"))

    admin_items = "\n".join(
        f'''      <div class="row"><div class="meta">
        <div class="rt">문항 {i} · {html.escape(it["title"])}</div>
        <div class="rs">{exam} · {html.escape(CATEGORIES[it["id"]])} · {html.escape(it["type"])} · 모범답안 {"있음" if it.get("model_answer") else "없음"}</div>
        <div class="acts"><button class="mini{" sec" if it.get("model_answer") else ""}" data-q="{it["id"]}" data-act="{"작성중" if it.get("model_answer") else "게시됨"}">{"작성중으로 내리기" if it.get("model_answer") else "게시"}</button></div>
      </div><span class="st" data-s="{"게시됨" if it.get("model_answer") else "작성중"}">{"게시됨" if it.get("model_answer") else "작성중"}</span></div>'''
        for i, it in enumerate(items, 1))

    counts = {}
    for it in items:
        counts[CATEGORIES[it["id"]]] = counts.get(CATEGORIES[it["id"]], 0) + 1
    catlist = "\n".join(
        f'''      <li><button type="button" data-cat-open="{c}">
        <span class="txt"><b>{c}</b></span>
        <span class="cat-count">{counts[c]}문항</span>
        <span class="arw" aria-hidden="true">›</span>
      </button></li>'''
        for c in CATEGORY_ORDER if counts.get(c))

    tpl = open(os.path.join(ROOT, "tools", "template.html"), encoding="utf-8").read()
    out = (tpl
           .replace("{{CARDS}}", cards)
           .replace("{{CATLIST}}", catlist)
           .replace("{{ADMINITEMS}}", admin_items)
           .replace("{{ROUND}}", str(data["exam_round"]))
           .replace("{{SESSION}}", str(data["session"]))
           .replace("{{COUNT}}", str(len(items)))
           .replace("{{READY}}", str(ready_n))
           .replace("{{PENDING}}", str(len(items) - ready_n))
           .replace("{{DRAWINGS}}", str(sum(len(it["drawings"]) for it in items)))
           .replace("{{DESC}}", str(sum(1 for it in items if it["type"] == "서술형")))
           .replace("{{CALC}}", str(sum(1 for it in items if it["type"] == "계산형"))))

    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "index.html")
    open(p, "w", encoding="utf-8").write(out)

    # 도면 원본 복사 (무변형)
    for sub in ("svg", "png"):
        dst = os.path.join(OUT, "drawings", sub)
        os.makedirs(dst, exist_ok=True)
        for it in items:
            for d in it["drawings"]:
                shutil.copyfile(os.path.join(SRC, d[sub]), os.path.join(dst, os.path.basename(d[sub])))

    # 공개 필드만 담은 데이터 파일 (internal_fields 제외)
    pub = {
        "exam_round": data["exam_round"],
        "session": data["session"],
        "item_count": len(items),
        "items": [{
            "id": it["id"],
            "title": it["title"],
            "type": it["type"],
            "difficulty_stars": it["difficulty_stars"],
            "homage": it["homage"],
            "question": it["question"],
            "model_answer": it.get("model_answer"),
            "drawings": [{k: d[k] for k in
                          ("drawing_id", "usage", "drawing_type", "svg", "png",
                           "status", "svg_sha256", "png_sha256")} for d in it["drawings"]],
        } for it in items],
    }
    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    with open(os.path.join(OUT, "data", "categories.json"), "w", encoding="utf-8") as f:
        json.dump({"note": "과목 분류는 원본 문항 데이터에 없는 별도 매핑이다. 검수 대상.",
                   "order": CATEGORY_ORDER,
                   "items": CATEGORIES}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "data", "139-3.public.json"), "w", encoding="utf-8") as f:
        json.dump(pub, f, ensure_ascii=False, indent=1)

    # 내부 필드 유출 검사
    src_txt = json.dumps(data, ensure_ascii=False)
    leaks = []
    for it in items:
        for f in it["internal_fields"]:
            v = it.get(f)
            if isinstance(v, str):
                for seg in [x.strip() for x in re.split(r"[\n|]", v) if len(x.strip()) > 12]:
                    if seg in out:
                        leaks.append((it["id"], f, seg[:40]))
        for d in it["drawings"]:
            if d["requirement_block"][:40] in out:
                leaks.append((it["id"], "requirement_block", d["drawing_id"]))
    print("bytes:", os.path.getsize(p))
    print("leaks:", leaks if leaks else "none")


if __name__ == "__main__":
    main()
