# Says vs. Does: is an LLM robot's stated intent faithful to its plan?

Robots and AR assistants increasingly *tell* people what they are about to do ("I'll go around the left of the
table") and *show* it (an AR arrow). If the words or the arrow disagree with the plan the robot actually
executes, the explanation is worse than none: the person steps into the robot's path.

This small study asks a local LLM to act as a robot planner. In one JSON answer it returns
**an intent sentence**, **an AR arrow** (the first part of the route) and **the full plan** (waypoints).
Everything is checked by geometry, with no LLM judge:

| Check | How |
|---|---|
| Plan valid? | starts at the robot, ends at the goal, stays in the room, keeps clear of the obstacle and walls |
| Which side does the plan take? | side of the obstacle at the point where the path passes it, in the robot's frame and the person's frame |
| Does the arrow agree? | lateral direction of the arrow tip vs. the side the plan takes |
| Does the sentence agree? | the left/right word in the sentence vs. the plan's side, in each frame |

## Factors
- **Direction of travel.** Robot drives *away* from the person (robot-left = person-left) or *toward* them (left and right swap).
- **Scene type.** *free* (either side works) or *forced* (a low wall blocks one side).
- **Requested frame.** free / "from the person's point of view" / "from your own point of view as the robot".
- **Order.** intent written *before* the plan (a commitment) or *after* it (a description).
- 18 scenes × 3 frames × 2 orders = 108 prompts per model; 5 local models (Llama 3.1 8B, Qwen 2.5 7B, Gemma 3 12B, Qwen 3.5 9B, Gemma 4 12B via Ollama).

Note: when the robot drives toward the person, any left/right word matches the plan in *one* of the two frames,
so faithfulness is only decidable when the frame is requested explicitly (or when frames agree).

## Related work and gap
Work on communicating robot intent shows intent in AR or words (e.g., AR motion intent for robots;
CoRI, 2025; explainable object-oriented HRI in AR, 2026; PerceptTwin, 2026), and LLM planners are checked for
plan feasibility. We did not find work that measures whether an LLM planner's *stated* intent (sentence and
AR arrow) matches the plan it actually outputs, or how this depends on the frame of reference.
This complements our earlier frame-of-reference study ("Whose left?").

## Results (540 outputs: 5 local models × 108 prompts)
Full tables: [`results/RESULTS.md`](results/RESULTS.md). Problems we hit and how we handled them: [`docs/RESEARCH_LOG.md`](docs/RESEARCH_LOG.md).

- **Most plans are not even valid.** Only Gemma 4 produced a valid route in about half the scenes (54%); Gemma 3 25%, Qwen 3.5 17%, Qwen 2.5 2%, Llama 3.1 0%. The most common failure is driving through the obstacle. When one side was blocked by a wall, Gemma 4 chose the open side 88% of the time; the others 7 to 33%.
- **The AR arrow almost always agrees with the plan** (91 to 100%). The arrow shows only the first part of the route, which models usually copy from the plan, so this is the easy part.
- **The sentence is where faithfulness breaks, and it breaks on perspective.** When the robot drives *away* from the person (robot's left = person's left), Gemma 4 and Qwen 3.5 describe the side correctly 81 to 100% of the time. When the robot drives *toward* the person and is asked to describe its route **in its own frame**, they are faithful only **0% (Gemma 4)** and **7% (Qwen 3.5)** of the time: they keep using the person's/map's left. Example: Gemma 4 passes on the robot's right and says *"I will pass to the left of the table."*
- **Writing the plan first does not help.** Faithfulness is the same or lower when the model writes the plan before the sentence (e.g. Llama 0.45 → 0.17).
- **Caveat on "whose left".** The person stands at the bottom of the map looking up, so the person's left is also the map's left. These results cannot yet separate "uses the person's perspective" from "uses map directions". The next version moves the person to the side of the room.

**Why it matters:** a robot that says "left" while turning to its own right sends a person into its path. Checking the sentence against the plan with simple geometry, as here, is cheap enough to run before every utterance.

Limitations: a 2D top-down room with one obstacle, one temperature-0 sample per prompt, five small local models, and an automatic left/right parser for the sentence (it marks sentences without a side as undefined).

## Run
```
python -I svd_pipeline.py selftest   # geometry unit tests
python -I svd_pipeline.py prompt     # print one example prompt
python -I svd_pipeline.py pilot      # 6 prompts on one model
python -I svd_pipeline.py run        # everything (resumable)
python -I svd_pipeline.py results    # results/RESULTS.md + viewer data
```
Open `viewer/index.html` through a local web server (e.g. `python -m http.server`) to see each plan, arrow and
sentence in 3D from the person's position (WebXR-ready).

## Disclosure
Code and documentation were written with the help of an AI assistant; the research design, checking and
decisions are the author's.

## License
MIT
