from rag.fetch_wiki import fetch_webpage

URLS = [
    "https://www.geeksforgeeks.org/operating-systems/cpu-scheduling-in-operating-systems/",
    "https://www.geeksforgeeks.org/operating-systems/preemptive-and-non-preemptive-scheduling/",
    "https://www.geeksforgeeks.org/operating-systems/shortest-job-first-or-sjf-cpu-scheduling/",
    "https://www.geeksforgeeks.org/dsa/shortest-remaining-time-first-preemptive-sjf-scheduling-algorithm/",
    "https://www.geeksforgeeks.org/operating-systems/round-robin-scheduling-in-operating-system/",
    "https://www.geeksforgeeks.org/operating-systems/priority-scheduling-in-operating-system/",
    "https://www.geeksforgeeks.org/operating-systems/highest-response-ratio-next-hrrn-cpu-scheduling/",
    "https://www.geeksforgeeks.org/operating-systems/multilevel-queue-mlq-cpu-scheduling/",
    "https://www.geeksforgeeks.org/operating-systems/multilevel-feedback-queue-scheduling-mlfq-cpu-scheduling/"
]

def fetch_all(urls=URLS):
    print(f"Fetching {len(urls)} pages...\n")
    ok, failed = [], []

    for url in urls:
        print(f"-> {url}")
        try:
            path = fetch_webpage(url)
            ok.append(url)
        except Exception as e:
            print(f"  ! Failed: {e}")
            failed.append(url)

    print(f"\nDone. {len(ok)} saved, {len(failed)} failed.")
    if failed:
        print("Failed URLs:")
        for url in failed:
            print(f"  - {url}")


if __name__ == "__main__":
    fetch_all()
