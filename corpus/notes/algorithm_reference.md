# CPU Scheduling — Algorithm Reference

Conventions follow the prescribed textbook (Silberschatz, Galvin and Gagne): a lower priority number means a higher priority, ties are broken by arrival time and then by process number, waiting time = turnaround time − burst time, turnaround time = completion time − arrival time, response time = first start time − arrival time. Each answer below is written to stand alone.

## Basic concepts

### What is CPU scheduling?

CPU scheduling is the operating system's decision about which process in the ready queue gets the CPU next. Because a process alternates between CPU bursts and I/O bursts, the CPU would sit idle during I/O if nothing else could run. The scheduler keeps the CPU busy by switching to another ready process whenever the running one blocks, finishes, or is preempted. The goal is to maximise CPU utilisation and throughput while minimising waiting time, turnaround time and response time.

### What are the types of schedulers?

There are three types of schedulers: the long-term (job) scheduler, which admits jobs into memory and controls the degree of multiprogramming; the medium-term scheduler, which swaps processes out of and back into memory; and the short-term (CPU) scheduler, which chooses the next ready process to run and runs very often. FCFS, SJF, Priority and Round Robin are short-term (CPU) scheduling algorithms.

### What is the difference between the long-term, medium-term and short-term scheduler?

The long-term (job) scheduler decides which jobs are admitted into memory, so it controls the degree of multiprogramming. The short-term (CPU) scheduler decides which ready process runs on the CPU next and runs very frequently, so it must be fast. The medium-term scheduler swaps processes out of memory and back in to reduce the degree of multiprogramming. The algorithms FCFS, SJF, Priority and Round Robin are all short-term (CPU) scheduling algorithms.

### What is the difference between a CPU burst and an I/O burst?

A CPU burst is a stretch of time in which a process executes instructions on the CPU. An I/O burst is a stretch in which the process waits for an input or output operation to finish. A process alternates between the two until it terminates. The burst time used in scheduling numericals is the length of the CPU burst. Most real bursts are short, and a few are very long, which is why SJF-style prediction works reasonably well.

### What is the difference between CPU-bound and I/O-bound processes?

A CPU-bound process spends most of its time computing and has a few long CPU bursts. An I/O-bound process spends most of its time waiting for I/O and has many short CPU bursts. A good scheduler favours the I/O-bound processes slightly, because they need the CPU only briefly and then keep the I/O devices busy, which improves overall utilisation.

### What is the ready queue?

The ready queue holds all processes that are in memory, ready to run and waiting only for the CPU. It is usually a linked list of process control blocks. How it is ordered depends on the algorithm: arrival order for FCFS, burst length for SJF, priority for Priority scheduling and a circular FIFO order for Round Robin.

### What is the degree of multiprogramming?

The degree of multiprogramming is the number of processes held in memory at once, ready to compete for the CPU. The long-term scheduler controls it by deciding how many new jobs are admitted. Too low a degree leaves the CPU idle between bursts because there are not enough ready processes to switch to; too high a degree can exhaust memory or make each process wait too long for its turn. CPU scheduling algorithms such as FCFS, SJF, Priority and Round Robin operate on whichever processes the long-term scheduler has already admitted.

### What is throughput?

Throughput is the number of processes completed per unit of time. For example, 5 processes finishing in 20 time units give a throughput of 0.25 processes per time unit. Short jobs raise throughput; a long job lowers it. Throughput is one of the criteria to maximise.

### What is CPU utilisation and how is it calculated?

CPU utilisation is the percentage of time the CPU is busy running processes. In a Gantt chart it is the total time the CPU spends running processes divided by the total length of the chart, multiplied by 100. Idle gaps, when no process has arrived yet, reduce it. For example, if the CPU runs for 16 of 20 time units, the utilisation is 80 percent.

### How do you draw a Gantt chart?

A Gantt chart is a bar showing which process holds the CPU during each interval of time. To draw one, start at time 0 or at the first arrival; at every scheduling point choose the next process using the algorithm's rule; draw its box for the time it runs; write the start and end times under the box edges. If no process is ready, draw an idle box until the next arrival. The completion time of each process is the end of its last box.

### How do you calculate waiting time, turnaround time and response time from a Gantt chart?

Read the completion time of each process off the end of its last box on the chart. Turnaround time = completion time − arrival time. Waiting time = turnaround time − burst time. Response time = the start of the process's first box − its arrival time. Then average each column over all processes. An alternative for waiting time is to add up every interval the process spent ready but not running.

### What is the difference between waiting time and response time?

Waiting time is the total time a process spends in the ready queue over its whole life, including every time it was preempted and had to wait again. Response time is only the time from arrival until the first time the process gets the CPU. In non-preemptive algorithms the two are equal, because the process runs to completion once started. In preemptive algorithms such as Round Robin the waiting time is usually larger than the response time.

### What is the difference between turnaround time and waiting time?

Turnaround time is the total time from arrival to completion, so it includes waiting in the ready queue and actually running on the CPU. Waiting time counts only the time spent in the ready queue. Therefore turnaround time = waiting time + burst time, and turnaround time is always at least as large as waiting time.

### What are the scheduling criteria to maximise and to minimise?

Maximise CPU utilisation and throughput. Minimise turnaround time, waiting time and response time. In exams, the comparison between algorithms is usually made on average waiting time and average turnaround time. Some systems also care about fairness and about predictability of response time.

### Why do we need a ready queue and a dispatcher?

The ready queue stores the processes that can run, and the scheduler picks one from it. The dispatcher then actually gives the CPU to the chosen process by switching context, switching to user mode and jumping to the right place in the program. The scheduler decides, the dispatcher acts.

### What is preemptive scheduling?

In preemptive scheduling the operating system can take the CPU away from a running process before its burst is finished, for example when a timer interrupt fires or when a more urgent process arrives. Examples are Round Robin, SRTF and the preemptive version of Priority scheduling. Preemption improves response time, but it adds context-switch overhead and needs care when processes share data.

### What is non-preemptive scheduling?

In non-preemptive scheduling, once a process gets the CPU it keeps it until it finishes its burst or blocks for I/O; the scheduler makes a new decision only when the CPU becomes free. Examples are FCFS, SJF and the non-preemptive version of Priority scheduling. It has low overhead and is simple, but a long process can make everyone else wait.

## First Come First Served (FCFS)

### What is FCFS scheduling?

First Come First Served is the simplest CPU scheduling algorithm. The process that arrives first in the ready queue gets the CPU first and keeps it until it finishes or blocks for I/O. The ready queue is a plain FIFO queue: new processes join at the tail and the CPU is given to the process at the head. FCFS is non-preemptive.

### How does FCFS work step by step?

First, order the processes by arrival time, and by process number if arrival times are equal. Second, run the first process to completion. Third, when it finishes, take the next process from the head of the queue; if it has not arrived yet, the CPU idles until it does. Fourth, repeat until all are done. Finally compute completion, turnaround = completion − arrival and waiting = turnaround − burst for each process.

### What are the advantages of FCFS?

FCFS is very simple to understand and implement with a FIFO queue. It is fair in the sense that processes are served strictly in the order they arrive. It has no starvation, because every process eventually reaches the head of the queue. It has the lowest scheduling and context-switch overhead, because there is no preemption.

### What are the disadvantages of FCFS?

The average waiting time under FCFS is often long and depends heavily on the arrival order. A long process at the front makes every short process behind it wait, which is the convoy effect. FCFS is non-preemptive, so it gives poor response time and is unsuitable for interactive time-sharing systems. It also lowers CPU and I/O device utilisation when CPU-bound and I/O-bound processes are mixed.

### Is FCFS preemptive or non-preemptive?

FCFS is non-preemptive. Once a process is given the CPU it runs until it terminates or voluntarily blocks for I/O. The scheduler never takes the CPU away from it, even if a shorter process arrives.

### Does FCFS cause starvation?

No. FCFS cannot cause starvation, because the queue is served strictly in arrival order, so every process eventually reaches the head of the queue and gets the CPU. A process may wait a long time behind a long job, but it does not wait forever.

### How are ties broken in FCFS?

If two processes arrive at the same time, the one that appears first in the process list, usually the lower process number, is served first. For example, with P1 and P2 both arriving at time 0, P1 runs first.

### When is FCFS used?

FCFS is suitable for simple batch systems where the jobs are not interactive, where overhead must be minimal and where the order of arrival is an acceptable order of service. It is also used inside other schedulers, for example for processes of equal priority.

## Shortest Job First (SJF) and Shortest Remaining Time First (SRTF)

### What is SJF scheduling?

Shortest Job First schedules the ready process with the smallest next CPU burst. When the CPU becomes free, the scheduler looks only at the processes that have already arrived and picks the one with the shortest burst; ties are broken by arrival time. The basic version is non-preemptive. SJF is provably optimal in the sense that it gives the minimum average waiting time for a given set of processes.

### How does non-preemptive SJF work step by step?

Start at time 0 or at the first arrival. At each scheduling point, collect all the processes that have arrived and not finished. Pick the one with the smallest burst time; break ties by earlier arrival. Run it to completion, move the clock forward by its burst time, and repeat. If no process is ready, jump the clock to the next arrival and draw an idle gap.

### What are the advantages of SJF?

SJF gives the minimum average waiting time of any algorithm for a given set of processes, so it is optimal in that sense. It gives very good throughput because short jobs finish quickly. It reduces the convoy effect, since short processes are not stuck behind long ones.

### What are the disadvantages of SJF?

SJF needs to know the next CPU burst length in advance, which is impossible in general, so it must be predicted. It can starve long processes if short ones keep arriving. The non-preemptive version still lets a long job block a newly arrived short job once the long job has started. It is therefore hard to use as a pure short-term scheduler and is more often used as a model for comparison.

### Is SJF preemptive or non-preemptive?

The basic SJF algorithm is non-preemptive: once a process starts it runs to the end of its burst. The preemptive version is called Shortest Remaining Time First (SRTF), where a newly arrived process with a shorter burst than the remaining time of the running process takes the CPU.

### Does SJF cause starvation?

Yes. If shorter jobs keep arriving, a long job may be passed over again and again and never get the CPU. That is starvation, also called indefinite blocking. Aging, which gradually raises the priority of a waiting process, is the standard remedy.

### How are ties broken in SJF?

If two processes have the same burst time, the one that arrived earlier runs first; if they also arrived together, the one with the lower process number runs first. That is the same as applying FCFS between equal bursts.

### Why is SJF optimal?

Moving a short job ahead of a long job decreases the short job's waiting time by the long job's burst and increases the long job's waiting time by only the short job's burst. Since the short burst is smaller, the total waiting time decreases with every such swap. When no more swaps are possible the jobs are in order of increasing burst, which gives the minimum total and therefore the minimum average waiting time.

### Can SJF really be implemented?

Not exactly, because the scheduler does not know the length of the next CPU burst in advance. It can be approximated by predicting the next burst as an exponential average of the previous bursts: τ(n+1) = α·t(n) + (1 − α)·τ(n). In a batch system the user can state the time limit of the job and the system can use that instead.

### What is SRTF scheduling?

Shortest Remaining Time First is the preemptive version of SJF. Whenever a new process arrives, its burst is compared with the remaining time of the running process; if the new burst is strictly shorter, the running process is preempted and the new one runs. The preempted process returns to the ready queue with its remaining time. SRTF gives an even lower average waiting time than non-preemptive SJF.

### How does SRTF work step by step?

At every instant a process arrives or finishes, look at all the ready processes including the running one, and choose the one with the smallest remaining burst time. If it is a different process from the one running, preempt the running one. Draw the Gantt chart in pieces, recording each switch. Completion times come from the last piece of each process; then waiting = completion − arrival − burst.

### What are the advantages and disadvantages of SRTF?

Advantages: it gives the lowest possible average waiting time among the standard algorithms, and short jobs get a very fast response. Disadvantages: it needs the burst lengths in advance, it causes more context switches than SJF, and long processes can starve. A process that has been preempted must be resumed later, so the scheduler also has to keep track of remaining times.

### What is the difference between SJF and SRTF?

Both choose the process with the least CPU time, but SJF is non-preemptive and SRTF is preemptive. In SJF, once a process starts it finishes its burst even if a shorter process arrives. In SRTF, an arriving process with a shorter remaining time than the running process preempts it. SRTF gives a lower or equal average waiting time but needs more context switches.

## Priority scheduling

### What is Priority scheduling?

Priority scheduling assigns each process a priority number and always gives the CPU to the ready process with the highest priority. In this course a lower number means a higher priority, so priority 1 runs before priority 3. Processes with equal priority are served in FCFS order. It can be preemptive or non-preemptive.

### How does non-preemptive Priority scheduling work step by step?

At each scheduling point, collect the processes that have arrived and are not finished, choose the one with the highest priority (smallest number), break ties by arrival time and then process number, and run it to completion. A higher-priority process that arrives while another is running must wait until the running one finishes. Then repeat.

### How does preemptive Priority scheduling work step by step?

The scheduler always runs the highest-priority ready process. When a new process arrives with a strictly higher priority than the running one, the running process is preempted and goes back to the ready queue with its remaining time, and the new process runs. An arrival with equal priority does not preempt. Completion times are read off the pieces of the Gantt chart.

### How are ties broken in Priority scheduling?

If two ready processes have the same priority, the one that arrived earlier runs first; if they also arrived at the same time, the one given first in the process list (the lower process number) runs first. That is the same tie-break rule FCFS uses, applied within a priority level.

### Worked example: Priority scheduling with a tie in priority

P1 arrives at 0 with burst 4 and priority 2; P2 arrives at 0 with burst 3 and priority 2; P3 arrives at 1 with burst 2 and priority 1. At t=0, P1 and P2 are both ready with the best priority (2), so the tie is broken by process order: P1 runs first, 0 to 4. At t=4, P3 (priority 1, waiting since t=1) and P2 (priority 2) are ready, so P3 runs next, 4 to 6. P2 runs last, 6 to 9. Waiting times: P1 = 0, P2 = 9 − 3 = 6, P3 = 6 − 1 − 2 = 3, so the average waiting time is (0 + 6 + 3) / 3 = 3.00.

### What is the difference between preemptive and non-preemptive Priority scheduling?

In non-preemptive Priority scheduling, a newly arrived higher-priority process waits until the running process finishes its burst. In preemptive Priority scheduling it takes the CPU immediately and the running process is put back in the ready queue. Preemptive gives faster service to important work but causes more context switches; both can starve low-priority processes.

### How are priorities assigned?

Priorities can be defined internally or externally. Internal priorities are computed from measurable properties of the process, such as time limits, memory requirements, the number of open files and the ratio of average I/O burst to average CPU burst. External priorities come from outside the operating system, such as the importance of the process, the type or amount of funds being paid for computer use, or the department sponsoring the work. Priorities can be static (fixed) or dynamic (change over time).

### What are the advantages and disadvantages of Priority scheduling?

Advantages: important processes are served first, and the priority can be tuned to the needs of the system. SJF is itself a special case. Disadvantages: low-priority processes can starve, which is solved by aging; and a preemptive version adds context-switch overhead. Choosing good priorities is also not easy.

### Does Priority scheduling cause starvation?

Yes. A low-priority process can wait indefinitely if higher-priority processes keep arriving. This is indefinite blocking or starvation. The remedy is aging: gradually increasing the priority of processes that wait for a long time so that they eventually reach the highest priority.

### What is priority inversion?

Priority inversion happens when a high-priority process has to wait for a lock held by a low-priority process, and a medium-priority process preempts the low-priority one, so the high-priority process is delayed by an unrelated medium-priority process. It is solved by priority inheritance: the low-priority lock holder temporarily inherits the higher priority until it releases the lock.

### Is SJF a priority scheduling algorithm?

Yes. SJF is priority scheduling in which the priority is the inverse of the predicted next CPU burst: the shorter the burst, the higher the priority. It therefore also shares the starvation problem of priority scheduling.

## Round Robin (RR)

### What is Round Robin scheduling?

Round Robin is a preemptive algorithm designed for time-sharing systems. Each process is given a small unit of CPU time called the time quantum or time slice. The ready queue is a circular FIFO queue: the scheduler takes the process at the head, runs it for at most one quantum, and if it has not finished it is preempted and placed at the tail of the queue.

### How does Round Robin work step by step?

Put the processes in the ready queue in order of arrival. Take the process at the head. Run it for the time quantum or until it finishes, whichever is smaller. If processes arrived during that slice, add them to the queue first. If the running process still has work left, add it to the tail of the queue behind them; otherwise record its completion time. Repeat until the queue is empty.

### How do I order the queue in Round Robin when a process arrives at the same time as a quantum expires?

The newly arrived process goes into the ready queue before the preempted process is placed at the back. So if P3 arrives at exactly the moment P1's quantum ends, the queue becomes P3 followed by P1. This rule is a common source of mistakes in Round Robin numericals.

### Worked example: Round Robin with two arrivals exactly at a quantum expiry

P1 arrives at 0 with burst 6; P2 arrives at 3 with burst 2; P3 arrives at 3 with burst 4; quantum 3. P1 runs 0 to 3 and still has 3 units left. At t=3, P2 and P3 arrive at exactly the moment P1's quantum expires, so they join the queue before P1 goes to the back: the queue is now P2, P3, P1. P2 runs 3 to 5 and finishes (its burst of 2 is shorter than the quantum). P3 runs 5 to 8 and still has 1 unit left, so it goes to the back behind P1: queue is P1, P3. P1 runs 8 to 11 and finishes (its remaining 3 units exactly use one more quantum). P3 runs 11 to 12 and finishes. Waiting times: P1 = 11 − 0 − 6 = 5, P2 = 5 − 3 − 2 = 0, P3 = 12 − 3 − 4 = 5, so the average waiting time is (5 + 0 + 5) / 3 = 3.33.

### What are the advantages of Round Robin?

Round Robin is fair: every process gets the CPU in turn. It has no starvation, because every process reaches the head of the queue within a bounded time. It gives good response time, which suits interactive time-sharing systems. It is simple to implement with a circular queue and a timer.

### What are the disadvantages of Round Robin?

The performance depends heavily on the time quantum. Too small a quantum causes many context switches and wastes CPU time; too large a quantum makes it behave like FCFS. The average turnaround time is usually higher than in SJF, and the average waiting time is often higher too. There is more overhead than in the non-preemptive algorithms.

### What is the time quantum in Round Robin?

The time quantum, or time slice, is the maximum continuous CPU time a process may use before it is preempted and sent to the back of the ready queue. It is typically 10 to 100 milliseconds in real systems. In numericals it is given in time units, for example q = 4.

### How should the time quantum be chosen?

The quantum should be large compared with the context-switch time, so that switching is a small overhead, but small enough to give good response time. A common rule of thumb is that about 80 percent of the CPU bursts should be shorter than the quantum. If the quantum is infinite, Round Robin becomes FCFS; if it shrinks towards zero, each of the n processes appears to run on its own processor at 1/n of the speed (processor sharing).

### How does the time quantum affect context switches and overhead?

A smaller quantum means more context switches, because processes are preempted more often. If a context switch takes s time units and the quantum is q, the fraction of CPU time lost to switching is about s divided by (q + s). For example, with q = 4 and s = 1, 20 percent of the time is wasted. A larger quantum cuts the overhead but weakens the responsiveness.

### What happens in Round Robin if the time quantum is very large?

If the quantum is larger than the longest CPU burst, no process is ever preempted, so Round Robin behaves exactly like FCFS. It then has the convoy effect and poor response time.

### What happens in Round Robin if the time quantum is very small?

If the quantum is very small, the CPU spends most of its time switching between processes instead of doing useful work, so the throughput and the average turnaround time get worse. In the limit it approximates processor sharing, in which each process seems to run on its own slower processor.

### What is the maximum waiting time in Round Robin?

If there are n processes in the ready queue and the quantum is q, no process waits more than (n − 1) × q time units before its next turn. For example, with 5 processes and q = 4, a process gets the CPU again within 16 time units. This bound is why Round Robin gives predictable response time and has no starvation.

### Does Round Robin cause starvation?

No. Every process in the ready queue gets the CPU within (n − 1) × q time units, so no process waits forever. Round Robin is starvation-free; its drawback is overhead from context switches, not starvation.

### Is Round Robin preemptive or non-preemptive?

Round Robin is preemptive: a timer interrupt takes the CPU from the running process when its quantum expires, even though its burst is not finished.

### Give pseudocode for Round Robin scheduling.

Pseudocode: put all arrived processes in a FIFO queue; while the queue is not empty: remove the process at the head; run it for min(quantum, remaining time); advance the clock by that amount; enqueue any processes that arrived during this time; if the process still has remaining time, enqueue it at the tail, otherwise record completion time = clock; if the queue is empty but processes are still to arrive, advance the clock to the next arrival.

### Why does Round Robin give better response time than FCFS?

In FCFS a process may have to wait for every earlier process to run to completion before it first gets the CPU. In Round Robin each process gets its first turn within (n − 1) × q time units of reaching the queue. So response time is short and bounded, which suits interactive users. The price is a higher average turnaround time.

## Related and advanced algorithms

### What is Highest Response Ratio Next (HRRN)?

Highest Response Ratio Next is a non-preemptive algorithm that picks the ready process with the highest response ratio, where response ratio = (waiting time + burst time) / burst time. Short jobs have a high ratio at first, as in SJF, but the ratio of a waiting job keeps rising, so long jobs are eventually chosen. HRRN therefore avoids the starvation of SJF by using aging.

### What is a multilevel queue scheduler?

A multilevel queue scheduler splits the ready queue into several separate queues, such as foreground (interactive) and background (batch) processes. Each queue has its own scheduling algorithm, for example Round Robin for the foreground queue and FCFS for the background queue. There is also scheduling between the queues, either fixed priority or time slicing. A process stays in the queue it was assigned to.

### What is a multilevel feedback queue (MLFQ)?

A multilevel feedback queue is like a multilevel queue except that processes can move between queues based on their behaviour. A new process enters the top queue. A process that uses its full time allotment at a level moves down, so CPU-bound jobs sink to lower-priority queues. Interactive jobs that give up the CPU early stay high. Periodically all jobs may be boosted to the top queue to prevent starvation.

### What are the rules of MLFQ?

The standard rules are: if the priority of A is higher than B, A runs; if the priorities are equal, they run in Round Robin using the quantum of their queue; a new job enters the highest-priority queue; once a job uses up its time allotment at a level it moves down one queue; and after some period S all jobs are moved to the topmost queue (the priority boost), which prevents starvation and handles jobs whose behaviour changes.

### What is lottery scheduling?

Lottery scheduling is a proportional-share algorithm. Each process holds a number of tickets; at every scheduling decision a ticket is drawn at random and the process holding it runs. A process with more tickets is chosen more often, so over time each process receives CPU time roughly in proportion to its tickets. Stride scheduling is the deterministic version of the same idea.

### What is real-time scheduling, EDF and Rate Monotonic?

Real-time scheduling must meet deadlines. Earliest Deadline First (EDF) always runs the ready task with the nearest deadline and is optimal on a single processor when total utilisation is at most 100 percent. Rate Monotonic scheduling gives a fixed priority to each periodic task, higher for a shorter period, and is guaranteed to meet deadlines if the utilisation is below n(2^(1/n) − 1), which is about 69 percent for large n.

### What is multiprocessor scheduling?

Multiprocessor scheduling decides how ready processes are spread across more than one CPU. In symmetric multiprocessing (SMP) every processor runs the scheduler and picks from a shared ready queue, which needs locking to avoid two CPUs grabbing the same process. An alternative is asymmetric multiprocessing, where only one designated processor makes scheduling decisions and the rest execute user code, which is simpler but that one processor can become a bottleneck.

### What is processor affinity and why does it matter?

Processor affinity means a process is kept on the same CPU across repeated runs instead of being migrated to whichever CPU is free. Each run leaves useful data in that CPU's cache; moving the process to a different CPU invalidates that cache and the data must be reloaded, which costs time. Soft affinity is the scheduler's best effort to keep a process on the same CPU; hard affinity lets a process explicitly pin itself to a set of CPUs and never migrate off them.

### What is load balancing on a multiprocessor system?

Load balancing moves processes between the per-CPU ready queues of a multiprocessor system so that no CPU sits idle while another has a backlog. Push migration has a periodic task check the queues and push processes from a busy CPU to an idle one; pull migration has an idle CPU pull a waiting process from a busy one. Load balancing works against processor affinity, since moving a process to balance load also throws away its cache state, so real schedulers trade the two off.

### What is gang scheduling?

Gang scheduling runs a set of related threads or processes (a "gang") on a group of processors at the same time, and schedules and de-schedules them together. It suits parallel programs whose threads communicate and wait on each other, because those threads make no progress while some are running and others are waiting to be scheduled; running them simultaneously avoids that wasted waiting.

### How are threads scheduled?

Kernel-level threads are scheduled directly by the OS scheduler like any other schedulable unit. User-level threads are invisible to the OS and are scheduled onto kernel threads by a thread library using its own scheme, such as a simple Round Robin among the user threads of a process; the kernel only ever sees and schedules the underlying kernel thread(s). This two-level scheduling is why some thread libraries are described as having process-contention scope (user-level) versus system-contention scope (kernel-level).

### What does a real operating system like Linux use?

Linux's default scheduler is the Completely Fair Scheduler (CFS), which does not use fixed time quanta. It keeps a red-black tree of ready tasks keyed on "virtual runtime" (CPU time already received, scaled by priority/niceness) and always picks the task with the smallest virtual runtime, which approximates giving every task an equal share of the CPU over time. It is conceptually closer to Round Robin's fairness goal than to SJF or FCFS, but it is not one of the four algorithms used for the numericals in this course.

## Comparisons and choices

### Which scheduling algorithm gives the minimum average waiting time?

Shortest Job First gives the minimum average waiting time among non-preemptive algorithms, and Shortest Remaining Time First, its preemptive version, gives the minimum overall for processes with different arrival times. The catch is that both need to know the burst lengths in advance.

### Which scheduling algorithm gives the best response time?

Round Robin with a suitably small time quantum gives the best and most predictable response time, because every process gets a turn within (n − 1) × q time units. SRTF also gives very good response time to short jobs, but can make long ones wait.

### Which scheduling algorithm is the fairest?

Round Robin is the fairest in the sense that every process receives equal CPU time slices in turn and none starves. FCFS is fair in order of arrival but not in service quality. SJF and Priority scheduling can treat long or low-priority processes unfairly.

### Which scheduling algorithms can cause starvation?

SJF, SRTF and Priority scheduling can cause starvation: SJF and SRTF starve long jobs, and Priority scheduling starves low-priority processes. FCFS and Round Robin cannot, since every process eventually reaches the head of the queue. Aging fixes starvation in the first group.

### Which scheduling algorithms are preemptive and which are non-preemptive?

Non-preemptive: FCFS, SJF and Priority (non-preemptive version). Preemptive: SRTF (preemptive SJF), Round Robin and Priority (preemptive version). Multilevel feedback queues are preemptive too.

### Which scheduling algorithm is best for batch systems and which for interactive systems?

Batch systems care about throughput and turnaround time, so FCFS or SJF/SRTF are suitable. Interactive time-sharing systems care about response time, so Round Robin or a multilevel feedback queue is the better choice. Real-time systems use priority-based schemes such as EDF or Rate Monotonic.

### Compare FCFS, SJF, Priority and Round Robin in a table.

FCFS: non-preemptive, simple, no starvation, convoy effect, high average waiting time. SJF: non-preemptive, minimum average waiting time, needs burst prediction, starvation of long jobs. SRTF: preemptive, even lower average waiting time, more context switches, starvation. Priority: preemptive or non-preemptive, serves important work first, starvation of low priority solved by aging. Round Robin: preemptive, fair, good response time, no starvation, depends on the quantum, more overhead.

### Why is preemptive scheduling needed?

Without preemption, one long or never-ending process could keep the CPU forever and the system would not respond to anyone else. Preemption lets the operating system regain control through the timer interrupt, gives interactive users good response time, and lets urgent processes run immediately. The cost is context-switch overhead and the need to protect shared data from being interrupted midway.

### How many context switches does a scheduling algorithm cause?

In a non-preemptive algorithm a switch happens only when a process finishes or blocks, so for n processes there are about n − 1 switches. A preemptive algorithm adds a switch at every preemption. In Round Robin a process with burst b and quantum q is interrupted about ⌈b/q⌉ − 1 times. The more preemptions, the larger the overhead.

### What is the convoy effect and which algorithm suffers from it?

The convoy effect happens in FCFS when a long CPU-bound process holds the CPU and many short processes wait behind it, like cars behind a slow truck. The short processes could have finished quickly, but they wait, so the average waiting time rises and I/O devices sit idle. SJF and Round Robin avoid it because short jobs do not wait for the long job to finish.

## Formulas and exam methods

### What is the formula for waiting time?

Waiting time = turnaround time − burst time, which is the same as completion time − arrival time − burst time. It is the total time a process spends in the ready queue. For example, a process that arrives at 2, has burst 5 and completes at 12 has turnaround time 12 − 2 = 10 and waiting time 10 − 5 = 5. Never subtract a constant such as 1.

### What is the formula for turnaround time?

Turnaround time = completion time − arrival time. It is also equal to waiting time + burst time. It is the total time from the moment the process arrives until it finishes.

### What is the formula for response time?

Response time = time of the first start on the CPU − arrival time. It measures how long a process waits before it first gets the CPU. In non-preemptive algorithms it equals the waiting time.

### What is the formula for completion time?

For a non-preemptive algorithm, completion time = start time + burst time. For a preemptive algorithm such as Round Robin or SRTF, read the completion time from the Gantt chart: it is the end of the last box of that process.

### What is the formula for average waiting time and average turnaround time?

Average waiting time = (sum of the waiting times of all processes) / n, where n is the number of processes. Average turnaround time = (sum of the turnaround times of all processes) / n. Compute each process's own time first, then add them up and divide.

### How do I compute waiting time in FCFS?

Draw the FCFS Gantt chart, running processes in order of arrival. Because FCFS is non-preemptive, each process runs once without interruption, so waiting time = start time − arrival time, which is equal to completion time − arrival time − burst time. For example, if P2 arrives at 0 and starts at 24, its waiting time is 24.

### How do I compute waiting time in SJF?

Draw the non-preemptive SJF Gantt chart: at each scheduling point run the arrived process with the shortest burst. Then for each process, waiting time = turnaround time − burst time, where turnaround time = completion time − arrival time. Since a process in non-preemptive SJF is never interrupted, this is also start time − arrival time. Average the results over all processes.

### How do I compute waiting time in SRTF or any preemptive algorithm?

Draw the Gantt chart with every preemption. A preempted process waits more than once, so do not use start time − arrival time. Use waiting time = completion time − arrival time − burst time, where the completion time is the end of the process's last box on the chart. Equivalently, add up every interval during which the process was ready but not running.

### How do I compute waiting time in Round Robin?

Draw the Round Robin Gantt chart using the quantum and the queue rule that new arrivals join the queue before the preempted process. Then waiting time = completion time − arrival time − burst time for each process, because a process is preempted and waits several times. Average the values at the end.

### How do I compute waiting time in Priority scheduling?

Draw the Gantt chart choosing the ready process with the highest priority (smallest number) each time, preempting only if the version is preemptive. Then waiting time = completion time − arrival time − burst time. For the non-preemptive version this equals start time − arrival time.

### What is the formula for CPU utilisation and throughput?

CPU utilisation = (time the CPU is busy running processes / total elapsed time) × 100 percent, so idle gaps lower it. Throughput = number of processes completed / total elapsed time. For example, 5 processes finished in 20 time units give a throughput of 0.25 processes per time unit.

### What is the formula for the response ratio in HRRN?

Response ratio = (waiting time + burst time) / burst time. HRRN runs the ready process with the highest response ratio. The ratio grows as a process waits, so long jobs are not starved.

### What is the formula for the exponential average used to predict the next CPU burst?

τ(n+1) = α·t(n) + (1 − α)·τ(n), where t(n) is the length of the most recent actual CPU burst, τ(n) is the previous prediction, and α is a weight between 0 and 1, commonly 1/2. With α = 0 the prediction never changes; with α = 1 only the last burst counts.

### What is the formula for the context-switch overhead in Round Robin?

If one context switch takes s time units and the time quantum is q, the fraction of CPU time lost to switching is about s / (q + s). For example, q = 4 and s = 1 waste 1/5 = 20 percent of the time. A larger quantum lowers the overhead.

## Optimality claims

### Is SRTF optimal?

Yes, for average waiting time. When the burst lengths and arrival times are known in advance, Shortest Remaining Time First gives the minimum possible average waiting time, so it is provably optimal on that measure. It is not optimal for fairness: long jobs can starve, and it causes many context switches. In real systems the burst lengths have to be predicted, so SRTF is approximated rather than achieved exactly.

### Is SJF optimal?

Yes, for average waiting time when the burst lengths are known: Shortest Job First gives the minimum average waiting time for a set of processes that are available together, and it is a very good choice otherwise. With staggered arrivals the preemptive version, SRTF, can do even better. SJF is not optimal for fairness, because long jobs can starve.

### Is Round Robin optimal?

No. Round Robin is not optimal for average waiting time or turnaround time, because SJF and SRTF beat it on both. It is chosen for fairness and good response time in time-sharing systems, not for the lowest waiting time.

### Is FCFS optimal?

No. FCFS is generally not optimal for average waiting time, because a long job at the front delays every short job behind it (the convoy effect). It is optimal only in the special case where the processes happen to arrive in order of increasing burst time.

### Can Priority scheduling and other non-preemptive algorithms suffer from the convoy effect?

The convoy effect is classically described for FCFS, but any non-preemptive algorithm can show it. In non-preemptive Priority scheduling, once a long process has the CPU, every process behind it, even a newly arrived higher-priority one, must wait until it finishes. Preemptive Priority scheduling avoids this for higher-priority arrivals, because they take the CPU at once, although short low-priority jobs can still be held up. SJF reduces the convoy effect by running short jobs first, and Round Robin avoids it by limiting each turn to one quantum.

## Advantages and disadvantages of related algorithms

### What are the advantages and disadvantages of multilevel queue scheduling?

Advantages: processes of different kinds (system, interactive, batch) are kept in separate queues, and each queue can use the algorithm that suits it, for example Round Robin for interactive work and FCFS for batch work. Because the priorities between queues are fixed, the behaviour is easy to predict, and interactive or system processes get fast response while critical work is not stuck behind batch jobs. Disadvantages: with fixed priorities between queues, the lower queues can starve if the higher ones are always busy. A process cannot move to another queue, so a process that is placed badly, or whose behaviour changes, stays in the wrong queue. It also needs more bookkeeping than a single queue, and the designer has to choose the queues and the rule between them.

### What are the advantages and disadvantages of multilevel feedback queue scheduling?

Advantages: it adapts to how each process behaves, because a process that uses its whole time slice moves down while one that gives up the CPU early stays high. This favours short and I/O-bound interactive jobs and gives good response time. It does not need the burst times in advance, and an aging rule or periodic priority boost stops low queues from starving. Disadvantages: it is the most complex scheduler to set up, because the number of queues, the quantum of each queue and the rules for moving between queues all have to be chosen. It has more overhead than a single queue, and it can be gamed by a process that gives up the CPU just before its quantum ends to stay in a high queue. Without a boost, low-priority processes can still starve.

### What are the advantages and disadvantages of HRRN scheduling?

Advantages: Highest Response Ratio Next is fair, because the response ratio of a waiting process keeps rising, so long jobs are eventually chosen and nothing starves. It still favours short jobs, which have a high ratio at first, and its rule is simple to state. It is non-preemptive, so it does not add context-switch overhead. Disadvantages: it needs the burst time of every process in advance, which in practice has to be predicted. The ratio of every ready process must be recalculated at each scheduling decision, which adds overhead when many processes are waiting. Being non-preemptive, a long job that has started still blocks newcomers, and it does not give the minimum average waiting time, which SJF and SRTF do.
