#!/usr/bin/env python3
"""UA file-analyzer stage: deterministic per-batch graph generator for the GWC project.

Reads  batches.json  from the project's .ua/intermediate directory, inspects each
file on disk (first ~120 lines + tail), and emits one batch-<batchIndex>.json
graph output containing nodes and edges. Files >150KB are split into parts.
"""
import json
import os
import re
import sys

PROJECT_ROOT = "/Users/mac/prj/DW-SuperApps/projects/gwc"
OUT_DIR = os.path.join(PROJECT_ROOT, ".ua", "intermediate")
BATCHES_PATH = os.path.join(OUT_DIR, "batches.json")
MAX_BYTES = 150 * 1024
HEAD_LINES = 120
TAIL_LINES = 30

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def head_and_tail(path):
    text = read_text(path)
    if text is None:
        return "", "", []
    lines = text.splitlines()
    head = "\n".join(lines[:HEAD_LINES])
    tail = "\n".join(lines[-TAIL_LINES:]) if len(lines) > HEAD_LINES else ""
    return head, tail, lines


# --- title / name extraction -------------------------------------------------

def yaml_title(text):
    m = re.search(r"^title:\s*(.+)$", text, re.M)
    if m:
        t = m.group(1).strip().strip("'\"")
        if t:
            return t[:120]
    return ""


def md_title(text):
    m = re.search(r"^#\s+(.+)$", text, re.M)
    if m:
        return m.group(1).strip()[:120]
    return ""


def json_title(text):
    try:
        obj = json.loads(text)
    except Exception:
        # JSONL: first line
        for line in text.splitlines():
            try:
                obj = json.loads(line)
                break
            except Exception:
                continue
        else:
            return ""
    def find_first(obj, keys):
        if isinstance(obj, dict):
            for k in keys:
                v = obj.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()[:120]
            for v in obj.values():
                r = find_first(v, keys)
                if r:
                    return r
        elif isinstance(obj, list):
            for v in obj[:20]:
                r = find_first(v, keys)
                if r:
                    return r
        return ""
    return find_first(obj, ["title", "name", "id", "task_id", "$id"])


def base_name(path):
    return os.path.basename(path)


def stem_name(path):
    return os.path.splitext(os.path.basename(path))[0]


# --- symbol extraction --------------------------------------------------------

PY_CLASS_RE = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
PY_FUNC_RE = re.compile(r"^\s*def\s+([a-zA-Z_][A-Za-z0-9_]*)\s*\(", re.M)
PY_TESTCLASS_RE = re.compile(r"^\s*class\s+(Test[A-Za-z0-9_]*)\s*(\(|:)", re.M)
JS_FUNC_RE = re.compile(
    r"(?:function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(|"
    r"(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>)",
    re.M,
)
JS_CLASS_RE = re.compile(r"^\s*class\s+([A-Za-z_$][A-Za-z0-9_$]*)", re.M)


def extract_symbols(language, lines):
    """Return (functions, classes) lists of names for significant symbols."""
    text = "\n".join(lines)
    funcs, classes = [], []
    if language == "python":
        classes = PY_CLASS_RE.findall(text)
        funcs = [f for f in PY_FUNC_RE.findall(text)]
        if len(classes) > 12:
            keep = [c for c in classes if c.startswith("Test") or c.isupper() or c[0].isupper()]
            funcs = []
            classes = (keep + [c for c in classes if c not in keep])[:12]
        if len(funcs) > 15:
            # prefer public non-dunder
            pub = [f for f in funcs if not f.startswith("_")]
            priv = [f for f in funcs if f.startswith("_") and not f.startswith("__")]
            dunder = [f for f in funcs if f.startswith("__")]
            funcs = (pub + priv)[:15] + ([] if len(pub)+len(priv) <= 15 else []) + \
                    ([dunder[0]] if dunder and len(pub)+len(priv) < 15 else [])
            funcs = funcs[:15]
    elif language == "javascript":
        classes = JS_CLASS_RE.findall(text)
        funcs = [a or b for a, b in JS_FUNC_RE.findall(text)]
        funcs, classes = funcs[:12], classes[:8]
    return funcs, classes


# --- complexity heuristic ------------------------------------------------------

def complexity_for(category, n_lines, n_symbols, language=""):
    if category == "code":
        if n_lines >= 300 or n_symbols >= 12:
            return "complex"
        if n_lines >= 80 or n_symbols >= 4:
            return "moderate"
        return "simple"
    if n_lines >= 400:
        return "complex"
    if n_lines >= 100:
        return "moderate"
    return "simple"


# --- summaries & tags ----------------------------------------------------------

def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def summarize(path, rel, language, category, head, n_lines, exports, title):
    """Return (summary, tags, name)."""
    fname = base_name(rel)
    tags = set()

    # ---- name
    name = stem_name(rel)

    # ---- path-driven tags
    top = rel.split("/")[0]
    top_tag = top.lstrip(".").replace("_", "-") or "root"
    if top_tag in ("github",):
        top_tag = "ci"
    tags.add(top_tag)
    for kw, tag in [
        ("test", "tests"), ("schema", "schema"), ("workflow", "ci"),
        ("runbook", "runbook"), ("contract", "contract"), ("gate", "gates"),
        ("approval", "approvals"), ("validator", "validation"),
        ("validate", "validation"), ("registry", "registry"),
        ("runtime", "runtime"), ("agent", "agents"), ("instruction", "instructions"),
        ("release", "release"), ("changelog", "changelog"), ("config", "config"),
        ("intake", "intake"), ("envelope", "envelope"), ("checkpoint", "checkpoint"),
        ("audit", "audit"), ("digest", "digest"), ("capture", "capture"),
        ("adapter", "adapter"), ("viewer", "viewer"), ("catalog", "catalog"),
        ("node", "nodes"), ("task", "tasks"), ("scrum", "scrum"), ("g0", "g0"),
        ("g1", "g1"), ("g2", "g2"), ("g3", "g3"), ("g4", "g4"), ("g5", "g5"), ("g6", "g6"),
    ]:
        if kw in rel.lower():
            tags.add(tag)
    if category == "docs":
        tags.add("documentation")

    # ---- content sniffing
    low = head.lower()
    content_tags = {
        "gate": "gates", "approval": "approvals", "validator": "validation",
        "yaml": "yaml", "json schema": "schema", "draft": "draft-schema",
        "required": "spec", "enum": "enum",
    }
    if '"$schema"' in head or "'$schema'" in head or low.lstrip().startswith("{"):
        pass
    if "json schema" in low or '"$id"' in head:
        tags.add("schema")

    # ---- type-specific summaries
    if rel.startswith(".github/workflows"):
        summary = (
            f"GitHub Actions CI workflow ({fname}) defining automated pipeline steps "
            f"for the GWC repository across {n_lines} lines of YAML."
        )
        steps = re.findall(r"name:\s*(.+)", head)
        step_names = [clean(s) for s in steps if s and len(clean(s)) < 60][:3]
        if step_names:
            summary += " Key jobs/steps include: " + ", ".join(step_names) + "."
        triggers = re.findall(r'on:\s*\n?\s*([a-z_]+):', head)
        if triggers:
            summary += f" Triggered on {', '.join(dict.fromkeys(triggers))} events."
        tags.update({"ci", "github-actions"})
        return summary, sorted(tags)[:6], fname

    if language == "markdown":
        title_name = title or md_title(head) or stem_name(rel).replace("-", " ").replace("_", " ")
        first_para = ""
        for block in head.split("\n\n"):
            b = clean(block)
            if len(b) > 80 and not b.startswith("#") and not b.startswith("|"):
                first_para = b
                break
        if len(first_para) > 320:
            cut = first_para[:300]
            first_para = cut[:cut.rfind(" ")] if " " in cut else cut
        summary = f'Markdown document "{title_name}" '
        kind = (
            "specification" if any(k in rel.lower() for k in ("spec", "requirements")) else
            "plan" if "plan" in rel.lower() else
            "report" if any(k in rel.lower() for k in ("report", "record", "summary")) else
            "runbook" if "runbook" in rel.lower() else
            "changelog entry" if "changelog" in rel.lower() else
            "guideline/contract" if any(k in rel.lower() for k in ("contract", "policy", "rules")) else
            "document"
        )
        summary += f"({kind}, {n_lines} lines)"
        if first_para:
            summary += f": {first_para}"
        else:
            summary += "."
        if "agents/" in rel:
            tags.add("agents"); tags.add("instructions")
        return summary, sorted(tags)[:6], title_name

    if language in ("yaml", "yml"):
        t = title or yaml_title(head)
        what = "YAML configuration"
        if "schema" in rel or '"oneOf"' in head or "required:" in head and "properties:" in head:
            what = "YAML schema/structure definition"
        low_path = rel.lower()
        if "/tasks/" in low_path or "scrum-" in low_path:
            what = "GWC task governance YAML"
        elif "envelope" in low_path:
            what = "execution/approval envelope definition"
        elif "config" in low_path or "defaults" in low_path:
            what = "configuration file"
        elif "capabilities" in low_path:
            what = "capability declaration"
        elif "registry" in low_path:
            what = "registry definition"
        elif "preflight" in low_path or "brainstorming" in low_path or "context-snapshot" in low_path:
            what = "G0/G1 gate-phase artifact"
        elif "delivery-record" in low_path:
            what = "delivery record artifact"
        elif "intake" in low_path:
            what = "intake artifact"
        summary = f"{what}"
        if t:
            summary += f' "{t}"'
        summary += f" ({fname}, {n_lines} lines)"
        keys = re.findall(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(?:$|\S)", head, re.M)
        keyset = [k for k in dict.fromkeys(keys)][:6]
        if keyset:
            summary += ". Top-level keys: " + ", ".join(keyset) + "."
        else:
            summary += "."
        tags.add("yaml")
        return summary, sorted(tags)[:6], (t or stem_name(rel))

    if language == "json":
        parsed_ok = True
        try:
            obj = json.loads(read_text(os.path.join(PROJECT_ROOT, rel)) or "")
        except Exception:
            parsed_ok = False
            obj = {}
        t = title or json_title(head) or stem_name(rel).replace("-", " ").replace("_", " ")
        what = "JSON data file"
        low_path = rel.lower()
        if "schema" in low_path or (isinstance(obj, dict) and (obj.get("$schema") or obj.get("type") == "object" and "properties" in obj)):
            what = "JSON Schema definition"
            tags.add("schema")
        elif "/runs/" in low_path or "task-me" in low_path:
            what = "Task Me run artifact"
        elif "package-lock" in low_path or "node_modules" in low_path:
            what = "npm lock/data file"
        elif "registry" in low_path:
            what = "registry data"
        elif "manifest" in low_path:
            what = "manifest"
        summary = f"{what}"
        if t:
            summary += f' "{t}"'
        summary += f" ({fname}, {n_lines} lines)"
        if isinstance(obj, dict):
            ks = [k for k in list(obj.keys())[:6]]
            summary += " Top-level keys: " + ", ".join(str(k) for k in ks) + "."
        else:
            summary += "."
        tags.add("json")
        return summary, sorted(tags)[:6], str(t)

    if language == "python":
        modname = stem_name(rel)
        is_test = rel.startswith("tests/") or modname.startswith("test_")
        funcs, classes = extract_symbols("python", head.split("\n") + [])
        doc_m = re.search(r'^"""([\s\S]{10,400}?)"""', head, re.M)
        docline = clean(doc_m.group(1)) if doc_m else ""
        if is_test:
            summary = f"Python test module ({fname}, {n_lines} lines)"
            scope = modname.replace("test_", "").replace("_", " ")
            summary += f" covering {scope}"
            if docline:
                summary += f': {docline[:200]}'
            summary += "."
            tags.add("tests")
        else:
            summary = f"Python module ({fname}, {n_lines} lines)"
            if docline:
                summary += f": {docline[:280]}"
            else:
                summary += f" providing {modname.replace('_', ' ')} functionality."
            tags.add("python")
        if exports:
            summary += " Defines: " + ", ".join(exports[:5]) + "."
        return summary, sorted(tags)[:6], modname

    if language == "javascript":
        modname = stem_name(rel)
        summary = f"JavaScript module ({fname}, {n_lines} lines) implementing {modname.replace('-', ' ')}."
        tags.add("javascript")
        return summary, sorted(tags)[:6], modname

    if language == "html":
        return (f"HTML page ({fname}, {n_lines} lines) providing a rendered web view.",
                sorted(tags | {"html"})[:6], stem_name(rel))
    if language == "csv":
        return (f"CSV data table ({fname}, {n_lines} rows/lines).",
                sorted(tags | {"data"})[:6], stem_name(rel))
    if language == "mmd":
        return (f"Mermaid diagram source ({fname}) describing architecture or flow visually.",
                sorted(tags | {"diagram"})[:6], stem_name(rel))
    if language == "txt":
        return (f"Plain-text file ({fname}, {n_lines} lines).", sorted(tags)[:6], stem_name(rel))

    # unknown
    return (f"File ({fname}, {n_lines} lines) of undetected type.", sorted(tags)[:6], stem_name(rel))


# --- node id helpers ------------------------------------------------------------

def file_node_id(rel):
    return f"file:{rel}"


def node_type(rel, language, category):
    if rel.startswith(".github/workflows"):
        return "pipeline"
    if language == "markdown":
        return "document"
    if language in ("yaml", "json"):
        return "config"
    if category == "code":
        if "/tools/" in rel or rel.startswith("tools/"):
            return "service" if "runtime" in rel else "module"
        if rel.startswith("core/"):
            return "module"
        return "module"
    if category == "data":
        return "resource"
    return "resource"


# ---------------------------------------------------------------------------
# main generation
# ---------------------------------------------------------------------------

def gen_batch(batch, exports_by_path):
    batch_files = []
    nodes = []
    edges = []

    for finfo in batch["files"]:
        rel = finfo["path"]
        language = finfo["language"]
        size_lines = finfo["sizeLines"]
        category = finfo["fileCategory"]
        abs_path = os.path.join(PROJECT_ROOT, rel)
        head, tail, all_lines = head_and_tail(abs_path)
        n_lines = max(size_lines, len(all_lines))

        exports = exports_by_path.get(rel) or []
        summary, tags, name = summarize(rel, rel, language, category, head, n_lines, exports, "")

        # guarantee 2-5 lowercase tags
        tags = list(dict.fromkeys([t.lower() for t in tags if t]))[:5]
        filler = ["gwc", language if language != "unknown" else "file", category]
        for ftag in filler:
            if len(tags) >= 2:
                break
            if ftag and ftag not in tags:
                tags.append(ftag)

        node_type_v = node_type(rel, language, category)
        nid = file_node_id(rel)
        cx = complexity_for(category, n_lines, 0, language)

        # function/class nodes for larger code files
        sym_nodes = []
        contains_edges = []
        if language == "python" and n_lines >= 80 and os.path.exists(abs_path):
            fulltext = read_text(abs_path) or ""
            funcs, classes = extract_symbols("python", fulltext.split("\n"))
            exports_set = set(exports)
            # prioritize exported symbols
            def pri(f):
                return 0 if f in exports_set else (1 if not f.startswith("_") else 2)
            func_sorted = sorted(set(funcs), key=pri)[:10]
            class_sorted = sorted(set(classes), key=pri)[:8]
            for cname in class_sorted:
                cid = f"class:{rel}:{cname}"
                sym_nodes.append({
                    "id": cid, "type": "class", "name": cname, "filePath": rel,
                    "summary": f"Class {cname} defined in {rel}.",
                    "tags": ["python", "class"], "complexity": "simple",
                })
                contains_edges.append({"source": nid, "target": cid, "type": "contains", "weight": 0.9})
            for fname_ in func_sorted:
                fid = f"function:{rel}:{fname_}"
                sym_nodes.append({
                    "id": fid, "type": "function", "name": fname_, "filePath": rel,
                    "summary": f"Function {fname_} defined in {rel}.",
                    "tags": ["python", "function"], "complexity": "simple",
                })
                contains_edges.append({"source": nid, "target": fid, "type": "contains", "weight": 0.9})
            if len(func_sorted) + len(class_sorted) >= 8 or n_lines >= 250:
                cx = "complex" if (len(func_sorted) + len(class_sorted) >= 10 or n_lines >= 300) else cx

        nodes.append({
            "id": nid, "type": node_type_v, "name": name, "filePath": rel,
            "summary": summary, "tags": tags[:5], "complexity": cx,
        })
        nodes.extend(sym_nodes)
        edges.extend(contains_edges)
        batch_files.append({
            "path": rel, "language": language, "sizeLines": size_lines,
            "fileCategory": category,
        })

    # imports edges from batchImportData (pre-resolved by upstream stage)
    for src, targets in batch.get("batchImportData", {}).items():
        if not targets:
            continue
        src_id = file_node_id(src)
        tgt_list = targets if isinstance(targets, list) else []
        for t in tgt_list:
            if isinstance(t, dict):
                tpath = t.get("path") or t.get("resolved") or t.get("target")
            else:
                tpath = t
            if not tpath:
                continue
            tid = file_node_id(tpath)
            known_ids = {n["id"] for n in nodes}
            if tid in known_ids or tpath in {bf["path"] for bf in batch_files}:
                edges.append({"source": src_id, "target": tid, "type": "imports", "weight": 0.9})

    # cross-batch neighbor edges from neighborMap
    for src, neighbors in batch.get("neighborMap", {}).items():
        src_id = file_node_id(src)
        if not isinstance(neighbors, list):
            continue
        own = {bf["path"] for bf in batch_files}
        for nb in neighbors:
            if isinstance(nb, dict):
                npath = nb.get("path") or nb.get("neighbor")
            else:
                npath = nb
            if not npath:
                continue
            tid = file_node_id(npath)
            edges.append({
                "source": src_id, "target": tid,
                "type": "related" if npath not in own else "related",
                "weight": 0.7,
            })

    # intra-batch heuristic relations (same-directory grouping)
    by_dir = {}
    for bf in batch_files:
        d = os.path.dirname(bf["path"])
        by_dir.setdefault(d, []).append(bf["path"])
    for d, paths in by_dir.items():
        if 1 < len(paths) <= 8:
            for i in range(len(paths) - 1):
                edges.append({
                    "source": file_node_id(paths[i]),
                    "target": file_node_id(paths[i + 1]),
                    "type": "related", "weight": 0.5,
                })

    # test -> code tested_by edges within batch
    test_paths = [bf["path"] for bf in batch_files if bf["language"] == "python" and
                  (bf["path"].startswith("tests/") or os.path.basename(bf["path"]).startswith("test_"))]
    if test_paths:
        known = {bf["path"] for bf in batch_files}
        for tp in test_paths:
            ttext = read_text(os.path.join(PROJECT_ROOT, tp)) or ""
            for other in known:
                if other == tp or other.endswith(".py") is False:
                    continue
                mod = os.path.splitext(os.path.basename(other))[0]
                if mod.startswith("test_"):
                    continue
                if mod in ttext:
                    edges.append({
                        "source": file_node_id(other),
                        "target": file_node_id(tp),
                        "type": "tested_by", "weight": 0.8,
                    })

    return batch_files, nodes, edges


def write_batch_outputs(batch_index, batch_files, nodes, edges):
    payload = json.dumps({"batchFiles": batch_files, "nodes": nodes, "edges": edges},
                         ensure_ascii=False, indent=1)
    encoded = payload.encode("utf-8")
    if len(encoded) <= MAX_BYTES:
        out = os.path.join(OUT_DIR, f"batch-{batch_index}.json")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(payload)
        return [out]
    # split into parts: nodes+files first, then edge chunks
    parts = []
    chunk_edges = []
    base = json.dumps({"batchFiles": batch_files, "nodes": nodes, "edges": []},
                      ensure_ascii=False, indent=1)
    budget = MAX_BYTES - len(base.encode("utf-8")) - 64
    cur, cur_size = [], 0
    for e in edges:
        esz = len(json.dumps(e, ensure_ascii=False).encode("utf-8")) + 1
        if cur_size + esz > budget and cur:
            chunk_edges.append(cur)
            cur, cur_size = [], 0
        cur.append(e)
        cur_size += esz
    if cur:
        chunk_edges.append(cur)
    for k, ce in enumerate(chunk_edges, start=1):
        out = os.path.join(OUT_DIR, f"batch-{batch_index}-part-{k}.json")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"batchFiles": batch_files, "nodes": nodes if k == 1 else [],
                                 "edges": ce}, ensure_ascii=False, indent=1))
        parts.append(out)
    return parts


def main():
    with open(BATCHES_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    exports_by_path = data.get("exportsByPath", {})
    batches = data["batches"]
    total_nodes = total_edges = 0
    written = []
    only = set(int(a) for a in sys.argv[1:]) if len(sys.argv) > 1 else None
    for batch in batches:
        bi = batch["batchIndex"]
        if only and bi not in only:
            continue
        bf, nodes, edges = gen_batch(batch, exports_by_path)
        paths = write_batch_outputs(bi, bf, nodes, edges)
        written.extend(paths)
        total_nodes += len(nodes)
        total_edges += len(edges)
        print(f"batch {bi}: {len(nodes)} nodes, {len(edges)} edges -> {os.path.basename(paths[0])}"
              + (f" (+{len(paths)-1} parts)" if len(paths) > 1 else ""))
    print(f"DONE batches={len(written)} total_nodes={total_nodes} total_edges={total_edges}")


if __name__ == "__main__":
    main()
