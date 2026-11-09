# Good first issues

Seeded issues for new contributors. File each one on GitHub with the
`good first issue` and `help wanted` labels.

## 1. Add a per-lane benchmark summary

Title: Show the average rate per total mile by lane

Description: After the summary, print a short table grouping loads
by lane (origin to destination) with the load count and the average
rate per total mile for each lane, so a dispatcher can see which
lanes consistently pay above or below benchmark. Lanes with a
single load are still listed.

Difficulty: Easy

Acceptance criteria: the table appears in text output with the
correct per-lane averages for the sample file; JSON output is
unchanged; a test checks the table rows.

## 2. Support CSV input

Title: Accept a CSV file of loads

Description: Accept a CSV file with columns id, lane, equipment,
loaded_miles, deadhead_miles, gross_pay, so dispatchers can feed a
spreadsheet export directly. Empty deadhead cells mean zero. The
same validation rules apply, and bad rows are reported as data
errors with the row number.

Difficulty: Easy

Acceptance criteria: the sample loads as a CSV produce the same
report as examples/loads.json; a bad row reports its row number;
a test covers both cases; README documents the format.

## 3. Add a minimum-rate filter flag

Title: Add a --min-rate flag that lists only loads clearing a rate

Description: Add a --min-rate flag that takes a dollars-per-mile
figure and only evaluates loads whose rate per total mile is at or
above it, so a dispatcher can pre-filter a load board to offers
worth a second look. The summary counts only the loads that pass
the filter.

Difficulty: Easy

Acceptance criteria: --min-rate 3.50 on the sample file keeps only
L-201 and L-204; the summary says 2 loads; a test covers the
filter and the summary counts; README documents the flag.

## 4. Fetch the latest DAT benchmarks automatically

Title: Add a --refresh-benchmarks flag that pulls the newest DAT averages

Description: Add a --refresh-benchmarks flag that fetches the
latest published DAT national spot averages (dry van, reefer,
flatbed, linehaul plus fuel surcharge) from a public source, prints
the figures with their week and source, and writes them to a
benchmarks JSON file for reuse with --benchmarks. The fetch must
fail cleanly with a clear error when offline, and the tool must
never guess a figure it did not find.

Difficulty: Medium

Acceptance criteria: with a mocked fetch returning a known page,
the flag writes the correct benchmarks file; offline, it exits 2
with a clear error; a test covers both cases; README documents the
flag and warns that the defaults are a snapshot.
