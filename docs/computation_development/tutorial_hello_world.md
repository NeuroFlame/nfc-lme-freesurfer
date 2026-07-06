# Hello World Tutorial

## View on Youtube:
[![Hello World](https://img.youtube.com/vi/_wGZxmQclFA/0.jpg)](https://www.youtube.com/watch?v=_wGZxmQclFA)

> **Note:** Instructions below have changed slightly since the video. The job folder is now prepared with `makeJob.py` and the simulator is run on `./job`.

# Build the dev image
```
docker build -t nvflare-dev -f Dockerfile-dev .
```

# Run the container
## Linux/Mac:
```
./dockerRun.sh
```
## Windows:
```
docker run --rm -it ^
    --ipc=host --ulimit memlock=-1 --ulimit stack=67108864 ^
    --name nvflare-dev ^
    -v %cd%:/workspace ^
    -w //workspace ^
    nvflare-dev:latest
```


# Prepare the job folder
```
python makeJob.py site1,site2
```

# Run the simulator
```
nvflare simulator ./job
```

# View the results
Navigate to:
```
./test_results/simulate_job
```