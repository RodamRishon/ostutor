# CPU Scheduling — Course Notes (Unit: CPU Scheduling)

Compiled for the OS CPU Scheduling Tutor. Conventions follow the prescribed textbook (Silberschatz, Galvin and Gagne, Operating System Concepts): a lower priority number means a higher priority, and ties are broken by arrival time and then by process number.

Basic concepts. CPU scheduling is the job of the short-term scheduler: whenever the CPU becomes idle it selects one process from the ready queue and the dispatcher gives that process control of the CPU. Process execution alternates between CPU bursts and I/O bursts, which is why scheduling is needed at all. Scheduling decisions happen when a process switches from running to waiting, from running to ready (an interrupt or a timer expiry), from waiting to ready, or when it terminates. If scheduling only happens on the first and last of these, the scheme is non-preemptive (cooperative); otherwise it is preemptive.

Dispatcher and dispatch latency. The dispatcher switches context, switches to user mode and jumps to the right location in the user program. The time the dispatcher takes to stop one process and start another is the dispatch latency. Every context switch is pure overhead: no useful user work is done while registers and the process control block are being saved and restored.

Scheduling criteria. CPU utilisation and throughput should be maximised. Turnaround time, waiting time and response time should be minimised. Turnaround time is the interval from arrival (submission) to completion: turnaround = completion time − arrival time. Waiting time is the total time a process spends in the ready queue: waiting = turnaround − burst time. Response time is the time from arrival until the process first gets the CPU: response = first start time − arrival time. For non-preemptive algorithms response time equals waiting time, because a process runs to completion once it starts.

How to solve a scheduling numerical. Step 1: list every process with its arrival time, burst time and priority. Step 2: simulate the algorithm on a time line, deciding at every scheduling point which ready process runs. Step 3: draw the Gantt chart, including idle gaps when no process has arrived. Step 4: read each completion time off the Gantt chart. Step 5: compute turnaround = completion − arrival, then waiting = turnaround − burst. Step 6: average each column. Most lost marks come from a wrong tie-break, from forgetting an idle gap, or from inserting a newly arrived process into the Round Robin queue in the wrong order.

## First Come First Served (FCFS)

FCFS is the simplest CPU scheduling algorithm: the process that requests the CPU first is allocated the CPU first. It is implemented with a FIFO queue. When a process enters the ready queue its PCB is linked onto the tail of the queue; when the CPU is free it is given to the process at the head. FCFS is non-preemptive: once a process has the CPU it keeps it until it terminates or requests I/O.

FCFS worked example. Processes P1, P2 and P3 arrive at time 0 in that order with burst times 24, 3 and 3. The Gantt chart is P1 from 0 to 24, P2 from 24 to 27, P3 from 27 to 30. Waiting times are P1 = 0, P2 = 24, P3 = 27, so the average waiting time is (0 + 24 + 27) / 3 = 17.00. If the same processes arrive in the order P2, P3, P1 the waiting times become 6, 0 and 3, and the average drops to 3.00. The average waiting time under FCFS is therefore generally not minimal and varies a lot with the order of arrival.

Convoy effect. Under FCFS all the short processes wait for one long process to get off the CPU, like cars stuck behind a slow truck. With one CPU-bound process and many I/O-bound processes, the I/O-bound processes finish their I/O and sit in the ready queue while the I/O devices go idle, then they all run quickly and go back to I/O while the CPU sits idle. The result is lower CPU and device utilisation. FCFS is particularly troublesome for time-sharing systems, where each user should get a share of the CPU at regular intervals.

## Shortest Job First (SJF) and Shortest Remaining Time First (SRTF)

SJF associates with each process the length of its next CPU burst and gives the CPU to the process with the smallest next burst. If two processes have the same burst length, FCFS order breaks the tie. SJF is provably optimal: it gives the minimum average waiting time for a given set of processes, because moving a short process before a long one decreases the short process's waiting time more than it increases the long one's.

SJF worked example. P1 = 6, P2 = 8, P3 = 7, P4 = 3, all arriving at time 0. SJF runs P4 (0–3), P1 (3–9), P3 (9–16), P2 (16–24). Waiting times are P1 = 3, P2 = 16, P3 = 9, P4 = 0, so the average waiting time is (3 + 16 + 9 + 0) / 4 = 7.00. FCFS on the same processes would give an average of 10.25.

Predicting the next CPU burst. The real difficulty with SJF is knowing the length of the next CPU request. The usual approach is to predict it as an exponential average of previous bursts: τ(n+1) = α·t(n) + (1 − α)·τ(n), where t(n) is the length of the most recent burst, τ(n) is the past prediction and 0 ≤ α ≤ 1, commonly α = 1/2. With α = 0 recent history has no effect; with α = 1 only the last burst counts.

Preemptive SJF is called Shortest Remaining Time First (SRTF). When a new process arrives with a next CPU burst shorter than what is left of the currently executing process, SRTF preempts the running process. Non-preemptive SJF lets the running process finish its burst.

SRTF worked example. P1 arrives at 0 with burst 8, P2 at 1 with burst 4, P3 at 2 with burst 9, P4 at 3 with burst 5. P1 starts at 0. At time 1 P2 arrives with burst 4, which is less than P1's remaining 7, so P1 is preempted. The Gantt chart is P1 (0–1), P2 (1–5), P4 (5–10), P1 (10–17), P3 (17–26). Waiting times: P1 = (10 − 1) = 9, P2 = 0, P3 = 15, P4 = 2. The average waiting time is (9 + 0 + 15 + 2) / 4 = 26 / 4 = 6.50. Non-preemptive SJF on the same data gives 7.75.

Starvation under SJF. A long process can wait indefinitely if short processes keep arriving, because there is always a shorter job to pick; this is starvation (indefinite blocking). SRTF makes it worse because a long job can also be preempted repeatedly.

## Priority Scheduling

A priority is associated with each process and the CPU is allocated to the process with the highest priority. Equal-priority processes are scheduled in FCFS order. In this course a lower number means higher priority, so priority 1 runs before priority 3. SJF is a special case of priority scheduling where the priority is the inverse of the predicted next CPU burst. Priority scheduling can be preemptive (a newly arrived higher-priority process takes the CPU immediately) or non-preemptive (the new process is put at the head of the ready queue).

Priority worked example. Five processes arrive at time 0: P1 burst 10 priority 3, P2 burst 1 priority 1, P3 burst 2 priority 4, P4 burst 1 priority 5, P5 burst 5 priority 2. The Gantt chart is P2 (0–1), P5 (1–6), P1 (6–16), P3 (16–18), P4 (18–19). Waiting times are P1 = 6, P2 = 0, P3 = 16, P4 = 18, P5 = 1, so the average waiting time is 41 / 5 = 8.20.

Starvation and aging. The major problem with priority scheduling is indefinite blocking, or starvation: a low-priority process can be left waiting forever while higher-priority processes keep arriving. The solution is aging: gradually increase the priority of processes that wait in the system for a long time, for example by improving the priority by 1 every 15 minutes, so that eventually even the lowest-priority process reaches the highest priority and runs.

## Round Robin (RR)

Round Robin is designed for time-sharing systems. It is similar to FCFS but adds preemption: a small unit of time called a time quantum or time slice, generally 10 to 100 milliseconds, is defined, and the ready queue is treated as a circular FIFO queue. The scheduler picks the first process, sets a timer to interrupt after one quantum and dispatches it. If the process has a burst shorter than the quantum it releases the CPU itself; otherwise the timer goes off, a context switch happens and the process is put at the tail of the ready queue.

Round Robin queue order rule. When a process arrives at the same moment that the running process's quantum expires, or during the slice, the newly arrived process is added to the ready queue before the preempted process is put back at the tail. Getting this order wrong is the most common error in RR numericals and changes every waiting time after that point.

Round Robin worked example. P1 = 24, P2 = 3, P3 = 3, all arriving at time 0, quantum 4. P1 runs 0–4 and goes to the back. P2 runs 4–7 and finishes, P3 runs 7–10 and finishes, then P1 runs alone from 10 to 30 in five more quanta. Waiting times are P1 = 10 − 4 = 6, P2 = 4, P3 = 7, so the average waiting time is 17 / 3 = 5.67.

Choosing the time quantum. Performance of RR depends heavily on the quantum. If the quantum is extremely large, RR becomes the same as FCFS. If it is extremely small, the system spends most of its time context switching, and each process appears to have its own processor running at 1/n speed (processor sharing). The quantum should be large compared with the context-switch time; a rule of thumb is that about 80 percent of CPU bursts should be shorter than the time quantum. RR typically gives higher average turnaround than SJF but better response time.

RR and starvation. Round Robin does not cause starvation. Every process in the ready queue gets the CPU within (n − 1) × q time units, where n is the number of processes and q is the quantum, so no process waits forever. The cost of this fairness is more context switches and therefore more overhead than FCFS or SJF.

Context-switch overhead in RR. Because RR preempts a process every quantum, it performs many more context switches than FCFS or SJF. With a quantum of 1 and a process of burst 10 there are 9 context switches for that one process; with a quantum of 12 there are none. Each switch saves and restores the CPU state in the PCB and may flush caches and the TLB, so a very small quantum wastes a large fraction of CPU time.

## Comparison summary

FCFS: non-preemptive, simple, no starvation, suffers from the convoy effect, poor average waiting time. SJF: non-preemptive, optimal average waiting time, needs burst prediction, long jobs can starve. SRTF: preemptive SJF, even lower average waiting time, more context switches, long jobs can starve. Priority: preemptive or non-preemptive, flexible, low-priority starvation fixed by aging. Round Robin: preemptive, fair, good response time, no starvation, performance depends on the quantum, higher context-switch overhead.

Multilevel queue and multilevel feedback queue. A multilevel queue partitions the ready queue into separate queues, for example foreground (interactive, RR) and background (batch, FCFS), each with its own algorithm and with scheduling between the queues. A multilevel feedback queue lets processes move between queues: a process that uses too much CPU time is moved to a lower-priority queue, and a process that waits too long in a lower queue is moved up, which is a form of aging that prevents starvation.
