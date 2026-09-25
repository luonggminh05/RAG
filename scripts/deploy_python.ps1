$ErrorActionPreference = "Stop"

# Load local environment settings if present
$EnvFile = Join-Path $PSScriptRoot ".env.ps1"
if (Test-Path -LiteralPath $EnvFile) {
    . $EnvFile
}

$ProjectRoot = (Get-Item $PSScriptRoot).Parent.FullName

$Vm = if (![string]::IsNullOrWhiteSpace($env:DEPLOY_VM)) { $env:DEPLOY_VM } else { "user@your-server-ip" }
$RemoteApp = if (![string]::IsNullOrWhiteSpace($env:DEPLOY_REMOTE_APP)) { $env:DEPLOY_REMOTE_APP } else { "/home/user/rag" }
$Kubectl = "sudo KUBECONFIG=/etc/rancher/rke2/rke2.yaml /var/lib/rancher/rke2/bin/kubectl"
$Ctr = "sudo /var/lib/rancher/rke2/bin/ctr -a /run/k3s/containerd/containerd.sock -n k8s.io"

Write-Host "1. Re-creating remote application directory on VM..."
ssh -t $Vm "mkdir -p $RemoteApp/configs $RemoteApp/infra/docker $RemoteApp/infra/k8s && rm -rf $RemoteApp/app $RemoteApp/configs/* $RemoteApp/infra/*"

Write-Host "2. Copying Python service directories and files to VM..."
# Copy app and ui directory
scp -r "$ProjectRoot\app" $Vm`:$RemoteApp/
scp -r "$ProjectRoot\ui" $Vm`:$RemoteApp/
# Copy configs and infra
scp "$ProjectRoot\configs\requirements.txt" $Vm`:$RemoteApp/configs/
scp "$ProjectRoot\infra\docker\Dockerfile" $Vm`:$RemoteApp/Dockerfile
scp "$ProjectRoot\infra\k8s\rag-python.yaml" $Vm`:$RemoteApp/rag-python.yaml

Write-Host "3. Building Docker image and importing into RKE2 containerd..."
ssh -t $Vm "cd $RemoteApp && sudo docker build -t rag_api_python:latest -f Dockerfile . && sudo docker save rag_api_python:latest -o images.tar && $Ctr images import images.tar && sudo rm -f images.tar"

Write-Host "4. Applying Kubernetes manifests..."
ssh -t $Vm "$Kubectl apply -f $RemoteApp/rag-python.yaml"

Write-Host "5. Restarting application pods..."
ssh -t $Vm "$Kubectl delete pod -l app=rag-python-service --force --grace-period=0 --ignore-not-found=true"

Write-Host "Done! Python RAG API deployed and running on NodePort 30001."
