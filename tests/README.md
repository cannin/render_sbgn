# Cross-language tests

`conformance.py` renders every canonical `.sbgn` input with all four native
implementations. It verifies PNG type and dimensions, validates manifest shape,
and compares backend-independent primitive identity and topology.

Generated images, manifests, and helper binaries are written to `output/`,
which is ignored by Git.
