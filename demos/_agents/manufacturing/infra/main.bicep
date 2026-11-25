// Workflow, actions and observability for the Manufacturing AI Agents pack.
// Deployed by the gallery into the pack's resource group after the Foundry
// account, project and model exist. Compile with:
//   az bicep build --file demos/_agents/manufacturing/infra/main.bicep
targetScope = 'resourceGroup'

param location string = resourceGroup().location

@description('Existing Foundry (AIServices) account in this resource group.')
param foundryAccountName string

@description('Existing Foundry project under the account.')
param foundryProjectName string

@description('Model deployment used for the workflow extraction steps and evaluations.')
param modelDeploymentName string

var suffix = take(uniqueString(resourceGroup().id), 8)
var tags = {
  'created-by': 'fabric-demo-gallery'
}
var tableDataContributor = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
var azureAiUser = '53ca6127-db72-4b80-b1b0-d745d6d5456d'
var projectEndpoint = 'https://${foundryAccountName}.services.ai.azure.com/api/projects/${foundryProjectName}'

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName

  resource project 'projects' existing = {
    name: foundryProjectName
  }
}

// ── Simulated plant systems: work orders, quality holds, approvals ─────────

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stfdg${suffix}'
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowSharedKeyAccess: false
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    // The Consumption Logic Apps reach the tables over the public endpoint
    // (Entra ID only - shared keys are disabled).
    publicNetworkAccess: 'Enabled'
  }

  resource tableService 'tableServices' = {
    name: 'default'

    resource workorders 'tables' = {
      name: 'workorders'
    }
    resource qualityholds 'tables' = {
      name: 'qualityholds'
    }
    resource approvals 'tables' = {
      name: 'approvals'
    }
  }
}

// ── Observability ──────────────────────────────────────────────────────────

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-fdg-${suffix}'
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
  name: 'appi-fdg-${suffix}'
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

// Foundry sends agent traces to the project's Application Insights connection.
resource appInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: foundry::project
  name: 'appinsights'
  properties: {
    category: 'AppInsights'
    target: appInsights.id
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: appInsights.properties.ConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsights.id
    }
  }
}

// ── Maintenance system API (used by agents as an OpenAPI tool) ─────────────

resource cmms 'Microsoft.Logic/workflows@2019-05-01' = {
  name: 'logic-plant-cmms-${suffix}'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    state: 'Enabled'
    definition: loadJsonContent('cmms.workflow.json')
    parameters: {
      storageAccount: {
        value: storage.name
      }
    }
  }
}

var cmmsCallback = listCallbackUrl('${cmms.id}/triggers/manual', '2019-05-01')

// The agents' OpenAPI tool passes the trigger signature as an API key in the query.
resource cmmsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: foundry::project
  name: 'plant-cmms'
  properties: {
    category: 'CustomKeys'
    target: '_'
    authType: 'CustomKeys'
    isSharedToAll: true
    credentials: {
      keys: {
        sig: cmmsCallback.queries.sig
      }
    }
  }
}

// ── Incident response workflow ─────────────────────────────────────────────

resource incident 'Microsoft.Logic/workflows@2019-05-01' = {
  name: 'logic-incident-response-${suffix}'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    state: 'Enabled'
    definition: loadJsonContent('incident.workflow.json')
    parameters: {
      projectEndpoint: {
        value: projectEndpoint
      }
      model: {
        value: modelDeploymentName
      }
      storageAccount: {
        value: storage.name
      }
    }
  }
}

// ── Least-privilege role assignments ───────────────────────────────────────

resource cmmsTables 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, cmms.id, tableDataContributor)
  properties: {
    principalId: cmms.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', tableDataContributor)
  }
}

resource incidentTables 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, incident.id, tableDataContributor)
  properties: {
    principalId: incident.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', tableDataContributor)
  }
}

resource incidentFoundry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundry
  name: guid(foundry.id, incident.id, azureAiUser)
  properties: {
    principalId: incident.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureAiUser)
  }
}

output cmmsBaseUrl string = cmmsCallback.basePath
output cmmsApiVersion string = cmmsCallback.queries['api-version']
output cmmsSp string = cmmsCallback.queries.sp
output cmmsSv string = cmmsCallback.queries.sv
output cmmsConnectionId string = cmmsConnection.id
output cmmsWorkflowName string = cmms.name
output incidentWorkflowName string = incident.name
output appInsightsName string = appInsights.name
output storageAccountName string = storage.name
