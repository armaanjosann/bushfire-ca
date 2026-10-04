"""Single entry point: python run.py --exp 0|0b|pilot|1-coarse|1|scars|2|2b|3|4|all (project-context.md §4.7)."""

import argparse

from src import experiments

EXPERIMENTS = {
    "0": experiments.run_exp0,
    "0b": experiments.run_exp0b,
    "pilot": experiments.run_pilot,
    "1-coarse": experiments.run_exp1_coarse,
    "1": experiments.run_exp1,
    "scars": experiments.run_scars,
    "2": experiments.run_exp2,
    "2b": experiments.run_exp2b,
    "3": experiments.run_exp3,
    "4": experiments.run_exp4,
}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bushfire CA experiment runner")
    parser.add_argument(
        "--exp",
        required=True,
        choices=[*EXPERIMENTS.keys(), "all"],
        help="Experiment to run, or 'all' to run every experiment in sequence.",
    )
    args = parser.parse_args(argv)

    if args.exp == "all":
        for run in EXPERIMENTS.values():
            run()
    else:
        EXPERIMENTS[args.exp]()


if __name__ == "__main__":
    main()
