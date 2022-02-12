from enum import Enum

hook_config_filename: str

class JobState(Enum):
    RUNNING: int

JOB_STATE_RUNNING = JobState.RUNNING

class Job:

    def __init__(self):
        self.Variable_List: dict[str, str] = ...
        self.Resource_List: dict[str, str] = ...
        self.job_state: JobState = ...
        self.Execution_Time: float = ...


class Event:

    def __init__(self):
        self.job: Job = ...
        self.hook_name: str = ...

    def accept(self) -> None: ...

    def reject(self, msg: str) -> None: ...


class Server:

    def jobs(self) -> list[Job]: ...


def event() -> Event: ...


def server() -> Server: ...


def duration(t: int) -> int: ...


class LogLevel(Enum):
    DEBUG: int

LOG_DEBUG = LogLevel.DEBUG

def logmsg(level: LogLevel, msg:str) -> None: ...