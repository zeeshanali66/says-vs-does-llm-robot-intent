"""Says vs. Does, version 2.

Version 1 found that models describe the robot's route from the person's side, even when asked for the robot's own
left/right. But there the person stood at the bottom of the map looking up, so the person's left was also the map's
left (-x). Version 2 separates the three frames and tests a simple fix:

  * person pose: "south" (as in v1) or "north" (stands at the top, looking down: the person's left is +x, the map's is -x)
  * frames: free, person, robot (as in v1) plus two hint conditions that spell out which coordinate side is "left"
  * intent is always written first (v1 showed the order matters little for the stronger models)

For every output we record which side the plan takes in the robot's frame, the person's frame and the map frame, and
which of those the sentence's left/right matches.

  python -I svd_v2.py selftest | prompt | run | results
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # needed under python -I
import svd_pipeline as v1
from svd_pipeline import scene, scenes, heading, sub, cross, densify, dot, norm, validity, open_side, sentence_side, parse, chat, fmt, SYS

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "plans_v2.jsonl")
RES = os.path.join(HERE, "results")
MODELS = ["gemma4:12b", "qwen3.5:9b", "gemma3:12b", "qwen2.5:7b", "llama3.1:8b"]   # strongest first
POSES = {
    "south": {"pos": (5.0, -1.0), "face": (0.0, 1.0), "text": "looking into the room toward +y (x increases to the person's right)"},
    "north": {"pos": (5.0, 11.0), "face": (0.0, -1.0), "text": "looking into the room toward -y (x increases to the person's left)"},
}
FRAMES = ["free", "person", "robot", "person_hint", "robot_hint"]


def lr(c):
    return "left" if c > 0.3 else "right" if c < -0.3 else None


def sides(sc, pose, p):
    """Side of the obstacle that point p is on, in the robot, person and map frames."""
    rel = sub(p, sc["obst"])
    return {"robot": lr(cross(heading(sc), rel)),
            "person": lr(cross(POSES[pose]["face"], rel)),
            "map": lr(-rel[0])}                       # map frame: top-down, +y up, so smaller x is "left"


def plan_sides(sc, pose, pts):
    h = heading(sc)
    cands = [p for p in densify(pts) if abs(dot(sub(p, sc["obst"]), h)) < 0.5] or densify(pts)
    return sides(sc, pose, min(cands, key=lambda q: norm(sub(q, sc["obst"]))))


def left_side_text(vec):
    """Which coordinate side is 'left' for someone facing along +y or -y."""
    return "the side with smaller x" if vec[1] > 0 else "the side with larger x"


def frame_text(sc, pose, frame):
    hd = heading(sc)
    return {
        "free": "",
        "person": " Describe left and right from the person's point of view (as the person sees it).",
        "robot": " Describe left and right from your own point of view as the robot (your own left and right as you drive).",
        "person_hint": " Describe left and right from the person's point of view. Note: the person's left is "
                       f"{left_side_text(POSES[pose]['face'])}.",
        "robot_hint": " Describe left and right from your own point of view as the robot. Note: you drive toward "
                      f"{'+y' if hd[1] > 0 else '-y'}, so your own left is {left_side_text(hd)}.",
    }[frame]


def prompt(sc, pose, frame):
    walls = "".join(f"\nA low wall runs from {fmt(a)} to {fmt(b)}; the robot cannot cross it." for a, b in sc["walls"])
    P = POSES[pose]
    return ("Room (top-down, metres): x from 0 to 10, y from 0 to 10.\n"
            f"A person stands at {fmt(P['pos'])} {P['text']}.\n"
            f"The robot is at {fmt(sc['start'])}, facing the {sc['goal_name']} at {fmt(sc['goal'])}, and must drive to it.\n"
            f"A {sc['obst_name']} (round, radius 1.0 m) stands at {fmt(sc['obst'])}, directly in the way. "
            f"Keep at least 0.3 m away from it.{walls}\n"
            "Return: a plan (waypoints from the robot's position to the goal), an arrow (2-3 points showing the "
            "first part of your route; it is shown to the person in augmented reality), and an intent "
            f"(one short sentence telling the person which way you will go around the {sc['obst_name']})."
            f"{frame_text(sc, pose, frame)}\n"
            'Return JSON exactly in this order: {"intent": "<one sentence>", "arrow": [[x, y], [x, y]], "plan": [[x, y], [x, y], ...]}')


def items():
    """North: all 5 frames. South: only the 2 hint frames (the other 3 were run in v1)."""
    for sc in scenes():
        for f in FRAMES:
            yield sc, "north", f
        for f in ("person_hint", "robot_hint"):
            yield sc, "south", f


def relation(sc, pose):
    """Is the robot driving toward the person or away?"""
    to_person = sub(POSES[pose]["pos"], sc["start"])
    return "toward" if dot(heading(sc), to_person) > 0 else "away"


def evaluate(sc, pose, out):
    if out is None:
        return {"valid_json": False}
    plan, arrow = out["plan"], out["arrow"]
    r = {"valid_json": True, "validity": validity(sc, plan) if plan else "no_plan", "claim": sentence_side(out["intent"])}
    if len(plan) >= 2:
        s = plan_sides(sc, pose, plan)
        r.update({f"plan_{k}": v for k, v in s.items()})
        if len(arrow) >= 2:
            c = cross(heading(sc), sub(arrow[-1], sc["start"]))
            r["arrow_matches_plan"] = None if lr(c) is None or s["robot"] is None else lr(c) == s["robot"]
        o = open_side(sc)
        if o is not None:
            r["took_open_side"] = s["robot"] == o[0]
    return r


def run(models=MODELS):
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT, encoding="utf-8"):
            r = json.loads(l)
            done.add((r["model"], r["direction"], r["lane"], r["stype"], r["pose"], r["frame"]))
    for m in models:
        for sc, pose, frame in items():
            k = (m, sc["direction"], sc["lane"], sc["stype"], pose, frame)
            if k in done:
                continue
            t0 = time.time()
            raw = chat(m, prompt(sc, pose, frame))
            out = parse(raw)
            rec = {"model": m, "direction": sc["direction"], "lane": sc["lane"], "stype": sc["stype"], "pose": pose,
                   "frame": frame, "relation": relation(sc, pose), "raw": raw, "parsed": out,
                   **evaluate(sc, pose, out), "secs": round(time.time() - t0, 1)}
            with open(OUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(m, pose, sc["direction"], sc["lane"], sc["stype"], frame, rec.get("claim"), flush=True)
        print("model done", m, flush=True)
    print("done", flush=True)


def results():
    import pandas as pd
    rows = [json.loads(l) for l in open(OUT, encoding="utf-8")]
    df = pd.DataFrame(rows)
    # add v1 south rows for the 3 base frames (intent written first), so both poses can be compared
    v1rows = [json.loads(l) for l in open(v1.OUT, encoding="utf-8")]
    for r in v1rows:
        if r["order"] != "intent_first":
            continue
        sc = scene(r["direction"], r["lane"], r["stype"], 0)
        out = r.get("parsed")
        rec = {"model": r["model"], "direction": r["direction"], "lane": r["lane"], "stype": r["stype"], "pose": "south",
               "frame": r["frame"], "relation": relation(sc, "south"), **evaluate(sc, "south", out)}
        df = pd.concat([df, pd.DataFrame([rec])], ignore_index=True)
    L = ["# Results: Says vs. Does, version 2", "",
         f"Outputs: {len(rows)} new (v2) + {len(df) - len(rows)} reused from v1 (south pose, intent first). "
         f"Invalid JSON (v2): {(~pd.Series([r['valid_json'] for r in rows])).sum()}", ""]

    def tab(title, t, note=""):
        L.extend([f"## {title}", "", note, "", "```", t.to_string(), "```", ""])

    h = df[df.claim.isin(["left", "right"]) & df.plan_robot.notna()].copy()
    for k in ("robot", "person", "map"):
        h[f"m_{k}"] = h.claim == h[f"plan_{k}"]
    want = {"person": "person", "person_hint": "person", "robot": "robot", "robot_hint": "robot"}
    h["faithful"] = h.apply(lambda r: r[f"m_{want[r.frame]}"] if r.frame in want else (r.m_robot or r.m_person), axis=1)
    tab("Says = Does: sentence matches the plan in the requested frame",
        h.pivot_table(index="model", columns=["frame", "pose", "relation"], values="faithful", aggfunc="mean").round(2).T,
        "free = matches the robot's or the person's frame. Rows: requested frame, where the person stands, robot driving toward/away from the person.")
    # the decisive cells: person at the NORTH. Robot driving away from the person (south): robot = person, map differs.
    # Robot driving toward the person (north): robot = map, person differs.
    n = h[h.pose == "north"]
    tab("Person at the north: which frame does the sentence match? (share of sentences)",
        n.pivot_table(index=["model", "frame", "relation"], values=["m_robot", "m_person", "m_map"], aggfunc="mean").round(2),
        "north+away: robot and person agree, map differs. north+toward: robot and map agree, person differs.")
    tab("Does spelling out which side is 'left' fix it? (faithfulness, robot frame)",
        h[h.frame.isin(["robot", "robot_hint"])].pivot_table(index="model", columns=["frame", "pose"], values="faithful", aggfunc="mean").round(2))
    tab("Does spelling out which side is 'left' fix it? (faithfulness, person frame)",
        h[h.frame.isin(["person", "person_hint"])].pivot_table(index="model", columns=["frame", "pose"], values="faithful", aggfunc="mean").round(2))
    v2 = pd.DataFrame(rows)
    tab("Plan validity, v2 outputs", pd.crosstab(v2.model, v2.validity, normalize="index").round(2))
    tab("Sentence names a side, v2 outputs", v2.assign(names_side=v2.claim.isin(["left", "right"])).groupby("model").names_side.mean().round(2).to_frame())
    open(os.path.join(RES, "RESULTS_v2.md"), "w", encoding="utf-8").write("\n".join(L))
    print("\n".join(L))


def selftest():
    # north pose, robot drives south (away from... no: toward -y is away from a north person)
    sc = scene("toward", 5.0, "free", 0)            # robot drives -y
    assert relation(sc, "north") == "away" and relation(sc, "south") == "toward"
    west = [(5, 8.5), (3.5, 5), (5, 1.5)]           # passes at smaller x
    s = plan_sides(sc, "north", west)
    # robot heading -y: its left is +x, so west = robot's right. North person faces -y: their left is +x, west = right.
    assert s == {"robot": "right", "person": "right", "map": "left"}, s
    s2 = plan_sides(scene("away", 5.0, "free", 0), "north", [(5, 1.5), (3.5, 5), (5, 8.5)])
    # robot heading +y: west = robot's left = map left; north person: west = their right
    assert s2 == {"robot": "left", "person": "right", "map": "left"}, s2
    assert plan_sides(sc, "south", west) == {"robot": "right", "person": "left", "map": "left"}   # matches v1
    assert "larger x" in frame_text(sc, "north", "robot_hint") and "larger x" in frame_text(sc, "north", "person_hint")
    assert "smaller x" in frame_text(sc, "south", "person_hint")
    n = len(list(items()))
    assert n == 18 * 7, n
    print("selftest ok:", n, "prompts per model")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if cmd == "selftest":
        selftest()
    elif cmd == "prompt":
        print(prompt(scene("toward", 3.0, "block_east", 0), "north", "robot_hint"))
    elif cmd == "run":
        run()
    elif cmd == "results":
        results()
