$ErrorActionPreference = "Stop"

# Load local environment settings if present
$EnvFile = Join-Path $PSScriptRoot ".env.ps1"
if (Test-Path -LiteralPath $EnvFile) {
    . $EnvFile
}

$Vm = if (![string]::IsNullOrWhiteSpace($env:DEPLOY_VM)) { $env:DEPLOY_VM } else { "luonggminh05@192.168.18.129" }
$RemoteApp = if (![string]::IsNullOrWhiteSpace($env:DEPLOY_REMOTE_APP)) { $env:DEPLOY_REMOTE_APP } else { "/home/luonggminh05/Rag" }
$Kubectl = "sudo KUBECONFIG=/etc/rancher/rke2/rke2.yaml /var/lib/rancher/rke2/bin/kubectl"
$Ctr = "sudo /var/lib/rancher/rke2/bin/ctr -a /run/k3s/containerd/containerd.sock -n k8s.io"

Write-Host "1. Re-creating remote application directory on VM..."
ssh -t $Vm "mkdir -p $RemoteApp && rm -rf $RemoteApp/*"

Write-Host "2. Copying Python service directories and files to VM..."
# Copy app directory
scp -r "$PSScriptRoot\app" $Vm`:$RemoteApp/
# Copy other configurations
scp "$PSScriptRoot\requirements.txt" $Vm`:$RemoteApp/
scp "$PSScriptRoot\Dockerfile" $Vm`:$RemoteApp/
scp "$PSScriptRoot\rag-python.yaml" $Vm`:$RemoteApp/
if (Test-Path "$PSScriptRoot\ollama-pod.yaml") {
    scp "$PSScriptRoot\ollama-pod.yaml" $Vm`:$RemoteApp/
}

Write-Host "3. Building Docker image and importing into RKE2 containerd..."
ssh -t $Vm "cd $RemoteApp && sudo docker build -t rag_api_python:latest -f Dockerfile . && sudo docker save rag_api_python:latest -o images.tar && $Ctr images import images.tar && sudo rm -f images.tar"

Write-Host "4. Applying Kubernetes manifests..."
ssh -t $Vm "$Kubectl apply -f $RemoteApp/rag-python.yaml"
ssh -t $Vm "if [ -f $RemoteApp/ollama-pod.yaml ]; then $Kubectl apply -f $RemoteApp/ollama-pod.yaml; fi"

Write-Host "5. Restarting application pods..."
ssh -t $Vm "$Kubectl delete pod -l app=rag-python-service --force --grace-period=0 --ignore-not-found=true"

Write-Host "Done! Python RAG API deployed and running on NodePort 30001."
