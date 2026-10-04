# Results

The committed experiments are generated from the headless runner. `intersection-4/report.md` reports 20 paired seeds for every combination of the three demand patterns, two disruption profiles, and three algorithms, with 60-second warm-up and 600-second measurement windows.

Additional breadth checks appear in `breadth/report.md`; their shorter windows and smaller seed count are explicitly exploratory. The full 4,320-run suite is available through the default benchmark command, but should not be inferred from these subsets.

Read raw configurations, solver gaps, and provenance alongside the reports. Whole-traversal exclusion and the limited rolling horizon influence the result. Zero collision observations apply only to the scenarios and seeds executed.
