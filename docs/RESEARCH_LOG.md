# Research log: Says vs. Does

## 1. Idea and novelty check (2026-11-24)
Inspired by work on communicating robot intent with AR (e.g., Szafir's lab) and LLM-generated AR guidance
(e.g., Suzuki's lab). Search found intent-communication systems (CoRI 2025, X-OOHRI 2026, PerceptTwin 2026)
but nothing that measures whether an LLM planner's stated intent matches its own plan. Small enough for one PC.

## 2. Design decisions
- **No LLM judge.** Side-of-obstacle is computed with geometry so results are reproducible and cheap.
- **Two frames.** Every left/right claim is labelled robot-frame, person-frame, both or neither, reusing the
  frame-of-reference checker idea from "Whose left?".
- **Undecidable case found while designing.** With the robot driving toward the person and no requested frame,
  every left/right word is "faithful" in one frame. We therefore report frame *choice* for that cell and
  measure faithfulness only where it is decidable.
- **Forced scenes** (a wall closes one side) test whether the plan is even sensible before we judge the words.
- **Order factor.** Writing the intent first may act as a commitment; writing it after may be a post-hoc
  description. JSON key order is the only change between the two.

## 3. Testing
- `selftest` covers: detours valid, straight line hits the obstacle, side labels in both frames for both
  directions, wall collision, open-side logic, arrow side, mixed left/right sentences, tolerant JSON parsing.
- The results script and the 3D viewer were tested end to end on synthetic outputs before the real run.

## 4. Run
Started automatically after the overnight GPU queue (09:14 to 10:32 PKT, 540 outputs, 5 models), with the temperature watchdog (peak 74 °C, no alerts).

## 5. Problem: cut-off answers
40 of 540 answers were not valid JSON, 29 of them from Qwen 3.5. Reading them showed they were not malformed but **cut off**: Qwen 3.5 writes very fine-grained routes (a waypoint every 0.1 m), and the 400-token output limit ended them mid-list. That would have unfairly counted a style choice as a failure. Fix: raise the limit to 1,500 tokens and re-run only the invalid items (`python -I svd_pipeline.py retry`; the original file is kept as `data/plans_before_retry.jsonl`). Because decoding is deterministic (temperature 0, fixed seed), a larger limit only extends answers that would otherwise have been cut off; the 500 complete answers would not change. After the re-run, 14 answers were still invalid (13 from Qwen 3.5, 1 from Llama). These are not a limit problem: they are runaway lists of waypoints that never close, some creeping toward a point (5.0000001, 5.00000005, ...) until 1,500 tokens run out. A plan that never ends is unusable for a robot, so we count these as failures.

## 6. Problem: "the person's left" is confounded with "the map's left"
In the results, when the robot drives *toward* the person and is asked to describe its route in its own frame, the strongest models (Gemma 4, Qwen 3.5) almost always use the person's left instead. We checked by hand that the geometry is right: e.g. Gemma 4 drives along x = 1.5 (west of the table) while heading south, which is the robot's *right*, and says "I will pass to the left of the table".
But the person stands at the bottom of the map looking "up" (+y), so the person's left is also the left of the top-down map. The data cannot tell whether models take the **person's** perspective or simply the **map's** (fixed, allocentric) left, which is a common default in text descriptions of grid worlds. Next version: put the person on the side of the room (looking along +x), so that person-left, map-left and robot-left are all different.

## 7. A naming bug in the results table
The "sentence names a side at all" table printed its column as `c`. Renamed to `names_side`.

## 8. Version 2 removed our own confound
Adding a person at the top of the room separated the three frames. Result: models use map directions. A hint that
spells out which side is "left" helps only the newest models.

## 9. Version 3: fixes, and a launch false alarm
Three fixes were tested on the hardest setting. Rotating the scene into the speaker's view and check-and-repair both
reached 0.9-1.0 for the stronger models; reason-first was unreliable because models often state the wrong side.
Problem we hit: twice the run looked "stuck" at launch (no output, no model loaded). It was the first request loading
the model and producing a long answer, not a hang; restarting it was unnecessary. Lesson: check the server and the
open connection before assuming a freeze.
