# CPU Scheduling — What aging does and does not guarantee, with examples

Standard assumptions used in this note: aging adds a positive amount to a waiting process's priority at regular intervals, the processes that run ahead of a waiting process eventually finish or block for I/O, and the number of processes is finite.

### Does aging guarantee that starvation will never occur?

No, not in every case. Aging is a mitigation built into a priority-style policy: it gradually raises the priority of a waiting process, so under the standard assumptions the waiting process eventually reaches the highest priority and gets the CPU. It is not a guarantee about every possible scheduling policy or workload. A policy that ignores waiting time and has no aging, such as plain SJF, SRTF or priority scheduling, can still starve a process. Aging does not bound the waiting time unless its rate is known, it does not remove the convoy effect, and a badly tuned rate (too slow, or a priority that is capped below what newly arriving jobs have) leaves the process waiting for a very long time. So aging reduces the risk of starvation; it does not make starvation impossible everywhere.

### How does aging help a starving process eventually run?

Aging raises the priority of a process the longer it waits. Suppose a long process has priority 5 (a lower number means a higher priority in this course) and processes with priorities 1, 2 and 3 keep arriving, so under priority scheduling without aging it can be bypassed again and again. With aging the scheduler lowers the waiting process's priority number by one after every fixed interval of waiting. After enough intervals its effective priority is better than that of the newly arriving processes, so the scheduler selects it and it runs. This holds under the standard assumptions: the aging step is positive and applied regularly, and the processes that run before it eventually finish or block.

### What is a practical example of starvation and aging?

A print server gives urgent jobs priority over ordinary ones. If urgent jobs keep arriving, a large ordinary report can wait indefinitely, which is starvation. A textbook remedy is aging: if priorities run from 127 (lowest) to 0 (highest) and a waiting job's priority number is lowered by 1 every 15 minutes, even a job that starts at 127 reaches priority 0 after a little over 31 hours and then runs. Starvation here depends on the policy and the workload: if urgent jobs stop arriving, the report runs even without aging.
