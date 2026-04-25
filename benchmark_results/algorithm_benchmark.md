# Algorithm benchmark

Runs: 56
Real compute time: 225.58s

## Overall ranking

| Rank | Algorithm | Avg score | Pallets | Boxes retrieved | Relocations | Avg sim time |
|---:|---|---:|---:|---:|---:|---:|
| 1 | nearest_head | 26155474.2 | 1034 | 12408 | 2632 | 14358.0s |
| 2 | balanced_ready | 26155454.6 | 1034 | 12408 | 2707 | 13617.0s |
| 3 | throughput | 26154665.2 | 1034 | 12408 | 2597 | 22885.9s |
| 4 | balanced | 26154664.0 | 1034 | 12408 | 2535 | 23672.7s |
| 5 | baseline | 26154662.2 | 1034 | 12408 | 2588 | 23028.0s |
| 6 | grouped | 26154519.7 | 1034 | 12408 | 2700 | 23052.6s |
| 7 | least_blocked | 26154467.5 | 1034 | 12408 | 2593 | 24912.2s |
| 8 | grouped_blocked | 26154354.2 | 1034 | 12408 | 2626 | 25633.3s |
| 9 | most_boxes | 26154334.0 | 1034 | 12408 | 2758 | 24185.2s |
| 10 | dense_batch | 26154244.0 | 1034 | 12408 | 2558 | 27584.6s |
| 11 | retrieval_friendly | 26154124.9 | 1034 | 12408 | 2623 | 27963.7s |
| 12 | spread_unblocked | 26154072.8 | 1034 | 12408 | 2497 | 30059.3s |
| 13 | opportunistic | 26154047.0 | 1034 | 12408 | 2565 | 29467.7s |
| 14 | scarcity_depth | 26153854.5 | 1034 | 12408 | 2687 | 29867.8s |

## Per-state winners

| State | Winner | Pallets | Boxes retrieved | Relocations | Sim time |
|---|---|---:|---:|---:|---:|
| heavy_70 | nearest_head | 464 | 5568 | 1447 | 27504.0s |
| initial | nearest_head | 90 | 1080 | 256 | 4138.4s |
| light_25 | balanced_ready | 176 | 2112 | 263 | 8489.8s |
| medium_45 | balanced_ready | 304 | 3648 | 683 | 15817.4s |
