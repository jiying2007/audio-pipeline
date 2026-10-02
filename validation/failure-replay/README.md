# Failure Replay Bank

This directory defines durable failure-replay contracts. Generated audio and run artifacts are retained by CI/evidence archives rather than committed blindly.

A replay record binds source/corpus/case identity and seed, complete perturbation dimensions, report/telemetry references, expected failure signature, shipping-output identity, first observable bad stage (or null when not proven), and a regression assertion.

Do not convert a heuristic stage guess into a proven root cause. S001-S003 may emit null and keep the case for later decomposition.
