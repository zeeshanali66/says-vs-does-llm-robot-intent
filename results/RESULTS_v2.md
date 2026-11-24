# Results: Says vs. Does, version 2

Outputs: 630 new (v2) + 270 reused from v1 (south pose, intent first). Invalid JSON (v2): 18

## Says = Does: sentence matches the plan in the requested frame

free = matches the robot's or the person's frame. Rows: requested frame, where the person stands, robot driving toward/away from the person.

```
model                       gemma3:12b  gemma4:12b  llama3.1:8b  qwen2.5:7b  qwen3.5:9b
frame       pose  relation                                                             
free        north away            0.20        0.00         0.17        0.00        0.00
                  toward          1.00        1.00         1.00        1.00        1.00
            south away            1.00        1.00         0.50        0.33        1.00
                  toward          1.00        1.00         1.00        1.00        1.00
person      north away            0.17        0.00         0.00        0.00        0.00
                  toward          0.12        0.11         0.25        0.00        0.00
            south away            0.71        1.00         0.86        1.00        1.00
                  toward          0.83        1.00         0.67        1.00        0.89
person_hint north away            0.00        0.44         0.00        0.00        0.40
                  toward          0.11        0.44         0.57        0.00        0.50
            south away            1.00        1.00         0.67        1.00        1.00
                  toward          1.00        1.00         0.33        1.00        1.00
robot       north away            0.29        0.00         0.20        0.00        0.00
                  toward          0.71        1.00         0.50        1.00        0.89
            south away            0.75        1.00         1.00        1.00        1.00
                  toward          0.25        0.00         0.33        0.00        0.00
robot_hint  north away            0.14        0.67         0.20        0.00        0.25
                  toward          0.80        1.00         0.33        0.33        1.00
            south away            1.00        1.00         1.00        0.50        1.00
                  toward          0.20        0.44         0.33        0.00        0.40
```

## Person at the north: which frame does the sentence match? (share of sentences)

north+away: robot and person agree, map differs. north+toward: robot and map agree, person differs.

```
                                  m_map  m_person  m_robot
model       frame       relation                          
gemma3:12b  free        away       0.80      0.20     0.20
                        toward     0.88      0.12     0.88
            person      away       0.83      0.17     0.17
                        toward     0.88      0.12     0.88
            person_hint away       1.00      0.00     0.00
                        toward     0.89      0.11     0.89
            robot       away       0.71      0.29     0.29
                        toward     0.71      0.29     0.71
            robot_hint  away       0.86      0.14     0.14
                        toward     0.80      0.20     0.80
gemma4:12b  free        away       1.00      0.00     0.00
                        toward     1.00      0.00     1.00
            person      away       1.00      0.00     0.00
                        toward     0.89      0.11     0.89
            person_hint away       0.56      0.44     0.44
                        toward     0.56      0.44     0.56
            robot       away       1.00      0.00     0.00
                        toward     1.00      0.00     1.00
            robot_hint  away       0.33      0.67     0.67
                        toward     1.00      0.00     1.00
llama3.1:8b free        away       0.83      0.17     0.17
                        toward     0.71      0.29     0.71
            person      away       1.00      0.00     0.00
                        toward     0.75      0.25     0.75
            person_hint away       1.00      0.00     0.00
                        toward     0.43      0.57     0.43
            robot       away       0.80      0.20     0.20
                        toward     0.50      0.50     0.50
            robot_hint  away       0.80      0.20     0.20
                        toward     0.33      0.67     0.33
qwen2.5:7b  free        away       1.00      0.00     0.00
                        toward     0.50      0.50     0.50
            person      away       1.00      0.00     0.00
                        toward     1.00      0.00     1.00
            person_hint away       1.00      0.00     0.00
                        toward     1.00      0.00     1.00
            robot       away       1.00      0.00     0.00
                        toward     1.00      0.00     1.00
            robot_hint  away       1.00      0.00     0.00
                        toward     0.33      0.67     0.33
qwen3.5:9b  free        away       1.00      0.00     0.00
                        toward     1.00      0.00     1.00
            person      away       1.00      0.00     0.00
                        toward     1.00      0.00     1.00
            person_hint away       0.60      0.40     0.40
                        toward     0.50      0.50     0.50
            robot       away       1.00      0.00     0.00
                        toward     0.89      0.11     0.89
            robot_hint  away       0.75      0.25     0.25
                        toward     1.00      0.00     1.00
```

## Does spelling out which side is 'left' fix it? (faithfulness, robot frame)



```
frame       robot       robot_hint      
pose        north south      north south
model                                   
gemma3:12b   0.50  0.58       0.42  0.56
gemma4:12b   0.50  0.50       0.83  0.72
llama3.1:8b  0.33  0.80       0.27  0.75
qwen2.5:7b   0.50  0.62       0.20  0.40
qwen3.5:9b   0.44  0.53       0.60  0.79
```

## Does spelling out which side is 'left' fix it? (faithfulness, person frame)



```
frame       person       person_hint      
pose         north south       north south
model                                     
gemma3:12b    0.14  0.77        0.07   1.0
gemma4:12b    0.06  1.00        0.44   1.0
llama3.1:8b   0.17  0.80        0.36   0.5
qwen2.5:7b    0.00  1.00        0.00   1.0
qwen3.5:9b    0.00  0.94        0.44   1.0
```

## Plan validity, v2 outputs



```
validity     hits_obstacle  hits_wall  leaves_room  misses_goal    ok
model                                                                
gemma3:12b            0.38       0.21         0.02         0.02  0.36
gemma4:12b            0.28       0.09         0.00         0.00  0.63
llama3.1:8b           0.59       0.02         0.00         0.37  0.02
qwen2.5:7b            0.92       0.00         0.00         0.06  0.02
qwen3.5:9b            0.30       0.18         0.06         0.17  0.30
```

## Sentence names a side, v2 outputs



```
             names_side
model                  
gemma3:12b         0.98
gemma4:12b         1.00
llama3.1:8b        0.95
qwen2.5:7b         0.97
qwen3.5:9b         0.75
```
