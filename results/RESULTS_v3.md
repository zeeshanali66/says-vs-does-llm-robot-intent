# Results: Says vs. Does, version 3 (fixes)

Person at the north. Share of intent sentences that name the side the plan really takes, in the requested frame.
none/hint come from version 2. Unnamed side or invalid JSON counts as not faithful.

```
fix                none (v2)  hint (v2)  reason_first  ego_coords  repair
model      frame                                                         
gemma3:12b person       0.11       0.06          0.22        0.50    0.78
           robot        0.39       0.28          0.50        0.67    0.78
gemma4:12b person       0.06       0.44          0.94        1.00    0.94
           robot        0.50       0.83          0.61        1.00    0.72
qwen3.5:9b person       0.00       0.22          0.06        0.89    1.00
           robot        0.44       0.50          0.44        0.94    1.00
```

## By frame and direction (all 3 models)

```
fix              ego_coords  hint (v2)  none (v2)  reason_first  repair
frame  relation                                                        
person away            0.89       0.22       0.04          0.48    0.85
       toward          0.70       0.26       0.07          0.33    0.96
robot  away            0.93       0.33       0.07          0.30    0.74
       toward          0.81       0.74       0.81          0.74    0.93
```

## Repair

Answers wrong before repair: 80 of 107; fixed by one round of feedback: 66 (82%).

## Reason-first: is the model's stated 'left' correct?

The checker compares the stated side (smaller/larger x) with the true left side in the requested view.

```
model       frame 
gemma3:12b  person    0.00
            robot     0.50
gemma4:12b  person    1.00
            robot     0.50
qwen3.5:9b  person    0.94
            robot     0.39
```
