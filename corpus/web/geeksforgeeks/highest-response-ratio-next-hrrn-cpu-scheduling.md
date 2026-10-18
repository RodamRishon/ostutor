CPU scheduling is the process of deciding which process will own the CPU to use while another process is suspended. The main function of CPU scheduling is to ensure that whenever the CPU remains idle, the OS has at least selected one of the processes available in the ready-to-use line. Highest Response Ratio Next (HRRN) Scheduling is a part of non-preemptive CPU scheduling.

## What is the Highest Response Ratio Next (HRRN) Scheduling?

One of the most optimal scheduling algorithms is the Highest Response Ratio Next (HRNN). This algorithm is a non-preemptive algorithm in which, HRRN scheduling is done based on an extra parameter, which is called Response Ratio. Given N processes with their Arrival times and Burst times, the task is to find the average waiting time and an average turnaround time using the HRRN scheduling algorithm.

The name itself states that we need to find the response ratio of all available processes and select the one with the highest Response Ratio. It is designed to improve upon simpler algorithms like First-Come-First-Serve (FCFS) and Shortest Job Next (SJN) by balancing both the waiting time and the burst time of processes. A process once selected will run till completion. below is the formula to calculate the Response Ratio.

Response Ratio = (W + S)/S W : Waiting time of the process so far S : Burst time of the process.

In HRRN, the process with the highest response ratio is selected for execution next. This approach gives priority to processes that have been waiting longer, but also considers the burst time, ensuring a fair balance between long-waiting and quick-execution processes.

## Characteristics of HRRN Scheduling

- Highest Response Ratio Next is a non-preemptive CPU Scheduling algorithm and it is considered as one of the most optimal scheduling algorithms.
- The criteria for HRRN is Response Ratio , and the mode is Non-Preemptive.
- HRRN is considered as the modification of the Shortest Job First to reduce the problem of starvation .
- In comparison with SJF, during the HRRN scheduling algorithm, the CPU is allotted to the next process which has the highest response ratio, and not to the process having less burst time.

## Performance of HRRN Scheduling

- Shorter Processes are favored.
- Aging without service increases the ratio, longer jobs can get past shorter jobs.

## Advantages of HRRN

- Fairness: HRRN provides fairness by considering both the waiting time and burst time of processes. It ensures that processes with longer waiting times are given priority, which helps prevent starvation.
- Better Response Time: Since HRRN prioritizes processes that have been waiting for a longer period, it can lead to better response times for these processes compared to simpler algorithms like FCFS.
- No Starvation: Unlike some other scheduling algorithms like Shortest Job First (SJF), HRRN reduces the risk of starvation. Even processes that need more CPU time will eventually get executed.
- Simple to Implement: The algorithm is easy to understand and implement since it only requires calculating the response ratio and selecting the process with the highest ratio.
- Dynamic Prioritization: The HRRN algorithm dynamically adjusts priorities meaning that processes which have been waiting longer (but are not necessarily the shortest jobs) will eventually be given higher priority.

## Disadvantages of HRRN

- HRRN is not practically feasible to implement the HRRN scheduling algorithm because we cannot predict the burst time of every process in advance.
- HRRN requires the calculation of the response ratio for each process, which adds some computational overhead, especially in systems with a large number of processes.

## Example of Highest Response Ratio Next (HRRN) Scheduling Algorithm

Process ID | Arrival Time | Burst Time | Completion Time (CT) | Turnaround Time (TAT) | Waiting Time (WT)
P1 | 0 | 5 | 5 | 5 | 0
P2 | 1 | 3 | 8 | 7 | 4
P4 | 3 | 6 | 14 | 11 | 5
P3 | 2 | 8 | 22 | 20 | 12
Average Turnaround Time (TAT) : Average TAT=TAT 1 +TAT 2 +TAT 3 +TAT 4 /4 = 5+7+11+20/4 = 43/4 = 10.75 Average Waiting Time (WT) : Average WT=WT 1 +WT 2 +WT 3 +WT 4 /4 = 0+4+5+12/4 = 21/4 = 5.25

Read about Program for HRRN CPU Scheduling Algorithm.

## Conclusion

The Highest Response Ratio Next (HRRN) scheduling algorithm works by giving priority to processes that have been waiting longer or require less CPU time. This method helps in reducing waiting times and ensures fairness by preventing starvation. Although it requires knowing the burst time in advance, HRRN is effective in improving overall system performance. It balances the needs of different processes, making it a good choice for scheduling in many scenarios.
