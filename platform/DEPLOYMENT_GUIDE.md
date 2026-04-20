# 🚀 DevOps Platform - Deployment Guide

## Prerequisites

Before deploying, ensure you have:

1. **Kubernetes cluster** (EKS / kubeadm / k3s) running and accessible via `kubectl`
2. **Helm v3.12+** installed
3. **kubectl** configured with cluster-admin access
4. **Domain** pointed to your cluster's external IP (A or CNAME record)
5. **GitHub** repository access configured

## Quick Reference - Subdomain Mapping

| Subdomain | Service | Purpose |
|---|---|---|
| `argocd.yourdomain.com` | ArgoCD | GitOps deployment dashboard |
| `grafana.yourdomain.com` | Grafana | Monitoring & observability |
| `keycloak.yourdomain.com` | Keycloak | Identity & access management |
| `app.yourdomain.com` | Frontend UI | E-Commerce application |
| `api.yourdomain.com` | API Gateway | Backend API endpoint |

---

## Step 1: Install HAProxy Ingress Controller

```bash
# Add Helm repo
helm repo add haproxytech https://haproxytech.github.io/helm-charts
helm repo update

# Create namespace
kubectl create namespace haproxy-ingress

# Install HAProxy Ingress
helm install haproxy-ingress haproxytech/kubernetes-ingress \
  --namespace haproxy-ingress \
  --set controller.kind=DaemonSet \
  --set controller.ingressClass=haproxy \
  --set controller.service.type=LoadBalancer

# Verify
kubectl get pods -n haproxy-ingress
kubectl get svc -n haproxy-ingress
```

> **Note the EXTERNAL-IP** from the LoadBalancer service — point your domain's DNS here.

---

## Step 2: Install cert-manager

```bash
# Add Helm repo
helm repo add jetstack https://charts.jetstack.io
helm repo update

# Install cert-manager with CRDs
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --set installCRDs=true

# Verify
kubectl get pods -n cert-manager

# Apply ClusterIssuers (update email in the file first)
kubectl apply -f platform/ingress/templates/cluster-issuer.yaml
```

---

## Step 3: Install Keycloak

```bash
# Apply the Keycloak chart (contains all templates)
kubectl create namespace keycloak-ns
helm install keycloak platform/keycloak -n keycloak-ns

# Wait for pods
kubectl get pods -n keycloak-ns -w

# Apply the ingress route
kubectl apply -f platform/ingress/templates/ingress-routes/keycloak-ingress.yaml

# Access Keycloak
# URL: https://keycloak.yourdomain.com
# Admin: admin / admin (change in production!)
```

### Configure K8s API Server for OIDC (EKS)

For EKS, update the cluster config:

```bash
aws eks update-cluster-config --name YOUR_CLUSTER \
  --kubernetes-network-config \
  --authentication-mode API_AND_CONFIG_MAP

# Add OIDC provider to kube-apiserver (for self-managed clusters):
# --oidc-issuer-url=https://keycloak.yourdomain.com/realms/devops-platform
# --oidc-client-id=kubernetes
# --oidc-username-claim=preferred_username
# --oidc-groups-claim=groups
```

### Apply K8s OIDC RBAC

```bash
kubectl apply -f platform/keycloak/templates/kubernetes-oidc-rbac.yaml
```

### Configure kubectl for OIDC Login

```bash
# Install kubelogin plugin
kubectl krew install oidc-login

# Configure kubectl
kubectl config set-credentials oidc-user \
  --exec-api-version=client.authentication.k8s.io/v1beta1 \
  --exec-command=kubectl \
  --exec-arg=oidc-login \
  --exec-arg=get-token \
  --exec-arg=--oidc-issuer-url=https://keycloak.clahanfashion.shop/realms/devops-platform \
  --exec-arg=--oidc-client-id=kubernetes \
  --exec-arg=--oidc-client-secret=kubernetes-oidc-secret

# Use the OIDC user
kubectl config set-context --current --user=oidc-user
```

---

## Step 4: Install ArgoCD

```bash
# Add Helm repo
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update

# Create namespace
kubectl create namespace argocd

# Install ArgoCD with custom values (includes OIDC config)
helm install argocd argo/argo-cd \
  --namespace argocd \
  -f platform/argocd/install/values.yaml

# Apply RBAC policies
kubectl apply -f platform/argocd/projects/

# Apply the ingress route
kubectl apply -f platform/ingress/templates/ingress-routes/argocd-ingress.yaml

# Verify
kubectl get pods -n argocd
```

---

## Step 5: Install Argo Rollouts

```bash
# Install Argo Rollouts controller
helm install argo-rollouts argo/argo-rollouts \
  --namespace argo-rollouts \
  --create-namespace \
  -f platform/argo-rollouts/install/values.yaml

# Verify
kubectl get pods -n argo-rollouts
```

---

## Step 6: Install Monitoring Stack

```bash
# Add Helm repos
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Create namespace
kubectl create namespace monitoring

# Install kube-prometheus-stack (Prometheus + Grafana + Alertmanager)
# Extract values from the ConfigMap first, or use directly:
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  -f platform/monitoring/templates/prometheus-values.yaml

# Install Loki stack (Loki + Promtail)
helm install loki grafana/loki-stack \
  --namespace monitoring \
  -f platform/monitoring/templates/loki-values.yaml

# Apply Grafana dashboards
kubectl apply -f platform/monitoring/templates/grafana-dashboards/

# Apply Grafana ingress
kubectl apply -f platform/ingress/templates/ingress-routes/grafana-ingress.yaml

# Verify
kubectl get pods -n monitoring
```

---

## Step 7: Bootstrap with App-of-Apps

This is the **final step** — applying the root Application bootstraps everything through ArgoCD:

```bash
# Apply the App-of-Apps (this is the ONLY manual apply needed)
kubectl apply -f platform/argocd/applications/app-of-apps.yaml

# Watch all applications sync
kubectl get applications -n argocd -w
```

---

## Step 8: Verify Everything

```bash
# Check all namespaces
kubectl get pods --all-namespaces

# Check ArgoCD applications
kubectl get applications -n argocd

# Check ingress
kubectl get ingress --all-namespaces

# Check certificates
kubectl get certificates --all-namespaces

# Check Argo Rollouts (when deployed)
kubectl argo rollouts list rollouts -n clahanstore-dev
```

---

## 🔄 Frontend Blue-Green Deployment Workflow

Once Argo Rollouts are active:

```bash
# 1. Update the frontend image tag in values-override.yaml (or CI pipeline does this)
# 2. ArgoCD syncs the change → Argo Rollouts creates preview

# 3. Check rollout status
kubectl argo rollouts status frontend-ui -n clahanstore-dev

# 4. Preview the new version
kubectl argo rollouts get rollout frontend-ui -n clahanstore-dev

# 5. Promote when ready (manual in staging/prod)
kubectl argo rollouts promote frontend-ui -n clahanstore-staging

# 6. Rollback if needed
kubectl argo rollouts undo frontend-ui -n clahanstore-staging
```

---

## 📧 Alerting Setup

1. Update SMTP credentials in `platform/monitoring/values.yaml`
2. Update email recipients in:
   - `platform/argocd/install/values.yaml` (notifications section)
   - `platform/monitoring/templates/prometheus-values.yaml` (alertmanager section)
3. GitHub Actions secrets needed:
   - `SMTP_USERNAME`: Gmail address
   - `SMTP_PASSWORD`: Gmail App Password
   - `EMAIL_RECIPIENTS`: Comma-separated email list

---

## 🔑 Default Credentials (Change in Production!)

| Service | Username | Password |
|---|---|---|
| Keycloak Admin | `admin` | `admin` |
| Keycloak User (Admin) | `admin` | `admin123` |
| Keycloak User (Developer) | `developer` | `dev123` |
| Keycloak User (Viewer) | `viewer` | `view123` |
| Grafana | `admin` | `grafana-admin` |
| ArgoCD | `admin` | `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" \| base64 -d` |
