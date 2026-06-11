import json
import os
import threading
from datetime import datetime
from queue import Empty, Queue

import pandas as pd
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

import database as db
import scraper
import summarizer

_root = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__,
            template_folder=os.path.join(_root, "templates"))
db.init_db()
db.seed_known_regulations()  # 핵심 규제 항상 보장 (AI 파이프라인 우회)

_queues: dict[str, Queue] = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stats")
def api_stats():
    return jsonify(db.get_stats())


@app.route("/api/regulations")
def api_regulations():
    source = request.args.get("source", "전체")
    importance = request.args.get("importance", "전체")
    days = request.args.get("days", type=int, default=None)
    df = db.get_regulations(source, importance, days)
    return jsonify(df.where(pd.notna(df), None).to_dict("records"))


@app.route("/api/collect", methods=["POST"])
def api_collect():
    data = request.get_json(force=True) or {}
    source = data.get("source", "ALL")
    sid = data.get("sid", "default")
    q: Queue = Queue()
    _queues[sid] = q

    def worker():
        def cb(label, i, total):
            q.put({"type": "progress", "label": label, "step": i + 1, "total": total})
        try:
            items = scraper.run_all(cb) if source == "ALL" else scraper.run_by_source(source, cb)
            q.put({"type": "status", "message": f"AI 요약 중... ({len(items)}건)"})
            summarized = summarizer.batch_summarize(items)
            new_count = sum(1 for it in summarized if db.insert_regulation(it))
            q.put({"type": "done", "new": new_count, "total": len(summarized)})
        except Exception as exc:
            q.put({"type": "error", "message": str(exc)})

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"sid": sid})


@app.route("/api/collect/stream/<sid>")
def api_collect_stream(sid):
    def generate():
        q = _queues.get(sid)
        if not q:
            yield f'data: {json.dumps({"type":"error","message":"session not found"})}\n\n'
            return
        while True:
            try:
                msg = q.get(timeout=120)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg["type"] in ("done", "error"):
                    _queues.pop(sid, None)
                    break
            except Empty:
                yield 'data: {"type":"keepalive"}\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/mark_read/<int:reg_id>", methods=["POST"])
def api_mark_read(reg_id):
    db.mark_as_read(reg_id)
    return jsonify({"status": "ok"})


@app.route("/api/delete/<int:reg_id>", methods=["DELETE"])
def api_delete(reg_id):
    db.delete_regulation(reg_id)
    return jsonify({"status": "ok"})


@app.route("/api/export")
def api_export():
    source = request.args.get("source", "전체")
    importance = request.args.get("importance", "전체")
    days = request.args.get("days", type=int, default=None)
    df = db.get_regulations(source, importance, days)
    cols = {
        "source": "기관", "importance": "중요도", "title": "제목",
        "summary_kr": "한국어 요약", "keywords_matched": "감지 키워드",
        "published_date": "발행일", "effective_date": "시행 예정일", "url": "원문 링크",
    }
    export_df = df[[c for c in cols if c in df.columns]].rename(columns=cols)
    filename = f"regulations_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(
        export_df.to_csv(index=False, encoding="utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
