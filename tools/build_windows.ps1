param(
    [switch]$Fast,
    [switch]$Clean,
    [switch]$Ci,
    [switch]$Diagnose
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$App = 'Vacancy Parser Pro'
$Version = '4.9'
$NumericVersion = '4.9.0.0'
$Entry = 'vacancy_parser.py'
$PythonSeries = '3.13'
$PyInstallerVersion = '6.22.3'
$HooksVersion = '2026.7'
$PythonInstallerUrl = 'https://www.python.org/ftp/python/3.13.15/python-3.13.15-amd64.exe'
$PythonInstallerHash = 'edec09c4853aeae9ac36efb8c9f95b6b8e2fee65eee56d9767a8b7c69c574403'

$Venv = Join-Path $Root '.build-venv'
$BuildPython = Join-Path $Venv 'Scripts\python.exe'
$Work = Join-Path $Root '.build'
$Cache = Join-Path $Root '.build-cache'
$Logs = Join-Path $Root 'build_logs'
$Dist = Join-Path $Root 'dist'
$PreviousDist = Join-Path $Root 'dist_previous'
$Timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$LogPath = Join-Path $Logs "build_$Timestamp.log"
$SummaryPath = Join-Path $Logs 'last_build_summary.json'
$Stage = 'bootstrap'
$BasePython = $null
$GitCommit = 'source-archive'
$TranscriptStarted = $false

function Write-Step([string]$Message) {
    Write-Host "[$Stage] $Message"
}

function Remove-Safe([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Invoke-Native {
    param([string]$FilePath, [string[]]$Arguments, [string]$Label)
    Write-Host "[RUN] $Label"
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

function Invoke-Timed {
    param([string]$FilePath, [string[]]$Arguments, [int]$TimeoutSeconds, [string]$WorkingDirectory)
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -PassThru
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        try { $process.Kill() } catch { }
        throw "Timed out after $TimeoutSeconds seconds: $FilePath"
    }
    if ($process.ExitCode -ne 0) {
        throw "Packaged process failed with exit code $($process.ExitCode): $FilePath"
    }
}

function Test-PythonCandidate([string]$Executable) {
    try {
        $raw = & $Executable -c "import json,platform,sys; print(json.dumps({'exe':sys.executable,'series':f'{sys.version_info[0]}.{sys.version_info[1]}','version':platform.python_version(),'arch':platform.architecture()[0]}))" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }
        $info = ($raw | Select-Object -Last 1) | ConvertFrom-Json
        if ($info.series -ne $PythonSeries -or $info.arch -ne '64bit') { return $null }
        return [pscustomobject]@{ executable = [string]$info.exe; version = [string]$info.version }
    } catch {
        return $null
    }
}

function Find-Python {
    if ($env:pythonLocation) {
        $candidate = Join-Path $env:pythonLocation 'python.exe'
        if (Test-Path $candidate) {
            $result = Test-PythonCandidate $candidate
            if ($result) { return $result }
        }
    }
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        try {
            $candidate = & py.exe -3.13 -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $candidate) {
                $result = Test-PythonCandidate ($candidate | Select-Object -Last 1)
                if ($result) { return $result }
            }
        } catch { }
    }
    foreach ($candidate in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:ProgramFiles 'Python313\python.exe')
    )) {
        if (Test-Path $candidate) {
            $result = Test-PythonCandidate $candidate
            if ($result) { return $result }
        }
    }
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $result = Test-PythonCandidate $pythonCommand.Source
        if ($result) { return $result }
    }
    return $null
}

function Download-WithRetry([string]$Uri, [string]$Destination) {
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Write-Host "[DOWNLOAD] $Uri ($attempt/3)"
            Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $Destination -TimeoutSec 180
            return
        } catch {
            if ($attempt -eq 3) { throw }
            Start-Sleep -Seconds (2 * $attempt)
        }
    }
}

function Ensure-Python {
    $result = Find-Python
    if ($result) { return $result }
    if ($Ci) { throw 'Python 3.13 x64 is missing in CI; setup-python must provide it.' }

    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($winget) {
        try {
            & $winget.Source install --id Python.Python.3.13 -e --scope user --silent --accept-source-agreements --accept-package-agreements
            if ($LASTEXITCODE -eq 0) {
                $result = Find-Python
                if ($result) { return $result }
            }
        } catch { }
    }

    New-Item -ItemType Directory -Force -Path $Cache | Out-Null
    $installer = Join-Path $Cache 'python-3.13.15-amd64.exe'
    if (-not (Test-Path $installer)) { Download-WithRetry $PythonInstallerUrl $installer }
    $actualHash = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $PythonInstallerHash) {
        Remove-Item $installer -Force -ErrorAction SilentlyContinue
        throw 'Python installer SHA-256 mismatch.'
    }
    $process = Start-Process $installer -ArgumentList @('/quiet','InstallAllUsers=0','PrependPath=0','Include_launcher=1','Include_pip=1','Include_test=0','SimpleInstall=1') -PassThru -Wait
    if ($process.ExitCode -ne 0) { throw "Python installer failed with exit code $($process.ExitCode)" }
    $result = Find-Python
    if (-not $result) { throw 'Python installation finished but Python 3.13 x64 was not found.' }
    return $result
}

function Get-GitCommit {
    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if (-not $git) { return 'source-archive' }
    try {
        $value = & $git.Source -C $Root rev-parse HEAD 2>$null
        if ($LASTEXITCODE -eq 0 -and $value) { return ($value | Select-Object -Last 1).Trim() }
    } catch { }
    return 'source-archive'
}

function Write-Summary([string]$Status, [string]$ErrorText = $null, [string]$Artifact = $null) {
    New-Item -ItemType Directory -Force -Path $Logs | Out-Null
    [ordered]@{
        schema = 1; app = $App; app_version = $Version; status = $Status; stage = $Stage
        error = $ErrorText; artifact = $Artifact; generated_at_utc = [DateTime]::UtcNow.ToString('o')
        git_commit = $GitCommit; python = if ($BasePython) { $BasePython.version } else { $null }
        pyinstaller = $PyInstallerVersion; fast = [bool]$Fast; clean = [bool]$Clean; ci = [bool]$Ci; diagnose = [bool]$Diagnose
    } | ConvertTo-Json -Depth 4 | Set-Content $SummaryPath -Encoding UTF8
}

function Assert-Preflight {
    $script:Stage = 'preflight'
    Write-Step 'Checking Windows x64, resources, write access and disk space...'
    if ($env:OS -ne 'Windows_NT') { throw 'Windows only.' }
    if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { throw "x64 release build required; detected $env:PROCESSOR_ARCHITECTURE" }
    foreach ($file in @($Entry,'vacancy_gui.py','job_scraper.py','problem_logging.py','requirements.txt','icon.ico')) {
        if (-not (Test-Path (Join-Path $Root $file))) { throw "Missing required file: $file" }
    }
    $probe = Join-Path $Root '.build_probe.tmp'
    try { 'ok' | Set-Content $probe -Encoding ASCII } finally { Remove-Item $probe -Force -ErrorAction SilentlyContinue }
    $drive = Get-PSDrive -Name (([IO.Path]::GetPathRoot($Root)).Substring(0,1))
    if ($drive.Free -lt 3GB) { throw 'At least 3 GB free disk space is required.' }
    Write-Host "[INFO] Free space: $([Math]::Round($drive.Free / 1GB, 2)) GB"
}

function Prepare-Toolchain {
    $script:Stage = 'toolchain'
    if ($Clean) { Remove-Safe $Venv; Remove-Safe $Cache; Remove-Safe $Work }
    $script:BasePython = Ensure-Python
    Write-Host "[INFO] Python: $($BasePython.version) at $($BasePython.executable)"
    if ($Diagnose) { return }

    if (Test-Path $BuildPython) {
        if (-not (Test-PythonCandidate $BuildPython)) { Remove-Safe $Venv }
    }
    if (-not (Test-Path $BuildPython)) {
        Invoke-Native $BasePython.executable @('-m','venv',$Venv) 'Create build venv'
    }

    $marker = Join-Path $Venv '.toolchain-id'
    $runtimeRequirements = (Get-Content 'requirements.txt' -Raw).Trim()
    $expected = "$runtimeRequirements`npyinstaller==$PyInstallerVersion`npyinstaller-hooks-contrib==$HooksVersion"
    $current = if (Test-Path $marker) { (Get-Content $marker -Raw).Trim() } else { '' }
    if (-not $Fast -or $current -ne $expected) {
        Invoke-Native $BuildPython @('-m','pip','install','--disable-pip-version-check','--no-input','--timeout','60','--retries','2','-r','requirements.txt') 'Install runtime dependencies'
        Invoke-Native $BuildPython @('-m','pip','install','--disable-pip-version-check','--no-input','--timeout','60','--retries','2',"pyinstaller==$PyInstallerVersion","pyinstaller-hooks-contrib==$HooksVersion") 'Install build toolchain'
        $expected | Set-Content $marker -Encoding UTF8
    }
    Invoke-Native $BuildPython @('-m','pip','check') 'pip check'
}

function New-Metadata {
    $script:Stage = 'metadata'
    $directory = Join-Path $Work 'metadata'
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $manifest = Join-Path $directory 'app.manifest'
    $versionFile = Join-Path $directory 'version.txt'
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0"><assemblyIdentity version="4.9.0.0" processorArchitecture="amd64" name="Vacancy.Parser.Pro" type="win32"/><trustInfo xmlns="urn:schemas-microsoft-com:asm.v3"><security><requestedPrivileges><requestedExecutionLevel level="asInvoker" uiAccess="false"/></requestedPrivileges></security></trustInfo><application xmlns="urn:schemas-microsoft-com:asm.v3"><windowsSettings><dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">PerMonitorV2,PerMonitor</dpiAwareness><longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware></windowsSettings></application></assembly>' | Set-Content $manifest -Encoding UTF8
    "VSVersionInfo(ffi=FixedFileInfo(filevers=(4,9,0,0),prodvers=(4,9,0,0),mask=0x3f,flags=0x0,OS=0x40004,fileType=0x1,subtype=0x0,date=(0,0)),kids=[StringFileInfo([StringTable('040904B0',[StringStruct('CompanyName','Dmitry Kolesnichenko'),StringStruct('FileDescription','Vacancy Parser Pro'),StringStruct('FileVersion','4.9.0.0'),StringStruct('OriginalFilename','Vacancy Parser Pro.exe'),StringStruct('ProductName','Vacancy Parser Pro'),StringStruct('ProductVersion','4.9')])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])" | Set-Content $versionFile -Encoding UTF8
    return [pscustomobject]@{ manifest = $manifest; version = $versionFile }
}

function Invoke-SourceVerification {
    $script:Stage = 'source-verification'
    Invoke-Native $BuildPython @('-m','compileall','-q','vacancy_parser.py','vacancy_gui.py','job_scraper.py','problem_logging.py','tests') 'Compile sources'
    Invoke-Native $BuildPython @('-m','unittest','discover','-s','tests','-v') 'Unit tests'
    Invoke-Native $BuildPython @($Entry,'--self-test') 'Source self-test'
}

function New-Package($Metadata) {
    $script:Stage = 'pyinstaller'
    $stageDist = Join-Path $Work 'stage-dist'; $workPath = Join-Path $Work 'pyinstaller-work'; $specPath = Join-Path $Work 'spec'
    Remove-Safe $stageDist; if (-not $Fast) { Remove-Safe $workPath }; Remove-Safe $specPath
    New-Item -ItemType Directory -Force -Path $stageDist,$workPath,$specPath | Out-Null
    $arguments = @('-m','PyInstaller','--noconfirm','--onefile','--windowed','--noupx','--name',$App,'--icon','icon.ico','--distpath',$stageDist,'--workpath',$workPath,'--specpath',$specPath,'--manifest',$Metadata.manifest,'--version-file',$Metadata.version)
    if (-not $Fast) { $arguments += '--clean' }
    $arguments += $Entry
    Invoke-Native $BuildPython $arguments 'PyInstaller package'
    $exe = Join-Path $stageDist "$App.exe"
    if (-not (Test-Path $exe)) { throw 'Expected EXE was not created.' }
    if ((Get-Item $exe).Length -lt 15MB) { throw 'EXE is unexpectedly small; refusing to publish an incomplete build.' }
    return $exe
}

function Test-Package([string]$Exe) {
    $script:Stage = 'packaged-self-test'
    $directory = Split-Path $Exe -Parent
    Copy-Item 'icon.ico' (Join-Path $directory 'icon.ico') -Force
    Invoke-Timed $Exe @('--self-test') 90 $directory

    $script:Stage = 'portable-folder-test'
    $temp = Join-Path $env:TEMP ('Проверка Vacancy Parser ' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $temp | Out-Null
    try {
        Copy-Item $Exe (Join-Path $temp "$App.exe")
        Copy-Item 'icon.ico' (Join-Path $temp 'icon.ico')
        Invoke-Timed (Join-Path $temp "$App.exe") @('--self-test') 90 $temp
    } finally { Remove-Safe $temp }
}

function Publish-Package([string]$Exe) {
    $script:Stage = 'distribution'
    $package = Join-Path $Work 'package'; $final = Join-Path $Work 'final-dist'
    Remove-Safe $package; Remove-Safe $final
    New-Item -ItemType Directory -Force -Path $package,$final | Out-Null
    $packagedExe = Join-Path $package "$App.exe"
    Copy-Item $Exe $packagedExe; Copy-Item 'icon.ico' (Join-Path $package 'icon.ico')
    $exeHash = (Get-FileHash $packagedExe -Algorithm SHA256).Hash.ToLowerInvariant()
    $script:GitCommit = Get-GitCommit
    [ordered]@{schema=1;app=$App;app_version=$Version;artifact_type='onefile-portable-x64';built_at_utc=[DateTime]::UtcNow.ToString('o');git_commit=$GitCommit;python=$BasePython.version;pyinstaller=$PyInstallerVersion;architecture='x64';exe="$App.exe";exe_sha256=$exeHash;resources=@('icon.ico');verification=@('compile','unit-tests','source-self-test','packaged-self-test','portable-folder-test','zip-extract-self-test')} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $package 'build_info.json') -Encoding UTF8
    $zipName = 'Vacancy-Parser-Pro-portable-x64.zip'; $zip = Join-Path $Work $zipName
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    Compress-Archive -Path (Join-Path $package '*') -DestinationPath $zip -CompressionLevel Optimal

    $script:Stage = 'zip-verification'
    $temp = Join-Path $env:TEMP ('Проверка ZIP Vacancy Parser ' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $temp | Out-Null
    try {
        Expand-Archive $zip $temp -Force
        $zipExe = Join-Path $temp "$App.exe"
        if ((Get-FileHash $zipExe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $exeHash) { throw 'ZIP EXE hash mismatch.' }
        if (-not (Test-Path (Join-Path $temp 'icon.ico'))) { throw 'ZIP icon.ico is missing.' }
        Invoke-Timed $zipExe @('--self-test') 90 $temp
    } finally { Remove-Safe $temp }

    $zipHash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    Copy-Item $packagedExe (Join-Path $final "$App.exe")
    Copy-Item 'icon.ico' (Join-Path $final 'icon.ico')
    Copy-Item (Join-Path $package 'build_info.json') (Join-Path $final 'build_info.json')
    Copy-Item $zip (Join-Path $final $zipName)
    @("$exeHash *$App.exe", "$zipHash *$zipName") | Set-Content (Join-Path $final 'SHA256SUMS.txt') -Encoding ASCII

    $script:Stage = 'atomic-publish'
    Remove-Safe $PreviousDist
    if (Test-Path $Dist) { Move-Item $Dist $PreviousDist }
    try { Move-Item $final $Dist } catch {
        if ((-not (Test-Path $Dist)) -and (Test-Path $PreviousDist)) { Move-Item $PreviousDist $Dist }
        throw
    }
    return (Join-Path $Dist "$App.exe")
}

$exitCode = 0
try {
    New-Item -ItemType Directory -Force -Path $Logs | Out-Null
    Get-ChildItem $Logs -Filter 'build_*.log' -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -Skip 20 | Remove-Item -Force -ErrorAction SilentlyContinue
    try { Start-Transcript $LogPath -Force | Out-Null; $TranscriptStarted = $true } catch { }
    $GitCommit = Get-GitCommit
    Assert-Preflight
    Prepare-Toolchain
    if ($Diagnose) {
        $Stage = 'diagnose-complete'; Write-Summary 'diagnose-ok'; Write-Host '[OK] Diagnostic preflight completed.'
    } else {
        New-Item -ItemType Directory -Force -Path $Work | Out-Null
        $metadata = New-Metadata
        Invoke-SourceVerification
        $exe = New-Package $metadata
        Test-Package $exe
        $artifact = Publish-Package $exe
        $Stage = 'complete'
        Write-Summary 'success' $null $artifact
        Write-Host ''; Write-Host '[OK] READY BUILD CREATED AND VERIFIED'; Write-Host "EXE: $artifact"; Write-Host "ZIP: $(Join-Path $Dist 'Vacancy-Parser-Pro-portable-x64.zip')"
    }
} catch {
    $exitCode = 1
    $message = $_.Exception.Message
    Write-Host "[ERROR] Build failed at '$Stage': $message" -ForegroundColor Red
    try { Write-Summary 'failed' $message } catch { }
    Write-Host '[INFO] Existing dist was not replaced by an unverified candidate.'
} finally {
    if ($TranscriptStarted) { try { Stop-Transcript | Out-Null } catch { } }
}
exit $exitCode
