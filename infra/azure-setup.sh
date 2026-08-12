#!/usr/bin/env bash
# =============================================================================
# AcademicPregrader — one-time Azure bootstrap
# Run this ONCE in Azure Cloud Shell (Bash) or locally with the Azure CLI.
# It creates all infrastructure and wires up GitHub OIDC so the CI/CD workflow
# can deploy without storing any secret in GitHub.
#
# Cost profile: Container App scales to zero (≈$0 idle) + ACR Basic (~$5/mo)
#               + tiny Azure Files share + Log Analytics.
# =============================================================================
set -euo pipefail

# ---- EDIT THESE ------------------------------------------------------------
SUBSCRIPTION_ID="<your-subscription-id>"
GITHUB_ORG_REPO="<your-github-user>/AcademicPregrader"   # e.g. jdoe/AcademicPregrader
LOCATION="eastus"                                        # pick a region close to you
# ---------------------------------------------------------------------------

RG="rg-pregrader"
ACR_NAME="acrpregrader$RANDOM"          # must be globally unique, lowercase, alphanumeric
ENV_NAME="cae-pregrader"                # Container Apps environment
APP_NAME="pregrader"                    # Container App
STORAGE_ACCOUNT="stpregrader$RANDOM"    # must be globally unique, lowercase
FILE_SHARE="config"
STORAGE_MOUNT="configmount"
IDENTITY_NAME="id-pregrader-cicd"       # user-assigned identity for GitHub OIDC
KEY_VAULT_NAME="kvpregrader${SUBSCRIPTION_ID//-/}"
KEY_VAULT_NAME="${KEY_VAULT_NAME:0:24}" # globally unique, 3-24 chars
IMAGE_TAG="bootstrap"

az account set --subscription "$SUBSCRIPTION_ID"
az extension add --name containerapp --upgrade -y
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights

echo "==> Resource group"
az group create -n "$RG" -l "$LOCATION" -o none

echo "==> Azure Container Registry (Basic)"
az acr create -g "$RG" -n "$ACR_NAME" --sku Basic -o none

echo "==> Storage account + Azure Files share (for persistent config.ini)"
az storage account create -g "$RG" -n "$STORAGE_ACCOUNT" -l "$LOCATION" \
  --sku Standard_LRS --kind StorageV2 -o none
STORAGE_KEY=$(az storage account keys list -g "$RG" -n "$STORAGE_ACCOUNT" --query "[0].value" -o tsv)
az storage share create --account-name "$STORAGE_ACCOUNT" --account-key "$STORAGE_KEY" \
  --name "$FILE_SHARE" --quota 1 -o none

echo "==> Container Apps environment"
az containerapp env create -g "$RG" -n "$ENV_NAME" -l "$LOCATION" -o none

echo "==> Key Vault for runtime API keys"
az keyvault create -g "$RG" -n "$KEY_VAULT_NAME" -l "$LOCATION" -o none
read -rsp "OpenAI API key (stored only in Key Vault): " OPENAI_API_KEY; echo
az keyvault secret set --vault-name "$KEY_VAULT_NAME" \
  --name "openai-api-key" --value "$OPENAI_API_KEY" -o none
unset OPENAI_API_KEY

echo "==> Register the file share with the environment"
az containerapp env storage set -g "$RG" -n "$ENV_NAME" \
  --storage-name "$STORAGE_MOUNT" \
  --azure-file-account-name "$STORAGE_ACCOUNT" \
  --azure-file-account-key "$STORAGE_KEY" \
  --azure-file-share-name "$FILE_SHARE" \
  --access-mode ReadWrite -o none

echo "==> Build the first image in ACR (so the app exists before CI/CD takes over)"
az acr build -r "$ACR_NAME" -t "pregrader:$IMAGE_TAG" .

# Admin inicial: se crea en el primer arranque vía env vars (nunca en git).
ADMIN_USER="${PREGRADER_ADMIN_USER:-NICOLASD}"
read -rsp "Contraseña del admin inicial ($ADMIN_USER): " ADMIN_PASSWORD; echo

echo "==> Create the Container App (min=0, max=1 — scale to zero, single instance)"
az containerapp create -g "$RG" -n "$APP_NAME" \
  --environment "$ENV_NAME" \
  --image "$ACR_NAME.azurecr.io/pregrader:$IMAGE_TAG" \
  --registry-server "$ACR_NAME.azurecr.io" \
  --target-port 5000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 1 \
  --cpu 1.0 --memory 2.0Gi \
  --system-assigned \
  --secrets "adminpass=$ADMIN_PASSWORD" \
  --env-vars PREGRADER_CONFIG_DIR=/app/config PYTHONUNBUFFERED=1 \
             "PREGRADER_ADMIN_USER=$ADMIN_USER" "PREGRADER_ADMIN_PASSWORD=secretref:adminpass" \
  -o none

APP_PRINCIPAL_ID=$(az containerapp identity show -g "$RG" -n "$APP_NAME" \
  --query principalId -o tsv)
az keyvault set-policy --name "$KEY_VAULT_NAME" --object-id "$APP_PRINCIPAL_ID" \
  --secret-permissions get list -o none
OPENAI_SECRET_URI=$(az keyvault secret show --vault-name "$KEY_VAULT_NAME" \
  --name "openai-api-key" --query id -o tsv)
az containerapp secret set -g "$RG" -n "$APP_NAME" \
  --secrets "openai-api-key=keyvaultref:$OPENAI_SECRET_URI,identityref:system" -o none
az containerapp update -g "$RG" -n "$APP_NAME" \
  --set-env-vars "OPENAI_API_KEY=secretref:openai-api-key" -o none

echo "==> Mount Azure Files at /app/config (persists non-secret app configuration)"
# Container Apps volume mounts are applied via a YAML patch; fetch, edit, re-apply.
az containerapp show -g "$RG" -n "$APP_NAME" -o yaml > app.yaml
python3 - "$STORAGE_MOUNT" <<'PY'
import sys, yaml
mount = sys.argv[1]
with open("app.yaml") as f:
    doc = yaml.safe_load(f)
tmpl = doc["properties"]["template"]
tmpl.setdefault("volumes", [])
if not any(v.get("name") == "configvol" for v in tmpl["volumes"]):
    tmpl["volumes"].append({"name": "configvol", "storageType": "AzureFile", "storageName": mount})
c = tmpl["containers"][0]
c.setdefault("volumeMounts", [])
if not any(m.get("volumeName") == "configvol" for m in c["volumeMounts"]):
    c["volumeMounts"].append({"volumeName": "configvol", "mountPath": "/app/config"})
with open("app.yaml", "w") as f:
    yaml.safe_dump(doc, f)
PY
az containerapp update -g "$RG" -n "$APP_NAME" --yaml app.yaml -o none
rm -f app.yaml

# ---------------------------------------------------------------------------
# GitHub OIDC: user-assigned managed identity that GitHub Actions logs in as.
# ---------------------------------------------------------------------------
echo "==> User-assigned identity + federated credential for GitHub OIDC"
az identity create -g "$RG" -n "$IDENTITY_NAME" -o none
CLIENT_ID=$(az identity show -g "$RG" -n "$IDENTITY_NAME" --query clientId -o tsv)
PRINCIPAL_ID=$(az identity show -g "$RG" -n "$IDENTITY_NAME" --query principalId -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)

az identity federated-credential create \
  --name "gh-main" \
  --identity-name "$IDENTITY_NAME" \
  -g "$RG" \
  --issuer "https://token.actions.githubusercontent.com" \
  --subject "repo:${GITHUB_ORG_REPO}:ref:refs/heads/main" \
  --audiences "api://AzureADTokenExchange" -o none

echo "==> Grant the identity permission to push images and deploy the app"
ACR_ID=$(az acr show -g "$RG" -n "$ACR_NAME" --query id -o tsv)
RG_ID=$(az group show -n "$RG" --query id -o tsv)
az role assignment create --assignee "$PRINCIPAL_ID" --role "AcrPush" --scope "$ACR_ID" -o none
az role assignment create --assignee "$PRINCIPAL_ID" --role "Contributor" --scope "$RG_ID" -o none

APP_URL=$(az containerapp show -g "$RG" -n "$APP_NAME" --query properties.configuration.ingress.fqdn -o tsv)

cat <<EOF

============================================================================
 DONE. App is live at: https://$APP_URL
============================================================================
Add these as GitHub repository *Secrets* (Settings > Secrets and variables > Actions):

  AZURE_CLIENT_ID        = $CLIENT_ID
  AZURE_TENANT_ID        = $TENANT_ID
  AZURE_SUBSCRIPTION_ID  = $SUBSCRIPTION_ID

Add these as GitHub repository *Variables*:

  AZURE_RESOURCE_GROUP   = $RG
  ACR_NAME               = $ACR_NAME
  CONTAINERAPP_NAME      = $APP_NAME

The OpenAI API key is stored in Key Vault and injected into the Container App.
============================================================================
EOF
