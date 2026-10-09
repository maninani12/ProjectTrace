# Local login and a new ZIP import

Open **http://127.0.0.1:5181** and sign in with your existing repository-owner account and password. Existing accounts are preserved; startup does not reset or seed them. No provider account is required for a ZIP import.

1. Sign in with email/password.
2. Open **Repositories** from the left navigation.
3. Choose **Import repository**.
4. Leave the destination as **New repository**, enter a new name, choose your ZIP and submit.
5. Select that repository in the header to inspect its job, claims, evidence, findings and dependency coverage.
6. To compare a later version, use **Upload new snapshot** on that repository. It preserves the prior snapshot instead of creating another repository.

**Explore Northstar demo** opens the separate labeled demo organization. Source imports are rejected there. Your two existing smart-waste repositories and their history remain in your real workspace; neither prevents importing another ZIP.

The source bundle excludes the existing local database, passwords, sessions and encryption keys. For a separate fresh installation, create a local workspace after following README startup instructions.

You can also open `http://127.0.0.1:5181/signup?next=%2Frepositories%3Fimport%3D1`, enter your own email and a password of at least 16 characters, and choose **Create workspace & continue**. This creates an empty real workspace and opens the import dialog. Choose **New repository**, select the ZIP under **Source archive**, and press **Analyze source snapshot**. Sign in later at `http://127.0.0.1:5181/login` with those same details.

Alternatively, PowerShell prompts for the password without writing it into a file:

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

## Current import choices

Use your existing repository-owner login; accounts and passwords are retained. **Import repository** offers **Upload ZIP**, **Public GitHub URL**, and **Connect private GitHub**. ZIP imports create a separate source history; only ZIP/local repositories accept later ZIP snapshots. Enter an HTTPS `github.com/owner/repository` home URL for a public one-time snapshot, and optionally a branch/tag/commit in the separate field. The resolved exact provider commit is shown with the snapshot. Private GitHub uses the existing Connections controls and operator App references.

The dialog reports actual upload/capture activity, then repository cards show persisted job stages. No fabricated progress percentage is displayed. Open **Trust & Coverage** to inspect PARTIAL, UNSUPPORTED, BINARY, policy exclusions and oversized files. Source-only hard limits default to 100,000 ZIP directory entries, 2,000,000,000 uncompressed bytes, 512,000,000 compressed bytes, 64,000,000 directory metadata bytes and compression ratio 200. Individual files over 512,000 bytes are recorded as SKIPPED_SIZE_LIMIT; that parser limit is separate from archive intake. Symbolic links are UNSUPPORTED and are never followed. Encrypted/special entries, unsafe paths and bombs are rejected with actionable codes.

Repeated submissions preserve a request identity and do not create another repository/job. **Retry analysis** operates on the retained job/input through your authenticated session. A full captured inventory does not mean analysis completed. In the 2026-10-09 `data` / `second` investigation, the original and first replay failed during native analysis; the second permitted replay actually published a PARTIAL snapshot with 92.967005% declared source parser completion. Its stored analysis time was 865.59 seconds; the external monitor took 904.11 seconds including admission and polling. The 720-second headroom target, full cold-cache qualification and complete multi-task stage resumption remain unmet. See the [current product audit](../PROJECTTRACE_PRODUCT_AUDIT_AND_READINESS.md) for timing scope, diagnostics and release blockers. Imported code, package scripts, installers, builds, Maven and Dockerfiles are never executed.
