# Local login and a new ZIP import

Open **http://127.0.0.1:5181** and use **admin@projecttrace.local** with the password already provided in this chat. The account and password are unchanged. These are local ProjectTrace credentials; no provider account is required.

1. Sign in with email/password.
2. Open **Repositories** from the left navigation.
3. Choose **Import repository**.
4. Leave the destination as **New repository**, enter a new name, choose your ZIP and submit.
5. Select that repository in the header to inspect its job, claims, evidence, findings and dependency coverage.
6. To compare a later version, use **Upload new snapshot** on that repository. It preserves the prior snapshot instead of creating another repository.

**Explore Northstar demo** opens the separate labeled demo organization. Source imports are rejected there. Your two existing smart-waste repositories and their history remain in your real workspace; neither prevents importing another ZIP.

The source bundle excludes the existing local database, passwords, sessions and encryption keys. For a separate fresh installation, create a local workspace after following README startup instructions. PowerShell prompts for the password without writing it into a file:

```powershell
$taskEmail = Read-Host 'New local email'
$taskSecret = Read-Host 'New password (at least 16 characters)' -AsSecureString
$taskCredential = [System.Management.Automation.PSCredential]::new($taskEmail, $taskSecret)
$taskPayload = @{email=$taskEmail; password=$taskCredential.GetNetworkCredential().Password; organization='ProjectTrace'} | ConvertTo-Json
$taskAccount = Invoke-RestMethod -Uri 'http://127.0.0.1:8011/api/auth/register' -Method Post -ContentType 'application/json' -Headers @{Origin='http://127.0.0.1:5181'} -Body $taskPayload
Remove-Variable taskPayload,taskCredential,taskSecret
$taskAccount | Select-Object email,role,organization
```

Then sign in through the browser. Local registration is disabled in production. Native analysis reads source as data; it does not execute the imported application or install its dependencies.
