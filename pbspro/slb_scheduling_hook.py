import sys
import os
import time
import re
from xmlrpc.client import boolean

if '/usr/lib64/python3.6' not in sys.path:
    sys.path.append('/usr/lib64/python3.6')

import pbs
import subprocess as sp
from pathlib import Path
import json
from enum import Enum


def parse_alternatives(alternatives: str) -> list[dict[str, int]]:
    """Convert eclipse_alternatives to a list of dictionaries."""

    def to_dict(alt: str) -> dict:
        """Convert eclipse license request to a dictionary."""
        licenses = [tuple(s.split('=')) for s in alt.split(':')]
        return dict([(key, int(token)) for key, token in licenses])

    return [to_dict(alt) for alt in alternatives.split('+')]


class FlexLicenseManager:
    """
    Attributes:
        lmutil (pathlib.Path): Absolute path to lmutil
        server (str): License server
    """

    def __init__(self, lmutil: Path, server: str):
        self.lmutil = lmutil
        self.server = server

    @staticmethod
    def parse_query(lines: str, feature: str) -> int:
        """Parse a license query result."""
        regex = re.compile(
            f'Users of {feature}:  \(Total of (\d+) licenses?? issued;  Total of (\d+) licenses?? in use\)')
        m = regex.search(lines)

        if m is None:
            raise ValueError(
                f'License feature is not found in FlexLM: {feature}')

        issued = int(m.group(1))
        used = int(m.group(2))
        return issued - used

    def query_license(self, feature: str, timeout: int = 5) -> int:
        """Query an eclipse license"""
        cmd = [str(self.lmutil), 'lmstat', '-c', self.server,
               '-f', feature, '-S', 'slbsls']
        result = sp.run(cmd, stdout=sp.PIPE, stderr=sp.PIPE,
                        encoding='utf-8', timeout=timeout, check=True)
        count = self.parse_query(result.stdout, feature)
        return count


class HookConfiguration:
    """Read the hook configuration file and store parameters.

    Attributes:
        lmutil (pathlib.Path): Absolute path to lmutil.
        issued_licenses (list[str]): List of issued licenses.
        stamp (pathlib.Path): Absolute path to time stamp file.
        interval_time (float): Interval time from the last Eclipse run.
        delay_time (float): Delay time if licenses are not available.
        license_server (str): License server

    Examples:
        Hook configuration file example in JSON format:
        {
            "lmutil"       : "abspath/to/lmutil",
            "issued_licenses"     : ["eclipse", "compositional", "parallel", "bparallel", "lgr", "networks", "gaslift"],
            "stamp"        : "/tmp/EclipseLastRun",
            "interval_time": 15.0,
            "delay_time"   : 60.0
        }
    """

    def __init__(self):
        if pbs.hook_config_filename is None:
            raise ValueError("pbs.hook_config_filename is not set")

        path = Path(pbs.hook_config_filename)

        if not path.exists():
            raise ValueError(f'Configuration file does not exist: {path}')

        with open(path, mode='r') as f:
            j = json.load(f)
            try:
                self.lmutil = Path(j['lmutil'])
                self.issued_licenses = j['issued_licenses']
            except KeyError as e:
                raise KeyError(
                    f'Parameter is not defined in the hook configuration file: {e}')

            self.stamp = Path(j.get('stamp', 'tmp/EclipseLastRun'))
            self.interval_time = j.get('interval_time', 15.0)
            self.delay_time = j.get('delay_time', 60.0)

        try:
            self.license_server = pbs.event(
            ).job.Variable_List['SLBSLS_LICENSE_FILE']
        except KeyError as e:
            raise KeyError(
                f"Environment variable \"SLBSLS_LICENSE_FILE\" is not defined: {e}")


class EclipseLicenseChecker:
    """
    Attributes:
        issued_licenses (list[str]): List of issued licenses.
        flexlm (FlexLicenseManager): FlexLicenseManager object
    """

    def __init__(self, issued_licenses: list[str], flexlm: FlexLicenseManager):
        self.issued_licenses = issued_licenses
        self.flexlm = flexlm

    def validiate(self, alternatives: list[dict[str, int]]) -> tuple[bool, list[str]]:
        """Validate eclipse_alternatives.

        If Eclipse licenses are not available and no missing licenses is found, it means that there is no valid license alternative.

        Returns:
            is_available (bool): Eclipse licenses are available.
            missing_licenses (list[str]): Missing licenses.
        """
        missing_licenses = []
        for alternative in alternatives:
            if not self.is_issued(alternative):
                continue
            pbs.logmsg(pbs.LOG_DEBUG,
                       f'Valid license alternative is found: {alternative}')
            for license, required_num in alternative.items():
                available_num = self.flexlm.query_license(license)
                if available_num < required_num:
                    if license not in missing_licenses:
                        missing_licenses.append(license)
                    break
            else:
                return True, []

        return False, missing_licenses

    def is_issued(self, licenses) -> bool:
        """Check if licenses are issued."""
        return all(license in self.issued_licenses for license in licenses)


class EclipseMultipleRealizationChecker:

    def __init__(self):
        self.job = pbs.event().job

    def is_mr_job(self) -> bool:
        """Checks if it is a multiple realization job."""
        return not self.job.Resource_List['eclipse_mr_key'] and 'ECL_LICS_REQD' in self.job.Variable_List and self.job.Variable_List['ECL_LICS_REQD'] != ''

    def is_another_mr_job_running(self) -> bool:
        """Checks if another multiple realization job from the same group is already running."""
        for other_job in pbs.server().jobs():
            if other_job.job_state is pbs.JOB_STATE_RUNNING and 'eclipse_mr_key' in other_job.Resource_List and self.job.Resource_List['eclipse_mr_key'] == other_job.Resource_List['eclipse_mr_key']:
                return True
        else:
            return False


try:
    e = pbs.event()
    j = e.job

    if 'eclipse_alternatives' not in j.Resource_List:
        sys.exit()

    config = HookConfiguration()

    if config.stamp.exists() and config.stamp.is_file():
        elapsed_time = time.time() - os.stat(config.stamp).st_mtime
        if elapsed_time < config.interval_time:
            j.Execution_Time = pbs.duration(
                time.time() + config.interval_time - elapsed_time)
            e.reject('Too little time passed from the last run. Delaying the job.')

    flexlm = FlexLicenseManager(config.lmutil, config.license_server)
    license_checker = EclipseLicenseChecker(config.licenses, flexlm)
    mr_checker = EclipseMultipleRealizationChecker()

    alternatives = parse_alternatives(j.Resource_List['eclipse_alternatives'])
    is_available, missing_licenses = license_checker.validiate(alternatives)

    if is_available:
        # Check multiple relization
        if mr_checker.is_mr_job() and not mr_checker.is_another_mr_job_running():
            mr_alternatives = parse_alternatives(
                j.Variable_List['ECL_LICS_REQD'])
            is_mr_available, mr_missing_licenses = license_checker.validate(
                mr_alternatives)
            if not is_mr_available:
                e.reject(
                    f'Licenses for a multiple realization job are not available. Rejecting the job: missing licenses = {mr_missing_licenses}')

        pbs.logmsg(pbs.LOG_DEBUG,
                   f'Eclipse licenses are available. Accepting the job.')
        with open(config.stamp, mode='w') as f:
            f.write('check')
        e.accept()
    elif not missing_licenses:
        j.Execution_Time = pbs.duration(time.time() + config.delay_time)
        e.reject(
            f'Licenses are not available. Delaying the job: missing licenses = {missing_licenses}')
    else:
        e.reject(f'Valid license alternative is not found.')


except SystemExit:
    pass

except:
    e = pbs.event()
    e.reject(f'{e.hook_name} hook failed with {sys.exc_info()[:2]}.')
