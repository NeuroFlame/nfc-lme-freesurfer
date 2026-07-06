## Developing in a container

- You can choose to develop inside a container or on your local host system.
- If you choose to develop in a container you can use the following command to build a dev docker image

```
docker build -t nvflare-pt -f Dockerfile-dev .
```

- You can launch the container by running `./dockerRun.sh`
- If you're using windows, launch the container by using the following command:

```
docker run --rm -it ^
    --ipc=host --ulimit memlock=-1 --ulimit stack=67108864 ^
    --name flare ^
    -v %cd%:/workspace ^
    -w //workspace ^
    nvflare-pt:latest

```

## Developing on local machine

Install the nvflare package:

```
python3 -m pip install nvflare==2.4.0
```

Make sure the following environment variables are set:

```
export PYTHONPATH=$PYTHONPATH:[path to this dir + ./app/code/]
export NVFLARE_POC_WORKSPACE=[path to this dir + ./poc-workspace/]
```

## NVFLARE Simulator

- The FL Simulator is a lightweight simulator of a running NVFLARE FL deployment, and it can allow researchers to test and debug their application without provisioning a real project.
- https://nvflare.readthedocs.io/en/2.4.0/user_guide/nvflare_cli/fl_simulator.html

### Using NVFLARE Simulator

The simulator can run the entire project as a single thread. This can be useful for attaching a debugger.

The following commands allow you to run the app using the Simulator

```
python makeJob.py site1,site2
nvflare simulator ./job
```