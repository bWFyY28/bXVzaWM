# Define a PowerShell function pointing here to use bxvzm from any directory.
$composePath = Join-Path $PSScriptRoot 'compose.yaml'
if ($args.Count -eq 1 -and $args[0] -eq '--stop-service') {
    & docker compose -f $composePath down
    exit $LASTEXITCODE
}
& docker compose -f $composePath up -d --build --wait app
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$execOptions = @('exec')
if ($args.Count -gt 0 -and $args[0] -ne 'open') { $execOptions += '-T' }
& docker compose -f $composePath @execOptions app bxvzm --config data/container-config.json @args
exit $LASTEXITCODE
