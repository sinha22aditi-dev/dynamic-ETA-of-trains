# DynamicRail Rebuilt Prototype Dataset

## Files
- `railpulse_master_clean.csv`: cleaned copy of the supplied 1,000-row master snapshot. No factual missing values were invented.
- `dynamicrail_sequential_simulation.csv`: 30,000-row synthetic sequential extension (995 base train snapshots × 30 time steps). Each sequence has 10-minute timestamps.
- `railway_graph_nodes.csv`: 30 station nodes derived from station codes in the supplied dataset.
- `railway_graph_edges.csv`: 574 directed station-to-station connections derived from observed `current_station -> next_station` pairs, with median segment distance and observed frequency.
- `data_validation_report.json`: automated consistency checks.

## Why the sequential dataset exists
The supplied snapshot has almost one row per train and therefore does not contain enough repeated observations per train to learn temporal behaviour directly. The sequential file is a **simulation dataset** calibrated to the distributions and observed station transitions in the supplied master snapshot.

## Transparency
These repeated observations are not real railway measurements and must not be presented as live/official railway data. They are suitable for prototype experimentation, API demos, and testing the planned GRU/GNN pipeline.

## Main supervised target
`future_additional_delay_mins` is calculated as the difference between the simulated delay at the current timestamp and the simulated delay 20 minutes later within the same `sequence_id`. The final two observations of each sequence have no 20-minute future observation and are therefore left without this target.

## Preventing leakage / overfitting
For model development, split by `sequence_id` (or stronger, by a true train journey ID when available), not by individual rows. This prevents adjacent time steps from the same synthetic sequence from appearing in both train and test sets.

## Important limitation
Synthetic data can be internally consistent and statistically calibrated, but it cannot prove real-world ETA accuracy. For production accuracy, replace the simulation with authorized real-time/historical operational observations when available.
