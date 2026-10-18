Priority scheduling is one of the most common scheduling algorithms used by the operating system to schedule processes based on their priority. Each process is assigned a priority value based on criteria such as memory requirements, time requirements, other resource needs, or the ratio of average I/O to average CPU burst time.

The process with the highest priority is selected for execution first. If there are multiple processes sharing the same priority, they are scheduled in the order they arrived, following a First-Come, First-Served approach. The chosen process is then executed, either until completion or until it is preempted, depending on whether the scheduling is preemptive or non-preemptive.

Priority Scheduling can be implemented in two ways:

- Non-Preemptive Priority Scheduling
- Preemptive Priority Scheduling

## Non-Preemptive Priority Scheduling

In Non-Preemptive Priority Scheduling, the CPU is not taken away from the running process. Even if a higher-priority process arrives, the currently running process will complete first.

Ex : A high-priority process must wait until the currently running process finishes.

### Example of Non-Preemptive Priority Scheduling:

Consider the following table of arrival time and burst time for three processes P1, P2 and P3:

Note: Lower number represents higher priority.

Process | Arrival Time | Burst Time | Priority
P1 | 0 | 4 | 2
P2 | 1 | 2 | 1
P3 | 2 | 6 | 3
Process

Arrival Time

Burst Time

Priority

- At Time 0: Only P1 has arrived. P1 starts execution as it is the only available process, and it will continue executing till t = 4 because it is a non-preemptive approach.
- At Time 4: P1 finishes execution. Both P2 and P3 have arrived. Since P2 has the highest priority (Priority 1), it is selected next.
- At Time 6: P2 finishes execution. The only remaining process is P3, so it starts execution.
- At Time 12: P3 finishes execution.
Gantt Chart:

Now, lets calculate average waiting time and turn around time:

Process | Arrival Time | Burst Time | Completion Time | Turnaround Time (CT - AT) | Waiting Time (TAT - BT)
P1 | 0 | 4 | 4 | 4 | 0
P2 | 1 | 2 | 6 | 5 | 3
P3 | 2 | 6 | 12 | 10 | 4
Completion Time

Turnaround Time (CT - AT)

Waiting Time (TAT - BT)

- Average Turnaround Time = 6.33
- Average Waiting Time = 2.33

## Code Implementation

- Program for Priority CPU Scheduling | Set 1
- Priority CPU Scheduling with different arrival time – Set 2

## Preemptive Priority Scheduling

In Preemptive Priority Scheduling , the CPU can be taken away from the currently running process if a new process with a higher priority arrives.

Ex: A low-priority process is running, and a high-priority process arrives; the CPU immediately switches to the high-priority process.

### Example of Preemptive Priority Scheduling (Same Arrival Time)

Note: Higher number represents higher priority.

Process | Arrival Time | Burst Time | Priority
P1 | 0 | 7 | 2
P2 | 0 | 4 | 1
P3 | 0 | 6 | 3
- At Time 0: All processes arrive at the same time. P3 has the highest priority (Priority 3), so it starts execution.
- At Time 6: P3 completes execution. Among the remaining processes, P1 (Priority 2) has a higher priority than P2 , so P1 starts execution.
- At Time 13: P1 completes execution. The only remaining process is P2 (Priority 1), so it starts execution.
- At Time 17: P2 completes execution. All processes are now finished.
Gant Chart:

Now, lets calculate average waiting time and turn around time :

Process | Arrival Time | Burst Time | Completion Time | Turnaround Time (CT - AT) | Waiting Time (TAT - BT)
P1 | 0 | 7 | 13 | 13 | 6
P2 | 0 | 4 | 17 | 17 | 13
P3 | 0 | 6 | 6 | 6 | 0
- Average Turnaround Time = 12
- Average Waiting Time = 6.33

### Example of Preemptive Priority Scheduling (Different Arrival Time)

Process | Arrival Time | Burst Time | Priority
P1 | 0 | 6 | 2
P2 | 1 | 4 | 3
P3 | 2 | 5 | 1
- At Time 0: Only P1 has arrived, so it starts execution.
- At Time 1: P2 arrives with a higher priority (Priority 3) than P1. P1 is preempted, and P2 starts execution.
- At Time 5: P2 completes execution. Both P1 and P3 are available. P1 has the higher priority (Priority 2), so it starts execution.
- At Time 10: P1 completes execution. P3 resumes execution to finish its remaining burst time.
- At Time 15: P3 completes execution. All processes are now finished.
Process | Arrival Time | Burst Time | Completion Time | Turnaround Time (CT - AT) | Waiting Time (TAT - BT)
P1 | 0 | 6 | 10 | 10 | 4
P2 | 1 | 4 | 5 | 4 | 0
P3 | 2 | 5 | 15 | 13 | 8
- Average Turnaround Time = 9
- Average Waiting Time = 4
