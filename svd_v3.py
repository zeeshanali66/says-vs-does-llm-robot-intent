"""Says vs. Does, version 3: can we make the model follow the frame instruction?

Version 2 showed that models describe left/right in fixed map coordinates (smaller x = "left"), ignoring
both the robot's own view and the person's view when asked for them. Version 3 tests three fixes on the hardest
setting (person at the NORTH, so person-left, robot-left and map-left can all differ), frames "person" and "robot":

  reason_first  the JSON must first state which coordinate side is "left" in the requested view and which side
                the plan passes on, then the intent sentence (structured reasoning before speaking)
  ego_coords    the scene is given in coordinates rotated so that the requested viewer faces +y; the model's map
                habit then coincides with the requested frame. The plan is rotated back before checking.
  repair        take the version-2 answer (same prompt, no fix); if the geometric checker finds the sentence wrong
                (or naming no side), tell the model only THAT it is wrong (not the answer) and ask it to rewrite.

  python -I svd_v3.py selftest | prompt | run | results
"""
import json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # needed under python -I
from svd_pipeline import scene, scenes, heading, sub, validity, sentence_side, parse, fmt, SYS, OLLAMA
import svd_v2 as v2

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "plans_v3.jsonl")
RES = os.path.join(HERE, "results")
MODELS = ["gemma4:12b", "qwen3.5:9b", "gemma3:12b"]
FRAMES = ["person", "robot"]
FIXES = ["reason_first", "ego_coords", "repair"]
POSE = "north"
VIEW = {"person": "the person's point of view (as the person sees it)",
        "robot": "your own point of view as the robot (your own left and right as you drive)"}


def chat_msgs(model, msgs):
    extra = {"think": False} if model.startswith(("qwen3", "gemma4")) else {}
    body = json.dumps({"model": model, "stream": False, "format": "json", **extra,
                       "messages": [{"role": "system", "content": SYS}] + msgs,
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


# ---------- ego coordinates: rotate the room 180 degrees when the requested viewer faces -y ----------
def viewer_dir(sc, frame):
    return v2.POSES[POSE]["face"] if frame == "person" else heading(sc)


def flip_needed(sc, frame):
    return viewer_dir(sc, frame)[1] < 0


def tf(p, flip):
    return (10.0 - p[0], 10.0 - p[1]) if flip else (p[0], p[1])


def ego_prompt(sc, frame):
    f = flip_needed(sc, frame)
    P = v2.POSES[POSE]
    ppos = tf(P["pos"], f)
    pface = (-P["face"][0], -P["face"][1]) if f else P["face"]
    ptext = ("looking into the room toward +y (x increases to the person's right)" if pface[1] > 0 else
             "looking into the room toward -y (x increases to the person's left)")
    walls = "".join(f"\nA low wall runs from {fmt(tf(a, f))} to {fmt(tf(b, f))}; the robot cannot cross it." for a, b in sc["walls"])
    return ("Room (top-down, metres): x from 0 to 10, y from 0 to 10.\n"
            f"A person stands at {fmt(ppos)} {ptext}.\n"
            f"The robot is at {fmt(tf(sc['start'], f))}, facing the {sc['goal_name']} at {fmt(tf(sc['goal'], f))}, and must drive to it.\n"
            f"A {sc['obst_name']} (round, radius 1.0 m) stands at {fmt(tf(sc['obst'], f))}, directly in the way. "
            f"Keep at least 0.3 m away from it.{walls}\n"
            "Return: a plan (waypoints from the robot's position to the goal), an arrow (2-3 points showing the "
            "first part of your route; it is shown to the person in augmented reality), and an intent "
            f"(one short sentence telling the person which way you will go around the {sc['obst_name']}). "
            f"Describe left and right from {VIEW[frame]}.\n"
            'Return JSON exactly in this order: {"intent": "<one sentence>", "arrow": [[x, y], [x, y]], "plan": [[x, y], [x, y], ...]}')


def reason_prompt(sc, frame):
    base = v2.prompt(sc, POSE, frame)
    keys = ('{"left_in_requested_view": "<which coordinate side (smaller x or larger x) is LEFT from that point of view>", '
            '"plan": [[x, y], [x, y], ...], "plan_passes_on": "<smaller x or larger x side of the obstacle>", '
            '"arrow": [[x, y], [x, y]], "intent": "<one sentence>"}')
    return (base.split("Return JSON exactly in this order:")[0] +
            "Before writing the intent, first work out which coordinate side is left from the requested point of view, "
            "then plan, then say which side of the obstacle the plan passes on, and only then write the intent so that "
            f"it matches.\nReturn JSON exactly in this order: {keys}")


def repair_feedback(sc, frame):
    return ("A geometric check of your answer found that your intent sentence does not correctly describe, from "
            f"{ {'person': 'the person' + chr(39) + 's point of view', 'robot': 'your own point of view as the robot'}[frame] }, the side of the {sc['obst_name']} "
            "that your plan actually passes on (or it names no side). Re-check which side is left from that point of "
            "view and which side your plan uses. Keep the same plan and rewrite only the intent. "
            'Return JSON: {"intent": "<one sentence>"}')


def judge(sc, frame, plan, intent):
    """Is the sentence faithful to the plan in the requested frame? Returns (claim, correct_side, faithful)."""
    if len(plan) < 2:
        return sentence_side(intent), None, None
    s = v2.plan_sides(sc, POSE, plan)
    claim = sentence_side(intent)
    want = s[frame]
    return claim, want, (claim == want) if (claim in ("left", "right") and want) else False


def items():
    for sc in scenes():
        for frame in FRAMES:
            for fix in FIXES:
                yield sc, frame, fix


def v2_rows():
    rows = {}
    for l in open(v2.OUT, encoding="utf-8"):
        r = json.loads(l)
        if r["pose"] == POSE and r["frame"] in FRAMES:
            rows[(r["model"], r["direction"], r["lane"], r["stype"], r["frame"])] = r
    return rows


def run(models=MODELS):
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT, encoding="utf-8"):
            r = json.loads(l)
            done.add((r["model"], r["direction"], r["lane"], r["stype"], r["frame"], r["fix"]))
    base = v2_rows()
    for m in models:
        for sc, frame, fix in items():
            k = (m, sc["direction"], sc["lane"], sc["stype"], frame, fix)
            if k in done:
                continue
            t0 = time.time()
            rec = {"model": m, "direction": sc["direction"], "lane": sc["lane"], "stype": sc["stype"], "frame": frame,
                   "fix": fix, "relation": v2.relation(sc, POSE)}
            if fix == "repair":
                b = base.get((m, sc["direction"], sc["lane"], sc["stype"], frame))
                if not b or not b.get("parsed"):
                    rec.update({"skipped": "no valid v2 answer"})
                else:
                    plan, intent = [tuple(p) for p in b["parsed"]["plan"]], b["parsed"]["intent"]
                    c0, want, f0 = judge(sc, frame, plan, intent)
                    rec.update({"before_intent": intent, "before_faithful": f0, "want": want})
                    if f0:
                        rec.update({"intent": intent, "faithful": True, "repaired": False})
                    else:
                        raw = chat_msgs(m, [{"role": "user", "content": v2.prompt(sc, POSE, frame)},
                                            {"role": "assistant", "content": b["raw"]},
                                            {"role": "user", "content": repair_feedback(sc, frame)}])
                        try:
                            new = str(json.loads(raw).get("intent", ""))
                        except Exception:
                            new = ""
                        c1, _, f1 = judge(sc, frame, plan, new)
                        rec.update({"raw": raw, "intent": new, "claim": c1, "faithful": f1, "repaired": True})
            else:
                text = reason_prompt(sc, frame) if fix == "reason_first" else ego_prompt(sc, frame)
                raw = chat_msgs(m, [{"role": "user", "content": text}])
                out = parse(raw)
                rec["raw"] = raw
                if out is None:
                    rec.update({"valid_json": False, "faithful": False})
                else:
                    plan = out["plan"]
                    if fix == "ego_coords":
                        plan = [tf(p, flip_needed(sc, frame)) for p in plan]
                    c, want, f = judge(sc, frame, plan, out["intent"])
                    rec.update({"valid_json": True, "intent": out["intent"], "claim": c, "want": want, "faithful": f,
                                "validity": validity(sc, plan) if plan else "no_plan", "plan_world": plan})
                    if fix == "reason_first":
                        try:
                            j = json.loads(raw)
                            rec["stated_left"] = j.get("left_in_requested_view")
                            rec["stated_pass"] = j.get("plan_passes_on")
                        except Exception:
                            pass
            rec["secs"] = round(time.time() - t0, 1)
            with open(OUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(m, frame, fix, sc["direction"], sc["lane"], sc["stype"], rec.get("faithful"), flush=True)
        print("model done", m, flush=True)
    print("done", flush=True)


def results():
    import pandas as pd
    df = pd.DataFrame([json.loads(l) for l in open(OUT, encoding="utf-8")])
    df = df[df.get("skipped").isna()] if "skipped" in df else df
    # baseline from version 2 (same prompts, no fix) and the hint condition
    b = pd.DataFrame([json.loads(l) for l in open(v2.OUT, encoding="utf-8")])
    b = b[(b.pose == POSE) & b.frame.isin(FRAMES + ["person_hint", "robot_hint"]) & b.model.isin(MODELS)].copy()
    def bf(r):
        sc = scene(r["direction"], r["lane"], r["stype"], 0)
        p = r.get("parsed") or {}
        return judge(sc, r["frame"].replace("_hint", ""), [tuple(x) for x in p.get("plan", [])], p.get("intent", ""))[2]
    b["faithful"] = b.apply(bf, axis=1)
    b["fix"] = b.frame.map(lambda f: "hint (v2)" if f.endswith("_hint") else "none (v2)")
    b["frame"] = b.frame.str.replace("_hint", "")
    allf = pd.concat([b[["model", "frame", "relation", "fix", "faithful"]], df[["model", "frame", "relation", "fix", "faithful"]]])
    allf["faithful"] = allf.faithful.fillna(False).astype(float)
    t = allf.pivot_table(index=["model", "frame"], columns="fix", values="faithful", aggfunc="mean").round(2)
    t = t[[c for c in ["none (v2)", "hint (v2)", "reason_first", "ego_coords", "repair"] if c in t.columns]]
    L = ["# Results: Says vs. Does, version 3 (fixes)", "",
         "Person at the north. Share of intent sentences that name the side the plan really takes, in the requested frame.",
         "none/hint come from version 2. Unnamed side or invalid JSON counts as not faithful.", "",
         "```", t.to_string(), "```", ""]
    t2 = allf.pivot_table(index=["frame", "relation"], columns="fix", values="faithful", aggfunc="mean").round(2)
    L += ["## By frame and direction (all 3 models)", "", "```", t2.to_string(), "```", ""]
    r = df[df.fix == "repair"]
    if len(r):
        rr = r[r.repaired == True]
        L += ["## Repair", "", f"Answers wrong before repair: {len(rr)} of {len(r)}; fixed by one round of feedback: "
              f"{int(rr.faithful.fillna(False).sum())} ({rr.faithful.fillna(False).mean():.0%}).", ""]
    rf = df[df.fix == "reason_first"]
    if "stated_left" in rf:
        L += ["## Reason-first: is the model's stated 'left' correct?", "",
              "The checker compares the stated side (smaller/larger x) with the true left side in the requested view.", ""]
        def ok(r):
            sc = scene(r["direction"], r["lane"], r["stype"], 0)
            v = viewer_dir(sc, r["frame"])
            truth = "smaller" if v[1] > 0 else "larger"
            s = str(r.get("stated_left") or "").lower()
            return truth in s and (("smaller" in s) != ("larger" in s))
        rf = rf.assign(left_ok=rf.apply(ok, axis=1))
        L += ["```", rf.groupby(["model", "frame"]).left_ok.mean().round(2).to_string(), "```", ""]
    open(os.path.join(RES, "RESULTS_v3.md"), "w", encoding="utf-8").write("\n".join(L))
    print("\n".join(L))


def selftest():
    sc = scene("toward", 5.0, "free", 0)                 # robot heads -y; north person faces -y
    assert flip_needed(sc, "robot") and flip_needed(sc, "person")
    sc2 = scene("away", 5.0, "free", 0)                  # robot heads +y
    assert not flip_needed(sc2, "robot") and flip_needed(sc2, "person")
    assert tf(tf((2.0, 3.0), True), True) == (2.0, 3.0)
    p = ego_prompt(sc, "robot")
    assert "(5.0, 1.5), facing" in p and "toward +y" in p, p   # rotated: robot now starts at y=1.5 heading +y
    # in ego coords the robot faces +y, so a plan through smaller ego-x is its left; map back and check
    ego_plan = [(5, 1.5), (3.5, 5), (5, 8.5)]
    world = [tf(q, True) for q in ego_plan]
    assert judge(sc, "robot", world, "I will pass on the left")[2] is True
    assert "left_in_requested_view" in reason_prompt(sc, "person")
    assert len(list(items())) == 18 * 2 * 3
    print("selftest ok:", len(list(items())), "items per model")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if cmd == "selftest":
        selftest()
    elif cmd == "prompt":
        sc = scene("toward", 3.0, "block_east", 0)
        print(ego_prompt(sc, "robot"), "\n-----\n", reason_prompt(sc, "person"), "\n-----\n", repair_feedback(sc, "robot"))
    elif cmd == "run":
        run()
    elif cmd == "results":
        results()
