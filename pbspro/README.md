# PBS Hooks for License Schduling of Schlumberger Applications

## slb_scheduling_hook

### Configuring Your Server

This hook is assumed to be run on a linux server, and Python 3.6 packages are available in `/usr/lib64/python3.6`. If the Python version or package path is different, modify the following part in the hook script accordingly:

```python
if '/usr/lib64/python3.6' not in sys.path:
    sys.path.append('/usr/lib64/python3.6')
```

### Configuring PBS Professional

The following procedure assumes PBS Professional 2021.1. If you use a different version of PBS Professional, please refer to PBS Professional Hooks Guide and Administrator's Guide of the corresponding version.

First, create two custom server-level resources of type string, `eclipse_alternatives` and `eclipse_mr_key`, using `qmgr` command:

```terminal
qmgr: create resource eclipse_alternatives type = string
qmgr: create resource eclipse_mr_key type = string
```

After you define the above resources, put the resource names in the "resources:" line in `$PBS_HOME/sched_priv/sched_config`, and HUP the scheduler by the following command:

```terminal
ps -ef | grep pbs_sched
kill -HUP <PID>
```

Next, place `slb_scheduling_hook.py` and `slb_scheduling_hook.json` in some directory in the PBS server. Modify parameters in `slb_scheduling_hook.json` according to your environment. At least you need to check and modify `issued_licenses` and `lmutil`. `issued_licenses` is a list of license names issued for your company, and it is used to validate `eclipse_alternatives`. `lmutil` is an absolute path to `lmutil` command accessible from the PBS server.

Lastly, change directory where `slb_scheduling_hook.py` and `slb_scheduling_hook.json` are stored, and create and import slb_scheduling_hook using `qmgr` command:

```terminal
qmgr: create hook slb_scheduling
qmgr: import hook slb_scheduling application/x-python default slb_scheduling_hook.py
qmgr: import hook slb_scheduling application/x-config default slb_scheduling_hook.json
qmgr: set hook slb_scheduling event = runjob
```
