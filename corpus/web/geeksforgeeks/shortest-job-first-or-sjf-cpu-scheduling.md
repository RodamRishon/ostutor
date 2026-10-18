Shortest Job First (SJF) or Shortest Job Next (SJN) is a scheduling process that selects the waiting process with the smallest execution time to execute next. This scheduling method may or may not be preemptive. Significantly reduces the average waiting time for other processes waiting to be executed.

### Estimation Formula Concept in SJF Scheduling

The Shortest Job First (SJF) Scheduling algorithm selects the process with the smallest burst time for execution. But in some cases, the exact burst time of a process may not be known in advance. In such scenarios, an estimation formula is used to predict the next burst time based on the previous burst times.

Estimation Formula

T_{n+1} = \alpha \cdot t_n + (1 - \alpha) \cdot T_n

Where:

- T n+1 ​: Predicted burst time for the next process.
- T n : Previously predicted burst time.
- t n : Actual burst time of the previous process.
- α: Smoothing factor (0 ≤ α ≤ 1).

## Characteristics of SJF Scheduling

- Shortest Job first has the advantage of having a minimum average waiting time among all operating system scheduling algorithms.
- It is associated with each task as a unit of time to complete.
- It may cause starvation if shorter processes keep coming. This problem can be solved using the concept of ageing .
Example: Consider the following table of arrival time and burst time for three processes P1, P2 and P3 .

Process | Burst Time | Arrival Time
P1 | 6 ms | 0 ms
P2 | 8 ms | 2 ms
P3 | 3 ms | 4 ms
Step-by-Step Execution:

- Time 0-6 (P1) : P1 runs for 6 ms (total time left: 0 ms)
- Time 6-9 (P3) : P3 runs for 3 ms (total time left: 0 ms)
- Time 9-17 (P2) : P2 runs for 8 ms (total time left: 0 ms)
Gantt chart :

As we know,

- Turn Around time = Completion time - arrival time
- Waiting Time = Turn around time - burst time
Now, lets calculate average waiting time and turn around time:

Process | Arrival Time (AT) | Burst Time (BT) | Completion Time (CT) | Turn Around Time (TAT) | Waiting Time (WT)
P1 | 0 | 6 | 6 | 6-0 = 6 | 6-6 = 0
P2 | 2 | 8 | 17 | 17-2 = 15 | 15-8 = 7
P3 | 4 | 3 | 9 | 9-4 = 5 | 5-3 = 2
Arrival Time (AT)

Burst Time (BT)

- Average Turn around time = (6 + 15 + 5)/3 = 8.6 ms
- Average waiting time = ( 2 + 0 + 7 )/3 = 9/3 = 3 ms
To learn about Preemptive Shortest Job First or Shortest Remaining Time First , please refer the following

- Shortest Job First (Preemptive) or Shortest Remaining Time First
To learn about Non- Preemptive Shortest Job First , please refer the following

- Shortest Job First (Non-Preemptive).

## Implementation of SJF Scheduling

Step 1: Input number of processes and their burst times (arrival time too, if it’s non-preemptive with arrivals). Step 2: Sort processes by burst time (if same, use arrival order). Step 3: Start with the process having the shortest burst time. Step 4: Calculate Completion Time = Start Time + Burst Time. Step 5: Calculate Turnaround Time = Completion Time − Arrival Time. Step 6: Calculate Waiting Time = Turnaround Time − Burst Time. Step 7: Repeat until all processes are completed. Step 8: Compute average waiting time and turnaround time. Step 9: Display completion, waiting, and turnaround times for each process along with averages.

### Code Implementation

To learn about how to implement this CPU scheduling algorithm, please refer the following

- Program for Shortest Job First (or SJF) CPU Scheduling
- Shortest Job First (or SJF) CPU Scheduling Non-preemptive algorithm using Segment Tree

## Advantages of SJF Scheduling

- SJF is better than the First come first serve (FCFS) algorithm as it reduces the average waiting time.
- SJF is generally used for long term scheduling.
- It is suitable for the jobs running in batches, where run times are already known.
- SJF is probably optimal in terms of average Turn Around Time (TAT).

## Disadvantages of SJF Scheduling

- SJF may cause very long turn-around times or starvation .
- In SJF job completion time must be known earlier.
- Many times it becomes complicated to predict the length of the upcoming CPU request.
