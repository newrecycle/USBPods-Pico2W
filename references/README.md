# Pinned reference snapshots

These sources are for offline comparison and the SDK-contract host fixtures.
They are not included in the firmware target. Do not mistake their behavior
for a requirement or copy an implementation without comparing the evidence.

`manifest.json` records each source repository, exact commit, source URL and
the SHA-256 of the materialized text snapshot. Text snapshots may have normalized
line endings; use the source URL for original repository bytes.

- `han-um/`: the microphone fork at `d18d083`, with its GPL-3.0 license.
- `librepods/`: the microphone PR head `99b0e58`, with its GPL-3.0 license.
- `btstack/`: the Pico SDK's pinned BTstack submodule `501e6d2`, including its
  license. `sdk-bluetooth.h` is the original `src/bluetooth.h`, named to work
  with the existing offline fixture. These are upstream contract snapshots;
  actual firmware builds also require our separate `sdk-patches/` changes.

Original copyright and license notices are retained. Each snapshot keeps its
own license; this directory does not relicense unrelated project components.

`research-history.json` indexes relevant commits and discussion links. Full
third-party discussion text is not vendored; the findings document paraphrases
the relevant evidence and links to its authors.
