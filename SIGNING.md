# Windows code signing setup

Prepared 2026-11-19. The existing executable is unsigned. The manual
`Build and sign Windows app` workflow is prepared but cannot sign until a public
trust signing identity has been issued and configured. No paid Azure resources
are created by the workflow or this documentation.

## Recommended service and cost

For an individual developer in the USA/Canada, Microsoft Azure Artifact Signing
(formerly Trusted Signing) supports public-trust Windows signing. Microsoft's
published Basic price is USD $9.99/month per signing account, including 5,000
signatures, with $0.005 per additional signature. The monthly account fee is not
prorated. A paid Azure subscription is required; free/trial/sponsored
subscriptions are not supported. Confirm current pricing before creating it.

Signing establishes a verified publisher and protects file integrity. It does
not guarantee instant SmartScreen reputation or eliminate antivirus warnings.

## One-time Azure setup (account owner)

1. Sign in to the [Azure portal](https://portal.azure.com/) and select the paid
   subscription you intend to bill. Do not upgrade/create paid resources until
   you approve the recurring charge.
2. Register the `Microsoft.CodeSigning` resource provider for that subscription.
3. Create an **Artifact Signing account**, Basic tier. Suggested resource group:
   `rg-icc-signing`; account name: an available name such as `pmatraiccsigning`;
   region: **East US**. These are suggestions, not resources already provisioned.
   Review the subscription, region and recurring price before Review + Create.
4. Assign yourself the **Artifact Signing Identity Verifier** role if needed.
   Start **Public Trust / Individual developer** identity validation in the
   account. For Individual Developer validation, the Azure billing account must have Account Type **Individual**; its legal name and sold-to address must match the government ID used for validation. Review these details in Azure first. Use your actual legal identity and complete Microsoft's requested
   verification yourself in the portal. Do not send identity documents,
   passwords or payment details through this repository or chat.
5. Wait for identity validation approval. It may require additional steps or
   several business days. Create a **Public Trust** certificate profile linked
   to that approved identity, for example `iccinspectorpublic`. Do not use a
   Private Trust/Test profile for public GitHub downloads.

The executable cannot honestly be described as publicly signed before these
steps finish. No self-signed substitute is used.

## Connect GitHub without storing a certificate or client secret

1. In Microsoft Entra ID, create an app registration/service principal for this
   repository, for example `ICC Inspector GitHub Signing`.
2. Add a federated credential for GitHub Actions:
   - Issuer: `https://token.actions.githubusercontent.com`
   - Organization/user: `pmatra`
   - Repository: `Printer-Profile-Inspector`
   - Entity: **Environment**; environment name: `release-signing`
   - Subject: `repo:pmatra/Printer-Profile-Inspector:environment:release-signing`
   - Audience: `api://AzureADTokenExchange`
3. Assign the app's service principal the **Artifact Signing Certificate Profile
   Signer** role, scoped to the intended certificate profile where supported.
   Azure login also needs visibility of the selected subscription; give it
   Reader at the resource group if needed. Do not give this signing identity
   Owner/Contributor merely to sign.
4. In GitHub repository Settings → Environments, create `release-signing`.
   Restrict deployment branches to `main` and configure a required reviewer.
5. Set the following **environment variables** (not Python source code):

   | GitHub environment variable | Value |
   | --- | --- |
   | `AZURE_CLIENT_ID` | Entra app registration Application/client ID |
   | `AZURE_TENANT_ID` | Entra directory/tenant ID |
   | `AZURE_SUBSCRIPTION_ID` | The paid subscription ID |
   | `SIGNING_ENDPOINT` | For East US: `https://eus.codesigning.azure.net/` |
   | `SIGNING_ACCOUNT_NAME` | The created Artifact Signing account name |
   | `SIGNING_CERTIFICATE_PROFILE` | The approved Public Trust profile name |

   The endpoint must match the account/profile region. These identifiers are
   configuration values, not private keys. The workflow uses GitHub OIDC and
   Azure CLI credentials; no PFX, private key or Azure client secret is uploaded.

## First signed build

Run `Build and sign Windows app` from the repository Actions tab on **main**.
Approve the protected environment when prompted. The workflow installs the
locked dependencies, runs the regression suite, builds the program, signs only
the application's own EXE, adds an RFC3161 timestamp, and verifies the trusted
signature and timestamp before producing an artifact.

Download `verified-signed-windows`: it contains the signed ZIP, SHA-256 checksum,
and a JSON record of publisher, source commit and signature status. Publish that
verified ZIP as a new release asset; do not silently relabel an old unsigned ZIP
as signed. Recompute checksums after signing. Existing vendor DLLs retain their
original signatures/licenses and are not re-signed as Peter Matra's code.

## Official references

- [Windows signing options, eligibility and SmartScreen](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)
- [Artifact Signing account and identity setup](https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart)
- [Pricing tiers](https://learn.microsoft.com/en-us/azure/artifact-signing/how-to-change-sku)
- [Subscription restrictions and billing FAQ](https://learn.microsoft.com/en-us/azure/artifact-signing/faq)
- [Official GitHub signing action](https://github.com/Azure/artifact-signing-action)
- [Azure login with GitHub OIDC](https://github.com/Azure/login)
