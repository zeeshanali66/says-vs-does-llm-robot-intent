# Results: Says vs. Does

Total outputs: 540; invalid JSON: 14

## Plan validity (share of outputs)



```
validity     hits_obstacle  hits_wall  leaves_room  misses_goal    ok
model                                                                
gemma3:12b            0.44       0.27         0.02         0.03  0.25
gemma4:12b            0.38       0.08         0.00         0.00  0.54
llama3.1:8b           0.67       0.00         0.00         0.33  0.00
qwen2.5:7b            0.73       0.01         0.00         0.24  0.02
qwen3.5:9b            0.34       0.20         0.15         0.15  0.17
```

## Forced scenes: plan takes the open side



```
            took_open_side
model                     
gemma3:12b            0.31
gemma4:12b            0.88
llama3.1:8b           0.14
qwen2.5:7b            0.07
qwen3.5:9b            0.33
```

## Which frame does the sentence use? (requested frame x direction)

away: robot and person frames agree; toward: they swap. 'neither' = the sentence names the side the plan does NOT take in either frame.

```
sentence_frame                both  neither  person  robot  undefined
model       frame  direction                                         
gemma3:12b  free   away       0.71     0.00    0.00   0.00       0.29
                   toward     0.00     0.00    0.59   0.00       0.41
            person away       0.65     0.12    0.00   0.00       0.24
                   toward     0.00     0.00    0.59   0.06       0.35
            robot  away       0.61     0.22    0.00   0.00       0.17
                   toward     0.00     0.00    0.44   0.17       0.39
gemma4:12b  free   away       1.00     0.00    0.00   0.00       0.00
                   toward     0.00     0.00    1.00   0.00       0.00
            person away       1.00     0.00    0.00   0.00       0.00
                   toward     0.00     0.00    0.89   0.11       0.00
            robot  away       1.00     0.00    0.00   0.00       0.00
                   toward     0.00     0.00    1.00   0.00       0.00
llama3.1:8b free   away       0.44     0.22    0.00   0.00       0.33
                   toward     0.00     0.00    0.17   0.11       0.72
            person away       0.50     0.22    0.00   0.00       0.28
                   toward     0.00     0.00    0.11   0.06       0.83
            robot  away       0.44     0.11    0.00   0.00       0.44
                   toward     0.00     0.00    0.12   0.06       0.82
qwen2.5:7b  free   away       0.06     0.11    0.00   0.00       0.83
                   toward     0.00     0.00    0.28   0.00       0.72
            person away       0.17     0.22    0.00   0.00       0.61
                   toward     0.00     0.00    0.17   0.00       0.83
            robot  away       0.33     0.06    0.00   0.00       0.61
                   toward     0.00     0.00    0.22   0.00       0.78
qwen3.5:9b  free   away       0.87     0.00    0.00   0.00       0.13
                   toward     0.00     0.00    0.60   0.20       0.20
            person away       0.81     0.00    0.00   0.00       0.19
                   toward     0.00     0.00    0.88   0.06       0.06
            robot  away       0.85     0.00    0.00   0.00       0.15
                   toward     0.00     0.00    0.80   0.07       0.13
```

## Says = Does: sentence faithful to the plan in the requested frame



```
frame        free        person        robot       
direction    away toward   away toward  away toward
model                                              
gemma3:12b   0.71   0.59   0.65   0.59  0.61   0.17
gemma4:12b   1.00   1.00   1.00   0.89  1.00   0.00
llama3.1:8b  0.44   0.28   0.50   0.11  0.44   0.06
qwen2.5:7b   0.06   0.28   0.17   0.17  0.33   0.00
qwen3.5:9b   0.87   0.80   0.81   0.88  0.85   0.07
```

## Order effect: faithfulness when the intent is written before vs after the plan



```
order        intent_first  plan_first
model                                
gemma3:12b           0.59        0.51
gemma4:12b           0.83        0.80
llama3.1:8b          0.45        0.17
qwen2.5:7b           0.28        0.06
qwen3.5:9b           0.72        0.70
```

## AR arrow points to the same side the plan takes



```
            arrow_matches_plan
model                         
gemma3:12b                 1.0
gemma4:12b                 1.0
llama3.1:8b               0.91
qwen2.5:7b                 1.0
qwen3.5:9b                0.91
```

## Sentence names a side at all



```
             names_side
model                  
gemma3:12b         0.96
gemma4:12b         1.00
llama3.1:8b        0.99
qwen2.5:7b         1.00
qwen3.5:9b         0.84
```
