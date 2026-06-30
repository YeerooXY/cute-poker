param(
[Parameter(Mandatory=$true)]
[string]$Message,

[switch]$SkipFullTests,
[switch]$AllowNoDocs
)

$ErrorActionPreference = "Stop"

function Run-Cmd {
param(
[Parameter(Mandatory=$true)]
[string]$Exe,

[Parameter(ValueFromRemainingArguments=$true)]
[string[]]$CommandArgs

)

Write-Host ""
Write-Host ">>> $Exe $($CommandArgs -join ' ')" -ForegroundColor Cyan
& $Exe @CommandArgs
if ($LASTEXITCODE -ne 0) {
throw "Command failed: $Exe $($CommandArgs -join ' ')"
}
}

function Get-ChangedPaths {
$paths = New-Object System.Collections.Generic.HashSet[string]

foreach ($p in (& git ls-files --modified --deleted --others --exclude-standard)) {
if ($p) {
[void]$paths.Add(($p -replace "\\", "/"))
}
}

return @($paths)
}

function Test-AnyChanged {
param(
[string[]]$Paths,
[string]$Pattern
)

foreach ($p in $Paths) {
if ($p -match $Pattern) {
return $true
}
}

return $false
}

function Test-ExcludedPath {
param([string]$Path)

$patterns = @(
'^logs/',
'^tmp/',
'^temp/',
'^debug/',
'^scratch/',
'^artifacts/',
'^.pytest_cache/',
'^htmlcov/',
'^coverage/',
'(^|/)__pycache__/',
'.pyc$',
'.pyo$',
'^.env$',
'^.env.',
'^node_modules/'
)

foreach ($pattern in $patterns) {
if ($Path -match $pattern) {
return $true
}
}

return $false
}

$branch = (& git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne "logic-core-hardening") {
throw "Refusing to commit from branch '$branch'. Expected 'logic-core-hardening'."
}

Write-Host "Branch: $branch" -ForegroundColor Green
Write-Host ""
Write-Host "Current status:"
& git status --short

$changed = Get-ChangedPaths
if (-not $changed -or $changed.Count -eq 0) {
Write-Host "No changes to commit." -ForegroundColor Yellow
exit 0
}

$codeChanged = @($changed | Where-Object {
$_ -match '^(static/|tests/|scripts/)' -or $_ -eq 'server.py'
})

$docsChanged = @($changed | Where-Object {
$_ -match '^docs/.*.md$' -or $_ -eq 'README.md' -or $_ -eq 'static/sounds/CREDITS.md'
})

if ($codeChanged.Count -gt 0 -and $docsChanged.Count -eq 0 -and -not $AllowNoDocs) {
throw "Code changed but no docs changed. Update docs/AGENT_WORKFLOW.md or another relevant Markdown file, or rerun with -AllowNoDocs for a truly mechanical change."
}

if (Test-Path "logs") {
Write-Host ""
Write-Host "Cleaning generated logs..." -ForegroundColor Cyan
Get-ChildItem "logs" -File -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
}

$changed = Get-ChangedPaths

if (Test-AnyChanged $changed '^(static/sfx.js|tests/test_sfx_frontend.js)$') {
Run-Cmd node "tests/test_sfx_frontend.js"
}

if (Test-AnyChanged $changed '^(static/|tests/test_history_ui_static.py)$') {
Run-Cmd python "-m" "pytest" "tests/test_history_ui_static.py" "-q"
}

if (Test-AnyChanged $changed '^(server.py|static/sounds/|tests/test_sound_assets.py)$') {
Run-Cmd python "-m" "pytest" "tests/test_sound_assets.py" "-q"
}

if (Test-AnyChanged $changed '^(docs/AGENT_WORKFLOW.md|scripts/safe_commit.ps1|tests/test_workflow_docs.py)$') {
Run-Cmd python "-m" "pytest" "tests/test_workflow_docs.py" "-q"
}

if (-not $SkipFullTests) {
Run-Cmd python "-m" "pytest" "-q"
} else {
Write-Host ""
Write-Host "Skipping full test suite because -SkipFullTests was provided." -ForegroundColor Yellow
}

$changed = Get-ChangedPaths
$allowed = @()
$excluded = @()

foreach ($p in $changed) {
if (Test-ExcludedPath $p) {
$excluded += $p
} else {
$allowed += $p
}
}

if ($excluded.Count -gt 0) {
Write-Host ""
Write-Host "Excluded from staging:" -ForegroundColor Yellow
$excluded | ForEach-Object { Write-Host " $_" }
}

if ($allowed.Count -eq 0) {
Write-Host "No allowed files to stage." -ForegroundColor Yellow
exit 0
}

Write-Host ""
Write-Host "Staging allowed files:" -ForegroundColor Cyan
$allowed | ForEach-Object { Write-Host " $_" }

& git add -- $allowed
if ($LASTEXITCODE -ne 0) {
throw "git add failed"
}

Write-Host ""
Write-Host "Staged status:"
& git status --short

Run-Cmd git "commit" "-m" $Message

Write-Host ""
Write-Host "Commit complete. Push manually after browser review:" -ForegroundColor Green
Write-Host " git push origin logic-core-hardening"
