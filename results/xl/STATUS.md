# Experiment status

Updated 2026-08-27. Read this first after a restart, then `ps -ef | grep python`
to see what is still running. Every long run writes per combination result files
and skips what is already on disk, so a restart never loses finished work.

Method layer code hash **`4dafbe9f0e36e7e4`** since the soft_mu change. Runs
launched before that carry `1f6d57bb1a15e4a0` and are not invalidated by it,
since the switch defaults to off and changes no existing path.

| experiment | script | seed 0 | seed 1 | seed 2 | note |
|---|---|---|---|---|---|
| main table | `run_main.py` | done | done | done | `f49fa8c`, f_full is the headline row |
| ablation, 7 rungs | `run_ablations.py` | done | done | done | `7e16b8c`, aggregated |
| shield conservatism | `shield_replay.py` | done | done | done | `fafbdd5`, recomputed on mixed |
| nRMSD by kind | `nrmsd_by_contamination.py` | done | done | done | `214e6a2`, from traces, no GPU |
| calibration decay | `calibration_decay.py` | done | done | done | `99b6b46`, extracted, bound is vacuous |
| soft penalty sweep | `run_soft_sweep.py` | done | done | done | `4ee8043`, 10 weights, mu 100 is the table's point |
| damage target sweep | not written | | | | experiment one sub table 3, next |
| downstream by stratum | not written | | | | PatchTST and DLinear, batch C |

## Rows that need no run

`experiment three, fixed rule arm` is the ablation's `c_no_policy`, which is
also the main table's `introact` configuration. Take the numbers from
`results/xl/ablation_c_no_policy_seed*.json` rather than running anything.

`experiment one sub table 1` comes from the stratified statistics and the replay
that are already on disk.

## Resuming a killed run

    cd /root/autodl-tmp/work2
    PY=/root/autodl-tmp/envs/w2/bin/python
    $PY experiments/run_soft_sweep.py --source mixed --scale xl --seeds 0,1,2 \
        --tau 0.02 --device cuda --n-jobs 32 --out results/xl

Finished weights are skipped, and a seed whose weights are all present skips
perception as well. `tmux` is not installed on this node; long runs are launched
detached with `setsid` through `tools/remote.py launch`, which survives the SSH
session closing exactly as tmux would.
