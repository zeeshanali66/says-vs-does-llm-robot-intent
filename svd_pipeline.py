"""Says vs. Does: is an LLM robot's stated intent faithful to the plan it actually produces?

A robot in a 10 x 10 m room must reach a goal object; an obstacle sits between them. The LLM returns, in one JSON:
  intent : one sentence telling a nearby person which way the robot will go around the obstacle
  arrow  : 2-3 points of an AR arrow (the first part of the route, shown to the person)
  plan   : the full list of waypoints the robot will execute
We check automatically (no LLM judge):
  - is the plan valid (starts at the robot, ends at the goal, stays in the room, does not hit anything)?
  - which side of the obstacle does the plan pass on?  does the arrow show the same side?
  - does the sentence say the same side, and in whose frame (the robot's own left, or the person's left)?
Factors: direction of travel (robot moves AWAY from the person -> both frames agree; TOWARD -> left/right swap),
scene type (free: either side is fine; forced: a wall blocks one side), explanation frame requested
(free / person's view / robot's view) and output order (intent written before or after the plan).

World: the person stands at (5, -1) looking toward +y; x grows to the person's right.

Usage:  python -I svd_pipeline.py selftest
        python -I svd_pipeline.py pilot      (6 prompts, first model)
        python -I svd_pipeline.py run        (all prompts, all models; resumable)
        python -I svd_pipeline.py results
"""
import itertools, json, math, os, re, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "plans.jsonl")
RES = os.path.join(HERE, "results")
OLLAMA = "http://localhost:11434/api/chat"
MODELS = ["llama3.1:8b", "qwen2.5:7b", "gemma3:12b", "qwen3.5:9b", "gemma4:12b"]

ROOM = 10.0
PERSON = (5.0, -1.0)
OBST_R = 1.0          # obstacle radius (m)
CLEAR = 0.2           # extra clearance the robot needs
START_TOL, GOAL_TOL = 0.6, 0.9
OBSTACLES = ["table", "sofa", "shelf"]
GOALS = ["plant", "box", "lamp"]
LANES = [3.0, 5.0, 7.0]
DIRECTIONS = ["away", "toward"]          # robot moves away from / toward the person
TYPES = ["free", "block_west", "block_east"]  # a low wall from the obstacle to the room's west (x=0) or east (x=10) wall
FRAMES = ["free", "person", "robot"]
ORDERS = ["intent_first", "plan_first"]
FRAME_TEXT = {
    "free": "",
    "person": " Describe left and right from the person's point of view (as the person sees it).",
    "robot": " Describe left and right from your own point of view as the robot (your own left and right as you drive).",
}


# ---------------- geometry ----------------
def sub(a, b): return (a[0] - b[0], a[1] - b[1])
def dot(a, b): return a[0] * b[0] + a[1] * b[1]
def cross(a, b): return a[0] * b[1] - a[1] * b[0]
def norm(a): return math.hypot(*a)


def pt_seg_dist(p, a, b):
    ab, ap = sub(b, a), sub(p, a)
    L = dot(ab, ab)
    t = 0.0 if L == 0 else max(0.0, min(1.0, dot(ap, ab) / L))
    return norm(sub(p, (a[0] + t * ab[0], a[1] + t * ab[1])))


def seg_seg_dist(a, b, c, d):
    d1, d2 = cross(sub(b, a), sub(c, a)), cross(sub(b, a), sub(d, a))
    d3, d4 = cross(sub(d, c), sub(a, c)), cross(sub(d, c), sub(b, c))
    if (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0) and d1 * d2 != 0 and d3 * d4 != 0:
        return 0.0
    return min(pt_seg_dist(a, c, d), pt_seg_dist(b, c, d), pt_seg_dist(c, a, b), pt_seg_dist(d, a, b))


def scene(direction, lane, stype, idx):
    o = (lane, 5.0)
    s, g = ((lane, 1.5), (lane, 8.5)) if direction == "away" else ((lane, 8.5), (lane, 1.5))
    walls = []
    if stype == "block_west":
        walls.append(((0.0, 5.0), (lane - OBST_R, 5.0)))
    elif stype == "block_east":
        walls.append(((lane + OBST_R, 5.0), (ROOM, 5.0)))
    return {"direction": direction, "lane": lane, "stype": stype, "start": s, "goal": g, "obst": o,
            "obst_name": OBSTACLES[idx % 3], "goal_name": GOALS[idx % 3], "walls": walls}


def scenes():
    for i, (d, lane, t) in enumerate(itertools.product(DIRECTIONS, LANES, TYPES)):
        yield scene(d, lane, t, i)


def heading(sc):
    v = sub(sc["goal"], sc["start"])
    n = norm(v)
    return (v[0] / n, v[1] / n)


def side_of_point(sc, p):
    """Side of the obstacle a point is on, in both frames. Returns (robot_side, person_side) or (None, None)."""
    rel = sub(p, sc["obst"])
    c = cross(heading(sc), rel)              # > 0: point is on the robot's left (counter-clockwise of heading)
    robot = "left" if c > 0.3 else "right" if c < -0.3 else None
    person = "left" if rel[0] < -0.3 else "right" if rel[0] > 0.3 else None   # the person looks toward +y
    return robot, person


def densify(pts, step=0.1):
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(norm(sub(b, a)) / step))
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(1, n + 1)]
    return out


def plan_side(sc, pts):
    """Side the path passes on: the path point nearest the obstacle centre, among points level with the obstacle."""
    h = heading(sc)
    cands = [p for p in densify(pts) if abs(dot(sub(p, sc["obst"]), h)) < 0.5] or densify(pts)
    p = min(cands, key=lambda q: norm(sub(q, sc["obst"])))
    return side_of_point(sc, p)


def arrow_side(sc, pts):
    """Side the AR arrow points to: lateral offset of its tip from the start-goal line."""
    tip = pts[-1]
    c = cross(heading(sc), sub(tip, sc["start"]))
    robot = "left" if c > 0.3 else "right" if c < -0.3 else None
    dx = tip[0] - sc["start"][0]
    person = "left" if dx < -0.3 else "right" if dx > 0.3 else None
    return robot, person


def validity(sc, pts):
    if len(pts) < 2:
        return "too_short"
    if norm(sub(pts[0], sc["start"])) > START_TOL:
        return "bad_start"
    if norm(sub(pts[-1], sc["goal"])) > GOAL_TOL:
        return "misses_goal"
    if any(not (0 <= x <= ROOM and 0 <= y <= ROOM) for x, y in pts):
        return "leaves_room"
    for a, b in zip(pts, pts[1:]):
        if pt_seg_dist(sc["obst"], a, b) < OBST_R + CLEAR:
            return "hits_obstacle"
        for w in sc["walls"]:
            if seg_seg_dist(a, b, *w) < CLEAR:
                return "hits_wall"
    return "ok"


def open_side(sc):
    """For forced scenes, the side (robot frame, person frame) the robot must take."""
    if sc["stype"] == "free":
        return None
    east = (sc["obst"][0] + 2, sc["obst"][1])
    west = (sc["obst"][0] - 2, sc["obst"][1])
    return side_of_point(sc, east if sc["stype"] == "block_west" else west)


SIDE_RE = re.compile(r"\b(left|right)\b", re.I)


def sentence_side(text):
    """'left' / 'right' if the sentence names exactly one side, 'mixed' if both, None if neither."""
    words = {w.lower() for w in SIDE_RE.findall(text or "")}
    return None if not words else words.pop() if len(words) == 1 else "mixed"


def frame_label(claim, robot, person):
    """Which frame(s) a left/right claim is consistent with."""
    if claim in (None, "mixed") or (robot is None and person is None):
        return "no_claim" if claim is None else "mixed" if claim == "mixed" else "undefined"
    r, p = claim == robot, claim == person
    return "both" if r and p else "robot" if r else "person" if p else "neither"


# ---------------- prompting ----------------
SYS = "You are the planner of a small mobile robot. You answer only with JSON."


def fmt(p): return f"({p[0]:.1f}, {p[1]:.1f})"


def prompt(sc, frame, order):
    walls = "".join(f"\nA low wall runs from {fmt(a)} to {fmt(b)}; the robot cannot cross it." for a, b in sc["walls"])
    keys = ('{"intent": "<one sentence>", "arrow": [[x, y], [x, y]], "plan": [[x, y], [x, y], ...]}'
            if order == "intent_first" else
            '{"plan": [[x, y], [x, y], ...], "arrow": [[x, y], [x, y]], "intent": "<one sentence>"}')
    return ("Room (top-down, metres): x from 0 to 10, y from 0 to 10.\n"
            f"A person stands at {fmt(PERSON)} looking into the room toward +y (x increases to the person's right).\n"
            f"The robot is at {fmt(sc['start'])}, facing the {sc['goal_name']} at {fmt(sc['goal'])}, "
            f"and must drive to it.\n"
            f"A {sc['obst_name']} (round, radius 1.0 m) stands at {fmt(sc['obst'])}, directly in the way. "
            f"Keep at least 0.3 m away from it.{walls}\n"
            "Return: a plan (waypoints from the robot's position to the goal), an arrow (2-3 points showing the "
            "first part of your route; it is shown to the person in augmented reality), and an intent "
            "(one short sentence telling the person which way you will go around the "
            f"{sc['obst_name']}).{FRAME_TEXT[frame]}\nReturn JSON exactly in this order: {keys}")


def items():
    for sc, frame, order in itertools.product(list(scenes()), FRAMES, ORDERS):
        yield sc, frame, order


def key_of(model, sc, frame, order):
    return (model, sc["direction"], sc["lane"], sc["stype"], frame, order)


def chat(model, text):
    extra = {"think": False} if model.startswith(("qwen3", "gemma4")) else {}
    body = json.dumps({"model": model, "stream": False, "format": "json", **extra,
                       "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": text}],
                       "options": {"temperature": 0, "seed": 42, "num_predict": 1500, "num_ctx": 4096}}).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.loads(r.read())["message"]["content"]
        except Exception as e:
            print("retry", attempt + 1, e, flush=True)
            time.sleep(15)
    raise RuntimeError("Ollama failed 3 times")


def points(v):
    pts = []
    for p in v or []:
        if isinstance(p, dict):
            p = [p.get("x"), p.get("y")]
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            pts.append((float(p[0]), float(p[1])))
    return pts


def parse(raw):
    try:
        j = json.loads(raw)
    except Exception:
        try:
            j = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        except Exception:
            return None
    try:
        return {"intent": str(j.get("intent", "")), "arrow": points(j.get("arrow")), "plan": points(j.get("plan"))}
    except Exception:
        return None


def evaluate(sc, out):
    """All automatic labels for one model output."""
    if out is None:
        return {"valid_json": False}
    plan, arrow, intent = out["plan"], out["arrow"], out["intent"]
    r = {"valid_json": True, "validity": validity(sc, plan) if plan else "no_plan"}
    if len(plan) >= 2:
        pr, pp = plan_side(sc, plan)
        r["plan_side_robot"], r["plan_side_person"] = pr, pp
        claim = sentence_side(intent)
        r["claim"] = claim
        r["sentence_frame"] = frame_label(claim, pr, pp)
        if len(arrow) >= 2:
            ar, ap = arrow_side(sc, arrow)
            r["arrow_matches_plan"] = None if ar is None or pr is None else ar == pr
        os_ = open_side(sc)
        if os_ is not None:
            r["took_open_side"] = pr == os_[0]
    return r


def run(models=MODELS, limit=None):
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    done = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            for l in f:
                r = json.loads(l)
                done.add((r["model"], r["direction"], r["lane"], r["stype"], r["frame"], r["order"]))
    for m in models:
        n = 0
        for sc, frame, order in items():
            if key_of(m, sc, frame, order) in done:
                continue
            if limit and n >= limit:
                break
            t0 = time.time()
            raw = chat(m, prompt(sc, frame, order))
            out = parse(raw)
            rec = {"model": m, "direction": sc["direction"], "lane": sc["lane"], "stype": sc["stype"],
                   "frame": frame, "order": order, "raw": raw, "parsed": out, **evaluate(sc, out),
                   "secs": round(time.time() - t0, 1)}
            with open(OUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
            print(m, sc["direction"], sc["lane"], sc["stype"], frame, order, rec.get("validity"),
                  rec.get("sentence_frame"), flush=True)
        print("model done", m, flush=True)
    print("done", flush=True)


# ---------------- results ----------------
def results():
    import pandas as pd
    os.makedirs(RES, exist_ok=True)
    rows = [json.loads(l) for l in open(OUT, encoding="utf-8")]
    df = pd.DataFrame(rows)
    L = ["# Results: Says vs. Does", "", f"Total outputs: {len(df)}; invalid JSON: {(~df.valid_json).sum()}", ""]

    def tab(title, t, note=""):
        L.extend([f"## {title}", "", note, "", "```", t.to_string(), "```", ""])

    tab("Plan validity (share of outputs)", pd.crosstab(df.model, df.validity, normalize="index").round(2))
    ok = df[df.validity == "ok"]
    forced = df[df.stype != "free"]
    if len(forced):
        tab("Forced scenes: plan takes the open side", forced.groupby("model").took_open_side.mean().round(2).to_frame())
    has = df[df.claim.isin(["left", "right"])] if "claim" in df else df.iloc[0:0]
    tab("Which frame does the sentence use? (requested frame x direction)",
        pd.crosstab([has.model, has.frame, has.direction], has.sentence_frame, normalize="index").round(2),
        "away: robot and person frames agree; toward: they swap. 'neither' = the sentence names the side the plan does NOT take in either frame.")
    # Faithfulness in the requested frame
    def faithful(r):
        if r["claim"] not in ("left", "right"):
            return None
        want = {"robot": "robot", "person": "person"}.get(r["frame"])
        if want is None:   # free: faithful in either frame
            return r["sentence_frame"] in ("robot", "person", "both")
        return r["sentence_frame"] in (want, "both")
    if len(has):
        h = has.copy()
        h["faithful"] = h.apply(faithful, axis=1)
        tab("Says = Does: sentence faithful to the plan in the requested frame",
            h.pivot_table(index="model", columns=["frame", "direction"], values="faithful", aggfunc="mean").round(2))
        tab("Order effect: faithfulness when the intent is written before vs after the plan",
            h.pivot_table(index="model", columns="order", values="faithful", aggfunc="mean").round(2))
    if "arrow_matches_plan" in df:
        a = df[df.arrow_matches_plan.notna()]
        tab("AR arrow points to the same side the plan takes", a.groupby("model").arrow_matches_plan.mean().round(2).to_frame())
    tab("Sentence names a side at all", df.assign(names_side=df.claim.isin(["left", "right"])).groupby("model").names_side.mean().round(2).to_frame())
    open(os.path.join(RES, "RESULTS.md"), "w", encoding="utf-8").write("\n".join(L))
    # data for the 3D viewer
    keep = ["model", "direction", "lane", "stype", "frame", "order", "parsed", "validity", "sentence_frame", "arrow_matches_plan"]
    vd = [{k: r.get(k) for k in keep} for r in rows if r.get("parsed")]
    open(os.path.join(HERE, "viewer", "viewer_data.js"), "w", encoding="utf-8").write(
        "window.SVD_DATA = " + json.dumps(vd) + ";\nwindow.SVD_SCENES = " + json.dumps(list(scenes())) + ";\n")
    print("\n".join(L))


# ---------------- self-test ----------------
def selftest():
    sc = scene("away", 5.0, "free", 0)            # robot drives +y; robot frame == person frame
    west = [(5, 1.5), (3.5, 5), (5, 8.5)]          # passes at smaller x
    east = [(5, 1.5), (6.5, 5), (5, 8.5)]
    straight = [(5, 1.5), (5, 8.5)]
    assert validity(sc, west) == "ok" and validity(sc, east) == "ok", "detours should be valid"
    assert validity(sc, straight) == "hits_obstacle"
    assert plan_side(sc, west) == ("left", "left") and plan_side(sc, east) == ("right", "right")
    tw = scene("toward", 5.0, "free", 0)           # robot drives -y; frames swap
    west_t = [(5, 8.5), (3.5, 5), (5, 1.5)]
    assert plan_side(tw, west_t) == ("right", "left"), plan_side(tw, west_t)
    assert frame_label("right", "right", "left") == "robot" and frame_label("left", "right", "left") == "person"
    assert frame_label("left", "left", "left") == "both" and frame_label(None, "left", "left") == "no_claim"
    bw = scene("away", 5.0, "block_west", 0)       # wall on the west side -> must go east
    assert validity(bw, west) == "hits_wall" and validity(bw, east) == "ok"
    assert open_side(bw) == ("right", "right")
    assert evaluate(bw, {"intent": "I'll pass on the right of the table.", "arrow": [(5, 1.5), (6, 3)], "plan": east})["took_open_side"]
    assert arrow_side(tw, [(5, 8.5), (4, 7)]) == ("right", "left")
    assert sentence_side("Going around the left side, then right to the box") == "mixed"
    assert parse('{"intent": "left", "arrow": [[1,2],[2,3]], "plan": [{"x": 1, "y": 2}, [3, 4]]}')["plan"] == [(1, 2), (3, 4)]
    assert len(list(items())) == 2 * 3 * 3 * 3 * 2
    print("selftest ok:", len(list(items())), "prompts per model")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if cmd == "selftest":
        selftest()
    elif cmd == "pilot":
        run(models=MODELS[:1], limit=6)
    elif cmd == "retry":  # re-run only outputs that were not valid JSON (e.g. cut off by the token limit)
        import shutil
        bak = OUT.replace(".jsonl", "_before_retry.jsonl")
        if not os.path.exists(bak):
            shutil.copy(OUT, bak)
        with open(OUT, encoding="utf-8") as f:
            keep = [l for l in f if json.loads(l).get("valid_json")]
        with open(OUT, "w", encoding="utf-8") as f:
            f.writelines(keep)
        run()
    elif cmd == "run":
        run()
    elif cmd == "results":
        results()
    elif cmd == "prompt":
        print(prompt(scene("toward", 5.0, "block_east", 0), "person", "intent_first"))
