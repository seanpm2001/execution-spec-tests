"""
Transition tool evaluate methods
"""
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import textwrap
from typing import Any, Dict, List, Optional, Tuple
from ._filesystem import _dump_files_to_directory, _write_json_file

def _evaluate_stream(
        self,
        *,
        alloc: Any,
        txs: Any,
        env: Any,
        fork_name: str,
        chain_id: int = 1,
        reward: int = 0,
        eips: Optional[List[int]] = None,
        debug_output_path: str = "",
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Executes a transition tool using stdin and stdout for its inputs and outputs.
        """
        fork_name = apply_eips_to_forkname(fork_name, eips)
        reward = correct_reward_for_genesis(reward, env)
        temp_dir = ""
        if self.trace:
            temp_dir = make_tempdir()
        args = make_stream_args(self, fork_name, chain_id, reward, temp_dir)

        stdin = {
            "alloc": alloc,
            "txs": txs,
            "env": env,
        }

        encoded_input = str.encode(json.dumps(stdin))
        result = subprocess.run(
            args,
            input=encoded_input,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if debug_output_path:
            t8n_call = " ".join(args)
            t8n_output_base_dir = os.path.join(debug_output_path, "t8n.sh.out")
            if self.trace:
                t8n_call = t8n_call.replace(temp_dir.name, t8n_output_base_dir)
            t8n_script = textwrap.dedent(
                f"""\
                #!/bin/bash
                rm -rf {debug_output_path}/t8n.sh.out  # hard-coded to avoid surprises
                mkdir {debug_output_path}/t8n.sh.out  # unused if tracing is not enabled
                {t8n_call} < {debug_output_path}/stdin.txt
                """
            )
            _dump_files_to_directory(
                debug_output_path,
                {
                    "args.py": args,
                    "input/alloc.json": stdin["alloc"],
                    "input/env.json": stdin["env"],
                    "input/txs.json": stdin["txs"],
                    "returncode.txt": result.returncode,
                    "stdin.txt": stdin,
                    "stdout.txt": result.stdout.decode(),
                    "stderr.txt": result.stderr.decode(),
                    "t8n.sh+x": t8n_script,
                },
            )

        if result.returncode != 0:
            raise Exception("failed to evaluate: " + result.stderr.decode())

        output = json.loads(result.stdout)

        if not all([x in output for x in ["alloc", "result", "body"]]):
            raise Exception("Malformed t8n output: missing 'alloc', 'result' or 'body'.")

        if debug_output_path:
            _dump_files_to_directory(
                debug_output_path,
                {
                    "output/alloc.json": output["alloc"],
                    "output/result.json": output["result"],
                    "output/txs.rlp": output["body"],
                },
            )

        if self.trace:
            self.collect_traces(output["result"]["receipts"], temp_dir, debug_output_path)
            temp_dir.cleanup()

        return output["alloc"], output["result"]

def make_stream_args(self, fork_name, chain_id, reward, temp_dir):
    command: list[str] = [str(self.binary)]
    if self.t8n_subcommand:
        command.append(self.t8n_subcommand)

    args = command + [
        "--input.alloc=stdin",
        "--input.txs=stdin",
        "--input.env=stdin",
        "--output.result=stdout",
        "--output.alloc=stdout",
        "--output.body=stdout",
        f"--state.fork={fork_name}",
        f"--state.chainid={chain_id}",
        f"--state.reward={reward}",
    ]

    if self.trace:
        args.append("--trace")
        args.append(f"--output.basedir={temp_dir.name}")

    return args

def _evaluate_filesystem(
        self,
        *,
        alloc: Any,
        txs: Any,
        env: Any,
        fork_name: str,
        chain_id: int = 1,
        reward: int = 0,
        eips: Optional[List[int]] = None,
        debug_output_path: str = "",
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Executes a transition tool using the filesystem for its inputs and outputs.
        """
        fork_name = apply_eips_to_forkname(fork_name, eips)

        temp_dir = tempfile.TemporaryDirectory()
        os.mkdir(os.path.join(temp_dir.name, "input"))
        os.mkdir(os.path.join(temp_dir.name, "output"))

        input_contents = {
            "alloc": alloc,
            "env": env,
            "txs": txs,
        }

        input_paths = {
            k: os.path.join(temp_dir.name, "input", f"{k}.json") for k in input_contents.keys()
        }
        for key, file_path in input_paths.items():
            _write_json_file(input_contents[key], file_path)

        output_paths = {
            output: os.path.join("output", f"{output}.json") for output in ["alloc", "result"]
        }
        output_paths["body"] = os.path.join("output", "txs.rlp")

        # Construct args for evmone-t8n binary
        args = [
            str(self.binary),
            "--state.fork",
            fork_name,
            "--input.alloc",
            input_paths["alloc"],
            "--input.env",
            input_paths["env"],
            "--input.txs",
            input_paths["txs"],
            "--output.basedir",
            temp_dir.name,
            "--output.result",
            output_paths["result"],
            "--output.alloc",
            output_paths["alloc"],
            "--output.body",
            output_paths["body"],
            "--state.reward",
            str(reward),
            "--state.chainid",
            str(chain_id),
        ]

        if self.trace:
            args.append("--trace")

        result = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if debug_output_path:
            if os.path.exists(debug_output_path):
                shutil.rmtree(debug_output_path)
            shutil.copytree(temp_dir.name, debug_output_path)
            t8n_output_base_dir = os.path.join(debug_output_path, "t8n.sh.out")
            t8n_call = " ".join(args)
            for file_path in input_paths.values():  # update input paths
                t8n_call = t8n_call.replace(
                    os.path.dirname(file_path), os.path.join(debug_output_path, "input")
                )
            t8n_call = t8n_call.replace(  # use a new output path for basedir and outputs
                temp_dir.name,
                t8n_output_base_dir,
            )
            t8n_script = textwrap.dedent(
                f"""\
                #!/bin/bash
                rm -rf {debug_output_path}/t8n.sh.out  # hard-coded to avoid surprises
                mkdir -p {debug_output_path}/t8n.sh.out/output
                {t8n_call}
                """
            )
            _dump_files_to_directory(
                debug_output_path,
                {
                    "args.py": args,
                    "returncode.txt": result.returncode,
                    "stdout.txt": result.stdout.decode(),
                    "stderr.txt": result.stderr.decode(),
                    "t8n.sh+x": t8n_script,
                },
            )

        if result.returncode != 0:
            raise Exception("failed to evaluate: " + result.stderr.decode())

        for key, file_path in output_paths.items():
            output_paths[key] = os.path.join(temp_dir.name, file_path)

        output_contents = {}
        for key, file_path in output_paths.items():
            if "txs.rlp" in file_path:
                continue
            with open(file_path, "r+") as file:
                output_contents[key] = json.load(file)

        if self.trace:
            self.collect_traces(output_contents["result"]["receipts"], temp_dir, debug_output_path)

        temp_dir.cleanup()

        return output_contents["alloc"], output_contents["result"]


def correct_reward_for_genesis(reward, env):
    if int(env["currentNumber"], 0) == 0:
        return -1
    return reward

def apply_eips_to_forkname(fork_name, eips):
    if eips is not None:
        fork_name = "+".join([fork_name] + [str(eip) for eip in eips])
    return fork_name

def make_tempdir():
    return tempfile.TemporaryDirectory()