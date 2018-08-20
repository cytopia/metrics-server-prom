#!/usr/bin/env bash

# Be strict
set -e
set -u
set -o pipefail

export KUBECONFIG=/etc/kube/config

# Function to store stdout and stderr in two different variables
# https://stackoverflow.com/questions/11027679/capture-stdout-and-stderr-into-different-variables
catch()
{
	eval "$({
	__2="$(
		{ __1="$("${@:3}")"; } 2>&1;
		ret=$?;
		printf '%q=%q\n' "$1" "$__1" >&2;
		exit $ret
		)"
	ret="$?";
	printf '%s=%q\n' "$2" "$__2" >&2;
	printf '( exit %q )' "$ret" >&2;
	} 2>&1 )";
}



###
### Check existance of kube config
###
printf "[init] Checking for kube config ..."

if [ ! -f "${KUBECONFIG}" ]; then
	>&2 echo "FAILED"
	>&2 echo "[init] Error, ${KUBECONFIG} file does not exist."
	>&2 echo "[init] You should mount kube config via '-v \$(pwd)/.kube/config:${KUBECONFIG}:ro'"
	exit 1
fi
printf "OK\n"


###
### Set custom kube context
###
if printenv KUBE_CONTEXT >/dev/null 2>&1; then
	echo "[init] KUBE_CONTEXT set, using user specified context: ${KUBE_CONTEXT}"
	printf "[init] Checking kube context ..."
	if ! ERROR="$( (kubectl config use-context ${KUBE_CONTEXT} 3>&2 2>&1 1>&3) 2>/dev/null) )"; then
		>&2 echo "FAILED"
		>&2 echo "[init] Error, invalid kube context"
		>&2 echo "[init] ${ERROR}"
		exit 1
	fi
	printf "OK\n"
else
	echo "[init] KUBE_CONTEXT not set, relying on context set in ${KUBECONFIG}"
fi


###
### Check current context
###
printf "[init] Checking current kube context ..."
if ! catch CONTEXT ERROR kubectl config current-context; then
	>&2 echo "FAILED"
	>&2 echo "[init] Error, invalid kube context"
	>&2 echo "[init] ${ERROR}"
	exit 1
else
	printf "OK\n"
	printf "[init] Current context: %s\n" "${CONTEXT}"
fi


###
### Check Kubernetes cluster reachability
###
printf "[init] Checking cluster info ..."
if ! ERROR="$( (kubectl cluster-info --request-timeout='5s' 3>&2 2>&1 1>&3) 2>/dev/null) )"; then
	>&2 echo "FAILED"
	>&2 echo "[init] Error, could not use provided kube config to validate against the cluster"
	>&2 echo "[init] ${ERROR}"
	exit 1
fi
printf "OK\n"


###
### Start up
###
exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
