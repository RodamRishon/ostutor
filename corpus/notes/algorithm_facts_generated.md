# Algorithm facts: per-algorithm aspects and all pairwise comparisons

## Per-algorithm aspects

### How does FCFS handle a newly arrived process?

A newly arrived process joins the tail of the ready queue and never interrupts the running process.

### What happens in FCFS when two processes have the same arrival time or priority?

If two processes arrive at the same time, the one that comes first in the process list (the lower process number) runs first.

### Does FCFS need to know the burst time in advance?

FCFS does not need to know burst times at all.

### How is FCFS implemented, and what data structure does it use?

FCFS needs only a simple FIFO queue: enqueue at the tail, dequeue from the head, so each decision takes constant time.

### What is the response time behaviour of FCFS?

In FCFS, the response time is equal to the waiting time, which can be very long when a long job is ahead (the convoy effect).

### What kind of system is FCFS best suited for?

FCFS is best suited to simple batch systems where jobs are not interactive and low overhead matters. Batch workloads with no interactivity requirement.

### Summarise FCFS in a few lines.

First Come First Served (FCFS) runs the ready process that arrived first, strictly in arrival order. It is non-preemptive: a running process keeps the CPU until it finishes or blocks for I/O. On starvation, it cannot starve any process, because every process eventually reaches the head of the FIFO queue. Its average waiting time is often long and very sensitive to the order of arrival, and its context-switch overhead is the lowest, because there is no preemption.

### What is the effect of FCFS on average waiting time?

The average waiting time under FCFS is often long and very sensitive to the order of arrival.

### What is the context-switch overhead of FCFS?

FCFS has the lowest, because there is no preemption context-switch overhead. It is non-preemptive: a running process keeps the CPU until it finishes or blocks for I/O.

### How does SJF handle a newly arrived process?

A newly arrived process, even a shorter one, must wait until the running process finishes its burst.

### What happens in SJF when two processes have the same arrival time or priority?

If two processes have the same burst time, the one that arrived earlier runs first, and then the one with the lower process number.

### Does SJF need to know the burst time in advance?

SJF needs the next CPU burst length in advance, which in practice must be predicted, for example with an exponential average of past bursts.

### How is SJF implemented, and what data structure does it use?

SJF can be implemented with a min-heap (priority queue) keyed on burst time, so each decision takes O(log n).

### What is the response time behaviour of SJF?

In SJF, the response time is equal to the waiting time; short jobs start quickly but a long job may wait a long time.

### What kind of system is SJF best suited for?

SJF is best suited to batch systems where run times are known or can be estimated well. Batch workloads with known or predictable run times, when low average waiting time matters.

### Summarise SJF in a few lines.

Shortest Job First (SJF, non-preemptive) picks, among the processes that have arrived, the one with the smallest burst time and runs it to completion. It is non-preemptive: once a process starts, it finishes its burst even if a shorter job arrives. On starvation, it can starve long jobs if shorter jobs keep arriving. Its average waiting time is the minimum among non-preemptive algorithms, and its context-switch overhead is low, because there is no preemption.

### What is the effect of SJF on average waiting time?

The average waiting time under SJF is the minimum among non-preemptive algorithms.

### What is the context-switch overhead of SJF?

SJF has low, because there is no preemption context-switch overhead. It is non-preemptive: once a process starts, it finishes its burst even if a shorter job arrives.

### How does SRTF handle a newly arrived process?

A newly arrived process preempts the running one if its burst is strictly less than the running process's remaining time; with an equal value the running process keeps the CPU.

### What happens in SRTF when two processes have the same arrival time or priority?

If remaining times are equal, the running process keeps the CPU; otherwise the one that arrived earlier, then the lower process number, runs.

### Does SRTF need to know the burst time in advance?

SRTF needs the burst lengths in advance, so they must be known or predicted.

### How is SRTF implemented, and what data structure does it use?

SRTF can be implemented with a min-heap keyed on remaining time that is re-evaluated at every arrival, so each decision takes O(log n).

### What is the response time behaviour of SRTF?

In SRTF, the response time is very good for short jobs, which start almost immediately, but poor for long ones.

### What kind of system is SRTF best suited for?

SRTF is best suited to systems where burst lengths can be estimated accurately and a low average waiting time is the main goal. Workloads with accurate burst estimates where the lowest average waiting time is the goal.

### Summarise SRTF in a few lines.

Shortest Remaining Time First (SRTF, preemptive SJF) always runs the arrived process with the smallest remaining burst time. It is preemptive: a newly arrived process with a shorter remaining time takes the CPU at once. On starvation, it can starve long jobs, even more easily than SJF, because a long job can also be preempted repeatedly. Its average waiting time is the lowest of all the standard algorithms, and its context-switch overhead is higher than SJF, because every preemption is a context switch.

### What is the effect of SRTF on average waiting time?

The average waiting time under SRTF is the lowest of all the standard algorithms.

### What is the context-switch overhead of SRTF?

SRTF has higher than SJF, because every preemption is a context switch context-switch overhead. It is preemptive: a newly arrived process with a shorter remaining time takes the CPU at once.

### How does non-preemptive Priority handle a newly arrived process?

A newly arrived process, even with a higher priority, waits until the running process finishes its burst.

### What happens in non-preemptive Priority when two processes have the same arrival time or priority?

Processes with equal priority are served in FCFS order: earlier arrival first, then the lower process number.

### Does non-preemptive Priority need to know the burst time in advance?

Priority scheduling needs a priority value for every process, but not the burst length.

### How is non-preemptive Priority implemented, and what data structure does it use?

Priority scheduling can be implemented with a priority queue (min-heap on the priority number), so each decision takes O(log n).

### What is the response time behaviour of non-preemptive Priority?

In non-preemptive Priority, the response time is equal to the waiting time; high-priority work starts first, low-priority work may wait a long time.

### What kind of system is non-preemptive Priority best suited for?

non-preemptive Priority is best suited to systems where processes differ in importance and switching must stay cheap. Systems where some processes are clearly more important than others.

### Summarise non-preemptive Priority in a few lines.

Priority scheduling (non-preemptive) picks, among the processes that have arrived, the one with the highest priority (the lowest priority number) and runs it to completion. It is non-preemptive: a higher-priority arrival waits until the running process finishes. On starvation, it can starve low-priority processes if higher-priority ones keep arriving, which aging fixes. Its average waiting time is not minimised; it depends on how the priorities are assigned, and its context-switch overhead is low, because there is no preemption.

### What is the effect of non-preemptive Priority on average waiting time?

The average waiting time under non-preemptive Priority is not minimised; it depends on how the priorities are assigned.

### What is the context-switch overhead of non-preemptive Priority?

non-preemptive Priority has low, because there is no preemption context-switch overhead. It is non-preemptive: a higher-priority arrival waits until the running process finishes.

### How does preemptive Priority handle a newly arrived process?

A newly arrived process preempts the running one only if its priority is strictly higher; an equal priority does not preempt.

### What happens in preemptive Priority when two processes have the same arrival time or priority?

Processes with equal priority are served in FCFS order, and an arrival with an equal priority does not preempt the running process.

### Does preemptive Priority need to know the burst time in advance?

Preemptive Priority scheduling needs a priority value for every process, but not the burst length.

### How is preemptive Priority implemented, and what data structure does it use?

Preemptive Priority scheduling can be implemented with a priority queue (min-heap on the priority number) that is re-checked at every arrival, so each decision takes O(log n).

### What is the response time behaviour of preemptive Priority?

In preemptive Priority, the response time is very good for high-priority processes and poor for low-priority ones.

### What kind of system is preemptive Priority best suited for?

preemptive Priority is best suited to systems with urgent processes that must run immediately, such as interactive or real-time work. Systems with urgent processes that must not wait.

### Summarise preemptive Priority in a few lines.

Priority scheduling (preemptive) always runs the arrived process with the highest priority (the lowest priority number). It is preemptive: a newly arrived process with a strictly higher priority takes the CPU immediately. On starvation, it can starve low-priority processes, which aging fixes. Its average waiting time is not minimised; it depends on how the priorities are assigned, and its context-switch overhead is higher than non-preemptive Priority, because every preemption is a context switch.

### What is the effect of preemptive Priority on average waiting time?

The average waiting time under preemptive Priority is not minimised; it depends on how the priorities are assigned.

### What is the context-switch overhead of preemptive Priority?

preemptive Priority has higher than non-preemptive Priority, because every preemption is a context switch context-switch overhead. It is preemptive: a newly arrived process with a strictly higher priority takes the CPU immediately.

### How does Round Robin handle a newly arrived process?

A newly arrived process joins the tail of the ready queue; if it arrives during a slice, it enters the queue before the preempted process is put back.

### What happens in Round Robin when two processes have the same arrival time or priority?

Processes that arrive at the same time enter the queue in process-number order, and a process that arrives exactly when a quantum expires enters the queue before the preempted process.

### Does Round Robin need to know the burst time in advance?

Round Robin does not need to know burst times; it needs a time quantum.

### How is Round Robin implemented, and what data structure does it use?

Round Robin needs a circular FIFO queue and a timer interrupt, so each decision takes constant time.

### What is the response time behaviour of Round Robin?

In Round Robin, the response time is short and predictable, because every process gets its first turn within (n − 1) × q time units.

### What kind of system is Round Robin best suited for?

Round Robin is best suited to time-sharing and interactive systems where every user needs regular turns. Interactive time-sharing systems.

### Summarise Round Robin in a few lines.

Round Robin (RR) serves a circular FIFO ready queue and gives each process at most one time quantum before moving it to the tail. It is preemptive: a timer interrupt takes the CPU when the quantum expires. On starvation, it cannot starve any process, because every process gets the CPU within (n − 1) × q time units. Its average waiting time is usually higher than SJF, but bounded for each turn, and its context-switch overhead is the highest, because it switches at every quantum expiry.

### What is the effect of Round Robin on average waiting time?

The average waiting time under Round Robin is usually higher than SJF, but bounded for each turn.

### What is the context-switch overhead of Round Robin?

Round Robin has the highest, because it switches at every quantum expiry context-switch overhead. It is preemptive: a timer interrupt takes the CPU when the quantum expires.

## All pairwise comparisons

### Compare FCFS and SJF in detail

FCFS and SJF differ in how they choose the next process and in what they cost. FCFS runs the ready process that arrived first, strictly in arrival order. SJF picks, among the processes that have arrived, the one with the smallest burst time and runs it to completion. Both are non-preemptive. On starvation, FCFS cannot starve any process, because every process eventually reaches the head of the FIFO queue, while SJF can starve long jobs if shorter jobs keep arriving. Average waiting time under FCFS is often long and very sensitive to the order of arrival, while under SJF it is the minimum among non-preemptive algorithms. For context-switch overhead, FCFS has the lowest, because there is no preemption, and SJF has low, because there is no preemption. Choose FCFS for simple batch systems where jobs are not interactive and low overhead matters; choose SJF for batch systems where run times are known or can be estimated well.

### Compare FCFS and SRTF in detail

FCFS and SRTF differ in how they choose the next process and in what they cost. FCFS runs the ready process that arrived first, strictly in arrival order. SRTF always runs the arrived process with the smallest remaining burst time. FCFS is non-preemptive, whereas SRTF is preemptive. On starvation, FCFS cannot starve any process, because every process eventually reaches the head of the FIFO queue, while SRTF can starve long jobs, even more easily than SJF, because a long job can also be preempted repeatedly. Average waiting time under FCFS is often long and very sensitive to the order of arrival, while under SRTF it is the lowest of all the standard algorithms. For context-switch overhead, FCFS has the lowest, because there is no preemption, and SRTF has higher than SJF, because every preemption is a context switch. Choose FCFS for simple batch systems where jobs are not interactive and low overhead matters; choose SRTF for systems where burst lengths can be estimated accurately and a low average waiting time is the main goal.

### Compare FCFS and non-preemptive Priority in detail

FCFS and non-preemptive Priority differ in how they choose the next process and in what they cost. FCFS runs the ready process that arrived first, strictly in arrival order. non-preemptive Priority picks, among the processes that have arrived, the one with the highest priority (the lowest priority number) and runs it to completion. Both are non-preemptive. On starvation, FCFS cannot starve any process, because every process eventually reaches the head of the FIFO queue, while non-preemptive Priority can starve low-priority processes if higher-priority ones keep arriving, which aging fixes. Average waiting time under FCFS is often long and very sensitive to the order of arrival, while under non-preemptive Priority it is not minimised; it depends on how the priorities are assigned. For context-switch overhead, FCFS has the lowest, because there is no preemption, and non-preemptive Priority has low, because there is no preemption. Choose FCFS for simple batch systems where jobs are not interactive and low overhead matters; choose non-preemptive Priority for systems where processes differ in importance and switching must stay cheap.

### Compare FCFS and preemptive Priority in detail

FCFS and preemptive Priority differ in how they choose the next process and in what they cost. FCFS runs the ready process that arrived first, strictly in arrival order. preemptive Priority always runs the arrived process with the highest priority (the lowest priority number). FCFS is non-preemptive, whereas preemptive Priority is preemptive. On starvation, FCFS cannot starve any process, because every process eventually reaches the head of the FIFO queue, while preemptive Priority can starve low-priority processes, which aging fixes. Average waiting time under FCFS is often long and very sensitive to the order of arrival, while under preemptive Priority it is not minimised; it depends on how the priorities are assigned. For context-switch overhead, FCFS has the lowest, because there is no preemption, and preemptive Priority has higher than non-preemptive Priority, because every preemption is a context switch. Choose FCFS for simple batch systems where jobs are not interactive and low overhead matters; choose preemptive Priority for systems with urgent processes that must run immediately, such as interactive or real-time work.

### Compare FCFS and Round Robin in detail

FCFS and Round Robin differ in how they choose the next process and in what they cost. FCFS runs the ready process that arrived first, strictly in arrival order. Round Robin serves a circular FIFO ready queue and gives each process at most one time quantum before moving it to the tail. FCFS is non-preemptive, whereas Round Robin is preemptive. On starvation, FCFS cannot starve any process, because every process eventually reaches the head of the FIFO queue, while Round Robin cannot starve any process, because every process gets the CPU within (n − 1) × q time units. Average waiting time under FCFS is often long and very sensitive to the order of arrival, while under Round Robin it is usually higher than SJF, but bounded for each turn. For context-switch overhead, FCFS has the lowest, because there is no preemption, and Round Robin has the highest, because it switches at every quantum expiry. Choose FCFS for simple batch systems where jobs are not interactive and low overhead matters; choose Round Robin for time-sharing and interactive systems where every user needs regular turns.

### Compare SJF and SRTF in detail

SJF and SRTF differ in how they choose the next process and in what they cost. SJF picks, among the processes that have arrived, the one with the smallest burst time and runs it to completion. SRTF always runs the arrived process with the smallest remaining burst time. SJF is non-preemptive, whereas SRTF is preemptive. On starvation, SJF can starve long jobs if shorter jobs keep arriving, while SRTF can starve long jobs, even more easily than SJF, because a long job can also be preempted repeatedly. Average waiting time under SJF is the minimum among non-preemptive algorithms, while under SRTF it is the lowest of all the standard algorithms. For context-switch overhead, SJF has low, because there is no preemption, and SRTF has higher than SJF, because every preemption is a context switch. Choose SJF for batch systems where run times are known or can be estimated well; choose SRTF for systems where burst lengths can be estimated accurately and a low average waiting time is the main goal.

### Compare SJF and non-preemptive Priority in detail

SJF and non-preemptive Priority differ in how they choose the next process and in what they cost. SJF picks, among the processes that have arrived, the one with the smallest burst time and runs it to completion. non-preemptive Priority picks, among the processes that have arrived, the one with the highest priority (the lowest priority number) and runs it to completion. Both are non-preemptive. On starvation, SJF can starve long jobs if shorter jobs keep arriving, while non-preemptive Priority can starve low-priority processes if higher-priority ones keep arriving, which aging fixes. Average waiting time under SJF is the minimum among non-preemptive algorithms, while under non-preemptive Priority it is not minimised; it depends on how the priorities are assigned. For context-switch overhead, SJF has low, because there is no preemption, and non-preemptive Priority has low, because there is no preemption. Choose SJF for batch systems where run times are known or can be estimated well; choose non-preemptive Priority for systems where processes differ in importance and switching must stay cheap.

### Compare SJF and preemptive Priority in detail

SJF and preemptive Priority differ in how they choose the next process and in what they cost. SJF picks, among the processes that have arrived, the one with the smallest burst time and runs it to completion. preemptive Priority always runs the arrived process with the highest priority (the lowest priority number). SJF is non-preemptive, whereas preemptive Priority is preemptive. On starvation, SJF can starve long jobs if shorter jobs keep arriving, while preemptive Priority can starve low-priority processes, which aging fixes. Average waiting time under SJF is the minimum among non-preemptive algorithms, while under preemptive Priority it is not minimised; it depends on how the priorities are assigned. For context-switch overhead, SJF has low, because there is no preemption, and preemptive Priority has higher than non-preemptive Priority, because every preemption is a context switch. Choose SJF for batch systems where run times are known or can be estimated well; choose preemptive Priority for systems with urgent processes that must run immediately, such as interactive or real-time work.

### Compare SJF and Round Robin in detail

SJF and Round Robin differ in how they choose the next process and in what they cost. SJF picks, among the processes that have arrived, the one with the smallest burst time and runs it to completion. Round Robin serves a circular FIFO ready queue and gives each process at most one time quantum before moving it to the tail. SJF is non-preemptive, whereas Round Robin is preemptive. On starvation, SJF can starve long jobs if shorter jobs keep arriving, while Round Robin cannot starve any process, because every process gets the CPU within (n − 1) × q time units. Average waiting time under SJF is the minimum among non-preemptive algorithms, while under Round Robin it is usually higher than SJF, but bounded for each turn. For context-switch overhead, SJF has low, because there is no preemption, and Round Robin has the highest, because it switches at every quantum expiry. Choose SJF for batch systems where run times are known or can be estimated well; choose Round Robin for time-sharing and interactive systems where every user needs regular turns.

### Compare SRTF and non-preemptive Priority in detail

SRTF and non-preemptive Priority differ in how they choose the next process and in what they cost. SRTF always runs the arrived process with the smallest remaining burst time. non-preemptive Priority picks, among the processes that have arrived, the one with the highest priority (the lowest priority number) and runs it to completion. SRTF is preemptive, whereas non-preemptive Priority is non-preemptive. On starvation, SRTF can starve long jobs, even more easily than SJF, because a long job can also be preempted repeatedly, while non-preemptive Priority can starve low-priority processes if higher-priority ones keep arriving, which aging fixes. Average waiting time under SRTF is the lowest of all the standard algorithms, while under non-preemptive Priority it is not minimised; it depends on how the priorities are assigned. For context-switch overhead, SRTF has higher than SJF, because every preemption is a context switch, and non-preemptive Priority has low, because there is no preemption. Choose SRTF for systems where burst lengths can be estimated accurately and a low average waiting time is the main goal; choose non-preemptive Priority for systems where processes differ in importance and switching must stay cheap.

### Compare SRTF and preemptive Priority in detail

SRTF and preemptive Priority differ in how they choose the next process and in what they cost. SRTF always runs the arrived process with the smallest remaining burst time. preemptive Priority always runs the arrived process with the highest priority (the lowest priority number). Both are preemptive. On starvation, SRTF can starve long jobs, even more easily than SJF, because a long job can also be preempted repeatedly, while preemptive Priority can starve low-priority processes, which aging fixes. Average waiting time under SRTF is the lowest of all the standard algorithms, while under preemptive Priority it is not minimised; it depends on how the priorities are assigned. For context-switch overhead, SRTF has higher than SJF, because every preemption is a context switch, and preemptive Priority has higher than non-preemptive Priority, because every preemption is a context switch. Choose SRTF for systems where burst lengths can be estimated accurately and a low average waiting time is the main goal; choose preemptive Priority for systems with urgent processes that must run immediately, such as interactive or real-time work.

### Compare SRTF and Round Robin in detail

SRTF and Round Robin differ in how they choose the next process and in what they cost. SRTF always runs the arrived process with the smallest remaining burst time. Round Robin serves a circular FIFO ready queue and gives each process at most one time quantum before moving it to the tail. Both are preemptive. On starvation, SRTF can starve long jobs, even more easily than SJF, because a long job can also be preempted repeatedly, while Round Robin cannot starve any process, because every process gets the CPU within (n − 1) × q time units. Average waiting time under SRTF is the lowest of all the standard algorithms, while under Round Robin it is usually higher than SJF, but bounded for each turn. For context-switch overhead, SRTF has higher than SJF, because every preemption is a context switch, and Round Robin has the highest, because it switches at every quantum expiry. Choose SRTF for systems where burst lengths can be estimated accurately and a low average waiting time is the main goal; choose Round Robin for time-sharing and interactive systems where every user needs regular turns.

### Compare non-preemptive Priority and preemptive Priority in detail

non-preemptive Priority and preemptive Priority differ in how they choose the next process and in what they cost. non-preemptive Priority picks, among the processes that have arrived, the one with the highest priority (the lowest priority number) and runs it to completion. preemptive Priority always runs the arrived process with the highest priority (the lowest priority number). non-preemptive Priority is non-preemptive, whereas preemptive Priority is preemptive. On starvation, non-preemptive Priority can starve low-priority processes if higher-priority ones keep arriving, which aging fixes, while preemptive Priority can starve low-priority processes, which aging fixes. Average waiting time under non-preemptive Priority is not minimised; it depends on how the priorities are assigned, while under preemptive Priority it is not minimised; it depends on how the priorities are assigned. For context-switch overhead, non-preemptive Priority has low, because there is no preemption, and preemptive Priority has higher than non-preemptive Priority, because every preemption is a context switch. Choose non-preemptive Priority for systems where processes differ in importance and switching must stay cheap; choose preemptive Priority for systems with urgent processes that must run immediately, such as interactive or real-time work.

### Compare non-preemptive Priority and Round Robin in detail

non-preemptive Priority and Round Robin differ in how they choose the next process and in what they cost. non-preemptive Priority picks, among the processes that have arrived, the one with the highest priority (the lowest priority number) and runs it to completion. Round Robin serves a circular FIFO ready queue and gives each process at most one time quantum before moving it to the tail. non-preemptive Priority is non-preemptive, whereas Round Robin is preemptive. On starvation, non-preemptive Priority can starve low-priority processes if higher-priority ones keep arriving, which aging fixes, while Round Robin cannot starve any process, because every process gets the CPU within (n − 1) × q time units. Average waiting time under non-preemptive Priority is not minimised; it depends on how the priorities are assigned, while under Round Robin it is usually higher than SJF, but bounded for each turn. For context-switch overhead, non-preemptive Priority has low, because there is no preemption, and Round Robin has the highest, because it switches at every quantum expiry. Choose non-preemptive Priority for systems where processes differ in importance and switching must stay cheap; choose Round Robin for time-sharing and interactive systems where every user needs regular turns.

### Compare preemptive Priority and Round Robin in detail

preemptive Priority and Round Robin differ in how they choose the next process and in what they cost. preemptive Priority always runs the arrived process with the highest priority (the lowest priority number). Round Robin serves a circular FIFO ready queue and gives each process at most one time quantum before moving it to the tail. Both are preemptive. On starvation, preemptive Priority can starve low-priority processes, which aging fixes, while Round Robin cannot starve any process, because every process gets the CPU within (n − 1) × q time units. Average waiting time under preemptive Priority is not minimised; it depends on how the priorities are assigned, while under Round Robin it is usually higher than SJF, but bounded for each turn. For context-switch overhead, preemptive Priority has higher than non-preemptive Priority, because every preemption is a context switch, and Round Robin has the highest, because it switches at every quantum expiry. Choose preemptive Priority for systems with urgent processes that must run immediately, such as interactive or real-time work; choose Round Robin for time-sharing and interactive systems where every user needs regular turns.
