# CPU Scheduling — Fundamentals, Queues and Complexity

Conventions used throughout this course and in the simulator: a lower priority number means a higher priority; turnaround time = completion time − arrival time; waiting time = turnaround time − burst time; response time = first time on the CPU − arrival time; a context switch is assumed to take zero time unless a question says otherwise.

### What is a process?

A process is a program in execution: the program's code together with its current activity, which includes the program counter, the registers, the stack and the data. A program is a passive file on disk; a process is the active entity that the operating system creates, schedules and eventually terminates. The operating system keeps each process's information in a process control block (PCB). In a CPU scheduling problem a process is described by an arrival time, a CPU burst time and, for priority scheduling, a priority.

### What are the states of a process?

A process moves between five states. New: the process is being created. Ready: it is in memory and waiting only for the CPU. Running: its instructions are being executed on the CPU. Waiting (also called blocked): it is waiting for an event such as I/O completion. Terminated: it has finished execution. The transitions are: new to ready when the process is admitted; ready to running when the dispatcher gives it the CPU; running to ready when it is preempted (a timer interrupt or a higher-priority arrival); running to waiting when it requests I/O or waits for an event; waiting to ready when the I/O or event completes; running to terminated when it exits. CPU scheduling decides which ready process moves to running.

### What are ready queues and waiting queues?

The ready queue holds the processes that are in memory, ready to run and waiting only for the CPU; the CPU scheduler selects the next process from it. A waiting queue (also called a device queue or I/O queue, usually one per device) holds the processes that are blocked waiting for an I/O device or an event. A process leaves the ready queue when it is dispatched. If it then requests I/O it joins a waiting queue, and when the I/O completes it moves back to the ready queue. Only processes in the ready queue compete for the CPU.

### What is the time complexity of simulating a scheduling algorithm?

The cost of a simulation depends on how it is implemented, and is different from the cost of the scheduling algorithm itself. For n processes, sorting by arrival time costs O(n log n). After that, a FCFS simulation needs a single pass over the sorted processes, so the whole simulation is O(n log n), dominated by the sort, and O(n) if the input is already sorted. Non-preemptive SJF and Priority simulations that scan all ready processes at every decision cost O(n²); using a min-heap for the ready queue reduces this to O(n log n). A preemptive simulation that advances one time unit at a time costs O(T × n) for a total running time T if it scans the ready processes at every step, or O(n log n) if it is event-driven with a heap and only decides at arrivals and completions. A Round Robin simulation does constant work per time slice, so it costs O(number of slices), which is about the sum of ceil(burst / quantum) over all processes.

### What is the time complexity of the scheduling decision itself?

The cost of choosing the next process is a property of the data structure the scheduler uses. FCFS and Round Robin use a FIFO queue, so enqueue and dequeue take O(1). SJF, SRTF and Priority scheduling need the minimum burst, remaining time or priority number, which takes O(n) with an unsorted list or a linear scan, and O(log n) per decision with a min-heap (priority queue). The theoretical comparison of algorithms by waiting time is separate from this implementation cost.

### What is the space complexity of the ready queue?

The ready queue holds at most one entry (a PCB reference) per process, so its space is O(n) for n processes, whether it is a FIFO queue, a sorted list or a heap. A simulation also stores the Gantt chart, which has one entry per execution segment: at most n for a non-preemptive algorithm, and more for preemptive algorithms and Round Robin.

### Why is SJF not practical in real systems even though it is optimal?

SJF gives the minimum average waiting time only if the scheduler knows the length of each process's next CPU burst, and the operating system does not know it in advance. The burst can only be estimated from the past, commonly by exponential averaging: the prediction for the next burst is tau(n+1) = alpha × t(n) + (1 − alpha) × tau(n), where t(n) is the length of the last actual burst, tau(n) is the previous prediction and alpha is between 0 and 1. A wrong prediction removes the optimality guarantee. SJF can also starve long jobs. For these reasons SJF is mostly used as a benchmark or in batch settings where run times are known, and real schedulers use approximations such as the multilevel feedback queue.

### What is the difference between scheduling overhead and context-switch overhead?

Context-switch overhead is the time the system spends saving one process's state and loading another's, during which no user process makes progress. Scheduling overhead is the larger cost of running the scheduler itself: examining the ready queue, updating data structures such as a heap, and calling the dispatcher. Both grow when an algorithm preempts often; Round Robin with a very small quantum has high context-switch overhead, while FCFS has the lowest. Textbook numerical problems usually ignore both and treat a context switch as taking zero time.

### What is the difference between theoretical and practical scheduling performance?

Textbook results such as "SJF minimises the average waiting time" assume a single CPU, burst times known exactly, a fixed set of processes and zero context-switch cost. A real system has unknown and changing bursts, I/O, many processes arriving unpredictably, context-switch and cache costs, and goals beyond average waiting time such as response time and fairness. As a result the algorithm that is best in theory on one metric is often not the one used in practice; real operating systems combine ideas, for example a priority-based multilevel feedback queue with Round Robin inside each level.
