# Third-Party Modified Version of the Fraunhofer FDK AAC Codec Library for Android

USBPods modification on 2026-11-03: the encoder's QC channel overlay is sized
for two channels instead of eight. Both `aacEncOpen` and the internal core
open/configuration paths reject requests beyond two channels; a zero maximum
selects two. AAC-LC stereo, AAC-ELD stereo and mono fixture encoding remain
covered by native round-trip tests. This does not change codec bitstream syntax.

This repository also contains earlier embedded decoder restrictions and memory
changes, annotated in their source files. The upstream license and copyright
notices remain in `NOTICE` and the source headers.
