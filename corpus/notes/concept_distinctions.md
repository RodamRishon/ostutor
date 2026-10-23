# CPU Scheduling — Commonly Confused Concepts (convoy effect, starvation, aging, who favours short jobs)

Standard assumptions used in this note: every process that gets the CPU eventually finishes or blocks for I/O, the number of processes ahead of a waiting process is finite, and Round Robin uses a finite time quantum.

### What is the difference between the convoy effect and starvation?

The convoy effect is a performance problem: a long CPU-bound process holds the CPU and many short processes wait behind it, so average waiting time rises and CPU and I/O-device utilisation fall. It is classically associated with FCFS, which is non-preemptive and serves processes in arrival order. Every waiting process still gets the CPU eventually, so the delay is long but finite. Starvation (indefinite blocking or indefinite postponement) is different: a ready process is passed over again and again and may never get the CPU. It can happen in SJF and SRTF when shorter jobs keep arriving ahead of a long job, and in Priority scheduling when higher-priority processes keep arriving ahead of a low-priority one. Under the standard assumptions, FCFS does not cause starvation and Round Robin does not either, because every ready process gets a turn within (n − 1) × q time units. Aging, which gradually raises the priority of a waiting process, is the usual remedy for starvation in priority-based scheduling. In short: the convoy effect is a long wait that ends, caused by a long job at the front; starvation is a wait that may never end, caused by the scheduler's selection rule.

### Convoy effect versus starvation: a comparison table

| | Convoy effect | Starvation |
|---|---|---|
| Meaning | Short processes wait behind one long CPU-bound process | A process is postponed indefinitely and may never get the CPU |
| Nature of the problem | Poor performance: high average waiting time, low utilisation | Unfairness: a process makes no progress |
| Does the wait end? | Yes, when the long process finishes or blocks | Not necessarily, if favoured processes keep arriving |
| Classic algorithm | FCFS (any non-preemptive discipline with a long job at the front) | SJF and SRTF (long jobs), Priority scheduling (low-priority jobs) |
| Cause | A long burst at the head of a non-preemptive queue | A selection rule that keeps favouring other processes |
| Typical remedy | Preemption (Round Robin, SRTF) or running short jobs first | Aging, or a fair policy such as Round Robin |

### What is the difference between the convoy effect and starvation in an example?

Convoy effect example under FCFS: P1 needs 100 time units and arrives first, then P2 and P3 need 2 units each. P2 and P3 wait about 100 units, which is a long delay, but both run as soon as P1 finishes. Starvation example under SJF: a long job P1 is waiting while a stream of short jobs keeps arriving, and each time the scheduler picks the shortest job, so P1 can be passed over indefinitely. In Priority scheduling the same happens to a low-priority job while higher-priority jobs keep arriving.

### Can starvation occur in FCFS?

Not in standard FCFS. Processes are served strictly in arrival order, so a waiting process has only finitely many processes ahead of it, and, assuming each of them eventually finishes or blocks, it reaches the head of the queue and gets the CPU. A process can wait a long time behind a long job, but that is the convoy effect: a long, finite delay, not indefinite postponement. Starvation would need an exceptional case, for example a process ahead that never terminates, which is outside the usual assumptions.

### Can starvation occur in SJF?

Yes. SJF always selects the ready process with the shortest CPU burst. If shorter jobs keep arriving while a long job is waiting, there is always a shorter job to pick, so the long job can be passed over again and again and may never get the CPU. This is starvation (indefinite blocking). SRTF makes it more likely, because a running long job can also be preempted by each shorter arrival. Whether starvation actually happens depends on the workload: if short jobs stop arriving, the long job eventually runs. Aging is the usual remedy.

### Why can starvation occur in Priority scheduling?

Priority scheduling always gives the CPU to the ready process with the highest priority. A low-priority process can be bypassed repeatedly if higher-priority processes keep arriving or stay ready, so it may wait indefinitely. This can happen in both preemptive and non-preemptive Priority scheduling, depending on the workload. The usual mitigation is aging: the priority of a process is raised gradually the longer it waits, so eventually even a low-priority process becomes the highest-priority one and gets the CPU.

### Does Round Robin prioritize short processes?

No. Round Robin does not choose processes by length. It serves the ready queue in cyclic order and gives each process at most one time quantum per turn, then moves it to the back of the queue. A short process whose burst fits within one quantum finishes in its first turn, and so finishes after fewer turns than a long process, but it is not selected first because it is short: it still waits its place in the queue. SJF, not Round Robin, is the algorithm that deliberately picks the shortest job first.

### Does Round Robin or SJF prevent starvation?

Under standard assumptions Round Robin avoids starvation, because every ready process receives a finite quantum in cyclic order and so gets the CPU within (n − 1) × q time units; it does this by rotating fairly, not by favouring short jobs. SJF does not prevent starvation; it can starve long jobs when shorter jobs keep arriving. SJF does reduce the convoy effect, because short jobs are not stuck behind long ones.

### Which scheduling algorithms can suffer starvation and which cannot?

SJF and SRTF can starve long jobs if shorter jobs keep arriving. Priority scheduling, preemptive or non-preemptive, can starve low-priority processes if higher-priority ones keep arriving; aging mitigates this. Under standard assumptions FCFS and Round Robin do not starve a process: FCFS because each process eventually reaches the head of the queue, Round Robin because each ready process gets a turn within (n − 1) × q time units. FCFS can still show the convoy effect, which is a long delay and not starvation.
