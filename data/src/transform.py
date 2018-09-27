# -*- coding: utf-8 -*-
'''
Auther:  cytopia
License: MIT

Transformer for kubernetes-incubator/metrics-server from json
into Prometheus readable format.
'''

import os
import json
import re
import time
import requests
import subprocess
from flask import Flask
from flask import Response


'''
Globals that specify at which url metrics for nodes and pods can be found
'''
PROXY = 'http://127.0.0.1:8080'
URL_NODES = PROXY + '/apis/metrics.k8s.io/v1beta1/nodes'
URL_PODS = PROXY + '/apis/metrics.k8s.io/v1beta1/pods'

def shell_exec(command):
    '''
    Execute raw shell command and return exit code and output

    Args:
        command (str): Command to execute
    Returns:
        tuple (int, str, str): Returns exit code, stdout and stderr
    '''
    # Get absolute path of bash
    bash = os.popen('command -v bash').read().rstrip('\r\n')
    cpt = subprocess.Popen(
        command,
        executable=bash,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait until process terminates (without using p.wait())
    while cpt.poll() is None:
        # Process hasn't exited yet, let's wait some more time
        time.sleep(0.1)

    # Get stdout, stderr and return code
    stdout, stderr = cpt.communicate()
    return_code = 0 #cpt.returncode

    return return_code, stdout, stderr


def json2dict(data):
    '''
    Safely convert a potential JSON string into a dict

    Args:
        data (str): Valid or invalid JSON string.
    Returns:
        dict: Returns dict of string or empty dict in case of invalid JSON input.
    '''
    json_object = dict()
    try:
        json_object = json.loads(data)
    except ValueError:
        pass
    return json_object


def val2base(string):
    '''
    Transforms an arbitrary string value into a prometheus valid base (int|float) type by best guess:
    https://prometheus.io/docs/instrumenting/exposition_formats/#comments-help-text-and-type-information
    https://golang.org/pkg/strconv/#ParseFloat
    https://golang.org/pkg/strconv/#ParseInt

    Currently able to handle values of:
      15Ki
      15Mi
      15Gi
      1m0s
      5m

    Args:
        string (str): metrics-server metrics value
    Returns:
        int|float|string: transformed value or initial value if no transformation regex was found.
    '''

    # Transform KiloByte into Bytes
    val = re.search('^([0-9]+)Ki$', string, re.IGNORECASE)
    if val and val.group(1):
        return int(val.group(1)) * 1024
    # Transform Megabytes into Bytes
    val = re.search('^([0-9]+)Mi$', string, re.IGNORECASE)
    if val and val.group(1):
        return int(val.group(1)) * (1024*1024)
    # Transform Gigabytes into Bytes
    val = re.search('^([0-9]+)Gi$', string, re.IGNORECASE)
    if val and val.group(1):
        return int(val.group(1)) * (1024*1024*1024)
    # Transform Terrabytes into Bytes
    val = re.search('^([0-9]+)Ti$', string, re.IGNORECASE)
    if val and val.group(1):
        return int(val.group(1)) * (1024*1024*1024*1024)

    # Transform hours, minutes and seconds into seconds
    val = re.search('^(([0-9]+)\s*h\s*)?(([0-9]+)\s*m\s*)?(([0-9]+)\s*s\s*)?$', string, re.IGNORECASE)
    if val and (val.group(2) or val.group(4) or val.group(6)):
        return (
            (int(val.group(2) or 0) * 60 * 60) +
            (int(val.group(4) or 0) * 60) +
            (int(val.group(6) or 0))
        )

    # Otherwise return value as it came in
    return string


def trans_node_metrics(string):
    '''
    Transforms metrics-server node metrics (in the form of a JSON string) into Prometheus
    readable metrics format (text-based).
    https://prometheus.io/docs/instrumenting/exposition_formats/
    https://en.wikipedia.org/wiki/Extended_Backus%E2%80%93Naur_form

    Args:
        string (str): Valid or invalid JSON string.
    Returns:
        str: Returns newline separated node metrics ready for Prometheus to pull.
    '''
    data = json2dict(string)
    cpu = []
    mem = []

    cpu.append('# HELP kube_metrics_server_node_cpu The CPU time of a node in seconds.')
    cpu.append('# TYPE kube_metrics_server_node_cpu gauge')
    mem.append('# HELP kube_metrics_server_node_mem The memory of a node in Bytes.')
    mem.append('# TYPE kube_metrics_server_node_mem gauge')

    tpl = 'kube_metrics_server_node_{}{{node="{}",debugval="{}"}} {}'

    for node in data.get('items', []):
        lbl = {
            'node': node.get('metadata', []).get('name', '')
        }
        val = {
            'cpu': node.get('usage', []).get('cpu', ''),
            'mem': node.get('usage', []).get('memory', '')
        }
        cpu.append(tpl.format('cpu', lbl['node'], val['cpu'], val2base(val['cpu'])))
        mem.append(tpl.format('mem', lbl['node'], val['mem'], val2base(val['mem'])))
    return '\n'.join(cpu + mem)


def trans_pod_metrics(string):
    '''
    Transforms metrics-server pod metrics (in the form of a JSON string) into Prometheus
    readable metrics format (text-based).
    https://prometheus.io/docs/instrumenting/exposition_formats/
    https://en.wikipedia.org/wiki/Extended_Backus%E2%80%93Naur_form

    Args:
        string (str): Valid or invalid JSON string.
    Returns:
        str: Returns newline separated node metrics ready for Prometheus to pull.
    '''
    data = json2dict(string)
    more = get_pod_metrics_from_cli()
    cpu = []
    mem = []

    cpu.append('# HELP kube_metrics_server_pod_cpu The CPU time of a pod in seconds.')
    cpu.append('# TYPE kube_metrics_server_pod_cpu gauge')
    mem.append('# HELP kube_metrics_server_pod_mem The memory of a pod in Bytes.')
    mem.append('# TYPE kube_metrics_server_pod_mem gauge')

    tpl = 'kube_metrics_server_pod_{}{{node="{}",pod="{}",ip="{}",container="{}",namespace="{}",debugval="{}"}} {}'

    for pod in data.get('items', []):
        lbl = {
            'pod': pod.get('metadata', []).get('name', ''),
            'ns': pod.get('metadata', []).get('namespace', '')
        }
        # Loop over defined container in each pod
        for container in pod.get('containers', []):
            lbl['cont'] = container.get('name', '')
            val = {
                'cpu': container.get('usage', []).get('cpu', ''),
                'mem': container.get('usage', []).get('memory', '')
            }
            cpu.append(tpl.format(
                'cpu',
                more[lbl['pod']]['node'],
                lbl['pod'],
                more[lbl['pod']]['ip'],
                lbl['cont'],
                lbl['ns'],
                val['cpu'],
                val2base(val['cpu'])
            ))
            mem.append(tpl.format(
                'mem',
                more[lbl['pod']]['node'],
                lbl['pod'],
                more[lbl['pod']]['ip'],
                lbl['cont'],
                lbl['ns'],
                val['mem'],
                val2base(val['mem'])
            ))
    return '\n'.join(cpu + mem)


def get_pod_metrics_from_cli():
    '''
    Get pod metrics via CLI (allows to have node for enriching the data)

    Returns
        data: Dictionary of additional pod metrics
    '''

    data = dict()
    command = 'kubectl get pods -o wide --no-headers --all-namespaces'
    ret, out, err = shell_exec(command)

    # 1:NS | 2:Name | 3:Ready | 4:Status | 5:Restarts | 6:Age | 7:IP | 8:Node
    reg = re.compile(r"^([^ ]+)\s+([^ ]+)\s+([^ ]+)\s+([^ ]+)\s+([^ ]+)\s+([^ ]+)\s+([^ ]+)\s+([^ ]+)$")

    for line in out.splitlines():
        line = line.decode("utf-8")
        line = reg.match(line)

        data[line.group(2)] = {
            'ns': line.group(1),
            'name': line.group(2),
            'ready': line.group(3),
            'status': line.group(4),
            'restarts': line.group(5),
            'age': line.group(6),
            'ip': line.group(7),
            'node': line.group(8)
        }

    return data


application = Flask(__name__) # pylint: disable=invalid-name

@application.route("/metrics")
def metrics():
    '''
    This function is the /metrics http entrypoint and will itself do two callbacks
    to the running kubectl proxy in order to gather node and pod metrics from specified
    kubernetes api urls. Current output is JSON and we must therefore transform both results
    into Prometheus readable format:
        https://prometheus.io/docs/instrumenting/exposition_formats/
        https://en.wikipedia.org/wiki/Extended_Backus%E2%80%93Naur_form
    '''
    # Get info from K8s API
    req = {
        'nodes': requests.get(URL_NODES),
        'pods': requests.get(URL_PODS)
    }

    # Object to JSON text
    json = {
        'nodes': req['nodes'].text,
        'pods': req['pods'].text
    }

    # Convert to Prometheus format
    prom = {
        'nodes': trans_node_metrics(json['nodes']),
        'pods': trans_pod_metrics(json['pods'])
    }
    get_pod_metrics_from_cli()
    # Return response
    return Response(prom['nodes'] + '\n' + prom['pods'], status=200, mimetype='text/plain')


@application.route("/healthz")
def healthz():
    '''
    This function is the /healthz http entrypoint and will itself do two callbacks
    in order to determine the health of node and pod metric endpoints.

    Returns:
        Response: Flask Response object that will handle returning http header and body.
                  If one of the pages (nodes or pods metrics by metrics-server) fails,
                  it will report an overall failure and respond with 503 (service unavailable).
                  If both a good, it will respond with 200.
    '''
    req = {
        'nodes': requests.get(URL_NODES),
        'pods': requests.get(URL_PODS)
    }
    health = 'ok'
    status = 200
    if req['nodes'].status_code != 200:
        health = 'failed'
        status = 503
    if req['pods'].status_code != 200:
        health = 'failed'
        status = 503

    return Response(health, status=status, mimetype='text/plain')


@application.route("/")
def index():
    '''
    This function is the / http entrypoint and will simply provide a link to
    the metrics and health page. This is done, because all metrics endpoints I have encountered
    so far also do it exactly this way.

    Returns:
        Response: Flask Response object that will handle returning http header and body.
                  Returns default Prometheus endpoint index page (http 200) with links
                  to /healthz and /metrics.
    '''
    return '''
        <html>
        <head><title>metrics-server-prom</title></head>
        <body>
            <h1>metrics-server-prom</h1>
	    <ul>
                <li><a href='/metrics'>metrics</a></li>
                <li><a href='/healthz'>healthz</a></li>
	    </ul>
        </body>
        </html>
    '''

if __name__ == "__main__":
    application.run(host='0.0.0.0')
