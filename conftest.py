"""
Top-level pytest configuration file providing:
- Command-line options,
- Test-fixtures that can be used by all test cases,
and that modifies pytest hooks in order to fill test specs for all tests and
writes the generated fixtures to file.
"""
import json
import os
import re
from typing import Any, Dict, List, Tuple, Type

import pytest

from ethereum_test_forks import (
    ArrowGlacier,
    InvalidForkError,
    set_latest_fork_by_name,
)
from ethereum_test_tools import (
    BlockchainTest,
    BlockchainTestFiller,
    Fixture,
    JSONEncoder,
    StateTest,
    StateTestFiller,
    fill_test,
)
from evm_block_builder import EvmBlockBuilder
from evm_transition_tool import EvmTransitionTool


def pytest_addoption(parser):
    group = parser.getgroup(
        "evm", "Arguments defining evm executable behavior"
    )
    group.addoption(
        "--evm-bin",
        action="store",
        dest="evm_bin",
        default=None,
        help="Path to evm executable that provides `t8n` and `b11r` ",
    )
    group.addoption(
        "--traces",
        action="store_true",
        dest="evm_collect_traces",
        default=None,
        help="Collect traces of the execution information from the "
        + "transition tool",
    )

    group = parser.getgroup(
        "fillers", "Arguments defining filler location and output"
    )
    group.addoption(
        "--filler-path",
        action="store",
        dest="filler_path",
        default="./fillers/",
        help="Path to filler directives",
    )
    group.addoption(
        "--output",
        action="store",
        dest="output",
        default="./out/",
        help="Directory to store filled test fixtures",
    )
    group.addoption(
        "--latest-fork",
        action="store",
        dest="latest_fork",
        default=None,
        help="Latest fork used to fill tests",
    )


def pytest_configure(config):
    """
    Check parameters and make session-wide configuration changes, such as
    setting the latest fork.
    """
    latest_fork = config.getoption("latest_fork")
    if latest_fork is not None:
        try:
            set_latest_fork_by_name(latest_fork)
        except InvalidForkError as e:
            pytest.exit(f"Error applying --latest-fork={latest_fork}: {e}.")
        except Exception as e:
            raise e
    return None


@pytest.hookimpl(trylast=True)
def pytest_report_header(config, start_path):
    """A pytest hook called to obtain the report header."""
    bold = "\033[1m"
    warning = "\033[93m"
    reset = "\033[39;49m"
    if config.getoption("latest_fork") is None:
        header = [
            (
                bold
                + warning
                + "Only executing fillers with stable/deployed forks: "
                "Specify an upcoming fork via --latest-fork=fork to "
                "run experimental fillers." + reset
            )
        ]
    else:
        header = [
            (
                bold + "Executing fillers up to and including "
                f"{config.getoption('latest_fork')}." + reset
            ),
        ]
    return header


@pytest.fixture(autouse=True, scope="session")
def evm_bin(request):
    """
    Returns the configured evm tool binary path.
    """
    return request.config.getoption("evm_bin")


@pytest.fixture(autouse=True, scope="session")
def t8n(request):
    """
    Returns the configured transition tool.
    """
    t8n = EvmTransitionTool(
        binary=request.config.getoption("evm_bin"),
        trace=request.config.getoption("evm_collect_traces"),
    )
    return t8n


@pytest.fixture(autouse=True, scope="session")
def b11r(request):
    """
    Returns the configured block builder tool.
    """
    b11r = EvmBlockBuilder(binary=request.config.getoption("evm_bin"))
    return b11r


class FixtureCollector:
    """
    Collects all fixtures generated by the test cases.
    """

    all_fixtures: Dict[str, List[Tuple[str, Any]]]
    output_dir: str

    def __init__(self, output_dir: str) -> None:
        self.all_fixtures = {}
        self.output_dir = output_dir

    def add_fixture(self, item, fixture: Fixture) -> None:
        """
        Adds a fixture to the list of fixtures of a given test case.
        """

        def get_module_dir(item) -> str:
            """
            Returns the directory of the test case module.
            """
            dirname = os.path.dirname(item.path)
            basename, _ = os.path.splitext(item.path)
            module_path_no_ext = os.path.join(dirname, basename)
            module_dir = os.path.relpath(
                module_path_no_ext,
                item.funcargs["filler_path"],
            )
            return module_dir

        module_dir = get_module_dir(item) + "/" + item.originalname
        if module_dir not in self.all_fixtures:
            self.all_fixtures[module_dir] = []
        m = re.match(r".*\[(.*)\]", item.name)
        if not m:
            raise Exception("Could not parse test name: " + item.name)
        name = m.group(1)
        if fixture.name:
            name += "-" + fixture.name
        jsonFixture = json.loads(json.dumps(fixture, cls=JSONEncoder))
        self.all_fixtures[module_dir].append((name, jsonFixture))

    def dump_fixtures(self) -> None:
        """
        Dumps all collected fixtures to their respective files.
        """
        for module_file, fixtures in self.all_fixtures.items():
            output_json = {}
            for index, name_fixture in enumerate(fixtures):
                name, fixture = name_fixture
                name = str(index).zfill(3) + "-" + name
                output_json[name] = fixture
            file_path = self.output_dir + os.sep + module_file + ".json"
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w") as f:
                json.dump(output_json, f, indent=4)


@pytest.fixture(autouse=True, scope="session")
def fixture_collector(request):
    """
    Returns the configured fixture collector instance used for all tests.
    """
    fixture_collector = FixtureCollector(
        output_dir=request.config.getoption("output")
    )
    yield fixture_collector
    fixture_collector.dump_fixtures()


@pytest.fixture(autouse=True, scope="session")
def engine():
    """
    Returns the sealEngine used in the generated test fixtures.
    """
    return "NoProof"


@pytest.fixture(autouse=True, scope="session")
def filler_path(request):
    """
    Returns the directory containing the fillers to execute.
    """
    return request.config.getoption("filler_path")


@pytest.fixture(autouse=True)
def eips():
    """
    A fixture specifying that, by default, no EIPs should be activated for
    fillers.

    This fixture (function) may be redefined in test filler modules in order
    to overwrite this default and return a list of integers specifying which
    EIPs should be activated for the fillers in scope.
    """
    return []


@pytest.fixture(autouse=True)
def reference_spec():
    return None


@pytest.fixture(scope="function")
def state_test() -> StateTestFiller:
    """
    Fixture used to instantiate an auto-fillable StateTest object from within
    a test function.

    Every test that defines a StateTest filler must explicitly specify this
    fixture in its function arguments and set the StateTestWrapper's spec
    property.

    Implementation detail: It must be scoped on test function level to avoid
    leakage between tests.

    Proper definition of the StateTestWrapper is done during the
    pytest_runtest_call.
    """

    class StateTestWrapper(StateTest):
        pass

    return StateTestWrapper


@pytest.fixture(scope="function")
def blockchain_test() -> BlockchainTestFiller:
    """
    Fixture used to define an auto-fillable BlockchainTest analogous to the
    state_test fixture for StateTests.
    See the state_test fixture docstring for details.
    """

    class BlockchainTestWrapper(BlockchainTest):
        pass

    return BlockchainTestWrapper


def pytest_make_parametrize_id(config, val, argname):
    """
    Pytest hook called when generating test ids. We use this to generate
    more readable test ids for the generated tests.
    """
    return f"{argname}={val}"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    """
    Pytest hook called in the context of test execution. After pytest
    has executed the test function and created the test spec, we fill
    the test spec and write the generated fixture to file.
    """

    # Get config from session-wide fixtures. Note, we could also access these
    # from the pytest config object via item.config
    # evm_bin = item.funcargs["evm_bin"]
    t8n = item.funcargs["t8n"]
    b11r = item.funcargs["b11r"]
    engine = item.funcargs["engine"]
    reference_spec = item.funcargs["reference_spec"]
    fixture_collector: FixtureCollector = item.funcargs["fixture_collector"]

    # Get test-specific params from potentially locally defined fixtures
    eips = item.funcargs["eips"]
    fork = item.funcargs["fork"]

    if not t8n.is_fork_supported(fork):
        pytest.skip(f"Fork '{fork}' not supported by t8n, skipped")
    if fork == ArrowGlacier:
        pytest.skip(f"Fork '{fork}' not supported by hive, skipped")

    spec_types: Dict[str, Type] = {
        "state_test": StateTest,
        "blockchain_test": BlockchainTest,
    }

    spec_type_count = 0
    for spec_type, spec_class in spec_types.items():
        if spec_type in item.funcargs:
            spec_type_count += 1

            class AutoFillerWrapper(spec_class):
                def __init__(self, *args, **kwargs):
                    super(AutoFillerWrapper, self).__init__(*args, **kwargs)
                    fixture_collector.add_fixture(
                        item,
                        fill_test(
                            "",
                            t8n,
                            b11r,
                            self,
                            fork,
                            engine,
                            reference_spec,
                            eips=eips,
                        ),
                    )

            item.funcargs[spec_type] = AutoFillerWrapper

    if spec_type_count == 0:
        raise Exception(
            "Test function must define at least one of the following spec "
            + "type arguments: "
            + ", ".join(spec_types.keys())
        )

    output = yield  # Execute the test function

    # Process test result; this will stop execution if there was an issue in
    # the test function and trigger a pytest error or fail for this spec.
    output.get_result()
