The pre-emptive version of Shortest Job First (SJF) scheduling is called Shortest Remaining Time First (SRTF). In SRTF, the process with the least time left to finish is selected to run. The running process continues until it finishes or a new process with a shorter remaining time arrives, ensuring the fastest finishing process always gets priority.

## Example of SJF Algorithm:

### Scenario 1: Processes with Same Arrival Time

Example: Consider the following table of arrival time and burst time for three processes P1, P2 and P3 .

Process | Burst Time | Arrival Time
P1 | 6 ms | 0 ms
P2 | 8 ms | 0 ms
P3 | 5 ms | 0 ms
Step-by-Step Execution:

- Time 0-5 (P3) : P3 runs for 5 ms (total time left: 0 ms) as it has shortest remaining time left.
- Time 5-11 (P1) : P1 runs for 6 ms (total time left: 0 ms) as it has shortest remaining time left.
- Time 11-19 (P2) : P2 runs for 8 ms (total time left: 0 ms) as it has shortest remaining time left.
Gantt chart :

Now, lets calculate average waiting time and turn around time:

As we know,

- Turn Around time = Completion time - arrival time
- Waiting Time = Turn around time - burst time
Process | Arrival Time (AT) | Burst Time (BT) | Completion Time (CT) | Turn Around Time (TAT) | Waiting Time (WT)
P1 | 0 | 6 | 11 | 11-0 = 11 | 11-6 = 5
P2 | 0 | 8 | 19 | 19-0 = 19 | 19-8 = 11
P3 | 0 | 5 | 5 | 5-0 = 5 | 5-5 = 0
Arrival Time

(AT)

Burst Time

(BT)

Now,

- Average Turn around time = (11 + 19 + 5)/3 = 11.6 ms
- Average waiting time = (5 + 0 + 11 )/3 = 16/3 = 5.33 ms

### Scenario 2: Processes with Different Arrival Times

Consider the following table of arrival time and burst time for three processes P1, P2 and P3.

Process | Burst Time | Arrival Time
P1 | 6 ms | 0 ms
P2 | 3 ms | 1 ms
P3 | 7 ms | 2 ms
- Time 0-1 (P1) : P1 runs for 1 ms (total time left: 5 ms) as it has shortest remaining time left.
- Time 1-4 (P2) : P2 runs for 3 ms (total time left: 0 ms) as it has shortest remaining time left among P1 and P2.
- Time 4-9 (P1) : P1 runs for 5 ms (total time left: 0 ms) as it has shortest remaining time left among P1 and P3.
- Time 9-16 (P3) : P3 runs for 7 ms (total time left: 0 ms) as it has shortest remaining time left.
Process | Arrival Time (AT) | Burst Time (BT) | Completion Time (CT) | Turn Around Time (TAT) | Waiting Time (WT)
P1 | 0 | 6 | 9 | 9-0 = 9 | 9-6 = 3
P2 | 1 | 3 | 4 | 4-1 = 3 | 3-3 = 0
P3 | 2 | 7 | 16 | 16-2 = 14 | 14-7 = 7
Arrival Time (AT)

Burst Time (BT)

- Average Turn around time = (9 + 14 + 3)/3 = 8.6 ms
- Average waiting time = (3 + 0 + 7 )/3 = 10/3 = 3.33 ms

## Implementation of SRTF Algorithm

Step 1: Input number of processes with arrival time and burst time. Step 2: Initialize remaining times (burst times), current time = 0, and counters. Step 3: At each time unit, add processes that have arrived into the ready queue. Step 4: Select the process with the shortest remaining time (preempt if a shorter one arrives). Step 5: Execute the selected process for 1 unit, reduce its remaining time, and increment current time. Step 6: If a process completes:

- Turnaround Time = Completion Time − Arrival Time
- Waiting Time = Turnaround Time − Burst Time
Step 7: Repeat Steps 3–6 until all processes complete. Step 8: Calculate average waiting time and turnaround time. Step 9: Display completion, waiting, and turnaround times for each process, along with averages.

### Code Implementation

Program to implement Shortest Remaining Time First is as follows:

Advantages of SRTF Scheduling

- Minimizes average waiting time by always selecting the process with the shortest remaining time.
- Short processes finish quickly, improving system responsiveness and throughput.
- Helps time-critical tasks get CPU attention earlier than longer jobs.
Disadvantages of SRTF Scheduling

- Long processes may suffer starvation if short jobs keep arriving continuously.
- Accurate prediction of CPU burst time is difficult and often unreliable.
- Frequent context switching increases overhead and can reduce overall performance.
