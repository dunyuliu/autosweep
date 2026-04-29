import argparse
import os
import re
import shutil
import subprocess
import sys


def parse_arguments():
    parser = argparse.ArgumentParser(description="Run a Permafrost MATLAB simulation")
    parser.add_argument("--output_dir", type=str, required=True, help="Base output directory")
    parser.add_argument(
        "--source_dir", type=str, default="src", help="Source directory of the MATLAB code"
    )
    parser.add_argument(
        "--case_number",
        type=int,
        required=True,
        help="Case number for folder naming (e.g. Case_1, Case_2)",
    )
    parser.add_argument(
        "--wait", action="store_true", help="Wait for MATLAB simulation to finish"
    )
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        help="Override parameters in the form key=value",
    )
    return parser.parse_args()


def parse_params(param_list):
    params = {}
    for item in param_list or []:
        if "=" not in item:
            print(f"Warning: Invalid parameter format '{item}'. Expected key=value.")
            continue
        key, value = item.split("=", 1)
        params[key.strip()] = value.strip()
    return params


def setup_simulation_directory(source_dir, output_base_dir, case_number):
    case_dir = os.path.join(output_base_dir, f"Case_{case_number}")
    abs_source = os.path.abspath(source_dir)
    abs_dest = os.path.abspath(case_dir)

    os.makedirs(output_base_dir, exist_ok=True)

    if os.path.exists(abs_dest):
        print(f"Warning: Directory {abs_dest} already exists. Deleting...")
        shutil.rmtree(abs_dest)

    print(f"Copying {abs_source} to {abs_dest}...")
    shutil.copytree(abs_source, abs_dest)
    return abs_dest


def modify_initialization(sim_dir, params):
    if not params:
        return

    init_file = os.path.join(sim_dir, "Initialization.m")
    with open(init_file, "r") as f:
        content = f.read()

    for key, value in params.items():
        pattern_vector = (
            r"(\b" + re.escape(key) + r"\s*=\s*)([\d\.\+\-eE]+)(\s*\*\s*ones.+?;)"
        )
        new_content, count = re.subn(pattern_vector, r"\g<1>" + value + r"\g<3>", content)
        if count > 0:
            content = new_content
            print(f"Updated vector scalar {key} to {value} in Initialization.m")
            continue

        pattern_general = r"(\b" + re.escape(key) + r"\s*=\s*)(.+?)(\s*;)"
        new_content, count = re.subn(pattern_general, r"\g<1>" + value + r"\g<3>", content)
        if count > 0:
            content = new_content
            print(f"Updated {key} to {value} in Initialization.m")
        else:
            print(f"Warning: Could not find '{key}' in Initialization.m")

    with open(init_file, "w") as f:
        f.write(content)


def write_runner(sim_dir):
    runner_script = os.path.join(sim_dir, "runner.m")
    with open(runner_script, "w") as f:
        f.write("try\n")
        f.write("    Main_loop_2D;\n")
        f.write("catch ME\n")
        f.write("    disp(getReport(ME));\n")
        f.write("end\n")
        f.write("exit;\n")


def run_matlab(sim_dir, wait=False):
    write_runner(sim_dir)

    cmd = [
        "matlab",
        "-nodisplay",
        "-nodesktop",
        "-nosplash",
        "-singleCompThread",
        "-r",
        "runner",
    ]
    log_file_path = os.path.join(sim_dir, "simulation.log")

    print(f"Launching MATLAB {'(blocking)' if wait else '(background)'}...")
    print(f"Logs: {log_file_path}")

    with open(log_file_path, "w") as log_file:
        if wait:
            subprocess.run(
                cmd,
                cwd=sim_dir,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                check=False,
            )
        else:
            subprocess.Popen(
                cmd,
                cwd=sim_dir,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )


def main():
    args = parse_arguments()

    if not os.path.exists(args.source_dir):
        print(f"Error: Source directory '{args.source_dir}' not found.")
        sys.exit(1)

    params = parse_params(args.param)
    sim_dir = setup_simulation_directory(args.source_dir, args.output_dir, args.case_number)
    modify_initialization(sim_dir, params)
    run_matlab(sim_dir, wait=args.wait)


if __name__ == "__main__":
    main()
