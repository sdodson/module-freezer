IMAGE ?= quay.io/sdodsonrht/module-freezer
TAG ?= latest

.PHONY: build push deploy deploy-openshift clean

build:
	podman build -t $(IMAGE):$(TAG) .

push: build
	podman push $(IMAGE):$(TAG)

deploy:
	kubectl apply -f deploy/namespace.yaml
	kubectl apply -f deploy/serviceaccount.yaml
	kubectl apply -f deploy/clusterrole.yaml
	kubectl apply -f deploy/clusterrolebinding.yaml
	kubectl apply -f deploy/daemonset.yaml

deploy-openshift:
	oc apply -f deploy/openshift/namespace.yaml
	oc apply -f deploy/openshift/serviceaccount.yaml
	oc apply -f deploy/clusterrole.yaml
	oc apply -f deploy/openshift/clusterrolebinding.yaml
	oc apply -f deploy/openshift/scc.yaml
	oc apply -f deploy/openshift/scc-role.yaml
	oc apply -f deploy/openshift/daemonset.yaml

undeploy:
	kubectl delete -f deploy/daemonset.yaml --ignore-not-found
	kubectl delete -f deploy/clusterrolebinding.yaml --ignore-not-found
	kubectl delete -f deploy/clusterrole.yaml --ignore-not-found
	kubectl delete -f deploy/serviceaccount.yaml --ignore-not-found
	kubectl delete -f deploy/namespace.yaml --ignore-not-found

undeploy-openshift:
	oc delete -f deploy/openshift/daemonset.yaml --ignore-not-found
	oc delete -f deploy/openshift/scc-role.yaml --ignore-not-found
	oc delete -f deploy/openshift/clusterrolebinding.yaml --ignore-not-found
	oc delete -f deploy/openshift/scc.yaml --ignore-not-found
	oc delete -f deploy/openshift/serviceaccount.yaml --ignore-not-found
	oc delete -f deploy/clusterrole.yaml --ignore-not-found
	oc delete -f deploy/openshift/namespace.yaml --ignore-not-found

clean:
	podman rmi $(IMAGE):$(TAG) || true
