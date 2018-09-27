# Kubernetes Metrics Server Prometheus Adapter

**[Motivation](#motivation)** |
**[Usage](#usage)** |
**[Docker Compose](#docker-compose)** |
**[Metrics transformation](#metrics-transformation)** |
**[License](#license)**

[![Build Status](https://travis-ci.org/cytopia/metrics-server-prom.svg?branch=master)](https://travis-ci.org/cytopia/metrics-server-prom)
[![release](https://img.shields.io/github/tag/cytopia/metrics-server-prom.svg)](https://github.com/cytopia/metrics-server-prom/releases)

<a target="_blank" title="DockerHub" href="https://hub.docker.com/r/cytopia/metrics-server-prom/"><img src="https://dockeri.co/image/cytopia/metrics-server-prom" /></a>

## Motivation

### What is provided

A Docker image on which [Prometheus](https://github.com/prometheus/prometheus) can scrape Kubernetes metrics provided by **[metrics-server](https://github.com/kubernetes-incubator/metrics-server)**. The image can run anywhere where Prometheus can use it as a target, even in Kubernetes itself.

### Why is it needed

metrics-server seems to be the [successor of heapster](https://github.com/kubernetes/heapster) for Kubernetes monitoring. However, metrics-server currently only provides its metrics in JSON format via the Kubernetes API server.

Prometheus on the other hand expects a special [text-based format](https://prometheus.io/docs/instrumenting/exposition_formats/#comments-help-text-and-type-information).
So in order for Prometheus to scrape those metrics, they must be transparently transformed from JSON to its own format on every request.

### Differences

Other than metrics-server itself, this Docker container provides additional metrics metadata that are
retrieved via `kubectl` API calls and included in the Prometheus output.

### How does it work

The following diagram illustrates how the format transformation is achieved:

[![workflow](doc/metrics-server-prom-adapter.png)](doc/metrics-server-prom-adapter.png)

1. Prometheus scrapes the Docker container on `:9100/metrics`
2. Inside the Docker container [uwsgi](https://github.com/unbit/uwsgi) is proxying the request to [kube proxy](https://kubernetes.io/docs/reference/command-line-tools-reference/kube-proxy/)
3. kube-proxy reads the provided config file and tunnels the request into Kubernetes to metrics-server
4. metrics-server replies with JSON formatted metrics
5. kube proxy forwards the request back to uwsgi
6. uwsgi calls [transform.py](data/src/transform.py)
7. transform.py rewrites the JSON into Prometheus readable output and hands the result back to uwsgi
8. uwsgi sends the final response back to Prometheus


## Usage

### Run metrics-server-prom

Simply run the Docker image with a kube config mounted into `/etc/kube/config`.

```bash
$ docker run -d \
    -p 9100:9100 \
    -v ${HOME}/.kube/config:/etc/kube/config:ro \
    cytopia/metrics-server-prom
```
If your kube config contains multiple contexts, you can tell `metrics-server-prom` what context
to use, to connect to the cluster.

```bash
$ docker run -d \
    -p 9100:9100 \
    -v ${HOME}/.kube/config:/etc/kube/config:ro \
    -e KUBE_CONTEXT=my-context \
    cytopia/metrics-server-prom
```

### Configure Prometheus

`prometheus.yml`:
```yml
scrape_configs:
  - job_name: 'kubernetes'
    scrape_interval: '15s'
    metrics_path: '/metrics'
    static_configs:
      - targets:
        - <DOCKER_IP_ADDRESS>:9100
```

## Docker Compose

To test this out locally, this repository ships an example Docker Compose setup with
metrics-server-prom and Prometheus.

1. Navigate to [example/](example/)
2. Copy `env-example` to `.env`
3. Adjust `KUBE_CONTEXT` in `.env`
4. Run it `docker-compose up`


## Metrics transformation

metrics-server provices metrics in the following format:
```json
{
  "kind": "PodMetricsList",
  "apiVersion": "metrics.k8s.io/v1beta1",
  "metadata": {
    "selfLink": "/apis/metrics.k8s.io/v1beta1/pods"
  },
  "items": [
    {
      "metadata": {
        "name": "etcd-server-events-abc",
        "namespace": "kube-system",
        "selfLink": "/apis/metrics.k8s.io/v1beta1/namespaces/kube-system/pods/etcd-server-events-ip-10-30-78-99.eu-central-1.compute.internal",
        "creationTimestamp": "2018-08-20T03:19:05Z"
      },
      "timestamp": "2018-08-20T03:19:00Z",
      "window": "1m0s",
      "containers": [
        {
          "name": "etcd-container",
          "usage": {
            "cpu": "7m",
            "memory": "125448Ki"
          }
        }
      ]
    },

  ]
}
```

metrics-server-prom transforms it to the following format:

**Note:** Additional metadata (`node` and `ip`) have been added.
```
# HELP kube_metrics_server_pod_cpu The CPU time of a pod in seconds.
# TYPE kube_metrics_server_pod_cpu gauge
kube_metrics_server_pod_cpu{node="ip-10-30-78-99.eu-central-1.compute.internal",pod="etcd-server-events-abc",ip="10.30.62.138",container="etcd-container",namespace="kube-system",window="1m0s"} 420
# HELP kube_metrics_server_pod_mem The memory of a pod in KiloBytes.
# TYPE kube_metrics_server_pod_mem gauge
kube_metrics_server_pod_mem{node="ip-10-30-78-99.eu-central-1.compute.internal",pod="etcd-server-events-abc",ip="10.30.62.138",container="etcd-container",namespace="kube-system",window="1m0s"} 128475136
```

## License

[MIT License](LICENSE)

Copyright (c) 2018 [cytopia](https://github.com/cytopia)
