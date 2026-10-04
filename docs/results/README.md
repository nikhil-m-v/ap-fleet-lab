# Results

The committed experiments are generated from the headless runner. [Full experiment overview](full/overview.md) and [tables](full/report.md) report 20 paired seeds for all three environments, fleet sizes 4/8/16/32, three demand patterns, two disruption profiles, and three algorithms, with 60-second warm-up and 600-second measurement windows.

The full 4,320-run suite is reproducible through the default benchmark command. Use `--workers 4` to run cases in four separate processes; the default is one worker. Raw records are compressed for GitHub delivery and include each run's actual source revision. To resume from the compressed archive, decompress it as `results.jsonl` before using `--resume`.

Read raw configurations, solver gaps, and provenance alongside the reports. Whole-traversal exclusion and the limited rolling horizon influence the result. Zero collision observations apply only to the scenarios and seeds executed.
