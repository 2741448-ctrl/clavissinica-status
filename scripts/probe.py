#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe.py · 从 GitHub Actions 的机器上探测 ClavisSinica 的公开端点。

设计上的几条硬规矩:

1. 【探针必须跑在被探对象之外】。这是这个状态页存在的全部意义 ——
   探针跑在那台服务器上的话, 机器一挂, 页面就永远停在最后一次
   "一切正常"。GitHub Actions 跑在 GitHub 的机器上, 和我们的服务器
   没有任何共同的故障域。

2. 【只探公开端点, 不泄露架构】。不探内网, 不显示 IP、端口、上游
   服务名。状态页是给外人看的, 它本身不该变成一份内部拓扑图。

3. 【读 body, 不只看状态码】。/v1/health 在上游挂掉时【仍然返回
   HTTP 200】, 只在 body 里写 status: "degraded"。只看状态码的监控
   会一路绿到底 —— 那正是这个状态页要解决的问题, 不能自己再犯一次。

4. 【不报告没测过的东西】。样本数一起写进 status.json 并显示在页面上。
   跑了两个小时就显示"100% 可用"是一句误导。
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "status.json")

TIMEOUT = 20
SAMPLE_HOURS = 24        # 明细保留多久
DAY_BUCKETS = 90         # 日聚合保留多少天
UA = "ClavisSinica-StatusProbe/1 (+https://github.com/)"


def _get(url):
    """返回 (http_code, body_text, 毫秒)。任何异常都算 0 码。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    t0 = datetime.now(timezone.utc)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read(65536).decode("utf-8", "replace")
            code = r.getcode()
    except urllib.error.HTTPError as e:
        # 4xx/5xx 也是"服务器在回话", 对某些检查来说就是 up
        body = ""
        try:
            body = e.read(65536).decode("utf-8", "replace")
        except Exception:
            pass
        code = e.code
    except Exception:
        code, body = 0, ""
    ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
    return code, body, ms


def probe():
    checks = {}

    # ── API 本身 ──
    code, body, ms = _get("https://clavissinica.org/api-health")
    api_up = code == 200
    engine_up = False
    db_up = False
    if api_up:
        try:
            d = json.loads(body)
            # 这里【必须】读 body: 上游挂掉时这个端点仍然返回 200,
            # 只在 status 字段里写 degraded。
            engine_up = bool((d.get("checks") or {}).get("upstream"))
            db_up = bool((d.get("checks") or {}).get("database"))
        except Exception:
            engine_up = db_up = False
    checks["api"] = {"up": api_up, "ms": ms}
    checks["engine"] = {"up": api_up and engine_up, "ms": None}
    checks["storage"] = {"up": api_up and db_up, "ms": None}

    # ── 鉴权层 ── 不带 Key 打服务目录, 401 才是"活着"
    code, _, ms = _get("https://clavissinica.org/v1/chinese/services")
    checks["auth"] = {"up": code == 401, "ms": ms}

    # ── 文档站 ──
    code, _, ms = _get("https://clavissinica.org/")
    checks["site"] = {"up": code == 200, "ms": ms}

    return checks


def load():
    try:
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"samples": [], "days": [], "first_seen": None}


def main():
    now = datetime.now(timezone.utc)
    checks = probe()
    data = load()

    if not data.get("first_seen"):
        data["first_seen"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    sample = {"t": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "ms": checks["api"]["ms"]}
    for k, v in checks.items():
        sample[k] = 1 if v["up"] else 0
    data.setdefault("samples", []).append(sample)

    cutoff = now - timedelta(hours=SAMPLE_HOURS)
    data["samples"] = [s for s in data["samples"]
                       if s.get("t", "") >= cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")]

    # ── 日聚合 ──
    day = now.strftime("%Y-%m-%d")
    days = {d["d"]: d for d in data.get("days", [])}
    b = days.setdefault(day, {"d": day, "n": 0,
                              "up": {k: 0 for k in checks}})
    b["n"] += 1
    for k, v in checks.items():
        b["up"][k] = b["up"].get(k, 0) + (1 if v["up"] else 0)
    keep = (now - timedelta(days=DAY_BUCKETS)).strftime("%Y-%m-%d")
    data["days"] = sorted((v for k, v in days.items() if k >= keep),
                          key=lambda x: x["d"])

    data["generated_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    data["components"] = {k: {"up": v["up"], "ms": v["ms"]}
                          for k, v in checks.items()}
    data["total_samples"] = sum(d["n"] for d in data["days"])

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")

    line = "  ".join("%s=%s" % (k, "up" if v["up"] else "DOWN")
                     for k, v in sorted(checks.items()))
    print("%s  %s  (api %sms)" % (data["generated_at"], line, checks["api"]["ms"]))
    # 探测失败【不让 workflow 失败】: 失败本身就是要记录的数据,
    # 让 Actions 变红只会让真正的 workflow 故障淹没在里面。
    return 0


if __name__ == "__main__":
    sys.exit(main())
