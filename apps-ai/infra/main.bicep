// Shared runtime for the Apps & AI gallery demos: a public frontend Container
// App that proxies /api to an internal-only backend Container App, which calls
// an existing Foundry project with its system-assigned managed identity.
//
// The gallery backend provisions the Foundry account, project, and model first
// (so it can fall back across models on quota errors), then deploys this
// template into the same resource group. Compile with:
//   az bicep build --file apps-ai/infra/main.bicep --outfile demos/_apps/container-apps.json
targetScope = 'resourceGroup'

@description('Gallery app id, used for tags and telemetry.')
param appId string

@description('Short lowercase prefix for resource names (max 8 characters).')
@maxLength(8)
param namePrefix string

param location string = resourceGroup().location

@description('Existing Foundry (AIServices) account in this resource group.')
param foundryAccountName string

@description('Existing Foundry project under the account.')
param foundryProjectName string

@description('Model deployment name the backend uses by default.')
param modelDeploymentName string

@description('Public backend container image.')
param backendImage string

@description('Public frontend container image.')
param frontendImage string

@description('Port the backend container listens on.')
param backendPort int

@description('Port the frontend container listens on.')
param frontendPort int = 8080

@description('Additional backend environment variables ({name, value}).')
param backendEnv array = []

@description('IPv4 CIDR ranges allowed to reach the frontend. Empty means public.')
param allowedIpRanges array = []

var suffix = take(uniqueString(resourceGroup().id, appId), 8)
var tags = {
  'fdg-app': appId
  purpose: 'fabric-demo-gallery'
}
var projectEndpoint = 'https://${foundryAccountName}.services.ai.azure.com/api/projects/${foundryProjectName}'
var ipRestrictions = [for (range, i) in allowedIpRanges: {
  name: 'allow-${i}'
  ipAddressRange: range
  action: 'Allow'
}]
var azureAiUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

resource logs 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: 'log-${namePrefix}-${suffix}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${namePrefix}-${suffix}'
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${namePrefix}-${suffix}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource backend 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-api-${suffix}'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: backendPort
        transport: 'auto'
        allowInsecure: false
      }
      secrets: [
        {
          name: 'applicationinsights-connection-string'
          value: appInsights.properties.ConnectionString
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: backendImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat([
            {
              name: 'AZURE_AI_PROJECT_ENDPOINT'
              value: projectEndpoint
            }
            {
              name: 'AZURE_FOUNDRY_MODEL'
              value: modelDeploymentName
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              secretRef: 'applicationinsights-connection-string'
            }
            {
              name: 'OTEL_AGENT_ID'
              value: appId
            }
          ], backendEnv)
        }
      ]
      // In-process run state (Demand Portfolio Planning) requires one replica.
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

resource azureAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundryAccount
  name: guid(foundryAccount.id, backend.id, azureAiUserRoleId)
  properties: {
    principalId: backend.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureAiUserRoleId)
  }
}

// Document Intelligence (prebuilt-layout) and the deployments listing use the
// Cognitive Services data plane on the same AIServices account.
resource cognitiveServicesUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundryAccount
  name: guid(foundryAccount.id, backend.id, cognitiveServicesUserRoleId)
  properties: {
    principalId: backend.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
  }
}

resource frontend 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-web-${suffix}'
  location: location
  tags: tags
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: frontendPort
        transport: 'auto'
        allowInsecure: false
        ipSecurityRestrictions: ipRestrictions
      }
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: frontendImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'BACKEND_URL'
              value: 'https://${backend.properties.configuration.ingress.fqdn}'
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

output frontendUrl string = 'https://${frontend.properties.configuration.ingress.fqdn}'
output frontendAppName string = frontend.name
output backendAppName string = backend.name
output appInsightsName string = appInsights.name
